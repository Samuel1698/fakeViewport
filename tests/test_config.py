import sys
import os
import importlib
import pytest
from pathlib import Path
from unittest.mock import patch

def reload_in(tmp_path):
    orig_cwd = os.getcwd()
    orig_mod = sys.modules.pop("viewport", None)
    try:
        os.chdir(tmp_path)
        mod = importlib.import_module("viewport")
        # Override file paths for testing
        mod.config_file = tmp_path / "config.ini"
        mod.env_file = tmp_path / ".env"
        mod.logs_dir = tmp_path / "logs"
        mod.api_dir = tmp_path / "api"
    finally:
        os.chdir(orig_cwd)
        if orig_mod is not None:
            sys.modules["viewport"] = orig_mod
        else:
            sys.modules.pop("viewport", None)
    return mod
    orig_cwd = os.getcwd()
    orig_mod = sys.modules.pop("viewport", None)
    try:
        os.chdir(tmp_path)
        mod = importlib.import_module("viewport")
    finally:
        os.chdir(orig_cwd)
        if orig_mod is not None:
            sys.modules["viewport"] = orig_mod
        else:
            sys.modules.pop("viewport", None)
    return mod

BASE_INI = """
[General]
SLEEP_TIME = {sleep}
WAIT_TIME = {wait}
MAX_RETRIES = {retries}
RESTART_TIMES = {restart_times}

[Logging]
LOG_FILE = true
LOG_CONSOLE = false
ERROR_LOGGING = false
LOG_DAYS = {log_days}
LOG_INTERVAL = {log_interval}

[Browser]
BROWSER_BINARY = {binary}
BROWSER_PROFILE_PATH = {profile}

[API]
USE_API = false
"""

BASE_ENV = """
USERNAME={username}
PASSWORD={password}
URL={url}
"""

EXAMPLE_URL = "http://192.168.100.100/protect/dashboard/multiviewurl"

def write_config(tmp_path, **overrides):
    ini_text = BASE_INI.format(
        sleep=overrides.get("sleep", 300),
        wait=overrides.get("wait", 30),
        retries=overrides.get("retries", 5),
        restart_times=overrides.get("restart_times", "03:00"),
        log_days=overrides.get("log_days", 7),
        log_interval=overrides.get("log_interval", 60),
        binary=overrides.get("binary", "/usr/bin/google-chrome"),
        profile=overrides.get("profile", "/home/test/.config/google-chrome")
    )
    (tmp_path / "config.ini").write_text(ini_text)

    env_text = BASE_ENV.format(
        username=overrides.get("username", "admin"),
        password=overrides.get("password", "1234"),
        url=overrides.get("url", "http://192.168.1.10")
    )
    (tmp_path / ".env").write_text(env_text)

# --- Tests ---

def test_valid_config(tmp_path):
    write_config(tmp_path)
    mod = reload_in(tmp_path)
    assert mod.validate_config(strict=False, print=True, config_file=tmp_path / 'config.ini', env_file=tmp_path / '.env', logs_dir=tmp_path / 'logs', api_dir=tmp_path / 'api') is True
    assert mod.SLEEP_TIME == 300
    assert mod.WAIT_TIME == 30
    assert mod.MAX_RETRIES == 5

@pytest.mark.parametrize("sleep", [30, 59])
@patch("viewport.logging.error")
def test_invalid_sleep_time(mock_log_error, tmp_path, sleep):
    write_config(tmp_path, sleep=sleep)
    mod = reload_in(tmp_path)
    with pytest.raises(SystemExit):
        mod.validate_config(strict=True, config_file=tmp_path / 'config.ini', env_file=tmp_path / '.env', logs_dir=tmp_path / 'logs', api_dir=tmp_path / 'api')
    result = mod.validate_config(strict=False, print=True, config_file=tmp_path / 'config.ini', env_file=tmp_path / '.env', logs_dir=tmp_path / 'logs', api_dir=tmp_path / 'api')
    assert result is False
    mock_log_error.assert_any_call("SLEEP_TIME must be ≥ 60.")

@pytest.mark.parametrize("wait", [0, 5])
@patch("viewport.logging.error")
def test_invalid_wait_time(mock_log_error, tmp_path, wait):
    write_config(tmp_path, wait=wait)
    mod = reload_in(tmp_path)
    with pytest.raises(SystemExit):
        mod.validate_config(strict=True, config_file=tmp_path / 'config.ini', env_file=tmp_path / '.env', logs_dir=tmp_path / 'logs', api_dir=tmp_path / 'api')
    result = mod.validate_config(strict=False, print=True, config_file=tmp_path / 'config.ini', env_file=tmp_path / '.env', logs_dir=tmp_path / 'logs', api_dir=tmp_path / 'api')
    assert result is False
    mock_log_error.assert_any_call("WAIT_TIME must be > 5.")

@pytest.mark.parametrize("retries", [0, 1, 2])
@patch("viewport.logging.error")
def test_invalid_max_retries(mock_log_error, tmp_path, retries):
    write_config(tmp_path, retries=retries)
    mod = reload_in(tmp_path)
    with pytest.raises(SystemExit):
        mod.validate_config(strict=True, config_file=tmp_path / 'config.ini', env_file=tmp_path / '.env', logs_dir=tmp_path / 'logs', api_dir=tmp_path / 'api')
    result = mod.validate_config(strict=False, print=True, config_file=tmp_path / 'config.ini', env_file=tmp_path / '.env', logs_dir=tmp_path / 'logs', api_dir=tmp_path / 'api')
    assert result is False
    mock_log_error.assert_any_call("MAX_RETRIES must be ≥ 3.")

@pytest.mark.parametrize("log_days", [0])
@patch("viewport.logging.error")
def test_invalid_log_days(mock_log_error, tmp_path, log_days):
    write_config(tmp_path, log_days=log_days)
    mod = reload_in(tmp_path)
    with pytest.raises(SystemExit):
        mod.validate_config(strict=True, config_file=tmp_path / 'config.ini', env_file=tmp_path / '.env', logs_dir=tmp_path / 'logs', api_dir=tmp_path / 'api')
    result = mod.validate_config(strict=False, print=True)
    assert result is False
    mock_log_error.assert_any_call("LOG_DAYS must be ≥ 1.")

@pytest.mark.parametrize("log_interval", [0])
@patch("viewport.logging.error")
def test_invalid_log_interval(mock_log_error, tmp_path, log_interval):
    write_config(tmp_path, log_interval=log_interval)
    mod = reload_in(tmp_path)
    with pytest.raises(SystemExit):
        mod.validate_config(strict=True, config_file=tmp_path / 'config.ini', env_file=tmp_path / '.env', logs_dir=tmp_path / 'logs', api_dir=tmp_path / 'api')
    result = mod.validate_config(strict=False, print=True)
    assert result is False
    mock_log_error.assert_any_call("LOG_INTERVAL must be ≥ 1.")

@patch("viewport.logging.error")
def test_bad_restart_times(mock_log_error, tmp_path):
    write_config(tmp_path, restart_times="badtime")
    mod = reload_in(tmp_path)
    with pytest.raises(SystemExit):
        mod.validate_config(strict=True, config_file=tmp_path / 'config.ini', env_file=tmp_path / '.env', logs_dir=tmp_path / 'logs', api_dir=tmp_path / 'api')
    result = mod.validate_config(strict=False, print=True)
    assert result is False
    mock_log_error.assert_any_call("Invalid RESTART_TIME: 'badtime' (expected HH:MM)")

@patch("viewport.logging.error")
def test_browser_mismatch(mock_log_error, tmp_path):
    write_config(tmp_path, binary="/usr/bin/firefox", profile="/home/test/.config/google-chrome")
    mod = reload_in(tmp_path)
    with pytest.raises(SystemExit):
        mod.validate_config(strict=True, config_file=tmp_path / 'config.ini', env_file=tmp_path / '.env', logs_dir=tmp_path / 'logs', api_dir=tmp_path / 'api')
    result = mod.validate_config(strict=False, print=True)
    assert result is False
    mock_log_error.assert_any_call("Browser Mismatch: BROWSER_BINARY uses 'firefox', but BROWSER_PROFILE_PATH does not.")

@patch("viewport.logging.error")
def test_env_empty_username(mock_log_error, tmp_path):
    write_config(tmp_path, username="")
    mod = reload_in(tmp_path)
    with pytest.raises(SystemExit):
        mod.validate_config(strict=True, config_file=tmp_path / 'config.ini', env_file=tmp_path / '.env', logs_dir=tmp_path / 'logs', api_dir=tmp_path / 'api')
    result = mod.validate_config(strict=False, print=True)
    assert result is False
    mock_log_error.assert_any_call("USERNAME is present in .env but empty.")

@patch("viewport.logging.error")
def test_env_example_url(mock_log_error, tmp_path):
    write_config(tmp_path, url=EXAMPLE_URL)
    mod = reload_in(tmp_path)
    with pytest.raises(SystemExit):
        mod.validate_config(strict=True, config_file=tmp_path / 'config.ini', env_file=tmp_path / '.env', logs_dir=tmp_path / 'logs', api_dir=tmp_path / 'api')
    result = mod.validate_config(strict=False, print=True)
    assert result is False
    mock_log_error.assert_any_call("URL is still set to the example value. Please update it.")

@patch("viewport.logging.error")
def test_env_unexpected_key(mock_log_error, tmp_path):
    write_config(tmp_path)
    (tmp_path / ".env").write_text(BASE_ENV.format(username="admin", password="1234", url="http://192.168.1.10") + "\nWRONG_KEY=val")
    mod = reload_in(tmp_path)
    with pytest.raises(SystemExit):
        mod.validate_config(strict=True, config_file=tmp_path / 'config.ini', env_file=tmp_path / '.env', logs_dir=tmp_path / 'logs', api_dir=tmp_path / 'api')
    result = mod.validate_config(strict=False, print=True)
    assert result is False
    assert any("Unexpected key in .env: 'WRONG_KEY'" in str(call) for call in mock_log_error.call_args_list)

@patch("viewport.logging.error")
def test_missing_config_ini(mock_log_error, tmp_path):
    (tmp_path / ".env").write_text(BASE_ENV.format(username="admin", password="1234", url="http://192.168.1.10"))
    mod = reload_in(tmp_path)
    with pytest.raises(SystemExit):
        mod.validate_config(strict=True, config_file=tmp_path / 'config.ini', env_file=tmp_path / '.env', logs_dir=tmp_path / 'logs', api_dir=tmp_path / 'api')
    result = mod.validate_config(strict=False, print=True)
    assert result is False
    mock_log_error.assert_any_call("Missing config.ini file.")

@patch("viewport.logging.error")
def test_missing_dotenv(mock_log_error, tmp_path):
    write_config(tmp_path)
    os.remove(tmp_path / ".env")
    mod = reload_in(tmp_path)
    with pytest.raises(SystemExit):
        mod.validate_config(strict=True, config_file=tmp_path / 'config.ini', env_file=tmp_path / '.env', logs_dir=tmp_path / 'logs', api_dir=tmp_path / 'api')
    result = mod.validate_config(strict=False, print=True)
    assert result is False
    mock_log_error.assert_any_call("Missing .env file.")
