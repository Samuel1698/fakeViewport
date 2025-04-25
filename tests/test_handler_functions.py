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



# # Test for check_for_title
# @patch("viewport.WebDriverWait")
# @patch("viewport.EC")
# def test_check_for_title(mock_ec, mock_wait):
#     mock_driver = MagicMock()
#     mock_driver.title = "Dashboard"

#     # Test with a specific title
#     mock_wait.return_value.until.return_value = True
#     assert check_for_title(mock_driver, "Dashboard") is True

#     # Test with no title
#     mock_wait.return_value.until.return_value = True
#     assert check_for_title(mock_driver) is True

#     # Simulate TimeoutException
#     mock_wait.return_value.until.side_effect = Exception("TimeoutException")
#     assert check_for_title(mock_driver, "Nonexistent Title") is False


# # Test for handle_login
# @patch("viewport.WebDriverWait")
# @patch("viewport.EC")
# def test_handle_login(mock_ec, mock_wait):
#     mock_driver = MagicMock()
#     mock_username_field = MagicMock()
#     mock_password_field = MagicMock()
#     mock_submit_button = MagicMock()

#     mock_wait.return_value.until.side_effect = [
#         mock_username_field,
#         mock_password_field,
#         mock_submit_button,
#     ]

#     # Mock username and password
#     with patch("viewport.username", "test_user"), patch("viewport.password", "test_password"):
#         assert handle_login(mock_driver) is True

#     # Ensure the fields were interacted with
#     mock_username_field.clear.assert_called_once()
#     mock_username_field.send_keys.assert_called_once_with("test_user")
#     mock_password_field.clear.assert_called_once()
#     mock_password_field.send_keys.assert_called_once_with("test_password")
#     mock_submit_button.click.assert_called_once()


# # Test for handle_page
# @patch("viewport.check_for_title")
# @patch("viewport.handle_elements")
# def test_handle_page(mock_handle_elements, mock_check_for_title):
#     mock_driver = MagicMock()
#     mock_driver.title = "Dashboard"

#     # Simulate successful page load
#     mock_check_for_title.return_value = True
#     assert handle_page(mock_driver) is True
#     mock_handle_elements.assert_called_once_with(mock_driver)

#     # Simulate login page
#     mock_driver.title = "Ubiquiti Account"
#     with patch("viewport.handle_login", return_value=True):
#         assert handle_page(mock_driver) is True

#     # Simulate timeout
#     mock_driver.title = "Unknown Page"
#     mock_check_for_title.return_value = False
#     assert handle_page(mock_driver) is False


# # Test for handle_retry
# @patch("viewport.chrome_restart_handler")
# @patch("viewport.handle_page")
# def test_handle_retry(mock_handle_page, mock_chrome_restart_handler):
#     mock_driver = MagicMock()
#     mock_url = "http://example.com"

#     # Simulate successful retry
#     mock_handle_page.return_value = True
#     assert handle_retry(mock_driver, mock_url, 1, MAX_RETRIES) == mock_driver

#     # Simulate failure and restart
#     mock_handle_page.return_value = False
#     mock_chrome_restart_handler.return_value = mock_driver
#     assert handle_retry(mock_driver, mock_url, MAX_RETRIES, MAX_RETRIES) == mock_driver


# # Test for handle_view
# @patch("viewport.handle_page")
# @patch("viewport.check_driver")
# @patch("viewport.api_status")
# def test_handle_view(mock_api_status, mock_check_driver, mock_handle_page):
#     mock_driver = MagicMock()
#     mock_url = "http://example.com"

#     # Simulate healthy page
#     mock_handle_page.return_value = True
#     mock_check_driver.return_value = True
#     handle_view(mock_driver, mock_url)
#     mock_api_status.assert_called_with("Feed Healthy")


# # Test for chrome_handler
# @patch("viewport.webdriver.Chrome")
# @patch("viewport.Service")
# def test_chrome_handler(mock_service, mock_chrome):
#     mock_driver = MagicMock()
#     mock_chrome.return_value = mock_driver

#     mock_url = "http://example.com"
#     result = chrome_handler(mock_url)
#     assert result == mock_driver
#     mock_driver.get.assert_called_once_with(mock_url)


# # Test for chrome_restart_handler
# @patch("viewport.chrome_handler")
# @patch("viewport.handle_page")
# def test_chrome_restart_handler(mock_handle_page, mock_chrome_handler):
#     mock_driver = MagicMock()
#     mock_chrome_handler.return_value = mock_driver

#     mock_url = "http://example.com"
#     result = chrome_restart_handler(mock_url)
#     assert result == mock_driver
#     mock_handle_page.assert_called_once_with(mock_driver)


# # Test for restart_handler
# @patch("viewport.os.execv")
# def test_restart_handler(mock_execv):
#     mock_driver = MagicMock()

#     restart_handler(mock_driver)
#     mock_driver.quit.assert_called_once()
#     mock_execv.assert_called_once()


# # Test for process_handler
# @patch("viewport.subprocess.run")
# def test_process_handler(mock_subprocess_run):
#     mock_subprocess_run.return_value.stdout = "1234\n5678"

#     # Test check action
#     assert process_handler("mock_process", action="check") is True

#     # Test kill action
#     assert process_handler("mock_process", action="kill") is False