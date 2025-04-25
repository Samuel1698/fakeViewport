import pytest
from unittest.mock import MagicMock, PropertyMock, patch
from selenium.common.exceptions import WebDriverException
import sys
from pathlib import Path

# Add the parent directory to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from viewport import (
  handle_elements,
  handle_loading_issue,
  handle_fullscreen_button,
  handle_login,
  handle_page,
  handle_retry,
  handle_view
)