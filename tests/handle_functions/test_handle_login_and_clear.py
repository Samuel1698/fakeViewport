import pytest
import viewport
from unittest.mock import MagicMock, patch, call
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.keys import Keys

# --------------------------------------------------------------------------- # 
# Tests for handle_login function
# --------------------------------------------------------------------------- # 
@pytest.mark.parametrize("exc, expect_ret, expect_error_msg, expect_api", [
    (None, True, None, None),
    (Exception("oops"), False, "Error during login: ", "Error Logging In"),
])
@patch("viewport.browser_restart_handler")
@patch("viewport.api_status")
@patch("viewport.log_error")
@patch("viewport.time.sleep", return_value=None)
@patch("viewport.handle_clear")
@patch("viewport.WebDriverWait")
def test_handle_login(
    mock_wdw, mock_handle_clear, mock_sleep, mock_log_error, mock_api_status, mock_restart,
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
            username_el.send_keys.assert_called_once_with("u")
            password_el.send_keys.assert_called_once_with("p")
            submit_el.click.assert_called_once()
            mock_check.assert_called_with(driver, "Dashboard")
            assert result is True
        else:
            mock_log_error.assert_called()
            mock_api_status.assert_called_with(expect_api)
            assert result is False

@patch("viewport.handle_clear")
def test_handle_login_trust_prompt_not_found(mock_handle_clear, monkeypatch):
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
    username_field.send_keys.assert_called_once_with("testuser")
    password_field.send_keys.assert_called_once_with("testpass")

    # Login button was clicked
    submit_button.click.assert_called_once()

    # check_for_title was called twice (before and after trust‐block)
    assert len(calls) == 2

@patch("viewport.handle_clear")
def test_handle_login_with_trust_device(mock_handle_clear, monkeypatch):
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
    username_el.send_keys.assert_called_once_with("testuser")
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

@patch("viewport.time.sleep", return_value=None)
@patch("viewport.handle_clear")
@patch("viewport.WebDriverWait")
def test_handle_login_uses_force_clear(mock_wdw, mock_handle_clear, mock_sleep, monkeypatch):
    driver = MagicMock()

    # fake elements returned by WebDriverWait.until()
    user_el, pass_el, submit_el = MagicMock(), MagicMock(), MagicMock()
    mock_wdw.return_value.until.side_effect = [user_el, pass_el, submit_el]

    # stub creds
    monkeypatch.setattr(viewport, "username", "demoUser")
    monkeypatch.setattr(viewport, "password", "demoPass")
    viewport.WAIT_TIME = 1

    # make title check succeed
    with patch("viewport.check_for_title", return_value=True):
        assert viewport.handle_login(driver) is True

    # handle_clear should be called for BOTH elements, in order
    mock_handle_clear.assert_has_calls(
        [call(driver, user_el), call(driver, pass_el)]
    )

# --------------------------------------------------------------------------- # 
# Tests for the handle_clear function
# --------------------------------------------------------------------------- # 
class DummyField:
    def __init__(self):
        self.value = "savedPASS"
        self.clear_called = False
        self.send_keys_calls = []

    def clear(self):
        # Selenium’s .clear()
        self.value = ""
        self.clear_called = True

    def send_keys(self, *args):
        # capture all send_keys calls
        self.send_keys_calls.append(args)

class DummyDriver:
    def __init__(self):
        self.script_calls = []

    def execute_script(self, script, element):
        self.script_calls.append(script)

def test_handle_clear_removes_prefilled_value():
    drv   = DummyDriver()
    field = DummyField()

    # Sanity: value starts non-empty
    assert field.value == "savedPASS"

    # Act
    viewport.handle_clear(drv, field)

    # Assert the input is now empty
    assert field.value == ""

    # And each clearing step ran
    assert field.clear_called is True
    assert any("value = ''" in s for s in drv.script_calls)
    assert (Keys.CONTROL, "a", Keys.DELETE) in field.send_keys_calls

@pytest.mark.parametrize("fail_step", ["clear", "execute_script", "send_keys"])
def test_handle_clear_swallows_exceptions(fail_step):
    # When any internal step inside handle_clear raises,
    # the helper must swallow the exception and exit silently.
    drv   = MagicMock()
    field = MagicMock()

    # Configure which step should raise
    if fail_step == "clear":
        field.clear.side_effect = Exception("boom")
    else:
        field.clear.return_value = None

    if fail_step == "execute_script":
        drv.execute_script.side_effect = Exception("boom")
    else:
        drv.execute_script.return_value = None

    if fail_step == "send_keys":
        field.send_keys.side_effect = Exception("boom")
    else:
        field.send_keys.return_value = None

    # Should NOT raise, regardless of which step failed
    viewport.handle_clear(drv, field)

    # Assertions: the failing step ran, later steps (if any) did not
    if fail_step == "clear":
        field.clear.assert_called_once()
        drv.execute_script.assert_not_called()
        field.send_keys.assert_not_called()
    elif fail_step == "execute_script":
        field.clear.assert_called_once()
        drv.execute_script.assert_called_once()
        field.send_keys.assert_not_called()
    else:  # fail_step == "send_keys"
        field.clear.assert_called_once()
        drv.execute_script.assert_called_once()
        field.send_keys.assert_called_once()