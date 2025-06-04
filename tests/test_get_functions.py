import concurrent.futures
from pathlib import Path
from unittest.mock import patch
from datetime import datetime, time as dt_time
import pytest
import viewport
# ----------------------------------------------------------------------------- 
# Fixtures and Helpers
# ----------------------------------------------------------------------------- 
class DummyMgr:
    def __init__(self, *_, **__):
        pass
    def install(self):
        # Return a path that does not exist for unit-test purposes
        return "/fake/driver/path"

class DummyFuture:
    def result(self, timeout=None):
        raise concurrent.futures.TimeoutError

class DummyExecutor:
    def __init__(self, max_workers):
        pass
    def shutdown(self, wait):
        pass
    def submit(self, fn, *args, **kwargs):
        # Always “hang” – returns DummyFuture
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

# --------------------------------------------------------------------------- #
# get_driver_path  – happy-path tests
# --------------------------------------------------------------------------- #
def _patch_cleaner(monkeypatch):
    """Disable `stale_drivers_handler()` for tests that only need happy path."""
    monkeypatch.setattr(viewport, "stale_drivers_handler", lambda *_: None)

def test_get_driver_path_chrome_success(monkeypatch):
    _patch_cleaner(monkeypatch)
    monkeypatch.setattr(viewport, "ChromeDriverManager", lambda *_, **__: DummyMgr())
    path = viewport.get_driver_path("chrome", timeout=1)
    assert path == "/fake/driver/path"

def test_get_driver_path_chromium_success(monkeypatch):
    _patch_cleaner(monkeypatch)
    monkeypatch.setattr(viewport, "ChromeDriverManager", lambda *_, **__: DummyMgr())
    path = viewport.get_driver_path("chromium", timeout=1)
    assert path == "/fake/driver/path"

def test_get_driver_path_firefox_success(monkeypatch):
    _patch_cleaner(monkeypatch)
    monkeypatch.setattr(viewport, "GeckoDriverManager", lambda *_, **__: DummyMgr())
    path = viewport.get_driver_path("firefox", timeout=1)
    assert path == "/fake/driver/path"

# --------------------------------------------------------------------------- #
# get_driver_path  – timeout branch
# --------------------------------------------------------------------------- #
def test_get_driver_path_timeout_calls(monkeypatch):
    _patch_cleaner(monkeypatch)
    monkeypatch.setattr(viewport, "ChromeDriverManager", lambda *_, **__: DummyMgr())
    monkeypatch.setattr(concurrent.futures, "ThreadPoolExecutor", DummyExecutor)

    with pytest.raises(viewport.DriverDownloadStuckError) as exc:
        viewport.get_driver_path("chrome", timeout=0.01)

    assert "Chrome driver download stuck" in str(exc.value)
    viewport.log_error.assert_called_once_with(
        "Chrome driver download stuck (> 0.01s)"
    )
    viewport.api_status.assert_called_once_with(
        "Driver download stuck; restart computer if it persists"
    )

def test_get_driver_path_unsupported_browser():
    with pytest.raises(ValueError):
        viewport.get_driver_path("safari")

# --------------------------------------------------------------------------- #
# stale_drivers_handler
# --------------------------------------------------------------------------- #
def stale_drivers_handler(base: Path, versions):
    """
    Create …/linux64/<version>/chromedriver (or geckodriver) files under *base*.
    Returns Path to the newest driver binary (last item in *versions*).
    """
    platform_dir = base / "chromedriver" / "linux64"
    platform_dir.mkdir(parents=True)

    ver_dirs = {}
    for v in versions:
        ver_dir = platform_dir / v
        ver_dir.mkdir()
        (ver_dir / "chromedriver").touch()
        ver_dirs[v] = ver_dir / "chromedriver"

    # pick the max by semantic version, not by insertion order
    newest_version = max(versions, key=viewport.get_tuple)
    return ver_dirs[newest_version]

def test_stale_drivers_handler_keeps_latest(tmp_path):
    # last element becomes the freshly-downloaded build
    versions = ["114.0.7150.60", "137.0.7151.65", "137.0.7151.68", "138.0.7152.10"]
    newest_bin = stale_drivers_handler(tmp_path, versions)

    viewport.stale_drivers_handler(newest_bin)        # keep_latest = 1

    remaining = sorted(
        d.name for d in (newest_bin.parent.parent).iterdir() if d.is_dir()
    )
    # fresh build (138…)  +  newest spare (137.0.7151.68)
    assert remaining == ["137.0.7151.68", "138.0.7152.10"]

def test_stale_drivers_handler_keep_two(tmp_path):
    # put the highest version last so it’s the “fresh install”
    versions = ["v.101.0", "v.102.0", "v.103.0", "v.100.0"]
    newest_bin = stale_drivers_handler(tmp_path, versions)

    viewport.stale_drivers_handler(newest_bin, keep_latest=2)

    remaining = sorted(
        d.name for d in (newest_bin.parent.parent).iterdir() if d.is_dir()
    )
    # fresh build (v.103.0) + two newest siblings (v.102.0, v.101.0)
    assert remaining == ["v.101.0", "v.102.0", "v.103.0"]

def test_stale_drivers_handler_no_siblings(tmp_path):
    # Single version → nothing to delete
    newest_bin = stale_drivers_handler(tmp_path, ["123.0"])
    viewport.stale_drivers_handler(newest_bin)
    platform_dir = newest_bin.parent.parent
    assert any(platform_dir.iterdir()), "Directory should still exist"

def test_stale_drivers_handler_rmtree_error(tmp_path, monkeypatch):
    """stale_drivers_handler should log a warning if rmtree raises."""
    versions   = ["v.100.0", "v.101.0", "v.102.0"]
    newest_bin = stale_drivers_handler(tmp_path, versions)

    # force shutil.rmtree to fail
    def boom(path, ignore_errors=False):
        raise OSError("simulated permission error")

    # Patch *viewport*'s reference, not the global shutil
    monkeypatch.setattr(viewport.shutil, "rmtree", boom)

    # Capture warnings that should be emitted for the failing stale dir
    warnings = []
    monkeypatch.setattr(
        viewport.logging, "warning",
        lambda msg, *args: warnings.append(msg % args)
    )

    viewport.stale_drivers_handler(newest_bin, keep_latest=1)

    # should have logged at least one “Could not delete …” warning
    assert any("Could not delete" in w for w in warnings)
    # the newest build (v.102.0) must still be present
    remaining = {d.name for d in (newest_bin.parent.parent).iterdir()}
    assert "v.102.0" in remaining
