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
import json
import requests

from flask import Flask, Response, request

# --- Config ---
REPO_URL = "https://github.com/SethC94/auto_budget.git"
NGROK_DOMAIN = "mackerel-live-roughly.ngrok-free.app"
LOG_FILE = "budget_app_logs.txt"
INCIDENT_LOG = "app_incidents.log"
ALERT_EMAIL = "creasman.alert@gmail.com"
LOG_SERVER_LOCAL_URL = "http://localhost:5000/logs"
HEARTBEAT_INFO_FILE = "app_heartbeat_info.json"  # Persistent heartbeat state

# Email config loaded from config.json
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

# --- Shared heartbeat info (threadsafe) ---
heartbeat_info = {
    "app_start_time": time.time(),
    "last_restart": time.strftime('%Y-%m-%d %I:%M:%S %p'),
    "email_ingest_alive": False,
    "email_ingest_last_check": None,
    "email_ingest_last_error": None,
    "transactions_inserted": 0,
    "emails_skipped": 0,
    "log_server_alive": False,
    "ngrok_url": None,
    "last_critical_error": None,
    "last_git_error": None,
}
heartbeat_lock = threading.Lock()

def update_heartbeat_info(**kwargs):
    with heartbeat_lock:
        heartbeat_info.update(kwargs)
        try:
            with open(HEARTBEAT_INFO_FILE, "w") as f:
                json.dump(heartbeat_info, f)
        except Exception:
            pass

def get_heartbeat_info():
    with heartbeat_lock:
        return dict(heartbeat_info)

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
def kill_other_ngrok_processes():
    """
    I need to kill any other ngrok processes before starting a new tunnel.
    TODO: Test this on both Windows and Unix platforms to make sure it works everywhere.
    """
    try:
        if os.name == 'nt':
            # Windows
            cmd = 'tasklist'
            proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            out, _ = proc.communicate()
            if b'ngrok.exe' in out:
                kill_cmd = 'taskkill /F /IM ngrok.exe'
                subprocess.call(kill_cmd, shell=True)
                logger.info("Killed existing ngrok.exe processes.")
        else:
            # Mac/Linux
            cmd = "pgrep ngrok"
            proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            out, _ = proc.communicate()
            pids = [line.decode().strip() for line in out.splitlines() if line.strip()]
            for pid in pids:
                if pid:
                    os.kill(int(pid), signal.SIGKILL)
            if pids:
                logger.info(f"Killed existing ngrok processes: {', '.join(pids)}")
    except Exception as e:
        logger.warning(f"Failed to kill existing ngrok processes: {e}")

def run_ngrok(domain):
    """I need to keep ngrok running on the specified domain, restarting if needed."""
    while True:
        logger.info("Starting ngrok tunnel...")
        try:
            # I need to make sure no other ngrok processes are running before I start a new one.
            kill_other_ngrok_processes()
            proc = subprocess.Popen(["ngrok", "http", "--domain", domain, "5000"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            _, err = proc.communicate()
            if proc.returncode != 0:
                logger.error(f"ngrok failed: {err.decode('utf-8')}")
                send_error_email("Budget App ngrok Failure", f"ngrok failed to start: {err.decode('utf-8')}")
            time.sleep(10)
        except Exception as e:
            logger.error(f"ngrok crashed: {e}")
            send_error_email("Budget App ngrok Crash", f"ngrok crashed: {e}")
            time.sleep(10)

# --- Ngrok URL Fetcher ---
def get_ngrok_url():
    """I need to get the public ngrok URL if available, or return None."""
    try:
        resp = requests.get("http://localhost:4040/api/tunnels", timeout=2)
        tunnels = resp.json().get("tunnels", [])
        for tunnel in tunnels:
            if tunnel["proto"] == "https":
                # Prefer custom domain
                if NGROK_DOMAIN in tunnel["public_url"]:
                    return tunnel["public_url"] + "/logs"
                # fallback: just return any https tunnel
                return tunnel["public_url"] + "/logs"
        return None
    except Exception:
        return None

def is_log_server_available():
    """I need to check if the log server is responding."""
    try:
        resp = requests.get(LOG_SERVER_LOCAL_URL, timeout=2)
        return resp.status_code == 200
    except Exception:
        return False

def get_log_access_url():
    """I need to return the ngrok log access URL if server is up and ngrok is up."""
    if is_log_server_available():
        url = get_ngrok_url()
        if url:
            return url
    return None

# --- Git command wrapper with robust error handling ---
def run_git_command(args, check=True):
    """
    Run a git command and handle errors, especially auth/SSH problems.
    Returns stdout, raises exception on error.
    TODO: If I get an authentication or SSH error, I need to check my SSH keys and git remote config.
    """
    try:
        logger.info(f"Running git command: {' '.join(args)}")
        proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = proc.communicate()
        out_str = out.decode().strip()
        err_str = err.decode().strip()
        if proc.returncode != 0:
            logger.error(f"Git command failed with code {proc.returncode}: {err_str}")
            auth_errors = [
                "Permission denied",
                "Authentication failed",
                "fatal: could not read Username",
                "fatal: Authentication failed",
                "fatal: unable to access",  # generic but may indicate bad https setup
                "fatal: Could not read from remote repository"
            ]
            for phrase in auth_errors:
                if phrase in err_str or phrase in out_str:
                    logger.critical(
                        "Git authentication/SSH error detected! "
                        "I need to check that my SSH keys are loaded (ssh-add -l), "
                        "my remote uses SSH (git remote -v), and my SSH key is on GitHub. "
                        "See https://docs.github.com/en/authentication/connecting-to-github-with-ssh"
                    )
                    update_heartbeat_info(last_git_error=err_str or out_str)
                    send_error_email(
                        "Budget App Git Auth Error",
                        f"""A git authentication or SSH error occurred:
{err_str or out_str}

TODO: I need to check:
- That my remote URL uses SSH (git remote -v)
- That my SSH key is loaded (ssh-add -l)
- That my SSH key is added to my GitHub account

See https://docs.github.com/en/authentication/connecting-to-github-with-ssh
"""
                    )
                    raise RuntimeError("Git authentication error: " + (err_str or out_str))
            # Some other git error
            update_heartbeat_info(last_git_error=err_str or out_str)
            raise RuntimeError("Git command failed: " + (err_str or out_str))
        update_heartbeat_info(last_git_error=None)
        return out_str
    except Exception as e:
        logger.error(f"Exception running git command: {e}")
        update_heartbeat_info(last_git_error=str(e))
        raise

# --- Email Ingest Process ---
def run_email_ingest(alive_event):
    """I need to run the email ingest script, and exit on KeyboardInterrupt or error."""
    from email_ingest import main as email_main
    try:
        logger.info("Starting email ingest process.")
        # Patch email_ingest to update heartbeat stats
        def track_stats_wrapper(ev):
            import email_ingest as ei
            def stats_handler(event_type, **kwargs):
                if event_type == "ingest_ok":
                    update_heartbeat_info(
                        email_ingest_alive=True,
                        email_ingest_last_check=time.strftime('%Y-%m-%d %I:%M:%S %p'),
                        emails_skipped=kwargs.get("emails_skipped", 0),
                        transactions_inserted=kwargs.get("transactions_inserted", 0),
                        email_ingest_last_error=None
                    )
                elif event_type == "ingest_error":
                    update_heartbeat_info(
                        email_ingest_alive=False,
                        email_ingest_last_error=kwargs.get("error", ""),
                        email_ingest_last_check=time.strftime('%Y-%m-%d %I:%M:%S %p'),
                    )
            ei.HEARTBEAT_STATS_HOOK = stats_handler
            ei.main(ev)
        track_stats_wrapper(alive_event)
    except Exception as e:
        logger.error(f"Email ingest crashed: {e}", exc_info=True)
        update_heartbeat_info(email_ingest_alive=False, email_ingest_last_error=str(e))
        send_error_email("Budget App Email Ingest Crash", f"Email ingest crashed: {e}")
        raise

# --- Self-Updater ---
def is_mainpy_updated():
    """I need to check if remote main.py is newer than local and only update then."""
    try:
        run_git_command(["git", "fetch"])
        local_hash = run_git_command(["git", "rev-parse", "HEAD:main.py"])
        remote_hash = run_git_command(["git", "rev-parse", "origin/main:main.py"])
        return local_hash != remote_hash
    except Exception as e:
        logger.error(f"Failed to check for main.py update: {e}")
        return False

def self_update_and_restart():
    """I need to pull only if main.py changed, then restart. If fails, revert and restart."""
    try:
        current_commit = run_git_command(["git", "rev-parse", "HEAD"])
        run_git_command(["git", "pull"])
        logger.info("Pulled latest code from origin.")
        python = sys.executable
        os.execl(python, python, *sys.argv)
    except Exception as e:
        logger.error(f"Update failed, attempting revert: {e}")
        send_error_email("Budget App Update Failure", f"Update failed: {e}")
        try:
            run_git_command(["git", "reset", "--hard", current_commit])
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
            break
        except Exception as e:
            logger.error(f"App crashed: {e}", exc_info=True)
            update_heartbeat_info(last_critical_error=str(e))
            send_error_email("Budget App Crash", f"App crashed: {e}")
            time.sleep(10)

# --- Remote Restart Trigger ---
def monitor_restart_flag():
    """I need to watch for a 'restart.flag' file to trigger a remote restart."""
    while True:
        if os.path.exists("restart.flag"):
            logger.info("Remote restart flag detected, restarting app.")
            os.remove("restart.flag")
            update_heartbeat_info(last_restart=time.strftime('%Y-%m-%d %I:%M:%S %p'))
            python = sys.executable
            os.execl(python, python, *sys.argv)
        time.sleep(5)

# --- Heartbeat Logging and Email ---
def send_heartbeat_email(alive_event):
    """I need to log a heartbeat, showing component status and including ngrok log link if available."""
    info = get_heartbeat_info()
    log_url = get_log_access_url()
    uptime_sec = int(time.time() - info.get("app_start_time", time.time()))
    uptime_str = f"{uptime_sec//3600}h {(uptime_sec//60)%60}m {uptime_sec%60}s"
    body = f"""
Budget App Health Report

• App running: Yes
• Uptime: {uptime_str}
• Last restart: {info.get('last_restart')}
• Log server: {"Alive" if is_log_server_available() else "NOT RESPONDING"}
• ngrok logs URL: {log_url if log_url else "Unavailable"}
• Email ingest: {"Alive" if info.get('email_ingest_alive') else "DOWN"}
• Last email check: {info.get('email_ingest_last_check')}
• Transactions inserted (since last): {info.get('transactions_inserted')}
• Emails skipped (since last): {info.get('emails_skipped')}
• Last email ingest error: {info.get('email_ingest_last_error') or "-"}
• Last app error: {info.get('last_critical_error') or "-"}
• Last git error: {info.get('last_git_error') or "-"}
• TODO: If you see a git authentication or SSH error, I need to check my remote, agent, and GitHub keys. See the docs for details.

See logs at: {log_url if log_url else 'Unavailable'}
"""
    try:
        msg = MIMEText(body)
        msg['Subject'] = "Budget App Heartbeat"
        msg['From'] = CONFIG["gmail_user"]
        msg['To'] = CONFIG["my_alert_email"]

        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(CONFIG["gmail_user"], CONFIG["gmail_app_password"])
        server.sendmail(CONFIG["gmail_user"], [CONFIG["my_alert_email"]], msg.as_string())
        server.quit()
        logger.info("Heartbeat email sent.")
    except Exception as e:
        logger.error(f"Failed to send heartbeat email: {e}")

def heartbeat(alive_event):
    """I need to log a heartbeat every 10min, showing component status and sending an email."""
    while True:
        update_heartbeat_info(log_server_alive=is_log_server_available(), ngrok_url=get_log_access_url())
        logger.info("I'm alive and running. Everything is super cool. Email ingest alive: %s", alive_event.is_set())
        send_heartbeat_email(alive_event)
        time.sleep(600)

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
        update_heartbeat_info(last_critical_error=str(e))
        send_error_email("Budget App Fatal Error", f"Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
