import pytest
import types
import monitoring
from unittest.mock import patch, MagicMock

class DummyApp:
    def __init__(self):
        self.run_called = False
        self.run_args = None

    def run(self, host, port):
        self.run_called = True
        self.run_args = (host, port)

def test_main_with_valid_config(monkeypatch):
    # Stub out process_handler so that it always returns False (i.e. "no existing process")
    monkeypatch.setattr(monitoring, "process_handler", lambda name, action: False)

    fake_cfg = types.SimpleNamespace(host="1.2.3.4", port=2500)
    monkeypatch.setattr(monitoring, "validate_config", lambda *a, **k: fake_cfg)

    dummy = DummyApp()
    monkeypatch.setattr(monitoring, "create_app", lambda: dummy)

    # Should not raise, and should call DummyApp.run(host, port)
    monitoring.main()

    assert dummy.run_called is True
    assert dummy.run_args == ("1.2.3.4", 2500)

def test_main_with_missing_host_port(monkeypatch):
    # Stub process_handler again
    monkeypatch.setattr(monitoring, "process_handler", lambda name, action: False)

    # host and port both falsey
    fake_cfg = types.SimpleNamespace(host="", port=0)
    monkeypatch.setattr(monitoring, "validate_config", lambda *a, **k: fake_cfg)

    dummy = DummyApp()
    monkeypatch.setattr(monitoring, "create_app", lambda: dummy)

    # Should still not raise; run_args should default to (None, None)
    monitoring.main()

    assert dummy.run_args == (None, None)

def test_main_config_validation_failure(monkeypatch):
    # In this case, validate_config() raises SystemExit before process_handler is ever called.
    # We still stub process_handler (unused) for consistency.
    monkeypatch.setattr(monitoring, "process_handler", lambda name, action: False)

    def _bad_validate(*a, **k):
        raise SystemExit(1)
    monkeypatch.setattr(monitoring, "validate_config", _bad_validate)

    # We never get as far as create_app()
    with pytest.raises(SystemExit) as exc:
        monitoring.main()
    assert exc.value.code == 1

def test_main_app_creation_failure(monkeypatch):
    # Stub process_handler so main() doesn’t hang on real process checks
    monkeypatch.setattr(monitoring, "process_handler", lambda name, action: False)

    fake_cfg = types.SimpleNamespace(host="x", port=1)
    monkeypatch.setattr(monitoring, "validate_config", lambda *a, **k: fake_cfg)

    def _broken_create():
        raise RuntimeError("boom at create_app")
    monkeypatch.setattr(monitoring, "create_app", _broken_create)

    with pytest.raises(RuntimeError) as exc:
        monitoring.main()
    assert "boom at create_app" in str(exc.value)

def test_main_app_run_failure(monkeypatch):
    # Stub process_handler again
    monkeypatch.setattr(monitoring, "process_handler", lambda name, action: False)

    fake_cfg = types.SimpleNamespace(host="h", port=2)
    monkeypatch.setattr(monitoring, "validate_config", lambda *a, **k: fake_cfg)

    class BadApp:
        def run(self, host, port):
            raise IOError("boom at run")

    monkeypatch.setattr(monitoring, "create_app", lambda: BadApp())

    with pytest.raises(IOError) as exc:
        monitoring.main()
    assert "boom at run" in str(exc.value)
    
def test_main_process_handler_true(monkeypatch):
    # When process_handler('monitoring.py', action='check') returns True,
    # main() should call time.sleep(3), then process_handler(..., action='kill'),
    # and finally start the Flask app using create_app().run().
    recorded = {"check_called": False, "kill_called": False}
    fake_cfg = types.SimpleNamespace(host="h", port=2)
    monkeypatch.setattr(monitoring, "validate_config", lambda *a, **k: fake_cfg)
    # Stub process_handler: first call (action='check') → True, second call (action='kill') → record kill
    def fake_process_handler(name, action):
        if action == "check":
            recorded["check_called"] = True
            return True
        elif action == "kill":
            recorded["kill_called"] = True
            return True
        else: pass
    monkeypatch.setattr(monitoring, "process_handler", fake_process_handler)

    # Stub monitoring.time.sleep so it does not actually sleep
    monkeypatch.setattr(monitoring.time, "sleep", lambda seconds: None)

    dummy_app = DummyApp()
    monkeypatch.setattr(monitoring, "create_app", lambda: dummy_app)

    # Call main() (validate_config is already patched by the autouse fixture)
    monitoring.main()

    # Assert that process_handler was called with action="check" and action="kill"
    assert recorded["check_called"] is True, "process_handler(check) was not called"
    assert recorded["kill_called"] is True, "process_handler(kill) was not called"

    # Assert that create_app().run(...) was invoked using the host and port from patch_validate_config
    assert dummy_app.run_called is True, "create_app().run() was not invoked"
    assert dummy_app.run_args == (monitoring.host, monitoring.port)
    _ = fake_process_handler("monitoring.py", action="noop")