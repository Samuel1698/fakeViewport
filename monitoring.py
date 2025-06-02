#!/usr/bin/env python3
import sys, os, time, configparser, psutil, subprocess, logging  
from functools import wraps
from pathlib import Path
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

script_dir = Path(__file__).resolve().parent
_base = Path(__file__).parent
config_file = _base / 'config.ini'
env_file    = _base / '.env'
logs_dir    = _base / 'logs'
api_dir     = _base / 'api'

# ----------------------------------------------------------------------------- 
# Load and validate everything via our shared validator
# ----------------------------------------------------------------------------- 
cfg = validate_config()
# pull everything out into locals/globals
for name, val in vars(cfg).items():
    setattr(_mon, name, val)
# ----------------------------------------------------------------------------- 
# Setup Logging
# ----------------------------------------------------------------------------- 
configure_logging(
    log_file_path=str(mon_file),
    log_file=LOG_FILE_FLAG,
    log_console=LOG_CONSOLE,
    log_days=LOG_DAYS,
    Debug_logging=DEBUG_LOGGING
)
# ----------------------------------------------------------------------------- 
# Application for the monitoring API
# ----------------------------------------------------------------------------- 
def create_app():
    app = Flask(__name__)
    # This is only needed to inject the different configs we test with
    if "pytest" in sys.modules:
        cfg = validate_config()
        for name, val in vars(cfg).items():
            setattr(_mon, name, val)
    app.secret_key  = CONTROL_TOKEN or os.urandom(24)
    # ----------------------------------------------------------------------------- 
    # Enable CORS
    # ----------------------------------------------------------------------------- 
    CORS(app)
    # ----------------------------------------------------------------------------- 
    # Helper: read and strip text files
    # ----------------------------------------------------------------------------- 
    def _read_api_file(path):
        if not path.exists():
            return None
        try:
            return path.read_text().strip()
        except Exception as e:
            app.logger.error(f"Error reading {path}: {e}")
            return None
    app._read_api_file = _read_api_file
    # ----------------------------------------------------------------------------- 
    # Protect routes if SECRET is set
    # ----------------------------------------------------------------------------- 
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
    # ----------------------------------------------------------------------------- 
    # Routes
    # ----------------------------------------------------------------------------- 
    @app.route("/login", methods=["GET", "POST"])
    def login():
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
                if not urlparse(next_url).netloc and not urlparse(next_url).scheme:
                    # Safe relative path, redirect to it
                    return redirect(next_url)
                # Unsafe or invalid path, redirect to dashboard
                return redirect(url_for("dashboard"))

            # Failed login: flash error, but session stays cleared
            error = "Invalid API key"
            flash(error, "danger")

        # Render login form (with any flashed message)
        return render_template("login.html", error=error)

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.route("/")
    @login_required
    def dashboard():
        return render_template("index.html")

    @app.route("/api/control/<action>", methods=["POST"])
    @login_required
    def api_control(action):
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
    # ----------------------------------------------------------------------------- 
    # Update
    # ----------------------------------------------------------------------------- 
    @app.route("/api/update")
    def api_update_info():
        try:
            return jsonify(status="ok", data={
                "current": update.current_version(),
                "latest":  update.latest_version(),
            })
        except Exception as e:
            app.logger.exception("version check failed")
            return jsonify(status="error", message=str(e)), 500
    @app.route("/api/update/changelog")
    def api_update_changelog():
        # Fetch and return the latest release changelog (up to the '---' delimiter),
        # plus a link to the GitHub release page.
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
            return jsonify(status="error", message=str(e)), 500
    @app.route("/api/update/apply", methods=["POST"])
    @login_required
    def api_update_apply():
        # ignore any prefer_git flag—perform_update now always
        # tries git first (if clean) then falls back to tar
        outcome = update.perform_update()
        return jsonify(status="ok", data={"outcome": outcome}), 202
    # ----------------------------------------------------------------------------- 
    @app.route("/api/self/restart", methods=["POST"])
    @login_required
    def api_restart():
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
            return jsonify(status="error", message=str(e)), 500
    # ----------------------------------------------------------------------------- 
    @app.route("/api")
    @app.route("/api/")
    def api_index():
        return jsonify({
            "update":          url_for("api_update_info",     _external=True),
            "update/changelog":url_for("api_update_changelog",_external=True),
            "script_uptime":   url_for("api_script_uptime",   _external=True),
            "system_info":     url_for("api_system_info",     _external=True),
            "logs":            url_for("api_logs",            _external=True),
            "status":          url_for("api_status",          _external=True),
            "config":          url_for("api_config",          _external=True),
        })
    @app.route("/api/script_uptime")
    def api_script_uptime():
        raw = _read_api_file(sst_file)
        if raw is None:
            return jsonify(status="error", message="SST file not found"), 404
        try:
            start = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S.%f")
            uptime = (datetime.now() - start).total_seconds()
            return jsonify(status="ok", data={"script_uptime": uptime})
        except ValueError:
            return jsonify(status="error", message="Malformed SST timestamp"), 400
    @app.route("/api/system_info")
    def api_system_info():
        try:
            # Get OS info
            with open('/etc/os-release', 'r') as f:
                os_release = f.read()
            pretty_name = next(
                line.split('=', 1)[1].strip('"') 
                for line in os_release.split('\n') 
                if line.startswith('PRETTY_NAME=')
            )
            # Get hardware model (works for Raspberry Pi and many x86 systems)
            hardware_model = "Unknown"
            try:
                # Try Raspberry Pi first
                with open('/proc/device-tree/model', 'r') as f:
                    hardware_model = f.read().strip('\x00')
                if not hardware_model:  # Fallback to x86 systems
                    with open('/sys/class/dmi/id/product_name', 'r') as f:
                        hardware_model = f.read().strip()
            except:
                pass  # Keep "Unknown" if both methods fail
            # Get available disk space (root partition)
            disk_info = subprocess.check_output(
                ['df', '-h', '--output=avail', '/']
            ).decode().split('\n')[1].strip()
            # Uptime
            uptime = time.time() - psutil.boot_time()
            # Get RAM
            vm = psutil.virtual_memory()
            return jsonify(
                status="ok",
                data={
                    "os_name": pretty_name,
                    "system_uptime": uptime,
                    "hardware_model": hardware_model,
                    "disk_available": disk_info,
                    "ram_used": vm.used, 
                    "ram_total": vm.total
                }
            )
        except Exception as e:
            return jsonify(
                status="error",
                message=f"System info error: {str(e)}"
            ), 500
    @app.route("/api/log")
    @app.route("/api/logs")
    def api_logs():
        # grab optional ?limit=... (default 100)
        try:
            limit = int(request.args.get("limit", 100))
        except ValueError:
            limit = 100
        try:
            # tail the file
            with open(log_file, 'r') as f:
                last_lines = deque(f, maxlen=limit)
            # return as an array of strings
            return jsonify(status="ok", data={"logs": list(last_lines)})
        except Exception as e:
            app.logger.exception("Failed reading logs")
            return jsonify(status="error", message="An internal error occurred while reading logs"), 500
    @app.route("/api/status")
    def api_status():
        line = _read_api_file(status_file)
        if line is None:
            return jsonify(status="error", message="Status file not found"), 404
        return jsonify(status="ok", data={"status": line})    
    @app.route("/api/config")
    def api_config():
        try:
            # Re-parse config on each call
            cfg = validate_config(strict=False)
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
            return jsonify(
                status="error",
                message=f"Config error: {str(e)}"
            ), 500
            
    return app

# ----------------------------------------------------------------------------- 
# Run server when invoked directly
# ----------------------------------------------------------------------------- 
def main():
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