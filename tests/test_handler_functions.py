import pytest
from unittest.mock import MagicMock, PropertyMock, patch
from selenium.common.exceptions import WebDriverException
import sys
from pathlib import Path

# Add the parent directory to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from viewport import (
    signal_handler,
    status_handler,
    process_handler,
    chrome_handler,
    chrome_restart_handler,
    restart_handler,
)

@patch("viewport.logging")
@patch("viewport.api_status")
@patch("viewport.sys.exit")
def test_signal_handler_calls_exit(mock_exit, mock_api_status, mock_logging):
    mock_driver = MagicMock()

    # Call the signal handler manually
    signal_handler(signum=2, frame=None, driver=mock_driver)

    # Assertions
    mock_driver.quit.assert_called_once()
    mock_logging.info.assert_any_call("Gracefully shutting down Chrome.")
    mock_logging.info.assert_any_call("Gracefully shutting down script instance.")
    mock_api_status.assert_called_once_with("Stopped")
    mock_exit.assert_called_once_with(0)
