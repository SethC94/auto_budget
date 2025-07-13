"""
Flask log server for remote log viewing.
I need to run this alongside my main app to securely serve recent logs.
TODO: Switch to a more robust auth system if users increase.
TODO: Add better error recovery for failed log file reads.
TODO: Consider limiting concurrent requests to avoid DoS.
"""

import os
import logging
import smtplib
from email.mime.text import MIMEText
from flask import Flask, Response, request

LOG_FILE = "budget_app_logs.txt"
LOG_LINES = 100
USERNAME = "colin"      # TODO: Change to something more secure
PASSWORD = "waffles69"  # TODO: Change to something more secure
CONFIG_FILE = "config.json"

# --- Logging Setup ---
def setup_logging():
    """I need to set up logging for the log server component."""
    logger = logging.getLogger("LogServer")
    logger.setLevel(logging.INFO)
    fh = logging.FileHandler("log_server_activity.log")
    fh.setFormatter(logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s'))
    logger.addHandler(fh)
    sh = logging.StreamHandler()
    sh.setFormatter(logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s'))
    logger.addHandler(sh)
    return logger

logger = setup_logging()

# --- Email Notification ---
def send_status_email(subject, body):
    """I need to send a status email when the log server starts or stops."""
    try:
        import json
        with open(CONFIG_FILE) as f:
            config = json.load(f)
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = config["gmail_user"]
        msg['To'] = config["my_alert_email"]
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(config["gmail_user"], config["gmail_app_password"])
        server.sendmail(config["gmail_user"], [config["my_alert_email"]], msg.as_string())
        server.quit()
        logger.info("Sent status email: %s", subject)
    except Exception as e:
        logger.error("Failed to send status email: %s", e)

def check_auth(username, password):
    """I need to check basic auth credentials."""
    return username == USERNAME and password == PASSWORD

def authenticate():
    """I need to return a 401 for failed auth."""
    return Response(
        "Authentication required", 401,
        {"WWW-Authenticate": 'Basic realm="Login Required"'}
    )

app = Flask(__name__)

@app.route("/logs")
def logs():
    """I need to serve the last N lines of the main log file, with basic auth."""
    auth = request.authorization
    if not auth or not check_auth(auth.username, auth.password):
        logger.warning("Unauthorized log access attempt.")
        return authenticate()
    if not os.path.exists(LOG_FILE):
        return Response("No log file found.", mimetype="text/plain")
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()[-LOG_LINES:]
        return Response("".join(lines), mimetype="text/plain")
    except Exception as e:
        logger.error("Error reading logs: %s", e)
        return Response(f"Error reading logs: {e}", mimetype="text/plain")

def main():
    """I need to start the Flask log server and send start/stop email notifications."""
    logger.info("Log server starting up.")
    send_status_email("Budget App Log Server Started", "The log server has started successfully.")
    try:
        app.run(host="0.0.0.0", port=5000)
    except KeyboardInterrupt:
        logger.info("Log server received shutdown signal. Exiting.")
        send_status_email("Budget App Log Server Stopped", "The log server was stopped (KeyboardInterrupt).")
    except Exception as e:
        logger.error(f"Log server crashed: {e}")
        send_status_email("Budget App Log Server Crashed", f"Log server crashed: {e}")

if __name__ == "__main__":
    main()
