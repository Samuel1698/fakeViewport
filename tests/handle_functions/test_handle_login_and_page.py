import pytest
import viewport
from unittest.mock import MagicMock, patch, call
from selenium.common.exceptions import TimeoutException
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
        submit_el   = MagicMock()
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
    
def test_handle_login_trust_prompt_not_found(monkeypatch):
    driver = MagicMock()

    # Stub credentials
    monkeypatch.setattr(viewport, "username", "testuser")
    monkeypatch.setattr(viewport, "password", "testpass")

    # Prepare fake fields
    username_field = MagicMock()
    password_field = MagicMock()
    submit_button = MagicMock()

    # WebDriverWait.until should return username, password, submit, then raise TimeoutException
    seq = [username_field, password_field, submit_button]
    def fake_until(cond):
        if seq:
            return seq.pop(0)
        raise TimeoutException()
    monkeypatch.setattr(viewport, "WebDriverWait", lambda drv, t: MagicMock(until=fake_until))

    # check_for_title returns False on first call, True on second
    calls = []
    def fake_check(drv, title="Dashboard"):
        calls.append(title)
        return False if len(calls) == 1 else True
    monkeypatch.setattr(viewport, "check_for_title", fake_check)

    # No real sleeping
    monkeypatch.setattr(viewport.time, "sleep", lambda s: None)

    # Act
    result = viewport.handle_login(driver)

    # Assert
    assert result is True

    # Credentials were entered
    username_field.clear.assert_called_once()
    username_field.send_keys.assert_called_once_with("testuser")
    password_field.clear.assert_called_once()
    password_field.send_keys.assert_called_once_with("testpass")

    # Login button was clicked
    submit_button.click.assert_called_once()

    # check_for_title was called twice (before and after trust‐block)
    assert len(calls) == 2


def test_handle_login_with_trust_device(monkeypatch):
    driver = MagicMock()

    # stub credentials
    monkeypatch.setattr(viewport, "username", "testuser")
    monkeypatch.setattr(viewport, "password", "testpass")

    # create the elements returned by WebDriverWait.until()
    username_el   = MagicMock()
    password_el   = MagicMock()
    submit_btn    = MagicMock()
    trust_span    = MagicMock()
    trust_button  = MagicMock()

    # When we do trust_span.find_element(...), return our fake button
    trust_span.find_element.return_value = trust_button

    # WebDriverWait.until should return username, password, submit, then trust_span
    seq = [username_el, password_el, submit_btn, trust_span]
    def fake_until(cond):
        return seq.pop(0)
    monkeypatch.setattr(
        viewport,
        "WebDriverWait",
        lambda drv, t: MagicMock(until=fake_until)
    )

    # check_for_title: first call False (login not yet complete),
    # second call True (after trusting device)
    calls = {"n": 0}
    def fake_check_for_title(drv, title="Dashboard"):
        calls["n"] += 1
        return calls["n"] > 1
    monkeypatch.setattr(viewport, "check_for_title", fake_check_for_title)

    # Spy on time.sleep so we can assert the 1s pause after clicking
    sleep_calls = []
    monkeypatch.setattr(viewport.time, "sleep", lambda s: sleep_calls.append(s))

    # Stub out error handlers to avoid side effects
    monkeypatch.setattr(viewport, "log_error", MagicMock())
    monkeypatch.setattr(viewport, "api_status", MagicMock())

    # Act
    result = viewport.handle_login(driver)

    # Assert
    assert result is True

    # Credentials flow
    username_el.clear.assert_called_once()
    username_el.send_keys.assert_called_once_with("testuser")
    password_el.clear.assert_called_once()
    password_el.send_keys.assert_called_once_with("testpass")
    submit_btn.click.assert_called_once()

    # Trust‐this‐device flow
    trust_span.find_element.assert_called_once_with(
        viewport.By.XPATH,
        "./ancestor::button"
    )
    trust_button.click.assert_called_once()

    # We should sleep 1 second after clicking "Trust This Device"
    assert 1 in sleep_calls
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

# handle_page should *not* call handle_elements when HIDE_CURSOR is False
@patch("viewport.time.sleep", return_value=None)
@patch("viewport.check_for_title")
@patch("viewport.handle_elements")
def test_handle_page_no_elements_when_hide_cursor_false(
    mock_handle_elements,
    mock_check_title,
    mock_sleep,
    monkeypatch,
):
    # Disable cursor-hiding
    monkeypatch.setattr(viewport, "HIDE_CURSOR", False)

    # Pretend we’re already on the dashboard
    driver = MagicMock(title="Dashboard – Protect")
    viewport.WAIT_TIME = 1
    mock_check_title.return_value = None

    assert viewport.handle_page(driver) is True
    mock_handle_elements.assert_not_called()

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
