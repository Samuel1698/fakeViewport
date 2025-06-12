import pytest
import logging, datetime, os, sys, re
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

# --------------------------------------------------------------------------- #
# Boilerplate configuration check
# --------------------------------------------------------------------------- #
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

# --------------------------------------------------------------------------- #
# Re-use-existing-handler branch coverage
# --------------------------------------------------------------------------- #
def test_configure_logging_reuses_existing_handler(tmp_path):
    """
    Calling configure_logging() twice with the *same* path must not add a second
    TimedRotatingFileHandler - the early-return branch should trigger.
    """
    log_file = tmp_path / "viewport.log"

    first = configure_logging(
        log_file_path=str(log_file),
        log_file=True,
        log_console=False,
        log_days=1,
        Debug_logging=False,
    )
    handlers_before = [h for h in first.handlers if isinstance(h, TimedRotatingFileHandler)]
    assert len(handlers_before) == 1

    second = configure_logging(
        log_file_path=str(log_file),
        log_file=True,
        log_console=False,
        log_days=1,
        Debug_logging=False,
    )
    handlers_after = [h for h in second.handlers if isinstance(h, TimedRotatingFileHandler)]
    assert second is first                                   # same logger object
    assert handlers_after == handlers_before                 # same single handler

    # tidy up to avoid bleed-through
    for h in list(first.handlers):
        first.removeHandler(h)
        h.close()

# --------------------------------------------------------------------------- #
# End-to-end routing & filter behaviour
# --------------------------------------------------------------------------- #
def test_viewport_and_monitoring_logs_routed_and_filtered(tmp_path):
    """
    • viewport.log gets *root/update* messages, not monitoring/werkzeug  
    • monitoring.log gets monitoring + cleaned werkzeug lines  
    • ANSI codes, IP addresses, and timestamps are stripped in monitoring.log
    """
    vp_log = tmp_path / "viewport.log"
    mon_log = tmp_path / "monitoring.log"

    # viewport sets up first – root handler
    configure_logging(
        log_file_path=str(vp_log),
        log_file=True,
        log_console=False,
        log_days=1,
        Debug_logging=False,
    )
    # monitoring adds its own handler without wiping the first
    configure_logging(
        log_file_path=str(mon_log),
        log_file=True,
        log_console=False,
        log_days=1,
        Debug_logging=False,
    )

    # emit one message for each logger type
    logging.info("ROOT message")
    logging.getLogger("monitoring").info("MON message")
    raw_access = "\x1b[0;32m127.0.0.1 - - [01/Jan/2025 00:00:00] \"GET /api/test HTTP/1.1\" 200 -\x1b[0m"
    logging.getLogger("werkzeug").info(raw_access)

    # flush all handlers so files are written
    for h in logging.getLogger().handlers:
        h.flush()

    vp_text  = vp_log.read_text()
    mon_text = mon_log.read_text()

    # viewport.log expectations
    assert "ROOT message" in vp_text
    assert "MON message" not in vp_text
    assert "/api/test"   not in vp_text

    # monitoring.log expectations
    assert "MON message" in mon_text
    assert "ROOT message" not in mon_text
    assert "\"GET /api/test HTTP/1.1\" 200" in mon_text    # cleaned access line
    assert "\x1b[" not in mon_text                         # no ANSI codes
    assert not "127.0.0.1 - - [01/Jan/2025 00:00:00]" in mon_text
    # no IP + timestamp clutter
    assert not re.search(r"\d+\.\d+\.\d+\.\d+ - - \[", mon_text)
