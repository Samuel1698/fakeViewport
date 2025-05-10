import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))
import logging
import logging.handlers
# stub out the rotating‐file handler before viewport.py ever sees it
logging.handlers.TimedRotatingFileHandler = lambda *args, **kwargs: logging.NullHandler()

import pytest
import os
from io import StringIO
from datetime import datetime, time as dt_time
import time 
from webdriver_manager.core.os_manager import ChromeType
import viewport
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, call
import signal
import subprocess
# helper to build a fake psutil.Process‐like object
def _make_proc(pid, cmdline, uids=None, name=None):
    if isinstance(cmdline, str):
        cmdline = cmdline.split()
    if name is None:
        name = cmdline[0] if cmdline else f"proc{pid}"

    proc = MagicMock()
    info = {
        "pid": pid,
        "cmdline": cmdline,
        "uids": uids or SimpleNamespace(real=1000),
        "name": name,
    }
    proc.info = info
    return proc
@pytest.fixture(autouse=True)
def isolate_sst(tmp_path, monkeypatch):
    # redirect every test’s sst_file into tmp_path/…
    fake = tmp_path / "sst.txt"
    fake.write_text("2025-01-01 00:00:00.000000")  # or leave empty
    monkeypatch.setattr(viewport, "sst_file", fake)
# -------------------------------------------------------------------------
# Test for Singal Handler
# -------------------------------------------------------------------------
@patch("viewport.logging")
@patch("viewport.api_status")
@patch("viewport.sys.exit")
def test_signal_handler_calls_exit(mock_exit, mock_api_status, mock_logging):
    mock_driver = MagicMock()

    # Call the signal handler manually
    viewport.signal_handler(signum=2, frame=None, driver=mock_driver)

    # Assertions
    mock_driver.quit.assert_called_once()
    mock_logging.info.assert_any_call(f"Gracefully shutting down {viewport.BROWSER}.")
    mock_logging.info.assert_any_call("Gracefully shutting down script instance.")
    mock_api_status.assert_called_once_with("Stopped ")
    mock_exit.assert_called_once_with(0)
# -------------------------------------------------------------------------
# Tests for screenshot handler
# -------------------------------------------------------------------------
@pytest.mark.parametrize("file_ages_days, expected_deleted", [
    ([10, 5, 1], ["screenshot_0.png", "screenshot_1.png"]),  # 10 and 5 days old, delete if cutoff is 2
    ([1, 0.5], []),  # recent files, none deleted
])
def test_screenshot_handler(tmp_path, file_ages_days, expected_deleted, monkeypatch):
    # Arrange
    max_age_days = 2
    now = time.time()

    created_files = []
    for i, age in enumerate(file_ages_days):
        file = tmp_path / f"screenshot_{i}.png"
        file.write_text("dummy")
        os.utime(file, (now - age * 86400, now - age * 86400))
        created_files.append(file)

    mock_info = MagicMock()
    mock_api_status = MagicMock()
    mock_log_error = MagicMock()

    monkeypatch.setattr(logging, "info", mock_info)
    monkeypatch.setattr(viewport, "api_status", mock_api_status)
    monkeypatch.setattr(viewport, "log_error", mock_log_error)

    # Act
    viewport.screenshot_handler(tmp_path, max_age_days)

    # Assert
    deleted_names = [f.name for f in created_files if not f.exists()]
    assert sorted(deleted_names) == sorted(expected_deleted)
    assert mock_info.call_count == len(expected_deleted)
    assert mock_api_status.call_count == len(expected_deleted)
    mock_log_error.assert_not_called() 
def test_screenshot_handler_unlink_raises(tmp_path, monkeypatch):
    import time
    from pathlib import Path

    # Arrange
    file = tmp_path / "screenshot_fail.png"
    file.write_text("dummy")
    os.utime(file, (time.time() - 10 * 86400, time.time() - 10 * 86400))  # definitely old

    mock_info = MagicMock()
    mock_api_status = MagicMock()
    mock_log_error = MagicMock()

    class BadFile:
        def __init__(self, path):
            self._path = path
            self.name = path.name
        def stat(self):
            return type('stat', (), {'st_mtime': time.time() - 10 * 86400})()
        def unlink(self):
            raise OSError("unlink failed")

    monkeypatch.setattr(logging, "info", mock_info)
    monkeypatch.setattr(viewport, "api_status", mock_api_status)
    monkeypatch.setattr(viewport, "log_error", mock_log_error)
    monkeypatch.setattr(Path, "glob", lambda self, pattern: [BadFile(file)] if pattern == "screenshot_*.png" else [])

    # Act
    viewport.screenshot_handler(tmp_path, max_age_days=2)

    # Assert
    mock_info.assert_not_called()
    mock_api_status.assert_not_called()
    mock_log_error.assert_called_once()
    assert "unlink failed" in str(mock_log_error.call_args[0][1])
# -------------------------------------------------------------------------
# Test for usage_handler
# -------------------------------------------------------------------------
@patch("viewport.psutil.process_iter")
def test_usage_handler_sums_matching_procs(mock_process_iter):
    # Arrange
    p1 = _make_proc(1, ["python", "target_app.py"])
    p2 = _make_proc(2, ["other_process", "target_app", "--debug"])
    p3 = _make_proc(3, ["bash", "-c", "something"], name="not_relevant")

    # Add cpu_percent and memory_info behavior
    for proc in [p1, p2]:
        proc.cpu_percent.return_value = 7.5
        proc.memory_info.return_value = MagicMock(rss=200000)

    p3.cpu_percent.return_value = 1.0
    p3.memory_info.return_value = MagicMock(rss=50000)

    mock_process_iter.return_value = [p1, p2, p3]

    # Act
    cpu, mem = viewport.usage_handler("target")

    # Assert
    assert cpu == 15.0  # 7.5 + 7.5
    assert mem == 400000  # 200k + 200k
@patch("viewport.psutil.process_iter")
def test_usage_handler_ignores_exceptions(mock_process_iter):
    # One matching proc, one that raises
    p1 = _make_proc(1, ["target_app"])
    p1.cpu_percent.return_value = 10.0
    p1.memory_info.return_value = MagicMock(rss=100000)

    broken = _make_proc(2, ["target_app"])
    broken.cpu_percent.side_effect = Exception("denied")

    mock_process_iter.return_value = [p1, broken]

    cpu, mem = viewport.usage_handler("target")
    assert cpu == 10.0
    assert mem == 100000
# -------------------------------------------------------------------------
# Test for Status Handler
# -------------------------------------------------------------------------
@pytest.mark.parametrize(
    "sst_exists, status_exists, log_content, process_names, expected_error, expected_output_snippets",
    [
        # 1) All present → full status block, no errors
        (
            True, True, "[INFO] All good", ["viewport.py"],
            None,
            [
                "Fake Viewport 1.2.3",
                "Script Uptime:",
                "Monitoring API:",
                "Usage:",
                "Next Health Check:",
                "Last Status Update:",
                "Last Log Entry:",
            ],
        ),
        # 2) Missing sst.txt → fallback to now, still prints uptime, no error
        (
            False, True, "[INFO] OK", ["viewport.py"],
            None,
            [
                "Script Uptime:",
                "Monitoring API:",
            ],
        ),
        # 3) Missing status.txt → prints “Status file not found.” + logs error
        (
            True, False, "[INFO] OK", ["viewport.py"],
            "Status File not found",
            ["Status file not found."],
        ),
        # 4) Missing log file → prints “Log file not found.” + logs error
        (
            True, True, None, ["viewport.py"],
            "Log File not found",
            ["Log file not found."],
        ),
        # 5) Empty log file → prints “No log entries yet.”, no error
        (
            True, True, "", ["viewport.py"],
            None,
            ["Last Log Entry:", "No log entries yet."],
        ),
        # 6) Script not running → uptime shows “Not Running”
        (
            True, True, "[INFO] OK", [], 
            None,
            ["Script Uptime:", "Not Running"],
        ),
    ]
)
@patch("viewport.time.time", return_value=0)
@patch("viewport.get_next_interval", return_value=60)
@patch("viewport.psutil.virtual_memory")
@patch("viewport.psutil.process_iter", return_value=[])
@patch("viewport.process_handler")
@patch("builtins.open")
@patch("viewport.log_error")
def test_status_handler_various(
    mock_log_error,
    mock_open,
    mock_process_handler,
    mock_process_iter,
    mock_virtual_memory,
    mock_get_next_interval,
    mock_time_time,
    sst_exists,
    status_exists,
    log_content,
    process_names,
    expected_error,
    expected_output_snippets,
    capsys
):
    # Stub total RAM to 1 GB
    mock_virtual_memory.return_value = MagicMock(total=1024**3)

    # Point viewport at simple filenames and fixed config
    viewport.sst_file       = "sst.txt"
    viewport.status_file    = "status.txt"
    viewport.log_file       = "viewport.log"
    viewport.viewport_version = "1.2.3"
    viewport.SLEEP_TIME     = 60
    viewport.LOG_INTERVAL   = 10

    # Prepare our fake file‐handles
    sst_data = StringIO(
        datetime(2024, 4, 25, 12, 0, 0).strftime("%Y-%m-%d %H:%M:%S.%f")
    ) if sst_exists else None
    status_data = StringIO("Feed Healthy") if status_exists else None

    def open_side_effect(path, *args, **kwargs):
        p = str(path)
        if p == viewport.sst_file:
            if not sst_exists:
                raise FileNotFoundError
            return StringIO(sst_data.getvalue())
        if p == viewport.status_file:
            if not status_exists:
                raise FileNotFoundError
            return StringIO(status_data.getvalue())
        if p == viewport.log_file:
            if log_content is None:
                raise FileNotFoundError
            return StringIO(log_content)
        raise FileNotFoundError

    mock_open.side_effect = open_side_effect
    mock_process_handler.side_effect = lambda name, action="check": name in process_names

    # Run the handler
    viewport.status_handler()
    out = capsys.readouterr().out

    if expected_error:
        mock_log_error.assert_called_once()
        assert expected_error in mock_log_error.call_args[0][0]
    else:
        mock_log_error.assert_not_called()

    for snippet in expected_output_snippets:
        assert snippet in out
# -------------------------------------------------------------------------
# Test for Process Handler
# -------------------------------------------------------------------------
@pytest.mark.parametrize(
    "proc_list, current_pid, name, action, expected_result, expected_kill_calls, expected_api_calls, expected_log_info",
    [
        # Process Running
        # Current PID, Name to, Check, Exists?
        # Expected Kill Calls, Expected API Calls

        # No process, 'viewport', check, Not Present
        (
            [], 
            100, "viewport.py", "check", False, 
            [], [], []
        ),

        # Only Self Viewport Process running
        # 'viewport', 'check', Should be False
        (
            [_make_proc(100, ["viewport.py"])],
            100, "viewport.py", "check", False, 
            [], [], []
        ),

        # Different Viewport Process running
        # 'viewport', 'check', Should be True
        (
            [_make_proc(1, ["python", "viewport.py"])],
            100, "viewport.py", "check", True, 
            [], [], []
        ),

        # Different commandline process with argument
        # 'viewport', 'check', Should be True
        (
            [_make_proc(10, ["/usr/bin/viewport.py", "--foo"])], 
            0, "viewport.py", "check", True, 
            [], [], []
        ),

        # No Process Running = None to kill
        # 'viewport', 'kill', Should be False
        (
            [], 
            200, "viewport.py", "kill", False, 
            [], [], []
        ),

        # Only Self Viewport Process Runnning = Do not Kill
        # 'viewport', 'kill', Should be False
        (
            [_make_proc(200, ["viewport.py"])], 
            200, "viewport.py", "kill", False, 
            [], [], []
        ),

        # Chrome Processes (2, 3) running in backgrond
        # 'chrome', 'kill', If killed should return False
        # Process 2 and 3 gets SIGTERM, API Call should be:
        (
            [_make_proc(2, ["chrome"]),
             _make_proc(3, ["chrome"])], 
            999, "chrome", "kill", False,
            [(2, signal.SIGKILL), (3, signal.SIGKILL)], ["Killed process 'chrome'"], ["Killed process 'chrome' with PIDs: 2, 3"]
        ),

        # Chromium Process (2, 3) running in backgrond
        # 'chromium', 'kill', If killed should return False
        # Process 2 and 3 get SIGKILL, API Call should be:
        (
            [_make_proc(2, ["chromium"]),
             _make_proc(3, ["chromium"])], 
            999, "chromium", "kill", False,
            [(2, signal.SIGKILL), (3, signal.SIGKILL)], ["Killed process 'chromium'"], ["Killed process 'chromium' with PIDs: 2, 3"]
        ),

        # Multiple viewport instances running in background, separate from current instance
        # 'viewport', 'kill', If killed should return False
        # Process 2 and 3 get SIGKILL, API Call should be:
        (   
            [_make_proc(2, ["viewport.py"]),
             _make_proc(3, ["viewport.py"]),
             _make_proc(4, ["other"])], 
            999, "viewport.py", "kill", False,
            [(2, signal.SIGKILL), (3, signal.SIGKILL)], ["Killed process 'viewport.py'"], ["Killed process 'viewport.py' with PIDs: 2, 3"]
        ),
        # One other viewport instance running in background
        # 'viewport', 'kill', If killed should return False
        # Process 2, API Call should be:
        (   
            [_make_proc(2, ["viewport.py"]),
             _make_proc(3, ["other"])], 
            999, "viewport.py", "kill", False,
            [(2, signal.SIGKILL)], ["Killed process 'viewport.py'"], ["Killed process 'viewport.py' with PIDs: 2"]
        ),
        # Firefox main + root-owned helper: should kill only the main (uid == me)
        (
            [
                # main firefox, owned by us
                _make_proc(2, ["firefox"], uids=SimpleNamespace(real=1000)),
                # helper, owned by root → should be ignored
                _make_proc(3, ["firefox"], uids=SimpleNamespace(real=0)),
            ],
            999, "firefox", "kill", False,
            # only pid 2 gets SIGKILL
            [(2, signal.SIGKILL)],
            # api_status should be called with this message
            ["Killed process 'firefox'"],
            # logging.info with this
            ["Killed process 'firefox' with PIDs: 2"]
        ),
    ]
)
@patch("viewport.logging.info")
@patch("viewport.psutil.process_iter")
@patch("viewport.os.geteuid")
@patch("viewport.os.getpid")
@patch("viewport.os.kill")
@patch("viewport.api_status")
def test_process_handler(
    mock_api, mock_kill, mock_getpid, mock_geteuid, mock_iter, mock_log_info,
    proc_list, current_pid, name, action,
    expected_result, expected_kill_calls, expected_api_calls, expected_log_info
):
    # arrange
    mock_geteuid.return_value = 1000
    mock_iter.return_value = iter(proc_list)
    mock_getpid.return_value = current_pid

    # act
    result = viewport.process_handler(name, action=action)

    # assert return value
    assert result is expected_result

    # assert os.kill calls
    if expected_kill_calls:
        assert mock_kill.call_count == len(expected_kill_calls)
        for pid, sig in expected_kill_calls:
            mock_kill.assert_any_call(pid, sig)
    else:
        mock_kill.assert_not_called()
    
    # Assert logging.info calls
    if expected_log_info:
        for msg in expected_log_info:
            mock_log_info.assert_any_call(msg)
    else:
        mock_log_info.assert_not_called()
    # assert api_status calls
    if expected_api_calls:
        assert mock_api.call_args_list == [call(msg) for msg in expected_api_calls]
    else:
        mock_api.assert_not_called()
# -------------------------------------------------------------------------
# Test for Service Handler
# -------------------------------------------------------------------------
@patch("viewport.ChromeDriverManager")
def test_service_handler_installs_chrome_driver_google(mock_chrome_driver_manager):
    # Reset the cached path
    viewport._chrome_driver_path = None
    # Simulate a Google-Chrome binary
    viewport.BROWSER_BINARY = "/usr/bin/google-chrome-stable"

    # Stub out the installer
    mock_installer = MagicMock()
    mock_installer.install.return_value = "/fake/path/to/chromedriver"
    mock_chrome_driver_manager.return_value = mock_installer

    path = viewport.service_handler()

    assert path == "/fake/path/to/chromedriver"
    mock_chrome_driver_manager.assert_called_once_with(chrome_type=ChromeType.GOOGLE)
    mock_installer.install.assert_called_once()
@patch("viewport.ChromeDriverManager")
def test_service_handler_installs_chrome_driver_chromium(mock_chrome_driver_manager):
    # Reset the cached path
    viewport._chrome_driver_path = None
    # Simulate a Chromium binary
    viewport.BROWSER_BINARY = "/usr/lib/chromium/chromium"

    # Stub out the installer
    mock_installer = MagicMock()
    mock_installer.install.return_value = "/fake/path/to/chromedriver-chromium"
    mock_chrome_driver_manager.return_value = mock_installer

    path = viewport.service_handler()

    assert path == "/fake/path/to/chromedriver-chromium"
    mock_chrome_driver_manager.assert_called_once_with(chrome_type=ChromeType.CHROMIUM)
    mock_installer.install.assert_called_once()
@patch("viewport.ChromeDriverManager")
def test_service_handler_reuses_existing_path(mock_chrome_driver_manager):
    # Pre-seed the cache
    viewport._chrome_driver_path = "/already/installed/driver"

    path = viewport.service_handler()

    assert path == "/already/installed/driver"
    mock_chrome_driver_manager.assert_not_called()
# -------------------------------------------------------------------------
# Test for browser_handler  
# -------------------------------------------------------------------------
@pytest.mark.parametrize(
    "browser, side_effects, expected_driver_get_calls, expected_kill_calls, expect_restart",
    [
        # Chrome cases
        ("chrome",  [MagicMock()],                    1, 1, False),
        ("chrome",  [Exception("boom"), MagicMock()], 1, 1, False),
        ("chrome",  [Exception("fail")] * 3,         0, 2, True),
        # Chrome cases
        ("chromium",  [MagicMock()],                    1, 1, False),
        ("chromium",  [Exception("boom"), MagicMock()], 1, 1, False),
        ("chromium",  [Exception("fail")] * 3,         0, 2, True),
        # Firefox cases
        ("firefox", [MagicMock()],                    1, 1, False),
        ("firefox", [Exception("boom"), MagicMock()], 1, 1, False),
        ("firefox", [Exception("fail")] * 3,         0, 2, True),
    ]
)
@patch("viewport.restart_handler")
@patch("viewport.process_handler")
@patch("viewport.FirefoxOptions")
@patch("viewport.FirefoxProfile")
@patch("viewport.FirefoxService")
@patch("viewport.GeckoDriverManager")
@patch("viewport.Options")
@patch("viewport.webdriver.Firefox")
@patch("viewport.webdriver.Chrome")
@patch("viewport.time.sleep", return_value=None)
@patch("viewport.api_status")
@patch("viewport.log_error")
def test_browser_handler_extended(
    mock_log_error,
    mock_api_status,
    mock_sleep,
    mock_chrome,
    mock_firefox,
    mock_options,
    mock_gecko_mgr,
    mock_ff_service,
    mock_ff_profile,
    mock_ff_opts,
    mock_process_handler,
    mock_restart_handler,
    monkeypatch,               
    browser,
    side_effects,
    expected_driver_get_calls,
    expected_kill_calls,
    expect_restart,
):
    url = "http://example.com"

    # temporarily override module‐globals for *this* test only
    monkeypatch.setattr(viewport, "BROWSER", browser)
    monkeypatch.setattr(viewport, "MAX_RETRIES", 3)
    monkeypatch.setattr(viewport, "SLEEP_TIME", 10)

    mock_driver = MagicMock()
    # build side effect for Chrome/Firefox
    effects = [e if isinstance(e, Exception) else mock_driver
               for e in side_effects]

    if browser in ("chrome", "chromium"):
        mock_chrome.side_effect = effects
        mock_options.return_value = MagicMock()
    else:
        mock_firefox.side_effect = effects
        mock_ff_opts.return_value     = MagicMock()
        mock_ff_profile.return_value  = MagicMock()
        mock_gecko_mgr.return_value.install.return_value = "/fake/gecko"
        mock_ff_service.return_value = MagicMock()

    # Act
    result = viewport.browser_handler(url)

    # Assert kill calls
    assert mock_process_handler.call_count == expected_kill_calls
    mock_process_handler.assert_any_call(browser, action="kill")

    # Assert constructor calls
    if browser in ("chrome", "chromium"):
        assert mock_chrome.call_count == len(side_effects)
    else:
        assert mock_firefox.call_count == len(side_effects)

    # .get/url and return value
    if expected_driver_get_calls:
        mock_driver.get.assert_called_once_with(url)
        assert result is mock_driver
    else:
        assert result is None

    # restart_handler only on permanent failure
    if expect_restart:
        mock_restart_handler.assert_called_once_with(driver=None)
    else:
        mock_restart_handler.assert_not_called()

    # log_error count
    error_count = sum(isinstance(e, Exception) for e in side_effects)
    min_errors = error_count - (1 if expect_restart else 0)
    assert mock_log_error.call_count >= min_errors
# -------------------------------------------------------------------------
# Tests for browser_restart_handler
# -------------------------------------------------------------------------
@pytest.mark.parametrize(
    "chrome_exc,    check_exc,     handle_page_ret, "
    "should_sleep,  should_feed_ok, should_return, "
    "should_log_err, should_raise, expected_api_calls",
    [
        # 1) Success, handle_page=True
        (
            None, None, True,
            True, True, True,
            False, False,
            [call(f"Restarting {viewport.BROWSER}"), call("Feed Healthy")],
        ),
        # 2) Success, handle_page=False
        (
            None, None, False,
            False, False, True,
            False, False,
            [call(f"Restarting {viewport.BROWSER}")],
        ),
        # 3) browser_handler throws
        (
            Exception("boom"), None, None,
            False, False, False,
            True, True,
            [call(f"Restarting {viewport.BROWSER}"), call(f"Error Killing {viewport.BROWSER}")],
        ),
        # 4) check_for_title throws
        (
            None, Exception("oops"), None,
            False, False, False,
            True, True,
            [call(f"Restarting {viewport.BROWSER}"), call(f"Error Killing {viewport.BROWSER}")],
        ),
    ]
)
@patch("viewport.time.sleep", return_value=None)
@patch("viewport.logging.info")
@patch("viewport.api_status")
@patch("viewport.log_error")
@patch("viewport.handle_page")
@patch("viewport.check_for_title")
@patch("viewport.browser_handler")
def test_browser_restart_handler(
    mock_browser_handler,
    mock_check_for_title,
    mock_handle_page,
    mock_log_error,
    mock_api_status,
    mock_log_info,
    mock_sleep,
    chrome_exc,
    check_exc,
    handle_page_ret,
    should_sleep,
    should_feed_ok,
    should_return,
    should_log_err,
    should_raise,
    expected_api_calls,
):
    url = "http://example.com"
    fake_driver = MagicMock()

    # wire up browser_handler
    if chrome_exc:
        mock_browser_handler.side_effect = chrome_exc
    else:
        mock_browser_handler.return_value = fake_driver

    # wire up check_for_title
    if check_exc:
        mock_check_for_title.side_effect = check_exc

    # wire up handle_page
    mock_handle_page.return_value = handle_page_ret

    # Act
    if should_raise:
        with pytest.raises(Exception):
            viewport.browser_restart_handler(url)
    else:
        result = viewport.browser_restart_handler(url)

    # Always start by logging & api_status "Restarting BROWSER"
    mock_log_info.assert_any_call(f"Restarting {viewport.BROWSER}...")
    mock_api_status.assert_any_call(f"Restarting {viewport.BROWSER}")

    # Check the full sequence of api_status calls
    assert mock_api_status.call_args_list == expected_api_calls

    # Sleep only when handle_page returned True and no exception
    assert mock_sleep.called == should_sleep

    # "Page successfully reloaded." only when handle_page was True and no exception
    if should_feed_ok:
        mock_log_info.assert_any_call("Page successfully reloaded.")
    else:
        assert not any("Page successfully reloaded." in args[0][0]
                       for args in mock_log_info.call_args_list)

    # Return driver only on full success
    if not should_raise:
        if should_return:
            assert result is fake_driver
        else:
            assert result is None

    # log_error only on exception paths
    assert mock_log_error.called == should_log_err
# -------------------------------------------------------------------------
# Tests for restart_scheduler
# -------------------------------------------------------------------------
def test_restart_scheduler_triggers_api_and_restart(monkeypatch):
    # 1) Fix "now" at 2025-05-08 12:00:00
    fixed_now = datetime(2025, 5, 8, 12, 0, 0)

    # Create a subclass so we can override now(), but inherit combine()/time() etc.
    class DummyDateTime(datetime):
        @classmethod
        def now(cls):
            return fixed_now

    # 2) Patch in our DummyDateTime and a single RESTART_TIME at 12:00:10
    monkeypatch.setattr(viewport, 'datetime', DummyDateTime)
    monkeypatch.setattr(viewport, 'RESTART_TIMES', [dt_time(12, 0, 10)])

    # 3) Capture the sleep duration
    sleep_calls = []
    monkeypatch.setattr(viewport.time, 'sleep', lambda secs: sleep_calls.append(secs))

    # 4) Capture api_status calls
    api_calls = []
    monkeypatch.setattr(viewport, 'api_status', lambda msg: api_calls.append(msg))

    # 5) Stub restart_handler to record the driver and then raise to break the loop
    restart_calls = []
    def fake_restart(driver):
        restart_calls.append(driver)
        raise StopIteration
    monkeypatch.setattr(viewport, 'restart_handler', fake_restart)

    dummy_driver = object()

    # Act: we expect StopIteration to bubble out after one iteration
    with pytest.raises(StopIteration):
        viewport.restart_scheduler(dummy_driver)

    # Compute what the wait _should_ have been:
    #   next_run = today at 12:00:10 → wait = 10 seconds
    expected_wait = (fixed_now.replace(hour=12, minute=0, second=10) - fixed_now).total_seconds()

    # === Assertions ===
    # A) We slept exactly the right amount
    assert sleep_calls == [expected_wait]

    # B) api_status was called once with the scheduled‐restart time
    assert len(api_calls) == 1
    assert api_calls[0] == f"Scheduled restart at {dt_time(12, 0, 10)}"

    # C) restart_handler was called with our dummy driver
    assert restart_calls == [dummy_driver]
def test_restart_scheduler_no_times(monkeypatch):
    # Arrange: no restart times configured
    monkeypatch.setattr(viewport, 'RESTART_TIMES', [])

    # Any of these being called would mean we didn't return early
    monkeypatch.setattr(viewport, 'api_status',                lambda msg: pytest.fail("api_status should NOT be called"))
    monkeypatch.setattr(viewport, 'restart_handler',           lambda drv: pytest.fail("restart_handler should NOT be called"))
    monkeypatch.setattr(viewport.time,   'sleep',              lambda secs: pytest.fail("time.sleep should NOT be called"))

    # Act & Assert: should return None and not raise
    result = viewport.restart_scheduler(driver="dummy")
    assert result is None
def test_restart_thread_terminates_on_system_exit(monkeypatch):
    # 1) Fix "now" at 2025-05-08 12:00:00
    fixed_now = datetime(2025, 5, 8, 12, 0, 0)
    class DummyDateTime(datetime):
        @classmethod
        def now(cls):
            return fixed_now

    # 2) Patch datetime and give us a single restart 10s in the future
    monkeypatch.setattr(viewport, 'datetime', DummyDateTime)
    monkeypatch.setattr(viewport, 'RESTART_TIMES', [dt_time(12, 0, 10)])

    # 3) Don’t actually sleep
    monkeypatch.setattr(viewport.time, 'sleep', lambda secs: None)

    # 4) Capture api_status so we know that happened
    api_msgs = []
    monkeypatch.setattr(viewport, 'api_status', lambda msg: api_msgs.append(msg))

    # 5) Make restart_handler simulate killing the thread via sys.exit(0)
    def fake_restart(driver):
        fake_restart.called = True
        raise SystemExit(0)
    fake_restart.called = False
    monkeypatch.setattr(viewport, 'restart_handler', fake_restart)

    # 6) Now when we call restart_scheduler, it should raise SystemExit(0)
    with pytest.raises(SystemExit) as exc:
        viewport.restart_scheduler(driver="DUMMY")

    # === Assertions ===
    assert exc.value.code == 0, "Thread should exit with code 0"
    assert fake_restart.called, "restart_handler must have been called"
    # And we also got our api_status before the exit
    assert api_msgs and api_msgs[0].startswith("Scheduled restart"), \
           "api_status should have been invoked before the exit"
           
# -------------------------------------------------------------------------
# Tests for restart_handler
# -------------------------------------------------------------------------
@pytest.mark.parametrize("initial_argv, driver_present, expected_flags", [
    # No flags          ⇒ no extra flags
    (["viewport.py"],                         False, []),
    # background flags  ⇒ preserved
    (["viewport.py", "-b"],                   False, ["--background"]),
    (["viewport.py", "--background"],         False, ["--background"]),
    (["viewport.py", "--backg"],              False, ["--background"]),
    # restart flags     ⇒ removed
    (["viewport.py", "-r"],                   False, []),
    (["viewport.py", "--restart"],            False, []),
    (["viewport.py", "--rest"],               False, []),
    # driver present    ⇒ quit()
    (["viewport.py", "--restart"],            True,  []),
])
@patch("viewport.sys.exit")
@patch("viewport.subprocess.Popen")
@patch("viewport.time.sleep", return_value=None)
@patch("viewport.api_status")
def test_restart_handler(
    mock_api_status,
    mock_sleep,
    mock_popen,
    mock_exit,
    initial_argv,
    driver_present,
    expected_flags
):
    # Arrange: set up sys.argv and optional driver
    viewport.sys.argv = list(initial_argv)
    driver = MagicMock() if driver_present else None

    # Act
    viewport.restart_handler(driver)

    # Assert: status update and sleep
    mock_api_status.assert_called_once_with("Restarting script...")
    mock_sleep.assert_called_once_with(2)

    # Assert: driver.quit() only if driver was passed
    if driver_present:
        driver.quit.assert_called_once()
    else:
        # ensure we didn't mistakenly call .quit()
        assert not getattr(driver, "quit", MagicMock()).called

    # Assert: Popen called exactly once with correct args
    expected_cmd = [sys.executable, viewport.__file__] + expected_flags
    mock_popen.assert_called_once_with(
        expected_cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        start_new_session=True,
    )

    # Assert: parent exits with code 0
    mock_exit.assert_called_once_with(0)
