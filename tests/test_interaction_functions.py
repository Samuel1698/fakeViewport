import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))
import time
import pytest
from unittest.mock import MagicMock, patch, ANY
from selenium.common.exceptions import TimeoutException, WebDriverException, InvalidSessionIdException, NoSuchElementException
from urllib3.exceptions import NewConnectionError
import viewport 

# -----------------------------------------------------------------------------
# Test for handle_elements function
# -----------------------------------------------------------------------------
def test_handle_elements_executes_both_scripts():
    driver = MagicMock()
    viewport.CSS_CURSOR = "cursor-class"
    viewport.CSS_PLAYER_OPTIONS = "player-options-class"

    viewport.handle_elements(driver)

    assert driver.execute_script.call_count == 2

    # first call hides the cursor
    script1, arg1 = driver.execute_script.call_args_list[0][0]
    assert "hideCursorStyle" in script1
    assert arg1 == "cursor-class"

    # second call hides player options
    script2, arg2 = driver.execute_script.call_args_list[1][0]
    assert "hidePlayerOptionsStyle" in script2
    assert arg2 == "player-options-class"

# -----------------------------------------------------------------------------
# Tests for handle_loading_issue function
# -----------------------------------------------------------------------------
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

    mock_log_error.assert_called_once_with(
        "Video feed trouble persisting for 15 seconds, refreshing the page."
    )
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

# -----------------------------------------------------------------------------
# Test for handle_fullscreen_button function
# -----------------------------------------------------------------------------
@pytest.mark.parametrize("throw_exc, expect_return, expect_error_msg, expect_api", [
    (None, True, None, "Fullscreen Activated"),
    (WebDriverException(), None, "Tab Crashed. Restarting Chrome...", "Tab Crashed"),
    (Exception("bad"), False, "Error while clicking the fullscreen button: ", "Error Clicking Fullscreen"),
])
@patch("viewport.chrome_restart_handler")
@patch("viewport.api_status")
@patch("viewport.log_error")
@patch("viewport.logging.info")
@patch("viewport.time.sleep", return_value=None)
@patch("viewport.ActionChains")
@patch("viewport.WebDriverWait")
def test_handle_fullscreen_button(
    mock_wdw, mock_ac, mock_sleep, mock_log_info,
    mock_log_error, mock_api_status, mock_restart,
    throw_exc, expect_return, expect_error_msg, expect_api
):
    driver = MagicMock()
    viewport.WAIT_TIME = 1
    viewport.CSS_FULLSCREEN_PARENT = ".parent"
    viewport.CSS_FULLSCREEN_BUTTON = ".child"
    fake_parent = MagicMock()
    fake_button = MagicMock()

    # first WebDriverWait returns parent (or raises)
    wd_instance = MagicMock()
    if isinstance(throw_exc, WebDriverException):
        wd_instance.until.side_effect = throw_exc
    else:
        wd_instance.until.side_effect = [fake_parent, fake_button] if throw_exc is None else [fake_parent]
    mock_wdw.return_value = wd_instance

    # element_to_be_clickable is called on the parent
    # ActionChains chaining
    ac_instance = MagicMock()
    mock_ac.return_value = ac_instance

    result = viewport.handle_fullscreen_button(driver)

    if throw_exc is None:
        # success path
        ac_instance.move_to_element.assert_any_call(fake_parent)
        ac_instance.move_to_element.assert_any_call(fake_button)
        ac_instance.click.assert_not_called()  # we did .move_to_element(button).click().perform()
        mock_log_info.assert_called_with("Fullscreen activated")
        mock_api_status.assert_called_with(expect_api)
        assert result is True
    elif isinstance(throw_exc, WebDriverException):
        mock_log_error.assert_called_with("Tab Crashed. Restarting Chrome...")
        mock_api_status.assert_called_with(expect_api)
        mock_restart.assert_called_once()  # called with undefined url in code
        assert result is None
    else:
        # generic exception path
        mock_log_error.assert_called()
        mock_api_status.assert_called_with(expect_api)
        assert result is False

# -----------------------------------------------------------------------------
# Tests for handle_login function
# -----------------------------------------------------------------------------
@pytest.mark.parametrize("exc, expect_ret, expect_error_msg, expect_api", [
    (None, True, None, None),
    (WebDriverException(), None, "Tab Crashed. Restarting Chrome...", "Tab Crashed"),
    (Exception("oops"), False, "Error during login: ", "Error Logging In"),
])
@patch("viewport.chrome_restart_handler")
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
        elif isinstance(exc, WebDriverException):
            mock_log_error.assert_called_with("Tab Crashed. Restarting Chrome...")
            mock_api_status.assert_called_with("Tab Crashed")
            mock_restart.assert_called_once_with("http://example.com")
            assert result is None
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

    mock_log_error.assert_called_with("Unexpected page loaded. The page title is: Something Else")
    mock_api_status.assert_called_with("Error Loading Page Something Else")
    assert ret is False

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
@patch("viewport.chrome_restart_handler", return_value="NEW_DRIVER")
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

# max_retries − 1 branch
@patch("viewport.api_status")
@patch("viewport.logging.info")
@patch("viewport.chrome_restart_handler", return_value="CH_RESTARTED")
@patch("viewport.check_driver", return_value=True)
def test_handle_retry_final_before_restart(
    mock_check_driver,
    mock_chrome_restart,
    mock_log_info,
    mock_api_status,
):
    driver = MagicMock(title="Whatever")
    url = "u"

    # attempt == max_retries−1 → should call chrome_restart_handler and return its value
    result = viewport.handle_retry(driver, url, attempt=2, max_retries=3)

    mock_chrome_restart.assert_called_once_with("u")
    assert result == "CH_RESTARTED"

# max_retries branch
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
# Tests for handle_view function
# -----------------------------------------------------------------------------
class BreakLoop(BaseException):
    # Custom exception used to break out of the infinite loop in handle_view.
    pass
# -----------------------------------------------------------------------------
# Initial Load Failure
@patch("viewport.restart_handler", side_effect=SystemExit)
@patch("viewport.api_status")
@patch("viewport.log_error")
@patch("viewport.handle_page", return_value=False)
def test_handle_view_initial_load_failure(
    mock_hp, mock_log_error, mock_api_status, mock_restart
):
    driver = MagicMock()
    with pytest.raises(SystemExit):
        viewport.handle_view(driver, "http://example.com")

    mock_log_error.assert_called_with("Error loading the live view. Restarting the program.")
    mock_api_status.assert_called_with("Error Loading Live View. Restarting...")
    mock_restart.assert_called_once_with(driver)
# -----------------------------------------------------------------------------
# Healthy‐path iteration
@patch("viewport.time.sleep", side_effect=BreakLoop)
@patch("viewport.check_next_interval", return_value=time.time())
@patch("viewport.check_unable_to_stream", return_value=False)
@patch("viewport.api_status")
@patch("viewport.handle_elements")
@patch("viewport.handle_loading_issue")
@patch("viewport.handle_fullscreen_button", return_value=True)
@patch("viewport.WebDriverWait")
@patch("viewport.check_driver", return_value=True)
@patch("viewport.handle_page", return_value=True)
@patch("viewport.logging.info")
def test_handle_view_healthy_iteration(
    mock_log_info,
    mock_handle_page,
    mock_check_driver,
    mock_wdw,
    mock_fs_btn,
    mock_loading,
    mock_elements,
    mock_api_status,
    mock_unable,
    mock_next_interval,
    mock_sleep,
):
    drv = MagicMock()
    url = "http://example.com"

    # offline_status test → None
    # then two script calls for screen.width & height
    drv.execute_script.side_effect = [None, 1920, 1080]
    drv.get_window_size.return_value = {"width": 1920, "height": 1080}

    # WebDriverWait.until(...) succeeds
    fake_wdw = MagicMock()
    fake_wdw.until.return_value = True
    mock_wdw.return_value = fake_wdw

    with pytest.raises(BreakLoop):
        viewport.handle_view(drv, url)

    # initial handle_page log
    mock_handle_page.assert_called_once_with(drv)
    mock_log_info.assert_any_call(f"Checking health of page every {viewport.SLEEP_TIME} seconds...")

    # in‐loop sanity checks
    mock_check_driver.assert_called_once_with(drv)
    mock_loading.assert_called_once_with(drv)
    mock_elements.assert_called_once_with(drv)
    mock_api_status.assert_called_with("Feed Healthy")


# -----------------------------------------------------------------------------
# Offline‐status branch
@patch("viewport.time.sleep", return_value=None)
@patch("viewport.handle_retry", side_effect=BreakLoop)
@patch("viewport.api_status")
@patch("viewport.logging.warning")
@patch("viewport.WebDriverWait")
@patch("viewport.check_driver", return_value=True)
@patch("viewport.handle_page", return_value=True)
def test_handle_view_offline_branch(
    mock_handle_page,
    mock_check_driver,
    mock_wdw,
    mock_log_warn,
    mock_api_status,
    mock_handle_retry,
    mock_sleep,
):
    drv = MagicMock()
    url = "u"

    # first execute_script() → truthy offline element
    drv.execute_script.return_value = object()

    # stub out the later wait so we never progress past offline branch
    fake_wdw = MagicMock()
    fake_wdw.until.return_value = True
    mock_wdw.return_value = fake_wdw

    with pytest.raises(BreakLoop):
        viewport.handle_view(drv, url)

    mock_log_warn.assert_any_call("Detected offline status: Console or Protect Offline.")
    mock_api_status.assert_called_with("Console or Protect Offline")
    mock_handle_retry.assert_called_once_with(drv, url, 1, viewport.MAX_RETRIES)

# -----------------------------------------------------------------------------
# All errors branch
@pytest.mark.parametrize(
    "trigger, expected_log_args, expected_api, recovery_fn, recovery_args",
    [
        # 1) InvalidSessionIdException => restart_handler(driver)
        (
            # make check_driver raise
            lambda drv, wdw: setattr(viewport, "check_driver", MagicMock(side_effect=InvalidSessionIdException())),
            ("Chrome session is invalid. Restarting the program.",),
            "Restarting Program",
            "restart_handler",
            lambda drv, url, mw: (drv,)
        ),
        # 2) TimeoutException => handle_retry(driver, url, 1, max_retries)
        (
            lambda drv, wdw: setattr(wdw, "until", MagicMock(side_effect=TimeoutException())),
            ("Video feeds not found or page timed out.",),
            "Video Feeds Not Found",
            "handle_retry",
            lambda drv, url, mw: (drv, url, 1, mw)
        ),
        # 3) NoSuchElementException => same as TimeoutException
        (
            lambda drv, wdw: setattr(wdw, "until", MagicMock(side_effect=NoSuchElementException())),
            ("Video feeds not found or page timed out.",),
            "Video Feeds Not Found",
            "handle_retry",
            lambda drv, url, mw: (drv, url, 1, mw)
        ),
        # 4) NewConnectionError => handle_retry(driver, url, 1, max_retries)
        (
            # driver.execute_script raises NewConnectionError
            lambda drv, wdw: drv.execute_script.__setattr__("side_effect", NewConnectionError(None, "fail")),
            ("Connection error occurred. Retrying...",),
            "Connection Error",
            "handle_retry",
            lambda drv, url, mw: (drv, url, 1, mw)
        ),
        # 5) WebDriverException => chrome_restart_handler(url)
        (
            lambda drv, wdw: setattr(wdw, "until", MagicMock(side_effect=WebDriverException())),
            ("Tab Crashed. Restarting Chrome...",),
            "Tab Crashed",
            "chrome_restart_handler",
            lambda drv, url, mw: (url,)
        ),
        # 6) Generic Exception => handle_retry(driver, url, 1, max_retries)
        (
            lambda drv, wdw: setattr(wdw, "until", MagicMock(side_effect=Exception("oops"))),
            ("Unexpected error occurred: ", ANY),
            "Unexpected Error",
            "handle_retry",
            lambda drv, url, mw: (drv, url, 1, mw)
        ),
    ]
)
@patch("viewport.time.sleep", return_value=None)
@patch("viewport.chrome_restart_handler", side_effect=BreakLoop)
@patch("viewport.handle_retry", side_effect=BreakLoop)
@patch("viewport.restart_handler", side_effect=BreakLoop)
@patch("viewport.api_status")
@patch("viewport.log_error")
@patch("viewport.logging.warning")
@patch("viewport.logging.info")
@patch("viewport.WebDriverWait")
@patch("viewport.check_driver", return_value=True)
@patch("viewport.handle_page", return_value=True)
def test_handle_view_all_error_branches(
    mock_handle_page,        # bottom‐most patch
    mock_check_driver,
    mock_wdw,
    mock_log_info,
    mock_log_warn,
    mock_log_error,
    mock_api_status,
    mock_restart,            # restart_handler patch → mock_restart
    mock_retry,              # handle_retry patch   → mock_retry
    mock_chrome_restart,     # chrome_restart_handler → mock_chrome_restart
    mock_sleep,              # time.sleep patch
    trigger,
    expected_log_args,
    expected_api,
    recovery_fn,
    recovery_args
):
    drv = MagicMock()
    url = "http://example.com"

    # handle_page passes, no offline status
    drv.execute_script.return_value = None

    # stub presence_of_element_located to succeed by default
    fake_wait = MagicMock()
    fake_wait.until.return_value = True
    mock_wdw.return_value = fake_wait

    # inject the chosen exception scenario
    trigger(drv, fake_wait)

    with pytest.raises(BreakLoop):
        viewport.handle_view(drv, url)

    # 1) check log_error args
    mock_log_error.assert_any_call(*expected_log_args)

    # 2) check api_status
    mock_api_status.assert_called_with(expected_api)

    # 3) dispatch to the right recovery mock
    if recovery_fn == "restart_handler":
        rec = mock_restart
    elif recovery_fn == "handle_retry":
        rec = mock_retry
    elif recovery_fn == "chrome_restart_handler":
        rec = mock_chrome_restart
    else:
        pytest.fail(f"Unknown recovery_fn: {recovery_fn}")

    rec.assert_called_once_with(*recovery_args(drv, url, viewport.MAX_RETRIES))