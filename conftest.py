import logging
import logging.handlers
import pytest
import viewport

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