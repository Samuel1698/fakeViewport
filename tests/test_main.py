import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))
import re
import signal
import logging
import logging.handlers

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, mock_open, ANY
import pytest
import viewport
# Ensure no scheduled restarts by default
viewport.RESTART_TIMES = []
@pytest.fixture(autouse=True)
def disable_external_side_effects(monkeypatch):
    # never actually sleep
    monkeypatch.setattr(viewport.time, "sleep", lambda *args, **kwargs: None)
    # never actually fork a process
    monkeypatch.setattr(viewport.subprocess, "Popen", lambda *args, **kwargs: None)
    # make main() think the config is always valid
    monkeypatch.setattr(viewport, "validate_config", lambda *args, **kwargs: True)
# ----------------------------------------------------------------------------- 
# Test main function
# ----------------------------------------------------------------------------- 
@pytest.mark.parametrize(
    "sst_exists,sst_size,other_running,expected_kill,expected_write",
    [
        # 1) first-ever run: no file                     -> Expect write   
        (False, 0,    False, False, True),
        # 2) file exists but empty                       -> Expect Write
        (True,  0,    False, False, True),
        # 3) crash-recovery: stale SST, no other process -> Expect Write  
        (True,  123,  False, False, True),
        # 4) normal restart: SST present + old process   -> Don't Write
        (True,  123,  True,  True,  False),
        # 5) Edge case Restart: SST Present, no size + Old process -> Write
        (True,  0,  True,  True,  True),
    ],
)
@patch("viewport.args_handler", return_value="continue")
@patch("viewport.process_handler")
@patch("viewport.api_handler")
@patch("viewport.api_status")
@patch("viewport.browser_handler")
@patch("builtins.open", new_callable=mock_open)
@patch("viewport.threading.Thread")
def test_main_various(
    mock_thread,
    mock_open_file,
    mock_chrome,
    mock_api_status,
    mock_api_handler,
    mock_process,
    mock_args,
    sst_exists,
    sst_size,
    other_running,
    expected_kill,
    expected_write,
):
    # Arrange
    viewport.API = False

    # stub out sst_file
    fake_sst = MagicMock()
    fake_sst.exists.return_value = sst_exists
    fake_sst.stat.return_value = SimpleNamespace(st_size=sst_size)
    viewport.sst_file = fake_sst
    # stub out status file
    viewport.status_file = MagicMock()
    dummy_driver = object()
    mock_chrome.return_value = dummy_driver

    # process_handler: check → other_running; kill → None
    def proc_side_effect(name, action="check"):
        if name == "viewport.py" and action == "check":
            return other_running
        return None
    mock_process.side_effect = proc_side_effect

    # Act
    viewport.main()

    # the test stub passes whatever args_handler gets, so just check it got called
    mock_args.assert_called_once()
    # process_handler('viewport.py','check') always happens
    mock_process.assert_any_call('viewport.py', action="check")

    # kill only if expected_kill
    kill_calls = [
        c for c in mock_process.call_args_list
        if c.kwargs.get('action') == "kill"
    ]
    if expected_kill:
        assert kill_calls, "Expected a kill() call but none occurred"
    else:
        assert not kill_calls, f"Did not expect kill(), but got: {kill_calls}"

    # SST write only if expected_write
    if expected_write:
        mock_open_file.assert_called_once_with(viewport.sst_file, 'w')
        handle = mock_open_file()
        handle.write.assert_called_once()
    else:
        mock_open_file.assert_not_called()

    # Chrome launched
    mock_chrome.assert_called_once_with(viewport.url)
   # handle_view should be spun up as before
    mock_thread.assert_any_call(
        target=viewport.handle_view,
        args=(dummy_driver, viewport.url)
    )
    # restart_scheduler must also be spun up—and as a daemon!
    mock_thread.assert_any_call(
        target=viewport.restart_scheduler,
        args=(dummy_driver,),
        daemon=True
    )
    # no API logic here
    mock_api_handler.assert_not_called()
    mock_api_status.assert_called_with("Starting...")

@patch("viewport.args_handler", return_value="something_else")
@patch("viewport.process_handler")
@patch("builtins.open", new_callable=mock_open)
@patch("viewport.browser_handler")
@patch("viewport.threading.Thread")
def test_main_skip_when_not_continue(
    mock_thread,
    mock_chrome,
    mock_open_file,
    mock_process,
    mock_args
):
    viewport.main()
    # process_handler, browser_handler, thread.start should never run
    mock_process.assert_not_called()
    mock_chrome.assert_not_called()
    mock_thread.assert_not_called()
# ----------------------------------------------------------------------------- 
# Test log_error function
# ----------------------------------------------------------------------------- 
@patch("viewport.logging")
@patch("viewport.screenshot_handler")
@patch("viewport.check_driver")
@patch("viewport.api_status")
@patch("viewport.logs_dir", Path("/mock/logs"))
@patch("viewport.LOG_DAYS", 7)
def test_log_error_exception_logged(mock_api, mock_check, mock_sh, mock_log, *_):
    with patch("viewport.ERROR_LOGGING", True), patch("viewport.ERROR_PRTSCR", False):
        viewport.log_error("Something broke", exception=ValueError("fail"))
        mock_log.exception.assert_called_once_with("Something broke")
        mock_log.error.assert_not_called()
        mock_sh.assert_not_called()
        mock_api.assert_not_called()

@patch("viewport.logging")
@patch("viewport.screenshot_handler")
@patch("viewport.check_driver")
@patch("viewport.api_status")
@patch("viewport.logs_dir", Path("/mock/logs"))
@patch("viewport.LOG_DAYS", 7)
def test_log_error_without_exception(mock_api, mock_check, mock_sh, mock_log, *_):
    with patch("viewport.ERROR_LOGGING", True), patch("viewport.ERROR_PRTSCR", False):
        viewport.log_error("Basic error")
        mock_log.error.assert_called_once_with("Basic error")
        mock_log.exception.assert_not_called()
        mock_sh.assert_not_called()
        mock_api.assert_not_called()

@patch("viewport.logging")
@patch("viewport.screenshot_handler")
@patch("viewport.check_driver")
@patch("viewport.api_status")
@patch("viewport.logs_dir", Path("/mock/logs"))
@patch("viewport.LOG_DAYS", 7)
def test_log_error_with_driver_success(mock_api, mock_check, mock_sh, mock_log, *_):
    mock_driver = MagicMock()
    with patch("viewport.ERROR_LOGGING", False), patch("viewport.ERROR_PRTSCR", True), patch("viewport.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2025, 5, 10, 12, 0, 0)
        viewport.log_error("driver fail", driver=mock_driver)

        # Screenshot handler and check_driver called
        mock_sh.assert_called_once()
        mock_check.assert_called_once_with(mock_driver)

        # Screenshot path should match expected format
        mock_driver.save_screenshot.assert_called_once_with("/mock/logs/screenshot_2025-05-10_12-00-00.png")
        mock_log.info.assert_called_once()
        mock_api.assert_called_once_with("Saved error screenshot.")

@patch("viewport.logging")
@patch("viewport.screenshot_handler")
@patch("viewport.check_driver")
@patch("viewport.api_status")
@patch("viewport.logs_dir", Path("/mock/logs"))
@patch("viewport.LOG_DAYS", 7)
def test_log_error_screenshot_webdriver_exception(mock_api, mock_check, mock_sh, mock_log, *_):
    # Setup mock driver and raise WebDriverException
    mock_driver = MagicMock()
    from selenium.common.exceptions import WebDriverException
    with patch("viewport.ERROR_LOGGING", False), patch("viewport.ERROR_PRTSCR", True):
        mock_driver.save_screenshot.side_effect = WebDriverException("chrome died")
        viewport.log_error("error with driver", driver=mock_driver)

        mock_log.warning.assert_called_with("Could not take screenshot: WebDriver not alive (Message: chrome died\n)")
# ----------------------------------------------------------------------------- 
# Test api_status function
# ----------------------------------------------------------------------------- 
def test_api_status_writes(tmp_path, monkeypatch):
    status_file = tmp_path / "status.txt"
    monkeypatch.setattr(viewport, "status_file", status_file)
    viewport.api_status("OKAY")
    assert status_file.read_text() == "OKAY"
# ----------------------------------------------------------------------------- 
# Test api_handler function
# ----------------------------------------------------------------------------- 
@patch("viewport.process_handler", return_value=False)
@patch("viewport.subprocess.Popen")
@patch("viewport.api_status")
def test_api_handler_starts_api(mock_api_status, mock_popen, mock_proc):
    # Arrange
    # ensure monitoring.py is not “running”
    viewport.api_handler()
    # Should spawn monitoring.py detached
    assert mock_popen.called
    mock_api_status.assert_called_with("Starting API...")
@patch("viewport.process_handler", return_value=False)
@patch("viewport.subprocess.Popen", side_effect=Exception("fail"))
@patch("viewport.log_error")
@patch("viewport.api_status")
def test_api_handler_failure(
    mock_api_status,
    mock_log_error,
    mock_popen,
    mock_proc
):
    viewport.api_handler()
    mock_log_error.assert_called_with("Error starting API: ", ANY)
    mock_api_status.assert_called_with("Error Starting API")
@patch("viewport.process_handler", return_value=True)
@patch("viewport.subprocess.Popen")
@patch("viewport.api_status")
def test_api_handler_already_running(mock_api_status, mock_popen, mock_proc):
    viewport.api_handler()
    mock_popen.assert_not_called()
    mock_api_status.assert_not_called()
# ----------------------------------------------------------------------------- 
# Test Script Start Time File
# ----------------------------------------------------------------------------- 

# ----------------------------------------------------------------------------- 
# 1) args_handler: background/restart should leave SST alone; quit must clear it
@pytest.mark.parametrize(
    "flag, pre, should_clear",
    [
        # background variants → no clear
        ("-b",           "old", False),
        ("--background", "old", False),
        ("--backg",      "old", False),

        # restart variants → no clear
        ("-r",           "old", False),
        ("--restart",    "old", False),
        ("--rest",       "old", False),

        # quit variants → clear
        ("-q",           "old", True),
        ("--quit",       "old", True),
    ]
)
@patch("viewport.process_handler")
@patch("viewport.sys.exit")
def test_args_handler_flag_sst(mock_exit, mock_proc, flag, pre, should_clear, tmp_path):
    # path for our fake SST file
    sst = tmp_path / "sst.txt"
    sst.write_text(pre)
    viewport.sst_file = sst

    # build a minimal Args object
    args = SimpleNamespace(
        status=False,
        logs=None,
        background = flag in ("-b", "--background") or flag.startswith("--b"),
        restart    = flag in ("-r", "--restart")    or flag.startswith("--r"),
        diagnose   = flag in ("-d", "--diagnose"),
        quit       = flag in ("-q", "--quit"),
        api=False
    )

    # invoke
    viewport.args_handler(args)

    # check file
    content = sst.read_text()
    if should_clear:
        assert content == ""
    else:
        assert content == pre

# ----------------------------------------------------------------------------- 
# 2) main(): initial / crash / normal cases for writing SST
@pytest.mark.parametrize(
    "pre, other_running, expect_write",
    [
        # first-ever run: no file => write
        ( None,    False,  True),
        # crash recovery: file exists + no other process => rewrite
        ("old",    False,  True),
        # normal restart: file exists + other process => leave untouched
        ("old",     True,  False),
    ]
)
@patch("viewport.args_handler", return_value="continue")
@patch("viewport.browser_handler")
@patch("viewport.threading.Thread")
def test_main_sst_write_logic(mock_thread, mock_chrome, mock_args, pre, other_running, expect_write, tmp_path, monkeypatch):
    # set up
    sst = tmp_path / "sst.txt"
    viewport.sst_file = sst

    if pre is not None:
        sst.write_text(pre)
    # stub out status file
    viewport.status_file = MagicMock()
    # stub process_handler for viewport.py check
    def fake_proc(name, action="check"):
        return other_running if name=="viewport.py" else None
    viewport.process_handler = fake_proc

    # run
    viewport.main()

    # verify
    if expect_write:
        assert sst.exists()
        val = sst.read_text().strip()
        # should look like a timestamp: YYYY-MM-DD HH:MM:SS.ffffff
        assert re.match(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+", val), f"bad ts: {val}"
    else:
        # untouched
        assert sst.read_text() == pre

# ----------------------------------------------------------------------------- 
# 3) simulate SIGTERM (signal_handler): clears SST, then main() writes again
@patch("viewport.sys.exit")
def test_sigterm_clears_and_next_main_writes(mock_exit, tmp_path, monkeypatch):
    #  a) prepopulate
    sst = tmp_path / "sst.txt"
    viewport.sst_file = sst
    sst.write_text("old")
    monkeypatch.setattr(viewport, "status_file", tmp_path / "status.txt")

    # b) simulate kill by SIGTERM
    viewport.signal_handler(signum=signal.SIGTERM, frame=None, driver=None)
    assert sst.read_text() == ""

    # c) stub out everything else so main() will actually write
    monkeypatch.setattr(viewport, "args_handler", lambda a: "continue")
    monkeypatch.setattr(viewport, "process_handler", lambda n, action="check": False)
    monkeypatch.setattr(viewport, "browser_handler", lambda url: MagicMock())
    monkeypatch.setattr(viewport.threading, "Thread", lambda *args, **kwargs: MagicMock(start=lambda: None))

    # d) call main again
    viewport.main()
    assert sst.read_text().strip() != ""

# ----------------------------------------------------------------------------- 
# 4) simulate a true crash (no SIGTERM cleanup): prefilled SST + no process => main rewrites
def test_crash_recovery_writes(tmp_path, monkeypatch):
    sst = tmp_path / "sst.txt"
    viewport.sst_file = sst
    sst.write_text("2025-04-27 12:00:00.000001")
    # Mock status file
    monkeypatch.setattr(viewport, "status_file", tmp_path / "status.txt")
    # no other viewport.py running → crash condition
    monkeypatch.setattr(viewport, "process_handler", lambda n,action="check": False)

    # ensure main goes through
    monkeypatch.setattr(viewport, "args_handler", lambda a: "continue")
    monkeypatch.setattr(viewport, "browser_handler", lambda url: MagicMock())
    monkeypatch.setattr(viewport.threading, "Thread", lambda *args, **kwargs: MagicMock(start=lambda: None))

    viewport.main()
    # new timestamp should differ from old
    new = sst.read_text().strip()
    assert new != "2025-04-27 12:00:00.000001"
    assert re.match(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+", new)