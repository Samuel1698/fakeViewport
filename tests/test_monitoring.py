# tests/test_monitoring.py
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))
import os
import configparser
import pytest
import subprocess
import pathlib
from pathlib import Path
from datetime import datetime, timedelta
import psutil
import monitoring
from monitoring import create_app
# -------------------------------------------------------------------------
# Helper to build an app/client
# -------------------------------------------------------------------------
@pytest.fixture
def client(tmp_path, monkeypatch):
    # 1) Stub out real logging
    monkeypatch.setattr(monitoring, 'configure_logging', lambda *a, **k: None)

    # 2) Fix system uptime: boot_time=1000, time.time()=1010 ⇒ uptime=10s
    monkeypatch.setattr(monitoring.psutil, 'boot_time', lambda: 1000)
    monkeypatch.setattr(monitoring.time, 'time', lambda: 1010)

    # 3) Fake RAM numbers
    class DummyVM:
        used = 12345
        total = 67890
    monkeypatch.setattr(monitoring.psutil, 'virtual_memory', lambda: DummyVM)

    # 4) Temp config.ini pointing API_FILE_PATH to tmp_path/api
    cfg = configparser.ConfigParser()
    cfg['API'] = {'API_FILE_PATH': str(tmp_path / 'api')}
    cfg['General'] = {
        'SLEEP_TIME': '300',     # health_interval_sec
        'LOG_INTERVAL': '15'     # log_interval_min
    }
    cfg['Logging'] = {
        'LOG_FILE': 'no',
        'LOG_CONSOLE': 'no',
        'VERBOSE_LOGGING': 'no',
        'LOG_DAYS': '1'
    }
    cfg_path = tmp_path / 'config.ini'
    with open(cfg_path, 'w') as f:
        cfg.write(f)

    app = create_app(str(cfg_path))
    app.testing = True
    return app.test_client(), tmp_path / 'api'
# -------------------------------------------------------------------------
# Helper to build an app/client with SECRET in the environment
# -------------------------------------------------------------------------
def _make_auth_client(tmp_path, monkeypatch):
    # Stub logging and set SECRET before app creation
    monkeypatch.setattr(monitoring, "configure_logging", lambda *a, **k: None)
    monkeypatch.setenv("SECRET", "shh")
    # Minimal config.ini
    cfg = configparser.ConfigParser()
    cfg["API"]     = {"API_FILE_PATH": str(tmp_path / "api")}
    cfg["General"] = {"SLEEP_TIME": "300", "LOG_INTERVAL": "15"}
    cfg["Logging"] = {
        "LOG_FILE": "no",
        "LOG_CONSOLE": "no",
        "VERBOSE_LOGGING": "no",
        "LOG_DAYS": "1",
    }
    cfg_path = tmp_path / "config.ini"
    with open(cfg_path, "w") as f:
        cfg.write(f)
    # Render templates to a known string
    monkeypatch.setattr(monitoring, "render_template", lambda tpl, **ctx: f"TEMPLATE({tpl})")
    app = create_app(str(cfg_path))
    app.testing = True
    return app.test_client()
# -------------------------------------------------------------------------
# Helper to build an app/client with NO SECRET in the environment
# -------------------------------------------------------------------------
def no_secret_client(tmp_path, monkeypatch):
    # Ensure SECRET is not set → CONTROL_TOKEN will be falsey
    monkeypatch.delenv("SECRET", raising=False)
    # Stub out logging setup so it doesn’t write anywhere
    monkeypatch.setattr("monitoring.configure_logging", lambda *a, **k: None)
    # 2) Fix system uptime: boot_time=1000, time.time()=1010 ⇒ uptime=10s
    monkeypatch.setattr(monitoring.psutil, 'boot_time', lambda: 1000)
    monkeypatch.setattr(monitoring.time, 'time', lambda: 1010)

    # 3) Fake RAM numbers
    class DummyVM:
        used = 12345
        total = 67890
    monkeypatch.setattr(monitoring.psutil, 'virtual_memory', lambda: DummyVM)

    # 4) Temp config.ini pointing API_FILE_PATH to tmp_path/api
    cfg = configparser.ConfigParser()
    cfg['API'] = {'API_FILE_PATH': str(tmp_path / 'api')}
    cfg['General'] = {
        'SLEEP_TIME': '300',     # health_interval_sec
        'LOG_INTERVAL': '15'     # log_interval_min
    }
    cfg['Logging'] = {
        'LOG_FILE': 'no',
        'LOG_CONSOLE': 'no',
        'VERBOSE_LOGGING': 'no',
        'LOG_DAYS': '1'
    }
    cfg_path = tmp_path / 'config.ini'
    with open(cfg_path, 'w') as f:
        cfg.write(f)

    app = create_app(str(cfg_path))
    app.testing = True
    return app.test_client(), tmp_path / 'api'
# -------------------------
# 1. Control endpoint (/api/control/<action>)
# -------------------------
@pytest.mark.parametrize(
    "action, expected_message",
    [
        # Valid 'start' action
        ("start",   "Start command issued"),
        # Valid 'restart' action
        ("restart", "Restart command issued"),
        # Valid 'quit' action
        ("quit",    "Quit command issued"),
    ]
)
def test_api_control_valid_actions(client, monkeypatch, action, expected_message):
    client_app, api_dir = client
    # Stub out subprocess.Popen to simulate success
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: None)
    resp = client_app.post(f"/api/control/{action}")
    assert resp.status_code == 202
    data = resp.get_json()
    assert data["status"] == "ok"
    assert data["message"] == expected_message

def test_api_control_unknown_action(client):
    client_app, api_dir = client
    # Unknown action should return 400 with appropriate error
    resp = client_app.post("/api/control/foobar")
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["status"] == "error"
    assert 'Unknown action "foobar"' in data["message"]

@pytest.mark.parametrize("action", ["start", "restart", "quit"])
def test_control_requires_login_for_all_actions(tmp_path, monkeypatch, action):
    client_app = _make_auth_client(tmp_path, monkeypatch)
    resp = client_app.post(f"/api/control/{action}", follow_redirects=False)
    assert resp.status_code == 302
    assert f"/login?next=/api/control/{action}" in resp.headers["Location"]
    
@pytest.mark.parametrize("exc_msg", ["boom", "kaboom"])
def test_api_control_dispatch_failure(client, monkeypatch, exc_msg):
    client_app, api_dir = client
    # Make Popen raise to exercise the 500 branch
    def fake_popen(*args, **kwargs):
        raise RuntimeError(exc_msg)
    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    resp = client_app.post("/api/control/start")
    assert resp.status_code == 500
    data = resp.get_json()
    assert data["status"] == "error"
    assert exc_msg in data["message"]
# -------------------------
# 2. /api/log_entry error path
# -------------------------
def test_api_log_entry_read_error(client, monkeypatch):
    client_app, api_dir = client
    # Force .exists() → True and .read_text() → IOError
    monkeypatch.setattr(Path, "exists",    lambda self: True)
    monkeypatch.setattr(Path, "read_text", lambda self: (_ for _ in ()).throw(IOError("boom")))
    resp = client_app.get("/api/log_entry")
    assert resp.status_code == 500
    data = resp.get_json()
    assert data["status"] == "error"
    assert data["message"] == "Error reading log file"

# -------------------------
# 3. CORS headers
# -------------------------
@pytest.mark.parametrize("route", [
    # Base API endpoint
    "/api",
    # Single endpoint
    "/api/log_entry",
])
def test_cors_headers_for_api_routes(client, route):
    client_app, api_dir = client
    resp = client_app.get(route)
    # Flask-CORS should inject this header
    assert resp.headers.get("Access-Control-Allow-Origin") == "*"

# -------------------------
# 4. Trailing-slash alias for /api index
# -------------------------
@pytest.mark.parametrize("path", [
    # Without trailing slash
    "/api",
    # With trailing slash
    "/api/",
])
def test_api_index_trailing_slash_alias(client, path):
    client_app, api_dir = client
    resp_base = client_app.get("/api")
    resp_alias = client_app.get(path)
    # Both must have same status and payload
    assert resp_alias.status_code == resp_base.status_code
    assert resp_alias.get_json()    == resp_base.get_json()

# -------------------------
# 5. Generic 404 for unknown API path
# -------------------------
def test_unknown_api_path_returns_404(client):
    client_app, api_dir = client
    resp = client_app.get("/api/nonexistent")
    assert resp.status_code == 404

# -------------------------
# 6. API directory is created by the fixture
# -------------------------
def test_api_directory_created_by_fixture(client):
    client_app, api_dir = client
    assert api_dir.exists() and api_dir.is_dir()

# -------------------------
# 7. Authentication flows when SECRET is set
# -------------------------
def test_dashboard_requires_login(tmp_path, monkeypatch):
    client_app = _make_auth_client(tmp_path, monkeypatch)
    # Unauthenticated GET "/" → redirect to login
    resp = client_app.get("/", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login?next=/" in resp.headers["Location"]

def test_login_get_renders_form(tmp_path, monkeypatch):
    client_app = _make_auth_client(tmp_path, monkeypatch)
    # GET /login shows our fake template
    resp = client_app.get("/login")
    assert resp.status_code == 200
    assert b"TEMPLATE(login.html)" in resp.data

def test_login_post_wrong_key_flashes_error(tmp_path, monkeypatch):
    client_app = _make_auth_client(tmp_path, monkeypatch)
    # POST bad key → 200 (re-renders login), flash("Invalid API key")
    resp = client_app.post("/login", data={"key": "nope"}, follow_redirects=False)
    assert resp.status_code == 200

    # Inspect the session to see that the flash was recorded
    with client_app.session_transaction() as sess:
        flashes = sess.get("_flashes", [])
    # flashes is a list of (category, message) tuples
    assert ("danger", "Invalid API key") in flashes

def test_login_post_correct_key_redirects(tmp_path, monkeypatch):
    client_app = _make_auth_client(tmp_path, monkeypatch)
    # POST good key → redirect to next ("/")
    resp = client_app.post("/login?next=/", data={"key": "shh"}, follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/")

def test_logout_clears_session_and_redirects(tmp_path, monkeypatch):
    client_app = _make_auth_client(tmp_path, monkeypatch)
    # /logout should always 302 → /login
    resp = client_app.get("/logout", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/login")
# -------------------------------------------------------------------------
# LOGIN SKIP WHEN NO SECRET
# -------------------------------------------------------------------------
def test_login_redirects_to_dashboard_if_no_secret(tmp_path, monkeypatch):
    """
    When SECRET is not set, /login should skip auth and redirect straight to dashboard (/).
    """
    client_app, api_dir = no_secret_client(tmp_path, monkeypatch)
    resp = client_app.get("/login", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/")

@pytest.mark.parametrize("action,expected_msg", [
    ("start",   "Start command issued"),
    ("restart", "Restart command issued"),
    ("quit",    "Quit command issued"),
])
def test_control_endpoints_allowed_without_login(tmp_path, monkeypatch, action, expected_msg):
    """
    Even if no SECRET is set, POST /api/control/<action> should still work.
    """
    client_app, api_dir = no_secret_client(tmp_path, monkeypatch)
    # stub out Popen to simulate success
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: None)
    resp = client_app.post(f"/api/control/{action}")
    assert resp.status_code == 202
    data = resp.get_json()
    assert data["status"]  == "ok"
    assert data["message"] == expected_msg
# -------------------------
# /api index
# -------------------------
def test_api_index_links(client):
    client, api_dir = client
    resp = client.get('/api')
    assert resp.status_code == 200
    data = resp.get_json()
    expected = {
        'script_uptime',
        'system_uptime',
        'ram',
        'health_interval',
        'log_interval',
        'status',
        'log_entry',
    }
    assert set(data.keys()) == expected
    for key, url in data.items():
        assert url.endswith(f'/api/{key}')

# -------------------------
# /api/script_uptime
# -------------------------
def test_script_uptime_missing(client):
    client, api_dir = client
    resp = client.get('/api/script_uptime')
    assert resp.status_code == 404
    obj = resp.get_json()
    assert obj['status'] == 'error'
    assert 'SST file not found' in obj['message']

def test_script_uptime_malformed(client):
    client, api_dir = client
    (api_dir / 'sst.txt').write_text('not a timestamp')
    resp = client.get('/api/script_uptime')
    assert resp.status_code == 400
    obj = resp.get_json()
    assert obj['status'] == 'error'
    assert 'Malformed SST timestamp' in obj['message']

def test_script_uptime_ok(monkeypatch, client):
    client, api_dir = client
    import datetime as real_dt
    fixed = real_dt.datetime(2025, 4, 28, 12, 0, 10)
    class DummyDT:
        @classmethod
        def now(cls): return fixed
        @staticmethod
        def strptime(s, fmt): return real_dt.datetime.strptime(s, fmt)
    monkeypatch.setattr(monitoring, 'datetime', DummyDT)

    ts = (fixed - real_dt.timedelta(seconds=10)).strftime('%Y-%m-%d %H:%M:%S.%f')
    (api_dir / 'sst.txt').write_text(ts)

    resp = client.get('/api/script_uptime')
    assert resp.status_code == 200
    obj = resp.get_json()
    assert obj['status'] == 'ok'
    assert pytest.approx(obj['data']['script_uptime'], rel=1e-3) == 10


# -------------------------
# /api/system_uptime
# -------------------------
def test_system_uptime_ok(client):
    client, api_dir = client
    resp = client.get('/api/system_uptime')
    assert resp.status_code == 200
    obj = resp.get_json()
    assert obj['status'] == 'ok'
    assert pytest.approx(obj['data']['system_uptime'], rel=1e-3) == 10

def test_system_uptime_error(monkeypatch, client):
    client, api_dir = client
    monkeypatch.setattr(monitoring.psutil, 'boot_time', lambda: (_ for _ in ()).throw(Exception()))
    resp = client.get('/api/system_uptime')
    assert resp.status_code == 500
    obj = resp.get_json()
    assert obj['status'] == 'error'
    assert 'Could not determine system uptime' in obj['message']


# -------------------------
# /api/ram
# -------------------------
def test_ram_endpoint(client):
    client, api_dir = client
    resp = client.get('/api/ram')
    assert resp.status_code == 200
    obj = resp.get_json()
    assert obj['status'] == 'ok'
    assert obj['data']['ram_used'] == 12345
    assert obj['data']['ram_total'] == 67890


# -------------------------
# /api/health_interval
# -------------------------
def test_health_interval(client):
    client, api_dir = client
    resp = client.get('/api/health_interval')
    assert resp.status_code == 200
    obj = resp.get_json()
    assert obj['status'] == 'ok'
    assert obj['data']['health_interval_sec'] == 300


# -------------------------
# /api/log_interval
# -------------------------
def test_log_interval(client):
    client, api_dir = client
    resp = client.get('/api/log_interval')
    assert resp.status_code == 200
    obj = resp.get_json()
    assert obj['status'] == 'ok'
    assert obj['data']['log_interval_min'] == 15


# -------------------------
# /api/status (last status update)
# -------------------------
def test_status_missing(client):
    client, api_dir = client
    resp = client.get('/api/status')
    assert resp.status_code == 404
    obj = resp.get_json()
    assert obj['status'] == 'error'
    assert 'Status file not found' in obj['message']

def test_status_ok(client):
    client, api_dir = client
    (api_dir / 'status.txt').write_text('All Good')
    resp = client.get('/api/status')
    assert resp.status_code == 200
    obj = resp.get_json()
    assert obj['status'] == 'ok'
    assert obj['data']['status'] == 'All Good'


# -------------------------
# /api/log_entry (last log line)
# -------------------------
def test_log_entry_missing(client, monkeypatch):
    client, api_dir = client

    # Patch Path.exists to always say the viewport.log doesn't exist
    orig_exists = pathlib.Path.exists
    def fake_exists(self):
        if self.name == 'viewport.log':
            return False
        return orig_exists(self)
    monkeypatch.setattr(pathlib.Path, 'exists', fake_exists)

    resp = client.get('/api/log_entry')
    assert resp.status_code == 404
    obj = resp.get_json()
    assert obj['status'] == 'error'
    assert 'Log file not found' in obj['message']

def test_log_entry_ok(client, monkeypatch):
    client, api_dir = client

    # Patch Path.exists to say viewport.log exists
    orig_exists = pathlib.Path.exists
    def fake_exists(self):
        if self.name == 'viewport.log':
            return True
        return orig_exists(self)
    monkeypatch.setattr(pathlib.Path, 'exists', fake_exists)

    # Patch Path.read_text to return our fake log contents
    orig_read = pathlib.Path.read_text
    def fake_read_text(self, *args, **kwargs):
        if self.name == 'viewport.log':
            return "first\nsecond\nthird"
        return orig_read(self, *args, **kwargs)
    monkeypatch.setattr(pathlib.Path, 'read_text', fake_read_text)

    resp = client.get('/api/log_entry')
    assert resp.status_code == 200
    obj = resp.get_json()
    assert obj['status'] == 'ok'
    assert obj['data']['log_entry'] == 'third'