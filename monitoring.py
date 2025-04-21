import os
import logging
import configparser
import uptime
from pathlib import Path
from datetime import datetime
from flask import Flask, jsonify

config = configparser.ConfigParser()
config.read('config.ini')
script_dir = Path(__file__).resolve().parent
API_PATH = config.get('API', 'API_FILE_PATH', fallback=str(script_dir / 'api'))

# Check if API_PATH exists; if not, create an 'api' folder in the current directory
api_dir = Path(API_PATH)
if not api_dir.exists():
    api_dir.mkdir(parents=True, exist_ok=True)
sst_file = api_dir / 'sst.txt'
status_file = api_dir / 'status.txt'

app = Flask(__name__)

# Set log level to Warning
log = logging.getLogger('werkzeug')
log.setLevel(logging.WARNING)

@app.route('/check_view')
def api_check_view():
    if not os.path.exists(status_file):
        return jsonify(view_status="File not found"), 404
    with open(status_file, 'r') as f:
        result = f.read()
    return jsonify(view_status=result)

@app.route('/get_system_uptime')
def get_system_uptime():
    # Get the uptime in seconds
    uptime_seconds = uptime.uptime()
    return jsonify(system_uptime=uptime_seconds)

@app.route('/get_script_uptime')
def api_get_script_uptime():
    if not os.path.exists(sst_file):
        return jsonify(script_uptime="File not found"), 404
    with open(sst_file, 'r') as f:
        script_start_time = datetime.strptime(f.read(), '%Y-%m-%d %H:%M:%S.%f')
    script_uptime = datetime.now() - script_start_time
    uptime_seconds = script_uptime.total_seconds()
    return jsonify(script_uptime=uptime_seconds)

@app.route('/admin')
def admin():
    view_status = api_check_view().json.get('view_status', "File not found")
    script_uptime = api_get_script_uptime().json.get('script_uptime', "File not found")
    system_uptime = get_system_uptime().json['system_uptime']
    return jsonify(
        view_status=view_status,
        script_uptime=script_uptime,
        system_uptime=system_uptime
    )

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)