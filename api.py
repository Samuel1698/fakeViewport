  GNU nano 6.2                                                                                                                                                                       api.py
import os
import logging
import uptime
from datetime import datetime, timedelta
from flask import Flask, jsonify

app = Flask(__name__)

# Set log level to Warning
log = logging.getLogger('werkzeug')
log.setLevel(logging.WARNING)

@app.route('/check_view')
def api_check_view():
    # Construct the path to the file in the user's home directory
    view_status_file = os.path.join(os.path.expanduser('~'), 'view_status.txt')
    with open(view_status_file, 'r') as f:
        result = f.read() == 'True'
    return jsonify(view_status=result)

@app.route('/api/get_system_uptime')
def get_system_uptime():
    # Get the uptime in seconds
    uptime_seconds = uptime.uptime()
    return jsonify(system_uptime=uptime_seconds)

@app.route('/get_script_uptime')
def api_get_script_uptime():
    # Construct the path to the file in the user's home directory
    script_start_time_file = os.path.join(os.path.expanduser('~'), 'script_start_time.txt')
    with open(script_start_time_file, 'r') as f:
        script_start_time = datetime.strptime(f.read(), '%Y-%m-%d %H:%M:%S.%f')
    script_uptime = datetime.now() - script_start_time
    uptime_seconds = script_uptime.total_seconds()
    return jsonify(script_uptime=uptime_seconds)

@app.route('/admin')
def admin():
    view_status = api_check_view().json['view_status']
    script_uptime = api_get_script_uptime().json['script_uptime']
    system_uptime = get_system_uptime().json['system_uptime']

    return jsonify(
        view_status=view_status,
        script_uptime=script_uptime,
        system_uptime=system_uptime
    )

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)