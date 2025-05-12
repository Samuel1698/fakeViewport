import sys
import pytest
import viewport
from unittest.mock import patch, mock_open
@pytest.fixture(autouse=True)
def isolate_sst(tmp_path, monkeypatch):
    # redirect every test’s sst_file into tmp_path/…
    fake = tmp_path / "sst.txt"
    fake.write_text("2025-01-01 00:00:00.000000")  # or leave empty
    monkeypatch.setattr(viewport, "sst_file", fake)
@pytest.mark.parametrize("argv_flags", [
    ["--status", "--background"],       # Two arguments
    ["-r", "-l"],                       # Abbreviated version 
])
def test_only_one_argument_allowed(monkeypatch, argv_flags):
    # passing any two mutually-exclusive flags should error out at parse time
    monkeypatch.setattr(sys, "argv", ["viewport.py"] + argv_flags)
    with pytest.raises(SystemExit):
        viewport.args_helper()

@patch("viewport.sys.exit")
@patch("viewport.status_handler")
def test_status_flag(mock_status_handler, mock_exit):
    mock_args = type("Args", (), {
        "status": True, "logs": None, "background": False,
        "quit": False, "diagnose": False, "api": False, "restart": False
    })()
    viewport.args_handler(mock_args)
    mock_status_handler.assert_called_once()
    mock_exit.assert_called_once_with(1)

@patch("viewport.sys.exit")
@patch("viewport.open", new_callable=mock_open, read_data="[INFO] Something\n[WARNING] Be careful\n[ERROR] Uh oh\n")
def test_logs_flag(mock_file, mock_exit):
    mock_args = type("Args", (), {
        "status": False, "logs": 3, "background": False,
        "quit": False, "diagnose": False, "api": False, "restart": False
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
        "quit": False, "diagnose": False, "api": False, "restart": False
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
        "quit": True, "diagnose": False, "api": False, "restart": False
    })()
    viewport.args_handler(mock_args)
    mock_process_handler.assert_any_call("viewport.py", action="kill")
    mock_process_handler.assert_any_call(viewport.BROWSER, action="kill")
    mock_exit.assert_called_once_with(0)

@patch("viewport.sys.exit")
@patch("viewport.validate_config")
@patch("viewport.logging")
def test_diagnose_flag_success(mock_logging, mock_validate, mock_exit):
    mock_validate.return_value = True
    mock_args = type("Args", (), {
        "status": False, "logs": None, "background": False,
        "quit": False, "diagnose": True, "api": False, "restart": False
    })()

    viewport.args_handler(mock_args)

    mock_logging.info.assert_any_call("Checking validity of config.ini and .env variables...")
    mock_validate.assert_called_once_with(strict=False, print_errors=True)
    mock_logging.info.assert_any_call("No errors found.")
    mock_exit.assert_called_once_with(0)
    
@patch("viewport.sys.exit")
@patch("viewport.process_handler")
def test_api_flag_stop_monitoring(mock_process_handler, mock_exit):
    mock_process_handler.side_effect = lambda proc, action=None: True if proc == "monitoring.py" and action == "check" else None
    mock_args = type("Args", (), {
        "status": False, "logs": None, "background": False,
        "quit": False, "diagnose": False, "api": True, "restart": False
    })()
    viewport.args_handler(mock_args)
    assert mock_process_handler.call_count >= 2
    mock_exit.assert_called_once_with(0)

@patch("viewport.restart_handler")
@patch("viewport.logging.info")
def test_restart_flag(mock_log, mock_restart_handler):
    mock_args = type("Args", (), {
        "status": False, "logs": None, "background": False,
        "quit": False, "diagnose": False, "api": False, "restart": True
    })()
    result = viewport.args_handler(mock_args)
    mock_log.assert_called_once_with("Restarting the Fake Viewport script in the background")
    mock_restart_handler.assert_called_once_with(driver=None)
    assert result is None  # Because it does not hit the `return "continue"`

def test_no_arguments_passed():
    mock_args = type("Args", (), {
        "status": False, "logs": None, "background": False,
        "quit": False, "diagnose": False, "api": False, "restart": False
    })()
    result = viewport.args_handler(mock_args)
    assert result == "continue"

@pytest.mark.parametrize("flag", ["--backg", "--backgro", "--backgrou"])
def test_background_aliases_work(monkeypatch, flag):
    # any unambiguous prefix of --background still sets args.background=True
    monkeypatch.setattr(sys, "argv", ["viewport.py", flag])
    args = viewport.args_helper()
    assert args.background is True
    # all others default off
    assert not (args.status or args.restart or args.quit or args.api)
    assert args.logs is None

@pytest.mark.parametrize(
    "args_attrs, drop_flags, add_flags, expected",
    [
        # Drop api and logs, add --status
        (
            {"status": False, "background": False, "restart": False, "quit": False, "api": True,  "logs": 5},
            {"api", "logs"},
            {"status": None},
            ["--status"]
        ),
        # drop restart, add background
        (
            {"status": False, "background": False, "restart": True,  "quit": False, "diagnose": False, "api": False, "logs": None},
            {"restart"},
            {"background": None},
            ["--background"]
        ),
    ]
)
def test_args_child_handler_various_cases(args_attrs, drop_flags, add_flags, expected):
    # Build a dummy args object with the given attributes
    args = type("Args", (), args_attrs)()
    result = viewport.args_child_handler(args, drop_flags=drop_flags, add_flags=add_flags)
    assert result == expected