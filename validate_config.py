import sys
import os
import ipaddress
import configparser
import logging
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime, time
from urllib.parse import urlparse
from dotenv import load_dotenv, dotenv_values
import getpass

@dataclass
class AppConfig:
    # General
    SLEEP_TIME: int
    WAIT_TIME: int
    MAX_RETRIES: int
    RESTART_TIMES: list[time]
    # Browser
    BROWSER_PROFILE_PATH: str
    BROWSER_BINARY: str
    HEADLESS: bool
    BROWSER: str
    # Logging
    LOG_FILE_FLAG: bool
    LOG_CONSOLE: bool
    DEBUG_LOGGING: bool
    ERROR_LOGGING: bool
    ERROR_PRTSCR: bool
    LOG_DAYS: int
    LOG_INTERVAL: int
    # API
    API: bool
    CONTROL_TOKEN: str
    # Env credentials
    username: str
    password: str
    url: str
    host: str
    port: int
    # Paths
    mon_file: Path
    log_file: Path
    sst_file: Path
    status_file: Path

def check_files(config_file: Path, env_file: Path, errors: list[str]):
    if not config_file.exists():
        errors.append("Missing config.ini file.")
    if not env_file.exists():
        errors.append("Missing .env file.")

def prepare_directories(logs_dir: Path, api_dir: Path):
    logs_dir.mkdir(parents=True, exist_ok=True)
    api_dir.mkdir(parents=True, exist_ok=True)

def load_ini(config_file: Path) -> configparser.ConfigParser:
    config = configparser.ConfigParser()
    config.read(config_file)
    return config

def safe_get(config, section: str, key: str, fallback, parse_fn, type_name: str, errors: list[str]):
    raw = None
    try:
        raw = config.get(section, key, fallback=None)
        if raw is None or str(raw).strip() == "":
            return fallback
        return parse_fn(raw)
    except Exception:
        errors.append(f"{section}.{key} must be a valid {type_name}. Got: {raw!r}. Falling back to {fallback}.")
        return fallback

def safe_getint(config, section: str, key: str, fallback: int, errors: list[str]) -> int:
    return safe_get(config, section, key, fallback, int, "integer", errors)

def safe_getbool(config, section: str, key: str, fallback: bool, errors: list[str]) -> bool:
    return safe_get(config, section, key, fallback, config._convert_to_boolean, "boolean (true/false)", errors)

def safe_getstr(
    config, section: str, key: str, fallback: str, errors: list[str], forbidden: list[str] | None = None
) -> str:
    value = config.get(section, key, fallback=fallback).strip()
    if forbidden:
        for f in forbidden:
            if f in value:
                errors.append(f"{section}.{key} contains placeholder value {f!r}.")
                return fallback
    return value

def parse_restart_times(raw: str, errors: list[str]) -> list[time]:
    times: list[time] = []
    for part in raw.split(','):
        part = part.strip()
        if not part:
            continue
        try:
            times.append(datetime.strptime(part, '%H:%M').time())
        except ValueError:
            errors.append(f"Invalid RESTART_TIME: {part!r} (expected HH:MM)")
    return times

def validate_env(env_file: Path, api: bool, errors: list[str]) -> tuple[str, str, str, str, str, str, dict]:
    try:
        load_dotenv(dotenv_path=env_file)
        values = dotenv_values(env_file)
        allowed = {"USERNAME", "PASSWORD", "URL", "FLASK_RUN_HOST", "FLASK_RUN_PORT", "SECRET"}
        
        # Check for unexpected keys
        for key in values:
            if key not in allowed:
                errors.append(f"Unexpected key in .env: {key!r}. Allowed: {', '.join(sorted(allowed))}")
        
        # Required fields (must exist and be non-empty)
        required_fields = {
            "USERNAME": "YourLocalUsername",
            "PASSWORD": "YourLocalPassword", 
            "URL": "http://192.168.100.100/protect/dashboard/multiviewurl",
        }
        
        for key, example_value in required_fields.items():
            if key not in values:
                errors.append(f"{key} is missing from .env file.")
            elif not values[key].strip():
                errors.append(f"{key} cannot be empty.")
            elif example_value and values[key].strip() == example_value:
                errors.append(f"{key} is still set to the example value. Please update it.")
        
        # Optional fields unless running api (if present, must be non-empty)
        optional_fields = ["FLASK_RUN_HOST", "FLASK_RUN_PORT"]
        if not api:
            for key in optional_fields:
                if key in values and not values[key].strip():
                    errors.append(f"If {key} is specified, it cannot be empty.")
        # Secret is always optional
        if "SECRET" in values and not values["SECRET"].strip():
            errors.append("If SECRET is specified, it cannot be empty.")
        # Validate URL format if present and non-empty
        if "URL" in values and values["URL"].strip():
            validate_url(values["URL"], errors)
        
        host = os.getenv('FLASK_RUN_HOST', '').strip()
        port = os.getenv('FLASK_RUN_PORT', '').strip()
        if api:
            try:
                ipaddress.ip_address(host)
            except ValueError:
                errors.append(f"FLASK_RUN_HOST must be a valid IP address, got: '{host}'")
                errors.append(f"Falling back to 0.0.0.0")
                host="0.0.0.0"
            if not port.isdigit():
                errors.append(f"FLASK_RUN_PORT must be an integer, got: '{port}'")
                errors.append(f"Falling back to 5000")
                port=5000
            else:
                port = int(port)
                if not (1 <= port <= 65535):
                    errors.append(f"FLASK_RUN_PORT must be 1-65535, got: {port}")
        return (
            os.getenv('USERNAME', ''),
            os.getenv('PASSWORD', ''),
            os.getenv('URL', ''),
            host,
            port,
            os.getenv('SECRET', ''),
            values
        )
    except Exception as e:
        errors.append(f"Failed to validate .env file: {str(e)}")
        errors.append("Format should be KEY=value.")
        return ('', '', '', '', '', '', {})
    
def validate_url(url_val: str, errors: list[str]):
    parsed = urlparse(url_val)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        errors.append(f"URL must start with http:// or https:// and include a host, got: '{url_val}'")

def validate_config(
    strict:       bool = True,
    api:          bool = False,
    config_file: Path | None = None,
    env_file: Path | None = None,
    logs_dir: Path | None = None,
    api_dir: Path | None = None,
) -> AppConfig | bool:
    # Defaults
    base = Path(__file__).parent
    config_file = config_file or base / 'config.ini'
    env_file = env_file or base / '.env'
    logs_dir = logs_dir or base / 'logs'
    api_dir = api_dir or base / 'api'

    errors: list[str] = []
    # File checks
    check_files(config_file, env_file, errors)
    prepare_directories(logs_dir, api_dir)

    # Paths
    mon_file = logs_dir / 'monitoring.log'
    log_file = logs_dir / 'viewport.log'
    sst_file = api_dir / 'sst.txt'
    status_file = api_dir / 'status.txt'

    # Parse INI
    config = load_ini(config_file)

    # General section
    sleep_time = safe_getint(config, 'General', 'SLEEP_TIME', 300, errors)
    wait_time = safe_getint(config, 'General', 'WAIT_TIME', 30, errors)
    max_retries = safe_getint(config, 'General', 'MAX_RETRIES', 5, errors)
    raw_times = config.get('General', 'RESTART_TIMES', fallback='')
    restart_times = parse_restart_times(raw_times, errors)

    # Browser section
    user = getpass.getuser()
    default_profile = f"/home/{user}/.config/google-chrome/"
    profile_path = safe_getstr(config, 'Browser', 'BROWSER_PROFILE_PATH', default_profile, errors, ['your-user'])
    binary = safe_getstr(config, 'Browser', 'BROWSER_BINARY', '/usr/bin/google-chrome', errors)
    headless = safe_getbool(config, 'Browser', 'HEADLESS', False, errors)
    browser = (
        'firefox' if 'firefox' in binary.lower() else
        'chromium' if 'chromium' in binary.lower() else
        'chrome'
    )
    if browser not in profile_path.lower():
        errors.append(f"Browser mismatch: binary uses '{browser}', but profile path does not.")

    # Logging section
    log_file_flag = safe_getbool(config, 'Logging', 'LOG_FILE_FLAG', True, errors)
    log_console = safe_getbool(config, 'Logging', 'LOG_CONSOLE', True, errors)
    debug_logging = safe_getbool(config, 'Logging', 'DEBUG_LOGGING', False, errors)
    error_logging = safe_getbool(config, 'Logging', 'ERROR_LOGGING', False, errors)
    error_prtscr = safe_getbool(config, 'Logging', 'ERROR_PRTSCR', False, errors)
    log_days = safe_getint(config, 'Logging', 'LOG_DAYS', 7, errors)
    log_interval = safe_getint(config, 'Logging', 'LOG_INTERVAL', 60, errors)

    # API section
    api_flag = safe_getbool(config, 'API', 'USE_API', False, errors)

    # Validate .env
    username, password, url_val, host, port, secret, env_values = validate_env(env_file, api, errors)
    
    control_token = secret.strip()

    # Value constraints
    if sleep_time < 60:
        errors.append("SLEEP_TIME must be ≥ 60.")
    if wait_time <= 5:
        errors.append("WAIT_TIME must be > 5.")
    if max_retries < 3:
        errors.append("MAX_RETRIES must be ≥ 3.")
    if log_days < 1:
        errors.append("LOG_DAYS must be ≥ 1.")
    if log_interval < 1:
        errors.append("LOG_INTERVAL must be ≥ 1.")

    # Report or return
    if errors:
        for e in errors:
            logging.error(e)
        if strict:
            sys.exit(1)
        return False
    return AppConfig(
        SLEEP_TIME=sleep_time,
        WAIT_TIME=wait_time,
        MAX_RETRIES=max_retries,
        RESTART_TIMES=restart_times,
        BROWSER_PROFILE_PATH=profile_path,
        BROWSER_BINARY=binary,
        HEADLESS=headless,
        BROWSER=browser,
        LOG_FILE_FLAG=log_file_flag,
        LOG_CONSOLE=log_console,
        DEBUG_LOGGING=debug_logging,
        ERROR_LOGGING=error_logging,
        ERROR_PRTSCR=error_prtscr,
        LOG_DAYS=log_days,
        LOG_INTERVAL=log_interval,
        API=api_flag,
        CONTROL_TOKEN=control_token,
        username=username,
        password=password,
        url=url_val,
        host=host,
        port=port,
        mon_file=mon_file,
        log_file=log_file,
        sst_file=sst_file,
        status_file=status_file
    )
