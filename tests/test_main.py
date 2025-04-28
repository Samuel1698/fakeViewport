import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))
import logging
import logging.handlers
# stub out the rotating‐file handler before viewport.py ever sees it
logging.handlers.TimedRotatingFileHandler = lambda *args, **kwargs: logging.NullHandler()

from types import SimpleNamespace
from unittest.mock import MagicMock, patch, mock_open, ANY
import viewport

# -----------------------------------------------------------------------------
# Test main function
# -----------------------------------------------------------------------------
@patch("viewport.args_handler", return_value="continue")
@patch("viewport.process_handler")
@patch("viewport.api_handler")
@patch("viewport.api_status")
@patch("viewport.chrome_handler")
@patch("builtins.open", new_callable=mock_open)
@patch("viewport.threading.Thread")
def test_main_continue(
    mock_thread,
    mock_open_file,
    mock_chrome,
    mock_api_status,
    mock_api_handler,
    mock_process,
    mock_args
):
    # Arrange
    viewport.API = False
    # simulate missing or empty sst_file
    fake_sst = MagicMock()
    fake_sst.exists.return_value = False
    fake_sst.stat.return_value = SimpleNamespace(st_size=0)
    viewport.sst_file = fake_sst

    dummy_driver = object()
    mock_chrome.return_value = dummy_driver
    # Act
    viewport.main()
    # Assert args_handler was called
    mock_args.assert_called_once_with(viewport.args)
    # Should kill old viewport instance
    mock_process.assert_called_once_with('viewport.py', action="kill")
    # Because sst_file.exists() is False, we should open it once for writing
    mock_open_file.assert_called_once_with(viewport.sst_file, 'w')
    handle = mock_open_file()
    handle.write.assert_called_once()  # wrote the timestamp
    # Should launch chrome_handler
    mock_chrome.assert_called_once_with(viewport.url)
    # Should spawn a thread to run handle_view(driver, url)
    mock_thread.assert_called_once_with(
        target=viewport.handle_view,
        args=(dummy_driver, viewport.url)
    )
    mock_thread.return_value.start.assert_called_once()
    # api_handler() should NOT have been called (API=False)
    mock_api_handler.assert_not_called()
    # api_status("Starting...") should have been called
    mock_api_status.assert_called_with("Starting...")
@patch("viewport.args_handler", return_value="continue")
@patch("viewport.process_handler")
@patch("viewport.api_handler")
@patch("viewport.api_status")
@patch("viewport.chrome_handler")
@patch("builtins.open", new_callable=mock_open)
@patch("viewport.threading.Thread")
def test_main_continue_sst_exists(
    mock_thread,
    mock_open_file,
    mock_chrome,
    mock_api_status,
    mock_api_handler,
    mock_process,
    mock_args
):
    # Arrange
    viewport.API = False
    # simulate missing or empty sst_file
    fake_sst = MagicMock()
    fake_sst.exists.return_value = True
    fake_sst.stat.st_size = 1
    viewport.sst_file = fake_sst

    dummy_driver = object()
    mock_chrome.return_value = dummy_driver
    # Act
    viewport.main()
    # Assert args_handler was called
    mock_args.assert_called_once_with(viewport.args)
    # Should kill old viewport instance
    mock_process.assert_called_once_with('viewport.py', action="kill")
    # Because sst_file.exists() is True, we shouldn't open it
    mock_open_file.assert_not_called()
    # Should launch chrome_handler
    mock_chrome.assert_called_once_with(viewport.url)
    # Should spawn a thread to run handle_view(driver, url)
    mock_thread.assert_called_once_with(
        target=viewport.handle_view,
        args=(dummy_driver, viewport.url)
    )
    mock_thread.return_value.start.assert_called_once()
    # api_handler() should NOT have been called (API=False)
    mock_api_handler.assert_not_called()
    # api_status("Starting...") should have been called
    mock_api_status.assert_called_with("Starting...")

@patch("viewport.args_handler", return_value="something_else")
@patch("viewport.process_handler")
@patch("builtins.open", new_callable=mock_open)
@patch("viewport.chrome_handler")
@patch("viewport.threading.Thread")
def test_main_skip_when_not_continue(
    mock_thread,
    mock_chrome,
    mock_open_file,
    mock_process,
    mock_args
):
    viewport.main()
    # process_handler, chrome_handler, thread.start should never run
    mock_process.assert_not_called()
    mock_chrome.assert_not_called()
    mock_thread.assert_not_called()
# -----------------------------------------------------------------------------
# Test api_status function
# -----------------------------------------------------------------------------
def test_api_status_writes(tmp_path, monkeypatch):
    status_file = tmp_path / "status.txt"
    monkeypatch.setattr(viewport, "status_file", status_file)
    viewport.api_status("OKAY")
    assert status_file.read_text() == "OKAY"
# -----------------------------------------------------------------------------
# Test api_handler function
# -----------------------------------------------------------------------------
@patch("viewport.process_handler", return_value=False)
@patch("viewport.subprocess.Popen")
@patch("viewport.api_status")
def test_api_handler_starts_api(mock_api_status, mock_popen, mock_proc):
    # Arrange
    # ensure monitoring.py is not “running”
    viewport.api_handler()
    # Should spawn monitoring.py detached
    assert mock_popen.called
    mock_api_status.assert_called_with("Starting API...")

@patch("viewport.process_handler", return_value=False)
@patch("viewport.subprocess.Popen", side_effect=Exception("fail"))
@patch("viewport.log_error")
@patch("viewport.api_status")
def test_api_handler_failure(
    mock_api_status,
    mock_log_error,
    mock_popen,
    mock_proc
):
    viewport.api_handler()
    mock_log_error.assert_called_with("Error starting API: ", ANY)
    mock_api_status.assert_called_with("Error Starting API")

@patch("viewport.process_handler", return_value=True)
@patch("viewport.subprocess.Popen")
@patch("viewport.api_status")
def test_api_handler_already_running(mock_api_status, mock_popen, mock_proc):
    viewport.api_handler()
    mock_popen.assert_not_called()
    mock_api_status.assert_not_called()