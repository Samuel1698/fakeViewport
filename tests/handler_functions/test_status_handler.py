import pytest
import viewport
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, call

# --------------------------------------------------------------------------- #
# Helper function and fixture
# --------------------------------------------------------------------------- #
@pytest.fixture(autouse=True)
def isolate_all_files(tmp_path, monkeypatch):
    fake_sst    = tmp_path / "sst.txt"
    fake_status = tmp_path / "status.txt"
    fake_log    = tmp_path / "viewport.log"

    fake_sst.write_text("2025-01-01 00:00:00.000000")
    fake_status.write_text("OK\n")
    fake_log.write_text("[INFO] test\n")

    monkeypatch.setattr(viewport, "sst_file",    fake_sst)
    monkeypatch.setattr(viewport, "status_file", fake_status)
    monkeypatch.setattr(viewport, "log_file",    fake_log)
    
    yield fake_sst, fake_status, fake_log
@pytest.fixture
def default_status_env(monkeypatch):
    # Monkey-patch all of the module-level globals that status_handler expects
    # so tests can drop them in by just requesting this fixture.
    monkeypatch.setattr(viewport, "__version__", "1.2.3",             raising=False)
    monkeypatch.setattr(viewport, "SLEEP_TIME",      10,              raising=False)
    monkeypatch.setattr(viewport, "LOG_INTERVAL",    5,               raising=False)
    monkeypatch.setattr(viewport, "RESTART_TIMES",   [],              raising=False)
    yield

# --------------------------------------------------------------------------- #
# Test for Status Handler
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "sst_exists, status_exists, log_content, process_names, expected_error, expected_output_snippets",
    [
        # All present → full status block, no errors
        (
            True, True, "[INFO] All good", ["viewport.py"],
            None,
            [
                "Fake Viewport 1.2.3",
                "Script Uptime:",
                "Monitoring API:",
                "Usage:",
                "Next Health Check:",
                "Last Status Update:",
                "Last Log Entry:",
            ],
        ),
        # Missing sst.txt → fallback to now, still prints uptime, no error
        (
            False, True, "[INFO] OK", ["viewport.py"],
            None,
            [
                "Script Uptime:",
                "Monitoring API:",
            ],
        ),
        # Missing status.txt → prints “Status file not found.” + logs error
        (
            True, False, "[INFO] OK", ["viewport.py"],
            "Status File not found",
            ["Status file not found."],
        ),
        # Missing log file → prints “Log file not found.” + logs error
        (
            True, True, None, ["viewport.py"],
            "Log File not found",
            ["Log file not found."],
        ),
        # Empty log file → prints “No log entries yet.”, no error
        (
            True, True, "", ["viewport.py"],
            None,
            ["Last Log Entry:", "No log entries yet."],
        ),
        # Script not running → uptime shows “Not Running”
        (
            True, True, "[INFO] OK", [], 
            None,
            ["Script Uptime:", "Not Running"],
        ),
    ]
)
@patch("viewport.time.time", return_value=0)
@patch("viewport.get_next_interval", return_value=60)
@patch("viewport.psutil.virtual_memory", return_value=SimpleNamespace(total=1024**3))
@patch("viewport.psutil.process_iter", return_value=[])
@patch("viewport.process_handler")
@patch("viewport.log_error")
def test_status_handler(
    mock_log_error,
    mock_process_handler,
    mock_process_iter,
    mock_virtual_memory,
    mock_get_next_interval,
    mock_time_time,
    sst_exists,
    status_exists,
    log_content,
    process_names,
    expected_error,
    expected_output_snippets,
    isolate_all_files,
    default_status_env,
    capsys,
):
    fake_sst, fake_status, fake_log = isolate_all_files

    # sst_exists?
    if not sst_exists:
        fake_sst.unlink()
    else:
        # overwrite with a fixed past timestamp
        fake_sst.write_text(
            datetime(2024, 4, 25, 12, 0, 0).strftime("%Y-%m-%d %H:%M:%S.%f")
        )

    # status_exists?
    if not status_exists:
        fake_status.unlink()
    else:
        fake_status.write_text("Feed Healthy\n")

    #log_content?
    if log_content is None:
        fake_log.unlink()
    else:
        fake_log.write_text(log_content)

    # stub process_handler: running iff name in process_names
    mock_process_handler.side_effect = lambda name, action="check": name in process_names

    # run
    viewport.status_handler()
    out = capsys.readouterr().out

    # assert error logging
    if expected_error:
        mock_log_error.assert_called_once()
        assert expected_error in mock_log_error.call_args[0][0]
    else:
        mock_log_error.assert_not_called()

    # assert expected output snippets
    for snippet in expected_output_snippets:
        assert snippet in out

@pytest.mark.parametrize(
    "status_text, sleep_time, next_interval, expected_sleep_snippet, expected_next_snippet, expected_status_color",
    [
        # status OK, sleep=45s, next=8s  →  sec‐only branch
        ("OK\n",      45,   8,    "45 sec",    "8s",      viewport.GREEN),
        # status crash → still prints restart; crash coloring for last status update
        ("Fatal Crash detected\n", 75, 65, "1 min 15 sec", "1m 5s", viewport.RED),
        # status starting → restart + starting coloring; sleep=120s → min-only
        ("Starting API\n", 120, 3665, "2 min", "1h 1m", viewport.YELLOW),
    ],
)
@patch("viewport.time.time", return_value=0)
@patch("viewport.get_next_interval")
@patch("viewport.psutil.virtual_memory", return_value=MagicMock(total=1024**3))
@patch("viewport.process_handler", return_value=True)
@patch("viewport.usage_handler", return_value=(0.0, 0.0))
@patch("viewport.get_cpu_color", return_value=viewport.GREEN)
@patch("viewport.get_mem_color", return_value=viewport.GREEN)
def test_status_handler_param(
    mock_mem_color,
    mock_cpu_color,
    mock_usage,
    mock_proc,
    mock_mem,
    mock_interval,
    mock_time,
    monkeypatch,
    default_status_env,
    isolate_all_files,
    capsys,
    status_text,
    sleep_time,
    next_interval,
    expected_sleep_snippet,
    expected_next_snippet,
    expected_status_color,
):
    fake_sst, fake_status, fake_log = isolate_all_files
    
    viewport.SLEEP_TIME  = sleep_time
    fake_status.write_text(status_text)

    # stub next-interval
    mock_interval.return_value = next_interval

    # enable restart (monkeypatch will undo this for us)
    monkeypatch.setattr(viewport, "RESTART_TIMES", ["23:00"], raising=False)
    monkeypatch.setattr(
        viewport,
        "get_next_restart",
        lambda now: "2025-05-12 23:00:00",
        raising=False
    )
    # act
    viewport.status_handler()
    out = capsys.readouterr().out

    # assert
    assert "Scheduled Restart:" in out
    assert expected_sleep_snippet in out
    assert expected_next_snippet in out

    # last status‐update line is colored as expected
    # we look for the pattern: <COLOR><stripped_status><NC>
    stripped = status_text.strip()
    assert f"{expected_status_color}{stripped}{viewport.NC}" in out

# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #
@patch("viewport.time.time", return_value=0)
@patch("viewport.get_next_interval", return_value=5)
@patch("viewport.psutil.virtual_memory", return_value=MagicMock(total=1024**3))
@patch("viewport.process_handler", return_value=True)
@patch("viewport.usage_handler", return_value=(0.0, 0.0))
@patch("viewport.get_cpu_color",  return_value=viewport.GREEN)
@patch("viewport.get_mem_color",  return_value=viewport.GREEN)
def test_status_handler_malformed_timestamp_covered(
    mock_mem_color,
    mock_cpu_color,
    mock_usage,
    mock_proc,
    mock_mem,
    mock_interval,
    mock_time,
    default_status_env,
    isolate_all_files,
    capsys
):
    fake_sst, fake_status, fake_log = isolate_all_files
    fake_sst.write_text("not-a-timestamp\n")
    
    viewport.status_handler()
    out = capsys.readouterr().out

    # inner except ValueError should fallback to now, so we still see Uptime
    assert "Script Uptime:" in out
    # and we never hit the outer FileNotFound
    assert "Uptime file not found" not in out
    
@patch("viewport.log_error")
@patch("viewport.process_handler", side_effect=FileNotFoundError)
def test_status_handler_outer_file_not_found(mock_proc, mock_log_error, capsys):
    # leave SST open real so the first inner try only wraps its open
    # but we stub process_handler to blow up
    # also make sure no other unpatched code trips
    # run
    viewport.status_handler()
    out = capsys.readouterr().out

    # should hit the outer except
    assert "Uptime file not found." in out
    mock_log_error.assert_called_once_with("Uptime File not found")

@patch("viewport.log_error")
@patch("viewport.usage_handler", side_effect=RuntimeError("boom"))
@patch("viewport.process_handler", return_value=True)
def test_status_handler_catches_generic_exception(
    mock_proc,
    mock_usage,
    mock_log_error,
    capsys,
):
    # act
    viewport.status_handler()
    out = capsys.readouterr().out

    # assert: no normal output
    assert out == ""

    # should have logged exactly the generic‐exception branch
    mock_log_error.assert_called_once()
    msg, exc = mock_log_error.call_args[0]
    assert msg == "Error while checking status: "
    assert isinstance(exc, RuntimeError)
    assert str(exc) == "boom"

# --------------------------------------------------------------------------- #
# Label colors
# --------------------------------------------------------------------------- #
@patch("viewport.time.time", return_value=0)
@patch("viewport.get_next_interval", return_value=10)
@patch("viewport.psutil.virtual_memory", return_value=MagicMock(total=1024**3))
@patch("viewport.process_handler", return_value=True)
@patch("viewport.usage_handler", return_value=(1.0, 1.0))
@patch("viewport.get_cpu_color")
@patch("viewport.get_mem_color")
def test_status_handler_label_color(
    mock_mem_color,
    mock_cpu_color,
    mock_usage,
    mock_proc,
    mock_mem,
    mock_interval,
    mock_time,
    capsys
):
    # stub get_cpu_color: RED for viewport.py, YELLOW for monitoring.py, else GREEN
    def cpu_color_side(proc_name, cpu):
        if proc_name == "viewport.py":
            return viewport.RED
        elif proc_name == "monitoring.py":
            return viewport.YELLOW
        else:
            return viewport.GREEN
    mock_cpu_color.side_effect = cpu_color_side

    # stub get_mem_color always GREEN (so mem_color never forces RED/YELLOW)
    mock_mem_color.side_effect = lambda pct: viewport.GREEN

    # act
    viewport.status_handler()
    out = capsys.readouterr().out

    # assert label colors per process
    # for label 'viewport'
    assert f"{viewport.RED}viewport" in out
    # for label 'api' (monitoring.py)
    assert f"{viewport.YELLOW}api" in out
    # for label equal to the BROWSER constant
    assert f"{viewport.GREEN}{viewport.BROWSER}" in out

@pytest.mark.parametrize("log_line, expected_color", [
    ("[ERROR] boom",    viewport.RED),
    ("[DEBUG] dbg",     viewport.CYAN),
    ("[WARNING] warn",  viewport.YELLOW),
    ("[INFO] info",     viewport.GREEN),
    ("plain text",      viewport.NC),
])
@patch("viewport.time.time", return_value=0)
@patch("viewport.get_next_interval", return_value=5)
@patch("viewport.psutil.virtual_memory", return_value=MagicMock(total=1024**3))
@patch("viewport.process_handler", return_value=True)
@patch("viewport.usage_handler", return_value=(0.0, 0.0))
@patch("viewport.get_cpu_color",  return_value=viewport.GREEN)
@patch("viewport.get_mem_color",  return_value=viewport.GREEN)
def test_status_handler_log_coloring(
    mock_mem_color,
    mock_cpu_color,
    mock_usage,
    mock_proc,
    mock_mem,
    mock_interval,
    mock_time,
    default_status_env,
    isolate_all_files,
    capsys,
    log_line,
    expected_color,
):  
    fake_sst, fake_status, fake_log = isolate_all_files  
    fake_log.write_text(log_line + "\n")
    
    # act
    viewport.status_handler()
    out = capsys.readouterr().out

    # assert: last log entry is wrapped in the expected color
    assert f"{expected_color}{log_line}{viewport.NC}" in out