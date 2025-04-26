import pytest
from unittest.mock import MagicMock, PropertyMock, patch
from selenium.common.exceptions import WebDriverException
import sys
from pathlib import Path

# Add the parent directory to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from viewport import (
    signal_handler,
    status_handler,
    process_handler,
    chrome_handler,
    chrome_restart_handler,
    restart_handler,
)
