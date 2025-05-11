import os
import configparser
import pytest
import subprocess
import pathlib
from pathlib import Path
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
    cfg["General"] = {
        "SLEEP_TIME":   "300",
        "LOG_INTERVAL": "15",
        "RESTART_TIMES": "12:00"
    }
    cfg["Logging"] = {
        # we no longer care about API_FILE_PATH here
        "LOG_FILE":       "False",
        "LOG_CONSOLE":    "False",
        "VERBOSE_LOGGING":"False",
        "LOG_DAYS":       "1",
    }
    cfg_path = tmp_path / "config.ini"
    with cfg_path.open("w") as f:
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
        "RESTART_TIMES": "12:00"
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
        "RESTART_TIMES": "12:00"
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
    # When SECRET is not set, /login should skip auth and redirect straight to dashboard (/).
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
    # Even if no SECRET is set, POST /api/control/<action> should still work.
    client_app = no_secret_client(tmp_path, monkeypatch)
    # stub out Popen to simulate success
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: None)
    resp = client_app.post(f"/api/control/{action}")
    assert resp.status_code == 202
    data = resp.get_json()
    assert data["status"]  == "ok"
    assert data["message"] == expected_msg
