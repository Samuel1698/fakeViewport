import pytest
import logging, datetime, os, sys
from pathlib import Path
from logging.handlers import TimedRotatingFileHandler
from logging_config import configure_logging, ColoredFormatter
# --------------------------------------------------------------------------- # 
# Override conftest's autouse isolate_logging
# --------------------------------------------------------------------------- # 
@pytest.fixture(autouse=True)
def isolate_logging_override():
    # no-op: prevents conftest.py from reconfiguring logging for these tests
    yield

# --------------------------------------------------------------------------- # 
# Clear root handlers before each test
# --------------------------------------------------------------------------- # 
@pytest.fixture(autouse=True)
def clear_root_handlers():
    root = logging.getLogger()
    saved = list(root.handlers)
    root.handlers.clear()
    yield
    root.handlers[:] = saved

def test_configure_logging_file_and_console(tmp_path):
    log_path = tmp_path / "app.log"
    logger = configure_logging(
        log_file_path=str(log_path),
        log_file=True,
        log_console=True,
        log_days=5,
        Debug_logging=False
    )

    # Root logger returned, level INFO
    assert logger is logging.getLogger()
    assert logger.level == logging.INFO

    # File handler present
    file_handlers = [
        h for h in logger.handlers
        if isinstance(h, TimedRotatingFileHandler)
    ]
    assert file_handlers, "Expected a TimedRotatingFileHandler"
    assert log_path.exists()

    # Console handler present (StreamHandler but NOT a file handler)
    # pick out the StreamHandler we added (writing to stderr)
    console_handlers = [
        h for h in logger.handlers
        if isinstance(h, logging.StreamHandler)
        and getattr(h, "stream", None) is sys.stderr
    ]
    assert len(console_handlers) == 1
    assert isinstance(console_handlers[0].formatter, ColoredFormatter)

def test_configure_logging_debug_mode_only_file(tmp_path):
    log_path = tmp_path / "debug.log"
    logger = configure_logging(
        log_file_path=str(log_path),
        log_file=True,
        log_console=False,
        log_days=2,
        Debug_logging=True
    )

    assert logger.level == logging.DEBUG

    # file handler still present
    assert any(isinstance(h, TimedRotatingFileHandler) for h in logger.handlers)
    # but no StreamHandler writing to stderr
    assert not any(
        isinstance(h, logging.StreamHandler)
        and getattr(h, "stream", None) is sys.stderr
        for h in logger.handlers
    )

def test_configure_logging_only_console(tmp_path):
    log_path = tmp_path / "unused.log"
    logger = configure_logging(
        log_file_path=str(log_path),
        log_file=False,
        log_console=True,
    )

    assert logger.level == logging.INFO

    # no file handlers at all
    assert not any(isinstance(h, TimedRotatingFileHandler)
        for h in logger.handlers)

    # exactly one StreamHandler writing to stderr
    console_handlers = [
        h for h in logger.handlers
        if isinstance(h, logging.StreamHandler)
        and getattr(h, "stream", None) is sys.stderr
    ]
    assert len(console_handlers) == 1

@pytest.mark.parametrize("level, expected_color", [
    (logging.ERROR,   ColoredFormatter.RED),
    (logging.WARNING, ColoredFormatter.YELLOW),
    (logging.INFO,    ColoredFormatter.GREEN),
    (logging.DEBUG,   ColoredFormatter.CYAN),
    (12345,           ColoredFormatter.NC),
])
def test_colored_formatter_all_branches(level, expected_color):
    fmt = ColoredFormatter("%(message)s")
    rec = logging.LogRecord(
        name="test",
        level=level,
        pathname=__file__,
        lineno=1,
        msg="Payload",
        args=(),
        exc_info=None
    )
    out = fmt.format(rec)
    assert out.startswith(expected_color)
    assert out.endswith(ColoredFormatter.NC)
    assert "Payload" in out

# --------------------------------------------------------------------------- # 
# Test log rotation
# --------------------------------------------------------------------------- # 
def test_date_only_rotation_culls_old_backups(tmp_path):
    """
    Create “test.log.YYYY-MM-DD” files by hand and verify the handler
    deletes the oldest if there are more than 3 days of backups.
    """
    # Build a handler exactly as done in configure_logging()
    handler = TimedRotatingFileHandler(
        filename    = str(tmp_path / "test.log"),
        when        = "midnight",
        interval    = 1,
        backupCount = 2,
        encoding    = "utf-8",
        utc         = False,
        atTime      = datetime.time(0, 0),
    )
    # Create five “date” backups in arbitrary order:
    for d in ["2025-05-03", "2025-05-01", "2025-05-05", "2025-05-02", "2025-05-04"]:
        (tmp_path / f"test.log.{d}").write_text("")

    # Ask which files would be deleted
    to_delete = handler.getFilesToDelete()
    filenames_to_delete = sorted(Path(p).name for p in to_delete)
    assert filenames_to_delete == ["test.log.2025-05-01", "test.log.2025-05-02", "test.log.2025-05-03"]

    # Simulate removing them and verify only the newest 3 remain
    for p in to_delete:
        os.remove(p)

    remaining = sorted(p.name for p in tmp_path.iterdir() if p.name.startswith("test.log"))
    assert remaining == [
        "test.log", 
        "test.log.2025-05-04",
        "test.log.2025-05-05",
    ]
