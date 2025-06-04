import re
import pytest
import logging
from pathlib import Path
from validate_config import validate_config

# Helpers to write test files
BASE_INI = """
[General]
SLEEP_TIME = 300
WAIT_TIME = 30
MAX_RETRIES = 5
RESTART_TIMES = 03:00

[Browser]
BROWSER_BINARY = /usr/bin/google-chrome
BROWSER_PROFILE_PATH = /home/test/.config/google-chrome
HEADLESS = false

[Logging]
LOG_FILE_FLAG = true
LOG_CONSOLE = true
ERROR_LOGGING = false
LOG_DAYS = 7
LOG_INTERVAL = 60

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
def write_base(tmp_path: Path, ini_overrides=None, env_overrides=None):
    # write config.ini
    ini = BASE_INI
    if ini_overrides:
        for key, val in ini_overrides.items():
            ini = re.sub(rf"^{key}\s*=.*$", f"{key} = {val}", ini, flags=re.MULTILINE)
    (tmp_path / "config.ini").write_text(ini)

    # write .env, allowing removal if override value is None
    base_kv = dict(line.split("=", 1) for line in BASE_ENV.strip().splitlines())
    if env_overrides:
        for k, v in env_overrides.items():
            if v is None:
                base_kv.pop(k, None)
            else:
                base_kv[k] = v
    out = "\n".join(f"{k}={v}" for k, v in base_kv.items()) + "\n"
    (tmp_path / ".env").write_text(out)

    # create dirs
    (tmp_path / "logs").mkdir(exist_ok=True)  
    (tmp_path / "api").mkdir(exist_ok=True)
# ----------------------------------------------------------------------------- 
# Strict mode should exit
# ----------------------------------------------------------------------------- 
def test_strict_mode_exits_on_missing(tmp_path):
    # no files at all
    with pytest.raises(SystemExit):
        validate_config(strict=True,
                        config_file=tmp_path / "config.ini",
                        env_file=tmp_path / ".env",
                        logs_dir=tmp_path / "logs",
                        api_dir=tmp_path / "api")
# ----------------------------------------------------------------------------- 
# INI value errors in loose mode
# ----------------------------------------------------------------------------- 
@pytest.mark.parametrize("ini_overrides, expected_msg", [
    ({"WAIT_TIME":"string"},      "General.WAIT_TIME must be a valid integer"),
    ({"HEADLESS":"string"},       "Browser.HEADLESS must be a valid boolean"),
    ({"BROWSER_PROFILE_PATH":"/home/your-user/foo"}, "placeholder value 'your-user'"),
    ({"RESTART_TIMES":"99:99"},     "Invalid RESTART_TIME: '99:99'"),
])
def test_invalid_ini_loose(tmp_path, caplog, ini_overrides, expected_msg):
    write_base(tmp_path, ini_overrides=ini_overrides)
    caplog.set_level("ERROR")
    ok = validate_config(strict=False,
                        config_file=tmp_path / "config.ini",
                        env_file=tmp_path / ".env",
                        logs_dir=tmp_path / "logs",
                        api_dir=tmp_path / "api")
    assert ok is False
    assert any(expected_msg in rec.message for rec in caplog.records)
# ----------------------------------------------------------------------------- 
# .env value errors in loose mode
# ----------------------------------------------------------------------------- 
@pytest.mark.parametrize("env_overrides, expected_msg", [
    ({"URL":"//nohost"},        "URL must start with http:// or https:// and include a host"),
    ({"URL":"ftp://example"},   "URL must start with http:// or https:// and include a host"),
    ({"URL":"http:///pathonly"},"URL must start with http:// or https:// and include a host"),
    ({"WRONG_KEY":"value"},     "Unexpected key in .env: 'WRONG_KEY'"),
    ({"USERNAME":""},           "USERNAME cannot be empty."),
    ({"PASSWORD":""},           "PASSWORD cannot be empty."),
])
def test_invalid_env_loose(tmp_path, caplog, monkeypatch, env_overrides, expected_msg):
    # clear any inherited env
    for k in ("USERNAME","PASSWORD","URL","SECRET","FLASK_RUN_HOST","FLASK_RUN_PORT"): monkeypatch.delenv(k, raising=False)
    write_base(tmp_path, env_overrides=env_overrides)
    caplog.set_level("ERROR")
    ok = validate_config(strict=False,
                        config_file=tmp_path / "config.ini",
                        env_file=tmp_path / ".env",
                        logs_dir=tmp_path / "logs",
                        api_dir=tmp_path / "api")
    assert ok is False
    assert any(expected_msg in rec.message for rec in caplog.records)
# ----------------------------------------------------------------------------- 
# .env exception
# ----------------------------------------------------------------------------- 
def test_env_parsing_exception(tmp_path, caplog):
    #If the .env file is malformed (e.g. a line without “=”)
    write_base(tmp_path)
    (tmp_path / ".env").write_text("PASSWORD\n")

    caplog.set_level("ERROR")
    ok = validate_config(
        strict=False,
        config_file=tmp_path / "config.ini",
        env_file=tmp_path / ".env",
        logs_dir=tmp_path / "logs",
        api_dir=tmp_path / "api",
    )

    assert ok is False
    assert any("Failed to validate .env file:" in rec.message for rec in caplog.records)
    assert any("Format should be KEY=value." in rec.message for rec in caplog.records)
# ----------------------------------------------------------------------------- 
# Host/Port parsing in loose mode (no validation errors)
# ----------------------------------------------------------------------------- 
@pytest.mark.parametrize(
    "host,port,expected_errors",
    [
        ("not_an_ip", "8080",        ["FLASK_RUN_HOST must be a valid IP address"]),
        ("127.0.0.1", "number",      ["FLASK_RUN_PORT must be an integer"]),
        ("::1",       "70000",       ["FLASK_RUN_PORT must be 1-65535"]),
    ],
)
def test_host_port_validation_api_mode(tmp_path, caplog, monkeypatch, host, port, expected_errors):
    # override the .env file, not just the env‐vars
    write_base(tmp_path, env_overrides={
        "FLASK_RUN_HOST": host,
        "FLASK_RUN_PORT": port,
    })
    caplog.set_level("ERROR")

    ok = validate_config(
        strict=False,
        config_file=tmp_path / "config.ini",
        env_file=tmp_path / ".env",
        logs_dir=tmp_path / "logs",
        api_dir=tmp_path / "api",
    )

    # Should fail in API mode
    assert ok is False
    # Each expected error must appear in the log
    for msg in expected_errors:
        assert any(msg in record.message for record in caplog.records), \
            f"Expected to find error '{msg}' in:\n" + "\n".join(r.message for r in caplog.records)
# ----------------------------------------------------------------------------- 
# Missing host/port should not error
# ----------------------------------------------------------------------------- 
def test_missing_host_port_no_errors(tmp_path, caplog, monkeypatch):
    write_base(tmp_path)
    # remove host/port
    monkeypatch.delenv("FLASK_RUN_HOST", raising=False)
    monkeypatch.delenv("FLASK_RUN_PORT", raising=False)
    caplog.set_level("ERROR")
    ok = validate_config(strict=False,
                        config_file=tmp_path / "config.ini",
                        env_file=tmp_path / ".env",
                        logs_dir=tmp_path / "logs",
                        api_dir=tmp_path / "api")
    # should succeed and no FLASK_RUN errors
    assert ok
    assert not isinstance(ok, bool)  # returns AppConfig object
    assert not any("FLASK_RUN_HOST" in rec.message or "FLASK_RUN_PORT" in rec.message for rec in caplog.records)

# ----------------------------------------------------------------------------- 
# Optional .env fields missing vs empty
# ----------------------------------------------------------------------------- 
@pytest.mark.parametrize("field", ["FLASK_RUN_HOST", "FLASK_RUN_PORT", "SECRET"])
def test_optional_env_fields_missing_and_empty(tmp_path, caplog, monkeypatch, field):
    # Any optional_fields (FLASK_RUN_HOST, FLASK_RUN_PORT, SECRET):
    #   - Missing → should succeed (no error)
    #   - Present but empty → should fail with the right message
    caplog.set_level("ERROR")

    # missing field in .env → still OK
    write_base(tmp_path, env_overrides={field: None})
    caplog.clear()
    ok1 = validate_config(
        strict=False,
        config_file=tmp_path / "config.ini",
        env_file=tmp_path / ".env",
        logs_dir=tmp_path / "logs",
        api_dir=tmp_path / "api",
    )
    assert ok1
    assert not any(field in rec.message for rec in caplog.records)
    # present but empty → should fail with "<FIELD> is specified but empty."
    caplog.clear()
    write_base(tmp_path, env_overrides={field: ""})
    ok2 = validate_config(
        strict=False,
        config_file=tmp_path / "config.ini",
        env_file=tmp_path / ".env",
        logs_dir=tmp_path / "logs",
        api_dir=tmp_path / "api",
    )
    assert ok2 is False
    assert any(
        f"{field} is specified but empty." in rec.message
        for rec in caplog.records
    )
# ----------------------------------------------------------------------------- 
# Error displays INI + env
# ----------------------------------------------------------------------------- 
@pytest.mark.parametrize("ini_overrides, env_overrides, expected_msg", [
    # example‐value still set
    (None, {"USERNAME": "YourLocalUsername"}, "USERNAME is still set to the example value. Please update it."),
    (None, {"PASSWORD": "YourLocalPassword"}, "PASSWORD is still set to the example value. Please update it."),
    (None, {"URL": "http://192.168.100.100/protect/dashboard/multiviewurl"},
    "URL is still set to the example value. Please update it."),
    # browser/profile mismatch
    ({"BROWSER_BINARY": "/usr/bin/firefox"}, {}, 
    "Browser mismatch: binary uses 'firefox', but profile path does not."),
    # numeric constraints
    ({"SLEEP_TIME": "30"}, {},       "SLEEP_TIME must be ≥ 60."),
    ({"WAIT_TIME": "5"}, {},         "WAIT_TIME must be > 5."),
    ({"MAX_RETRIES": "2"}, {},       "MAX_RETRIES must be ≥ 3."),
    ({"LOG_DAYS": "0"}, {},          "LOG_DAYS must be ≥ 1."),
    ({"LOG_INTERVAL": "0"}, {},      "LOG_INTERVAL must be ≥ 1."),
])
def test_additional_validate_config_errors(tmp_path, caplog, monkeypatch,
                                        ini_overrides, env_overrides, expected_msg):
    # write base files with overrides
    write_base(tmp_path, ini_overrides=ini_overrides, env_overrides=env_overrides)
    caplog.set_level("ERROR")
    ok = validate_config(
        strict=False,
        config_file=tmp_path / "config.ini",
        env_file=tmp_path / ".env",
        logs_dir=tmp_path / "logs",
        api_dir=tmp_path / "api",
    )
    # should fail and log exactly the expected message
    assert ok is False
    assert any(expected_msg in rec.message for rec in caplog.records), \
        f"Expected to see {expected_msg!r} in:\n" + "\n".join(r.message for r in caplog.records)

def test_validate_config_logs_errors_and_returns_false(tmp_path, caplog):
    # Arrange: produce at least one error (SECRET empty)
    write_base(tmp_path, env_overrides={"SECRET": ""})
    caplog.set_level(logging.ERROR)
    # Act
    ok = validate_config(
        strict=False,
        config_file=tmp_path / "config.ini",
        env_file=tmp_path / ".env",
        logs_dir=tmp_path / "logs",
        api_dir=tmp_path / "api",
    )
    # Assert
    assert ok is False
    # Should have logged one error per entry in errors[]
    messages = [rec.message for rec in caplog.records]
    assert any("SECRET is specified but empty." in m for m in messages)

def test_validate_config_strict_mode_exits_after_logging(tmp_path, caplog):
    # Arrange: again force an error
    write_base(tmp_path, env_overrides={"SECRET": ""})
    caplog.set_level(logging.ERROR)

    # Act & Assert
    with pytest.raises(SystemExit) as exc:
        validate_config(
            strict=True,
            config_file=tmp_path / "config.ini",
            env_file=tmp_path / ".env",
            logs_dir=tmp_path / "logs",
            api_dir=tmp_path / "api",
        )
    # exit code 1 on errors
    assert exc.value.code == 1

    # And verify we still logged our errors before exiting
    messages = [rec.message for rec in caplog.records]
    assert any("SECRET is specified but empty." in m for m in messages)
# ----------------------------------------------------------------------------- 
# Print and Exit behavior
# ----------------------------------------------------------------------------- 
def test_no_errors_skips_reporting(tmp_path, caplog):
    # Write base config with all valid values
    write_base(tmp_path)
    caplog.set_level(logging.ERROR)

    ok = validate_config(
        strict=False,
        print=False,
        config_file=tmp_path / "config.ini",
        env_file=tmp_path / ".env",
        logs_dir=tmp_path / "logs",
        api_dir=tmp_path / "api",
    )

    assert ok  # Should return AppConfig, not False
    assert not caplog.records  # No errors expected


def test_print_only_logs_errors(tmp_path, caplog):
    # Force a known error (SECRET empty)
    write_base(tmp_path, env_overrides={"SECRET": ""})
    caplog.set_level(logging.ERROR)

    ok = validate_config(
        strict=False,
        print=True,
        config_file=tmp_path / "config.ini",
        env_file=tmp_path / ".env",
        logs_dir=tmp_path / "logs",
        api_dir=tmp_path / "api",
    )
    assert ok is False
    assert any("SECRET is specified but empty." in r.message for r in caplog.records)

def test_strict_only_exits_on_error(tmp_path, caplog):
    write_base(tmp_path, env_overrides={"SECRET": ""})
    caplog.set_level(logging.ERROR)

    with pytest.raises(SystemExit) as exc:
        validate_config(
            strict=True,
            print=False,
            config_file=tmp_path / "config.ini",
            env_file=tmp_path / ".env",
            logs_dir=tmp_path / "logs",
            api_dir=tmp_path / "api",
        )

    assert exc.value.code == 1
    assert not caplog.records  

def test_print_and_strict_logs_and_exits(tmp_path, caplog):
    # Force a known error (SECRET empty)
    write_base(tmp_path, env_overrides={"SECRET": ""})
    caplog.set_level(logging.ERROR)

    with pytest.raises(SystemExit) as exc:
        validate_config(
            strict=True,
            print=True,
            config_file=tmp_path / "config.ini",
            env_file=tmp_path / ".env",
            logs_dir=tmp_path / "logs",
            api_dir=tmp_path / "api",
        )

    assert exc.value.code == 1
    assert any("SECRET is specified but empty." in r.message for r in caplog.records)