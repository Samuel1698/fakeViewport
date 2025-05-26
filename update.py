#!/usr/bin/env python3
import subprocess
import tempfile
import tarfile
import logging
from pathlib import Path
from urllib.request import urlopen
import json

REPO  = "Samuel1698/fakeViewport"
ROOT  = Path(__file__).resolve().parent
GIT   = ["git", "-C", str(ROOT)]
VERS  = ROOT / "api" / "VERSION"
TAR   = "viewport-v{VERS}-minimal.tar.gz"
# ----------------------------------------------------------------------------- 
# Helper functions
# ----------------------------------------------------------------------------- 
def current_version() -> str:
    return VERS.read_text().strip()

def latest_version() -> str:
    url = f"https://api.github.com/repos/{REPO}/releases/latest"
    with urlopen(url, timeout=5) as resp:
        data = json.load(resp)
    return data["tag_name"].lstrip("v")

def _clean_worktree() -> bool:
    """True ⇢ no uncommitted changes."""
    out = subprocess.check_output(GIT + ["status", "--porcelain"], text=True)
    return out.strip() == ""

def _git_ok(cmd) -> bool:
    try:
        subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True)
        return True
    except subprocess.CalledProcessError as e:
        logging.error("git failed: %s", e.output.strip())
        return False

# ----------------------------------------------------------------------------- 
# Strategies
# ----------------------------------------------------------------------------- 
def update_via_git(tag: str) -> bool:
    if not _clean_worktree():
        logging.warning("Local changes detected, aborting git update")
        return False
    steps = [
        GIT + ["fetch", "--tags", "--force"],
        GIT + ["checkout", f"v{tag}"],
        ["bash", str(ROOT / "minimize.sh")],
    ]
    return all(_git_ok(step) for step in steps)

def update_via_tar(tag: str) -> bool:
    try:
        url = f"https://github.com/{REPO}/releases/download/v{tag}/{TAR}"
        with urlopen(url, timeout=30) as r, tempfile.NamedTemporaryFile() as tmp:
            tmp.write(r.read()); tmp.flush()
            with tarfile.open(tmp.name) as tf:
                tf.extractall(path=ROOT.parent)
        return True
    except Exception as exc:
        logging.exception("tar update failed: %s", exc)
        return False
# ----------------------------------------------------------------------------- 
# API
# ----------------------------------------------------------------------------- 
def perform_update() -> str:
    cur, new = current_version(), latest_version()
    if cur == new:
        return "already-current"

    tried_git = False
    if (ROOT / ".git").exists() and _clean_worktree():
        tried_git = True
        try:
            if update_via_git(new):
                VERS.write_text(f"{new}\n")
                return f"updated-to-{new}-via-git"
        except Exception:
            # on git error, fall back to tar
            pass

    if update_via_tar(new):
        VERS.write_text(f"{new}\n")
        return f"updated-to-{new}-via-tar" + (" (git failed)" if tried_git else "")

    return "update-failed"