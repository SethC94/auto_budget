"""
Budget App Main Module
I need to manage ngrok tunnels, git updates, and system monitoring.
TODO: Consider adding more robust error recovery mechanisms.
"""

import subprocess
import time
import logging
import json
import smtplib
import os
from email.mime.text import MIMEText

CONFIG_FILE = "config.json"

def setup_logging():
    """I need to set up logging for the main app component."""
    logger = logging.getLogger("BudgetApp")
    logger.setLevel(logging.INFO)
    fh = logging.FileHandler("budget_app_logs.txt")
    fh.setFormatter(logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s'))
    logger.addHandler(fh)
    sh = logging.StreamHandler()
    sh.setFormatter(logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s'))
    logger.addHandler(sh)
    return logger

logger = setup_logging()

def send_error_email(subject, body):
    """I need to send error notification emails."""
    try:
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
        logger.info(f"Sent error email: {subject}")
    except Exception as e:
        logger.error(f"Failed to send error email: {e}")

def kill_existing_ngrok():
    """I need to kill any existing ngrok processes before starting a new one."""
    try:
        subprocess.run(["taskkill", "/F", "/IM", "ngrok.exe"], 
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        logger.debug(f"Failed to kill ngrok (this is normal if none was running): {e}")

def update_watcher():
    """I need to check for git updates to main.py every 30 seconds and handle updates.
    TODO: Check for updates every 30 seconds instead of 30 minutes for faster iteration.
    TODO: Implement robust rollback if update causes startup failure.
    """
    logger.info("Starting update watcher - checking for git updates every 30 seconds...")
    last_commit = None
    
    while True:
        try:
            # Get current commit hash
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                cwd=os.path.dirname(os.path.abspath(__file__))
            )
            
            if result.returncode == 0:
                current_commit = result.stdout.strip()
                
                if last_commit is None:
                    last_commit = current_commit
                    logger.info(f"Update watcher initialized. Current commit: {current_commit[:8]}")
                elif current_commit != last_commit:
                    logger.info(f"Local commit changed from {last_commit[:8]} to {current_commit[:8]}")
                    last_commit = current_commit
                
                # Check for remote updates
                subprocess.run(["git", "fetch"], capture_output=True)
                
                # Check if main.py has changes on remote
                result = subprocess.run(
                    ["git", "diff", "HEAD", "origin/HEAD", "--name-only"],
                    capture_output=True,
                    text=True,
                    cwd=os.path.dirname(os.path.abspath(__file__))
                )
                
                if result.returncode == 0 and "main.py" in result.stdout:
                    logger.info("main.py has updates on remote. Pulling changes...")
                    send_error_email(
                        "Budget App Update Available",
                        f"main.py has changes on remote. Attempting to pull and restart.\nCurrent commit: {current_commit[:8]}"
                    )
                    
                    # Pull changes
                    pull_result = subprocess.run(
                        ["git", "pull"],
                        capture_output=True,
                        text=True,
                        cwd=os.path.dirname(os.path.abspath(__file__))
                    )
                    
                    if pull_result.returncode == 0:
                        logger.info("Successfully pulled updates. App should restart.")
                        send_error_email(
                            "Budget App Updated Successfully",
                            f"main.py updated successfully. Pull output:\n{pull_result.stdout}"
                        )
                        # Note: In a real implementation, this would trigger an app restart
                    else:
                        logger.error(f"Failed to pull updates: {pull_result.stderr}")
                        send_error_email(
                            "Budget App Update Failed",
                            f"Failed to pull git updates:\n{pull_result.stderr}"
                        )
            else:
                logger.error(f"Failed to get current commit: {result.stderr}")
                
        except Exception as e:
            logger.error(f"Error in update watcher: {e}")
            send_error_email("Budget App Update Watcher Error", f"Update watcher encountered an error: {e}")
        
        # Check for updates every 30 seconds
        time.sleep(30)

def run_ngrok(domain):
    """I need to keep ngrok running on the specified domain, restarting if needed.
    TODO: If I get ERR_NGROK_108, I should alert myself and pause before retrying.
    TODO: If ngrok ever adds an API for agent session management, I should automate that here.
    """
    NGROK_DASHBOARD_URL = "https://dashboard.ngrok.com/agents"
    while True:
        kill_existing_ngrok()
        logger.info("Starting ngrok tunnel...")
        try:
            proc = subprocess.Popen(
                ["ngrok", "http", "--domain", domain, "5000"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            out, err = proc.communicate()
            out_str = out.decode("utf-8", errors="ignore")
            err_str = err.decode("utf-8", errors="ignore")

            if proc.returncode != 0:
                logger.error(f"ngrok failed: {err_str}")

                if "ERR_NGROK_108" in err_str or "Your account is limited to 1 simultaneous ngrok agent sessions" in err_str:
                    msg = (
                        "ngrok failed to start: Too many sessions (ERR_NGROK_108).\n"
                        "I need to clear old agent sessions in the ngrok dashboard before I can connect again.\n"
                        f"Please visit {NGROK_DASHBOARD_URL} and terminate any existing tunnels.\n"
                        "After clearing old sessions, the app will retry automatically."
                    )
                    logger.error(msg)
                    send_error_email(
                        "Budget App ngrok Failure: Too Many Sessions",
                        f"{msg}\n\nFull error:\n{err_str}"
                    )
                    # Optional: Open browser tab if interactive. Uncomment if desired.
                    # import webbrowser
                    # webbrowser.open(NGROK_DASHBOARD_URL)
                    # Wait longer before retrying
                    time.sleep(120)
                else:
                    send_error_email(
                        "Budget App ngrok Failure",
                        f"ngrok failed to start: {err_str}"
                    )
                    time.sleep(10)
            else:
                # ngrok started successfully
                time.sleep(10)
        except Exception as e:
            logger.error(f"ngrok crashed: {e}")
            send_error_email("Budget App ngrok Crash", f"ngrok crashed: {e}")
            time.sleep(10)
