import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))
import pytest
import configparser
from datetime import datetime as real_datetime, time as timecls, timedelta
import pathlib
from pathlib import Path
import monitoring
from monitoring import create_app

# ─────────────────────────────────────────────────────
# 1) Fake out datetime.now() for determinism
# ─────────────────────────────────────────────────────
class DummyDateTime:
    @classmethod
    def now(cls):
        return cls._fixed_now

    @staticmethod
    def combine(d, t):
        # use the real datetime.combine
        return real_datetime.combine(d, t)

    @staticmethod
    def strptime(s, fmt):
        return real_datetime.strptime(s, fmt)

@pytest.fixture(autouse=True)
def patch_datetime(monkeypatch):
    # Replace the module‐level datetime & timedelta
    monkeypatch.setattr(monitoring, 'datetime', DummyDateTime)
    monkeypatch.setattr(monitoring, 'timedelta', timedelta)
    yield
@pytest.fixture
def restart_times(request):
    # Provides the string value passed via @pytest.mark.parametrize(..., indirect=True)
    return getattr(request, 'param', '')

# ─────────────────────────────────────────────────────
# 2) Helper to build a client with a given RESTART_TIMES string
# ─────────────────────────────────────────────────────
@pytest.fixture
def client(tmp_path, monkeypatch, restart_times):
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
    cfg = configparser.ConfigParser()
    cfg['General'] = {
        'SLEEP_TIME':   '300',
        'LOG_INTERVAL': '15',
        'RESTART_TIMES': restart_times,        
    }
    cfg['Logging'] = {
        'LOG_FILE':       'False',
        'LOG_CONSOLE':    'False',
        'VERBOSE_LOGGING':'False',
        'LOG_DAYS':       '1',
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

# -------------------------
# /api/next_restart
# -------------------------
@pytest.mark.parametrize('restart_times', [''], indirect=True)
def test_no_restart_times(client):
    resp = client.get('/api/next_restart')
    assert resp.status_code == 404
    body = resp.get_json()
    assert body['status'] == 'error'
    assert 'No restart times configured' in body['message']

@pytest.mark.parametrize('restart_times', ['15:30'], indirect=True)
def test_single_time_future_today(client):
    # freeze “now” at 2025-05-08 10:00:00
    DummyDateTime._fixed_now = real_datetime(2025, 5, 8, 10, 0, 0)

    resp = client.get('/api/next_restart')
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['status'] == 'ok'

    expected_dt = DummyDateTime.combine(
        DummyDateTime._fixed_now.date(),
        timecls(15, 30)
    ).isoformat()
    assert body['data']['next_restart'] == expected_dt

@pytest.mark.parametrize('restart_times', ['15:30'], indirect=True)
def test_single_time_already_passed_today(client):
    # freeze “now” at 2025-05-08 18:00:00
    DummyDateTime._fixed_now = real_datetime(2025, 5, 8, 18, 0, 0)

    resp = client.get('/api/next_restart')
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['status'] == 'ok'

    tomorrow = DummyDateTime._fixed_now.date() + timedelta(days=1)
    expected_dt = DummyDateTime.combine(tomorrow, timecls(15, 30)).isoformat()
    assert body['data']['next_restart'] == expected_dt

@pytest.mark.parametrize('restart_times', ['18:00,01:00'], indirect=True)
def test_multiple_times_choose_earliest(client):
    # freeze “now” at 2025-05-08 16:45:00
    DummyDateTime._fixed_now = real_datetime(2025, 5, 8, 16, 45, 0)

    resp = client.get('/api/next_restart')
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['status'] == 'ok'

    today_run    = DummyDateTime.combine(DummyDateTime._fixed_now.date(),   timecls(18, 0))
    tomorrow_run = DummyDateTime.combine(DummyDateTime._fixed_now.date() + timedelta(days=1), timecls(1, 0))
    expected_dt  = min(today_run, tomorrow_run).isoformat()

    assert body['data']['next_restart'] == expected_dt

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
