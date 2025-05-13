import pytest
import viewport
from unittest.mock import MagicMock, patch
# ----------------------------------------------------------------------------- 
# Tests for handle_login function
# ----------------------------------------------------------------------------- 
@pytest.mark.parametrize("exc, expect_ret, expect_error_msg, expect_api", [
    (None, True, None, None),
    (Exception("oops"), False, "Error during login: ", "Error Logging In"),
])
@patch("viewport.browser_restart_handler")
@patch("viewport.api_status")
@patch("viewport.log_error")
@patch("viewport.time.sleep", return_value=None)
@patch("viewport.WebDriverWait")
def test_handle_login(
    mock_wdw, mock_sleep, mock_log_error, mock_api_status, mock_restart,
    exc, expect_ret, expect_error_msg, expect_api
):
    driver = MagicMock()
    viewport.WAIT_TIME = 1
    viewport.username = "u"
    viewport.password = "p"
    viewport.url = "http://example.com"
    # check_for_title returns True only on success path
    with patch("viewport.check_for_title", return_value= True if exc is None else None) as mock_check:
        # build three calls: username field, password field, submit button
        username_el = MagicMock()
        password_el = MagicMock()
        submit_el = MagicMock()
        wd = MagicMock()
        if exc is None:
            wd.until.side_effect = [username_el, password_el, submit_el]
        else:
            wd.until.side_effect = exc
        mock_wdw.return_value = wd

        result = viewport.handle_login(driver)

        if exc is None:
            username_el.clear.assert_called_once()
            username_el.send_keys.assert_called_once_with("u")
            password_el.clear.assert_called_once()
            password_el.send_keys.assert_called_once_with("p")
            submit_el.click.assert_called_once()
            mock_check.assert_called_with(driver, "Dashboard")
            assert result is True
        else:
            mock_log_error.assert_called()
            mock_api_status.assert_called_with(expect_api)
            assert result is False

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
