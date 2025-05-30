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