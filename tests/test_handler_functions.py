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
from datetime import datetime, timedelta
import viewport
import signal

# helper to build a fake psutil.Process‐like object
def _make_proc(pid, cmdline):
    proc = MagicMock()
    proc.info = {"pid": pid, "cmdline": cmdline}
    return proc
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
    mock_logging.info.assert_any_call("Gracefully shutting down Chrome.")
    mock_logging.info.assert_any_call("Gracefully shutting down script instance.")
    mock_api_status.assert_called_once_with("Stopped ")
    mock_exit.assert_called_once_with(0)

# -------------------------------------------------------------------------
# Test for Status Handler
# -------------------------------------------------------------------------
@pytest.mark.parametrize(
    "missing_file, expected_log_error, process_names, expect_in_output",
    [
        # happy path: all files present, check for key output lines
        (None, None, ["viewport.py"], [
            "Fake Viewport 1.2.3",
            "Script Uptime",
            "Monitoring API",
            "Usage:",
            "Next Health Check in:",
            "Last Status Update",
            "Last Log Entry",
        ]),
        # missing uptime file triggers only log_error
        ("sst", "Uptime File not found", ["viewport.py"], None),
        # missing status file
        ("status", "Status File not found", ["viewport.py", "monitoring.py"], None),
        # missing log file
        ("log", "Log File not found", ["viewport.py", "monitoring.py"], None),
    ]
)
@patch("viewport.time.time", return_value=0)                         # freeze time.time()
@patch("viewport.check_next_interval", return_value=60)              # fixed next-interval
@patch("viewport.psutil.virtual_memory")                             # stub RAM
@patch("viewport.psutil.process_iter", return_value=[])              # no real processes
@patch("viewport.process_handler")                                   # control running-process flags
@patch("builtins.open")                                              # intercept file IO
@patch("viewport.log_error")                                         # spy on errors
def test_status_handler(
    mock_log_error,
    mock_open,
    mock_process_handler,
    mock_process_iter,
    mock_virtual_memory,
    mock_check_next_interval,
    mock_time_time,
    missing_file,
    expected_log_error,
    process_names,
    expect_in_output,
    capsys
):
    # set a predictable total RAM in GB
    mock_virtual_memory.return_value = MagicMock(total=1024**3)

    # override module globals to simple strings/numbers
    viewport.sst_file = "sst.txt"
    viewport.status_file = "status.txt"
    viewport.log_file = "viewport.log"
    viewport.viewport_version = "1.2.3"
    viewport.SLEEP_TIME = 60
    viewport.LOG_INTERVAL = 10

    # prepare in-memory file contents
    start = datetime(2024, 4, 25, 12, 0, 0)
    sst_data    = StringIO(start.strftime('%Y-%m-%d %H:%M:%S.%f'))
    status_data = StringIO("Feed Healthy")
    log_data    = StringIO("[INFO] Viewport check successful.")

    # simulate FileNotFound at different stages
    def open_side_effect(path, *args, **kwargs):
        p = str(path)
        if "sst"    in p:
            if missing_file == "sst":    raise FileNotFoundError
            return sst_data
        if "status" in p:
            if missing_file == "status": raise FileNotFoundError
            return status_data
        if "log"    in p:
            if missing_file == "log":    raise FileNotFoundError
            return log_data
        raise FileNotFoundError

    mock_open.side_effect = open_side_effect

    # control which processes appear 'running'
    mock_process_handler.side_effect = lambda name, action="check": name in process_names

    # run the handler
    viewport.status_handler()

    # assertions
    if expected_log_error:
        mock_log_error.assert_called_once()
        assert expected_log_error in mock_log_error.call_args[0][0]
    else:
        out = capsys.readouterr().out
        for snippet in expect_in_output:
            assert snippet in out
        mock_log_error.assert_not_called()
@pytest.mark.parametrize(
    "proc_list, current_pid, name, action, expected_result, "
    "expected_kill_calls, expected_api_calls",
    [
        # check mode, no processes at all
        ([], 100, "viewport.py", "check", False, [], []),

        # check mode, only self → False
        ([_make_proc(100, ["viewport.py"])],
         100, "viewport.py", "check", False, [], []),

        # check mode, one other process → True
        ([_make_proc(1, ["python","viewport.py"])],
         100, "viewport.py", "check", True, [], []),

        # kill mode, no processes → False, no kills, no api
        ([], 200, "viewport.py", "kill", False, [], []),

        # kill mode, only self → False, no kills, no api
        ([_make_proc(200, ["viewport.py"])],
         200, "viewport.py", "kill", False, [], []),

        # **kill mode, chrome & chromium** → both killed when name="chrome"
        ([
            _make_proc(2, ["chrome"]),
            _make_proc(3, ["chromium"])
        ],
         999, "chrome", "kill", False,
         [(2, signal.SIGTERM), (3, signal.SIGTERM)],
         ["Killed process 'chrome'"]
        ),

        # kill mode, two viewport.py → those two killed
        ([
            _make_proc(2, ["viewport.py"]),
            _make_proc(3, ["viewport.py"]),
            _make_proc(4, ["other.py"])
        ],
         999, "viewport.py", "kill", False,
         [(2, signal.SIGTERM), (3, signal.SIGTERM)],
         ["Killed process 'viewport.py'"]
        ),

        # check mode, string‐cmdline instead of list → True
        ([_make_proc(10, "/usr/bin/viewport.py --foo")],
         0, "viewport.py", "check", True, [], []),
    ]
)
@patch("viewport.psutil.process_iter")
@patch("viewport.os.getpid")
@patch("viewport.os.kill")
@patch("viewport.api_status")
def test_process_handler_param(
    mock_api, mock_kill, mock_getpid, mock_iter,
    proc_list, current_pid, name, action,
    expected_result, expected_kill_calls, expected_api_calls
):
    # arrange
    mock_iter.return_value   = proc_list
    mock_getpid.return_value = current_pid

    # act — now uses the parametrized name
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

    # assert api_status calls
    if expected_api_calls:
        assert mock_api.call_args_list == [call(msg) for msg in expected_api_calls]
    else:
        mock_api.assert_not_called()
# -------------------------------------------------------------------------
# Test for Service Handler
# -------------------------------------------------------------------------
@patch("viewport.ChromeDriverManager")
def test_service_handler_installs_chromedriver(mock_chrome_driver_manager):
    # Reset global path first
    viewport._chrome_driver_path = None

    mock_installer = MagicMock()
    mock_installer.install.return_value = "/fake/path/to/chromedriver"
    mock_chrome_driver_manager.return_value = mock_installer

    result = viewport.service_handler()

    assert result == "/fake/path/to/chromedriver"
    mock_installer.install.assert_called_once()

@patch("viewport.ChromeDriverManager")
def test_service_handler_reuses_existing_path(mock_chrome_driver_manager):
    viewport._chrome_driver_path = "/already/installed/driver"

    result = viewport.service_handler()

    assert result == "/already/installed/driver"
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
    mock_process_handler.assert_any_call("chrome", action="kill")

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
        mock_log_error.assert_any_call("Failed to start Chrome after maximum retries.")
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
    "chrome_exc, check_exc, handle_page_ret, "
    "expect_sleep, expect_feed_healthy, expect_return_driver, "
    "expect_log_error, expect_api_calls",
    [
        # 1) All good, handle_page=True  ⇒ sleep, Feed Healthy, returns driver
        (None, None, True, True, True, True, False,
         [call("Restarting Chrome"), call("Feed Healthy")]),
        # 2) All good, handle_page=False ⇒ no sleep, no Feed Healthy, returns driver
        (None, None, False, False, False, True, False,
         [call("Restarting Chrome")]),
        # 3) chrome_handler raises ⇒ no sleep, no return, log_error & Error Killing Chrome
        (Exception("boom"), None, None, False, False, False, True,
         [call("Restarting Chrome"), call("Error Killing Chrome")]),
        # 4) check_for_title raises ⇒ same as #3
        (None, Exception("oops"), None, False, False, False, True,
         [call("Restarting Chrome"), call("Error Killing Chrome")]),
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
    expect_sleep,
    expect_feed_healthy,
    expect_return_driver,
    expect_log_error,
    expect_api_calls,
):
    url = "http://example.com"
    mock_driver = MagicMock()

    # Setup chrome_handler side effect or return
    if chrome_exc:
        mock_chrome_handler.side_effect = chrome_exc
    else:
        mock_chrome_handler.return_value = mock_driver

    # Setup check_for_title side effect
    if check_exc:
        mock_check_for_title.side_effect = check_exc

    # Setup handle_page return
    mock_handle_page.return_value = handle_page_ret

    # Act
    result = viewport.chrome_restart_handler(url)

    # Assert api_status calls
    assert mock_api_status.call_args_list == expect_api_calls

    # Assert log_error only when exceptions
    assert bool(mock_log_error.called) == expect_log_error

    # If full success path with driver:
    if expect_return_driver:
        assert result is mock_driver
        # handle_page True ⇒ sleep called once
        assert mock_sleep.called == expect_sleep
        if expect_feed_healthy:
            # feed-healthy log/info
            mock_log_info.assert_any_call("Page successfully reloaded.")
    else:
        # on exception path, returns None
        assert result is None

    # Always logs "Restarting chrome..."
    mock_log_info.assert_any_call("Restarting chrome...")

# -------------------------------------------------------------------------
# Tests for restart_handler
# -------------------------------------------------------------------------
@pytest.mark.parametrize(
    "initial_argv, driver_present, execv_exc, "
    "expect_quit, expect_sleep, expect_api, expect_execv, expect_log_error, expect_exit",
    [
        # Called with no argument, no driver, execv OK ⇒ no quit, sleep, api_status, execv
        (["script.py"],                     False, None, False, True, True, True,  False, False),
        # execv raises ⇒ quit, sleep, initial api_status, execv attempt,
        #    then log_error, error api_status, sys.exit(1)
        (["script.py", "--restart"],        True,  Exception("bad"), True,  True, True, True,  True,  True),
        # short-background
        (["script.py", "-b"],                False, None, False, True, True, True, False, False),
        # long-background
        (["script.py", "--background"],      False, None, False, True, True, True, False, False),
        # abbreviated background
        (["script.py", "--backg"],           False, None, False, True, True, True, False, False),
        # long-restart
        (["script.py", "--restart"],           True,  None, True,  True, True, True, False, False),
        # abbreviated restart
        (["script.py", "--resta"],           True,  None, True,  True, True, True, False, False),
        # short-restart
        (["script.py", "-r"],                True,  None, True,  True, True, True, False, False),
        # restart_handler should drop the --restart and only emit one --background
        (["script.py", "--restart", "--background"], False, None, False, True, True, True, False, False),
    ]
)
@patch("viewport.sys.exit")
@patch("viewport.os.execv")
@patch("viewport.time.sleep", return_value=None)
@patch("viewport.api_status")
@patch("viewport.log_error")
def test_restart_handler(
    mock_log_error,
    mock_api_status,
    mock_sleep,
    mock_execv,
    mock_exit,
    initial_argv,
    driver_present,
    execv_exc,
    expect_quit,
    expect_sleep,
    expect_api,
    expect_execv,
    expect_log_error,
    expect_exit,
):
    # Arrange
    viewport.sys.argv = list(initial_argv)
    dummy_driver = MagicMock() if driver_present else None

    if execv_exc:
        mock_execv.side_effect = execv_exc

    # Act
    viewport.restart_handler(dummy_driver)

    # Assert driver.quit() only if driver_present
    if expect_quit:
        dummy_driver.quit.assert_called_once()
    else:
        if dummy_driver:
            dummy_driver.quit.assert_not_called()

    # sleep and initial api_status should always run before execv
    assert mock_sleep.called == expect_sleep
    assert mock_api_status.called == expect_api

    # os.execv()
    if expect_execv:
        # Rebuild expected argv exactly as the code under test does:
        import argparse
        parser = argparse.ArgumentParser(add_help=False, allow_abbrev=True)
        parser.add_argument("-s","--status",   action="store_true", dest="status")
        parser.add_argument("-b","--background",action="store_true", dest="background")
        parser.add_argument("-r","--restart",  action="store_true", dest="restart")
        parser.add_argument("-q","--quit",     action="store_true", dest="quit")
        parser.add_argument("-l","--logs",     nargs="?", type=int, const=5, dest="logs")
        parser.add_argument("-a","--api",      action="store_true", dest="api")

        args, unknown = parser.parse_known_args(initial_argv[1:])

        expected = [initial_argv[0]]
        expected += unknown
        if args.logs     is not None: expected += ["--logs", str(args.logs)]
        if args.status:      expected.append("--status")
        if args.quit:        expected.append("--quit")
        if args.api:         expected.append("--api")
        # (note: args.restart is dropped on purpose)
        expected.append("--background")
        expected = [sys.executable] + expected
        mock_execv.assert_called_once_with(sys.executable, expected)
    else:
        mock_execv.assert_not_called()

    # on execv exception, we log_error, do error api_status, and exit(1)
    assert bool(mock_log_error.called) == expect_log_error
    if expect_exit:
        mock_api_status.assert_any_call("Error Restarting, exiting...")
        mock_exit.assert_called_once_with(1)
    else:
        mock_exit.assert_not_called()

@pytest.mark.parametrize("orig_argv, expected_child_flags", [
    # restarting should drop -r and add only --background
    (["viewport.py", "-r"], ["--background"]),
    (["viewport.py", "--restart"], ["--background"]),
    (["viewport.py", "-r", "--resta"], ["--background"]),
])
def test_restart_round_trip_parses_background(orig_argv, expected_child_flags, monkeypatch):
    # 1) Simulate the original invocation
    monkeypatch.setattr(viewport.sys, "argv", list(orig_argv))
    args = viewport.args_helper()
    assert args.restart is True, "original args_helper should see restart=True"

    # 2) Compute the flags that restart_handler would re-exec with
    child_flags = viewport.args_child_handler(
        args,
        drop_flags={"restart"},
        add_flags={"background"}
    )
    assert child_flags == expected_child_flags

    # 3) Now simulate a fresh process with just those flags
    monkeypatch.setattr(viewport.sys, "argv", ["viewport.py"] + child_flags)

    # 4) Ensure args_helper() accepts --background and nothing else
    new_args = viewport.args_helper()
    assert new_args.background is True
    # all the other switches must be False / None
    assert not new_args.restart
    assert not new_args.status
    assert not new_args.quit
    assert not new_args.api
    assert new_args.logs is None