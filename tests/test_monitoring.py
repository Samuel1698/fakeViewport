# tests/test_monitoring.py

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))
import configparser
import pytest
import monitoring                # monitoring.py :contentReference[oaicite:0]{index=0}&#8203;:contentReference[oaicite:1]{index=1}
from datetime import timedelta
import datetime as real_dt

# -----------------------------------------------------------------------------
# Fixture: create a Flask test client with a temp API directory
# -----------------------------------------------------------------------------
@pytest.fixture
def client(monkeypatch, tmp_path):
    # Prevent real log-file creation
    monkeypatch.setattr(monitoring, 'configure_logging', lambda *a, **k: None)

    # Freeze system‐uptime sources for predictability:  boot_time=1000, time.time()=1010
    monkeypatch.setattr(monitoring.psutil, 'boot_time', lambda: 1000)
    monkeypatch.setattr(monitoring.time, 'time', lambda: 1010)

    # Make a temporary API folder
    api_dir = tmp_path / "api"
    api_dir.mkdir()

    # Write a minimal config.ini pointing at our temp API folder
    cfg = configparser.ConfigParser()
    cfg['API'] = {'API_FILE_PATH': str(api_dir)}
    cfg['Logging'] = {
        'LOG_FILE': 'no',
        'LOG_CONSOLE': 'no',
        'VERBOSE_LOGGING': 'no',
        'LOG_DAYS': '1',
    }
    cfg_path = tmp_path / "config.ini"
    with open(cfg_path, 'w') as f:
        cfg.write(f)

    # Build app and test client
    app = monitoring.create_app(str(cfg_path))
    app.testing = True
    return app.test_client(), api_dir

# -----------------------------------------------------------------------------
# /api/check_view
# -----------------------------------------------------------------------------
def test_api_check_view_not_found(client):
    client, api_dir = client
    resp = client.get('/api/check_view')
    assert resp.status_code == 404
    data = resp.get_json()
    assert data['status'] == 'error'
    assert data['message'] == 'Status file not found'

def test_api_check_view_ok(client):
    client, api_dir = client
    # create status file
    status_file = api_dir / 'status.txt'
    status_file.write_text('healthy')
    resp = client.get('/api/check_view')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['status'] == 'ok'
    assert data['data']['view_status'] == 'healthy'

# -----------------------------------------------------------------------------
# /api/get_system_uptime
# -----------------------------------------------------------------------------
def test_api_get_system_uptime_ok(client):
    client, _ = client
    resp = client.get('/api/get_system_uptime')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['status'] == 'ok'
    # 1010 - 1000 = 10
    assert pytest.approx(data['data']['system_uptime'], rel=1e-3) == 10

def test_api_get_system_uptime_error(monkeypatch, client):
    # force boot_time to blow up
    monkeypatch.setattr(monitoring.psutil, 'boot_time', lambda: (_ for _ in ()).throw(Exception('fail')))
    client, _ = client
    resp = client.get('/api/get_system_uptime')
    assert resp.status_code == 500
    data = resp.get_json()
    assert data['status'] == 'error'
    assert data['message'] == 'Could not determine system uptime'

# -----------------------------------------------------------------------------
# /api/get_script_uptime
# -----------------------------------------------------------------------------
@pytest.mark.parametrize("raw, code, status, msg", [
    (None, 404, 'error', 'Script SST file not found'),
    ('not-a-timestamp', 400, 'error', 'Malformed timestamp in SST file'),
])
def test_api_get_script_uptime_errors(client, raw, code, status, msg):
    client, api_dir = client
    sst = api_dir / 'sst.txt'
    if raw is not None:
        sst.write_text(raw)
    resp = client.get('/api/get_script_uptime')
    assert resp.status_code == code
    data = resp.get_json()
    assert data['status'] == status
    assert data['message'] == msg

def test_api_get_script_uptime_ok(monkeypatch, client):
    client, api_dir = client

    # freeze datetime.now to a known value
    fixed_now = real_dt.datetime(2025, 4, 28, 12, 0, 10)
    class DummyDateTime:
        @classmethod
        def now(cls): return fixed_now
        @staticmethod
        def strptime(s, fmt): return real_dt.datetime.strptime(s, fmt)
    monkeypatch.setattr(monitoring, 'datetime', DummyDateTime)

    # write an SST timestamp exactly 10s before fixed_now
    earlier = fixed_now - real_dt.timedelta(seconds=10)
    (api_dir / 'sst.txt').write_text(earlier.strftime('%Y-%m-%d %H:%M:%S.%f'))

    resp = client.get('/api/get_script_uptime')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['status'] == 'ok'
    # expect ~10 seconds
    assert pytest.approx(data['data']['script_uptime'], rel=1e-3) == 10

# -----------------------------------------------------------------------------
# /api/admin
# -----------------------------------------------------------------------------
def test_api_admin_all_missing(client):
    client, _ = client
    resp = client.get('/api/admin')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['status'] == 'ok'
    assert data['data']['view_status'] == 'File not found'
    assert data['data']['script_uptime'] == 'File not found'
    assert pytest.approx(data['data']['system_uptime'], rel=1e-3) == 10

def test_api_admin_with_files(monkeypatch, client):
    client, api_dir = client

    # freeze datetime.now to 20s after a known start
    fixed_now = real_dt.datetime(2025, 4, 28, 12, 0, 20)
    class DummyDateTime2:
        @classmethod
        def now(cls): return fixed_now
        @staticmethod
        def strptime(s, fmt): return real_dt.datetime.strptime(s, fmt)
    monkeypatch.setattr(monitoring, 'datetime', DummyDateTime2)

    # write status.txt and sst.txt
    (api_dir / 'status.txt').write_text('OK')
    start = fixed_now - real_dt.timedelta(seconds=20)
    (api_dir / 'sst.txt').write_text(start.strftime('%Y-%m-%d %H:%M:%S.%f'))

    resp = client.get('/api/admin')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['status'] == 'ok'
    assert data['data']['view_status'] == 'OK'
    assert pytest.approx(data['data']['script_uptime'], rel=1e-3) == 20
    assert pytest.approx(data['data']['system_uptime'], rel=1e-3) == 10

def test_api_admin_system_error(monkeypatch, client):
    # force boot_time to error so system_uptime becomes 'Error'
    monkeypatch.setattr(monitoring.psutil, 'boot_time', lambda: (_ for _ in ()).throw(Exception('fail')))
    client, _ = client
    resp = client.get('/api/admin')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['status'] == 'ok'
    assert data['data']['system_uptime'] == 'Error'
