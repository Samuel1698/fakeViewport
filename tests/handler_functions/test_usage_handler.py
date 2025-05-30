import pytest
import viewport
from types import SimpleNamespace
from unittest.mock import patch
# import your helper; adjust the path if needed
from tests.handler_functions.test_process_handler import _make_proc

@pytest.mark.parametrize("match_str, proc_specs, exp_cpu, exp_mem", [
    (
        "viewport",
        [
            # pid,     cmdline,              cpu,   mem
            (1,      "viewport.py",         3.0,   1000),
            (2,     ["python", "viewport"], 2.0,   2000),
            (3,      "other.py",            5.0,   3000),
        ],
        5.0, 3000
    ),
    (
        "chrome",
        [
            (1,       "chrome",            1.0,  100),
            (2,     ["chromedriver"],      2.0,  200),
            (3,      "unrelated",          9.0,  900),
        ],
        3.0, 300
    ),
    (
        "chromium",
        [
            (1,      "chromium",           1.0,  100),
            (2,  ["chromiumdriver"],       2.0,  200),
            (3,      "unrelated",          9.0,  900),
        ],
        3.0, 300
    ),
])
def test_usage_handler(match_str, proc_specs, exp_cpu, exp_mem, monkeypatch):
    # build fake procs
    procs = []
    for pid, cmdline, cpu, mem in proc_specs:
        proc = _make_proc(pid, cmdline)
        proc.cpu_percent.return_value   = cpu
        proc.memory_info.return_value   = SimpleNamespace(rss=mem)
        procs.append(proc)

    # patch psutil.process_iter
    monkeypatch.setattr(viewport.psutil, "process_iter", lambda attrs: procs)

    cpu, mem = viewport.usage_handler(match_str)
    assert cpu == pytest.approx(exp_cpu)
    assert mem == exp_mem

@patch("viewport.psutil.process_iter")
def test_usage_handler_ignores_exceptions(mock_process_iter):
    # one good process
    good = _make_proc(1, ["target_app"])
    good.cpu_percent.return_value     = 10.0
    good.memory_info.return_value     = SimpleNamespace(rss=100000)

    # one broken process
    bad = _make_proc(2, ["target_app"])
    bad.cpu_percent.side_effect       = Exception("denied")
    bad.memory_info.return_value      = SimpleNamespace(rss=50000)

    mock_process_iter.return_value = [good, bad]

    cpu, mem = viewport.usage_handler("target")
    assert cpu == pytest.approx(10.0)
    assert mem == 100000
