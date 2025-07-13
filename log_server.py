"""
Flask log server for remote log viewing.
I need to run this alongside my main app to securely serve recent logs.
TODO: Switch to a more robust auth system if users increase.
"""

from flask import Flask, Response, request
import os

LOG_FILE = "budget_app_logs.txt"
LOG_LINES = 100
USERNAME = "colin"
PASSWORD = "waffles69"

app = Flask(__name__)

def check_auth(username, password):
    return username == USERNAME and password == PASSWORD

def authenticate():
    return Response(
        "Authentication required", 401,
        {"WWW-Authenticate": 'Basic realm="Login Required"'}
    )

@app.route("/logs")
def logs():
    auth = request.authorization
    if not auth or not check_auth(auth.username, auth.password):
        return authenticate()
    if not os.path.exists(LOG_FILE):
        return Response("No log file found.", mimetype="text/plain")
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()[-LOG_LINES:]
        return Response("".join(lines), mimetype="text/plain")
    except Exception as e:
        return Response(f"Error reading logs: {e}", mimetype="text/plain")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
