# tests/test_logging_config.py
import logging
import pytest
from logging.handlers import TimedRotatingFileHandler
from logging_config import configure_logging, ColoredFormatter
import sys
# ─── Override conftest's autouse isolate_logging ─────────────────────────────
@pytest.fixture(autouse=True)
def isolate_logging_override():
    # no-op: prevents conftest.py from reconfiguring logging for these tests
    yield

# ─── Clear root handlers before each test ────────────────────────────────────
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

    # 1) Root logger returned, level INFO
    assert logger is logging.getLogger()
    assert logger.level == logging.INFO

    # 2) File handler present
    file_handlers = [
        h for h in logger.handlers
        if isinstance(h, TimedRotatingFileHandler)
    ]
    assert file_handlers, "Expected a TimedRotatingFileHandler"
    assert log_path.exists()

    # 3) Console handler present (StreamHandler but NOT a file handler)
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
