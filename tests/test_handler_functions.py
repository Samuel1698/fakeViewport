import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))
import logging
import logging.handlers
# stub out the rotating‐file handler before viewport.py ever sees it
logging.handlers.TimedRotatingFileHandler = lambda *args, **kwargs: logging.NullHandler()

import pytest
from unittest.mock import MagicMock, patch, call
from io import StringIO
from datetime import datetime
from webdriver_manager.core.os_manager import ChromeType
import viewport
import signal
import subprocess
# helper to build a fake psutil.Process‐like object
def _make_proc(pid, cmdline):
    proc = MagicMock()
    proc.info = {"pid": pid, "cmdline": cmdline}
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
@patch("viewport.check_next_interval", return_value=60)
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
    mock_check_next_interval,
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
            [_make_proc(10, "/usr/bin/viewport.py --foo")], 
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
    ]
)
@patch("viewport.logging.info")
@patch("viewport.psutil.process_iter")
@patch("viewport.os.getpid")
@patch("viewport.os.kill")
@patch("viewport.api_status")
def test_process_handler(
    mock_api, mock_kill, mock_getpid, mock_iter, mock_log_info,
    proc_list, current_pid, name, action,
    expected_result, expected_kill_calls, expected_api_calls, expected_log_info
):
    # arrange
    mock_iter.return_value   = proc_list
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
# Test for Chrome Handler
# -------------------------------------------------------------------------
@pytest.mark.parametrize(
    "chrome_side_effects, "
    "expected_driver_get_calls, "
    "expected_kill_calls, "
    "expect_execv",
    [
        # 1) Success on first try
        ([MagicMock()], 1, 1, False),
        # 2) Fail twice, then succeed on 3rd (with MAX_RETRIES=3)
        ([Exception("boom"), Exception("boom"), MagicMock()], 1, 1, False),
        # 3) Always fail => exhaust retries, kill twice (start + final), then execv
        ([Exception("fail")] * 3, 0, 2, True),
    ]
)
@patch("viewport.process_handler")
@patch("viewport.Options")
@patch("viewport.webdriver.Chrome")
@patch("viewport.time.sleep", return_value=None)
@patch("viewport.os.execv")
@patch("viewport.api_status")
@patch("viewport.log_error")
def test_chrome_handler(
    mock_log_error,
    mock_api_status,
    mock_execv,
    mock_sleep,
    mock_chrome,
    mock_options,
    mock_process_handler,
    chrome_side_effects,
    expected_driver_get_calls,
    expected_kill_calls,
    expect_execv,
):
    # Arrange
    url = "http://example.com"
    viewport.MAX_RETRIES = 3
    viewport.SLEEP_TIME = 10  # so restart delay is predictable
    # ensure sys.argv is predictable
    viewport.sys.argv = ["script.py", "-b"]

    # Side effect for webdriver.Chrome: either return driver or raise
    mock_driver = MagicMock()
    # build side_effect list: if item is Exception, raise it; else return mock_driver
    side = []
    for item in chrome_side_effects:
        if isinstance(item, Exception):
            side.append(item)
        else:
            side.append(mock_driver)
    mock_chrome.side_effect = side

    # Options() should return a dummy options object
    dummy_opts = MagicMock()
    mock_options.return_value = dummy_opts

    # Service() is called with service_handler(); service_handler can just be default
    # Act
    result = viewport.chrome_handler(url)

    # Assert: process_handler("chrome", "kill") at start and possibly at final retry
    assert mock_process_handler.call_count == expected_kill_calls
    mock_process_handler.assert_any_call(viewport.BROWSER, action="kill")

    # Assert: webdriver.Chrome called up to MAX_RETRIES or until success
    assert mock_chrome.call_count == len(chrome_side_effects)

    # If we got a driver back, check .get(url) call count
    if expected_driver_get_calls:
        mock_driver.get.assert_called_once_with(url)
        assert result is mock_driver
    else:
        # on permanent failure, chrome_handler never returns driver
        assert result is None

    # execv only on permanent failure
    if expect_execv:
        mock_execv.assert_called_once_with(
            sys.executable,
            ['python3'] + viewport.sys.argv
        )
        # And we should have logged and API-status’d the restart
        mock_log_error.assert_any_call(f"Failed to start {viewport.BROWSER} after maximum retries.")
        mock_api_status.assert_any_call("Restarting Script in 5 seconds.")
    else:
        mock_execv.assert_not_called()
        # We still log any intermediate errors for intermittent failures
        if len(chrome_side_effects) > 1:
            # at least one log_error for each Exception
            assert mock_log_error.call_count >= sum(isinstance(e, Exception) for e in chrome_side_effects)
# -------------------------------------------------------------------------
# Tests for chrome_restart_handler
# -------------------------------------------------------------------------
@pytest.mark.parametrize(
    "chrome_exc,    check_exc,     handle_page_ret, "
    "should_sleep,  should_feed_ok, should_return, "
    "should_log_err, expected_api_calls",
    [
        # 1) Success, handle_page=True
        #    → sleep, log "Feed Healthy", return driver, no log_error
        (
            None,         None,            True,
            True,         True,            True,
            False,        [call(f"Restarting {viewport.BROWSER}"), call("Feed Healthy")],
        ),

        # 2) Success, handle_page=False
        #    → no sleep, no "Feed Healthy", return driver, no log_error
        (
            None,         None,            False,
            False,        False,           True,
            False,        [call(f"Restarting {viewport.BROWSER}")],
        ),

        # 3) chrome_handler throws
        #    → no sleep, no return, log_error, Error Killing Chrome
        (
            Exception("boom"), None,       None,
            False,        False,           False,
            True,         [call(f"Restarting {viewport.BROWSER}"), call(f"Error Killing {viewport.BROWSER}")],
        ),

        # 4) check_for_title throws
        #    → same as case 3
        (
            None,         Exception("oops"), None,
            False,        False,           False,
            True,         [call(f"Restarting {viewport.BROWSER}"), call(f"Error Killing {viewport.BROWSER}")],
        ),
    ]
)
@patch("viewport.time.sleep", return_value=None)
@patch("viewport.logging.info")
@patch("viewport.api_status")
@patch("viewport.log_error")
@patch("viewport.handle_page")
@patch("viewport.check_for_title")
@patch("viewport.chrome_handler")
def test_chrome_restart_handler(
    mock_chrome_handler,
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
    expected_api_calls,
):
    url = "http://example.com"
    fake_driver = MagicMock()

    # wire up chrome_handler
    if chrome_exc:
        mock_chrome_handler.side_effect = chrome_exc
    else:
        mock_chrome_handler.return_value = fake_driver

    # wire up check_for_title
    if check_exc:
        mock_check_for_title.side_effect = check_exc

    # wire up handle_page
    mock_handle_page.return_value = handle_page_ret

    # Act
    result = viewport.chrome_restart_handler(url)

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
    if should_return:
        assert result is fake_driver
    else:
        assert result is None

    # log_error only on exception paths
    assert mock_log_error.called == should_log_err
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
def test_restart_handler_new(
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