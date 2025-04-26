import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

import pytest
from unittest.mock import MagicMock, patch
from io import StringIO
from datetime import datetime, timedelta

import viewport
import signal

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
    mock_api_status.assert_called_once_with("Stopped")
    mock_exit.assert_called_once_with(0)

# -------------------------------------------------------------------------
# Test for Status Handler
# -------------------------------------------------------------------------
@pytest.mark.parametrize(
    "missing_file, expected_log_error, process_names, expect_in_output",
    [
        (None, None, ["viewport.py"], ["Fake Viewport 1.2.3", "Script Uptime", "Monitoring API", "Last Status Update", "Last Log Entry"]),
        ("sst", "Error while checking system uptime", ["viewport.py"], None),
        ("status", "Status File not found", ["viewport.py", "monitoring.py"], None),
        ("log", "Log File not found", ["viewport.py", "monitoring.py"], None),
    ]
)
@patch("viewport.time.sleep", return_value=None)
@patch("builtins.open")
@patch("viewport.process_handler")
@patch("viewport.log_error")
@patch("viewport.datetime")
def test_status_handler_parametrized(
    mock_datetime, mock_log_error, mock_process_handler, mock_open, mock_sleep,
    missing_file, expected_log_error, process_names, expect_in_output, capsys
):
    # Setup datetime mock for .now()
    now = datetime(2024, 4, 25, 12, 0, 0)
    mock_datetime.now.return_value = now

    # Variables
    viewport.sst_file = "sst.txt"
    viewport.status_file = "status.txt"
    viewport.log_file = "viewport.log"
    viewport.viewport_version = "1.2.3"
    # Prepare formatted string data (not datetime objects)
    start_time = now - timedelta(days=1, hours=2, minutes=30, seconds=45)
    start_time_str = start_time.strftime('%Y-%m-%d %H:%M:%S.%f')
    sst_data = StringIO(start_time_str)
    status_data = StringIO("Feed Healthy")
    log_data = StringIO("[INFO] Viewport check successful.")

    def open_side_effect(file, *args, **kwargs):
        if "sst" in file:
            if missing_file == "sst":
                raise FileNotFoundError
            return sst_data
        elif "status" in file:
            if missing_file == "status":
                raise FileNotFoundError
            return status_data
        elif "log" in file:
            if missing_file == "log":
                raise FileNotFoundError
            return log_data
        else:
            raise FileNotFoundError

    mock_open.side_effect = open_side_effect
    mock_process_handler.side_effect = lambda name, action="check": name in process_names

    # Call the function
    viewport.status_handler()

    if expected_log_error:
        mock_log_error.assert_called_once()
        assert expected_log_error in mock_log_error.call_args[0][0]
    else:
        captured = capsys.readouterr()
        for text in expect_in_output:
            assert text in captured.out
        mock_log_error.assert_not_called()
# -------------------------------------------------------------------------
# Test for Process Handler
# -------------------------------------------------------------------------
@pytest.mark.parametrize(
    "stdout_output, action, expected_result, should_kill",
    [
        ("12345\n67890", "check", True, False),   # Process exists, check mode
        ("12345\n67890", "kill", False, True),    # Process exists, kill mode
        ("", "check", False, False),              # No process found
    ],
)
@patch("viewport.time.sleep", return_value=None)
@patch("viewport.api_status")
@patch("viewport.log_error")
@patch("viewport.logging")
@patch("viewport.os.kill")
@patch("viewport.subprocess.run")
def test_process_handler(
    mock_run, mock_kill, mock_logging, mock_log_error, mock_api_status, mock_sleep,
    stdout_output, action, expected_result, should_kill
):
    mock_run.return_value.stdout = stdout_output

    with patch("viewport.os.getpid", return_value=99999):
        result = viewport.process_handler("viewport.py", action=action)

    assert result == expected_result

    if should_kill:
        mock_kill.assert_any_call(12345, signal.SIGTERM)
        mock_kill.assert_any_call(67890, signal.SIGTERM)
    else:
        mock_kill.assert_not_called()

    mock_log_error.assert_not_called()

@patch("viewport.time.sleep", return_value=None)
@patch("viewport.api_status")
@patch("viewport.log_error")
@patch("viewport.logging")
@patch("viewport.os.kill")
@patch("viewport.subprocess.run")
def test_process_handler_exception(
    mock_run, mock_kill, mock_logging, mock_log_error, mock_api_status, mock_sleep
):
    # Simulate subprocess.run throwing an exception
    mock_run.side_effect = Exception("Something went wrong")

    result = viewport.process_handler("viewport.py", action="check")

    assert result is False
    mock_log_error.assert_called_once()
    mock_api_status.assert_called_once()

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
def test_chrome_handler_parametrized(
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

