import pytest
from datetime import datetime as real_datetime, time as timecls, timedelta
from pathlib import Path
import psutil, builtins, subprocess, io
import monitoring
from types import SimpleNamespace
# ----------------------------------------------------------------------------- 
# Fake out datetime.now() for determinism
# ----------------------------------------------------------------------------- 
class DummyDateTime:
    _fixed_now = real_datetime(2023, 1, 1, 12, 0, 0)
    
    @classmethod
    def now(cls): 
        return cls._fixed_now

    @staticmethod
    def combine(d, t):
        # use the real datetime.combine
        from datetime import datetime as real_datetime
        return real_datetime.combine(d, t)

    @staticmethod
    def strptime(s, fmt):
        from datetime import datetime as real_datetime
        return real_datetime.strptime(s, fmt)

@pytest.fixture(autouse=True)
def patch_datetime(monkeypatch):
    monkeypatch.setattr(monitoring, 'datetime', DummyDateTime)
    monkeypatch.setattr(monitoring, 'timedelta', timedelta)
    yield

@pytest.fixture
def restart_times(request):
    # Provides the raw string passed via @pytest.mark.parametrize.
    return getattr(request, 'param', '')

def test_dummy_datetime_now():
    # Set a specific test time
    test_time = real_datetime(2023, 1, 2, 10, 30, 0)
    DummyDateTime._fixed_now = test_time
    
    # Verify now() returns what we set
    assert DummyDateTime.now() == test_time
    
    import monitoring
    assert monitoring.datetime.now() == test_time
# ----------------------------------------------------------------------------- 
# Helper to build a client with a given RESTART_TIMES string
# ----------------------------------------------------------------------------- 
@pytest.fixture
def client(tmp_path, monkeypatch, restart_times):
    # stub out the shared validate_config(...) to return exactly what we need
    # convert the restart_times string into a list of time objects
    times = [
        timecls(*map(int, t.split(':')))
        for t in restart_times.split(',') if t.strip()
    ]
    cfg = SimpleNamespace(
        CONTROL_TOKEN='',
        host='',
        port='',
        SLEEP_TIME=300,                
        LOG_INTERVAL=15,              
        RESTART_TIMES=times,
        LOG_FILE_FLAG=True,
        LOG_CONSOLE=True,
        DEBUG_LOGGING=False,
        LOG_DAYS=7,
        # Where monitoring will read/write files:
        mon_file=tmp_path / 'api' / 'mon.txt',
        log_file=tmp_path / 'logs' / 'viewport.log',
        sst_file=tmp_path / 'api' / 'sst.txt',
        status_file=tmp_path / 'api' / 'status.txt',
    )
    monkeypatch.setattr(monitoring, 'validate_config', lambda **kw: cfg)

    # stub out configure_logging (so we don't reconfigure pytest's caplog)
    monkeypatch.setattr(monitoring, 'configure_logging', lambda *a, **k: None)

    # force script_dir → tmp_path, and create the subdirectories
    monkeypatch.setattr(monitoring, 'script_dir', tmp_path)
    # make sure the dirs exist so endpoints that write/read them work:
    (tmp_path / 'api').mkdir(exist_ok=True)
    (tmp_path / 'logs').mkdir(exist_ok=True)

    # fake psutil / time
    monkeypatch.setattr(monitoring.psutil, 'boot_time',    lambda: 1000)
    monkeypatch.setattr(monitoring.time,    'time',        lambda: 1010)
    class DummyVM:
        used  = 12345
        total = 67890
    monkeypatch.setattr(monitoring.psutil, 'virtual_memory', lambda: DummyVM)

    # build the Flask client
    app = monitoring.create_app()
    app.testing = True
    return app.test_client()
# ----------------------------------------------------------------------------- 
# /api index
# ----------------------------------------------------------------------------- 
def test_api_index_links(client):
    resp = client.get('/api')
    assert resp.status_code == 200
    data = resp.get_json()
    expected = {
        'update',
        'update/changelog',
        'script_uptime',
        'system_info',
        'logs',
        'status',
        'config',
    }
    assert set(data.keys()) == expected
    for key, url in data.items():
        assert url.endswith(f'/api/{key}')

# ----------------------------------------------------------------------------- 
# /api/script_uptime
# ----------------------------------------------------------------------------- 
def test_script_uptime_missing(client):
    resp = client.get('/api/script_uptime')
    assert resp.status_code == 404
    obj = resp.get_json()
    assert obj['status'] == 'error'
    assert 'SST file not found' in obj['message']

def test_script_uptime_malformed(client, tmp_path, monkeypatch):
    # point monitoring.script_dir at a tmp dir
    monkeypatch.setattr(monitoring, 'script_dir', tmp_path)

    # compute the api_dir exactly like the app does
    api_dir: Path = monitoring.script_dir / 'api'
    api_dir.mkdir(parents=True, exist_ok=True)

    (api_dir / 'sst.txt').write_text('not a timestamp')
    resp = client.get('/api/script_uptime')
    assert resp.status_code == 400
    obj = resp.get_json()
    assert obj['status'] == 'error'
    assert 'Malformed SST timestamp' in obj['message']

def test_script_uptime_ok(client, tmp_path, monkeypatch):
    # point monitoring.script_dir at a tmp dir
    monkeypatch.setattr(monitoring, 'script_dir', tmp_path)

    # compute the api_dir exactly like the app does
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
# ----------------------------------------------------------------------------- 
# /api/system_info
# ----------------------------------------------------------------------------- 
def test_api_system_info_ok(client, monkeypatch):
    # Mock the network statistics
    class LastNetIO:
        bytes_sent = 500  # initial value
        bytes_recv = 1000  # initial value
        
    class CurrentNetIO:
        bytes_sent = 1000  # current value (500 more than last)
        bytes_recv = 2000  # current value (1000 more than last)
        
    def mock_net_io_counters(pernic, nowrap):
        return {'eth0': CurrentNetIO()}
    
    # Mock last_net_io and last_check_time
    monkeypatch.setattr(monitoring, 'last_net_io', {'eth0': LastNetIO()})
    monkeypatch.setattr(monitoring, 'last_check_time', 1009)  # 1 second before current time (1010)
    
    # Existing mocks
    def fake_open(path, mode='r', *args, **kwargs):
        if path == "/etc/os-release": return io.StringIO('PRETTY_NAME="TestOS"\n')
        elif path == "/proc/device-tree/model": return io.StringIO("FakeModel")

    monkeypatch.setattr(builtins, "open", fake_open)
    monkeypatch.setattr(subprocess, "check_output", lambda args: b"Filesystem\n100G\n")
    monkeypatch.setattr(psutil, "virtual_memory", lambda: SimpleNamespace(used=12345, total=67890, percent=50))
    monkeypatch.setattr(psutil, "boot_time", lambda: 1000)
    monkeypatch.setattr(psutil, "cpu_percent", lambda interval: 10)
    monkeypatch.setattr(psutil, "cpu_count", lambda logical: 4 if logical else 2)
    monkeypatch.setattr(psutil, "net_io_counters", mock_net_io_counters)
    monkeypatch.setattr(monitoring.time, "time", lambda: 1010)

    resp = client.get("/api/system_info")
    assert resp.status_code == 200
    data = resp.get_json()["data"]

    assert data["os_name"] == "TestOS"
    assert data["hardware_model"] == "FakeModel"
    assert data["disk_available"] == "100G"
    assert data["memory"]["used"] == 12345
    assert data["memory"]["total"] == 67890
    assert pytest.approx(data["system_uptime"], rel=1e-3) == 10
    
    # Network assertions
    assert "network" in data
    assert "interfaces" in data["network"]
    assert "eth0" in data["network"]["interfaces"]
    
    # Calculate expected rates:
    # Time elapsed = 1010 - 1009 = 1 second
    # Upload: (1000 - 500) / 1 = 500 bytes/sec
    # Download: (2000 - 1000) / 1 = 1000 bytes/sec
    assert data["network"]["interfaces"]["eth0"]["upload"] == pytest.approx(500.0)
    assert data["network"]["interfaces"]["eth0"]["download"] == pytest.approx(1000.0)
    assert data["network"]["interfaces"]["eth0"]["total_upload"] == 1000
    assert data["network"]["interfaces"]["eth0"]["total_download"] == 2000
def test_api_system_info_fallback_hardware_model(client, monkeypatch):
    # Mock network stats
    class DummyNetIO:
        bytes_sent = 1000
        bytes_recv = 2000
        
    def mock_net_io_counters(pernic, nowrap):
        return {'eth0': DummyNetIO()}
    
    monkeypatch.setattr(monitoring, 'last_net_io', {'eth0': DummyNetIO()})
    monkeypatch.setattr(monitoring, 'last_check_time', 149)
    monkeypatch.setattr(psutil, "net_io_counters", mock_net_io_counters)
    monkeypatch.setattr(psutil, "cpu_percent", lambda interval: 10)
    monkeypatch.setattr(psutil, "cpu_count", lambda logical: 4 if logical else 2)

    # Rest of existing mocks
    def fake_open(path, mode='r', *args, **kwargs):
        if path == "/etc/os-release": return io.StringIO('PRETTY_NAME="TestOS"\n')
        elif path == "/proc/device-tree/model": return io.StringIO("")
        elif path == "/sys/class/dmi/id/product_name": return io.StringIO("XModel")

    monkeypatch.setattr(builtins, "open", fake_open)
    monkeypatch.setattr(subprocess, "check_output", lambda args: b"Filesystem\n50G\n")
    monkeypatch.setattr(psutil, "virtual_memory", lambda: SimpleNamespace(used=1111, total=2222, percent=50))
    monkeypatch.setattr(psutil, "boot_time", lambda: 100)
    monkeypatch.setattr(monitoring.time, "time", lambda: 150)

    resp = client.get("/api/system_info")
    assert resp.status_code == 200
    data = resp.get_json()["data"]

    assert data["os_name"] == "TestOS"
    assert data["hardware_model"] == "XModel"
    assert data["disk_available"] == "50G"
    assert data["memory"]["used"] == 1111
    assert data["memory"]["total"] == 2222
    assert pytest.approx(data["system_uptime"], rel=1e-3) == 50
    assert "network" in data  # Verify network section exists
def test_api_system_info_both_open_fail_hardware_unknown(client, monkeypatch):
    # Mock network stats
    class DummyNetIO:
        bytes_sent = 1000
        bytes_recv = 2000
        
    def mock_net_io_counters(pernic, nowrap):
        return {'eth0': DummyNetIO()}
    
    monkeypatch.setattr(monitoring, 'last_net_io', {'eth0': DummyNetIO()})
    monkeypatch.setattr(monitoring, 'last_check_time', 259)
    monkeypatch.setattr(psutil, "net_io_counters", mock_net_io_counters)
    monkeypatch.setattr(psutil, "cpu_percent", lambda interval: 10)
    monkeypatch.setattr(psutil, "cpu_count", lambda logical: 4 if logical else 2)

    def fake_open(path, mode='r', *args, **kwargs):
        if path == "/etc/os-release": return io.StringIO('PRETTY_NAME="TestOS"\n')

    monkeypatch.setattr(builtins, "open", fake_open)
    monkeypatch.setattr(subprocess, "check_output", lambda args: b"Filesystem\n75G\n")
    monkeypatch.setattr(psutil, "virtual_memory", lambda: SimpleNamespace(used=3333, total=4444, percent=50))
    monkeypatch.setattr(psutil, "boot_time", lambda: 200)
    monkeypatch.setattr(monitoring.time, "time", lambda: 260)

    resp = client.get("/api/system_info")
    assert resp.status_code == 200
    data = resp.get_json()["data"]

    assert data["os_name"] == "TestOS"
    assert data["hardware_model"] == "Unknown"
    assert data["disk_available"] == "75G"
    assert data["memory"]["used"] == 3333
    assert data["memory"]["total"] == 4444
    assert pytest.approx(data["system_uptime"], rel=1e-3) == 60
    assert "network" in data  # Verify network section exists
def test_api_system_info_network_stats(client, monkeypatch):
    # Mock initial network stats
    class InitialNetIO:
        bytes_sent = 1000
        bytes_recv = 2000
        
    # Mock current network stats (after 1 second)
    class CurrentNetIO:
        bytes_sent = 2000  # 1000 bytes more
        bytes_recv = 3000  # 1000 bytes more
        
    def mock_net_io_counters(pernic, nowrap):
        return {'eth0': CurrentNetIO()}
    
    # Set initial state
    monkeypatch.setattr(monitoring, 'last_net_io', {'eth0': InitialNetIO()})
    monkeypatch.setattr(monitoring, 'last_check_time', 1009)
    monkeypatch.setattr(psutil, "net_io_counters", mock_net_io_counters)
    
    # Other required mocks
    monkeypatch.setattr(builtins, "open", lambda path, mode: io.StringIO('PRETTY_NAME="TestOS"\n'))
    monkeypatch.setattr(subprocess, "check_output", lambda args: b"Filesystem\n100G\n")
    monkeypatch.setattr(psutil, "virtual_memory", lambda: SimpleNamespace(used=0, total=0, percent=0))
    monkeypatch.setattr(psutil, "boot_time", lambda: 1000)
    monkeypatch.setattr(psutil, "cpu_percent", lambda interval: 0)
    monkeypatch.setattr(psutil, "cpu_count", lambda logical: 0)
    monkeypatch.setattr(monitoring.time, "time", lambda: 1010)

    resp = client.get("/api/system_info")
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    
    network = data["network"]
    assert network["interfaces"]["eth0"]["upload"] == pytest.approx(1000)  # (2000-1000)/1
    assert network["interfaces"]["eth0"]["download"] == pytest.approx(1000)  # (3000-2000)/1
    assert network["interfaces"]["eth0"]["total_upload"] == 2000
    assert network["interfaces"]["eth0"]["total_download"] == 3000  
def test_api_system_info_first_call_no_last_net_io(client, monkeypatch):
    # Mock network stats with no last_net_io (first call)
    class CurrentNetIO:
        bytes_sent = 1000
        bytes_recv = 2000
        
    def mock_net_io_counters(pernic, nowrap):
        return {'eth0': CurrentNetIO()}
    
    # Set last_net_io to None to test the else: pass branch
    monkeypatch.setattr(monitoring, 'last_net_io', None)
    monkeypatch.setattr(monitoring, 'last_check_time', 1009)
    monkeypatch.setattr(psutil, "net_io_counters", mock_net_io_counters)
    monkeypatch.setattr(psutil, "cpu_percent", lambda interval: 10)
    monkeypatch.setattr(psutil, "cpu_count", lambda logical: 4 if logical else 2)

    # Other required mocks
    def fake_open(path, mode='r', *args, **kwargs):
        if path == "/etc/os-release": return io.StringIO('PRETTY_NAME="TestOS"\n')
        elif path == "/proc/device-tree/model": return io.StringIO("FakeModel")

    monkeypatch.setattr(builtins, "open", fake_open)
    monkeypatch.setattr(subprocess, "check_output", lambda args: b"Filesystem\n100G\n")
    monkeypatch.setattr(psutil, "virtual_memory", lambda: SimpleNamespace(used=12345, total=67890, percent=50))
    monkeypatch.setattr(psutil, "boot_time", lambda: 1000)
    monkeypatch.setattr(monitoring.time, "time", lambda: 1010)

    resp = client.get("/api/system_info")
    assert resp.status_code == 200
    data = resp.get_json()["data"]

    # Verify network section exists but has no interfaces (since we passed the else: pass)
    assert "network" in data
    assert "interfaces" in data["network"]
    assert data["network"]["interfaces"] == {}  # No interfaces added when last_net_io is None
    assert data["network"]["primary_interface"] is None
def test_api_system_info_error(client, monkeypatch):
    # Force an exception during system info collection by making os-release
    # unreadable. Should return 500 with "System info error: ..."
    def mock_open(*args, **kwargs):
        # Force open() to raise when reading /etc/os-release
        if args[0] == '/etc/os-release': raise IOError("forced file read error")
    
    monkeypatch.setattr(builtins, 'open', mock_open)
    
    resp = client.get("/api/system_info")
    assert resp.status_code == 500
    payload = resp.get_json()
    assert payload["status"] == "error"
    assert "System info error: forced file read error" in payload["message"]
# ----------------------------------------------------------------------------- 
# /api/logs?limit
# ----------------------------------------------------------------------------- 
def test_default_limit_returns_100_lines(client, tmp_path, monkeypatch):
    client_app = client
    # point script_dir at tmp
    monkeypatch.setattr(monitoring, 'script_dir', tmp_path)

    # create logs/viewport.log
    logs_dir = monitoring.script_dir / 'logs'
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / 'viewport.log'

    # write 150 entries
    lines = [f"entry {i}" for i in range(150)]
    log_path.write_text("\n".join(lines) + "\n")

    # call endpoint
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
    resp = client_app.get("/api/logs?limit=string")
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
    assert "An internal error occurred while reading logs" in body["message"]

# ----------------------------------------------------------------------------- 
# /api/status
# ----------------------------------------------------------------------------- 
def test_status_missing(client):
    resp = client.get('/api/status')
    assert resp.status_code == 404
    obj = resp.get_json()
    assert obj['status'] == 'error'
    assert 'Status file not found' in obj['message']

def test_status_ok(client, tmp_path, monkeypatch):
    # point monitoring.script_dir at a tmp dir
    monkeypatch.setattr(monitoring, 'script_dir', tmp_path)

    # compute the api_dir exactly like the app does
    api_dir: Path = monitoring.script_dir / 'api'
    api_dir.mkdir(parents=True, exist_ok=True)

    (api_dir / 'status.txt').write_text('All Good')
    resp = client.get('/api/status')
    assert resp.status_code == 200
    obj = resp.get_json()
    assert obj['status'] == 'ok'
    assert obj['data']['status'] == 'All Good'
    
# ----------------------------------------------------------------------------- 
# /api/config
# ----------------------------------------------------------------------------- 
def test_api_config_no_restart(client, monkeypatch):
    # When RESTART_TIMES is an empty list, /api/config should return
    # restart_times = None and next_restart = None.
    fake_cfg = SimpleNamespace(
        SLEEP_TIME=5,
        WAIT_TIME=10,
        MAX_RETRIES=3,
        RESTART_TIMES=[],
        BROWSER_PROFILE_PATH=None,
        BROWSER_BINARY=None,
        HEADLESS=None,
    )
    monkeypatch.setattr(monitoring, "validate_config", lambda strict=False, print=False: fake_cfg)

    resp = client.get("/api/config")
    assert resp.status_code == 200
    data = resp.get_json()["data"]["general"]
    assert data["restart_times"] is None
    assert data["next_restart"] is None

def test_api_config_with_restart(client, monkeypatch):
    # When RESTART_TIMES contains a single time (“09:00”), /api/config should
    # return restart_times = ["09:00"] and compute next_restart correctly
    # based on a fixed current time of 2025-06-01 08:00:00.
    fake_cfg = SimpleNamespace(
        SLEEP_TIME=5,
        WAIT_TIME=10,
        MAX_RETRIES=3,
        RESTART_TIMES=[timecls(9, 0)],
        BROWSER_PROFILE_PATH=None,
        BROWSER_BINARY=None,
        HEADLESS=None,
    )
    monkeypatch.setattr(monitoring, "validate_config", lambda strict=False, print=False: fake_cfg)

    fixed_now = real_datetime(2025, 6, 1, 8, 0, 0)
    monkeypatch.setattr(monitoring.datetime, "now", classmethod(lambda cls: fixed_now))

    resp = client.get("/api/config")
    assert resp.status_code == 200
    general = resp.get_json()["data"]["general"]

    assert general["restart_times"] == ["09:00"]
    assert general["next_restart"] == "2025-06-01T09:00:00"
    
def test_api_config_compute_error(client, monkeypatch):
    # Force an exception during the "compute restart_times / next_restart" block
    # by having datetime.now() raise. Expect a 500 response with "Config error: ..."
    class ErrorDateTime:
        # Setup error-raising datetime
        @classmethod
        def now(cls):
            raise RuntimeError("forced failure")
    
    monkeypatch.setattr(monitoring, 'datetime', ErrorDateTime)

    # Setup config with restart times (same as working test)
    fake_cfg = SimpleNamespace(
        SLEEP_TIME=5,
        WAIT_TIME=10,
        MAX_RETRIES=3,
        RESTART_TIMES=[timecls(9, 0)],
    )
    monkeypatch.setattr(monitoring, 'validate_config', lambda strict=False, print=False: fake_cfg)

    resp = client.get("/api/config")
    assert resp.status_code == 500
    payload = resp.get_json()
    assert payload["status"] == "error"
    assert "Config error: forced failure" in payload["message"]