import psutil
import signal
import pytest
import viewport
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, call

# helper to build a fake psutil.Process‐like object
def _make_proc(pid, cmdline, uids=None, name=None, cpu: float = 0.0, mem: int = 0):
    # pid: process ID
    # cmdline: either a list of strings or a single binary name
    # uids: optionally a SimpleNamespace(real=<uid>) for ownership filtering
    # name: override process.info['name']
    # cpu: what cpu_percent(interval) should return
    # mem: what memory_info().rss should return

    # Normalize cmdline to list and derive default name
    if isinstance(cmdline, str):
        cmd = [cmdline]
    else:
        cmd = list(cmdline) if cmdline is not None else []
    default_name = cmd[0] if cmd else f"proc{pid}"
    proc_name = name or default_name

    # Build info dict
    info = {
        "pid": pid,
        "cmdline": cmd,
        "uids": uids or SimpleNamespace(real=1000),
        "name": proc_name,
    }

    # Create the MagicMock and attach methods
    proc = MagicMock()
    proc.info = info
    proc.cpu_percent.return_value = cpu
    proc.memory_info.return_value = MagicMock(rss=mem)
    return proc

# ----------------------------------------------------------------------------- 
# Test for Process Handler
# ----------------------------------------------------------------------------- 
@pytest.mark.parametrize(
    "proc_list, current_pid, name, action, expected_result, expected_kill_calls, expected_api_calls, expected_log_info",
    [
        # Process Running
        # Current PID, Name to, Check, Exists?
        # Expected Kill Calls, Expected API Calls

        # No process, 'viewport', check, Not Present
        (
            [], 
            100, "viewport.py", "check", False, 
            [], [], []
        ),

        # Only Self Viewport Process running
        # 'viewport', 'check', Should be False
        (
            [_make_proc(100, ["viewport.py"])],
            100, "viewport.py", "check", False, 
            [], [], []
        ),

        # Different Viewport Process running
        # 'viewport', 'check', Should be True
        (
            [_make_proc(1, ["python", "viewport.py"])],
            100, "viewport.py", "check", True, 
            [], [], []
        ),

        # Different commandline process with argument
        # 'viewport', 'check', Should be True
        (
            [_make_proc(10, ["/usr/bin/viewport.py", "--foo"])], 
            0, "viewport.py", "check", True, 
            [], [], []
        ),

        # No Process Running = None to kill
        # 'viewport', 'kill', Should be False
        (
            [], 
            200, "viewport.py", "kill", False, 
            [], [], []
        ),

        # Only Self Viewport Process Runnning = Do not Kill
        # 'viewport', 'kill', Should be False
        (
            [_make_proc(200, ["viewport.py"])], 
            200, "viewport.py", "kill", False, 
            [], [], []
        ),

        # Chrome Processes (2, 3) running in backgrond
        # 'chrome', 'kill', If killed should return False
        # Process 2 and 3 gets SIGTERM, API Call should be:
        (
            [_make_proc(2, ["chrome"]),
             _make_proc(3, ["chrome"])], 
            999, "chrome", "kill", False,
            [(2, signal.SIGKILL), (3, signal.SIGKILL)], ["Killed process 'chrome'"], ["Killed process 'chrome' with PIDs: 2, 3"]
        ),

        # Chromium Process (2, 3) running in backgrond
        # 'chromium', 'kill', If killed should return False
        # Process 2 and 3 get SIGKILL, API Call should be:
        (
            [_make_proc(2, ["chromium"]),
             _make_proc(3, ["chromium"])], 
            999, "chromium", "kill", False,
            [(2, signal.SIGKILL), (3, signal.SIGKILL)], ["Killed process 'chromium'"], ["Killed process 'chromium' with PIDs: 2, 3"]
        ),

        # Multiple viewport instances running in background, separate from current instance
        # 'viewport', 'kill', If killed should return False
        # Process 2 and 3 get SIGKILL, API Call should be:
        (   
            [_make_proc(2, ["viewport.py"]),
             _make_proc(3, ["viewport.py"]),
             _make_proc(4, ["other"])], 
            999, "viewport.py", "kill", False,
            [(2, signal.SIGKILL), (3, signal.SIGKILL)], ["Killed process 'viewport.py'"], ["Killed process 'viewport.py' with PIDs: 2, 3"]
        ),
        # One other viewport instance running in background
        # 'viewport', 'kill', If killed should return False
        # Process 2, API Call should be:
        (   
            [_make_proc(2, ["viewport.py"]),
             _make_proc(3, ["other"])], 
            999, "viewport.py", "kill", False,
            [(2, signal.SIGKILL)], ["Killed process 'viewport.py'"], ["Killed process 'viewport.py' with PIDs: 2"]
        ),
        # Firefox main + root-owned helper: should kill only the main (uid == me)
        (
            [
                # main firefox, owned by us
                _make_proc(2, ["firefox"], uids=SimpleNamespace(real=1000)),
                # helper, owned by root → should be ignored
                _make_proc(3, ["firefox"], uids=SimpleNamespace(real=0)),
            ],
            999, "firefox", "kill", False,
            # only pid 2 gets SIGKILL
            [(2, signal.SIGKILL)],
            # api_status should be called with this message
            ["Killed process 'firefox'"],
            # logging.info with this
            ["Killed process 'firefox' with PIDs: 2"]
        ),
    ]
)
@patch("viewport.logging.info")
@patch("viewport.psutil.process_iter")
@patch("viewport.os.geteuid")
@patch("viewport.os.getpid")
@patch("viewport.os.kill")
@patch("viewport.api_status")
def test_process_handler(
    mock_api, mock_kill, mock_getpid, mock_geteuid, mock_iter, mock_log_info,
    proc_list, current_pid, name, action,
    expected_result, expected_kill_calls, expected_api_calls, expected_log_info
):
    # arrange
    mock_geteuid.return_value = 1000
    mock_iter.return_value = iter(proc_list)
    mock_getpid.return_value = current_pid

    # act
    result = viewport.process_handler(name, action=action)

    # assert return value
    assert result is expected_result

    # assert os.kill calls
    if expected_kill_calls:
        assert mock_kill.call_count == len(expected_kill_calls)
        for pid, sig in expected_kill_calls:
            mock_kill.assert_any_call(pid, sig)
    else:
        mock_kill.assert_not_called()
    
    # Assert logging.info calls
    if expected_log_info:
        for msg in expected_log_info:
            mock_log_info.assert_any_call(msg)
    else:
        mock_log_info.assert_not_called()
    # assert api_status calls
    if expected_api_calls:
        assert mock_api.call_args_list == [call(msg) for msg in expected_api_calls]
    else:
        mock_api.assert_not_called()

# -----------------------------------------------------------------------------
# Cover the psutil.NoSuchProcess / AccessDenied path in the loop
# -----------------------------------------------------------------------------
@patch("viewport.psutil.process_iter")
def test_process_handler_ignores_uninspectable_procs(mock_iter):
    class BadProc:
        @property
        def info(self):
            # simulate a process that disappears or denies access
            raise psutil.NoSuchProcess(pid=123)
    mock_iter.return_value = iter([BadProc()])
    # should swallow and return False (no matches)
    assert viewport.process_handler("anything", action="check") is False

    # also cover AccessDenied
    class DeniedProc:
        @property
        def info(self):
            raise psutil.AccessDenied(pid=456)
    mock_iter.return_value = iter([DeniedProc()])
    assert viewport.process_handler("anything", action="check") is False

# ----------------------------------------------------------------------------- 
# Cover the ProcessLookupError inside the kill loop
# ----------------------------------------------------------------------------- 
@patch("viewport.os.kill")
@patch("viewport.os.getpid", return_value=0)
@patch("viewport.os.geteuid", return_value=1000)
@patch("viewport.psutil.process_iter")
@patch("viewport.api_status")
@patch("viewport.logging.info")
@patch("viewport.logging.warning")
def test_process_handler_kill_handles_processlookuperror(
    mock_warn, mock_info, mock_api, mock_iter,
    mock_geteuid, mock_getpid, mock_kill
):
    # one matching process
    proc = MagicMock()
    proc.info = {
        "pid": 99,
        "name": "foo",
        "uids": SimpleNamespace(real=1000),
        "cmdline": ["foo"],
    }
    mock_iter.return_value = iter([proc])

    # raise ProcessLookupError on kill
    mock_kill.side_effect = ProcessLookupError

    # kill action
    result = viewport.process_handler("foo", action="kill")
    assert result is False

    # ensure kill was attempted
    mock_kill.assert_called_once_with(99, signal.SIGKILL)
    # ensure warning logged
    mock_warn.assert_called_once_with("Process 99 already gone")
    # ensure we still log info about having 'killed' it
    mock_info.assert_called_once_with("Killed process 'foo' with PIDs: 99")
    # ensure API was still notified
    mock_api.assert_called_once_with("Killed process 'foo'")
    
# -----------------------------------------------------------------------------
# Cover the catch-all Exception path
# -----------------------------------------------------------------------------
@patch("viewport.api_status")
@patch("viewport.log_error")
@patch("viewport.os.geteuid", side_effect=RuntimeError("oh no"))
def test_process_handler_catches_unexpected(mock_geteuid, mock_log_error, mock_api):
    # When get_euid blows up, we should hit the catch-all
    result = viewport.process_handler("myproc", action="check")
    assert result is False

    # log_error should be called with the right message and the exception
    mock_log_error.assert_called_once()
    msg, exc = mock_log_error.call_args[0]
    assert "Error while checking process 'myproc'" in msg
    assert isinstance(exc, RuntimeError)
    assert str(exc) == "oh no"

    # api_status should be notified too
    mock_api.assert_called_once_with("Error Checking Process 'myproc'")