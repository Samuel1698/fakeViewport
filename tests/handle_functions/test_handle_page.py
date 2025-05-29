import pytest
import viewport
from unittest.mock import MagicMock, patch, call
# ----------------------------------------------------------------------------- 
# Tests for handle_page function
# ----------------------------------------------------------------------------- 
@patch("viewport.handle_elements")
@patch("viewport.check_for_title")
@patch("viewport.time.sleep", return_value=None)
@patch("viewport.logging.info")
def test_handle_page_dashboard_short_circuits(
    mock_log_info, mock_sleep, mock_check, mock_handle_elements
):
    driver = MagicMock(title="Dashboard Home")
    viewport.WAIT_TIME = 1
    mock_check.return_value = None

    ret = viewport.handle_page(driver)

    mock_check.assert_called_once_with(driver)
    mock_handle_elements.assert_called_once_with(driver)
    assert ret is True

@patch("viewport.log_error")
@patch("viewport.api_status")
@patch("viewport.check_for_title")
@patch("viewport.time.time")
@patch("viewport.time.sleep", return_value=None)
def test_handle_page_timeout_logs_and_returns_false(
    mock_sleep, mock_time, mock_check, mock_api_status, mock_log_error
):
    driver = MagicMock(title="Something Else")
    viewport.WAIT_TIME = 1

    # simulate time() so that after first check we immediately exceed WAIT_TIME*2
    mock_time.side_effect = [0, 3]
    ret = viewport.handle_page(driver)

    expected_log_error = "Unexpected page loaded. The page title is: Something Else"
    args, _ = mock_log_error.call_args
    assert args[0] == expected_log_error

    mock_api_status.assert_called_with("Error Loading Page Something Else")
    assert ret is False
# Covers the "Ubiquiti Account" / "UniFi OS" login‐page branch when login fails
@patch("viewport.handle_login", return_value=False)
@patch("viewport.logging.info")
@patch("viewport.check_for_title")
@patch("viewport.time.sleep", return_value=None)
def test_handle_page_login_page_fails(
    mock_sleep,
    mock_check_for_title,
    mock_log_info,
    mock_handle_login,
):
    # Arrange: driver.title indicates the login screen
    driver = MagicMock(title="Ubiquiti Account - please sign in")
    viewport.WAIT_TIME = 1  # so timeout logic won't kick in before our branch

    # Act
    result = viewport.handle_page(driver)

    # Assert: we tried to wait for title first
    mock_check_for_title.assert_called_once_with(driver)

    # We logged the login‐page message
    mock_log_info.assert_called_once_with("Log-in page found. Inputting credentials...")

    # Since handle_login returned False, handle_page should return False
    assert result is False

# Covers looping until title becomes Dashboard, then hits the final sleep(3)
@patch("viewport.handle_elements")
@patch("viewport.check_for_title")
@patch("viewport.time.sleep", return_value=None)
def test_handle_page_loops_then_dashboard(mock_sleep, mock_check_for_title, mock_handle_elements):
    # Arrange: simulate driver.title changing over iterations
    titles = ["Loading...", "Still Loading", "Dashboard | Protect"]
    class DummyDriver:
        def __init__(self, titles):
            self._titles = titles
            self._idx = -1
        @property
        def title(self):
            self._idx += 1
            # once past the list, stay at the last title
            return self._titles[min(self._idx, len(self._titles) - 1)]

    driver = DummyDriver(titles)
    # Make WAIT_TIME large enough so we never hit the timeout
    viewport.WAIT_TIME = 10
    # Act
    result = viewport.handle_page(driver)

    # Assert we returned True
    assert result is True

    # check_for_title should have been called once before the loop
    mock_check_for_title.assert_called_once_with(driver)

    # handle_elements should run exactly once when we hit Dashboard
    mock_handle_elements.assert_called_once_with(driver)

    # We expect two outer sleep(3) calls:
    #   1) after "Loading..." iteration
    #   2) after "Still Loading" iteration
    #   Inner sleep call gets a different MagicMock ID
    assert mock_sleep.call_count == 2
    assert mock_sleep.call_args_list == [call(3), call(3)]