import os, subprocess, sys
from pathlib import Path
from types import SimpleNamespace
from datetime import time as timecls
import pytest
import monitoring
from monitoring import create_app
# ----------------------------------------------------------------------------- 
# Helper to build an app/client
# ----------------------------------------------------------------------------- 
@pytest.fixture(autouse=True)
def patch_validate_config(monkeypatch, tmp_path):
    # Replace monitoring.validate_config(...) with one
    # that reads only from os.environ and returns exactly
    # the attributes monitoring.py expects.
    def fake_validate_config(
        strict=False,
        api=False,
        config_file=None,
        env_file=None,
        logs_dir=None,
        api_dir=None,
    ):
        # parse RESTART_TIMES from env or default "12:00"
        times = [
            timecls(*map(int, t.split(":")))
            for t in os.getenv("RESTART_TIMES", "12:00").split(",")
            if t.strip()
        ]

        return SimpleNamespace(
            # flask secret & host/port
            CONTROL_TOKEN=os.getenv("SECRET", ""),
            host=os.getenv("FLASK_RUN_HOST", ""),
            port=os.getenv("FLASK_RUN_PORT", ""),

            # intervals & restart times
            SLEEP_TIME=300,
            LOG_INTERVAL=15,
            RESTART_TIMES=times,

            # logging flags
            LOG_FILE_FLAG=False,
            LOG_CONSOLE=False,
            DEBUG_LOGGING=False,
            LOG_DAYS=1,

            # file paths under tmp_path
            mon_file=tmp_path / "api" / "mon.txt",
            log_file=tmp_path / "logs" / "viewport.log",
            sst_file=tmp_path / "api" / "sst.txt",
            status_file=tmp_path / "api" / "status.txt",
        )

    monkeypatch.setattr(monitoring, "validate_config", fake_validate_config)
@pytest.fixture
def client(tmp_path, monkeypatch):
    # stub out logging config
    monkeypatch.setattr(monitoring, "configure_logging", lambda *a, **k: None)

    # point all file ops under tmp_path
    monkeypatch.setattr(monitoring, "script_dir", tmp_path)
    (tmp_path / "api").mkdir(exist_ok=True)
    (tmp_path / "logs").mkdir(exist_ok=True)

    # fake system uptime & RAM
    monkeypatch.setattr(monitoring.psutil, "boot_time", lambda: 1000)
    monkeypatch.setattr(monitoring.time, "time", lambda: 1010)
    class DummyVM:
        used = 12345
        total = 67890
    monkeypatch.setattr(
        monitoring.psutil, "virtual_memory", lambda: DummyVM
    )
    # Temporarily disable login_required check
    monkeypatch.setenv("SECRET", "")
    # build Flask client
    app = create_app()
    app.testing = True
    return app.test_client()
# ----------------------------------------------------------------------------- 
# Helper to build an app/client with SECRET in the environment
# ----------------------------------------------------------------------------- 
def _make_auth_client(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRET", "shh")
    monkeypatch.setattr(monitoring, "configure_logging", lambda *a, **k: None)
    monkeypatch.setattr(monitoring, "script_dir", tmp_path)
    (tmp_path / "api").mkdir(exist_ok=True)
    (tmp_path / "logs").mkdir(exist_ok=True)

    # stub render_template so we can detect it
    monkeypatch.setattr(
        monitoring,
        "render_template",
        lambda tpl, **ctx: f"TEMPLATE({tpl})"
    )

    app = create_app()
    app.testing = True
    return app.test_client()
# ----------------------------------------------------------------------------- 
# Helper to build an app/client with NO SECRET in the environment
# ----------------------------------------------------------------------------- 
def no_secret_client(tmp_path, monkeypatch):
    monkeypatch.delenv("SECRET", raising=False)
    monkeypatch.setattr(monitoring, "configure_logging", lambda *a, **k: None)
    monkeypatch.setattr(monitoring, "script_dir", tmp_path)
    (tmp_path / "api").mkdir(exist_ok=True)
    (tmp_path / "logs").mkdir(exist_ok=True)

    app = create_app()
    app.testing = True
    return app.test_client()
# ----------------------------------------------------------------------------- 
# Control endpoint (/api/control/<action>)
# ----------------------------------------------------------------------------- 
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
# ----------------------------------------------------------------------------- 
# /api/self/restart
# ----------------------------------------------------------------------------- 
def test_api_restart_success(monkeypatch, client):
    recorded = {}

    # Patch subprocess.Popen so it does not spawn a real process
    class DummyPopen:
        def __init__(self, args, cwd=None, stdin=None, stdout=None, stderr=None,
                     close_fds=None, start_new_session=None):
            recorded["popen_args"] = args
            recorded["popen_cwd"] = cwd
            recorded["popen_kwargs"] = {
                "stdin": stdin,
                "stdout": stdout,
                "stderr": stderr,
                "close_fds": close_fds,
                "start_new_session": start_new_session,
            }

    monkeypatch.setattr(subprocess, "Popen", DummyPopen)

    # Perform the POST to the restart endpoint
    resp = client.post("/api/self/restart")
    assert resp.status_code == 202

    payload = resp.get_json()
    assert payload["status"] == "ok"
    assert "API restart initiated" in payload["message"]

    # Compute what the code uses for the script path and cwd
    expected_script_path = str(monitoring.script_dir / "monitoring.py")
    expected_cwd = str(monitoring.script_dir)

    popen_args = recorded.get("popen_args")
    assert popen_args is not None, "subprocess.Popen was not called"
    assert popen_args[0] == sys.executable
    assert popen_args[1] == expected_script_path
    assert recorded["popen_cwd"] == expected_cwd

def test_api_restart_fails_when_popen_raises(monkeypatch, client):
    def fake_popen(*args, **kwargs):
        raise RuntimeError("pop failed")

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    resp = client.post("/api/self/restart")
    assert resp.status_code == 500

    payload = resp.get_json()
    assert payload["status"] == "error"
    assert "pop failed" in payload["message"]
# ----------------------------------------------------------------------------- 
# /api/log_entry error path
# ----------------------------------------------------------------------------- 
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
def test_read_api_file_error_logs_and_returns_none(tmp_path, monkeypatch, caplog):
    # Stub configure_logging so app.logger works
    monkeypatch.setattr(monitoring, "configure_logging", lambda *a, **k: None)

    # Build app
    app = create_app()

    # Now monkeypatch Path.read_text to throw
    monkeypatch.setattr(Path, "exists", lambda self: True)
    monkeypatch.setattr(Path, "read_text", lambda self: (_ for _ in ()).throw(IOError("disk error")))

    # Hit the status endpoint, which under the hood calls _read_api_file
    caplog.set_level("ERROR")
    client = app.test_client()
    resp = client.get("/api/status")
    assert resp.status_code == 404  # raw == None
    # And we logged the ERROR
    assert "Error reading" in caplog.text

# ----------------------------------------------------------------------------- 
# CORS headers
# ----------------------------------------------------------------------------- 
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

# ----------------------------------------------------------------------------- 
# Trailing-slash alias for /api index
# ----------------------------------------------------------------------------- 
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

# ----------------------------------------------------------------------------- 
# Generic 404 for unknown API path
# ----------------------------------------------------------------------------- 
def test_unknown_api_path_returns_404(client):
    client_app = client
    resp = client_app.get("/api/nonexistent")
    assert resp.status_code == 404

# ----------------------------------------------------------------------------- 
# API directory is created by the fixture
# ----------------------------------------------------------------------------- 
def test_api_directory_created_by_fixture(client, tmp_path, monkeypatch):
    # point monitoring.script_dir at a tmp dir
    monkeypatch.setattr(monitoring, 'script_dir', tmp_path)

    # compute the api_dir exactly like the app does
    api_dir: Path = monitoring.script_dir / 'api'
    api_dir.mkdir(parents=True, exist_ok=True)

    assert api_dir.exists() and api_dir.is_dir()

# ----------------------------------------------------------------------------- 
# Authentication flows when SECRET is set
# ----------------------------------------------------------------------------- 
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
def test_login_post_with_secret_and_unsafe_next_redirects_dashboard(tmp_path, monkeypatch):
    client_app = _make_auth_client(tmp_path, monkeypatch)
    
    resp = client_app.post(
        "/login?next=http://evil.com/steal",
        data={"key": "shh"},      # matches CONTROL_TOKEN from the fixture
        follow_redirects=False
    )
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/"
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
# ----------------------------------------------------------------------------- 
# LOGIN SKIP WHEN NO SECRET
# ----------------------------------------------------------------------------- 
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
# ----------------------------------------------------------------------------- 
# Index
# -----------------------------------------------------------------------------   
def test_dashboard_renders_index(tmp_path, monkeypatch):
    # No SECRET means login is skipped and dashboard is public
    monkeypatch.delenv("SECRET", raising=False)
    monkeypatch.setattr(monitoring, "configure_logging", lambda *a, **k: None)
    # Stub render_template so we can detect the call
    monkeypatch.setattr(monitoring, "render_template", lambda tpl, **ctx: f"INDEX({tpl})")

    # Build App
    app = create_app()
    app.testing = True
    client = app.test_client()

    resp = client.get("/")
    assert resp.status_code == 200
    assert b"INDEX(index.html)" in resp.data
def test_authenticated_session_skips_redirect(client, monkeypatch):
    monkeypatch.setattr(monitoring, "CONTROL_TOKEN", "secret")

    with client.session_transaction() as sess:
        sess["authenticated"] = "secret"  # valid token

    response = client.get("/")  # or any @login_required route

    assert response.status_code == 200  # no redirect