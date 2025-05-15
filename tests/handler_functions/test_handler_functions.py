import sys
import logging
import pytest
import viewport
import os
from datetime import datetime, time as dt_time
import time 
from webdriver_manager.core.os_manager import ChromeType
from unittest.mock import MagicMock, patch, call
import signal
import subprocess

@pytest.fixture(autouse=True)
def isolate_sst(tmp_path, monkeypatch):
    # redirect every test’s sst_file into tmp_path/
    fake = tmp_path / "sst.txt"
    fake.write_text("2025-01-01 00:00:00.000000")  # or leave empty
    monkeypatch.setattr(viewport, "sst_file", fake)
# ----------------------------------------------------------------------------- 
# Test for Singal Handler
# ----------------------------------------------------------------------------- 
@patch("viewport.logging")
@patch("viewport.api_status")
@patch("viewport.sys.exit")
def test_signal_handler_calls_exit(mock_exit, mock_api_status, mock_logging):
    mock_driver = MagicMock()

    # Call the signal handler manually
    viewport.signal_handler(signum=2, frame=None, driver=mock_driver)

    # Assertions
    mock_driver.quit.assert_called_once()
    mock_logging.info.assert_any_call(f"Gracefully shutting down {viewport.BROWSER}.")
    mock_logging.info.assert_any_call("Gracefully shutting down script instance.")
    mock_api_status.assert_called_once_with("Stopped ")
    mock_exit.assert_called_once_with(0)
# ----------------------------------------------------------------------------- 
# Tests for screenshot handler
# ----------------------------------------------------------------------------- 
@pytest.mark.parametrize("file_ages_days, expected_deleted", [
    ([10, 5, 1], ["screenshot_0.png", "screenshot_1.png"]),  # 10 and 5 days old, delete if cutoff is 2
    ([1, 0.5], []),  # recent files, none deleted
])
def test_screenshot_handler(tmp_path, file_ages_days, expected_deleted, monkeypatch):
    # Arrange
    max_age_days = 2
    now = time.time()

    created_files = []
    for i, age in enumerate(file_ages_days):
        file = tmp_path / f"screenshot_{i}.png"
        file.write_text("dummy")
        os.utime(file, (now - age * 86400, now - age * 86400))
        created_files.append(file)

    mock_info = MagicMock()
    mock_api_status = MagicMock()
    mock_log_error = MagicMock()

    monkeypatch.setattr(logging, "info", mock_info)
    monkeypatch.setattr(viewport, "api_status", mock_api_status)
    monkeypatch.setattr(viewport, "log_error", mock_log_error)

    # Act
    viewport.screenshot_handler(tmp_path, max_age_days)

    # Assert
    deleted_names = [f.name for f in created_files if not f.exists()]
    assert sorted(deleted_names) == sorted(expected_deleted)
    assert mock_info.call_count == len(expected_deleted)
    assert mock_api_status.call_count == len(expected_deleted)
    mock_log_error.assert_not_called() 
def test_screenshot_handler_unlink_raises(tmp_path, monkeypatch):
    import time
    from pathlib import Path

    # Arrange
    file = tmp_path / "screenshot_fail.png"
    file.write_text("dummy")
    os.utime(file, (time.time() - 10 * 86400, time.time() - 10 * 86400))  # definitely old

    mock_info = MagicMock()
    mock_api_status = MagicMock()
    mock_log_error = MagicMock()

    class BadFile:
        def __init__(self, path):
            self._path = path
            self.name = path.name
        def stat(self):
            return type('stat', (), {'st_mtime': time.time() - 10 * 86400})()
        def unlink(self):
            raise OSError("unlink failed")

    monkeypatch.setattr(logging, "info", mock_info)
    monkeypatch.setattr(viewport, "api_status", mock_api_status)
    monkeypatch.setattr(viewport, "log_error", mock_log_error)
    monkeypatch.setattr(Path, "glob", lambda self, pattern: [BadFile(file)] if pattern == "screenshot_*.png" else [])

    # Act
    viewport.screenshot_handler(tmp_path, max_age_days=2)

    # Assert
    mock_info.assert_not_called()
    mock_api_status.assert_not_called()
    mock_log_error.assert_called_once()
    assert "unlink failed" in str(mock_log_error.call_args[0][1])
# ----------------------------------------------------------------------------- 
# Tests for browser_restart_handler
# ----------------------------------------------------------------------------- 
@pytest.mark.parametrize(
    "chrome_exc,    check_exc,     handle_page_ret, "
    "should_sleep,  should_feed_ok, should_return, "
    "should_log_err, should_raise, expected_api_calls",
    [
        # 1) Success, handle_page=True
        (
            None, None, True,
            True, True, True,
            False, False,
            [call(f"Restarting {viewport.BROWSER}"), call("Feed Healthy")],
        ),
        # 2) Success, handle_page=False
        (
            None, None, False,
            False, False, True,
            False, False,
            [call(f"Restarting {viewport.BROWSER}")],
        ),
        # 3) browser_handler throws
        (
            Exception("boom"), None, None,
            False, False, False,
            True, True,
            [call(f"Restarting {viewport.BROWSER}"), call(f"Error Killing {viewport.BROWSER}")],
        ),
        # 4) check_for_title throws
        (
            None, Exception("oops"), None,
            False, False, False,
            True, True,
            [call(f"Restarting {viewport.BROWSER}"), call(f"Error Killing {viewport.BROWSER}")],
        ),
    ]
)
@patch("viewport.time.sleep", return_value=None)
@patch("viewport.logging.info")
@patch("viewport.api_status")
@patch("viewport.log_error")
@patch("viewport.handle_page")
@patch("viewport.check_for_title")
@patch("viewport.browser_handler")
def test_browser_restart_handler(
    mock_browser_handler,
    mock_check_for_title,
    mock_handle_page,
    mock_log_error,
    mock_api_status,
    mock_log_info,
    mock_sleep,
    chrome_exc,
    check_exc,
    handle_page_ret,
    should_sleep,
    should_feed_ok,
    should_return,
    should_log_err,
    should_raise,
    expected_api_calls,
):
    url = "http://example.com"
    fake_driver = MagicMock()

    # wire up browser_handler
    if chrome_exc:
        mock_browser_handler.side_effect = chrome_exc
    else:
        mock_browser_handler.return_value = fake_driver

    # wire up check_for_title
    if check_exc:
        mock_check_for_title.side_effect = check_exc

    # wire up handle_page
    mock_handle_page.return_value = handle_page_ret

    # Act
    if should_raise:
        with pytest.raises(Exception):
            viewport.browser_restart_handler(url)
    else:
        result = viewport.browser_restart_handler(url)

    # Always start by logging & api_status "Restarting BROWSER"
    mock_log_info.assert_any_call(f"Restarting {viewport.BROWSER}...")
    mock_api_status.assert_any_call(f"Restarting {viewport.BROWSER}")

    # Check the full sequence of api_status calls
    assert mock_api_status.call_args_list == expected_api_calls

    # Sleep only when handle_page returned True and no exception
    assert mock_sleep.called == should_sleep

    # "Page successfully reloaded." only when handle_page was True and no exception
    if should_feed_ok:
        mock_log_info.assert_any_call("Page successfully reloaded.")
    else:
        assert not any("Page successfully reloaded." in args[0][0]
                       for args in mock_log_info.call_args_list)

    # Return driver only on full success
    if not should_raise and should_return:
        assert result is fake_driver

    # log_error only on exception paths
    assert mock_log_error.called == should_log_err
# ----------------------------------------------------------------------------- 
# Tests for restart_scheduler
# ----------------------------------------------------------------------------- 
def test_restart_scheduler_triggers_api_and_restart(monkeypatch):
    # Fix "now" at 2025-05-08 12:00:00
    fixed_now = datetime(2025, 5, 8, 12, 0, 0)

    # Create a subclass so we can override now(), but inherit combine()/time() etc.
    class DummyDateTime(datetime):
        @classmethod
        def now(cls):
            return fixed_now

    # Patch in our DummyDateTime and a single RESTART_TIME at 12:00:10
    monkeypatch.setattr(viewport, 'datetime', DummyDateTime)
    monkeypatch.setattr(viewport, 'RESTART_TIMES', [dt_time(12, 0, 10)])

    # Capture the sleep duration
    sleep_calls = []
    monkeypatch.setattr(viewport.time, 'sleep', lambda secs: sleep_calls.append(secs))

    # Capture api_status calls
    api_calls = []
    monkeypatch.setattr(viewport, 'api_status', lambda msg: api_calls.append(msg))

    # Stub restart_handler to record the driver and then raise to break the loop
    restart_calls = []
    def fake_restart(driver):
        restart_calls.append(driver)
        raise StopIteration
    monkeypatch.setattr(viewport, 'restart_handler', fake_restart)

    dummy_driver = object()

    # Act: we expect StopIteration to bubble out after one iteration
    with pytest.raises(StopIteration):
        viewport.restart_scheduler(dummy_driver)

    # Compute what the wait _should_ have been:
    #   next_run = today at 12:00:10 → wait = 10 seconds
    expected_wait = (fixed_now.replace(hour=12, minute=0, second=10) - fixed_now).total_seconds()

    # === Assertions ===
    # We slept exactly the right amount
    assert sleep_calls == [expected_wait]

    # api_status was called once with the scheduled‐restart time
    assert len(api_calls) == 1
    assert api_calls[0] == f"Scheduled restart at {dt_time(12, 0, 10)}"

    # restart_handler was called with our dummy driver
    assert restart_calls == [dummy_driver]
def test_restart_scheduler_no_times(monkeypatch):
    # Arrange: no restart times configured
    monkeypatch.setattr(viewport, 'RESTART_TIMES', [])

    # Any of these being called would mean we didn't return early
    monkeypatch.setattr(viewport, 'api_status',                lambda msg: pytest.fail("api_status should NOT be called"))
    monkeypatch.setattr(viewport, 'restart_handler',           lambda drv: pytest.fail("restart_handler should NOT be called"))
    monkeypatch.setattr(viewport.time,   'sleep',              lambda secs: pytest.fail("time.sleep should NOT be called"))

    # Act & Assert: should return None and not raise
    result = viewport.restart_scheduler(driver="dummy")
    assert result is None
def test_restart_thread_terminates_on_system_exit(monkeypatch):
    # Fix "now" at 2025-05-08 12:00:00
    fixed_now = datetime(2025, 5, 8, 12, 0, 0)
    class DummyDateTime(datetime):
        @classmethod
        def now(cls):
            return fixed_now

    # Patch datetime and give us a single restart 10s in the future
    monkeypatch.setattr(viewport, 'datetime', DummyDateTime)
    monkeypatch.setattr(viewport, 'RESTART_TIMES', [dt_time(12, 0, 10)])

    # Don’t actually sleep
    monkeypatch.setattr(viewport.time, 'sleep', lambda secs: None)

    # Capture api_status so we know that happened
    api_msgs = []
    monkeypatch.setattr(viewport, 'api_status', lambda msg: api_msgs.append(msg))

    # Make restart_handler simulate killing the thread via sys.exit(0)
    def fake_restart(driver):
        fake_restart.called = True
        raise SystemExit(0)
    fake_restart.called = False
    monkeypatch.setattr(viewport, 'restart_handler', fake_restart)

    # Now when we call restart_scheduler, it should raise SystemExit(0)
    with pytest.raises(SystemExit) as exc:
        viewport.restart_scheduler(driver="DUMMY")

    # === Assertions ===
    assert exc.value.code == 0, "Thread should exit with code 0"
    assert fake_restart.called, "restart_handler must have been called"
    # And we also got our api_status before the exit
    assert api_msgs and api_msgs[0].startswith("Scheduled restart"), \
           "api_status should have been invoked before the exit"