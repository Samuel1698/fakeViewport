import pytest
from urllib3.exceptions import MaxRetryError, NameResolutionError, NewConnectionError
from selenium.common.exceptions import InvalidArgumentException
from unittest.mock import MagicMock, patch, call
import viewport, logging

@pytest.fixture(autouse=True)
def stub_get_driver_path(monkeypatch):
    # no matter which browser or timeout, always return a fake path instantly
    monkeypatch.setattr(viewport, "get_driver_path", lambda *args, **kwargs: "/fake/driver/path")
# ----------------------------------------------------------------------------- 
# Test for browser_handler 
# ----------------------------------------------------------------------------- 
@pytest.mark.parametrize(
    "browser, side_effects, expected_driver_get_calls, expected_kill_calls, expect_restart",
    [
        # Chrome success & retry-then-success
        ("chrome",   [MagicMock()],                                                    1, 1, False),
        ("chrome",   [Exception("boom"), MagicMock()],                                 1, 1, False),
        # Chrome permanent-failure → 2 kills, restart
        ("chrome",   [Exception("fail")] * 4,                                          0, 2, True),
        
        # Chromium success & retry-then-success
        ("chromium",[MagicMock()],                                                     1, 1, False),
        ("chromium",[Exception("boom"), MagicMock()],                                  1, 1, False),
        # Chromium permanent-failure → 2 kills, restart
        ("chromium",[Exception("fail")] * 4,                                           0, 2, True),
        
        # Firefox success & retry-then-success
        ("firefox", [MagicMock()],                                                     1, 1, False),
        ("firefox", [Exception("boom"), MagicMock()],                                  1, 1, False),
        # Firefox permanent-failure → 2 kills, restart
        ("firefox", [Exception("fail")] * 4,                                           0, 2, True),
    ]
)
@patch("viewport.restart_handler")
@patch("viewport.process_handler")
@patch("viewport.validate_config", return_value=True)
@patch("viewport.FirefoxOptions")
@patch("viewport.FirefoxProfile")
@patch("viewport.FirefoxService")
@patch("viewport.GeckoDriverManager")
@patch("viewport.Options")
@patch("viewport.webdriver.Firefox")
@patch("viewport.webdriver.Chrome")
@patch("viewport.time.sleep", return_value=None)
@patch("viewport.api_status")
@patch("viewport.log_error")
@patch("viewport.ChromeDriverManager")
def test_browser_handler(
    mock_chrome_driver_manager,
    mock_log_error,
    mock_api_status,
    mock_sleep,
    mock_chrome,
    mock_firefox,
    mock_options,
    mock_gecko_mgr,
    mock_ff_service,
    mock_ff_profile,
    mock_ff_opts,
    mock_validate_config,
    mock_process_handler,
    mock_restart_handler,
    monkeypatch,               
    browser,
    side_effects,
    expected_driver_get_calls,
    expected_kill_calls,
    expect_restart,
):
    url = "http://example.com"
    monkeypatch.setattr(viewport, 'HEADLESS', "True")
    monkeypatch.setattr(viewport, 'BROWSER', browser)
    monkeypatch.setattr(viewport, "MAX_RETRIES", 3)
    monkeypatch.setattr(viewport, "SLEEP_TIME", 1)
    # Stub out the installer
    mock_installer = MagicMock()
    mock_installer.install.return_value = "/fake/path/to/chromedriver"
    mock_chrome_driver_manager.return_value = mock_installer

    mock_driver = MagicMock()
    effects = [
        e if isinstance(e, Exception) else mock_driver
        for e in side_effects
    ]
    if browser in ("chrome", "chromium"):
        mock_chrome.side_effect       = effects
        mock_options.return_value     = MagicMock()
    else:
        mock_firefox.side_effect      = effects
        mock_ff_opts.return_value     = MagicMock()
        mock_ff_profile.return_value  = MagicMock()
        mock_gecko_mgr.return_value.install.return_value = "/fake/gecko"
        mock_ff_service.return_value  = MagicMock()
        
    # Act
    result = viewport.browser_handler(url)

    # Assert kill calls
    assert mock_process_handler.call_count == expected_kill_calls
    mock_process_handler.assert_any_call(browser, action="kill")

    # Assert constructor calls
    if browser in ("chrome", "chromium"):
        assert mock_chrome.call_count == len(side_effects)
    else:
        assert mock_firefox.call_count == len(side_effects)
        
    # .get/url and return value
    if expected_driver_get_calls:
        mock_driver.get.assert_called_once_with(url)
        assert result is mock_driver
    else:
        assert result is None

    # restart_handler only on permanent failure
    if expect_restart:
        mock_restart_handler.assert_called_once_with(driver=None)
    else:
        mock_restart_handler.assert_not_called()

    # log_error count
    error_count = sum(isinstance(e, Exception) for e in side_effects)
    min_errors = error_count - (1 if expect_restart else 0)
    assert mock_log_error.call_count >= min_errors

@pytest.mark.parametrize("exc, expected_msg", [
    (NewConnectionError("conn refused", None),
    "Connection refused while starting chrome; retrying in 2s"),
    (MaxRetryError("network down", None),
    "Network issue while starting chrome; retrying in 2s"),
    (NameResolutionError("dns fail", None, None),
    "DNS resolution failed while starting chrome; retrying in 2s"),
    (Exception("oops"),
    "Error starting chrome: "),
])
def test_browser_handler_logs_expected_error(monkeypatch, exc, expected_msg):
    # Arrange: minimal environment
    monkeypatch.setattr(viewport, "BROWSER", "chrome")
    monkeypatch.setattr(viewport, "HEADLESS", True)
    monkeypatch.setattr(viewport, "MAX_RETRIES", 1)
    monkeypatch.setattr(viewport, "SLEEP_TIME", 4)  # so int(4/2) == 2
    monkeypatch.setattr(viewport, "process_handler", MagicMock())
    mock_log_error = MagicMock()
    monkeypatch.setattr(viewport, "log_error", mock_log_error)
    monkeypatch.setattr(viewport, "api_status", MagicMock())
    # Stub out options and service
    monkeypatch.setattr(viewport, "Options", lambda: MagicMock())
    monkeypatch.setattr(viewport, "Service", lambda path: MagicMock())
    # Make webdriver.Chrome always raise our exception
    monkeypatch.setattr(
        viewport.webdriver,
        "Chrome",
        lambda service, options: (_ for _ in ()).throw(exc)
    )
    # Prevent real sleeping and long loops
    monkeypatch.setattr(viewport.time, "sleep", lambda s: None)
    # Stop after error handling by intercepting restart_handler
    def raise_stop_iteration(driver):
        raise StopIteration

    monkeypatch.setattr(viewport, "restart_handler", raise_stop_iteration)

    # Act & Assert: StopIteration from our fake restart_handler
    with pytest.raises(StopIteration):
        viewport.browser_handler("http://example.com")

    # Verify log_error was called with the expected message at least once
    messages = [call_args[0][0] for call_args in mock_log_error.call_args_list]
    assert any(expected_msg in msg for msg in messages), f"{expected_msg!r} not found in {messages}"
    
def test_browser_handler_unsupported(monkeypatch):
    import viewport

    # Force an unrecognized browser name
    monkeypatch.setattr(viewport, 'BROWSER', 'safari')
    monkeypatch.setattr(viewport, 'HEADLESS', False)

    # Stub out the usual machinery so the function bails early
    monkeypatch.setattr(viewport, 'validate_config', lambda *a, **k: True)
    monkeypatch.setattr(viewport, 'process_handler', lambda *a, **k: False)
    monkeypatch.setattr(viewport, 'restart_handler', lambda *a, **k: None)
    monkeypatch.setattr(viewport, 'time', MagicMock(sleep=lambda s: None))

    # Capture log_error and api_status calls
    fake_log = MagicMock()
    fake_api = MagicMock()
    monkeypatch.setattr(viewport, 'log_error', fake_log)
    monkeypatch.setattr(viewport, 'api_status', fake_api)

    # Call it
    result = viewport.browser_handler("http://example.com")

    # Assert the unsupported-branch ran
    assert result is None
    fake_log.assert_called_once_with("Unsupported browser: safari")
    fake_api.assert_called_once_with("Unsupported browser: safari")
    
def test_browser_handler_logging_sequence_on_failures(monkeypatch, caplog):
    """
    Verify that browser_handler logs the correct retry sequence,
    kills existing processes before the final attempt, and gives up
    after MAX_RETRIES
    """
    monkeypatch.setattr(viewport, "BROWSER", "chromium")
    monkeypatch.setattr(viewport, "MAX_RETRIES", 3)     # 3 + final attempt
    monkeypatch.setattr(viewport, "SLEEP_TIME", 60)     # drives the last log line
    process_mock = MagicMock()
    monkeypatch.setattr(viewport, "process_handler", process_mock)
    monkeypatch.setattr(viewport, "restart_handler", MagicMock())
    monkeypatch.setattr(viewport.time, "sleep", lambda s: None)
    monkeypatch.setattr(
        viewport.webdriver,
        "Chrome",
        lambda *a, **k: (_ for _ in ()).throw(Exception("Failed to start browser"))
    )
    url = "http://example.com"
    with caplog.at_level(logging.INFO):
        viewport.browser_handler(url)
    log_messages = [rec.message for rec in caplog.records]
    expected_sequence = [
        "Error starting chromium: ",
        "Retrying... (Attempt 1 of 3)",
        "Error starting chromium: ",
        "Retrying... (Attempt 2 of 3)",
        "Error starting chromium: ",
        "Retrying... (Attempt 3 of 3)",
        "Killing existing chromium processes before final attempt...",
        "Error starting chromium: ",
        "Failed to start chromium after maximum retries.",
        "Starting Script again in 30 seconds.",
    ]
    # Ensure every expected fragment appears in the same order
    for expected, actual in zip(expected_sequence, log_messages):
        assert expected in actual, f"Expected '{expected}' in '{actual}'"
    # Quick sanity counts
    assert log_messages.count("Retrying... (Attempt 1 of 3)") == 1
    assert log_messages.count("Retrying... (Attempt 2 of 3)") == 1
    assert log_messages.count("Retrying... (Attempt 3 of 3)") == 1
    assert "Killing existing chromium processes before final attempt..." in log_messages
    assert "Failed to start chromium after maximum retries." in log_messages
    # process_handler: once at the very start (check) + once to kill
    assert process_mock.call_count == 2
    last_call = process_mock.call_args  # (args, kwargs)
    assert last_call[0][0] == "chromium"
    assert last_call.kwargs["action"] == "kill"

@pytest.mark.parametrize("browser", ["chrome", "chromium", "firefox"])
def test_browser_handler_invalid_binary(monkeypatch, browser):
    # Environment
    monkeypatch.setattr(viewport, "BROWSER", browser)
    monkeypatch.setattr(viewport, "HEADLESS", True)
    monkeypatch.setattr(viewport, "MAX_RETRIES", 1)
    monkeypatch.setattr(viewport, "process_handler", lambda *a, **k: None)

    # Stubs for options / services so constructor never touches the real ones
    monkeypatch.setattr(viewport, "Options", lambda *a, **k: MagicMock())
    monkeypatch.setattr(viewport, "Service", lambda *a, **k: MagicMock())
    monkeypatch.setattr(viewport, "FirefoxOptions", lambda *a, **k: MagicMock())
    monkeypatch.setattr(viewport, "FirefoxService", lambda *a, **k: MagicMock())

    # Force the driver constructor to raise InvalidArgumentException
    if browser in ("chrome", "chromium"):
        monkeypatch.setattr(
            viewport.webdriver,
            "Chrome",
            lambda *a, **k: (_ for _ in ()).throw(InvalidArgumentException("bad binary"))
        )
    else:
        monkeypatch.setattr(
            viewport.webdriver,
            "Firefox",
            lambda *a, **k: (_ for _ in ()).throw(InvalidArgumentException("bad binary"))
        )

    # Capture side effects
    log_mock = MagicMock()
    api_mock = MagicMock()
    monkeypatch.setattr(viewport, "log_error", log_mock)
    monkeypatch.setattr(viewport, "api_status", api_mock)

    # No real sleeping
    monkeypatch.setattr(viewport.time, "sleep", lambda s: None)

    with pytest.raises(SystemExit) as excinfo:
        viewport.browser_handler("http://example.com")

    assert excinfo.value.code == 1
    log_mock.assert_called_once_with(
        f"Browser Binary: {viewport.BROWSER_BINARY} is not a browser executable"
    )
    api_mock.assert_called_once_with(f"Error Starting {browser}")
# ----------------------------------------------------------------------------- 
# Tests for driver-stuck behavior in browser_handler
# ----------------------------------------------------------------------------- 
class Breakout(Exception): pass

@pytest.mark.parametrize("browser", ["chrome", "chromium", "firefox"])
def test_driver_download_stuck_logs_and_kills(monkeypatch, browser):
    # Force exactly one retry so loop only runs once
    monkeypatch.setattr(viewport, "MAX_RETRIES", 1)
    monkeypatch.setattr(viewport, "BROWSER", browser)

    # Spy on process_handler and log_error
    spy_kill = MagicMock()
    monkeypatch.setattr(viewport, "process_handler", spy_kill)

    spy_log = MagicMock()
    monkeypatch.setattr(viewport, "log_error", spy_log)

    # Stub out everything else so we never actually launch a driver
    monkeypatch.setattr(viewport, "validate_config", lambda *a, **k: True)
    monkeypatch.setattr(viewport, "api_status", lambda *a, **k: None)
    monkeypatch.setattr(viewport, "time", MagicMock(sleep=lambda s: None))

    # Make get_driver_path always raise DriverDownloadStuckError
    monkeypatch.setattr(
        viewport,
        "get_driver_path",
        lambda *a, **k: (_ for _ in ()).throw(viewport.DriverDownloadStuckError("stuck"))
    )

    # Stub restart_handler to break out immediately
    monkeypatch.setattr(
        viewport,
        "restart_handler",
        lambda *a, **k: (_ for _ in ()).throw(Breakout())
    )

    # Act: run until our Breakout bubbles up
    with pytest.raises(Breakout):
        viewport.browser_handler("http://example.com")

    # Assert: expecting 4 kills with the same signature
    assert spy_kill.call_count == 4
    spy_kill.assert_has_calls([call(browser, action="kill")] * 4)
    # Assert log has the appropriate line
    spy_log.assert_any_call(
        f"Error downloading {browser}WebDrivers; Restart machine if it persists."
    )

@pytest.mark.parametrize("browser", ["chrome", "chromium", "firefox"])
def test_cached_driver_path_is_reused(monkeypatch, tmp_path, browser):
    """
    If viewport.driver_path already contains a valid file, browser_handler
    must skip get_driver_path() and use the cached value.
    """
    # Arrange
    fake_driver = tmp_path / f"{browser}_driver"
    fake_driver.touch(mode=0o755)

    monkeypatch.setattr(viewport, "BROWSER", browser)
    monkeypatch.setattr(viewport, "validate_config", lambda *a, **k: True)
    monkeypatch.setattr(viewport, "api_status",     lambda *a, **k: None)
    monkeypatch.setattr(viewport, "time",           MagicMock(sleep=lambda _: None))
    monkeypatch.setattr(viewport, "restart_handler", MagicMock())

    # Seed the cache
    monkeypatch.setattr(viewport, "driver_path", str(fake_driver), raising=False)

    # Spy on get_driver_path → must not be called
    spy_get_driver = MagicMock()
    monkeypatch.setattr(viewport, "get_driver_path", spy_get_driver)

    # --- NEW for Firefox: stub the options and service factories ---
    monkeypatch.setattr(viewport, "FirefoxOptions",
                        lambda *args, **kwargs: MagicMock())
    monkeypatch.setattr(viewport, "FirefoxService",
                        lambda *args, **kwargs: MagicMock())

    # Stub the Selenium constructors so no real browser starts.
    dummy_driver = MagicMock()
    if browser in ("chrome", "chromium"):
        monkeypatch.setattr(viewport.webdriver, "Chrome",
                            lambda *a, **k: dummy_driver)
    else:
        monkeypatch.setattr(viewport.webdriver, "Firefox",
                            lambda *a, **k: dummy_driver)

    # Act
    result = viewport.browser_handler(url="about:blank")

    # Assert
    assert result is dummy_driver, "Handler did not return the created driver"
    assert spy_get_driver.call_count == 0, "get_driver_path() should NOT be called"
