import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from unittest.mock import patch, mock_open
import viewport

@patch("viewport.sys.exit")
@patch("viewport.status_handler")
def test_status_flag(mock_status_handler, mock_exit):
  mock_args = type("Args", (), {
      "status": True, "logs": None, "background": False,
      "quit": False, "api": False, "restart": False
  })()
  viewport.args_handler(mock_args)
  mock_status_handler.assert_called_once()
  mock_exit.assert_called_once_with(1)

@patch("viewport.sys.exit")
@patch("viewport.open", new_callable=mock_open, read_data="[INFO] Something\n[WARNING] Be careful\n[ERROR] Uh oh\n")
def test_logs_flag(mock_file, mock_exit):
  mock_args = type("Args", (), {
      "status": False, "logs": 3, "background": False,
      "quit": False, "api": False, "restart": False
  })()
  with patch("viewport.print") as mock_print:
      viewport.args_handler(mock_args)
      mock_exit.assert_called_once_with(0)
      assert mock_print.call_count == 3

@patch("viewport.sys.exit")
@patch("viewport.subprocess.Popen")
@patch("viewport.logging.info")
def test_background_flag(mock_log, mock_popen, mock_exit):
  mock_args = type("Args", (), {
      "status": False, "logs": None, "background": True,
      "quit": False, "api": False, "restart": False
  })()
  viewport.args_handler(mock_args)
  mock_log.assert_called_once_with("Starting the script in the background...")
  mock_popen.assert_called_once()
  mock_exit.assert_called_once_with(0)

@patch("viewport.sys.exit")
@patch("viewport.process_handler")
def test_quit_flag(mock_process_handler, mock_exit):
  mock_args = type("Args", (), {
      "status": False, "logs": None, "background": False,
      "quit": True, "api": False, "restart": False
  })()
  viewport.args_handler(mock_args)
  mock_process_handler.assert_any_call("viewport.py", action="kill")
  mock_process_handler.assert_any_call("chrome", action="kill")
  mock_exit.assert_called_once_with(0)

@patch("viewport.sys.exit")
@patch("viewport.process_handler")
def test_api_flag_stop_monitoring(mock_process_handler, mock_exit):
  mock_process_handler.side_effect = lambda proc, action=None: True if proc == "monitoring.py" and action == "check" else None
  mock_args = type("Args", (), {
      "status": False, "logs": None, "background": False,
      "quit": False, "api": True, "restart": False
  })()
  viewport.args_handler(mock_args)
  assert mock_process_handler.call_count >= 2
  mock_exit.assert_called_once_with(0)

@patch("viewport.restart_handler")
@patch("viewport.logging.info")
def test_restart_flag(mock_log, mock_restart_handler):
  mock_args = type("Args", (), {
      "status": False, "logs": None, "background": False,
      "quit": False, "api": False, "restart": True
  })()
  result = viewport.args_handler(mock_args)
  mock_log.assert_called_once_with("Restarting the Fake Viewport script...")
  mock_restart_handler.assert_called_once_with(driver=None)
  assert result is None  # Because it does not hit the `return "continue"`

def test_no_arguments_passed():
  mock_args = type("Args", (), {
      "status": False, "logs": None, "background": False,
      "quit": False, "api": False, "restart": False
  })()
  result = viewport.args_handler(mock_args)
  assert result == "continue"