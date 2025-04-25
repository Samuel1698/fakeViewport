import pytest
from unittest.mock import MagicMock, PropertyMock, patch
from selenium.common.exceptions import WebDriverException
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
mock_driver = MagicMock()

# Test for check_driver
def test_check_driver_valid():
  # Case 1: Driver is valid
  mock_driver.title = "Mock Title"
  assert check_driver(mock_driver) is True

  # Case 2: Interacting with the driver raises WebDriverException
  type(mock_driver).title = PropertyMock(side_effect=WebDriverException)
  assert check_driver(mock_driver) is False

  # Case 3: Interacting with the driver raises another Exception
  type(mock_driver).title = PropertyMock(side_effect=Exception)
  assert check_driver(mock_driver) is False
# Test for check_next_interval
def test_check_next_interval():
  # Case 1: 5 minutes interval
  now = datetime(2025, 1, 1, 10, 51, 0)
  result = check_next_interval(300, now=now)
  assert datetime.fromtimestamp(result) == datetime(2025, 1, 1, 10, 55, 0)

  # Case 2: Less than 30 seconds remaining skips ahead
  now = datetime(2025, 1, 1, 10, 59, 40)
  result = check_next_interval(300, now=now)
  assert datetime.fromtimestamp(result) == datetime(2025, 1, 1, 11, 5, 0)

  # Case 3: 1 minute interval
  now = datetime(2025, 1, 1, 10, 51, 10)
  result = check_next_interval(60, now=now)
  assert datetime.fromtimestamp(result) == datetime(2025, 1, 1, 10, 52, 0)

  # Case 4: 1 minute interval at :59:20
  now = datetime(2025, 1, 1, 10, 59, 20)
  result = check_next_interval(60, now=now)
  assert datetime.fromtimestamp(result) == datetime(2025, 1, 1, 11, 0, 0)
  
  # Case 5: 1 minute interval at :59:59
  now = datetime(2025, 1, 1, 10, 59, 59)
  result = check_next_interval(60, now=now)
  assert datetime.fromtimestamp(result) == datetime(2025, 1, 1, 11, 1, 0)