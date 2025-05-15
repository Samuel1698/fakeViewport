import pytest
import viewport
from unittest.mock import MagicMock, patch, call
from selenium.common.exceptions import WebDriverException
# ----------------------------------------------------------------------------- 
# Tests for handle_retry function
# ----------------------------------------------------------------------------- 
@pytest.mark.parametrize("attempt,title,check_driver_ok,login_ok,fullscreen_ok,expected_calls", [
    # 1) normal reload path
    (0, "Some Other", True, None, None, ["Attempting to load page from URL.", "Page successfully reloaded."]),
    # 2) login‐page path
    (0, "Ubiquiti Account", True, True, False, ["Log-in page found. Inputting credentials...",]),
])
@patch("viewport.restart_handler")
@patch("viewport.browser_restart_handler", return_value="NEW_DRIVER")
@patch("viewport.handle_fullscreen_button", return_value=False)
@patch("viewport.handle_login")
@patch("viewport.handle_page", return_value=True)
@patch("viewport.check_driver")
@patch("viewport.api_status")
@patch("viewport.logging.info")
@patch("viewport.time.sleep", return_value=None)
def test_handle_retry_basic_paths(
    mock_sleep, mock_log_info, mock_api_status, mock_check_driver,
    mock_handle_page, mock_handle_login, mock_handle_fs, mock_chrome_restart,
    mock_restart, attempt, title, check_driver_ok, login_ok, fullscreen_ok, expected_calls
):
    driver = MagicMock(title=title)
    url = "http://example.com"
    max_retries = 3

    mock_check_driver.return_value = check_driver_ok
    mock_handle_login.return_value = login_ok

    ret = viewport.handle_retry(driver, url, attempt, max_retries)

    # verify log/info calls for expected branch messages
    for msg in expected_calls:
        assert any(msg in args[0] for args in mock_log_info.call_args_list)

    # on login case, ensure handle_login + feed‐healthy
    if "Log-in page" in expected_calls[0]:
        mock_handle_login.assert_called_once_with(driver)
        mock_api_status.assert_any_call("Feed Healthy")

    # on normal reload, ensure driver.get called
    if "Attempting to load page" in expected_calls[0]:
        driver.get.assert_called_once_with(url)
        mock_api_status.assert_any_call("Feed Healthy")
        mock_sleep.assert_called()
# ----------------------------------------------------------------------------- 
# max_retries − 1 branch
# ----------------------------------------------------------------------------- 
@patch("viewport.api_status")
@patch("viewport.logging.info")
@patch("viewport.browser_restart_handler", return_value="CH_RESTARTED")
@patch("viewport.check_driver", return_value=True)
def test_handle_retry_final_before_restart(
    mock_check_driver,
    mock_chrome_restart,
    mock_log_info,
    mock_api_status,
):
    driver = MagicMock(title="Whatever")
    url = "u"

    # attempt == max_retries−1 → should call browser_restart_handler and return its value
    result = viewport.handle_retry(driver, url, attempt=2, max_retries=3)

    mock_chrome_restart.assert_called_once_with("u")
    assert result == "CH_RESTARTED"
# ----------------------------------------------------------------------------- 
# max_retries branch
# ----------------------------------------------------------------------------- 
@patch("viewport.restart_handler")
@patch("viewport.logging.info")
@patch("viewport.api_status")
def test_handle_retry_max_retries_calls_restart(mock_api, mock_info, mock_restart):
    driver = MagicMock()
    url = "u"
    # attempt == max_retries triggers restart_handler
    viewport.handle_retry(driver, url, attempt=3, max_retries=3)
    mock_info.assert_any_call("Max Attempts reached, restarting script...")
    mock_api.assert_called_with("Max Attempts Reached, restarting script")
    mock_restart.assert_called_once_with(driver)
# ----------------------------------------------------------------------------- 
# handle_retry triggers browser_restart_handler when driver has crashed
# ----------------------------------------------------------------------------- 
@patch("viewport.browser_restart_handler", return_value=MagicMock(title="Dashboard Home"))
@patch("viewport.handle_fullscreen_button", return_value=True)
@patch("viewport.handle_login", return_value=True)
@patch("viewport.handle_page", return_value=True)
@patch("viewport.check_driver", return_value=False)                       # simulate crash
@patch("viewport.api_status")
@patch("viewport.logging.warning")
@patch("viewport.logging.info")
@patch("viewport.time.sleep", return_value=None)
def test_handle_retry_detects_driver_crash_and_restarts(
    mock_sleep,
    mock_log_info,
    mock_log_warning,
    mock_api_status,
    mock_check_driver,
    mock_handle_page,
    mock_handle_login,
    mock_fs_btn,
    mock_chrome_restart,
):
    driver = MagicMock(title="Old Title")
    url = "http://example.com"

    result = viewport.handle_retry(driver, url, attempt=0, max_retries=3)

    # 1) we should have warned about a crash...
    mock_log_warning.assert_called_once_with("WebDriver crashed.")
    # 2) ...and then invoked browser_restart_handler(url)
    mock_chrome_restart.assert_called_once_with(url)

    new_driver = mock_chrome_restart.return_value
    # 3) new driver should be used to reload the page
    new_driver.get.assert_called_once_with(url)
    # 4) and we should have reported “Feed Healthy”
    mock_api_status.assert_called_with("Feed Healthy")
    # 5) finally, the returned driver is the new one
    assert result is new_driver

# ----------------------------------------------------------------------------- 
# InvalidSessionIdException path
# ----------------------------------------------------------------------------- 
@patch("viewport.log_error")
@patch("viewport.api_status")
@patch("viewport.restart_handler")
@patch("viewport.check_driver", side_effect=viewport.InvalidSessionIdException("bad session"))
def test_handle_retry_invalid_session(
    mock_check_driver, mock_restart, mock_api_status, mock_log_error
):
    driver = MagicMock(title="Dashboard")
    url = "http://x"
    attempt = 1
    max_retries = 5

    result = viewport.handle_retry(driver, url, attempt=attempt, max_retries=max_retries)

    # api_status should first log the retry, then the branch
    assert mock_api_status.call_args_list == [
        call(f"Retrying: {attempt} of {max_retries}"),
        call("Restarting Program"),
    ]

    # log_error called once with our InvalidSessionIdException
    err_call = mock_log_error.call_args[0]
    assert err_call[0] == f"{viewport.BROWSER} session is invalid. Restarting the program."
    assert isinstance(err_call[1], viewport.InvalidSessionIdException)

    # restart_handler must be invoked with the original driver
    mock_restart.assert_called_once_with(driver)

    # return value is whatever restart_handler returned (None by default)
    assert result is driver
    
# ----------------------------------------------------------------------------- 
# WebDriverException path
# ----------------------------------------------------------------------------- 
@patch("viewport.log_error")
@patch("viewport.api_status")
@patch("viewport.browser_restart_handler", return_value="new-driver")
@patch("viewport.check_driver", return_value=True)
def test_handle_retry_webdriver_exception(
    mock_check, mock_browser_restart, mock_api_status, mock_log_error
):
    driver = MagicMock(title="Dashboard")
    driver.get.side_effect = WebDriverException("tab died")
    url = "http://x"
    attempt = 0
    max_retries = 3

    result = viewport.handle_retry(driver, url, attempt=attempt, max_retries=max_retries)

    # api_status first logs retry, then "Tab Crashed"
    assert mock_api_status.call_args_list == [
        call(f"Retrying: {attempt} of {max_retries}"),
        call("Tab Crashed"),
    ]

    # log_error called once with the WebDriverException
    err_call = mock_log_error.call_args[0]
    assert err_call[0] == f"Tab Crashed. Restarting {viewport.BROWSER}..."
    assert isinstance(err_call[1], WebDriverException)

    # browser_restart_handler should be called once with the URL
    mock_browser_restart.assert_called_once_with(url)
    # and return value is what it returned
    assert result == "new-driver"

# ----------------------------------------------------------------------------- 
# Generic Exception path
# ----------------------------------------------------------------------------- 
@patch("viewport.log_error")
@patch("viewport.api_status")
@patch("viewport.check_driver", return_value=True)
def test_handle_retry_generic_exception(
    mock_check, mock_api_status, mock_log_error
):
    driver = MagicMock(title="Dashboard")
    url = "http://x"
    attempt = 0
    max_retries = 2

    # Patch handle_page to throw something unexpected
    with patch.object(viewport, "handle_page", side_effect=ValueError("oops")):
        result = viewport.handle_retry(driver, url, attempt=attempt, max_retries=max_retries)

    # api_status should first log retry, then "Error refreshing"
    assert mock_api_status.call_args_list == [
        call(f"Retrying: {attempt} of {max_retries}"),
        call("Error refreshing"),
    ]

    # log_error should be called once with our ValueError
    err_call = mock_log_error.call_args[0]
    assert err_call[0] == "Error while handling retry logic: "
    assert isinstance(err_call[1], ValueError)
    assert err_call[2] is driver

    # since this is attempt < max_retries-1, we return the original driver
    assert result is driver
    
# -----------------------------------------------------------------------------
# Page Failure path
# -----------------------------------------------------------------------------
from unittest.mock import MagicMock, patch, call
import pytest
import viewport

@patch("viewport.api_status")
@patch("viewport.logging.warning")
@patch("viewport.logging.info")
@patch("viewport.handle_page", return_value=False)
@patch("viewport.check_driver", return_value=True)
def test_handle_retry_page_failure(
    mock_check_driver,
    mock_handle_page,
    mock_log_info,
    mock_log_warning,
    mock_api_status,
):
    driver = MagicMock(title="Whatever")
    url = "http://example.com"
    attempt = 1
    max_retries = 3

    # Act
    result = viewport.handle_retry(driver, url, attempt=attempt, max_retries=max_retries)

    # Assert: info-logging for failed reload
    mock_log_info.assert_any_call("Couldn't reload page.")

    # Assert: warning-logging for skipping fullscreen / healthy-feed
    mock_log_warning.assert_called_once_with(
        "Page reload failed; skipping fullscreen and healthy-feed status."
    )

    # Assert: api_status called for retry then unhealthy feed
    assert mock_api_status.call_args_list == [
        call(f"Retrying: {attempt} of {max_retries}"),
        call("Couldn't verify feed"),
    ]

    # And our driver should just be returned unchanged
    assert result is driver