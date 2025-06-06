import logging, logging.handlers, shutil, pytest, inspect
from pathlib import Path
import viewport, monitoring
from validate_config import AppConfig

# --------------------------------------------------------------------------- # 
# Guard against rogue deletes – session scope, uses tmp_path_factory
# --------------------------------------------------------------------------- # 
@pytest.fixture(autouse=True, scope="session")
def hard_delete_guard(tmp_path_factory):
    safe_root = tmp_path_factory.getbasetemp().parents[0].resolve()
    real_rmtree = shutil.rmtree
    def guarded(path, *a, **kw):
        path = Path(path).resolve()
        if not str(path).startswith(str(safe_root)): 
            raise RuntimeError(f"Refusing to delete outside {safe_root}: {path}")
        else: pass
        return real_rmtree(path, *a, **kw)
    mp = pytest.MonkeyPatch()
    mp.setattr("viewport.shutil.rmtree", guarded, raising=True)
    yield
    mp.undo()

# --------------------------------------------------------------------------- # 
# Redirect logging
# --------------------------------------------------------------------------- # 
@pytest.fixture(autouse=True, scope="session")
def isolate_logging(tmp_path_factory):
    log_dir = tmp_path_factory.mktemp("logs")
    real_trfh = logging.handlers.TimedRotatingFileHandler

    class _PatchedTRFH(real_trfh):
        def __init__(self, *_, **kw):
            # Try to discover the function-scoped tmp_path on the call stack
            stack_tmp = next(
                (f.frame.f_locals["tmp_path"]
                    for f in inspect.stack()
                    if "tmp_path" in f.frame.f_locals),
                None,
            )
            target_dir = Path(stack_tmp or log_dir)

            # Forward only keyword args – drop the caller’s positional filename
            super().__init__(target_dir / "test.log", **kw)

    mp = pytest.MonkeyPatch()
    mp.setattr(logging.handlers, "TimedRotatingFileHandler", _PatchedTRFH)
    if hasattr(viewport, "logs_dir"): mp.setattr(viewport, "logs_dir", log_dir, raising=False)
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)

    viewport.configure_logging(
        log_file_path=str(log_dir / "test.log"),
        log_file=True, log_console=False,
        log_days=7, Debug_logging=True,
    )
    yield
    mp.undo()

# --------------------------------------------------------------------------- # 
# Dummy AppConfig – session scope, use tmp_path_factory
# --------------------------------------------------------------------------- # 
@pytest.fixture(autouse=True, scope="session")
def provide_dummy_config(tmp_path_factory):
    data_dir = tmp_path_factory.mktemp("data")
    cfg = AppConfig(
        # timeouts / sleeps / retries
        SLEEP_TIME=60,
        WAIT_TIME=30,
        MAX_RETRIES=3,
        RESTART_TIMES=[],
        # browser config
        BROWSER_PROFILE_PATH="",
        BROWSER_BINARY="",
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
        mon_file=str(data_dir / "monitoring.log"),
        log_file=str(data_dir / "viewport.log"),
        sst_file=data_dir / "sst.txt",
        status_file=data_dir / "status.txt",
        restart_file=data_dir / ".restart",
        pause_file= data_dir / ".pause",
    )
    # Save the real config browser since it changes based on other variables
    mp = pytest.MonkeyPatch()
    for mod in (viewport, monitoring):
        def _cfg(*_a, **_kw):
            # make sure any per-test monkey-patches bleed through
            cfg.sst_file     = getattr(viewport,   "sst_file",     cfg.sst_file)
            cfg.status_file  = getattr(viewport,   "status_file",  cfg.status_file)
            cfg.pause_file   = getattr(viewport,   "pause_file",   cfg.pause_file)
            cfg.restart_file = getattr(viewport,   "restart_file", cfg.restart_file)
            return cfg
        mp.setattr(mod, "validate_config", _cfg, raising=False)
        mp.setattr(mod, "cfg", cfg, raising=False)
        for k, v in vars(cfg).items():
            mp.setattr(mod, k, v, raising=False)

    yield cfg
    mp.undo() 