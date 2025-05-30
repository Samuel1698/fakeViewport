#!/usr/bin/venv python3
import subprocess
import io
import tarfile
import logging
from pathlib import Path
from urllib.request import urlopen
import json, os
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import base64

REPO  = "Samuel1698/fakeViewport"
ROOT  = Path(__file__).resolve().parent
GIT   = ["git", "-C", str(ROOT)]
VERS  = ROOT / "api" / "VERSION"
# ----------------------------------------------------------------------------- 
# Helper functions
# ----------------------------------------------------------------------------- 
def _github(url: str, *, accept="application/vnd.github+json"):
    hdr = {"Accept": accept}
    if (tok := os.getenv("GITHUB_TOKEN")):
        hdr["Authorization"] = f"Bearer {tok}"
    return urlopen(Request(url, headers=hdr), timeout=30)

def _clean_worktree() -> bool:
    return subprocess.check_output(GIT + ["status", "--porcelain"], text=True).strip() == ""

def _current_branch() -> str | None:
    # Return the active branch name or None if HEAD is detached.
    try:
        return subprocess.check_output(
            GIT + ["symbolic-ref", "--quiet", "--short", "HEAD"],
            text=True,
        ).strip()
    except subprocess.CalledProcessError:
        return None

def _default_branch() -> str:
    # Ask Git for the remote-default branch, fallback to GitHub API, then main.
    try:
        ref = subprocess.check_output(
            GIT + ["symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"],
            text=True,
        ).strip()             # -> "origin/main"
        return ref.split("/", 1)[1]
    except subprocess.CalledProcessError:
        try:
            with _github(f"https://api.github.com/repos/{REPO}") as r:
                return json.load(r)["default_branch"]
        except Exception:
            return "main"
# ----------------------------------------------------------------------------- 
# Strategies
# ----------------------------------------------------------------------------- 
def update_via_git(tag: str) -> bool:
    # Fast-forwards the current branch (or the repo’s default branch if detached)
    # to the commit that has the desired tag, then runs minimize.sh.
    if not _clean_worktree():
        logging.warning("Local changes detected - skipping git strategy")
        return False

    env = os.environ.copy()
    if (tok := os.getenv("GITHUB_TOKEN")):
        b64 = base64.b64encode(f"x-access-token:{tok}".encode()).decode()
        env.update({
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "http.extraHeader",
            "GIT_CONFIG_VALUE_0": f"Authorization: Basic {b64}",
        })

    branch = _current_branch() or _default_branch()
    steps = [
        GIT + ["checkout", branch],                     # leave detached-HEAD if needed
        GIT + ["fetch", "--tags", "--force", "--prune"],
        GIT + ["pull", "--ff-only", "origin", branch],  # ordinary pull
        GIT + ["merge", "--ff-only", f"v{tag}"],        # fast-forward to the tag
        ["bash", str(ROOT / "minimize.sh"), "--force"], # run minimizer
    ]
    for step in steps:
        try:
            subprocess.check_output(step, stderr=subprocess.STDOUT, text=True, env=env)
        except subprocess.CalledProcessError as e:
            logging.error("git failed: %s", e.output.strip())
            return False

    return True

def _download_asset(tag: str, keyword: str) -> bytes | None:
    with _github(f"https://api.github.com/repos/{REPO}/releases/tags/v{tag}") as r:
        data = json.load(r)
    for asset in data.get("assets", []):
        if keyword.lower() in asset["name"].lower():
            with _github(asset["url"], accept="application/octet-stream") as a:
                return a.read()
    return None

def update_via_tar(tag: str) -> bool:
    try:
        blob = _download_asset(tag, "minimal")
        if blob is None:
            logging.error("no 'minimal' asset found for v%s", tag)
            return False

        with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tf:
            members = []
            for m in tf.getmembers():
                if "/" in m.name: m.name = m.name.split("/", 1)[1]
                if m.name: members.append(m)
            tf.extractall(ROOT, members=members)  
        return True
    except Exception as exc:
        logging.exception("tar update failed: %s", exc)
        return False
# ----------------------------------------------------------------------------- 
# API
# ----------------------------------------------------------------------------- 
def current_version() -> str:
    return VERS.read_text().strip()

def latest_version() -> str:
    try:
        with _github(f"https://api.github.com/repos/{REPO}/releases/latest") as r:
            return json.load(r)["tag_name"].lstrip("v")
    except HTTPError:
        return "update-failed"
def latest_changelog() -> str:
    # Fetch the body of the latest GitHub release and return it,
    # truncating at the first occurrence of '---'.
    try:
        with _github(f"https://api.github.com/repos/{REPO}/releases/latest") as r:
            data = json.load(r)
        body = data.get("body", "")
        # Truncate at delimiter '---'
        parts = body.split('---', 1)
        return parts[0].rstrip()
    except Exception as e:
        logging.error("Failed to fetch changelog: %s", e)
        return ""
def perform_update() -> str:
    # Try git first (if the work-tree is clean) then fall back to the tarball.
    # Whatever happens, write the outcome to the log and return it.
    cur, new = current_version(), latest_version()

    # already current
    if cur == new:
        outcome = "already-current"
        logging.info(outcome)
        return outcome

    # git path 
    tried_git = False
    if (ROOT / ".git").exists() and _clean_worktree():
        tried_git = True
        if update_via_git(new):
            outcome = f"updated-to-{new}-via-git"
            logging.info(outcome)
            return outcome

    # tarball path 
    if update_via_tar(new):
        outcome = f"updated-to-{new}-via-tar" + (" (git failed)" if tried_git else "")
        logging.info(outcome)
        return outcome

    # failure
    outcome = "update-failed"
    logging.info(outcome)                       
    return outcome
