import os
import sys
import re
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
        mod.config_file = tmp_path / "config.ini"
        mod.env_file    = tmp_path / ".env"
        mod.logs_dir    = tmp_path / "logs"
        mod.api_dir     = tmp_path / "api"
    finally:
        os.chdir(orig_cwd)
        if orig_mod is not None:
            sys.modules["viewport"] = orig_mod
        else:
            sys.modules.pop("viewport", None)
    return mod

BASE_INI = """
[General]
SLEEP_TIME = 300
WAIT_TIME = 30
MAX_RETRIES = 5
RESTART_TIMES = 03:00

[Logging]
LOG_FILE = true
LOG_CONSOLE = true
ERROR_LOGGING = false
LOG_DAYS = 7
LOG_INTERVAL = 60

[Browser]
BROWSER_BINARY = /usr/bin/google-chrome
BROWSER_PROFILE_PATH = /home/test/.config/google-chrome
HEADLESS = false

[API]
USE_API = true
"""

BASE_ENV = """
USERNAME=admin
PASSWORD=secret
URL=http://example.com
SECRET=somesecret
FLASK_RUN_HOST=127.0.0.1
FLASK_RUN_PORT=8080
"""

def write_base(tmp_path, ini_overrides=None, env_overrides=None):
    ini = BASE_INI
    if ini_overrides:
        for key, val in ini_overrides.items():
            ini = re.sub(
                rf"^{key}\s*=.*$",
                f"{key} = {val}",
                ini,
                flags=re.MULTILINE
            )
    (tmp_path / "config.ini").write_text(ini)

    env = BASE_ENV
    if env_overrides:
        lines = env.strip().splitlines()
        updated = {k: v for k, v in (line.split("=",1) for line in lines)}
        updated.update(env_overrides)
        env = "\n".join(f"{k}={v}" for k, v in updated.items()) + "\n"
    (tmp_path / ".env").write_text(env)

# ----------------------------------------------------------------------------- 
# 1) Strict‐mode smoke test
# ----------------------------------------------------------------------------- 
def test_strict_mode_exits_on_any_error(tmp_path):
    mod = reload_in(tmp_path)
    with pytest.raises(SystemExit):
        mod.validate_config(strict=True)


# ----------------------------------------------------------------------------- 
# 2) INI edge‐cases in loose mode
# ----------------------------------------------------------------------------- 
@pytest.mark.parametrize("ini_overrides,substr", [
    ({"WAIT_TIME":"notanint"},              "must be a valid integer"),
    ({"HEADLESS":"notabool"},               "must be a valid boolean"),
    ({"BROWSER_PROFILE_PATH":"/home/your-user/foo"}, "placeholder"),
    ({"RESTART_TIMES":"99:99"},             "Invalid RESTART_TIME"),
])
@patch("viewport.logging.error")
def test_invalid_ini_values_loose(mock_log, tmp_path, ini_overrides, substr):
    write_base(tmp_path, ini_overrides=ini_overrides)
    mod = reload_in(tmp_path)
    ok = mod.validate_config(strict=False, print=True)
    assert ok is False
    assert any(substr in call.args[0] for call in mock_log.call_args_list)


# ----------------------------------------------------------------------------- 
# 3) .env edge‐cases in loose mode
# ----------------------------------------------------------------------------- 
@pytest.mark.parametrize("env_overrides,substr", [
    ({"URL":"//nohost"},         "URL must start with http:// or https://"),
    ({"URL":"ftp://example"},    "must start with http:// or https://"),
    ({"URL":"http:///pathonly"}, "include a host"),
    ({"SECRET":""},              "SECRET is present in .env but empty"),
    ({"WRONG_KEY":"value"},      "Unexpected key in .env"),
    ({"USERNAME":""},            "USERNAME is present in .env but empty"),
    ({"PASSWORD":""},            "PASSWORD is present in .env but empty"),
])
@patch("viewport.logging.error")
def test_invalid_env_values_loose(mock_log, tmp_path, monkeypatch, env_overrides, substr):
    # CLEAR any existing env so load_dotenv overrides
    for key in ("USERNAME","PASSWORD","URL","SECRET","FLASK_RUN_HOST","FLASK_RUN_PORT"):
        monkeypatch.delenv(key, raising=False)

    write_base(tmp_path, env_overrides=env_overrides)
    mod = reload_in(tmp_path)
    ok = mod.validate_config(strict=False, print=True)
    assert ok is False
    assert any(substr in call.args[0] for call in mock_log.call_args_list)

# ----------------------------------------------------------------------------- 
# 4) Host/Port edge‐cases in loose mode
# ----------------------------------------------------------------------------- 
@pytest.mark.parametrize("host,port,substr", [
    ("not_an_ip", "8080",   "FLASK_RUN_HOST must be a valid IP address"),
    ("127.0.0.1", "notnum", "must be an integer"),
    ("::1",       "70000",  "must be 1-65535"),
])
@patch("viewport.logging.error")
def test_bad_host_port_loose(mock_log, tmp_path, monkeypatch, host, port, substr):
    # 1) write a valid base .env so that all other keys pass
    write_base(tmp_path)
    # 2) force the bad host/port into os.environ
    monkeypatch.setenv("FLASK_RUN_HOST", host)
    monkeypatch.setenv("FLASK_RUN_PORT", port)

    mod = reload_in(tmp_path)
    ok = mod.validate_config(strict=False, print=True, api=True)
    assert ok is False
    assert any(substr in call.args[0] for call in mock_log.call_args_list)
