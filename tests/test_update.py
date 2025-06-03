import io, importlib, types, base64, subprocess, json, tarfile, warnings, logging
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, Mock
from urllib.error import HTTPError

import pytest
import monitoring
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

    # Reset cache before test
    uu.last_release_fetched = None
    uu.cached_release_data = None

    monkeypatch.setattr(
        uu, "_github",
        lambda url, **kw: _JSON('{"tag_name":"v9.9.9"}')
    )
    result = uu.latest_version()
    assert result == "9.9.9"
    # Ensure cache is set to the parsed dict
    assert isinstance(uu.cached_release_data, dict)
    assert uu.cached_release_data["tag_name"] == "v9.9.9"
    assert uu.last_release_fetched is not None

def test_latest_version_http_error_cache_fresh(monkeypatch):
    # Seed fresh cache
    uu.cached_release_data = {"tag_name": "v5.5.5"}
    uu.last_release_fetched = datetime.now()

    # Simulate HTTPError on fetch
    err = HTTPError(None, 403, "rate limit", hdrs={"X-RateLimit-Remaining": "0"}, fp=None)
    monkeypatch.setattr(uu, "_get_release_data", lambda: (_ for _ in ()).throw(err))

    result = uu.latest_version()
    assert result == "5.5.5"  # from cache

def test_latest_version_http_error_no_cache(monkeypatch):
    # No cache present
    uu.cached_release_data = None
    uu.last_release_fetched = None

    err = HTTPError(None, 404, "Not Found", hdrs=None, fp=None)
    monkeypatch.setattr(uu, "_get_release_data", lambda: (_ for _ in ()).throw(err))
    result = uu.latest_version()
    assert result == "failed-to-fetch"
    # Ensure cache not set
    assert uu.cached_release_data is None

def test_latest_version_exception(monkeypatch):
    # Any non-HTTP exception should yield "failed-to-fetch"
    uu.cached_release_data = None
    uu.last_release_fetched = None

    monkeypatch.setattr(uu, "_get_release_data", lambda: (_ for _ in ()).throw(ValueError("oops")))
    result = uu.latest_version()
    assert result == "failed-to-fetch"
    assert uu.cached_release_data is None

def test_latest_version_cache_expired(monkeypatch):
    # Seed old cache (older than CACHE_DURATION)
    uu.cached_release_data = {"tag_name": "v0.0.1"}
    uu.last_release_fetched = datetime.now() - timedelta(hours=2)

    # Provide new version
    class _JSON(io.StringIO):
        def __enter__(self): return self
        def __exit__(self, *exc): pass

    monkeypatch.setattr(uu, "_github", lambda url, **kw: _JSON('{"tag_name":"v2.0.0"}'))
    new = uu.latest_version()
    assert new == "2.0.0"
    # Ensure cache updated to new dict
    assert uu.cached_release_data["tag_name"] == "v2.0.0"
    assert uu.last_release_fetched is not None

def test__get_release_data_cache_expired(monkeypatch):
    # If last_release_fetched is older than CACHE_DURATION, _get_release_data should proceed
    # to call GitHub (and update the cache). We simulate that here to cover the 'false' branch
    # of the initial if.

    uu.cached_release_data = {"tag_name": "v0.0.1"}
    uu.last_release_fetched = datetime.now() - timedelta(hours=2)

    class _JSON(io.StringIO):
        def __enter__(self): return self
        def __exit__(self, *exc): pass

    # Return a fresh JSON payload
    monkeypatch.setattr(
        uu,
        "_github",
        lambda url, **kw: _JSON('{"tag_name":"v9.9.9","body":"notes"}')
    )

    new_data = uu._get_release_data()
    assert new_data["tag_name"] == "v9.9.9"
    assert uu.cached_release_data["tag_name"] == "v9.9.9"
    assert uu.last_release_fetched is not None

def test__get_release_data_rate_limit_branch(monkeypatch, caplog):
    # Ensure no fresh cache
    uu.cached_release_data = None
    uu.last_release_fetched = None

    # Create a 403 HTTPError with “rate limit” in its message
    err = HTTPError(
        url="https://api.github.com",
        code=403,
        msg="Rate limit exceeded",
        hdrs={"X-RateLimit-Remaining": "7"},
        fp=None
    )

    # Monkeypatch _github to immediately raise our HTTPError
    monkeypatch.setattr(uu, "_github", lambda *args, **kwargs: (_ for _ in ()).throw(err))

    caplog.set_level(logging.WARNING)
    with pytest.raises(HTTPError):
        uu._get_release_data()

    # Verify that the rate-limit warning was logged with the correct remaining value
    assert "GitHub rate limit exceeded (remaining: 7)" in caplog.text

def test__get_release_data_other_http_error_branch(monkeypatch, caplog):
    # Ensure no fresh cache
    uu.cached_release_data = None
    uu.last_release_fetched = None

    # Create a 404 HTTPError (not a rate-limit case)
    err = HTTPError(
        url="https://api.github.com",
        code=404,
        msg="Not Found",
        hdrs=None,
        fp=None
    )

    monkeypatch.setattr(uu, "_github", lambda *args, **kwargs: (_ for _ in ()).throw(err))

    caplog.set_level(logging.WARNING)
    with pytest.raises(HTTPError):
        uu._get_release_data()

    # Verify that a generic HTTPError warning was logged
    assert "HTTPError: HTTP Error 404" in caplog.text

def test__get_release_data_generic_exception_branch(monkeypatch):
    # Ensure no fresh cache
    uu.cached_release_data = None
    uu.last_release_fetched = None

    # Simulate a non-HTTPError (e.g., ValueError) being thrown by _github
    monkeypatch.setattr(uu, "_github", lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("network down")))

    # The ValueError should propagate unchanged
    with pytest.raises(ValueError) as excinfo:
        uu._get_release_data()
    assert "network down" in str(excinfo.value)
    
def test__get_release_data_returns_cached(monkeypatch):
    # If cached_release_data is set and last_release_fetched is recent,
    # _get_release_data should short-circuit and return the cache without calling GitHub.
    from datetime import datetime, timedelta

    # Seed the cache with a dummy payload and mark fetched as ‘now’
    uu.cached_release_data = {"tag_name": "vX.Y.Z", "body": "ignored"}
    uu.last_release_fetched = datetime.now()

    # Monkey‐patch _github to raise if called (to ensure we hit the 'return cached_release_data' path)
    monkeypatch.setattr(uu, "_github", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("GitHub should not be called")))

    result = uu._get_release_data()
    assert result == {"tag_name": "vX.Y.Z", "body": "ignored"}
    
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

    # git fails -> GitHub API fallback
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
# update_via_tar
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("asset_ok,tar_ok,expected,has_dirs", [
    (False, True,  False, False),   # no asset found
    (True,  False, False, False),   # tarfile.open blows
    (True,  True,  True,  False),   # everything fine (no dirs)
    (True,  True,  True,  True),    # everything fine (with dirs)
])
def test_update_via_tar(monkeypatch, asset_ok, tar_ok, expected, has_dirs, tmp_path):
    monkeypatch.setattr(uu, "ROOT", tmp_path)
    # _download_asset patch
    monkeypatch.setattr(
        uu, "_download_asset",
        lambda tag, kw="": b"blob" if asset_ok else None
    )
    if tar_ok:
        class TarInfoMock:
            def __init__(self, name, isdir=False):
                self.name = name
                self._isdir = isdir
                self.size = 0
                self.mode = 0o755
            
            def isdir(self):
                return self._isdir
        class TarDummy:
            def __init__(self):
                self.members = []
                if has_dirs:
                    # Create mock TarInfo objects with top-level directory
                    self.members.append(TarInfoMock("viewport-0.2.0/", isdir=True))
                    self.members.append(TarInfoMock("viewport-0.2.0/static/", isdir=True))
                    self.members.append(TarInfoMock("viewport-0.2.0/static/file.js"))
                    self.members.append(TarInfoMock("viewport-0.2.0/templates/file.html"))
                else:
                    self.members.append(TarInfoMock("viewport-0.2.0/file.txt"))
                
                self.extracted_members = None
            def getmembers(self):
                return self.members
            def extractall(self, path, members=None):
                self.extracted_members = members
                # Actually create the files in the temp directory
                for member in members:
                    dest = path / member.name
                    if member.isdir():
                        dest.mkdir(parents=True, exist_ok=True)
                    else:
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        dest.touch()
            # Context manager support
            def __enter__(self):
                return self
            def __exit__(self, exc_type, exc_val, exc_tb):
                pass
        dummy = TarDummy()
        monkeypatch.setattr(uu.tarfile, "open", lambda *a, **k: dummy)
    else:
        monkeypatch.setattr(uu.tarfile, "open",
                          lambda *a, **k: (_ for _ in ()).throw(RuntimeError))
    result = uu.update_via_tar("0.2.0")
    assert result is expected
    # Verify the actual file structure when successful
    if expected and tar_ok and asset_ok:
        if has_dirs:
            # Verify files were extracted to correct locations
            assert (tmp_path / "static/file.js").exists()
            assert (tmp_path / "templates/file.html").exists()
            # Verify top-level directory was NOT created
            assert not (tmp_path / "viewport-0.2.0").exists()
        else:
            # Verify single file was extracted correctly
            assert (tmp_path / "file.txt").exists()
            assert not (tmp_path / "viewport-0.2.0").exists()

@pytest.mark.filterwarnings("ignore::DeprecationWarning")
def test_update_via_tar_real_extraction(dummy_repo, monkeypatch):
    # Test actual tar extraction with real filesystem operations
    def make_version_tar_bytes(tag: str) -> bytes:
        import io, tarfile
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tf:
            # Add multiple files to test directory handling
            topdir = f"viewport-{tag}"
            # Add VERSION file
            version_data = f"{tag}\n".encode()
            version_info = tarfile.TarInfo(name=f"{topdir}/api/VERSION")
            version_info.size = len(version_data)
            tf.addfile(version_info, io.BytesIO(version_data))
            # Add a sample file in static directory
            static_info = tarfile.TarInfo(name=f"{topdir}/static/sample.js")
            static_info.size = 10
            tf.addfile(static_info, io.BytesIO(b"console.log()"))
            # Add empty directory
            dir_info = tarfile.TarInfo(name=f"{topdir}/empty_dir/")
            dir_info.type = tarfile.DIRTYPE
            tf.addfile(dir_info)
        return buf.getvalue()
    # Setup
    monkeypatch.setattr(uu, "ROOT", dummy_repo)
    api_dir = dummy_repo / "api"
    api_dir.mkdir(exist_ok=True)
    (api_dir / "VERSION").write_text("3.0.0\n")
    # Create static dir with existing file
    static_dir = dummy_repo / "static"
    static_dir.mkdir(exist_ok=True)
    (static_dir / "old.js").write_text("old")
    # Run update
    new_tag = "3.1.0"
    monkeypatch.setattr(uu, "_download_asset", lambda tag, kw="": make_version_tar_bytes(new_tag))
    assert uu.update_via_tar(new_tag) is True
    # Verify results
    assert (api_dir / "VERSION").read_text().strip() == new_tag  # Version updated
    assert (static_dir / "sample.js").exists()  # New file added
    assert (static_dir / "old.js").exists()  # Old file remains
    assert not (dummy_repo / f"viewport-{new_tag}").exists()  # No top-level dir
    assert (dummy_repo / "empty_dir").exists()  # Empty dir created

def test_update_via_tar_directory_filtering(monkeypatch, tmp_path):
    monkeypatch.setattr(uu, "ROOT", tmp_path)
    
    # Create a tar with:
    # 1. A top-level directory (should be skipped)
    # 2. A nested directory (should be kept)
    # 3. A file in root (should be kept)
    # 4. A file in nested dir (should be kept)
    class TarInfoMock:
        def __init__(self, name, isdir=False):
            self.name = name
            self._isdir = isdir
            self.size = 0
            self.mode = 0o755
    class TarDummy:
        def __init__(self):
            self.members = [
                TarInfoMock("top_dir/", isdir=True),               # Should be skipped
                TarInfoMock("top_dir/nested/", isdir=True),        # Should be kept
                TarInfoMock("top_dir/file.txt", isdir=False),      # Should be kept
                TarInfoMock("top_dir/nested/file.js", isdir=False) # Should be kept
            ]
            self.extracted_members = None

        def getmembers(self):
            return self.members

        def extractall(self, path, members=None):
            self.extracted_members = members
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    # Setup mocks
    monkeypatch.setattr(uu, "_download_asset", lambda tag, kw="": b"blob")
    dummy = TarDummy()
    monkeypatch.setattr(uu.tarfile, "open", lambda *a, **k: dummy)

    # Run the function
    assert uu.update_via_tar("0.2.0") is True

    # Verify filtering worked
    extracted_names = [m.name for m in dummy.extracted_members]
    assert "top_dir/" not in extracted_names  # Top-level dir was skipped
    assert "nested/" in extracted_names       # Nested dir was kept
    assert "file.txt" in extracted_names      # Root file was kept
    assert "nested/file.js" in extracted_names  # Nested file was kept
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
# _github helper / API integration
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

def test__github_rate_limit_warning(monkeypatch, caplog):
    import logging

    # Capture warnings at WARNING level
    caplog.set_level(logging.WARNING)

    # Stub Request so it doesn’t actually try to build a real request
    monkeypatch.setattr(uu, "Request", lambda url, headers: "DUMMY_REQ")

    # Make urlopen always raise a 403 HTTPError with "rate limit" in its message
    def fake_urlopen(req, timeout):
        raise HTTPError(
            url="http://api.github.com",
            code=403,
            msg="rate limit exceeded",
            hdrs={"X-RateLimit-Remaining": "2"},
            fp=None,
        )
    monkeypatch.setattr(uu, "urlopen", fake_urlopen)

    # Now calling _github should log a warning and re-raise the HTTPError
    with pytest.raises(HTTPError):
        uu._github("http://api.github.com/repos/foo/bar")

    # Verify that the warning about rate limiting was emitted
    assert "GitHub rate limit exceeded (remaining: 2)" in caplog.text
    
def test__github_other_http_error_logging(monkeypatch, caplog):
    # Simulate a non-403 HTTPError (e.g., 404 Not Found)
    err = HTTPError(url="http://example.com", code=404, msg="Not Found", hdrs=None, fp=None)
    monkeypatch.setattr(uu, "Request", lambda url, headers: "REQ")
    monkeypatch.setattr(uu, "urlopen", lambda req, timeout: (_ for _ in ()).throw(err))
    caplog.set_level("WARNING")
    with pytest.raises(HTTPError):
        uu._github("http://example.com")
    assert "HTTP Error 404" in caplog.text  
    
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

# ---------------------------------------------------------------------------
# Monitoring API endpoints
# ---------------------------------------------------------------------------
@patch.object(monitoring.update, "latest_version", lambda: "0.2.0")
def test_update_info_endpoint(app_client):
    r = app_client.get("/api/update")
    assert r.status_code == 200
    assert r.get_json()["data"] == {"current": "0.1.0", "latest": "0.2.0"}

def test_update_info_endpoint_error(app_client, monkeypatch, caplog):
    def boom(): raise RuntimeError("net down")
    monkeypatch.setattr(uu, "latest_version", boom)
    caplog.set_level("ERROR")
    resp = app_client.get("/api/update")
    assert resp.status_code == 500
    assert "An internal error has occurred." in resp.get_json()["message"]
    assert "version check failed" in caplog.text

def test_update_apply_endpoint(app_client, monkeypatch):
    monkeypatch.setattr(monitoring.update, "perform_update", lambda: "ok")
    r = app_client.post("/api/update/apply")
    assert r.status_code == 202
    assert r.get_json()["data"]["outcome"] == "ok"

def test_update_changelog_endpoint_success(app_client, monkeypatch):
    # Simulate a normal response from latest_changelog
    import monitoring
    monkeypatch.setattr(monitoring.update, "latest_changelog", lambda: "Example notes")
    response = app_client.get("/api/update/changelog")
    assert response.status_code == 200

    data = response.get_json()
    assert data["status"] == "ok"
    assert data["data"]["changelog"] == "Example notes"
    # The release_url should point to the GitHub releases/latest for the configured REPO
    assert monitoring.update.REPO in data["data"]["release_url"]
    assert data["data"]["release_url"].startswith("https://github.com/")

def test_update_changelog_endpoint_error(app_client, monkeypatch, caplog):
    # Simulate an exception in latest_changelog to hit the error branch
    import monitoring
    caplog.set_level("ERROR")
    monkeypatch.setattr(
        monitoring.update,
        "latest_changelog",
        lambda: (_ for _ in ()).throw(RuntimeError("fetch failed"))
    )

    response = app_client.get("/api/update/changelog")
    assert response.status_code == 500

    data = response.get_json()
    assert data["status"] == "error"
    assert "An internal error has occurred." in data["message"]
    # The log should contain the "changelog fetch failed" message
    assert "changelog fetch failed" in caplog.text

# ---------------------------------------------------------------------------
# latest_changelog: error & cache branches
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("body, expected", [
    ("Fix bug\nAdd feature\n",            "Fix bug\nAdd feature"),
    ("Release notes\n---\n-- tar info\n",  "Release notes"),
    ("Line1\nLine2\n--- Extra info\nLine3", "Line1\nLine2"),
])
def test_latest_changelog_splits_on_delimiter(monkeypatch, body, expected):
    # Stub _get_release_data to return a dict with "body"
    monkeypatch.setattr(uu, "_get_release_data", lambda: {"body": body})
    result = uu.latest_changelog()
    assert result == expected

def test_latest_changelog_http_error_no_cache(monkeypatch):
    # No cache, HTTPError should return empty string
    uu.cached_release_data = None
    uu.last_release_fetched = None
    monkeypatch.setattr(uu, "_get_release_data", lambda: (_ for _ in ()).throw(HTTPError("", 404, "Not Found", hdrs=None, fp=None)))
    assert uu.latest_changelog() == ""

def test_latest_changelog_http_error_cache_stale(monkeypatch):
    # Seed stale cache
    uu.cached_release_data = {"body": "Old notes\n--- extraneous"}
    uu.last_release_fetched = datetime.now() - timedelta(hours=2)
    # HTTPError should bypass cache (stale) and return ""
    monkeypatch.setattr(uu, "_get_release_data", lambda: (_ for _ in ()).throw(HTTPError("", 403, "rate limit", hdrs={"X-RateLimit-Remaining": "0"}, fp=None)))
    assert uu.latest_changelog() == ""

def test_latest_changelog_http_error_cache_fresh(monkeypatch):
    # Seed fresh cache
    raw_body = "Cached notes\n--- more"
    uu.cached_release_data = {"body": raw_body}
    uu.last_release_fetched = datetime.now()
    # HTTPError should cause return of truncated cached body
    monkeypatch.setattr(uu, "_get_release_data", lambda: (_ for _ in ()).throw(HTTPError("", 403, "rate limit", hdrs={"X-RateLimit-Remaining": "0"}, fp=None)))
    result = uu.latest_changelog()
    assert result == "Cached notes"

def test_latest_changelog_exception(monkeypatch):
    # Non-HTTP exception should return empty string
    uu.cached_release_data = None
    uu.last_release_fetched = None
    monkeypatch.setattr(uu, "_get_release_data", lambda: (_ for _ in ()).throw(ValueError("oops")))
    assert uu.latest_changelog() == ""