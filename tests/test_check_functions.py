import pytest
from unittest.mock import MagicMock, PropertyMock, patch
from selenium.common.exceptions import WebDriverException
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
