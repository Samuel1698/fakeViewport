import pytest
from unittest.mock import MagicMock, PropertyMock, patch
from selenium.common.exceptions import TimeoutException, NoSuchElementException, InvalidSessionIdException, WebDriverException
from datetime import datetime

import sys
from pathlib import Path

# Add the parent directory to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from viewport import (
    check_driver,
    check_next_interval,
    check_for_title,
    check_unable_to_stream
)
# -----------------------------------------------------------------
# Check Driver function
# -----------------------------------------------------------------
mock_driver = MagicMock()
def test_check_driver_valid():
  mock_driver.title = "Mock Title"
  assert check_driver(mock_driver) is True
def test_check_driver_WebdriverException():
  type(mock_driver).title = PropertyMock(side_effect=WebDriverException)
  assert check_driver(mock_driver) is False
def test_check_driver_other_exception():
  type(mock_driver).title = PropertyMock(side_effect=Exception)
  assert check_driver(mock_driver) is False
# -----------------------------------------------------------------
# Check Next Interval function
# -----------------------------------------------------------------
def test_exact_5_min_interval():
  now = datetime(2025, 1, 1, 10, 51, 0)
  result = check_next_interval(300, now=now)
  assert datetime.fromtimestamp(result) == datetime(2025, 1, 1, 10, 55, 0)
def test_less_than_30_seconds_skips_ahead():
  now = datetime(2025, 1, 1, 10, 59, 40)
  result = check_next_interval(300, now=now)
  assert datetime.fromtimestamp(result) == datetime(2025, 1, 1, 11, 5, 0)
def test_1_minute_interval():
  now = datetime(2025, 1, 1, 10, 51, 10)
  result = check_next_interval(60, now=now)
  assert datetime.fromtimestamp(result) == datetime(2025, 1, 1, 10, 52, 0)
def test_1_minute_interval_at_59_20():
  now = datetime(2025, 1, 1, 10, 59, 20)
  result = check_next_interval(60, now=now)
  assert datetime.fromtimestamp(result) == datetime(2025, 1, 1, 11, 0, 0)
def test_1_minute_interval_at_59_59():
  now = datetime(2025, 1, 1, 10, 59, 59)
  result = check_next_interval(60, now=now)
  assert datetime.fromtimestamp(result) == datetime(2025, 1, 1, 11, 1, 0)

# ---------------------------------------------------------------------
# Check for title function
# ---------------------------------------------------------------------

@patch("viewport.WebDriverWait")
@patch("viewport.api_status")
@patch("viewport.log_error")
@patch("viewport.logging")
def test_check_for_title_success(mock_logging, mock_log_error, mock_api_status, mock_wait):
  mock_driver = MagicMock()
  mock_wait.return_value.until.return_value = True

  result = check_for_title(mock_driver, title="Test Page")

  assert result is True
  mock_logging.info.assert_called_with("Loaded page: 'Test Page'")
  mock_api_status.assert_called_with("Loaded page: 'Test Page'")
  mock_log_error.assert_not_called()

@patch("viewport.WebDriverWait")
@patch("viewport.api_status")
@patch("viewport.log_error")
def test_check_for_title_timeout(mock_log_error, mock_api_status, mock_wait):
  mock_driver = MagicMock()
  mock_wait.return_value.until.side_effect = TimeoutException

  result = check_for_title(mock_driver, title="Missing Page")

  assert result is False
  mock_log_error.assert_called_with("Timed out waiting for the title 'Missing Page' to load.")
  mock_api_status.assert_called_with("Timed Out Waiting for Title 'Missing Page'")

@patch("viewport.WebDriverWait")
@patch("viewport.api_status")
@patch("viewport.log_error")
def test_check_for_title_empty(mock_log_error, mock_api_status, mock_wait):
  mock_driver = MagicMock()
  mock_driver.title = lambda d: d.title != ""
  mock_wait.return_value.until.return_value = True

  result = check_for_title(mock_driver)

  assert result is True
  mock_log_error.assert_not_called()
  mock_api_status.assert_not_called()

@patch("viewport.WebDriverWait")
@patch("viewport.api_status")
@patch("viewport.log_error")
def test_check_for_title_Webdriver_Exception(mock_log_error, mock_api_status, mock_wait):
  mock_driver = MagicMock()
  mock_wait.return_value.until.side_effect = WebDriverException

  result = check_for_title(mock_driver, title="Test Page")

  assert result is False
  mock_log_error.assert_called_with("Tab Crashed.")
  mock_api_status.assert_called_with("Tab Crashed")


