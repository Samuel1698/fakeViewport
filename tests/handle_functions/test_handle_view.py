import pytest
import viewport
import time
import math
from itertools import cycle
from selenium.common.exceptions import TimeoutException, WebDriverException, InvalidSessionIdException, NoSuchElementException
from urllib3.exceptions import NewConnectionError
from unittest.mock import MagicMock, patch, ANY
from datetime import datetime, timedelta
# ----------------------------------------------------------------------------- 
# Helper functions
# ----------------------------------------------------------------------------- 
class BreakLoop(BaseException):
    # Custom exception used to break out of the infinite loop in handle_view.
    pass
def make_driver(window_size, screen_size, offline_status=None):
    # Returns a fake driver whose get_window_size and execute_script
    # calls return the given window_size and screen_size values.
    driver = MagicMock()
    driver.get_window_size.return_value = window_size

    def exec_script(script):
        # offline_status check
        if "Console Offline" in script or "Protect Offline" in script:
            return offline_status
        # screen.width / screen.height
        if "return screen.width" in script:
            return screen_size["width"]

    driver.execute_script.side_effect = exec_script
    return driver
# ----------------------------------------------------------------------------- 
# Tests for handle_view function
# ----------------------------------------------------------------------------- 
@patch("viewport.restart_handler", side_effect=SystemExit)
@patch("viewport.api_status")
@patch("viewport.log_error")
@patch("viewport.handle_page", return_value=False)
def test_handle_view_initial_load_failure(
    mock_hp, mock_log_error, mock_api_status, mock_restart
):
    driver = MagicMock()
    with pytest.raises(SystemExit):
        viewport.handle_view(driver, "http://example.com")

    expected_log_error = "Error loading the live view. Restarting the program."
    args, _ = mock_log_error.call_args
    assert args[0] == expected_log_error
    
    mock_api_status.assert_called_with("Error Loading Live View. Restarting...")
    mock_restart.assert_called_once_with(driver)
# ----------------------------------------------------------------------------- 
# Healthy‐path iteration
@patch("viewport.time.sleep", side_effect=BreakLoop)
@patch("viewport.get_next_interval", return_value=time.time())
@patch("viewport.check_unable_to_stream", return_value=False)
@patch("viewport.api_status")
@patch("viewport.handle_elements")
@patch("viewport.handle_loading_issue")
@patch("viewport.handle_fullscreen_button", return_value=True)
@patch("viewport.WebDriverWait")
@patch("viewport.check_driver", return_value=True)
@patch("viewport.handle_page", return_value=True)
@patch("viewport.logging.info")
def test_handle_view_healthy_iteration(
    mock_log_info,
    mock_handle_page,
    mock_check_driver,
    mock_wdw,
    mock_fs_btn,
    mock_loading,
    mock_elements,
    mock_api_status,
    mock_unable,
    mock_next_interval,
    mock_sleep,
):
    drv = MagicMock()
    url = "http://example.com"

    # offline_status test → None
    # then two script calls for screen.width & height
    drv.execute_script.side_effect = [None, 1920, 1080]
    drv.get_window_size.return_value = {"width": 1920, "height": 1080}

    # WebDriverWait.until(...) succeeds
    fake_wdw = MagicMock()
    fake_wdw.until.return_value = True
    mock_wdw.return_value = fake_wdw

    with pytest.raises(BreakLoop):
        viewport.handle_view(drv, url)

    # initial handle_page log
    mock_handle_page.assert_called_once_with(drv)
    mock_log_info.assert_any_call(f"Checking health of page every {viewport.SLEEP_TIME} seconds...")

    # in‐loop sanity checks
    mock_check_driver.assert_called_once_with(drv)
    mock_loading.assert_called_once_with(drv)
    mock_elements.assert_called_once_with(drv)
    mock_api_status.assert_called_with("Feed Healthy")
# ----------------------------------------------------------------------------- 
# Interval Logging Test
@pytest.mark.parametrize("sleep_time, log_interval, now_minute, now_second, expected_minute", [
    # at hh:16:45, 1-min interval  → next boundary at :17
    (60,   1,  16, 45, 17),
    # at hh:36:33, 2-min interval  → next boundary at :38
    (60,   2,  36, 33, 38),
    # at hh:38:00, 2-min interval  → next boundary at :40
    (60,   2,  38, 00, 40),
    # at hh:36:00, 10-min interval → next boundary at :40
    (60,  10,  36,  0, 40),
    # at hh:36:20, 1-min interval  → next boundary at :37
    (120,  1,  36, 20, 37),
    # at hh:36:00, 10-min interval → next boundary at :40
    (120, 10,  36,  0, 40),
    # at hh:16:45, 30-min interval → next boundary at :30
    (300, 30,  16, 45, 30),
    # at hh:36:40, 30-min interval → next boundary at :00
    (300, 30,  36, 40,  0),
    # at hh:16:45, 60-min interval → next boundary at :00 of next hour
    (300, 60,  16, 45,  0),
    # at hh:59:45, 60-min interval → next boundary at :00 of next hour
    (300, 60,  59, 45,  0),
    # at hh:46:45, 5-min  interval but sleep is 5m → effective interval=5m → boundary at :50
    (300,  5,  46, 45, 50),
    # at hh:46:45, 3-min  interval but sleep is 5m → effective interval=5m → boundary at :50
    (300,  3,  46, 45, 50),
])
@patch("viewport.handle_page", return_value=True)
@patch("viewport.check_driver", return_value=True)
@patch("viewport.WebDriverWait")
@patch("viewport.handle_fullscreen_button", return_value=True)
@patch("viewport.handle_loading_issue")
@patch("viewport.handle_elements")
@patch("viewport.check_unable_to_stream", return_value=False)
@patch("viewport.api_status")
@patch("viewport.logging.info")
def test_handle_view_video_feeds_healthy_logging(
    mock_log_info,
    mock_api_status,
    mock_unable,
    mock_elements,
    mock_loading,
    mock_fs_btn,
    mock_wdw,
    mock_check_driver,
    mock_handle_page,
    sleep_time,
    log_interval,
    now_minute,
    now_second,
    expected_minute,
    monkeypatch,
):
    from itertools import cycle
    from datetime import datetime

    class BreakLoop(BaseException):
        pass

    # fake current time so we know exactly where the hour is
    fake_now = datetime(2025, 4, 27, 5, now_minute, now_second)
    monkeypatch.setattr(viewport, "datetime", MagicMock(now=MagicMock(return_value=fake_now)))

    # compute how many sleeps until we hit the boundary, then stop
    # first, figure out effective interval (can't log more often than sleep_time)
    effective_interval_secs = max(log_interval * 60, sleep_time)
    secs_since_hour = now_minute * 60 + now_second
    secs_to_boundary = (effective_interval_secs - (secs_since_hour % effective_interval_secs)) % effective_interval_secs
    # if we're close to a boundary, schedule one full interval out
    if secs_to_boundary < 30:
        secs_to_boundary = effective_interval_secs

    boundary_loops = math.ceil(secs_to_boundary / sleep_time)

    sleep_calls = []
    def fake_sleep(_):
        sleep_calls.append(1)
        # once we've done boundary_loops sleeps, break
        if len(sleep_calls) > boundary_loops:
            raise BreakLoop
    monkeypatch.setattr(viewport.time, "sleep", fake_sleep)

    # stub out driver
    driver = MagicMock()
    driver.execute_script.side_effect = cycle([None, 1920, 1080])
    driver.get_window_size.return_value = {"width": 1920, "height": 1080}
    fake_wait = MagicMock(); fake_wait.until.return_value = True
    mock_wdw.return_value = fake_wait

    # set module constants
    viewport.SLEEP_TIME = sleep_time
    viewport.LOG_INTERVAL = log_interval

    # run & break out
    with pytest.raises(BreakLoop):
        viewport.handle_view(driver, "http://example.com")

    # make sure the one-and-only “Video feeds healthy.” happened at the final log
    calls = [c.args[0] for c in mock_log_info.call_args_list]
    healthy_calls = [i for i, msg in enumerate(calls) if "Video feeds healthy." in msg]

    assert healthy_calls, "Expected at least one 'Video feeds healthy.' log"
    assert healthy_calls[-1] == len(calls) - 1, (
        f"Expected final log at minute {expected_minute}, "
        f"but computed boundary at {datetime(2025,4,27,5, now_minute, now_second) + timedelta(seconds=secs_to_boundary)}"
    )

# ----------------------------------------------------------------------------- 
# Decoding Error
@patch("viewport.logging.warning")
@patch("viewport.api_status")
@patch("viewport.time.sleep", side_effect=BreakLoop)                       # break out after first sleep
@patch("viewport.get_next_interval", return_value=time.time())
@patch("viewport.check_unable_to_stream", return_value=True)               # simulate decoding error
@patch("viewport.handle_elements")
@patch("viewport.handle_loading_issue")
@patch("viewport.handle_fullscreen_button", return_value=True)
@patch("viewport.WebDriverWait")
@patch("viewport.check_driver", return_value=True)
@patch("viewport.handle_page", return_value=True)
def test_handle_view_decoding_error_branch(
    mock_handle_page,
    mock_check_driver,
    mock_wdw,
    mock_fs_btn,
    mock_loading,
    mock_elements,
    mock_check_unable,
    mock_next_interval,
    mock_sleep,
    mock_api_status,
    mock_warning,
):
    driver = MagicMock()
    url = "http://example.com"

    # first two execute_script() calls: offline check → None, then width/height
    driver.execute_script.side_effect = [None, 1920, 1080]
    driver.get_window_size.return_value = {"width": 1920, "height": 1080}

    # stub out presence checks so we get past the wrapper logic
    fake_wdw = MagicMock()
    fake_wdw.until.return_value = True
    mock_wdw.return_value = fake_wdw

    with pytest.raises(BreakLoop):
        viewport.handle_view(driver, url)

    # on decoding error we should warn and set API status
    mock_warning.assert_called_once_with(
        "Live view contains cameras that the browser cannot decode."
    )
    mock_api_status.assert_called_with("Decoding Error in some cameras")
# ----------------------------------------------------------------------------- 
# Offline‐status branch
@patch("viewport.time.sleep", return_value=None)
@patch("viewport.handle_retry", side_effect=BreakLoop)
@patch("viewport.api_status")
@patch("viewport.logging.warning")
@patch("viewport.WebDriverWait")
@patch("viewport.check_driver", return_value=True)
@patch("viewport.handle_page", return_value=True)
def test_handle_view_offline_branch(
    mock_handle_page,
    mock_check_driver,
    mock_wdw,
    mock_log_warn,
    mock_api_status,
    mock_handle_retry,
    mock_sleep,
):
    drv = MagicMock()
    url = "u"

    # first execute_script() → truthy offline element
    drv.execute_script.return_value = object()

    # stub out the later wait so we never progress past offline branch
    fake_wdw = MagicMock()
    fake_wdw.until.return_value = True
    mock_wdw.return_value = fake_wdw

    with pytest.raises(BreakLoop):
        viewport.handle_view(drv, url)

    mock_log_warn.assert_any_call("Detected offline status: Console or Protect Offline.")
    mock_api_status.assert_called_with("Console or Protect Offline")
    mock_handle_retry.assert_called_once_with(drv, url, 1, viewport.MAX_RETRIES)

# ----------------------------------------------------------------------------- 
# All Exceptions branch
# ----------------------------------------------------------------------------- 
@pytest.mark.parametrize(
    "trigger, expected_log_args, expected_api, recovery_fn, recovery_args",
    [
        # 1) InvalidSessionIdException ⇒ restart_handler(driver)
        (
            lambda drv, wdw: setattr(
                viewport, "check_driver",
                MagicMock(side_effect=InvalidSessionIdException())
            ),
            # now expects the exception as second arg
            (f"{viewport.BROWSER} session is invalid. Restarting the program.", ANY),
            "Restarting Program",
            "restart_handler",
            lambda drv, url, mw: (drv,),
        ),
        # 2) TimeoutException ⇒ handle_retry(driver, url, 1, max_retries)
        (
            lambda drv, wdw: setattr(
                wdw, "until",
                MagicMock(side_effect=TimeoutException())
            ),
            ("Video feeds not found or page timed out.", ANY),
            "Video Feeds Not Found",
            "handle_retry",
            lambda drv, url, mw: (drv, url, 1, mw),
        ),
        # 3) NoSuchElementException ⇒ same as TimeoutException
        (
            lambda drv, wdw: setattr(
                wdw, "until",
                MagicMock(side_effect=NoSuchElementException())
            ),
            ("Video feeds not found or page timed out.", ANY),
            "Video Feeds Not Found",
            "handle_retry",
            lambda drv, url, mw: (drv, url, 1, mw),
        ),
        # 4) NewConnectionError ⇒ handle_retry(driver, url, 1, max_retries)
        (
            lambda drv, wdw: drv.execute_script.__setattr__(
                "side_effect", NewConnectionError(None, "fail")
            ),
            ("Connection error occurred. Retrying...", ANY),
            "Connection Error",
            "handle_retry",
            lambda drv, url, mw: (drv, url, 1, mw),
        ),
        # 5) WebDriverException ⇒ browser_restart_handler(url)
        (
            lambda drv, wdw: setattr(
                wdw, "until",
                MagicMock(side_effect=WebDriverException())
            ),
            (f"Tab Crashed. Restarting {viewport.BROWSER}...", ANY),
            "Tab Crashed",
            "browser_restart_handler",
            lambda drv, url, mw: (url,),
        ),
        # 6) Generic Exception ⇒ handle_retry(driver, url, 1, max_retries)
        (
            lambda drv, wdw: setattr(
                wdw, "until",
                MagicMock(side_effect=Exception("oops"))
            ),
            ("Unexpected error occurred: ", ANY),
            "Unexpected Error",
            "handle_retry",
            lambda drv, url, mw: (drv, url, 1, mw),
        ),
    ],
)
@patch("viewport.time.sleep")                       # we’ll configure side_effect in the test
@patch("viewport.browser_restart_handler", side_effect=Exception)
@patch("viewport.handle_retry")                     # no global exception here
@patch("viewport.restart_handler", side_effect=Exception)
@patch("viewport.api_status")
@patch("viewport.log_error")
@patch("viewport.logging.warning")
@patch("viewport.logging.info")
@patch("viewport.WebDriverWait")
@patch("viewport.check_driver", return_value=True)
@patch("viewport.handle_page", return_value=True)
def test_handle_view_all_error_branches(
    mock_handle_page,
    mock_check_driver,
    mock_wdw,
    mock_log_info,
    mock_log_warn,
    mock_log_error,
    mock_api_status,
    mock_restart,
    mock_retry,
    mock_chrome_restart,
    mock_sleep,
    trigger,
    expected_log_args,
    expected_api,
    recovery_fn,
    recovery_args,
):
    driver = MagicMock()
    url = "http://example.com"

    # normal path into the loop
    driver.execute_script.return_value = None
    fake_wait = MagicMock()
    fake_wait.until.return_value = True
    mock_wdw.return_value = fake_wait

    # inject the exception scenario
    trigger(driver, fake_wait)

    # if the branch under test uses handle_retry, we want the first sleep to pass
    # and the *second* sleep to raise StopIteration and break the loop.
    if recovery_fn == "handle_retry":
        mock_retry.side_effect = None
        mock_sleep.side_effect = [None, StopIteration()]
        with pytest.raises(StopIteration):
            viewport.handle_view(driver, url)
    else:
        # for restart_handler / browser_restart_handler cases, we still rely on
        # their Exceptions to break out immediately
        mock_sleep.return_value = None
        with pytest.raises(Exception):
            viewport.handle_view(driver, url)

    # Expected log error is logged
    args, kwargs = mock_log_error.call_args_list[0]
    assert expected_log_args[0] in args[0]

    mock_api_status.assert_called_with(expected_api)

    # check that the correct recovery function was called
    if recovery_fn == "restart_handler":
        rec = mock_restart
    elif recovery_fn == "handle_retry":
        rec = mock_retry
    else:
        rec = mock_chrome_restart

    rec.assert_called_once_with(*recovery_args(driver, url, viewport.MAX_RETRIES))
    
@pytest.fixture(autouse=True)
def base_setup(monkeypatch):
    # handle_page and check_driver always succeed up to our branch
    monkeypatch.setattr(viewport, "handle_page", lambda d: True)
    monkeypatch.setattr(viewport, "check_driver", lambda d: True)
    # disable retry logic
    monkeypatch.setattr(viewport, "handle_retry", lambda *a, **k: None)
    # stub out everything after our branch so it won't error
    monkeypatch.setattr(viewport, "handle_loading_issue", lambda d: None)
    monkeypatch.setattr(viewport, "handle_elements", lambda d: None)
    monkeypatch.setattr(viewport, "check_unable_to_stream", lambda d: False)
    monkeypatch.setattr(viewport, "api_status", lambda msg: None)

def test_handle_view_fullscreen_mismatch(monkeypatch):
    # Simulate a screen‐size mismatch so that handle_view logs the
    # 'Attempting to make live-view fullscreen.' info and then
    # a warning when handle_fullscreen_button returns False.

    # set up driver: window smaller than actual screen
    driver = make_driver(
        window_size={"width": 800, "height": 600},
        screen_size={"width": 1024, "height": 768}
    )

    # crash branch off
    monkeypatch.setattr(viewport, "check_crash", lambda d: False)
    # fullscreen button fails
    monkeypatch.setattr(viewport, "handle_fullscreen_button", lambda d: False)

    infos = []
    warns = []
    monkeypatch.setattr(viewport.logging, "info", lambda msg: infos.append(msg))
    monkeypatch.setattr(viewport.logging, "warning", lambda msg: warns.append(msg))

    # break out of the infinite loop after first iteration
    monkeypatch.setattr(viewport.time, "sleep", lambda s: (_ for _ in ()).throw(StopIteration))

    with pytest.raises(StopIteration):
        viewport.handle_view(driver, "http://example.com")

    assert any("Attempting to make live-view fullscreen." in i for i in infos), \
        f"Expected an info about fullscreen, got {infos}"
    assert any("Failed to activate fullscreen" in w for w in warns), \
        f"Expected a fullscreen-warning, got {warns}"

def test_handle_view_check_crash(monkeypatch):
    # Force check_crash to return True so that handle_view
    # calls browser_restart_handler, log_error and api_status.

    # driver pretends to already be fullscreen clean (no size mismatch)
    driver = make_driver(
        window_size={"width": 1024, "height": 768},
        screen_size={"width": 1024, "height": 768}
    )

    # crash branch on
    monkeypatch.setattr(viewport, "check_crash", lambda d: True)

    # stub restart to return a new driver
    new_driver = MagicMock()
    monkeypatch.setattr(viewport, "browser_restart_handler", lambda url: new_driver)

    errors = []
    apis = []
    monkeypatch.setattr(viewport, "log_error", lambda msg, e=None, driver=None: errors.append(msg))
    monkeypatch.setattr(viewport, "api_status", lambda msg: apis.append(msg))

    # break out of the infinite loop after first iteration
    monkeypatch.setattr(viewport.time, "sleep", lambda s: (_ for _ in ()).throw(StopIteration))

    with pytest.raises(StopIteration):
        viewport.handle_view(driver, "http://example.com")

    # verify that we logged the crash and updated the API status
    assert errors and errors[0].startswith(f"Tab Crashed. Restarting {viewport.BROWSER}"), \
        f"log_error not called correctly, got: {errors}"
    assert apis and apis[0] == "Tab Crashed", f"api_status not called, got: {apis}"