#!/usr/bin/env python3
import os
import sys
import time
import configparser
import psutil
import subprocess
from functools import wraps
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse
from flask import (
    Flask, render_template, request,
    session, redirect, url_for, flash,
    jsonify
)
from flask_cors import CORS
from logging_config import configure_logging
from dotenv import load_dotenv, find_dotenv
dotenv_file = find_dotenv()
load_dotenv(dotenv_file, override=True)
# -------------------------------------------------------------------
# Application for the monitoring API
# -------------------------------------------------------------------
def create_app(config_path=None):
    app = Flask(__name__)

    # -----------------------------
    # Load configuration
    # -----------------------------
    config = configparser.ConfigParser()
    config.read(config_path or 'config.ini')
    LOG_FILE = config.getboolean('Logging', 'LOG_FILE', fallback=True)
    LOG_CONSOLE = config.getboolean('Logging', 'LOG_CONSOLE', fallback=True)
    DEBUG_LOGGING = config.getboolean('Logging', 'DEBUG_LOGGING', fallback=False)
    LOG_DAYS = config.getint('Logging', 'LOG_DAYS', fallback=7)
    # Health check interval (seconds)
    SLEEP_TIME = config.getint('General', 'SLEEP_TIME', fallback=300)
    # Log interval (minutes)
    LOG_INTERVAL = config.getint('General', 'LOG_INTERVAL', fallback=60)
     # ─────── Secret & Sessions ───────
    CONTROL_TOKEN = os.getenv("SECRET", "").strip()
    # always give Flask a non-empty secret_key so session/flash() work
    app.secret_key = CONTROL_TOKEN or os.urandom(24)
    # -----------------------------
    # Prepare API directory and files
    # -----------------------------
    script_dir = Path(__file__).resolve().parent
    api_root = config.get('API', 'API_FILE_PATH', fallback=str(script_dir / 'api')).strip()
    api_dir = Path(api_root)
    api_dir.mkdir(parents=True, exist_ok=True)
    sst_file = api_dir / 'sst.txt'
    status_file = api_dir / 'status.txt'
    log_file = script_dir / 'logs' / 'viewport.log'
    # -----------------------------
    # Setup Logging
    # -----------------------------
    configure_logging(
        log_file_path=str(script_dir / 'logs' / 'monitoring.log'),
        log_file=LOG_FILE,
        log_console=LOG_CONSOLE,
        log_days=LOG_DAYS,
        Debug_logging=DEBUG_LOGGING
    )

    # -----------------------------
    # Enable CORS
    # -----------------------------
    CORS(app)

    # -----------------------------
    # Helper: read and strip text files
    # -----------------------------
    def _read_api_file(path):
        if not path.exists():
            return None
        try:
            return path.read_text().strip()
        except Exception as e:
            app.logger.error(f"Error reading {path}: {e}")
            return None
    # ─────────────────────────────────────────────────────
    # Protect routes if SECRET is set
    # ─────────────────────────────────────────────────────
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
    # ─────── Routes ───────
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
            return jsonify(status="error", message=str(e)), 500

    @app.route("/api")
    @app.route("/api/")
    def api_index():
        return jsonify({
            "script_uptime":   url_for("api_script_uptime",  _external=True),
            "system_uptime":   url_for("api_system_uptime",  _external=True),
            "ram":             url_for("api_ram",            _external=True),
            "health_interval": url_for("api_health_interval",_external=True),
            "log_interval":    url_for("api_log_interval",   _external=True),
            "status":          url_for("api_status",         _external=True),
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

    @app.route("/api/status")
    def api_status():
        line = _read_api_file(status_file)
        if line is None:
            return jsonify(status="error", message="Status file not found"), 404
        return jsonify(status="ok", data={"status": line})

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

# -------------------------------------------------------------------
# Run server when invoked directly
# -------------------------------------------------------------------
if __name__ == '__main__':
    host = os.getenv('FLASK_RUN_HOST', '0.0.0.0')
    port = int(os.getenv('FLASK_RUN_PORT', 5000))
    create_app().run(host=host, port=port)