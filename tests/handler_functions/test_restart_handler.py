import os
import sys
import subprocess
import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import viewport

class DummyDriver:
    def __init__(self):
        self.quit = MagicMock()
@pytest.fixture(autouse=True)
def isolate_sst(tmp_path, monkeypatch):
    # redirect every test’s sst_file into tmp_path/
    fake = tmp_path / "sst.txt"
    fake.write_text("2025-01-01 00:00:00.000000")  # or leave empty
    monkeypatch.setattr(viewport, "sst_file", fake)
@pytest.fixture
def patch_time_and_paths(monkeypatch):
    # No actual sleep
    monkeypatch.setattr(viewport.time, "sleep", lambda s: None)
    # Make script_path reproducible
    monkeypatch.setattr(viewport.os.path, "realpath", lambda p: "script.py")
    # Control python executable and argv
    monkeypatch.setattr(sys, "executable", "/usr/bin/py")
    monkeypatch.setattr(sys, "argv", ["script.py"])

@pytest.fixture
def patch_args_and_api(monkeypatch):
    # Stub out argument helpers
    monkeypatch.setattr(viewport, "args_helper", lambda: "ARGS")
    monkeypatch.setattr(viewport, "args_child_handler", lambda args, drop_flags: ["--child"])
    # Spy on api_status
    monkeypatch.setattr(viewport, "api_status", MagicMock())
# ----------------------------------------------------------------------------- 
# Tests for restart_handler
# ----------------------------------------------------------------------------- 
@pytest.mark.parametrize("initial_argv, driver_present, expected_flags", [
    # No flags          ⇒ no extra flags
    (["viewport.py"],                         False, []),
    # background flags  ⇒ preserved
    (["viewport.py", "-b"],                   False, ["--background"]),
    (["viewport.py", "--background"],         False, ["--background"]),
    (["viewport.py", "--backg"],              False, ["--background"]),
    # restart flags     ⇒ removed
    (["viewport.py", "-r"],                   False, []),
    (["viewport.py", "--restart"],            False, []),
    (["viewport.py", "--rest"],               False, []),
    # driver present    ⇒ quit()
    (["viewport.py", "--restart"],            True,  []),
])
@patch("viewport.sys.exit")
@patch("viewport.subprocess.Popen")
@patch("viewport.time.sleep", return_value=None)
@patch("viewport.api_status")
def test_restart_handler(
    mock_api_status,
    mock_sleep,
    mock_popen,
    mock_exit,
    initial_argv,
    driver_present,
    expected_flags
):
    # Arrange: set up sys.argv and optional driver
    viewport.sys.argv = list(initial_argv)
    driver = MagicMock() if driver_present else None
    
    # Act
    viewport.restart_handler(driver)

    # Assert: status update and sleep
    mock_api_status.assert_called_once_with("Restarting script...")
    mock_sleep.assert_called_once_with(2)

    # Assert: driver.quit() only if driver was passed
    if driver_present:
        driver.quit.assert_called_once()
    else:
        # ensure we didn't mistakenly call .quit()
        assert not getattr(driver, "quit", MagicMock()).called

    # Assert: Popen called exactly once with correct args
    expected_cmd = [sys.executable, viewport.__file__] + expected_flags
    mock_popen.assert_called_once_with(
        expected_cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        start_new_session=True,
    )

    # Assert: parent exits with code 0
    mock_exit.assert_called_once_with(0)
# ----------------------------------------------------------------------------- 
# Error‐flow: make subprocess.Popen throw ⇒ log_error, api_status, clear_sst, sys.exit(1)
# ----------------------------------------------------------------------------- 
@patch("viewport.api_status")
@patch("viewport.time.sleep", return_value=None)
@patch("viewport.args_child_handler", side_effect=RuntimeError("boom"))
@patch("viewport.args_helper", return_value=SimpleNamespace())
@patch("viewport.clear_sst")
@patch("viewport.log_error")
@patch("viewport.subprocess.Popen")
@patch("os.path.realpath", return_value="/fake/script.py")
def test_restart_handler_exception(
    mock_realpath,
    mock_popen,
    mock_log_error,
    mock_clear_sst,
    mock_args_helper,
    mock_args_child,
    mock_sleep,
    mock_api_status,
):
    # make Popen never even get called because args_child_handler blows up
    mock_popen.side_effect = AssertionError("should not reach popen")
    with pytest.raises(SystemExit) as exc:
        viewport.restart_handler(None)

    # exit code should be 1
    assert exc.value.code == 1

    # log_error should have been called with our exception
    assert mock_log_error.call_count == 1
    args, kwargs = mock_log_error.call_args
    assert "Error during restart process:" in args[0]
    assert isinstance(args[1], RuntimeError)

    # API should have been called to report the failure
    mock_api_status.assert_any_call("Error Restarting, exiting...")

    # clear_sst must have run and slept 2 seconds
    mock_clear_sst.assert_called_once()
    mock_sleep.assert_called_once_with(2)
    # no popen on error
    mock_popen.assert_not_called()

def test_restart_handler_exec_replace_failure(monkeypatch,
                                            patch_time_and_paths,
                                            patch_args_and_api):
    # Simulate interactive terminal
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)

    # Make execv throw, so we exercise the exception branch
    def bad_execv(exe, argv):
        raise RuntimeError("execv failed")
    monkeypatch.setattr(os, "execv", bad_execv)

    # Spy on log_error and clear_sst
    fake_log_error = MagicMock()
    fake_clear_sst = MagicMock()
    monkeypatch.setattr(viewport, "log_error", fake_log_error)
    monkeypatch.setattr(viewport, "clear_sst", fake_clear_sst)

    driver = DummyDriver()
    with pytest.raises(SystemExit) as se:
        viewport.restart_handler(driver)

    # It should exit with code 1
    assert se.value.code == 1

    # It should have shut down the driver
    driver.quit.assert_called_once()

    # And logged the error, updated the API, and cleared SST
    fake_log_error.assert_called_once()
    viewport.api_status.assert_called_with("Error Restarting, exiting...")
    fake_clear_sst.assert_called_once()

def test_restart_handler_detach(monkeypatch,
                                patch_time_and_paths,
                                patch_args_and_api):
    # Simulate background (no TTY)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: False)

    fake_popen = MagicMock()
    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr(sys, "exit", lambda code=0: (_ for _ in ()).throw(SystemExit(code)))
    driver = DummyDriver()
    with pytest.raises(SystemExit) as se:
        viewport.restart_handler(driver)

    # detach path always exits 0
    assert se.value.code == 0
    driver.quit.assert_called_once()
    viewport.api_status.assert_called_with("Restarting script...")
    fake_popen.assert_called_once()
    args, kwargs = fake_popen.call_args
    assert args[0] == ["/usr/bin/py", "script.py", "--child"]
    assert kwargs["stdin"]  == subprocess.DEVNULL
    assert kwargs["stdout"] == subprocess.DEVNULL
    assert kwargs["stderr"] == subprocess.DEVNULL
    assert kwargs["close_fds"]         is True
    assert kwargs["start_new_session"] is True