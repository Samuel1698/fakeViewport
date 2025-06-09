#!/usr/bin/env python3
import sys, os, time, configparser, psutil, subprocess, logging, socket
from functools import wraps
from pathlib import Path
from collections import deque
from datetime import datetime, timedelta
from urllib.parse import urlparse
from flask import (
    Flask, render_template, request,
    session, redirect, url_for, flash,
    jsonify
)
from flask_cors import CORS
from collections import deque
import update 
from logging_config import configure_logging
from validate_config import validate_config
from dotenv import load_dotenv, find_dotenv
from viewport import process_handler

_mon = sys.modules[__name__]
dotenv_file = find_dotenv()
load_dotenv(dotenv_file, override=True)
LOG_HARD_CAP = 1000
unwanted = None
last_net_io = None
last_check_time = time.time()
script_dir = Path(__file__).resolve().parent
_base = Path(__file__).parent
config_file = _base / 'config.ini'
env_file    = _base / '.env'
logs_dir    = _base / 'logs'
api_dir     = _base / 'api'

# --------------------------------------------------------------------------- # 
# Load and validate everything via our shared validator
# --------------------------------------------------------------------------- # 
cfg = validate_config(strict=False, print=False)
# pull everything out into locals/globals
for name, val in vars(cfg).items():
    setattr(_mon, name, val)

# --------------------------------------------------------------------------- # 
# Setup Logging
# --------------------------------------------------------------------------- # 
configure_logging(
    log_file_path=str(mon_file),
    log_file=LOG_FILE_FLAG,
    log_console=LOG_CONSOLE,
    log_days=LOG_DAYS,
    Debug_logging=DEBUG_LOGGING
)

# --------------------------------------------------------------------------- # 
# Application for the monitoring API
# --------------------------------------------------------------------------- # 
def create_app():
    """
    Build and configure the Flask Monitoring API application.

    The factory:

    * Reloads configuration (with relaxed validation when under pytest).
    * Injects helpers and authentication wrappers.
    * Registers all API and HTML routes, including update actions and
        system-information endpoints.
    * Enables CORS for cross-origin browser access.

    Returns:
        flask.Flask: A fully configured Flask application instance,
        ready to be served or unit-tested.
    """
    app = Flask(__name__) 
    # This is only needed to inject the different configs we test with
    if "pytest" in sys.modules:
        cfg = validate_config()
        for name, val in vars(cfg).items():
            setattr(_mon, name, val)
    app.secret_key  = CONTROL_TOKEN or os.urandom(24)
    # ----------------------------------------------------------------------- #
    # Enable CORS
    # ----------------------------------------------------------------------- #
    CORS(app)
    # ----------------------------------------------------------------------- #
    # Helper: read and strip text files
    # ----------------------------------------------------------------------- #
    def _read_api_file(path):
        if not path.exists():
            return None
        try:
            return path.read_text().strip()
        except Exception as e:
            app.logger.error(f"Error reading {path}: {e}")
            return None
    app._read_api_file = _read_api_file
    # ----------------------------------------------------------------------- #
    # Protect routes if SECRET is set
    # ----------------------------------------------------------------------- #
    def login_required(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if CONTROL_TOKEN:
                # invalidate any stale session if token changed or missing
                if session.get("authenticated") != CONTROL_TOKEN:
                    session.clear()
                    return redirect(url_for("login", next=request.path))
            return f(*args, **kwargs)
        return decorated
    # ----------------------------------------------------------------------- #
    # Dashboard Routes
    # ----------------------------------------------------------------------- #
    @app.route("/login", methods=["GET", "POST"])
    def login():
        """
        Display the login form and authenticate API users.

        On **GET** - renders the HTML form.  
        On **POST** - validates the submitted *key*; a correct value sets
        ``session["authenticated"]`` and redirects the user.

        Returns:
            flask.Response: HTML page or redirect response.
        """
        # If no SECRET is configured, skip login entirely
        if not CONTROL_TOKEN:
            session["authenticated"] = CONTROL_TOKEN
            return redirect(url_for("dashboard"))

        # Clear any old session data on every visit or attempt
        session.clear()

        error = None
        if request.method == "POST":
            key = request.form.get("key", "").strip()
            if key == CONTROL_TOKEN:
                # Successful login: set auth flag and go to dashboard (or next)
                session["authenticated"] = CONTROL_TOKEN
                next_url = request.args.get("next", "").replace("\\", "")

                # If next is provided and safe, use it
                if next_url and not urlparse(next_url).netloc and not urlparse(next_url).scheme:
                    return redirect(next_url)

                # If no next, check referrer (if safe)
                referrer = request.referrer
                if referrer:
                    parsed_referrer = urlparse(referrer)
                    # Extract the path from the referrer and validate it
                    referrer_path = parsed_referrer.path
                    if referrer_path and referrer_path.startswith("/") and referrer_path in [url_for("dashboard"), url_for("logout"), url_for("api_index")]: 
                        return redirect(referrer_path)
                    else: pass
                # Default to dashboard if no safe next/referrer
                return redirect(url_for("dashboard"))

            # Failed login: flash error, but session stays cleared
            error = "Invalid API key"
            flash(error, "danger")

        # Render login form (with any flashed message)
        return render_template("login.html", error=error)

    # ----------------------------------------------------------------------- #
    @app.route("/logout", methods=["POST"])
    def logout():
        """
        Clear the session and redirect to the login page.

        Returns:
            flask.Response: Redirect to ``/login``.
        """
        session.clear()
        return redirect(url_for("login"))

    # ----------------------------------------------------------------------- #
    @app.route("/")
    @app.route("/dashboard")
    @login_required
    def dashboard():
        """
        Render the main dashboard (index.html).

        Returns:
            flask.Response: HTML dashboard.
        """
        return render_template("index.html")

    # ----------------------------------------------------------------------- #
    # POSTS Routes
    # ----------------------------------------------------------------------- #
    @app.route("/api/control/<action>", methods=["POST"])
    @login_required
    def api_control(action):
        """
        Dispatch start/restart/quit commands to *viewport.py*.

        Args:
            action: One of ``"start"``, ``"restart"``, or ``"quit"``.

        Returns:
            flask.Response: JSON containing status and message.
        """
        if action not in ("start", "restart", "quit"):
            return jsonify(status="error",
                            message=f'Unknown action "{action}"'), 400

        flag = {"start":"--background", "restart":"--restart", "quit":"--quit"}[action]
        try:
            viewport_dir = str(script_dir / "viewport.py")
            subprocess.Popen(
                [sys.executable, viewport_dir, flag],
                cwd=str(script_dir),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                start_new_session=True,
            )
            return jsonify(status="ok",
                            message=f"{action.title()} command issued"), 202
        except Exception as e:
            app.logger.exception("Failed to dispatch control command")
            return jsonify(status="error", message="Failed to dispatch control command"), 500
    
    # ----------------------------------------------------------------------- #
    @app.route("/api/update/apply", methods=["POST"])
    @login_required
    def api_update_apply():
        """
        Trigger a software update (git first, tar fallback).

        Returns:
            flask.Response: JSON indicating the update outcome.
        """
        outcome = update.perform_update()
        return jsonify(status="ok", data={"outcome": outcome}), 202

    # ----------------------------------------------------------------------- #
    @app.route("/api/self/restart", methods=["POST"])
    @login_required
    def api_restart():
        """
        Spawn a fresh *monitoring.py* process and return 202 Accepted.

        Returns:
            flask.Response: JSON confirmation of restart initiation.
        """
        try:
            # Launch a new monitoring.py in the background
            monitoring_dir = str(script_dir / "monitoring.py")
            subprocess.Popen(
                [sys.executable, monitoring_dir],
                cwd=str(script_dir),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                start_new_session=True,
            )
            return jsonify(status="ok",
                        message=f"API restart initiated"), 202
        except Exception as e:
            app.logger.exception("Failed to restart API")
            return jsonify(status="error", message="An internal error has occurred."), 500

    # ----------------------------------------------------------------------- #
    # GET Routes
    # ----------------------------------------------------------------------- #
    @app.route("/api")
    @app.route("/api/")
    def api_index():
        """
        List all available API endpoints with absolute URLs.

        Returns:
            flask.Response: JSON index of endpoint URIs.
        """
        return jsonify({
            "dashboard":       url_for("dashboard",           _external=True),
            "update":          url_for("api_update_info",     _external=True),
            "update/changelog":url_for("api_update_changelog",_external=True),
            "script_uptime":   url_for("api_script_uptime",   _external=True),
            "system_info":     url_for("api_system_info",     _external=True),
            "logs":            url_for("api_logs",            _external=True),
            "status":          url_for("api_status",          _external=True),
            "config":          url_for("api_config",          _external=True),
        })

    # ----------------------------------------------------------------------- #
    @app.route("/api/update")
    def api_update_info():
        """
        Return the current and latest available Fake Viewport versions.

        Returns:
            flask.Response: ``{"current": "...", "latest": "..."}`` or error.
        """
        try:
            return jsonify(status="ok", data={
                "current": update.current_version(),
                "latest":  update.latest_version(),
            })
        except Exception as e:
            app.logger.exception("version check failed")
            return jsonify(status="error", message="An internal error has occurred."), 500

    # ----------------------------------------------------------------------- #
    @app.route("/api/update/changelog")
    def api_update_changelog():
        """
        Fetch the latest release notes and GitHub release URL.

        Returns:
            flask.Response: JSON with ``changelog`` and ``release_url`` keys.
        """
        try:
            changelog = update.latest_changelog()
            # You can point directly at the “latest” redirect, or use a tag-specific URL:
            release_url = f"https://github.com/{update.REPO}/releases/latest"
            return jsonify(
                status="ok",
                data={
                    "changelog": changelog,
                    "release_url": release_url,
                }
            )
        except Exception as e:
            app.logger.exception("changelog fetch failed")
            return jsonify(status="error", message="An internal error has occurred."), 500

    # ----------------------------------------------------------------------- #
    @app.route("/api/script_uptime")
    def api_script_uptime():
        """
        Report script-level uptime.

        Always returns 200 OK with a stable JSON schema:
            {
                "status": "ok",
                "data":   { "running": true,  "uptime": 123.45 }
            }
            {
                "status": "ok",
                "data":   { "running": false, "uptime": null  }
            }
        """
        raw = _read_api_file(sst_file)
        if raw is None:
            return jsonify(status="ok",
                        data={"running": False, "uptime": None})
        try:
            start = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S.%f")
        except ValueError:
            # Treat malformed timestamp as "not running"
            return jsonify(status="ok",
                        data={"running": False, "uptime": None})
        uptime = (datetime.now() - start).total_seconds()
        return jsonify(status="ok",
                    data={"running": True, "uptime": uptime})

    # ----------------------------------------------------------------------- #
    @app.route("/api/system_info")
    def api_system_info():
        """
        Return system metrics - OS, CPU, RAM, disk, and network stats.

        Returns:
            flask.Response: JSON payload on success or error message.
        """
        global last_net_io, last_check_time, unwanted
        try:
            # Get OS info
            with open('/etc/os-release', 'r') as f:
                os_release = f.read()
            pretty_name = next(
                line.split('=', 1)[1].strip('"') 
                for line in os_release.split('\n') 
                if line.startswith('PRETTY_NAME=')
            )
            hardware_model = "Unknown"
            # Try Raspberry Pi
            try:
                with open('/proc/device-tree/model', 'r') as f:
                    hardware_model = f.read().strip('\x00')
            except (FileNotFoundError, PermissionError):
                pass  # Not a Pi or no permission
            # Fallback to x86 DMI
            if hardware_model == "Unknown":
                try:
                    with open('/sys/devices/virtual/dmi/id/product_name', 'r') as f:
                        hardware_model = f.read().strip()
                except (FileNotFoundError, PermissionError):
                    pass  # Not available or no permission
            # Final fallback to hostname
            if hardware_model == "Unknown":
                try:
                    hardware_model = socket.gethostname()
                except:
                    hardware_model = "Unknown (Fallback Failed)"
            # Get available disk space (root partition)
            disk_info = subprocess.check_output(
                ['df', '-h', '--output=avail', '/']
            ).decode().split('\n')[1].strip()
            # Uptime
            uptime = time.time() - psutil.boot_time()
            # Get RAM
            vm = psutil.virtual_memory()
            # CPU Usage (percentage)
            cpu_percent = psutil.cpu_percent(interval=1)  
            # Network Usage (bytes sent/received)
            current_net_io = psutil.net_io_counters(pernic=True, nowrap=True)
            current_time = time.time()
            time_elapsed = current_time - last_check_time
            
            # Filter out virtual/unwanted interfaces
            unwanted_interfaces = ['lo', 'docker', 'veth', 'br-', 'virbr', 'tun', 'IO']
            network_stats = {}
            for interface, stats in current_net_io.items():
                if any(unwanted in interface for unwanted in unwanted_interfaces): 
                    continue
                if last_net_io:
                    # Calculate bytes/second
                    recv_rate = (stats.bytes_recv - last_net_io[interface].bytes_recv) / time_elapsed
                    sent_rate = (stats.bytes_sent - last_net_io[interface].bytes_sent) / time_elapsed
                    network_stats[interface] = {
                        'interface': interface,
                        'upload': sent_rate,
                        'download': recv_rate,
                        'total_upload': stats.bytes_sent,
                        'total_download': stats.bytes_recv
                    }
                else: pass
            last_net_io = current_net_io
            last_check_time = current_time
            return jsonify(
                status="ok",
                data={
                    "os_name": pretty_name,
                    "system_uptime": uptime,
                    "hardware_model": hardware_model,
                    "disk_available": disk_info,
                    "memory": {
                        "percent": vm.percent,
                        "used": vm.used,
                        "total": vm.total,
                    },
                    "cpu": {
                        "percent": cpu_percent,
                        "cores": psutil.cpu_count(logical=False),
                        "threads": psutil.cpu_count(logical=True)
                    },
                    "network": {
                        "interfaces": network_stats,
                        "primary_interface": list(network_stats.values())[0] if network_stats else None
                    }
                }
            )
        except Exception as e:
            app.logger.exception("An error occurred while fetching system information")
            return jsonify(
                status="error",
                message="An internal error occurred while fetching system information."
            ), 500

    # ----------------------------------------------------------------------- #
    @app.route("/api/log")
    @app.route("/api/logs")
    def api_logs() -> "flask.Response":
        """
        Tail the most recent log lines, spanning rotated files if needed.
        ?limit=N   Number of lines to return (1-1000). Default 100.

        Response schema
        ---------------
            {
                "status": "ok",
                "data": { "logs": [ "<line>", ... ] }
            }
        """
        try:
            limit = int(request.args.get("limit", 100))
        except ValueError:
            limit = 100
        limit = max(1, min(limit, LOG_HARD_CAP))

        log_path  = Path(log_file).resolve()        # e.g. viewport.log
        log_dir   = log_path.parent
        base_name = log_path.name                   #   "viewport.log"

        # TimedRotatingFileHandler names rotated files like
        #   viewport.log.2025-06-05
        rotated = sorted(
            (p for p in log_dir.glob(f"{base_name}.*") if p.is_file()),
            key=lambda p: p.stat().st_mtime,        # newest first
            reverse=True
        )

        # Always examine current log first, then yesterday, then older …
        candidates = [log_path] + rotated

        remaining = limit
        tail = deque(maxlen=limit)                  # keeps newest lines in order

        for path in candidates:
            try:
                # Read only what we still need from *this* file
                chunk = deque(maxlen=remaining)
                with path.open("r", encoding="utf-8") as f:
                    for line in f:
                        chunk.append(line.rstrip("\n"))
                # Prepend so chronology is preserved when we move to older logs
                tail.extendleft(reversed(chunk))
                remaining = limit - len(tail)
                if remaining == 0:                  # got everything we asked for
                    break
            except Exception:
                app.logger.warning("Could not read %s", path, exc_info=True)

        return jsonify(status="ok", data={"logs": list(tail)})

    # ----------------------------------------------------------------------- #
    @app.route("/api/status")
    def api_status():
        """
        Return the one-line status message written by *viewport.py*.

        Returns:
            flask.Response: JSON ``{"status": "..."}`` or error.
        """
        line = _read_api_file(status_file)
        if line is None:
            return jsonify(status="ok", data={"status": None})
        return jsonify(status="ok", data={"status": line})    

    # ----------------------------------------------------------------------- #
    @app.route("/api/config")
    def api_config():
        """
        Return the merged configuration currently in effect.

        Returns:
            flask.Response: JSON grouping general, browser, and logging
            settings, plus restart scheduling details.
        """
        try:
            # Re-parse config on each call
            cfg = validate_config(strict=False, print=False)
            # pull everything out into locals/globals
            for name, val in vars(cfg).items():
                setattr(_mon, name, val)
                
            restart_times = None
            next_restart = None
            
            if RESTART_TIMES:  # Checks if not None and not empty
                now = datetime.now()
                # compute next run for each time
                next_runs = []
                for t in RESTART_TIMES:
                    run_dt = datetime.combine(now.date(), t)
                    if run_dt <= now: run_dt += timedelta(days=1)
                    next_runs.append(run_dt)
                next_run = min(next_runs)
                restart_times = [t.strftime('%H:%M') for t in RESTART_TIMES]
                next_restart = next_run.isoformat()
                
            return jsonify(
                status="ok",
                data={
                    "general": {
                        "health_interval_sec": getattr(_mon, "SLEEP_TIME", None),
                        "wait_time_sec": getattr(_mon, "WAIT_TIME", None),
                        "max_retries": getattr(_mon, "MAX_RETRIES", None),
                        "restart_times": restart_times,
                        "next_restart": next_restart,
                    },
                    "browser": {
                        "profile_path": getattr(_mon, "BROWSER_PROFILE_PATH", None),
                        "binary_path": getattr(_mon, "BROWSER_BINARY", None),
                        "headless": getattr(_mon, "HEADLESS", None),
                    },
                    "logging": {
                        "log_file_flag": getattr(_mon, "LOG_FILE_FLAG", None),
                        "log_console_flag": getattr(_mon, "LOG_CONSOLE", None),
                        "debug_logging": getattr(_mon, "DEBUG_LOGGING", None),
                        "error_logging": getattr(_mon, "ERROR_LOGGING", None),
                        "ERROR_PRTSCR": getattr(_mon, "ERROR_PRTSCR", None),
                        "log_days": getattr(_mon, "LOG_DAYS", None),
                        "log_interval_min": getattr(_mon, "LOG_INTERVAL", None),
                    },
                })
        except Exception as e:
            logging.error("An error occurred while processing the configuration.", exc_info=True)
            return jsonify(
                status="error",
                message="An internal error has occurred while processing the configuration."
            ), 500
            
    return app

# --------------------------------------------------------------------------- # 
# Run server when invoked directly
# --------------------------------------------------------------------------- # 
def main():
    """
    Entry point for launching the monitoring API.

    * Re-validates configuration when running under pytest.
    * Ensures no duplicate ``monitoring.py`` process is active
        (gracefully terminates one if found).
    * Logs the bind address and starts the Flask development server.
    """
    if "pytest" in sys.modules:
        cfg = validate_config()
        for name, val in vars(cfg).items():
            setattr(_mon, name, val)
    
    should_kill_process = process_handler("monitoring.py", action="check")
    if should_kill_process:
        time.sleep(3)
        process_handler("monitoring.py", action="kill")
    
    logging.info(f"Starting server with http://{host}:{port}")
    create_app().run(host=host or None, port=port or None)

if __name__ == '__main__':
    main()