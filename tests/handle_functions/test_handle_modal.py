import pytest
from unittest.mock import MagicMock, patch
from selenium.common.exceptions import TimeoutException
import viewport

@pytest.fixture
def mock_driver():
    return MagicMock()

def test_handle_modal_success(mock_driver):
    with patch("viewport.WebDriverWait") as MockWait, \
        patch("viewport.ActionChains") as MockActions:
        # Simulate modal presence
        mock_driver.execute_script.return_value = True

        # Setup mocks for wait and actions
        mock_button = MagicMock()
        MockWait.return_value.until.side_effect = [
            mock_button,  # wait for close button
            True          # wait for modal to disappear
        ]
        mock_action_chain = MagicMock()
        MockActions.return_value = mock_action_chain

        assert viewport.handle_modal(mock_driver) is True
        mock_action_chain.click.assert_called()

def test_handle_modal_no_modal(mock_driver):
    mock_driver.execute_script.return_value = False
    assert viewport.handle_modal(mock_driver) is False

def test_handle_modal_no_close_button(mock_driver):
    mock_driver.execute_script.return_value = True
    with patch("viewport.WebDriverWait") as MockWait:
        MockWait.return_value.until.side_effect = TimeoutException
        assert viewport.handle_modal(mock_driver) is False

def test_handle_modal_close_button_but_modal_does_not_disappear(mock_driver):
    with patch("viewport.WebDriverWait") as MockWait, \
        patch("viewport.ActionChains"):
        mock_driver.execute_script.return_value = True
        mock_button = MagicMock()
        MockWait.return_value.until.side_effect = [
            mock_button,           # close button found
            TimeoutException()     # modal doesn't disappear
        ]
        assert viewport.handle_modal(mock_driver) is False

def test_handle_modal_unexpected_exception(mock_driver):
    mock_driver.execute_script.side_effect = Exception("unexpected")
    assert viewport.handle_modal(mock_driver) is False
