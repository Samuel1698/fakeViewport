from types import SimpleNamespace
import pytest
import viewport

@pytest.fixture(autouse=True)
def disable_external_side_effects(monkeypatch):
    # never actually sleep
    monkeypatch.setattr(viewport.time, "sleep", lambda *args, **kwargs: None)
    # never actually fork a process
    monkeypatch.setattr(viewport.subprocess, "Popen", lambda *args, **kwargs: None)

# --------------------------------------------------------------------------- # 
# Test api_handler function
# --------------------------------------------------------------------------- # 
class _FakeProcess:
    # Mimics the handful of attributes/behaviors api_handler relies on
    def __init__(self, *, exit_code=None, stdout_lines=None, stderr_lines=None):
        self._exit_code = exit_code                   # value returned by poll()
        self.returncode = exit_code                   # surfaced in the error msg
        self.stdout     = stdout_lines or []          # iterable for Thread‑target
        self.stderr     = stderr_lines or []

    def poll(self):
        return self._exit_code


class _DummyThread:
    # Replaces threading.Thread – runs the target *synchronously*
    started = 0

    def __init__(self, *, target=None, args=(), daemon=None):
        self._target = target
        self._args   = args

    def start(self):
        _DummyThread.started += 1
        if self._target: self._target(*self._args)

def _common_patches(monkeypatch):
    monkeypatch.setattr(viewport, "api_status", lambda *a, **k: None)

    import threading as _t
    monkeypatch.setattr(_t,             "Thread", _DummyThread)
    monkeypatch.setattr(viewport.threading, "Thread", _DummyThread)

    _DummyThread.started = 0          
def test_api_handler_already_running(monkeypatch):
    _common_patches(monkeypatch)
    # process_handler reports “monitoring.py” is alive
    monkeypatch.setattr(viewport, "process_handler", lambda *a, **k: True)

    # fail fast if api_handler ever tried to spawn a process
    monkeypatch.setattr(
        viewport.subprocess,
        "Popen",
        lambda *a, **k: pytest.fail("Popen must not be invoked when API is up"),
    )

    assert viewport.api_handler(standalone=True) is True
    assert _DummyThread.started == 0
    
def test_api_handler_starts_successfully(monkeypatch):
    _common_patches(monkeypatch)
    monkeypatch.setattr(viewport, "process_handler", lambda *a, **k: False)

    fake_proc = _FakeProcess(
        exit_code=None,                     # .poll() → None ⇒ still running
        stdout_lines=[
            "Serving Flask app\n",          # skipped by filter_output
            "Press CTRL+C to quit\n",       # skipped
            "Custom log line\n",            # logged
        ],
        stderr_lines=["Some warning\n"],
    )
    monkeypatch.setattr(viewport.subprocess, "Popen", lambda *a, **k: fake_proc)

    assert viewport.api_handler(standalone=True) is True
    # two filter threads (stdout + stderr) should have executed
    assert _DummyThread.started == 2
    
def test_api_handler_process_exits_early(monkeypatch):
    _common_patches(monkeypatch)
    monkeypatch.setattr(viewport, "process_handler", lambda *a, **k: False)

    fake_proc = _FakeProcess(exit_code=1)   # .poll() → 1 triggers RuntimeError
    monkeypatch.setattr(viewport.subprocess, "Popen", lambda *a, **k: fake_proc)

    assert viewport.api_handler(standalone=True) is False
    assert _DummyThread.started == 2        # threads still started
    
def test_api_handler_popen_raises(monkeypatch):
    _common_patches(monkeypatch)
    monkeypatch.setattr(viewport, "process_handler", lambda *a, **k: False)

    def _boom(*_a, **_kw):
        raise OSError("simulated failure")

    monkeypatch.setattr(viewport.subprocess, "Popen", _boom)

    assert viewport.api_handler() is False
    # Nothing spawned ⇒ no threads
    assert _DummyThread.started == 0

def test_api_handler_embedded_starts_without_threads(monkeypatch):
    """
    Exercise the `else: pass` branch (stand-alone = False).
    The child process is 'running', so the function should
    return True and spawn zero DummyThreads.
    """
    monkeypatch.setattr(viewport, "process_handler", lambda *a, **k: False)

    # dummy Popen that looks healthy
    class _DummyPopen:
        def __init__(self, *a, **k):
            self.stdout = None
            self.stderr = None
            self.returncode = None

        def poll(self):
            return None                 

    fake_proc = SimpleNamespace(
        Popen=_DummyPopen,
        PIPE=object(),
        DEVNULL=object(),
    )
    monkeypatch.setattr(viewport, "subprocess", fake_proc)

    monkeypatch.setattr(viewport.threading, "Thread", _DummyThread)

    # run & assert
    assert viewport.api_handler() is True          # standalone defaults to False
    assert _DummyThread.started == 0               # else-branch spawns none