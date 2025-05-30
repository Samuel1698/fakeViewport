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
    fake_cfg = types.SimpleNamespace(host="1.2.3.4", port=2500)
    monkeypatch.setattr(monitoring, "validate_config", lambda *a, **k: fake_cfg)

    dummy = DummyApp()
    monkeypatch.setattr(monitoring, "create_app", lambda: dummy)

    # Should not raise
    monitoring.main()

    assert dummy.run_called is True
    assert dummy.run_args == ("1.2.3.4", 2500)

# missing host/port ⇒ .run(None, None)
def test_main_with_missing_host_port(monkeypatch):
    # host and port both falsey
    fake_cfg = types.SimpleNamespace(host="", port=0)
    monkeypatch.setattr(monitoring, "validate_config", lambda *a, **k: fake_cfg)

    dummy = DummyApp()
    monkeypatch.setattr(monitoring, "create_app", lambda: dummy)

    monitoring.main()

    assert dummy.run_args == (None, None)

# config validation failure ⇒ SystemExit
def test_main_config_validation_failure(monkeypatch):
    # simulate strict-mode failure: validate_config() sys.exit(1)
    def _bad_validate(*a, **k):
        raise SystemExit(1)
    monkeypatch.setattr(monitoring, "validate_config", _bad_validate)

    # We never get as far as create_app()
    with pytest.raises(SystemExit) as exc:
        monitoring.main()
    assert exc.value.code == 1

# create_app() blows up ⇒ propagate exception 
def test_main_app_creation_failure(monkeypatch):
    fake_cfg = types.SimpleNamespace(host="x", port=1)
    monkeypatch.setattr(monitoring, "validate_config", lambda *a, **k: fake_cfg)

    def _broken_create():
        raise RuntimeError("boom at create_app")
    monkeypatch.setattr(monitoring, "create_app", _broken_create)

    with pytest.raises(RuntimeError) as exc:
        monitoring.main()
    assert "boom at create_app" in str(exc.value)

# app.run() blows up ⇒ propagate exception
def test_main_app_run_failure(monkeypatch):
    fake_cfg = types.SimpleNamespace(host="h", port=2)
    monkeypatch.setattr(monitoring, "validate_config", lambda *a, **k: fake_cfg)

    class BadApp:
        def run(self, host, port):
            raise IOError("boom at run")

    monkeypatch.setattr(monitoring, "create_app", lambda: BadApp())

    with pytest.raises(IOError) as exc:
        monitoring.main()
    assert "boom at run" in str(exc.value)