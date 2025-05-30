import update as uu, importlib
from unittest.mock import patch
import pytest, monitoring

@pytest.fixture
def dummy_repo(tmp_path, monkeypatch):
    # Create an isolated fake repo tree: VERSION + .git dir.
    (tmp_path / "VERSION").write_text("0.1.0\n")
    (tmp_path / ".git").mkdir()
    importlib.reload(uu)  # re-evaluate constants
    # point update module at our fake repo
    monkeypatch.setattr(uu, "ROOT", tmp_path)
    monkeypatch.setattr(uu, "VERS", tmp_path / "VERSION")
    yield tmp_path
    importlib.reload(uu)  # clean up


@pytest.fixture
def app_client(dummy_repo, monkeypatch):
    monkeypatch.setattr(monitoring, "configure_logging", lambda *a, **k: None)
    app = monitoring.create_app()
    app.testing = True
    return app.test_client()


@patch.object(uu, "latest_version", lambda: "0.2.0")
def test_update_info_endpoint(app_client):
    r = app_client.get("/update")
    data = r.get_json()["data"]
    assert data == {"current": "0.1.0", "latest": "0.2.0"}

def test_update_info_endpoint_error(app_client, monkeypatch, caplog):
    # /update returns 500 + logs when the version-check fails

    # Force update.latest_version() to raise
    def _boom():
        raise RuntimeError("network unreachable")
    monkeypatch.setattr(uu, "latest_version", _boom)

    # capture the log produced by app.logger.exception(...)
    caplog.set_level("ERROR")

    resp = app_client.get("/update")

    # Response 
    assert resp.status_code == 500
    payload = resp.get_json()
    assert payload["status"] == "error"
    assert "network unreachable" in payload["message"]

    # Log message 
    assert "version check failed" in caplog.text
    
@pytest.mark.parametrize("clean,expect_git", [(True, True), (False, False)])
def test_perform_update_paths(dummy_repo, monkeypatch, clean, expect_git):
    monkeypatch.setattr(uu, "latest_version", lambda: "0.2.0")
    monkeypatch.setattr(uu, "_clean_worktree", lambda: clean)
    called = {"git": False, "tar": False}

    def fake_git(tag):
        called["git"] = True
        return clean

    def fake_tar(tag):
        called["tar"] = True
        return not clean

    monkeypatch.setattr(uu, "update_via_git", fake_git)
    monkeypatch.setattr(uu, "update_via_tar", fake_tar)

    result = uu.perform_update()
    assert ("git" in result) is expect_git
    assert called["git"] == expect_git
    assert called["tar"] == (not expect_git)


def test_apply_endpoint_isolated(app_client, monkeypatch):
    # stub perform_update to avoid any real git/tar calls
    monkeypatch.setattr(uu, "perform_update", lambda: "ok")
    r = app_client.post("/update/apply", json={})
    assert r.status_code == 202
    assert r.get_json()["data"]["outcome"] == "ok"


def test_perform_update_git_error_fallback_to_tar(dummy_repo, monkeypatch):
    # Simulate git raising an exception; tar should then be called and succeed.
    monkeypatch.setattr(uu, "latest_version", lambda: "0.2.0")
    monkeypatch.setattr(uu, "_clean_worktree", lambda: True)
    called = {"git": False, "tar": False}

    def fake_git(tag):
        called["git"] = True
        raise RuntimeError("git checkout failed")

    def fake_tar(tag):
        called["tar"] = True
        return True

    monkeypatch.setattr(uu, "update_via_git", fake_git)
    monkeypatch.setattr(uu, "update_via_tar", fake_tar)

    result = uu.perform_update()
    assert "tar" in result
    assert called["git"] is True
    assert called["tar"] is True
    # And ensure the VERSION file got updated
    assert (dummy_repo / "VERSION").read_text().strip() == "0.2.0"
    
def test_current_version_reads_text(dummy_repo):
    # VERSION was written by the dummy_repo fixture -> "0.1.0\n"
    import update as uu
    assert uu.current_version() == "0.1.0"


@pytest.mark.parametrize("git_stdout,expected", [
    ("",      True),        # clean work-tree
    (" M x",  False),       # dirty    work-tree
])
def test_clean_worktree(monkeypatch, git_stdout, expected):
    import update as uu
    monkeypatch.setattr(uu.subprocess, "check_output",
                        lambda *a, **k: git_stdout)
    assert uu._clean_worktree() is expected


@pytest.mark.parametrize("raises,expected", [
    (False, True),                      # git OK
    (True,  False),                     # git fails -> logs + False
])
def test_git_ok(monkeypatch, caplog, raises, expected):
    import update as uu
    def fake_check(cmd, **kw):
        if raises:
            raise uu.subprocess.CalledProcessError(1, cmd, "boom")
        return "fine"
    monkeypatch.setattr(uu.subprocess, "check_output", fake_check)
    caplog.set_level("ERROR")
    assert uu._git_ok(["git"]) is expected
    if raises:
        assert "git failed: boom" in caplog.text

# ----------------------------------------------------------------------------- 
# update_via_git paths (clean vs dirty tree, success vs failure)
# -----------------------------------------------------------------------------
@pytest.mark.parametrize("clean,step_ok,expected", [
    (False, True,  False),   # dirty tree -> abort early
    (True,  True,  True),    # all steps succeed
    (True,  False, False),   # any step fails -> False
])
def test_update_via_git(monkeypatch, clean, step_ok, expected):
    import update as uu
    monkeypatch.setattr(uu, "_clean_worktree", lambda: clean)
    # record every step that _git_ok receives
    steps = []
    monkeypatch.setattr(uu, "_git_ok", lambda cmd: steps.append(cmd) or step_ok)
    assert uu.update_via_git("0.2.0") is expected
    if not clean:
        assert steps == []
    else:
        expected_len = 3 if step_ok else 1
        assert len(steps) == expected_len
# ----------------------------------------------------------------------------- 
# update_via_tar success and failure paths
# -----------------------------------------------------------------------------
class _DummyHTTP:
    def __enter__(self):  return self
    def __exit__(self, *a): pass
    def read(self):       return b"tar-bytes"

class _DummyTar:
    def __enter__(self):  return self
    def __exit__(self, *a): pass
    def extractall(self, path): self.extracted_to = path

@pytest.mark.parametrize("should_fail", [False, True])
def test_update_via_tar(monkeypatch, should_fail, tmp_path):
    import update as uu
    monkeypatch.setattr(uu, "ROOT", tmp_path)         # avoid writing outside tmp
    # stub out urlopen and tarfile.open
    if should_fail:
        monkeypatch.setattr(uu, "urlopen",
                            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("net down")))
    else:
        monkeypatch.setattr(uu, "urlopen", lambda *a, **k: _DummyHTTP())
        monkeypatch.setattr(uu.tarfile, "open", lambda *a, **k: _DummyTar())
    assert uu.update_via_tar("0.2.0") is (not should_fail)

# ----------------------------------------------------------------------------- 
# perform_update edge cases still missing
# -----------------------------------------------------------------------------
def test_perform_update_already_current(dummy_repo, monkeypatch):
    import update as uu
    monkeypatch.setattr(uu, "latest_version", lambda: "0.1.0")  # same as current
    assert uu.perform_update() == "already-current"

def test_perform_update_tar_only_path(dummy_repo, monkeypatch):
    # No .git folder → perform_update must jump straight to the tar strategy.
    import update as uu
    # remove the .git dir created by fixture
    (dummy_repo / ".git").rmdir()
    monkeypatch.setattr(uu, "latest_version", lambda: "0.2.0")
    monkeypatch.setattr(uu, "_clean_worktree", lambda: True)  # ignored, but safe
    monkeypatch.setattr(uu, "update_via_tar", lambda tag: True)
    res = uu.perform_update()
    assert res.startswith("updated-to-0.2.0-via-tar")
    # VERSION file should be updated
    assert (dummy_repo / "VERSION").read_text().strip() == "0.2.0"

def test_latest_version_parses_tag(monkeypatch):
    import io, update as uu

    class DummyResp(io.StringIO):
        def __enter__(self): return self
        def __exit__(self, *exc): pass

    # Fake GitHub API JSON payload
    monkeypatch.setattr(
        uu, "urlopen",
        lambda url, timeout=5: DummyResp('{"tag_name": "v9.9.9"}')
    )

    assert uu.latest_version() == "9.9.9"

def test_perform_update_all_strategies_fail(dummy_repo, monkeypatch):
    import update as uu

    monkeypatch.setattr(uu, "latest_version",   lambda: "0.2.0")
    monkeypatch.setattr(uu, "_clean_worktree",  lambda: True)

    called = {"git": False, "tar": False}

    monkeypatch.setattr(uu, "update_via_git", lambda tag: called.update(git=True) or False)
    monkeypatch.setattr(uu, "update_via_tar", lambda tag: called.update(tar=True) or False)

    outcome = uu.perform_update()

    assert outcome == "update-failed"
    assert called == {"git": True, "tar": True}
    # VERSION file must stay untouched
    assert (dummy_repo / "VERSION").read_text().strip() == "0.1.0"