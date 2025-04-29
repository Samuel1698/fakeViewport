#!/usr/bin/env python3
import os
import time
import configparser
import psutil  # replace external uptime dependency
from pathlib import Path
from datetime import datetime
from flask import Flask, jsonify
from flask_cors import CORS
from logging_config import configure_logging

def create_app(config_path=None):
    # Application factory for the monitoring API
    app = Flask(__name__)

    # Load configuration
    config = configparser.ConfigParser()
    config.read(config_path or 'config.ini')
    LOG_FILE = config.getboolean('Logging', 'LOG_FILE', fallback=True)
    LOG_CONSOLE = config.getboolean('Logging', 'LOG_CONSOLE', fallback=True)
    VERBOSE_LOGGING = config.getboolean('Logging', 'VERBOSE_LOGGING', fallback=False)
    LOG_DAYS = int(config.getint('Logging', 'LOG_DAYS', fallback=7))
    # Determine API directory and files
    script_dir = Path(__file__).resolve().parent
    api_root = config.get('API', 'API_FILE_PATH', fallback=str(script_dir / 'api')).strip()
    api_dir = Path(api_root)
    api_dir.mkdir(parents=True, exist_ok=True)
    sst_file = api_dir / 'sst.txt'
    status_file = api_dir / 'status.txt'

    # Set up Logging
    configure_logging(
        log_file_path=str(script_dir / 'logs' / 'monitoring.log'),
        log_file=LOG_FILE,
        log_console=LOG_CONSOLE,
        log_days=LOG_DAYS,
        verbose_logging=VERBOSE_LOGGING
    )
    # Enable CORS for all routes
    CORS(app)

    def _read_api_file(path, parser_fn=lambda x: x):
        # Centralized file-read logic with error handling
        if not path.exists():
            return None
        try:
            raw = path.read_text().strip()
            return parser_fn(raw)
        except Exception as e:
            app.logger.error(f"Error reading {path}: {e}")
            return None

    @app.route('/api/check_view')
    def api_check_view():
        # Returns the latest status from the status file
        status = _read_api_file(status_file)
        if status is None:
            return jsonify(status='error', message='Status file not found'), 404
        return jsonify(status='ok', data={'view_status': status})

    @app.route('/api/get_system_uptime')
    def api_get_system_uptime():
        # Returns system uptime based on psutil.boot_time()
        try:
            uptime_seconds = time.time() - psutil.boot_time()
            return jsonify(status='ok', data={'system_uptime': uptime_seconds})
        except Exception as e:
            app.logger.error(f"Error getting system uptime: {e}")
            return jsonify(status='error', message='Could not determine system uptime'), 500

    @app.route('/api/get_script_uptime')
    def api_get_script_uptime():
        # Returns how long the script has been running
        raw = _read_api_file(sst_file)
        if raw is None:
            return jsonify(status='error', message='Script SST file not found'), 404
        try:
            start = datetime.strptime(raw, '%Y-%m-%d %H:%M:%S.%f')
            uptime_seconds = (datetime.now() - start).total_seconds()
            return jsonify(status='ok', data={'script_uptime': uptime_seconds})
        except ValueError:
            return jsonify(status='error', message='Malformed timestamp in SST file'), 400

    @app.route('/api/admin')
    def api_admin():
        # Aggregated status endpoint
        view = _read_api_file(status_file) or 'File not found'
        # Script uptime computation
        raw = _read_api_file(sst_file)
        if raw:
            try:
                start = datetime.strptime(raw, '%Y-%m-%d %H:%M:%S.%f')
                script_uptime = (datetime.now() - start).total_seconds()
            except ValueError:
                script_uptime = 'Malformed timestamp'
        else:
            script_uptime = 'File not found'
        # System uptime computation
        try:
            system_uptime = time.time() - psutil.boot_time()
        except Exception:
            system_uptime = 'Error'

        return jsonify(
            status='ok',
            data={
                'view_status': view,
                'script_uptime': script_uptime,
                'system_uptime': system_uptime
            }
        )

    return app
if __name__ == '__main__':
    # Allow host/port configuration via environment
    host = os.getenv('FLASK_RUN_HOST', '0.0.0.0')
    port = int(os.getenv('FLASK_RUN_PORT', 5000))
    create_app().run(
        host=host,
        port=port,
    )