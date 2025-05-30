import io, importlib, types, base64, subprocess, json, tarfile, warnings
from pathlib import Path
from unittest.mock import patch
import pytest, monitoring
import update as uu
# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def dummy_repo(tmp_path, monkeypatch):
    # Create an isolated fake repo tree:  api/VERSION  +  .git dir
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "VERSION").write_text("0.1.0\n")
    (tmp_path / ".git").mkdir()

    importlib.reload(uu)              # ensure constants are rebound

    monkeypatch.setattr(uu, "ROOT", tmp_path)
    monkeypatch.setattr(uu, "VERS", tmp_path / "api" / "VERSION")
    monkeypatch.setattr(uu, "GIT",  ["git", "-C", str(tmp_path)])
    yield tmp_path
    importlib.reload(uu)              # restore globals for other tests

class DummyCM:
    def __enter__(self): return self
    def __exit__(self, *args): pass
    
class DummyResponse(io.StringIO):
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass
    
@pytest.fixture
def app_client(dummy_repo, monkeypatch):
    # Flask test-client with logging disabled for speed.
    monkeypatch.setattr(monitoring, "configure_logging", lambda *a, **k: None)
    app = monitoring.create_app()
    app.testing = True
    return app.test_client()
# ---------------------------------------------------------------------------
# current_version / latest_version
# ---------------------------------------------------------------------------
def test_current_version_reads_file(dummy_repo):
    assert uu.current_version() == "0.1.0"

def test_latest_version_success(monkeypatch):
    class _JSON(io.StringIO):
        def __enter__(self): return self
        def __exit__(self, *exc): pass

    monkeypatch.setattr(
        uu, "_github",
        lambda url, **kw: _JSON('{"tag_name":"v9.9.9"}')
    )
    assert uu.latest_version() == "9.9.9"

def test_latest_version_http_error(monkeypatch):
    from urllib.error import HTTPError
    err = HTTPError(None, 403, "nope", None, None)
    monkeypatch.setattr(uu, "_github", lambda *a, **k: (_ for _ in ()).throw(err))
    assert uu.latest_version() == "update-failed"
# ---------------------------------------------------------------------------
# helpers: _clean_worktree / _current_branch / _default_branch
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("stdout,expected", [("", True), (" M file", False)])
def test_clean_worktree(monkeypatch, stdout, expected):
    monkeypatch.setattr(
        uu.subprocess, "check_output",
        lambda *a, **k: stdout
    )
    assert uu._clean_worktree() is expected

def test_current_branch_detached(monkeypatch):
    def boom(*a, **k):
        raise uu.subprocess.CalledProcessError(1, a, "detached")
    monkeypatch.setattr(uu.subprocess, "check_output", boom)
    assert uu._current_branch() is None

def test_default_branch_paths(monkeypatch):
    # git answers -> strip "origin/"
    monkeypatch.setattr(
        uu.subprocess, "check_output",
        lambda *a, **k: "origin/develop\n"
    )
    assert uu._default_branch() == "develop"

    # git fails -> github JSON fallback
    def git_fail(*a, **k): raise uu.subprocess.CalledProcessError(1, a, "no ref")
    monkeypatch.setattr(uu.subprocess, "check_output", git_fail)

    class _JSON(io.StringIO):
        def __enter__(self): return self
        def __exit__(self, *exc): pass
    monkeypatch.setattr(
        uu, "_github",
        lambda url, **kw: _JSON('{"default_branch":"release"}')
    )
    assert uu._default_branch() == "release"

    # both fail -> hard-coded 'main'
    monkeypatch.setattr(uu, "_github", lambda *a, **k: (_ for _ in ()).throw(RuntimeError))
    assert uu._default_branch() == "main"

# ---------------------------------------------------------------------------
# update_via_git
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("clean,step_ok,expected", [
    (False, True,  False),   # dirty tree → abort
    (True,  True,  True),    # all steps succeed
    (True,  False, False),   # first step fails
])
def test_update_via_git(monkeypatch, clean, step_ok, expected, dummy_repo):
    monkeypatch.setattr(uu, "_clean_worktree", lambda: clean)
    monkeypatch.setattr(uu, "_current_branch", lambda: "main")
    # record actual calls
    calls = []
    def fake_check(cmd, **kw):
        calls.append(cmd)
        if not step_ok:
            raise uu.subprocess.CalledProcessError(1, cmd, "boom")
    monkeypatch.setattr(uu.subprocess, "check_output", fake_check)
    ok = uu.update_via_git("0.2.0")
    assert ok is expected
    if not clean:
        assert calls == []                 # bailed early
    else:
        assert len(calls) >= (1 if not step_ok else 5)
def test_update_via_git_real_file_change(dummy_repo, monkeypatch):
    # point version file and seed old version
    vers_path = dummy_repo / "api" / "VERSION"
    vers_path.write_text("4.4.4\n")

    # force clean repo and detached HEAD (so we pick up default branch)
    monkeypatch.setattr(uu, "_clean_worktree", lambda: True)
    monkeypatch.setattr(uu, "_current_branch", lambda: None)
    monkeypatch.setattr(uu, "_default_branch", lambda: "main")

    # fake subprocess: on the 'checkout' step, rewrite VERSION
    def fake_check(cmd, **kwargs):
        # cmd looks like ["git","-C", "/tmp/...", "checkout", "main"]
        if len(cmd) >= 5 and cmd[3] == "checkout":
            # simulate that the new commit contains the bumped version
            vers_path.write_text("5.5.5\n")
        return ""  # indicate success

    monkeypatch.setattr(uu.subprocess, "check_output", fake_check)

    # run the real update_via_git
    ok = uu.update_via_git("5.5.5")
    assert ok is True
    # verify that our “pulled” branch truly updated the file on disk
    assert vers_path.read_text().strip() == "5.5.5"
# ---------------------------------------------------------------------------
# update_via_tar
# ---------------------------------------------------------------------------
class _TarDummy:
    def __init__(self): self.extracted = False
    def __enter__(self): return self
    def __exit__(self, *e): pass
    def getmembers(self):
        m = types.SimpleNamespace(name="dir/file.txt")
        return [m]
    def extractall(self, root, members):
        self.extracted = True
        self.root = root

@pytest.mark.parametrize("asset_ok,tar_ok,expected", [
    (False, True,  False),   # no asset found
    (True,  False, False),   # tarfile.open blows
    (True,  True,  True),    # everything fine
])
def test_update_via_tar(monkeypatch, asset_ok, tar_ok, expected, tmp_path):
    monkeypatch.setattr(uu, "ROOT", tmp_path)

    # _download_asset path
    monkeypatch.setattr(
        uu, "_download_asset",
        lambda tag, kw="": b"blob" if asset_ok else None
    )

    if tar_ok:
        monkeypatch.setattr(uu.tarfile, "open", lambda *a, **k: _TarDummy())
    else:
        monkeypatch.setattr(uu.tarfile, "open",
                            lambda *a, **k: (_ for _ in ()).throw(RuntimeError))

    assert uu.update_via_tar("0.2.0") is expected
      
@pytest.mark.filterwarnings("ignore::DeprecationWarning")
def test_update_via_tar_real_extraction(dummy_repo, monkeypatch):
    import update as uu

    # in-memory tar builder
    def make_version_tar_bytes(tag: str) -> bytes:
        import io, tarfile
        topdir = f"v{tag}"
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tf:
            data = f"{tag}\n".encode()
            info = tarfile.TarInfo(name=f"{topdir}/api/VERSION")
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
        return buf.getvalue()

    # point ROOT at our dummy repo
    monkeypatch.setattr(uu, "ROOT", dummy_repo)
    # seed old version
    api_dir = dummy_repo / "api"
    (api_dir / "VERSION").write_text("3.0.0\n")

    # stub only download; let real update_via_tar run
    new_tag = "3.1.0"
    tar_bytes = make_version_tar_bytes(new_tag)
    monkeypatch.setattr(uu, "_download_asset", lambda tag, kw="": tar_bytes)

    ok = uu.update_via_tar(new_tag)
    assert ok is True
    # now verify the on-disk VERSION file was actually overwritten
    assert (api_dir / "VERSION").read_text().strip() == new_tag
# ---------------------------------------------------------------------------
# perform_update – all branches
# ---------------------------------------------------------------------------
def _write_version(path: Path, val: str):
    path.write_text(val + "\n")

@pytest.mark.parametrize("git_ok,tar_ok,expect", [
    (True,  True,  "updated-to-0.2.0-via-git"),             # git wins
    (False, True,  "updated-to-0.2.0-via-tar (git failed)"),# git fails → tar wins
    (False, False, "update-failed"),                        # both fail
])
def test_perform_update_paths(dummy_repo, monkeypatch, git_ok, tar_ok, expect):
    _write_version(dummy_repo / "api" / "VERSION", "0.1.0")

    monkeypatch.setattr(uu, "latest_version", lambda: "0.2.0")
    monkeypatch.setattr(uu, "_clean_worktree", lambda: True)

    def fake_git(tag):
        if git_ok:
            _write_version(dummy_repo / "api" / "VERSION", tag)
            return True
        return False
    def fake_tar(tag):
        if tar_ok:
            _write_version(dummy_repo / "api" / "VERSION", tag)
            return True
        return False
    monkeypatch.setattr(uu, "update_via_git", fake_git)
    monkeypatch.setattr(uu, "update_via_tar", fake_tar)

    result = uu.perform_update()
    assert result == expect
    # VERSION file only updates when a strategy succeeds
    updated = (dummy_repo / "api" / "VERSION").read_text().strip()
    assert updated == ("0.2.0" if result != "update-failed" else "0.1.0")

def test_perform_update_already_current(dummy_repo, monkeypatch):
    monkeypatch.setattr(uu, "latest_version", lambda: "0.1.0")   # same
    assert uu.perform_update() == "already-current"

def test_perform_update_tar_only(dummy_repo, monkeypatch):
    # No .git dir → straight to tar path.
    (dummy_repo / ".git").rmdir()                         # remove repo
    monkeypatch.setattr(uu, "latest_version", lambda: "0.2.0")
    monkeypatch.setattr(uu, "update_via_tar", lambda t: True)
    res = uu.perform_update()
    assert res.startswith("updated-to-0.2.0-via-tar")
# ---------------------------------------------------------------------------
# Test token/no token
# ---------------------------------------------------------------------------    
def test__github_headers(monkeypatch):
    # Without token
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    captured = {}
    def fake_Request(url, headers):
        captured.update(headers)
        return "REQ"
    monkeypatch.setattr(uu, "Request", fake_Request)
    monkeypatch.setattr(uu, "urlopen", lambda req, timeout: DummyCM())
    cm = uu._github("http://example.com")
    assert cm.__enter__() is cm
    assert captured == {"Accept": "application/vnd.github+json"}

    # With token and custom accept
    monkeypatch.setenv("GITHUB_TOKEN", "tok123")
    captured.clear()
    cm2 = uu._github("http://example.com", accept="foo/bar")
    assert captured == {
        "Accept": "foo/bar",
        "Authorization": "Bearer tok123"
    }

@pytest.mark.parametrize("assets,keyword,expected", [
    ([], "minimal", None),
    ([{"name": "other-file", "url": "u"}], "minimal", None),
    ([{"name": "pkg-Minimal-V1", "url": "u"}], "minimal", b"BYTES"),
])
def test__download_asset(monkeypatch, assets, keyword, expected):
    tag = "1.2.3"
    def fake__github(url, accept="application/vnd.github+json"):
        # metadata call
        if url.endswith(f"/tags/v{tag}"):
            meta = {"assets": assets}
            class Meta(DummyCM):
                def read(self): return json.dumps(meta)
            return Meta()
        # download call
        class Blob(DummyCM):
            def read(self): return b"BYTES"
        return Blob()

    monkeypatch.setattr(uu, "_github", fake__github)
    result = uu._download_asset(tag, keyword)
    assert result == expected

def test_update_via_git_injects_auth(monkeypatch):
    tag = "4.5.6"
    # Ensure clean worktree and branch resolution
    monkeypatch.setattr(uu, "_clean_worktree", lambda: True)
    monkeypatch.setenv("GITHUB_TOKEN", "secretToken")
    monkeypatch.setattr(uu, "_current_branch", lambda: "main")
    monkeypatch.setattr(uu, "_default_branch", lambda: "main")

    captured_env = {}
    def fake_check(cmd, stderr=None, text=None, env=None):
        captured_env.update(env)
        # Stop after first step
        raise subprocess.CalledProcessError(1, cmd, "fail")
    monkeypatch.setattr(uu.subprocess, "check_output", fake_check)

    assert uu.update_via_git(tag) is False

    # Verify auth headers in env
    assert captured_env["GIT_TERMINAL_PROMPT"] == "0"
    assert captured_env["GIT_CONFIG_COUNT"] == "1"
    assert captured_env["GIT_CONFIG_KEY_0"] == "http.extraHeader"
    expected_b64 = base64.b64encode(f"x-access-token:secretToken".encode()).decode()
    assert captured_env["GIT_CONFIG_VALUE_0"] == f"Authorization: Basic {expected_b64}"

def test_update_via_git_no_token(monkeypatch):
    tag = "7.8.9"
    monkeypatch.setattr(uu, "_clean_worktree", lambda: True)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(uu, "_current_branch", lambda: "main")
    monkeypatch.setattr(uu, "_default_branch", lambda: "main")

    captured_env = {}
    def fake_check(cmd, stderr=None, text=None, env=None):
        captured_env.update(env)
        raise subprocess.CalledProcessError(1, cmd, "fail")
    monkeypatch.setattr(uu.subprocess, "check_output", fake_check)

    assert uu.update_via_git(tag) is False

    # No auth-related keys should be present
    for key in ("GIT_TERMINAL_PROMPT", "GIT_CONFIG_COUNT",
                "GIT_CONFIG_KEY_0", "GIT_CONFIG_VALUE_0"):
        assert key not in captured_env
# ---------------------------------------------------------------------------
# Monitoring API endpoints
# ---------------------------------------------------------------------------
@patch.object(monitoring.update, "latest_version", lambda: "0.2.0")
def test_update_info_endpoint(app_client):
    r = app_client.get("/update")
    assert r.status_code == 200
    assert r.get_json()["data"] == {"current": "0.1.0", "latest": "0.2.0"}

def test_update_info_endpoint_error(app_client, monkeypatch, caplog):
    def boom(): raise RuntimeError("net down")
    monkeypatch.setattr(uu, "latest_version", boom)
    caplog.set_level("ERROR")
    resp = app_client.get("/update")
    assert resp.status_code == 500
    assert "net down" in resp.get_json()["message"]
    assert "version check failed" in caplog.text

def test_update_apply_endpoint(app_client, monkeypatch):
    monkeypatch.setattr(monitoring.update, "perform_update", lambda: "ok")
    r = app_client.post("/update/apply")
    assert r.status_code == 202
    assert r.get_json()["data"]["outcome"] == "ok"
    
@pytest.mark.parametrize("body, expected", [
    ("Fix bug\nAdd feature\n",            "Fix bug\nAdd feature"),
    ("Release notes\n---\n-- tar info\n",  "Release notes"),
    ("Line1\nLine2\n--- Extra info\nLine3", "Line1\nLine2"),
])
def test_latest_changelog_splits_on_delimiter(monkeypatch, body, expected):
    dummy_json = json.dumps({"body": body})
    # _github should return a context-manager file-like with JSON text
    monkeypatch.setattr(uu, "_github", lambda url, **kwargs: DummyResponse(dummy_json))
    result = uu.latest_changelog()
    assert result == expected

def test_latest_changelog_handles_http_error(monkeypatch):
    def raise_404(url, **kwargs):
        raise HTTPError(url, 404, "Not Found", hdrs=None, fp=None)
    monkeypatch.setattr(uu, "_github", raise_404)
    assert uu.latest_changelog() == ""