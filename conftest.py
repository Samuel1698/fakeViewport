import logging
import logging.handlers
import pytest
import viewport
from validate_config import AppConfig

@pytest.fixture(autouse=True)
def isolate_logging(tmp_path, monkeypatch):
    # 1) Redirect the RotatingFileHandler class itself
    real_RTFH = logging.handlers.TimedRotatingFileHandler
    def patched_factory(filename, *args, **kwargs):
        target = tmp_path / "test.log"
        return real_RTFH(str(target), *args, **kwargs)
    monkeypatch.setattr(logging.handlers, "TimedRotatingFileHandler", patched_factory)

    # 2) Wipe out any existing handlers so tests always start clean
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)

    # 3a) Patch your module’s logs_dir so log_error writes screenshots into tmp_path
    monkeypatch.setattr(viewport, "logs_dir", tmp_path)

    # 3b) (Re)configure the root logger exactly once for all tests
    #     pointing at tmp_path/"test.log", no console output.
    viewport.configure_logging(
        log_file_path=str(tmp_path / "test.log"),
        log_file=True,
        log_console=False,
        log_days=7,
        Debug_logging=True,
    )

@pytest.fixture(autouse=True)
def provide_dummy_config(monkeypatch, tmp_path):
    """
    Before every test:
      - Construct a minimal AppConfig with all of the attributes viewport.main
        and args_handler expect.
      - Monkey-patch viewport.validate_config to always return it.
      - Monkey-patch viewport.cfg to be it.
      - Also copy every cfg.<attr> up into viewport.<attr> so any code
        still referencing module-level globals continues to work.
    """
    # 1) build a dummy AppConfig
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
    )

    # 2) stub out validate_config to always give the above cfg
    monkeypatch.setattr(viewport, "validate_config", lambda *args, **kwargs: cfg)

    # 3) ensure viewport.cfg points at it too
    monkeypatch.setattr(viewport, "cfg", cfg)

    for name, val in vars(cfg).items():
        setattr(viewport, name, val)

    return cfg