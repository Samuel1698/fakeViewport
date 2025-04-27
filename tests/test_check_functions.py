import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))
import logging
import logging.handlers
# stub out the rotating‐file handler before viewport.py ever sees it
logging.handlers.TimedRotatingFileHandler = lambda *args, **kwargs: logging.NullHandler()
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
# Test: check_driver
# ---------------------------------------------------------------------
@pytest.mark.parametrize(
    "title_value, side_effect, expected_result",
    [
        ("Mock Title", None, True),               # Normal title => success
        (None, WebDriverException, False),         # WebDriver crash => failure
        (None, Exception, False),                  # Other exception => failure
    ],
    ids=[
        "valid_title",
        "webdriver_exception",
        "generic_exception",
    ]
)
def test_check_driver(mock_driver, title_value, side_effect, expected_result):
    if side_effect:
        type(mock_driver).title = PropertyMock(side_effect=side_effect)
    else:
        mock_driver.title = title_value

    assert viewport.check_driver(mock_driver) is expected_result
# ---------------------------------------------------------------------
# Test: check_next_interval
# ---------------------------------------------------------------------
@pytest.mark.parametrize(
    "interval_seconds, now, expected",
    [
        (300, datetime(2025, 1, 1, 10, 51, 0), datetime(2025, 1, 1, 10, 55, 0)),
        (300, datetime(2025, 1, 1, 10, 59, 40), datetime(2025, 1, 1, 11, 5, 0)),
        (60,  datetime(2025, 1, 1, 10, 51, 10), datetime(2025, 1, 1, 10, 52, 0)),
        (60,  datetime(2025, 1, 1, 10, 59, 20), datetime(2025, 1, 1, 11, 0, 0)),
        (60,  datetime(2025, 1, 1, 10, 59, 59), datetime(2025, 1, 1, 11, 1, 0)),
    ]
)
def test_check_next_interval(interval_seconds, now, expected):
    result = viewport.check_next_interval(interval_seconds, now=now)
    assert datetime.fromtimestamp(result) == expected

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
        mock_common["log_error"].assert_called_with(expected_log_error)
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