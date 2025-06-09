import time as real_time
import pytest
from selenium.common.exceptions import TimeoutException
import viewport
from unittest.mock import MagicMock, patch

# --------------------------------------------------------------------------- # 
# Tests for handle_loading_issue function
# --------------------------------------------------------------------------- # 
@patch("viewport.WebDriverWait")
@patch("viewport.time.sleep", return_value=None)
@patch("viewport.log_error")
@patch("viewport.logging.info")
@patch("viewport.api_status")
@patch("viewport.handle_page")
@patch("viewport.time.time", side_effect=[0, 16])
def test_handle_loading_issue_persists_and_refreshes(
    mock_time, mock_handle_page, mock_api_status, mock_log_info, mock_log_error, mock_sleep, mock_wdw
):
    driver = MagicMock()
    viewport.CSS_LOADING_DOTS = ".dots"
    viewport.SLEEP_TIME = 10

    # force WebDriverWait(...).until(...) to always return truthy
    fake_wait = MagicMock()
    fake_wait.until.return_value = True
    mock_wdw.return_value = fake_wait

    # first time we record start_time = 0, second time time.time() - start_time >= 15
    viewport.time.time = mock_time
    mock_handle_page.return_value = True

    viewport.handle_loading_issue(driver)

    expected_log_error = "Video feed trouble persisting for 15 seconds, refreshing the page."
    args, _ = mock_log_error.call_args
    assert args[0] == expected_log_error
    driver.refresh.assert_called_once()
    mock_api_status.assert_called_once_with("Loading Issue Detected")
    # since handle_page returned True, we do not log Error Reloading nor sleep(SLEEP_TIME)

@patch("viewport.WebDriverWait")
@patch("viewport.time.sleep", return_value=None)
@patch("viewport.log_error")
@patch("viewport.logging.info")
@patch("viewport.api_status")
def test_handle_loading_issue_no_persistence(
    mock_api_status, mock_log_info, mock_log_error, mock_sleep, mock_wdw
):
    driver = MagicMock()
    viewport.CSS_LOADING_DOTS = ".dots"

    # Make every .until() call raise TimeoutException
    fake_wait = MagicMock()
    fake_wait.until.side_effect = TimeoutException
    mock_wdw.return_value = fake_wait

    # Run — it should loop 30× without ever logging or refreshing
    viewport.handle_loading_issue(driver)

    mock_log_error.assert_not_called()
    driver.refresh.assert_not_called()

@patch("viewport.log_error")
@patch("viewport.time.sleep", return_value=None)
def test_handle_loading_issue_inspection_error_raises(mock_sleep, mock_log_error):
    driver = MagicMock()
    viewport.CSS_LOADING_DOTS = ".dots"

    # Simulate driver.find_elements throwing
    driver.find_elements.side_effect = Exception("boom")

    with pytest.raises(Exception) as excinfo:
        viewport.handle_loading_issue(driver)

    # It should have logged the error
    expected_log_error = "Error checking loading dots: "
    args, _ = mock_log_error.call_args
    assert args[0] == expected_log_error
    
    # And the original exception should bubble out
    assert "boom" in str(excinfo.value)

# --------------------------------------------------------------------------- # 
# Case: loading persists → refresh → handle_page returns False
# Should hit the "Unexpected page loaded after refresh..." branch
# --------------------------------------------------------------------------- # 
@patch("viewport.time.sleep", return_value=None)
@patch("viewport.api_status")
@patch("viewport.log_error")
@patch("viewport.handle_page", return_value=False)
def test_handle_loading_issue_refresh_then_handle_page_fails(
    mock_handle_page, mock_log_error, mock_api_status, mock_sleep
):
    driver = MagicMock()
    viewport.CSS_LOADING_DOTS = ".dots"
    viewport.SLEEP_TIME = 7  # arbitrary

    # Simulate .find_elements always returning something
    driver.find_elements.return_value = [MagicMock()]

    # time.time: first call t0=0, second call t1=16 to exceed 15s threshold
    t0_t1 = [0, 16]
    def fake_time():
        return t0_t1.pop(0)
    patcher = patch("viewport.time.time", side_effect=fake_time)
    patcher.start()

    # Act
    viewport.handle_loading_issue(driver)

    patcher.stop()

    # First log_error for 15s persistence
    first = mock_log_error.call_args_list[0][0][0]
    assert first == "Video feed trouble persisting for 15 seconds, refreshing the page."

    # api_status for detection
    mock_api_status.assert_any_call("Loading Issue Detected")

    # driver.refresh and initial sleep(5)
    driver.refresh.assert_called_once()
    mock_sleep.assert_any_call(5)

    # Because handle_page returned False, we hit the reload-error branch:
    second = mock_log_error.call_args_list[1][0][0]
    assert second == "Unexpected page loaded after refresh. Waiting before retrying..."
    mock_api_status.assert_any_call("Error Reloading")

    # And we waited SLEEP_TIME afterward
    mock_sleep.assert_any_call(viewport.SLEEP_TIME)

# --------------------------------------------------------------------------- # 
# Case: loading appears then clears immediately → reset timer branch
# Should never refresh or log anything
# --------------------------------------------------------------------------- # 
@patch("viewport.time.sleep", return_value=None)
@patch("viewport.log_error")
@patch("viewport.api_status")
def test_handle_loading_issue_clears_loading_resets_timer(
    mock_api_status, mock_log_error, mock_sleep
):
    driver = MagicMock()
    viewport.CSS_LOADING_DOTS = ".dots"

    # find_elements: first iteration returns non-empty, second returns empty
    driver.find_elements.side_effect = [
        [MagicMock()],  # trouble starts
        [],             # clears immediately
    ] + [[]] * 28       # rest of the loops

    # time.time shouldn't matter here, but patch to keep signature
    patcher = patch("viewport.time.time", return_value=real_time.time())
    patcher.start()

    # Act
    viewport.handle_loading_issue(driver)

    patcher.stop()

    # No refresh, no errors, no api calls
    driver.refresh.assert_not_called()
    mock_log_error.assert_not_called()
    mock_api_status.assert_not_called()