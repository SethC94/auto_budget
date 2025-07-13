"""
Main entry point and orchestrator for my budget app.
I need to supervise all components: email ingest, log server, ngrok tunnel, self-updates, error handling, and incident logging.
TODO: Review all TODOs below and improve as needed.
"""

import os
import sys
import time
import threading
import subprocess
import logging
from logging.handlers import RotatingFileHandler
import smtplib
from email.mime.text import MIMEText
import signal
import queue

from flask import Flask, Response, request

# --- Config ---
REPO_URL = "https://github.com/SethC94/auto_budget.git"
NGROK_DOMAIN = "mackerel-live-roughly.ngrok-free.app"
LOG_FILE = "budget_app_logs.txt"
INCIDENT_LOG = "app_incidents.log"
ALERT_EMAIL = "creasman.alert@gmail.com"

# Email config loaded from config.json
import json
with open("config.json") as f:
    CONFIG = json.load(f)

# --- Logging Setup ---
def setup_logging():
    """I need to set up rich logging to file and stdout, with custom formatting."""
    logger = logging.getLogger("BudgetApp")
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s', datefmt='%Y-%m-%d %I:%M:%S %p')

    # File handler (rotates at 5MB, keeps 3 backups)
    fh = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3)
    fh.setFormatter(formatter)
    fh.setLevel(logging.INFO)
    logger.addHandler(fh)

    # Incident handler (errors and above)
    ih = RotatingFileHandler(INCIDENT_LOG, maxBytes=2 * 1024 * 1024, backupCount=2)
    ih.setFormatter(formatter)
    ih.setLevel(logging.WARNING)
    logger.addHandler(ih)

    # Stdout handler (always present)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(formatter)
    sh.setLevel(logging.INFO)
    logger.addHandler(sh)
    return logger

logger = setup_logging()

# --- Email Notification ---
def send_error_email(subject, body):
    """I need to email myself when something bad happens."""
    try:
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = CONFIG["gmail_user"]
        msg['To'] = CONFIG["my_alert_email"]

        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(CONFIG["gmail_user"], CONFIG["gmail_app_password"])
        server.sendmail(CONFIG["gmail_user"], [CONFIG["my_alert_email"]], msg.as_string())
        server.quit()
    except Exception as e:
        logger.error(f"Failed to send alert email: {e}")

# --- Flask Log Server ---
def run_log_server():
    """I need to serve recent logs with basic auth via Flask, always running."""
    app = Flask(__name__)
    USERNAME = "colin"   # TODO: Change to something more secure
    PASSWORD = "waffles69"

    @app.route("/logs")
    def logs():
        auth = request.authorization
        if not auth or not (auth.username == USERNAME and auth.password == PASSWORD):
            return Response("Authentication required", 401, {"WWW-Authenticate": 'Basic realm="Login Required"'})
        try:
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                lines = f.readlines()[-100:]
            return Response("".join(lines), mimetype="text/plain")
        except Exception as e:
            return Response(f"Error reading logs: {e}", mimetype="text/plain")

    app.run(host="0.0.0.0", port=5000)

# --- Ngrok Tunnel ---
def run_ngrok(domain):
    """I need to keep ngrok running on the specified domain, restarting if needed."""
    while True:
        logger.info("Starting ngrok tunnel...")
        try:
            proc = subprocess.Popen(["ngrok", "http", "--domain", domain, "5000"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            _, err = proc.communicate()
            if proc.returncode != 0:
                logger.error(f"ngrok failed: {err.decode('utf-8')}")
                send_error_email("Budget App ngrok Failure", f"ngrok failed to start: {err.decode('utf-8')}")
            time.sleep(10)  # Wait before restart
        except Exception as e:
            logger.error(f"ngrok crashed: {e}")
            send_error_email("Budget App ngrok Crash", f"ngrok crashed: {e}")
            time.sleep(10)

# --- Email Ingest Process ---
def run_email_ingest(alive_event):
    """I need to run the email ingest script, and exit on KeyboardInterrupt or error."""
    from email_ingest import main as email_main
    try:
        logger.info("Starting email ingest process.")
        email_main(alive_event)
    except Exception as e:
        logger.error(f"Email ingest crashed: {e}", exc_info=True)
        send_error_email("Budget App Email Ingest Crash", f"Email ingest crashed: {e}")
        raise

# --- Self-Updater ---
def is_mainpy_updated():
    """I need to check if remote main.py is newer than local and only update then."""
    try:
        # Fetch remote main.py hash
        subprocess.run(["git", "fetch"], check=True)
        local_hash = subprocess.check_output(["git", "rev-parse", "HEAD:main.py"]).strip()
        remote_hash = subprocess.check_output(["git", "rev-parse", "origin/main:main.py"]).strip()
        return local_hash != remote_hash
    except Exception as e:
        logger.error(f"Failed to check for main.py update: {e}")
        return False

def self_update_and_restart():
    """I need to pull only if main.py changed, then restart. If fails, revert and restart."""
    try:
        # Save current commit hash
        current_commit = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()
        # Try to pull
        subprocess.run(["git", "pull"], check=True)
        logger.info("Pulled latest code from origin.")
        # Restart self
        python = sys.executable
        os.execl(python, python, *sys.argv)
    except Exception as e:
        logger.error(f"Update failed, attempting revert: {e}")
        send_error_email("Budget App Update Failure", f"Update failed: {e}")
        # Revert to last commit
        try:
            subprocess.run(["git", "reset", "--hard", current_commit], check=True)
            logger.info("Reverted to last known-good commit.")
            python = sys.executable
            os.execl(python, python, *sys.argv)
        except Exception as e2:
            logger.critical(f"Failed to revert: {e2}")
            send_error_email("Budget App Revert Failure", f"Revert failed: {e2}")
            raise

def update_watcher():
    """I need to check for main.py updates every 30min and update if needed."""
    while True:
        time.sleep(1800)
        if is_mainpy_updated():
            logger.info("main.py was updated in git, initiating self-update.")
            self_update_and_restart()

# --- Watcher (Resilience) ---
def app_watchdog(target_func, *args, **kwargs):
    """I need to keep the app running, revert if it crashes after update."""
    while True:
        try:
            target_func(*args, **kwargs)
            break  # Normal exit
        except Exception as e:
            logger.error(f"App crashed: {e}", exc_info=True)
            send_error_email("Budget App Crash", f"App crashed: {e}")
            # TODO: If crash right after update, attempt auto-revert here
            # For now, just restart
            time.sleep(10)

# --- Remote Restart Trigger ---
def monitor_restart_flag():
    """I need to watch for a 'restart.flag' file to trigger a remote restart."""
    while True:
        if os.path.exists("restart.flag"):
            logger.info("Remote restart flag detected, restarting app.")
            os.remove("restart.flag")
            python = sys.executable
            os.execl(python, python, *sys.argv)
        time.sleep(5)

# --- Heartbeat Logging ---
def heartbeat(alive_event):
    """I need to log a heartbeat every 10min, showing component status."""
    while True:
        time.sleep(600)
        logger.info("I'm alive and running. Everything is super cool. Email ingest alive: %s", alive_event.is_set())

# --- Main Orchestration ---
def main():
    """I need to orchestrate all app functions: servers, ingest, updater, etc."""
    logger.info("Budget App starting up. Let's get to work!")

    # Shared status event for heartbeat
    alive_event = threading.Event()
    alive_event.set()

    # Log server (thread)
    log_server_thread = threading.Thread(target=run_log_server, daemon=True)
    log_server_thread.start()

    # ngrok tunnel (thread)
    ngrok_thread = threading.Thread(target=run_ngrok, args=(NGROK_DOMAIN,), daemon=True)
    ngrok_thread.start()

    # Email ingest (thread + resilience)
    email_thread = threading.Thread(target=app_watchdog, args=(run_email_ingest, alive_event), daemon=True)
    email_thread.start()

    # Update watcher (thread)
    update_thread = threading.Thread(target=update_watcher, daemon=True)
    update_thread.start()

    # Heartbeat log (thread)
    heartbeat_thread = threading.Thread(target=heartbeat, args=(alive_event,), daemon=True)
    heartbeat_thread.start()

    # Remote restart monitor (thread)
    restart_thread = threading.Thread(target=monitor_restart_flag, daemon=True)
    restart_thread.start()

    # Main thread: wait for all others
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("Budget App received shutdown signal. Exiting.")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error in main: {e}", exc_info=True)
        send_error_email("Budget App Fatal Error", f"Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
