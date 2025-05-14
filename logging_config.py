import logging
from logging.handlers import TimedRotatingFileHandler

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

def configure_logging(
    log_file_path: str,
    log_file: bool,
    log_console: bool,
    log_days: int = 7,
    Debug_logging: bool = False
) -> logging.Logger:
    """
    Configure the root logger with:
      • timed-rotating file handler (if log_file is True)
      • colored console output    (if log_console is True)

    Args:
        log_file_path:    where to write the logfile
        log_file:         enable file logging
        log_console:      enable console logging
        log_days:         how many days to retain file logs
        debug_logging:    if True, set level to DEBUG; else INFO
    """
    logger = logging.getLogger()
    level = logging.DEBUG if Debug_logging else logging.INFO
    logger.setLevel(level)

    # Formatter for file handler
    file_fmt = logging.Formatter(f'[%(asctime)s] [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

    if log_file:
        file_handler = TimedRotatingFileHandler(
            log_file_path,
            when='D',
            interval=1,
            backupCount=log_days
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(file_fmt)
        logger.addHandler(file_handler)

    if log_console:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(
            ColoredFormatter(
                '[%(asctime)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S'
            )
        )
        logger.addHandler(console_handler)

    return logger