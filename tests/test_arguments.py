import sys
import pytest
import viewport
import subprocess
from types import SimpleNamespace as Namespace
from unittest.mock import MagicMock, patch, mock_open, call

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
        "status": True, "logs": None, "background": False, "pause": False,
        "quit": False, "diagnose": False, "api": False, "restart": False
    })()
    viewport.args_handler(mock_args)
    mock_status_handler.assert_called_once()
    mock_exit.assert_called_once_with(1)

@patch("viewport.sys.exit")
@patch("viewport.open", new_callable=mock_open, read_data="[INFO] Something\n[WARNING] Be careful\n[ERROR] Uh oh\n")
def test_logs_flag(mock_file, mock_exit):
    mock_args = type("Args", (), {
        "status": False, "logs": 3, "background": False, "pause": False,
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
        "status": False, "logs": None, "background": True, "pause": False,
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
        "status": False, "logs": None, "background": False, "pause": False,
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
        "status": False, "logs": None, "background": False, "pause": False,
        "quit": False, "diagnose": True, "api": False, "restart": False
    })()

    viewport.args_handler(mock_args)

    mock_logging.info.assert_any_call("Checking validity of config.ini and .env variables...")
    mock_validate.assert_called_once_with(strict=False)
    mock_logging.info.assert_any_call("No errors found.")
    mock_exit.assert_called_once_with(0)
    
@patch("viewport.sys.exit")
@patch("viewport.process_handler")
def test_api_flag_stop_monitoring(mock_process_handler, mock_exit):
    mock_process_handler.side_effect = lambda proc, action=None: True if proc == "monitoring.py" and action == "check" else None
    mock_args = type("Args", (), {
        "status": False, "logs": None, "background": False, "pause": False,
        "quit": False, "diagnose": False, "api": True, "restart": False
    })()
    viewport.args_handler(mock_args)
    assert mock_process_handler.call_count >= 2
    mock_exit.assert_called_once_with(0)
    
@patch("viewport.sys.exit")
def test_args_handler_api_enabled_calls_api_handler(mock_exit, monkeypatch):
    # Simulate “monitoring.py” not running, so we skip the stop‐monitoring branch:
    monkeypatch.setattr(viewport, "process_handler", lambda proc, action=None: False)

    # Force the config‐loaded API flag to True
    monkeypatch.setattr(viewport, "API", True)

    # Spy on api_handler
    called = {}
    monkeypatch.setattr(viewport, "api_handler", lambda: called.setdefault("api", True))

    # Build args with api=True
    args = Namespace(
        status=False, logs=None, background=False, pause=False,
        quit=False, diagnose=False, api=True, restart=False
    )

    # Act
    viewport.args_handler(args)

    # Assert: we hit the API branch, called api_handler(), then sys.exit(0)
    mock_exit.assert_called_once_with(0)
    assert called.get("api") is True

@patch("viewport.sys.exit")
def test_args_handler_api_disabled_logs_message(mock_exit, monkeypatch, caplog):
    # Simulate “monitoring.py” not running, so we skip the stop‐monitoring branch:
    monkeypatch.setattr(viewport, "process_handler", lambda proc, action=None: False)

    # Force API flag to False
    monkeypatch.setattr(viewport, "API", False)

    # Capture INFO‐level logs
    caplog.set_level("INFO")

    args = Namespace(
        status=False, logs=None, background=False, pause=False,
        quit=False, diagnose=False, api=True, restart=False
    )

    # Act
    viewport.args_handler(args)

    # Assert: logged the “not enabled” message, then exit(0)
    mock_exit.assert_called_once_with(0)
    assert any(
        "API is not enabled in config.ini" in rec.message
        for rec in caplog.records
    )
     
def test_restart_flag_when_running(monkeypatch, caplog):
    monkeypatch.setattr(viewport.os.path, "realpath", lambda p: "script.py")
    monkeypatch.setattr(sys, "executable", "/usr/bin/py")
    monkeypatch.setattr(sys, "argv", ["viewport.py"])
    # Arrange: process_handler.check returns True → simulate a running daemon
    fake_proc = MagicMock(return_value=True)
    monkeypatch.setattr(viewport, "process_handler", fake_proc)

    # Spy on Popen
    fake_popen = MagicMock()
    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    # Stub args_child_handler to include --background
    monkeypatch.setattr(
        viewport,
        "args_child_handler",
        lambda args, drop_flags, add_flags=None: ["--child"] + (["--background"] if add_flags else [])
    )

    args = Namespace(
        status=False, logs=None, background=False, pause=False,
        quit=False, diagnose=False, api=False, restart=True
    )

    # Act & Assert: SystemExit(0)
    with pytest.raises(SystemExit) as se:
        viewport.args_handler(args)
    assert se.value.code == 0

    # It should first check, then kill
    fake_proc.assert_has_calls([
        call("viewport.py", action="check"),
    ])
    assert fake_proc.call_count == 1

    # It should spawn exactly one background process
    fake_popen.assert_called_once_with(
        ["/usr/bin/py", "script.py", "--child", "--background"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        start_new_session=True,
    )

def test_restart_flag_when_not_running(monkeypatch, caplog):
    monkeypatch.setattr(viewport.os.path, "realpath", lambda p: "script.py")
    monkeypatch.setattr(sys, "executable", "/usr/bin/py")
    monkeypatch.setattr(sys, "argv", ["viewport.py"])
    # Arrange: process_handler.check returns False → simulate no daemon
    fake_proc = MagicMock(return_value=False)
    monkeypatch.setattr(viewport, "process_handler", fake_proc)

    fake_popen = MagicMock()
    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    args = Namespace(
        status=False, logs=None, background=False, pause=False,
        quit=False, diagnose=False, api=False, restart=True
    )

    # Act & Assert: SystemExit(0)
    with pytest.raises(SystemExit) as se:
        viewport.args_handler(args)
    assert se.value.code == 0

    # Only the check call, no kill
    fake_proc.assert_called_once_with("viewport.py", action="check")

    # No background spawn
    fake_popen.assert_not_called()

    # Verify log message
    assert "Fake Viewport is not running." in caplog.text
    
def test_no_arguments_passed():
    mock_args = type("Args", (), {
        "status": False, "logs": None, "background": False, "pause": False,
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
            {"status": False, "background": False, "pause": False, "restart": False, "quit": False, "api": True,  "logs": 5},
            {"api", "logs"},
            {"status": None},
            ["--status"]
        ),
        # drop restart, add background
        (
            {"status": False, "background": False, "pause": False, "restart": True,  "quit": False, "diagnose": False, "api": False, "logs": None},
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
        "status": False, "background": False, "pause": False, "restart": False,
        "quit": False, "diagnose": False, "api": False, "logs": None
    })()

    # list‐style override ⇒ should extend exactly the list
    flags = viewport.args_child_handler(args, add_flags={"status": ["--status", "--extra"]})
    assert flags == ["--status", "--extra"]

    # single‐value override ⇒ should produce ["--logs", "<value>"]
    flags2 = viewport.args_child_handler(args, add_flags={"logs": 42})
    assert flags2 == ["--logs", "42"]


def test_args_child_handler_override_none_value():
    args = type("Args", (), {
        "status": False, "background": False, "pause": False, "restart": False,
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
        "status": False, "background": False, "pause": False, "restart": False,
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
        "status": False, "logs": 5, "background": False, "pause": False,
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
        "status": False, "logs": 2, "background": False, "pause": False,
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
        "status": False, "logs": 1, "background": False, "pause": False,
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
        "status": False, "logs": 1, "background": False, "pause": False,
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
        "status": False, "logs": None, "background": False, "pause": False,
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
    
def test_pause_flag_when_not_running(monkeypatch, caplog):
    # Simulate viewport not running
    monkeypatch.setattr(viewport, "process_handler", lambda name, action: False)

    args = Namespace(
        status=False, logs=None, background=False, pause=True,
        quit=False, diagnose=False, api=False, restart=False
    )

    with pytest.raises(SystemExit):
        viewport.args_handler(args)

    # Should log that nothing was running, and not touch the pause file
    assert "Fake Viewport is not running." in caplog.text
    assert not viewport.pause_file.exists()

@pytest.mark.parametrize("initial, expected_msg, expected_status", [
    (False, "Pausing health checks.",  "Paused"),
    (True,  "Resuming health checks.", "Resumed"),
])
def test_pause_flag_toggle(monkeypatch, caplog, initial, expected_msg, expected_status):
    # Simulate viewport *is* running
    monkeypatch.setattr(viewport, "process_handler", lambda name, action: True)

    # Set up the .pause file in its initial state
    pf = viewport.pause_file
    if initial:
        pf.touch()
    else:
        if pf.exists(): pf.unlink()

    args = Namespace(
        status=False, logs=None, background=False, pause=True,
        quit=False, diagnose=False, api=False, restart=False
    )

    with pytest.raises(SystemExit):
        viewport.args_handler(args)

    # Check the right log and status
    assert expected_msg in caplog.text
    assert viewport.status_file.read_text() == expected_status

    # And that the file was toggled
    assert viewport.pause_file.exists() == (not initial)
    

def test_pause_flag_exception_branch(monkeypatch):
    # Make process_handler raise, to force the exception path
    def fake_process_handler(name, action):
        raise RuntimeError("oh no")
    monkeypatch.setattr(viewport, "process_handler", fake_process_handler)

    # Capture calls to log_error
    caught = []
    monkeypatch.setattr(viewport, "log_error", lambda msg, err: caught.append((msg, err)))

    # Build args with --pause
    args = Namespace(
        status=False, logs=None, background=False, pause=True,
        quit=False, diagnose=False, api=False, restart=False
    )

    # Calling args_handler should sys.exit(0) after catching our error
    with pytest.raises(SystemExit) as se:
        viewport.args_handler(args)
    assert se.value.code == 0

    # Ensure we hit the exception branch
    assert len(caught) == 1
    msg, err = caught[0]
    assert msg == "Error toggling pause state:"
    assert isinstance(err, RuntimeError)
    assert err.args[0] == "oh no"