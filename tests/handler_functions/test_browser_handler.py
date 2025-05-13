import pytest
from unittest.mock import MagicMock, patch
import viewport

# ----------------------------------------------------------------------------- 
# Test for browser_handler 
# ----------------------------------------------------------------------------- 
@pytest.mark.parametrize(
    "browser, side_effects, expected_driver_get_calls, expected_kill_calls, expect_restart",
    [
        # Chrome success & retry-then-success
        ("chrome",   [MagicMock()],                    1, 1, False),
        ("chrome",   [Exception("boom"), MagicMock()], 1, 1, False),
        # Chrome permanent-failure → 2 kills, restart
        ("chrome",   [Exception("fail")] * 3,          0, 2, True),

        # Chromium success & retry-then-success
        ("chromium",[MagicMock()],                     1, 1, False),
        ("chromium",[Exception("boom"), MagicMock()],  1, 1, False),
        # Chromium permanent-failure → 2 kills, restart
        ("chromium",[Exception("fail")] * 3,           0, 2, True),

        # Firefox success & retry-then-success
        ("firefox", [MagicMock()],                     1, 1, False),
        ("firefox", [Exception("boom"), MagicMock()],  1, 1, False),
        # Firefox permanent-failure → 2 kills, restart
        ("firefox", [Exception("fail")] * 3,           0, 2, True),
    ],
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
        mock_chrome.side_effect = effects
        mock_options.return_value = MagicMock()
    elif browser == "firefox":
        mock_firefox.side_effect = effects
        mock_ff_opts.return_value     = MagicMock()
        mock_ff_profile.return_value  = MagicMock()
        mock_gecko_mgr.return_value.install.return_value = "/fake/gecko"
        mock_ff_service.return_value = MagicMock()

    # Act
    result = viewport.browser_handler(url)

    # Assert kill calls
    assert mock_process_handler.call_count == expected_kill_calls
    mock_process_handler.assert_any_call(browser, action="kill")

    # Assert constructor calls
    if browser in ("chrome", "chromium"):
        assert mock_chrome.call_count == len(side_effects)
    elif browser == "firefox":
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