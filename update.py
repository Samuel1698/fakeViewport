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
from datetime import datetime, timedelta

CACHE_DURATION = timedelta(hours=1)
REPO  = "Samuel1698/fakeViewport"
ROOT  = Path(__file__).resolve().parent
GIT   = ["git", "-C", str(ROOT)]
VERS  = ROOT / "api" / "VERSION"
last_release_fetched: datetime | None = None
cached_release_data: dict | None = None
# ----------------------------------------------------------------------------- 
# Helper functions
# ----------------------------------------------------------------------------- 
def _github(url: str, *, accept="application/vnd.github+json"):
    """
    Open a GitHub API endpoint with automatic token and rate-limit handling.

    Args:
        url: Full HTTPS URL of the GitHub REST endpoint.
        accept: Value for the ``Accept`` request header.

    Returns:
        http.client.HTTPResponse: An open response object ready for
        ``.read()`` / JSON decoding.

    Raises:
        urllib.error.HTTPError: Propagates 4xx/5xx errors after logging.
        Exception: Any other network-related exception.
    """
    hdr = {"Accept": accept}
    # Always use token if available
    if (tok := os.getenv("GITHUB_TOKEN")):
        hdr["Authorization"] = f"Bearer {tok}"
    req = Request(url, headers=hdr)
    try:
        return urlopen(req, timeout=30)
    except HTTPError as e:
        if e.code == 403 and 'rate limit' in str(e):
            remaining = e.headers.get('X-RateLimit-Remaining', '?')
            logging.warning(f"GitHub rate limit exceeded (remaining: {remaining})")
        else:
            logging.warning(str(e))
        raise
    
def _clean_worktree() -> bool:
    """
    Check whether the local Git work-tree is clean.

    Returns:
        bool: ``True`` if ``git status --porcelain`` is empty, else
        ``False``.
    """
    return subprocess.check_output(GIT + ["status", "--porcelain"], text=True).strip() == ""

def _current_branch() -> str | None:
    """
    Get the name of the currently checked-out branch.

    Returns:
        string | None: Branch name, or ``None`` if HEAD is detached.
    """
    try:
        return subprocess.check_output(
            GIT + ["symbolic-ref", "--quiet", "--short", "HEAD"],
            text=True,
        ).strip()
    except subprocess.CalledProcessError:
        return None

def _default_branch() -> str:
    """
    Resolve the repository's default branch.

    Attempts ``git symbolic-ref`` first, then falls back to the GitHub
    API, and finally ``"main"`` if all else fails.

    Returns:
        string: The default branch name.
    """
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
    """
    Fast-forward the local repo to *tag* and run ``minimize.sh``.

    The strategy is skipped if uncommitted changes exist.

    Args:
        tag: Release tag without the leading ``"v"`` (e.g., ``"2.3.6"``).

    Returns:
        bool: ``True`` on success, ``False`` if any Git step fails.
    """
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
    """
    Download a release asset whose name contains *keyword*.

    Args:
        tag: Release tag without the leading ``"v"``.
        keyword: Case-insensitive substring to match the asset name.

    Returns:
        bytes | None: Asset content, or ``None`` if not found.
    """
    with _github(f"https://api.github.com/repos/{REPO}/releases/tags/v{tag}") as r:
        data = json.load(r)
    for asset in data.get("assets", []):
        if keyword.lower() in asset["name"].lower():
            with _github(asset["url"], accept="application/octet-stream") as a:
                return a.read()
    return None

def update_via_tar(tag: str) -> bool:
    """
    Update files by extracting the “minimal” tarball for *tag*.

    Args:
        tag: Release tag without the leading ``"v"``.

    Returns:
        bool: ``True`` if extraction succeeds, ``False`` otherwise.
    """
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
    """
    Read the locally installed version string.

    Returns:
        string: Contents of ``api/VERSION`` with surrounding whitespace
        stripped.
    """
    return VERS.read_text().strip()

def _get_release_data() -> dict:
    """
    Retrieve (and cache) the GitHub JSON for the latest release.

    Returns:
        dict: Raw JSON representing the latest release.

    Raises:
        urllib.error.HTTPError: Propagates 4xx/5xx errors.
        Exception: Any other network or parsing exception.
    """
    global last_release_fetched, cached_release_data

    now = datetime.now()
    if (
        cached_release_data is not None
        and last_release_fetched is not None
        and (now - last_release_fetched) < CACHE_DURATION
    ):  
        return cached_release_data
    url = f"https://api.github.com/repos/{REPO}/releases/latest"
    try:
        with _github(url) as resp:
            data = json.load(resp)
            cached_release_data = data
            last_release_fetched = now
            return data

    except HTTPError as e:
        # Log rate-limit (403 with “rate limit” in message) differently from other HTTP errors
        if e.code == 403 and "rate limit" in str(e).lower():
            remaining = e.headers.get("X-RateLimit-Remaining", "?")
            logging.warning(f"GitHub rate limit exceeded (remaining: {remaining})")
        else:
            logging.warning(f"HTTPError: {e}")
        raise

    except Exception as e:
        # Any other exception (network down, JSON parse error, etc.) – re-raise so callers know
        raise

def latest_version() -> str:
    """
    Return the tag of the latest GitHub release.

    Returns:
        string: Tag without the leading ``"v"``, or ``"failed-to-fetch"``
        if the lookup fails.
    """
    global cached_release_data, last_release_fetched
    now = datetime.now()
    try:
        data = _get_release_data()
        return data["tag_name"].lstrip("v")
    except HTTPError:
        # If cache exists and is still fresh, return cached tag_name
        if (
            cached_release_data is not None
            and last_release_fetched is not None
            and (now - last_release_fetched) < CACHE_DURATION
        ):
            return cached_release_data["tag_name"].lstrip("v")
        return "failed-to-fetch"
    except Exception:
        return "failed-to-fetch"

def latest_changelog() -> str:
    """
    Return the latest release notes, truncated at the first ``---`` line.

    Returns:
        string: Release body or an empty string if it cannot be fetched.
    """
    global cached_release_data, last_release_fetched
    now = datetime.now()
    try:
        data = _get_release_data()
        raw_body = data.get("body", "") or ""
        # Split on the first "\n---" (or just '---') and strip trailing whitespace/newlines
        return raw_body.split("\n---", 1)[0].rstrip("\n")
    except HTTPError:
        # If cache exists and is still fresh, return truncated cached body
        if (
            cached_release_data is not None
            and last_release_fetched is not None
            and (now - last_release_fetched) < CACHE_DURATION
        ):
            cached_body = cached_release_data.get("body", "") or ""
            return cached_body.split("\n---", 1)[0].rstrip("\n")
        return ""
    except Exception:
        return ""
    
def perform_update() -> str:
    """
    Update the installation to the newest release using Git or tarball.

    The function tries Git first (when possible) and falls back to the
    tarball strategy, logging the outcome.

    Returns:
        string: Outcome label, e.g. ``"already-current"``,
        ``"updated-to-2.3.6-via-git"``, or ``"update-failed"``.
    """
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
