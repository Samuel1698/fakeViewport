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

# ---------------------------------------------------------------------
# Tests for get_cpu_color and get_mem_color
# ---------------------------------------------------------------------
@pytest.mark.parametrize(
    "name, pct, expected_color",
    [
        # viewport.py thresholds
        ("viewport.py", 0.5,  viewport.GREEN),   # below 1%
        ("viewport.py", 5,    viewport.YELLOW),  # between 1% and 10%
        ("viewport.py", 20,   viewport.RED),     # above 10%
        # browser thresholds (e.g. chrome)
        ("chrome",     30,    viewport.GREEN),   # below 50%
        ("chrome",     60,    viewport.YELLOW),  # between 50% and 70%
        ("chrome",     90,    viewport.RED),     # above 70%
    ],
)
def test_get_cpu_color(name, pct, expected_color):
    assert viewport.get_cpu_color(name, pct) == expected_color

@pytest.mark.parametrize(
    "pct, expected_color",
    [
        (35, viewport.GREEN),   # <=35%
        (50, viewport.YELLOW),  # <=60%
        (80, viewport.RED),     # >60%
    ],
)
def test_get_mem_color(pct, expected_color):
    assert viewport.get_mem_color(pct) == expected_color

# ---------------------------------------------------------------------
# Test get_browser_version
# ---------------------------------------------------------------------
def test_get_browser_version(monkeypatch):
    # stub subprocess.check_output to return a fake version string
    fake_output = b"Google-Chrome 100.0.4896.127\n"
    monkeypatch.setattr(viewport.subprocess, "check_output", lambda cmd, stderr: fake_output)

    version = viewport.get_browser_version("chrome")
    assert version == "100.0.4896.127"

# ---------------------------------------------------------------------
# Test usage_handler sums CPU and memory for matching processes
# ---------------------------------------------------------------------
def test_usage_handler(monkeypatch):
    # Helper for fake memory info
    class FakeMem:
        def __init__(self, rss): self.rss = rss

    # Fake Proc object
    class FakeProc:
        def __init__(self, pid, name, cmdline, cpu, mem):
            self.info    = {"pid": pid, "name": name, "cmdline": cmdline}
            self._cpu    = cpu
            self._mem    = mem
        def cpu_percent(self, interval):
            return self._cpu
        def memory_info(self):
            return FakeMem(self._mem)

    test_cases = [
        # match_str,                                      procs,                              expected_cpu, expected_mem
        (
            "viewport",
            [
                FakeProc(1, "viewport.py",    None,                  cpu=3.0, mem=1000),
                FakeProc(2, None,             ["python", "viewport"],cpu=2.0, mem=2000),
                FakeProc(3, "other.py",       None,                  cpu=5.0, mem=3000),
            ],
            5.0, 3000
        ),
        (
            "chrome",
            [
                FakeProc(1, "chrome",          None,              cpu=1.0, mem=100),
                FakeProc(2, None,             ["chromedriver"],   cpu=2.0, mem=200),
                FakeProc(3, "unrelated",       None,              cpu=9.0, mem=900),
            ],
            3.0, 300
        ),
        (
            "chromium",
            [
                FakeProc(1, "chromium",          None,             cpu=1.0, mem=100),
                FakeProc(2, None,             ["chromiumdriver"],  cpu=2.0, mem=200),
                FakeProc(3, "unrelated",       None,               cpu=9.0, mem=900),
            ],
            3.0, 300
        ),
    ]

    for match_str, procs, exp_cpu, exp_mem in test_cases:
        # patch process_iter to return our fake procs
        monkeypatch.setattr(
            viewport.psutil, "process_iter",
            lambda attrs: procs
        )

        total_cpu, total_mem = viewport.usage_handler(match_str)

        assert total_cpu == pytest.approx(exp_cpu), f"{match_str!r} CPU sum"
        assert total_mem == exp_mem,              f"{match_str!r} memory sum"