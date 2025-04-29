import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))
import logging
import logging.handlers
# stub out the rotating‐file handler before viewport.py ever sees it
logging.handlers.TimedRotatingFileHandler = lambda *args, **kwargs: logging.NullHandler()
import os
import importlib
import pytest
from pathlib import Path
def reload_in(tmp_path):
    # 1) Save state
    orig_cwd = os.getcwd()
    orig_mod = sys.modules.get("viewport")

    # 2) Remove any existing viewport
    sys.modules.pop("viewport", None)

    try:
        # 3) Switch into test folder and import fresh
        os.chdir(tmp_path)
        mod = importlib.import_module("viewport")
    finally:
        # 4a) Go back where you were
        os.chdir(orig_cwd)
        # 4b) Restore the real viewport module
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

[Logging]
LOG_FILE = true
LOG_CONSOLE = false
ERROR_LOGGING = false
LOG_DAYS = {log_days}
LOG_INTERVAL = {log_interval}

[API]
USE_API = false
API_FILE_PATH = {api_path}
"""

ENV_CONTENT = """
USERNAME=user
PASSWORD=pass
URL={url}
"""
def write_config(tmp_path, **kwargs):
    ini = BASE_INI.format(
        sleep=kwargs.get("sleep", 300),
        wait=kwargs.get("wait", 30),
        retries=kwargs.get("retries", 5),
        log_days=kwargs.get("log_days", 7),
        log_interval=kwargs.get("log_interval", 60),
        api_path=str(tmp_path / "api")
    )
    (tmp_path / "config.ini").write_text(ini)

def test_valid_config(tmp_path):
    write_config(tmp_path)
    # should import without errors
    mod = reload_in(tmp_path)
    # config constants should match
    assert mod.SLEEP_TIME == 300
    assert mod.WAIT_TIME == 30
    assert mod.MAX_RETRIES == 5
    # api directory auto-created
    assert (tmp_path / "api").exists()

@pytest.mark.parametrize("sleep", [30, 59])
def test_invalid_sleep_time(tmp_path, sleep):
    write_config(tmp_path, sleep=sleep)
    with pytest.raises(SystemExit):
        reload_in(tmp_path)

@pytest.mark.parametrize("wait", [0, 5])
def test_invalid_wait_time(tmp_path, wait):
    write_config(tmp_path, wait=wait)
    with pytest.raises(SystemExit):
        reload_in(tmp_path)

@pytest.mark.parametrize("retries", [0, 1, 2])
def test_invalid_max_retries(tmp_path, retries):
    write_config(tmp_path, retries=retries)
    with pytest.raises(SystemExit):
        reload_in(tmp_path)

@pytest.mark.parametrize("log_days", [0])
def test_invalid_log_days(tmp_path, log_days):
    write_config(tmp_path, log_days=log_days)
    with pytest.raises(SystemExit):
        reload_in(tmp_path)

@pytest.mark.parametrize("log_interval", [0])
def test_invalid_log_interval(tmp_path, log_interval):
    write_config(tmp_path, log_interval=log_interval)
    with pytest.raises(SystemExit):
        reload_in(tmp_path)