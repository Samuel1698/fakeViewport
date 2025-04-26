import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from unittest.mock import MagicMock, patch
from io import StringIO
from datetime import datetime, timedelta
import viewport

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

# ---------------------------------------------------------------------------
# Test for Status Handler
# ---------------------------------------------------------------------------
@patch("builtins.open")
@patch("viewport.process_handler")
@patch("viewport.log_error")
@patch("viewport.datetime")
def test_status_handler(mock_datetime, mock_log_error, mock_process_handler, mock_open, capsys):
    # Setup datetime mock
    now = datetime(2024, 4, 25, 12, 0, 0)
    start_time = now - timedelta(days=1, hours=2, minutes=30, seconds=45)
    mock_datetime.now.return_value = now
    mock_datetime.strptime.return_value = start_time

    # Mock open for sst_file, status_file, and log_file
    sst_data = StringIO(start_time.strftime('%Y-%m-%d %H:%M:%S.%f'))
    status_data = StringIO("Feed Healthy")
    log_data = StringIO("[INFO] Viewport check successful.")

    def open_side_effect(file, *args, **kwargs):
        if "sst" in file:
            return sst_data
        elif "status" in file:
            return status_data
        elif "log" in file:
            return log_data
        else:
            raise FileNotFoundError
        
    mock_process_handler.side_effect = lambda name, action="check": name == "viewport.py"
    mock_open.side_effect = open_side_effect
    # Call the function
    viewport.status_handler()
    # Capture the output
    captured = capsys.readouterr()

    # Assertions
    assert "Fake Viewport 1.2.3" in captured.out
    assert "Script Uptime" in captured.out
    assert "Monitoring API" in captured.out
    assert "Last Status Update" in captured.out
    assert "Last Log Entry" in captured.out

    mock_log_error.assert_not_called()

@patch("viewport.log_error")
@patch("builtins.open")
def test_status_handler_missing_uptime(mock_open, mock_log_error):
    # Mock open for sst_file, status_file, and log_file
    status_data = StringIO("Feed Healthy")
    log_data = StringIO("[INFO] Viewport check successful.")
    def open_side_effect(file, *args, **kwargs):
        if "sst" in file:
            raise FileNotFoundError
        elif "status" in file:
            return status_data
        elif "log" in file:
            return log_data

    mock_open.side_effect = open_side_effect
    viewport.status_handler()

    mock_log_error.assert_called_once()
    assert "Error while checking system uptime" in mock_log_error.call_args[0][0]

@patch("viewport.process_handler")
@patch("viewport.log_error")
@patch("builtins.open")
def test_status_handler_missing_status(mock_open, mock_log_error, mock_process_handler):
    # Simulate uptime file is fine, then sst file missing
    # Mock open for sst_file, status_file, and log_file
    sst_data = StringIO("2024-04-24 09:00:00.000000")
    log_data = StringIO("[INFO] Viewport check successful.")

    def open_side_effect(file, *args, **kwargs):
        if "sst" in file:
            return sst_data
        elif "status" in file:
            raise FileNotFoundError
        elif "log" in file:
            return log_data
    mock_process_handler.side_effect = lambda name, action="check": name in ["viewport.py", "monitoring.py"]
    mock_open.side_effect = open_side_effect
    viewport.status_handler()

    mock_log_error.assert_called_once_with("Status File not found")

@patch("viewport.process_handler")
@patch("viewport.log_error")
@patch("builtins.open")
def test_status_handler_missing_log(mock_open, mock_log_error, mock_process_handler):
    # Mock open for sst_file, status_file, and log_file
    sst_data = StringIO("2024-04-24 09:00:00.000000")
    status_data = StringIO("Feed Healthy")

    def open_side_effect(file, *args, **kwargs):
        if "sst" in file:
            return sst_data
        elif "status" in file:
            return status_data
        elif "log" in file:
            raise FileNotFoundError
    mock_process_handler.side_effect = lambda name, action="check": name in ["viewport.py", "monitoring.py"]
    mock_open.side_effect = open_side_effect
    viewport.status_handler()

    mock_log_error.assert_called_once_with("Log File not found")
