#!/usr/bin/env python3
import sys
import os
import time
import configparser
import psutil
import subprocess
import logging
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
import viewport
from logging_config import configure_logging
from validate_config import validate_config, AppConfig
from dotenv import load_dotenv, find_dotenv

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
            subprocess.Popen(
                [sys.executable, str(script_dir / "viewport.py"), flag],
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

    @app.route("/api")
    @app.route("/api/")
    def api_index():
        return jsonify({
            "script_uptime":   url_for("api_script_uptime",  _external=True),
            "system_uptime":   url_for("api_system_uptime",  _external=True),
            "ram":             url_for("api_ram",            _external=True),
            "health_interval": url_for("api_health_interval",_external=True),
            "log_interval":    url_for("api_log_interval",   _external=True),
            "logs":            url_for("api_logs",           _external=True),
            "status":          url_for("api_status",         _external=True),
            "next_restart":    url_for("api_next_restart",   _external=True),
            "log_entry":       url_for("api_log_entry",      _external=True),
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

    @app.route("/api/system_uptime")
    def api_system_uptime():
        try:
            uptime = time.time() - psutil.boot_time()
            return jsonify(status="ok", data={"system_uptime": uptime})
        except Exception:
            return jsonify(status="error",
                           message="Could not determine system uptime"), 500

    @app.route("/api/ram")
    def api_ram():
        vm = psutil.virtual_memory()
        return jsonify(status="ok", data={"ram_used": vm.used, "ram_total": vm.total})

    @app.route("/api/health_interval")
    def api_health_interval():
        return jsonify(status="ok", data={"health_interval_sec": SLEEP_TIME})

    @app.route("/api/log_interval")
    def api_log_interval():
        return jsonify(status="ok", data={"log_interval_min": LOG_INTERVAL})
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
    @app.route("/api/next_restart")
    def api_next_restart():
        if not RESTART_TIMES:
            return jsonify(status="error", message="No restart times configured"), 404
        now = datetime.now()
        # compute next run for each time
        next_runs = []
        for t in RESTART_TIMES:
            run_dt = datetime.combine(now.date(), t)
            if run_dt <= now:
                run_dt += timedelta(days=1)
            next_runs.append(run_dt)
        next_run = min(next_runs)
        return jsonify(status="ok", data={"next_restart": next_run.isoformat()})
    @app.route("/api/log_entry")
    def api_log_entry():
        if not log_file.exists():
            return jsonify(status="error", message="Log file not found"), 404
        try:
            lines = log_file.read_text().splitlines()
            entry = lines[-1] if lines else None
            return jsonify(status="ok", data={"log_entry": entry})
        except Exception as e:
            app.logger.error(f"Error reading log file: {e}")
            return jsonify(status="error", message="Error reading log file"), 500

    return app

# ----------------------------------------------------------------------------- 
# Run server when invoked directly
# ----------------------------------------------------------------------------- 
def main():
    # This is only needed to inject the different configs we test with
    if "pytest" in sys.modules:
        cfg = validate_config()
        for name, val in vars(cfg).items():
            setattr(_mon, name, val)
    logging.info(f"Starting server with http://{host}:{port}")
    create_app().run(host=host or None,
                     port=port or None)
    
if __name__ == '__main__':
    main()