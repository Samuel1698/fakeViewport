import pytest
from unittest.mock import MagicMock, PropertyMock, patch
from selenium.common.exceptions import TimeoutException, WebDriverException
from datetime import datetime

import viewport

# ---------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------
@pytest.fixture
def mock_driver():
    return MagicMock()

@pytest.fixture(autouse=True)
def mock_common(mocker):
    patches = {
        "wait": mocker.patch("viewport.WebDriverWait"),
        "api_status": mocker.patch("viewport.api_status"),
        "log_error": mocker.patch("viewport.log_error"),
        "logging": mocker.patch("viewport.logging"),
    }
    return patches
# ---------------------------------------------------------------------
# Test: check_crash
# ---------------------------------------------------------------------
@pytest.mark.parametrize(
    "page_source, expected",
    [
        # 1) Page contains the "Aw, Snap!" crash banner
        ("<html>…Aw, Snap! Something broke…</html>", True),
        # 2) Page contains "Tab Crashed" text
        ("<div>Error: Tab Crashed while loading</div>", True),
        # 3) No crash indicators present
        ("<html><body>All systems operational.</body></html>", False),
        # 4) Partial match of "Aw, Snap" without the exclamation
        ("<p>Aw, Snap this is just text</p>", False),
        # 5) Partial match of "Crashed" without full phrase
        ("<span>The process crashed unexpectedly</span>", False),
    ],
    ids=[
        "contains_aw_snap",
        "contains_tab_crashed",
        "no_crash",
        "partial_aw_snap",
        "partial_crashed",
    ]
)
def test_check_crash(page_source, expected):
    # Create a dummy driver with a configurable page_source
    class DummyDriver:
        pass

    driver = DummyDriver()
    driver.page_source = page_source

    # Assert that check_crash returns the expected boolean
    assert viewport.check_crash(driver) is expected
# ---------------------------------------------------------------------
# Test: check_driver should return True on success, otherwise raise
# ---------------------------------------------------------------------
@pytest.mark.parametrize(
    "title_value, side_effect, expected_exception",
    [
        # 1) Normal title ⇒ returns True
        ("Mock Title",   None,               None),
        # 2) Selenium failure ⇒ should propagate WebDriverException
        (None,           WebDriverException, WebDriverException),
        # 3) Other error ⇒ should propagate generic Exception
        (None,           Exception,          Exception),
    ],
    ids=[
        "valid_title",
        "webdriver_exception",
        "generic_exception",
    ]
)
def test_check_driver(mock_driver, title_value, side_effect, expected_exception):
    # Arrange: either stub driver.title to return a value or raise
    if side_effect:
        type(mock_driver).title = PropertyMock(side_effect=side_effect)
    else:
        mock_driver.title = title_value

    # Act & Assert
    if expected_exception:
        with pytest.raises(expected_exception):
            viewport.check_driver(mock_driver)
    else:
        assert viewport.check_driver(mock_driver) is True
# ---------------------------------------------------------------------
# Test: check_for_title
# ---------------------------------------------------------------------
@pytest.mark.parametrize(
    "side_effect, title, expected_result, expected_log_error, expected_api_status",
    [
        (None, "Test Page", True, None, "Loaded page: 'Test Page'"),
        (TimeoutException, "Missing Page", False, "Timed out waiting for the title 'Missing Page' to load.", "Timed Out Waiting for Title 'Missing Page'"),
        (WebDriverException, "Test Page", False, "Tab Crashed.", "Tab Crashed"),
    ],
    ids=[
        "successful_load",
        "timeout_waiting_for_title",
        "webdriver_crash",
    ]
)
def test_check_for_title(mock_driver, mock_common, side_effect, title, expected_result, expected_log_error, expected_api_status):
    if side_effect:
        mock_common["wait"].return_value.until.side_effect = side_effect
    else:
        mock_common["wait"].return_value.until.return_value = True

    result = viewport.check_for_title(mock_driver, title=title)

    assert result is expected_result

    if expected_log_error:
        args, _ = mock_common["log_error"].call_args
        assert args[0] == expected_log_error
    else:
        mock_common["log_error"].assert_not_called()
        
    if expected_api_status:
        mock_common["api_status"].assert_called_with(expected_api_status)
    else:
        mock_common["api_status"].assert_not_called()

    if expected_result and title:
        mock_common["logging"].info.assert_called_with(f"Loaded page: '{title}'")

def test_check_for_title_no_title_given(mock_driver, mock_common):
    mock_common["wait"].return_value.until.return_value = True

    result = viewport.check_for_title(mock_driver)

    assert result is True
    mock_common["log_error"].assert_not_called()
    mock_common["api_status"].assert_not_called()

# ---------------------------------------------------------------------
# Test: check_unable_to_stream
# ---------------------------------------------------------------------
@pytest.mark.parametrize(
    "script_result, side_effect, expected_result, expect_log_error, expect_api_status",
    [
        (["mock-element"], None, True, False, False),       # Element found
        ([], None, False, False, False),                    # No element found
        (None, WebDriverException, False, True, True),      # WebDriver crash
        (None, Exception("Some JS error"), False, True, True),  # Other JS error
    ],
    ids=[
        "element_found",
        "no_element_found",
        "webdriver_crash",
        "generic_js_error",
    ]
)
@patch("viewport.api_status")
@patch("viewport.log_error")
def test_check_unable_to_stream(mock_log_error, mock_api_status, script_result, side_effect, expected_result, expect_log_error, expect_api_status):
    mock_driver = MagicMock()

    if side_effect:
        mock_driver.execute_script.side_effect = side_effect
    else:
        mock_driver.execute_script.return_value = script_result

    result = viewport.check_unable_to_stream(mock_driver)

    assert result is expected_result

    if expect_log_error:
        mock_log_error.assert_called()
    else:
        mock_log_error.assert_not_called()

    if expect_api_status:
        mock_api_status.assert_called()
    else:
        mock_api_status.assert_not_called()