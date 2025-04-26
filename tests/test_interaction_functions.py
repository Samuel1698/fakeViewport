import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

import pytest
import viewport
from unittest.mock import MagicMock, PropertyMock, patch
from selenium.common.exceptions import WebDriverException