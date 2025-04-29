# tests/test_monitoring.py
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))
import configparser
import pytest
import pathlib
from pathlib import Path
from datetime import datetime, timedelta
import psutil
import monitoring
from monitoring import create_app

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