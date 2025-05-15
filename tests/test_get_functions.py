import pytest
import concurrent.futures
from unittest.mock import MagicMock, PropertyMock, patch
from selenium.common.exceptions import TimeoutException, WebDriverException
from datetime import datetime, time as dt_time, timedelta
import viewport
# from viewport import viewport.get_driver_path

# ----------------------------------------------------------------------------- 
# Fixtures and Helpers
# ----------------------------------------------------------------------------- 
class DummyMgr:
    def __init__(self, *args, **kwargs):
        pass

    def install(self):
        return "/fake/driver/path"
class DummyFuture:
    def result(self, timeout=None):
        # always time out
        raise concurrent.futures.TimeoutError

class DummyExecutor:
    def __init__(self, max_workers):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        pass
    
    def shutdown(self, wait):
            pass
    def submit(self, fn, *args, **kwargs):
        # ignore fn, always return a dummy future
        return DummyFuture()

@pytest.fixture(autouse=True)
def mock_common(mocker):
    patches = {
        "wait": mocker.patch("viewport.WebDriverWait"),
        "api_status": mocker.patch("viewport.api_status"),
        "log_error": mocker.patch("viewport.log_error"),
        "logging": mocker.patch("viewport.logging"),
    }
    return patches
  
# ----------------------------------------------------------------------------- 
# Tests for get_cpu_color and get_mem_color
# ----------------------------------------------------------------------------- 
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

# ----------------------------------------------------------------------------- 
# Test get_browser_version
# ----------------------------------------------------------------------------- 
def test_get_browser_version(monkeypatch):
    # stub subprocess.check_output to return a fake version string
    fake_output = b"Google-Chrome 100.0.4896.127\n"
    monkeypatch.setattr(viewport.subprocess, "check_output", lambda cmd, stderr: fake_output)

    version = viewport.get_browser_version("chrome")
    assert version == "100.0.4896.127"

# ----------------------------------------------------------------------------- 
# Test get_next_restart
# ----------------------------------------------------------------------------- 
@patch("viewport.RESTART_TIMES", [dt_time(3, 0), dt_time(15, 0)])
def test_get_next_restart_future_today():
    now = datetime(2025, 5, 10, 2, 0)  # Before 03:00
    expected = datetime(2025, 5, 10, 3, 0)
    assert viewport.get_next_restart(now) == expected

@patch("viewport.RESTART_TIMES", [dt_time(3, 0), dt_time(15, 0)])
def test_get_next_restart_later_today():
    now = datetime(2025, 5, 10, 4, 0)  # After 03:00 but before 15:00
    expected = datetime(2025, 5, 10, 15, 0)
    assert viewport.get_next_restart(now) == expected

@patch("viewport.RESTART_TIMES", [dt_time(3, 0), dt_time(15, 0)])
def test_get_next_restart_tomorrow():
    now = datetime(2025, 5, 10, 16, 0)  # After all times
    expected = datetime(2025, 5, 11, 3, 0)
    assert viewport.get_next_restart(now) == expected
   
# ----------------------------------------------------------------------------- 
# Test: get_next_interval
# ----------------------------------------------------------------------------- 
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
def test_get_next_interval(interval_seconds, now, expected):
    result = viewport.get_next_interval(interval_seconds, now=now)
    assert datetime.fromtimestamp(result) == expected

# ----------------------------------------------------------------------------- 
# tests for get_driver_path
# ----------------------------------------------------------------------------- 
def test_get_driver_path_chrome_success(monkeypatch):
    # .install() returns immediately
    monkeypatch.setattr(viewport, "ChromeDriverManager", lambda chrome_type: DummyMgr())
    path = viewport.get_driver_path("chrome", timeout=1)
    assert path == "/fake/driver/path"

def test_get_driver_path_chromium_success(monkeypatch):
    # Same for the "chromium" alias
    monkeypatch.setattr(viewport, "ChromeDriverManager", lambda chrome_type: DummyMgr())
    path = viewport.get_driver_path("chromium", timeout=1)
    assert path == "/fake/driver/path"

def test_get_driver_path_firefox_success(monkeypatch):
    # Firefox path
    monkeypatch.setattr(viewport, "GeckoDriverManager", lambda: DummyMgr())
    path = viewport.get_driver_path("firefox", timeout=1)
    assert path == "/fake/driver/path"

def test_get_driver_path_timeout_calls(monkeypatch):
    # Patch ChromeDriverManager to return DummyMgr, and patch ThreadPoolExecutor
    monkeypatch.setattr(viewport, "ChromeDriverManager", lambda *args, **kwargs: DummyMgr())
    monkeypatch.setattr(concurrent.futures, "ThreadPoolExecutor", DummyExecutor)

    with pytest.raises(viewport.DriverDownloadStuckError) as exc:
        viewport.get_driver_path("chrome", timeout=0.01)
    # the exception message should include our timeout note
    assert "Chrome driver download stuck" in str(exc.value)

    # under mock_common, these are mocks, so assert they were called
    viewport.log_error.assert_called_once_with(
        "Chrome driver download stuck (> 0.01s)"
    )
    viewport.api_status.assert_called_once_with(
        "Driver download stuck; restart computer if it persists"
    )

def test_get_driver_path_unsupported_browser():
    with pytest.raises(ValueError) as exc:
        viewport.get_driver_path("safari")
    assert "Unsupported browser" in str(exc.value)