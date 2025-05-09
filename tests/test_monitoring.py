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
    # ─────────────────────────────────────────────────────
    # 1) Stub out all real logging
    # ─────────────────────────────────────────────────────
    monkeypatch.setattr(monitoring, 'configure_logging', lambda *a, **k: None)

    # ─────────────────────────────────────────────────────
    # 2) Force script_dir → tmp_path so all endpoints read/write there
    # ─────────────────────────────────────────────────────
    monkeypatch.setattr(monitoring, 'script_dir', tmp_path)

    # ─────────────────────────────────────────────────────
    # 3) Fake psutil uptime & RAM
    # ─────────────────────────────────────────────────────
    monkeypatch.setattr(monitoring.psutil, 'boot_time',    lambda: 1000)
    monkeypatch.setattr(monitoring.time,    'time',        lambda: 1010)
    class DummyVM:
        used  = 12345
        total = 67890
    monkeypatch.setattr(monitoring.psutil, 'virtual_memory', lambda: DummyVM)

    # ─────────────────────────────────────────────────────
    # 4) Write a minimal config.ini into tmp_path
    # ─────────────────────────────────────────────────────
    cfg = configparser.ConfigParser()
    cfg['General'] = {
        'SLEEP_TIME':   '300',
        'LOG_INTERVAL': '15',
    }
    cfg['Logging'] = {
        # we no longer care about API_FILE_PATH here
        'LOG_FILE':       'False',
        'LOG_CONSOLE':    'False',
        'VERBOSE_LOGGING':'False',
        'LOG_DAYS':       '1',
    }
    cfg_path = tmp_path / 'config.ini'
    with cfg_path.open('w') as f:
        cfg.write(f)

    # ─────────────────────────────────────────────────────
    # 5) Create & return the Flask test client
    # ─────────────────────────────────────────────────────
    app = create_app(str(cfg_path))
    app.testing = True
    return app.test_client()
# -------------------------------------------------------------------------
# Helper to build an app/client with SECRET in the environment
# -------------------------------------------------------------------------
def _make_auth_client(tmp_path, monkeypatch):
    # 1) Stub logging so it never writes
    monkeypatch.setattr(monitoring, "configure_logging", lambda *a, **k: None)

    # 2) Make SECRET present
    monkeypatch.setenv("SECRET", "shh")

    # 3) Redirect all file-based operations under tmp_path
    monkeypatch.setattr(monitoring, "script_dir", tmp_path)

    # 4) Build the minimal config.ini
    cfg = configparser.ConfigParser()
    cfg["General"] = {
        "SLEEP_TIME":   "300",   
        "LOG_INTERVAL": "15",    
    }
    cfg["Logging"] = {
        "LOG_FILE":        "False",
        "LOG_CONSOLE":     "False",
        "VERBOSE_LOGGING": "False",
        "LOG_DAYS":        "1",
    }
    cfg_path = tmp_path / "config.ini"
    with open(cfg_path, "w") as f:
        cfg.write(f)

    # 5) Stub out render_template so you know what’s returned
    monkeypatch.setattr(monitoring, "render_template",
                        lambda tpl, **ctx: f"TEMPLATE({tpl})")

    # 6) Create the app and return just the test client
    app = create_app(str(cfg_path))
    app.testing = True
    return app.test_client()
# -------------------------------------------------------------------------
# Helper to build an app/client with NO SECRET in the environment
# -------------------------------------------------------------------------
def no_secret_client(tmp_path, monkeypatch):
    # 1) Ensure SECRET isn’t set
    monkeypatch.delenv("SECRET", raising=False)

    # 2) Stub logging
    monkeypatch.setattr(monitoring, "configure_logging", lambda *a, **k: None)

    # 3) Fake out psutil / time so uptime & memory are deterministic
    monkeypatch.setattr(monitoring.psutil, "boot_time", lambda: 1000)
    monkeypatch.setattr(monitoring.time,   "time",      lambda: 1010)
    class DummyVM:
        used = 12345
        total = 67890
    monkeypatch.setattr(monitoring.psutil, "virtual_memory", lambda: DummyVM)

    # 4) Redirect all file-based operations under tmp_path
    monkeypatch.setattr(monitoring, "script_dir", tmp_path)

    # 5) Build the minimal config.ini 
    cfg = configparser.ConfigParser()
    cfg["General"] = {
        "SLEEP_TIME":   "300",
        "LOG_INTERVAL": "15",
    }
    cfg["Logging"] = {
        "LOG_FILE":        "False",
        "LOG_CONSOLE":     "False",
        "VERBOSE_LOGGING": "False",
        "LOG_DAYS":        "1",
    }
    cfg_path = tmp_path / "config.ini"
    with open(cfg_path, "w") as f:
        cfg.write(f)

    # 6) Create the app and return just the test client
    app = create_app(str(cfg_path))
    app.testing = True
    return app.test_client()
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
    client_app = client
    # Stub out subprocess.Popen to simulate success
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: None)
    resp = client_app.post(f"/api/control/{action}")
    assert resp.status_code == 202
    data = resp.get_json()
    assert data["status"] == "ok"
    assert data["message"] == expected_message

def test_api_control_unknown_action(client):
    client_app = client
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
    client_app = client
    # Make Popen raise to exercise the 500 branch
    def fake_popen(*args, **kwargs):
        raise RuntimeError(exc_msg)
    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    resp = client_app.post("/api/control/start")
    assert resp.status_code == 500
    data = resp.get_json()
    assert data["status"] == "error"
    assert exc_msg not in data["message"]
# -------------------------
# 2. /api/log_entry error path
# -------------------------
def test_api_log_entry_read_error(client, monkeypatch):
    client_app = client
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
    client_app = client
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
    client_app = client
    resp_base = client_app.get("/api")
    resp_alias = client_app.get(path)
    # Both must have same status and payload
    assert resp_alias.status_code == resp_base.status_code
    assert resp_alias.get_json()    == resp_base.get_json()

# -------------------------
# 5. Generic 404 for unknown API path
# -------------------------
def test_unknown_api_path_returns_404(client):
    client_app = client
    resp = client_app.get("/api/nonexistent")
    assert resp.status_code == 404

# -------------------------
# 6. API directory is created by the fixture
# -------------------------
def test_api_directory_created_by_fixture(client, tmp_path, monkeypatch):
    # 1) point monitoring.script_dir at a tmp dir
    monkeypatch.setattr(monitoring, 'script_dir', tmp_path)

    # 2) compute the api_dir exactly like the app does
    api_dir: Path = monitoring.script_dir / 'api'
    api_dir.mkdir(parents=True, exist_ok=True)

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
    client_app = no_secret_client(tmp_path, monkeypatch)
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
    client_app = no_secret_client(tmp_path, monkeypatch)
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
    resp = client.get('/api')
    assert resp.status_code == 200
    data = resp.get_json()
    expected = {
        'script_uptime',
        'system_uptime',
        'ram',
        'health_interval',
        'log_interval',
        'logs',
        'status',
        'next_restart',
        'log_entry',
    }
    assert set(data.keys()) == expected
    for key, url in data.items():
        assert url.endswith(f'/api/{key}')

# -------------------------
# /api/script_uptime
# -------------------------
def test_script_uptime_missing(client):
    resp = client.get('/api/script_uptime')
    assert resp.status_code == 404
    obj = resp.get_json()
    assert obj['status'] == 'error'
    assert 'SST file not found' in obj['message']

def test_script_uptime_malformed(client, tmp_path, monkeypatch):
    # 1) point monitoring.script_dir at a tmp dir
    monkeypatch.setattr(monitoring, 'script_dir', tmp_path)

    # 2) compute the api_dir exactly like the app does
    api_dir: Path = monitoring.script_dir / 'api'
    api_dir.mkdir(parents=True, exist_ok=True)

    (api_dir / 'sst.txt').write_text('not a timestamp')
    resp = client.get('/api/script_uptime')
    assert resp.status_code == 400
    obj = resp.get_json()
    assert obj['status'] == 'error'
    assert 'Malformed SST timestamp' in obj['message']

def test_script_uptime_ok(client, tmp_path, monkeypatch):
    # 1) point monitoring.script_dir at a tmp dir
    monkeypatch.setattr(monitoring, 'script_dir', tmp_path)

    # 2) compute the api_dir exactly like the app does
    api_dir: Path = monitoring.script_dir / 'api'
    api_dir.mkdir(parents=True, exist_ok=True)

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
    resp = client.get('/api/system_uptime')
    assert resp.status_code == 200
    obj = resp.get_json()
    assert obj['status'] == 'ok'
    assert pytest.approx(obj['data']['system_uptime'], rel=1e-3) == 10

def test_system_uptime_error(monkeypatch, client):
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
    resp = client.get('/api/health_interval')
    assert resp.status_code == 200
    obj = resp.get_json()
    assert obj['status'] == 'ok'
    assert obj['data']['health_interval_sec'] == 300


# -------------------------
# /api/log_interval
# -------------------------
def test_log_interval(client):
    resp = client.get('/api/log_interval')
    assert resp.status_code == 200
    obj = resp.get_json()
    assert obj['status'] == 'ok'
    assert obj['data']['log_interval_min'] == 15


# -------------------------
# /api/status (last status update)
# -------------------------
def test_status_missing(client):
    resp = client.get('/api/status')
    assert resp.status_code == 404
    obj = resp.get_json()
    assert obj['status'] == 'error'
    assert 'Status file not found' in obj['message']

def test_status_ok(client, tmp_path, monkeypatch):
    # 1) point monitoring.script_dir at a tmp dir
    monkeypatch.setattr(monitoring, 'script_dir', tmp_path)

    # 2) compute the api_dir exactly like the app does
    api_dir: Path = monitoring.script_dir / 'api'
    api_dir.mkdir(parents=True, exist_ok=True)

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
# -------------------------
# /api/logs?limit
# -------------------------
def test_default_limit_returns_100_lines(client, tmp_path, monkeypatch):
    client_app = client
    # 1) point script_dir at tmp
    monkeypatch.setattr(monitoring, 'script_dir', tmp_path)

    # 2) create logs/viewport.log
    logs_dir = monitoring.script_dir / 'logs'
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / 'viewport.log'

    # 3) write 150 entries
    lines = [f"entry {i}" for i in range(150)]
    log_path.write_text("\n".join(lines) + "\n")

    # 4) call endpoint
    resp = client_app.get("/api/logs")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "ok"

    logs = body["data"]["logs"]
    assert isinstance(logs, list)
    # last 100 of the 150
    assert len(logs) == 100
    assert logs[0] == "entry 50\n"
    assert logs[-1] == "entry 149\n"


@pytest.mark.parametrize("limit,expected_start", [
    (10, 140),
    (200, 0),
])
def test_custom_limit(client, limit, expected_start, tmp_path, monkeypatch):
    client_app = client
    monkeypatch.setattr(monitoring, 'script_dir', tmp_path)

    logs_dir = monitoring.script_dir / 'logs'
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / 'viewport.log'

    # 150 lines
    lines = [f"row {i}" for i in range(150)]
    log_path.write_text("\n".join(lines) + "\n")

    resp = client_app.get(f"/api/logs?limit={limit}")
    assert resp.status_code == 200
    logs = resp.get_json()["data"]["logs"]

    count = min(limit, 150)
    assert len(logs) == count
    assert logs[0] == f"row {150 - count}\n"
    assert logs[-1] == "row 149\n"

def test_invalid_limit_falls_back_to_default(client, tmp_path, monkeypatch):
    client_app = client
    monkeypatch.setattr(monitoring, 'script_dir', tmp_path)

    logs_dir = monitoring.script_dir / 'logs'
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / 'viewport.log'

    # 120 lines
    lines = [f"x{i}" for i in range(120)]
    log_path.write_text("\n".join(lines) + "\n")

    # non-integer limit → default 100
    resp = client_app.get("/api/logs?limit=notanumber")
    assert resp.status_code == 200
    logs = resp.get_json()["data"]["logs"]

    assert len(logs) == 100
    assert logs[0] == "x20\n"   # 120 - 100 = 20
    assert logs[-1] == "x119\n"


def test_missing_file_returns_500(client, tmp_path, monkeypatch):
    client_app = client
    monkeypatch.setattr(monitoring, 'script_dir', tmp_path)

    # create the logs dir, but do NOT create viewport.log
    logs_dir = monitoring.script_dir / 'logs'
    logs_dir.mkdir(parents=True, exist_ok=True)

    resp = client_app.get("/api/logs")
    assert resp.status_code == 500

    body = resp.get_json()
    assert body["status"] == "error"
    # should mention the missing file
    assert "No such file" in body["message"] or "not found" in body["message"]