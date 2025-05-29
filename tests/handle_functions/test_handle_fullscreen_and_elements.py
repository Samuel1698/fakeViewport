import pytest
import viewport 
from unittest.mock import MagicMock, patch
# ----------------------------------------------------------------------------- 
# Test for handle_elements function
# ----------------------------------------------------------------------------- 
def test_handle_elements_hides_cursor_and_player_options():
    driver = MagicMock()

    # handle_elements now expects lists (even if length‑1)
    viewport.CSS_CURSOR = ["cursor-class"]
    viewport.CSS_PLAYER_OPTIONS = ["player-options-class"]
    viewport.hide_delay_ms = 3000       

    viewport.handle_elements(driver)

    # Exactly ONE execute_script call
    driver.execute_script.assert_called_once()
    script, cursors, options, delay = driver.execute_script.call_args[0]

    # correct style‑tag id inside the injected JS
    assert "hideCursorAndOptionsStyle" in script

    # the two selector arrays are forwarded unchanged
    assert cursors  == ["cursor-class"]
    assert options  == ["player-options-class"]

    # delay propagated
    assert delay == 3000
# ----------------------------------------------------------------------------- 
# Test for handle_fullscreen_button function
# ----------------------------------------------------------------------------- 
@pytest.mark.parametrize("throw_exc, expect_return, expect_error_msg, expect_api", [
    (None, True, None, "Fullscreen Activated"),
    (Exception("bad"), False, "Error while clicking the fullscreen button: ", "Error Clicking Fullscreen"),
])
@patch("viewport.browser_restart_handler")
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
    else:
        # generic exception path
        mock_log_error.assert_called()
        mock_api_status.assert_called_with(expect_api)
        assert result is False

