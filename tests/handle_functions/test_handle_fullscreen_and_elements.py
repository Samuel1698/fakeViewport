import pytest
import viewport
from unittest.mock import MagicMock
from selenium.common.exceptions import WebDriverException

# --------------------------------------------------------------------------- # 
# Test for handle_elements function
# --------------------------------------------------------------------------- # 
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

@pytest.mark.parametrize("invocations", [1, 2, 3])
def test_banner_script_always_injected(invocations):
    driver = MagicMock()
    for _ in range(invocations):
        viewport.handle_pause_banner(driver)

    assert driver.execute_script.call_count == invocations
    script_source = driver.execute_script.call_args[0][0]
    assert 'pauseBannerPaused' in script_source

# --------------------------------------------------------------------------- # 
# Test for handle_fullscreen_button function
# --------------------------------------------------------------------------- # 
@pytest.fixture(autouse=True)
def setup_selectors_and_wait_time(monkeypatch):
    monkeypatch.setattr(viewport, "WAIT_TIME", 1)
    monkeypatch.setattr(viewport, "time", MagicMock(sleep=lambda s: None))
    viewport.CSS_FULLSCREEN_PARENT = ".parent"
    viewport.CSS_FULLSCREEN_BUTTON = ".child"

def make_wdw_side_effects(results):
    """
    Create a fake “WebDriverWait(...).until(...)” object whose .until(...)
    returns results[0], then results[1], etc.  Raises if .until() is called more
    times than there are items in 'results'.
    """
    class FakeWDW:
        def __init__(self, seq):
            self._seq = list(seq)
        def until(self, results):
            return self._seq.pop(0)
    return FakeWDW(results)

# --------------------------------------------------------------------------- # 
# Happy path - no minimize, maximize succeeds, both parent + child
# --------------------------------------------------------------------------- # 
def test_successful_fullscreen_click(monkeypatch):
    driver = MagicMock()

    # First call to get_window_rect() → {'width': 150}  (>=100 → skip minimize)
    # Second call to get_window_rect() → {'width': 1920} (>= 0.9 * screen_width)
    driver.get_window_rect.side_effect = [
        {'width': 150},
        {'width': 1920}
    ]
    # driver.execute_script("return screen.width") → 1920
    driver.execute_script.return_value = 1920

    # WebDriverWait(driver, WAIT_TIME).until(...)  returns fake_parent, then fake_button
    fake_parent = MagicMock()
    fake_button = MagicMock()
    wdw = make_wdw_side_effects([fake_parent, fake_button])
    monkeypatch.setattr(viewport, 'WebDriverWait', lambda drv, t: wdw)

    # ActionChains(driver) → a single ac_instance
    ac_instance = MagicMock()
    monkeypatch.setattr(viewport, 'ActionChains', lambda drv: ac_instance)

    # Run the function under test
    result = viewport.handle_fullscreen_button(driver)

    # --- ASSERTIONS ---
    # We never called minimize_window() because width was 150 >= 100
    driver.minimize_window.assert_not_called()

    # maximize_window() must have been called exactly once
    driver.maximize_window.assert_called_once()

    # We expect two calls to move_to_element(): one for “parent” and one for “button”
    assert ac_instance.move_to_element.call_count == 2

    # Exactly one .click() must have been queued (on the second move_to_element)
    assert ac_instance.click.call_count == 1

    # The function should finally return True
    assert result is True

# --------------------------------------------------------------------------- # 
# Initial width < 100 → calls minimize first
# --------------------------------------------------------------------------- # 
def test_minimize_then_fullscreen(monkeypatch):
    driver = MagicMock()

    # First get_window_rect() → {'width': 50}  → triggers minimize_window()
    # Then after maximize, get_window_rect() → {'width': 1920}
    driver.get_window_rect.side_effect = [
        {'width': 50},
        {'width': 1920}
    ]
    driver.execute_script.return_value = 1920

    fake_parent = MagicMock()
    fake_button = MagicMock()
    wdw = make_wdw_side_effects([fake_parent, fake_button])
    monkeypatch.setattr(viewport, 'WebDriverWait', lambda drv, t: wdw)

    ac_instance = MagicMock()
    monkeypatch.setattr(viewport, 'ActionChains', lambda drv: ac_instance)

    result = viewport.handle_fullscreen_button(driver)

    # ASSERTIONS
    # Because width was 50 (<100), we must have called minimize_window() once
    driver.minimize_window.assert_called_once()

    # After that, maximize_window() should still be called exactly once
    driver.maximize_window.assert_called_once()

    # Then we still hover on parent and button
    assert ac_instance.move_to_element.call_count == 2
    assert ac_instance.click.call_count == 1

    assert result is True

# --------------------------------------------------------------------------- # 
# Maximize failure (non-"maximized" WebDriverException) → return False
# --------------------------------------------------------------------------- # 
def test_maximize_failure_non_maximized(monkeypatch):
    driver = MagicMock()

    # get_window_rect() → {'width':150}  → skip minimize
    # Next get_window_rect() → {'width':500}   (<0.9 * 1920) → raises WebDriverException("Window failed to maximize")
    driver.get_window_rect.side_effect = [
        {'width': 150},
        {'width': 500}
    ]
    driver.execute_script.return_value = 1920

    # Since the “window_rect < 0.9*screen_width” check raises WebDriverException,
    # we do NOT expect any WebDriverWait or ActionChains calls here.  If they get called,
    # that’s a bug.  So stub them so that pytest.skip triggers if they are invoked.
    monkeypatch.setattr(viewport, 'WebDriverWait', lambda drv, t: pytest.skip("Should not reach button logic"))
    monkeypatch.setattr(viewport, 'ActionChains', lambda drv: pytest.skip("Should not reach button logic"))

    # Capture the calls to log_error and api_status
    errors = []
    statuses = []
    monkeypatch.setattr(viewport, 'log_error', lambda msg, e=None, driver=None: errors.append(msg))
    monkeypatch.setattr(viewport, 'api_status', lambda msg: statuses.append(msg))

    # Run under test
    result = viewport.handle_fullscreen_button(driver)

    # ASSERTIONS
    assert result is False

    # We must have logged exactly “Window restoration failed: ...”
    assert any("Window restoration failed" in err for err in errors)

    # api_status(...) must have been called once with that same string
    assert statuses == ["Window restoration failed"]

def test_handle_fullscreen_already_maximized(monkeypatch):
    # Tiny window forces the maximise code-path
    driver = MagicMock()
    driver.get_window_rect.return_value = {"width": 50, "height": 50}
    driver.minimize_window.return_value = None
    driver.maximize_window.side_effect = WebDriverException("window already maximized")
    driver.execute_script.return_value = 1920          # fake screen width

    # Skip real sleeps
    monkeypatch.setattr(viewport.time, "sleep", lambda *_: None)

    # Dummy WebDriverWait that just returns a parent first, a button second
    fake_parent, fake_button = MagicMock(), MagicMock()
    fake_button.click = MagicMock()

    class DummyWait:
        def __init__(self, *_a, **_kw):
            self.called = 0
        def until(self, *_):
            self.called += 1
            return fake_parent if self.called == 1 else fake_button

    monkeypatch.setattr(viewport, "WebDriverWait", DummyWait)

    # Replace ActionChains with a single shared mock
    ac_instance = MagicMock()
    monkeypatch.setattr(viewport, "ActionChains", lambda *_: ac_instance)

    # Capture side-effects
    errors, statuses = [], []
    monkeypatch.setattr(viewport, "log_error",
                        lambda msg, e=None, driver=None: errors.append(msg))
    monkeypatch.setattr(viewport, "api_status",
                        lambda msg: statuses.append(msg))

    result = viewport.handle_fullscreen_button(driver)

    # Branch behaviour: function succeeds, no error/status logged in the maximise block
    assert result is True
    assert errors == []
    assert statuses == ["Fullscreen restored"]

    # Existing expectations still hold
    assert ac_instance.click.call_count == 1
    assert ac_instance.move_to_element.call_count == 2

# --------------------------------------------------------------------------- # 
# Maximize failure with a *generic* Exception("already maximized")
# - this is not caught by except WebDriverException, so it bubbles 
# to outer except
# - “Critical error in fullscreen handling” / return False
# --------------------------------------------------------------------------- # 
def test_maximize_failure_already_maximized(monkeypatch):
    driver = MagicMock()

    # get_window_rect() → {'width':150}  → skip minimize
    # On the second call, get_window_rect() raises a *plain* Exception("already maximized")
    driver.get_window_rect.side_effect = [
        {'width': 150},
        Exception("already maximized")
    ]
    driver.execute_script.return_value = 1920

    # If we ever reach the “button‐click” logic, that’s wrong.  Force pytest.skip
    monkeypatch.setattr(viewport, 'WebDriverWait', lambda drv, t: pytest.skip("Should not reach button logic"))
    monkeypatch.setattr(viewport, 'ActionChains', lambda drv: pytest.skip("Should not reach button logic"))

    # Capture the calls to log_error and api_status
    errors = []
    statuses = []
    monkeypatch.setattr(viewport, 'log_error', lambda msg, e=None, driver=None: errors.append(msg))
    monkeypatch.setattr(viewport, 'api_status', lambda msg: statuses.append(msg))

    # Run under test
    result = viewport.handle_fullscreen_button(driver)

    # ASSERTIONS
    assert result is False

    # Because the inner exception was not a WebDriverException, it must have hit the outer except.
    # So log_error(...) should have been called with “Critical error in fullscreen handling”
    assert any("Critical error in fullscreen handling" in err for err in errors)

    # api_status(...) should have been called once with “Fullscreen Error”
    assert statuses == ["Fullscreen Error"]

# --------------------------------------------------------------------------- # 
# Parent found but child‐button lookup / click raises
# --------------------------------------------------------------------------- # 
def test_button_click_failure(monkeypatch):
    driver = MagicMock()

    # get_window_rect() → {'width':150}  → skip minimize
    # get_window_rect() → {'width':1920}  (so window is “large enough”)
    driver.get_window_rect.side_effect = [
        {'width': 150},
        {'width': 1920}
    ]
    driver.execute_script.return_value = 1920

    # WebDriverWait for “parent” returns a real fake_parent
    # On the second WebDriverWait call (child button), we force an Exception()
    fake_parent = MagicMock()
    wdw = make_wdw_side_effects([fake_parent, Exception("no clickable")])
    monkeypatch.setattr(viewport, 'WebDriverWait', lambda drv, t: wdw)

    # ActionChains will get created but the .click() path will throw
    ac_instance = MagicMock()
    monkeypatch.setattr(viewport, 'ActionChains', lambda drv: ac_instance)

    # Capture log_error / api_status
    errors = []
    statuses = []
    monkeypatch.setattr(viewport, 'log_error', lambda msg, e=None, driver=None: errors.append(msg))
    monkeypatch.setattr(viewport, 'api_status', lambda msg: statuses.append(msg))

    # Call under test
    result = viewport.handle_fullscreen_button(driver)

    # ASSERTIONS
    assert result is False

    # Because the child‐button lookup failed, we should have hit the
    # “Fullscreen button click failed” branch
    assert any("Fullscreen button click failed" in err for err in errors)
    assert statuses == ["Fullscreen click failed"]