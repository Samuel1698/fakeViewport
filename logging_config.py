import logging, re
from logging.handlers import TimedRotatingFileHandler
from datetime import time as dtime
from pathlib import Path

class ColoredFormatter(logging.Formatter):
    RED    = '\033[0;31m'
    GREEN  = '\033[0;32m'
    YELLOW = '\033[1;33m'
    CYAN   = '\033[36m'
    NC     = '\033[0m'

    def format(self, record):
        # Apply color based on level
        if record.levelno == logging.ERROR:
            color = self.RED
        elif record.levelno == logging.WARNING:
            color = self.YELLOW
        elif record.levelno == logging.INFO:
            color = self.GREEN
        elif record.levelno == logging.DEBUG:
            color = self.CYAN
        else:
            color = self.NC
        record.msg = f"{color}{record.msg}{self.NC}"
        return super().format(record)

def clean_flask_message(record):
    """
    Strip the 'IP - - [timestamp] ' preamble that Werkzeug adds, leaving
    the actual HTTP line intact.
    """
    if record.name.startswith(("werkzeug", "flask")):
        # record.msg looks like:
        # 127.0.0.1 - - [11/Jun/2025 16:37:01] "GET /api/status HTTP/1.1" 200 -
        record.msg = re.sub(
            r'^[0-9a-fA-F:.]+ - - \[[^\]]+\]\s*',  # IPv4 *or* IPv6, once
            '',
            record.getMessage(),
            count=1,
            flags=re.ASCII,
        ).strip()
        record.args = ()          # safety; Werkzeug doesn’t use %-style args
    return True

# Filter to remove ANSI color codes
def remove_ansi_codes(record):
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    if record.msg: record.msg = ansi_escape.sub('', str(record.msg))
    return True

def configure_logging(
    log_file_path: str,
    log_file: bool,
    log_console: bool,
    log_days: int = 7,
    Debug_logging: bool = False
) -> logging.Logger:
    """
    Configure the root logger with:
        • a TimedRotatingFileHandler (if log_file is True)
        • optional console output (if log_console is True)

    Args:
        log_file_path:   full path to the logfile (e.g. "/root/logs/viewport.log")
        log_file:        if True, enable file logging
        log_console:     if True, enable colored console output
        log_days:        how many days' worth of dated backups to keep
        Debug_logging:   if True, set level to DEBUG; otherwise INFO
    """
    logger = logging.getLogger()
    level = logging.DEBUG if Debug_logging else logging.INFO
    logger.setLevel(level)
    logger.propagate = False
    # If a handler for this file already exists, reuse it and exit.
    for h in logger.handlers:
        if isinstance(h, TimedRotatingFileHandler) and \
            Path(h.baseFilename) == Path(log_file_path):
            return logger
    # File formatter: [YYYY‐MM‐DD HH:MM:SS] [LEVEL] message
    file_fmt = logging.Formatter(f'[%(asctime)s] [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

    if log_file:
        file_handler = TimedRotatingFileHandler(
            filename    = log_file_path,
            when        = "midnight",
            interval    = 1,
            backupCount = log_days,
            encoding    = "utf-8",
            utc         = False,
            atTime      = dtime(0, 0),
        )
        file_handler.addFilter(remove_ansi_codes)
        # If the handler writes to viewport.log, keep monitoring noise out
        if Path(log_file_path).name == "viewport.log":
            viewport_filter = (
                lambda rec: not (
                    rec.name.startswith(("werkzeug", "flask", "monitoring"))
                    or "GET /api/" in rec.getMessage()          # safety-net for stray prints
                )
            )
            file_handler.addFilter(viewport_filter)
        if Path(log_file_path).name == "monitoring.log":
            file_handler.addFilter(lambda rec: rec.name.startswith(
                                        ("monitoring", "werkzeug", "flask")))
            file_handler.addFilter(clean_flask_message)
        file_handler.setLevel(logger.level)
        file_handler.setFormatter(file_fmt)
        logger.addHandler(file_handler)

    if log_console:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logger.level)
        console_handler.setFormatter(
            ColoredFormatter('[%(asctime)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        )
        logger.addHandler(console_handler)

    return logger