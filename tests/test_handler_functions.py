import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from unittest.mock import MagicMock, patch
from io import StringIO
from datetime import datetime, timedelta
import pytest
import viewport
import signal

# Mock config/global variables
viewport.sst_file = "sst.txt"
viewport.status_file = "status.txt"
viewport.log_file = "log.txt"
# viewport.SLEEP_TIME = 125
# viewport.LOG_INTERVAL = 5
viewport.viewport_version = "1.2.3"
# viewport.GREEN = "\033[92m"
# viewport.RED = "\033[91m"
# viewport.YELLOW = "\033[93m"
# viewport.CYAN = "\033[96m"
# viewport.NC = "\033[0m"
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