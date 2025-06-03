import logging
import logging.handlers
import pytest
import viewport
import monitoring
from validate_config import AppConfig

@pytest.fixture(autouse=True)
def isolate_logging(tmp_path, monkeypatch):
    # Redirect the RotatingFileHandler class itself
    real_RTFH = logging.handlers.TimedRotatingFileHandler
    def patched_factory(filename, *args, **kwargs):
        target = tmp_path / "test.log"
        return real_RTFH(str(target), *args, **kwargs)
    monkeypatch.setattr(logging.handlers, "TimedRotatingFileHandler", patched_factory)

    # Wipe out any existing handlers so tests always start clean
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)

    # Patch your module’s logs_dir so log_error writes screenshots into tmp_path
    monkeypatch.setattr(viewport, "logs_dir", tmp_path)

    # (Re)configure the root logger exactly once for all tests
    # pointing at tmp_path/"test.log", no console output.
    viewport.configure_logging(
        log_file_path=str(tmp_path / "test.log"),
        log_file=True,
        log_console=False,
        log_days=7,
        Debug_logging=True,
    )

@pytest.fixture(autouse=True)
def provide_dummy_config(monkeypatch, tmp_path):
    # Before every test:
    #   - Construct a minimal AppConfig with all of the attributes viewport.main
    #     and args_handler expect.
    #   - Monkey-patch viewport.validate_config to always return it.
    #   - Monkey-patch viewport.cfg to be it.
    #   - Also copy every cfg.<attr> up into viewport.<attr> so any code
    #     still referencing module-level globals continues to work.
    cfg = AppConfig(
        # timeouts / sleeps / retries
        SLEEP_TIME=60,
        WAIT_TIME=30,
        MAX_RETRIES=3,
        RESTART_TIMES=[],
        # browser config
        BROWSER_PROFILE_PATH="",
        BROWSER_BINARY="chromium",
        HEADLESS=False,
        BROWSER="",
        # logging config
        LOG_FILE_FLAG=False,
        LOG_CONSOLE=False,
        DEBUG_LOGGING=False,
        ERROR_LOGGING=False,
        ERROR_PRTSCR=False,
        LOG_DAYS=7,
        LOG_INTERVAL=60,
        # API & creds
        API=False,
        CONTROL_TOKEN="",
        username="user",
        password="pass",
        url="http://example.com",
        host="",
        port="",
        # file paths
        mon_file=str(tmp_path / "monitoring.log"),
        log_file=str(tmp_path / "viewport.log"),
        sst_file=tmp_path / "sst.txt",
        status_file=tmp_path / "status.txt",
        restart_file=tmp_path / ".restart",
        pause_file  = tmp_path / ".pause",
    )
    # Save the real config browser since it changes based on other variables
    real_browser = viewport.BROWSER
     # stub out viewport
    monkeypatch.setattr(viewport, "validate_config", lambda *args, **kwargs: cfg)
    monkeypatch.setattr(viewport, "cfg", cfg)
    for k, v in vars(cfg).items():
        setattr(viewport, k, v)

    # now stub out monitoring exactly the same way:
    monkeypatch.setattr(monitoring, "validate_config", lambda *args, **kwargs: cfg)
    monkeypatch.setattr(monitoring, "cfg", cfg)
    for k, v in vars(cfg).items():
        setattr(monitoring, k, v)
    # Bring back browser from the real config
    viewport.BROWSER = real_browser
    return cfg