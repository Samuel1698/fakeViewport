import sys
import pytest
import viewport
import subprocess
from types import SimpleNamespace as Namespace
from unittest.mock import MagicMock, patch, mock_open
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
    mock_validate.assert_called_once_with(strict=False, print_errors=True, api=True)
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

def test_restart_flag(monkeypatch, caplog):
    # Prepare deterministic script path and python executable
    monkeypatch.setattr(viewport.os.path, "realpath", lambda p: "script.py")
    monkeypatch.setattr(sys, "executable", "/usr/bin/py")
    monkeypatch.setattr(sys, "argv", ["viewport.py"])

    # Stub out process_handler and subprocess.Popen
    fake_kill = MagicMock()
    monkeypatch.setattr(viewport, "process_handler", fake_kill)
    fake_popen = MagicMock()
    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    # Stub args_child_handler to include --background when requested
    def fake_args_child_handler(args, drop_flags, add_flags=None):
        parts = ["--child"]
        if add_flags and "background" in add_flags:
            parts.append("--background")
        return parts
    monkeypatch.setattr(viewport, "args_child_handler", fake_args_child_handler)

    # Create args with restart=True
    args = Namespace(
        status=False, logs=None, background=False,
        quit=False, diagnose=False, api=False, restart=True
    )

    # Run and expect it to exit
    with pytest.raises(SystemExit) as se:
        viewport.args_handler(args)
    assert se.value.code == 0

    # Check logged messages
    assert "Stopping existing Viewport instance for restart…" in caplog.text
    assert "Starting new Viewport instance in background…" in caplog.text

    # Verify the old daemon was killed
    fake_kill.assert_called_once_with("viewport.py", action="kill")

    # Verify a new background process was spawned correctly
    fake_popen.assert_called_once_with(
        ["/usr/bin/py", "script.py", "--child", "--background"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        start_new_session=True
    )
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
def test_args_child_handler_override_list_and_single_value():
    args = type("Args", (), {
        "status": False, "background": False, "restart": False,
        "quit": False, "diagnose": False, "api": False, "logs": None
    })()

    # 1) list‐style override ⇒ should extend exactly the list
    flags = viewport.args_child_handler(args, add_flags={"status": ["--status", "--extra"]})
    assert flags == ["--status", "--extra"]

    # 2) single‐value override ⇒ should produce ["--logs", "<value>"]
    flags2 = viewport.args_child_handler(args, add_flags={"logs": 42})
    assert flags2 == ["--logs", "42"]


def test_args_child_handler_override_none_value():
    args = type("Args", (), {
        "status": False, "background": False, "restart": False,
        "quit": False, "diagnose": False, "api": False, "logs": None
    })()

    # override None uses mapping tokens for known dest
    flags = viewport.args_child_handler(args, add_flags={"api": None})
    assert flags == ["--api"]

    # unknown dest falls back to "--<dest>"
    flags2 = viewport.args_child_handler(args, add_flags={"foo": None})
    assert flags2 == ["--foo"]


def test_args_child_handler_add_flags_as_list_or_tuple():
    args = type("Args", (), {
        "status": False, "background": False, "restart": False,
        "quit": False, "diagnose": False, "api": False, "logs": None
    })()

    # add_flags as list ⇒ triggers else-branch at line 198
    flags_list = viewport.args_child_handler(args, add_flags=["status", "foo"])
    # 'status' maps to ['--status'], 'foo' falls back to ['--foo']
    assert flags_list == ["--status", "--foo"]

    # same with tuple
    flags_tuple = viewport.args_child_handler(args, add_flags=("quit",))
    assert flags_tuple == ["--quit"]

@patch("viewport.sys.exit")
def test_logs_file_not_found(mock_exit):
    # Simulate open() raising FileNotFoundError in the logs branch
    mock_args = type("Args", (), {
        "status": False, "logs": 5, "background": False,
        "quit": False, "diagnose": False, "api": False, "restart": False
    })()
    with patch("viewport.open", side_effect=FileNotFoundError), \
         patch("viewport.print") as mock_print:
        viewport.args_handler(mock_args)
    mock_print.assert_called_once_with(
        f"{viewport.RED}Log file not found: {viewport.log_file}{viewport.NC}"
    )
    mock_exit.assert_called_once_with(0)

@patch("viewport.sys.exit")
@patch("viewport.log_error")
def test_logs_generic_exception(mock_log_error, mock_exit):
    # Simulate open() raising a generic Exception in the logs branch
    mock_args = type("Args", (), {
        "status": False, "logs": 2, "background": False,
        "quit": False, "diagnose": False, "api": False, "restart": False
    })()
    with patch("viewport.open", side_effect=Exception("oops")):
        viewport.args_handler(mock_args)
    mock_log_error.assert_called_once()
    # first arg to log_error should include our message
    err_msg = mock_log_error.call_args[0][0]
    assert "Error reading log file: oops" in err_msg
    mock_exit.assert_called_once_with(0)

@patch("viewport.sys.exit")
@patch("viewport.open", new_callable=mock_open, read_data="[DEBUG] debug message\n")
def test_logs_debug_flag(mock_file, mock_exit):
    mock_args = type("Args", (), {
        "status": False, "logs": 1, "background": False,
        "quit": False, "diagnose": False, "api": False, "restart": False
    })()
    with patch("viewport.print") as mock_print:
        viewport.args_handler(mock_args)
    # should strip the "[DEBUG]" and color via CYAN
    mock_print.assert_called_once_with(f"{viewport.CYAN}[DEBUG] debug message{viewport.NC}")
    mock_exit.assert_called_once_with(0)

@patch("viewport.sys.exit")
@patch("viewport.open", new_callable=mock_open, read_data="plain line without tag\n")
def test_logs_default_flag(mock_file, mock_exit):
    mock_args = type("Args", (), {
        "status": False, "logs": 1, "background": False,
        "quit": False, "diagnose": False, "api": False, "restart": False
    })()
    with patch("viewport.print") as mock_print:
        viewport.args_handler(mock_args)
    # no INFO/WARNING/DEBUG/ERROR ⇒ falls back to NC…NC
    mock_print.assert_called_once_with(f"{viewport.NC}plain line without tag{viewport.NC}")
    mock_exit.assert_called_once_with(0)

@patch("viewport.sys.exit")
@patch("viewport.logging.info")
def test_api_flag_disabled(mock_info, mock_exit):
    # Simulate args.api=True but no monitoring process and API flag off
    mock_args = type("Args", (), {
        "status": False, "logs": None, "background": False,
        "quit": False, "diagnose": False, "api": True, "restart": False
    })()
    # ensure process_handler returns False for monitoring.py check
    with patch("viewport.process_handler", return_value=False):
        viewport.API = False
        viewport.args_handler(mock_args)
    mock_info.assert_any_call(
        "API is not enabled in config.ini. Please set USE_API=True and restart script to use this feature."
    )
    mock_exit.assert_called_once_with(0)