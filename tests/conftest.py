# tests/conftest.py
import sys
import pytest

from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

import logging
import logging.handlers
# stub out the rotating‐file handler before viewport.py ever sees it
logging.handlers.TimedRotatingFileHandler = lambda *args, **kwargs: logging.NullHandler()
