"""
Email ingest for my budget app.
I need to poll Gmail, parse transactions, and insert them into my sheet.
TODO: Refactor for more robust IMAP and error handling if needed.
TODO: Add startup and shutdown email notifications for monitoring.
TODO: Consider limiting the number of retries on error.
"""

import imaplib
import email
import time
import json
import traceback
import logging
import requests
import smtplib
from email.mime.text import MIMEText
from insert_transaction import insert_transaction
from transaction_parser import parse_email_transaction
from modify_budget import load_config

HEARTBEAT_INTERVAL = 3600  # seconds (1 hour)
LAST_UID_FILE = "last_email_uid.txt"
LAST_TXN_FILE = "last_transaction.json"
LOG_SERVER_LOCAL_URL = "http://localhost:5000/logs"
CONFIG_FILE = "config.json"

def get_logger():
    """I need to get the main logger for the app."""
    logger = logging.getLogger("EmailIngest")
    if not logger.handlers:
        fh = logging.FileHandler("email_ingest_activity.log")
        fh.setFormatter(logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s'))
        logger.addHandler(fh)
        sh = logging.StreamHandler()
        sh.setFormatter(logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s'))
        logger.addHandler(sh)
    logger.setLevel(logging.INFO)
    return logger

logger = get_logger()

def send_status_email(subject, body):
    """I need to send a status or heartbeat email."""
    try:
        with open(CONFIG_FILE) as f:
            config = json.load(f)
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = config["gmail_user"]
        msg['To'] = config["my_alert_email"]
        s = smtplib.SMTP("smtp.gmail.com", 587)
        s.starttls()
        s.login(config["gmail_user"], config["gmail_app_password"])
        s.sendmail(config["gmail_user"], [config["my_alert_email"]], msg.as_string())
        s.quit()
        logger.info(f"Sent email: {subject}")
    except Exception as e:
        logger.error(f"Failed to send status email: {e}")

def save_last_uid(uid):
    with open(LAST_UID_FILE, "w") as f:
        f.write(str(uid))

def load_last_uid():
    try:
        with open(LAST_UID_FILE, "r") as f:
            return int(f.read().strip())
    except Exception:
        return None

def save_last_transaction(txn):
    with open(LAST_TXN_FILE, "w") as f:
        json.dump(txn, f)

def load_last_transaction():
    try:
        with open(LAST_TXN_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return None

def get_ngrok_url():
    """I need to get the public ngrok URL if available, or return None."""
    try:
        resp = requests.get("http://localhost:4040/api/tunnels", timeout=2)
        tunnels = resp.json().get("tunnels", [])
        for tunnel in tunnels:
            if tunnel["proto"] == "https" and "log" in tunnel["public_url"]:
                return tunnel["public_url"] + "/logs"
            if tunnel["proto"] == "https":
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

def check_inbox_and_process(config, alive_event):
    """I need to connect to IMAP, look for new transaction emails, and process them."""
    last_uid = load_last_uid()
    last_txn = load_last_transaction()
    logger.info("Started email listener.")
    logger.info(f"Last processed email UID: {last_uid}")

    imap = None
    try:
        imap = imaplib.IMAP4_SSL(config["imap_server"])
        imap.login(config["gmail_user"], config["gmail_app_password"])
        logger.info("Connected to Gmail inbox.")

        imap.select("inbox")
        status, data = imap.uid('search', None, "ALL")
        uids = [int(x) for x in data[0].split()]
        new_uids = [uid for uid in uids if last_uid is None or uid > last_uid]

        for uid in new_uids:
            status, msg_data = imap.uid('fetch', str(uid), '(RFC822)')
            if status != "OK":
                continue
            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)
            subject = msg["Subject"]
            if msg.is_multipart():
                for part in msg.walk():
                    ctype = part.get_content_type()
                    if ctype == "text/plain":
                        body = part.get_payload(decode=True).decode()
                        break
                else:
                    body = ""
            else:
                body = msg.get_payload(decode=True).decode()

            txn = parse_email_transaction(body)
            if txn:
                logger.info(f"Transaction email detected (UID {uid}). Subject: {subject}")
                insert_transaction(txn, config)
                save_last_transaction(txn)
                logger.info(f"Processed transaction from email UID {uid}: {txn}")
            else:
                logger.info(f"Skipped email UID {uid} (not a transaction alert).")
            save_last_uid(uid)
        imap.logout()
        logger.info("Logged out from Gmail.")
    except Exception as e:
        if imap:
            try:
                imap.logout()
            except Exception:
                pass
        logger.error(f"IMAP/network error: {e}, will retry in 60 seconds.")
        raise
    finally:
        alive_event.set()

def main(alive_event=None):
    """I need to poll Gmail for transaction emails and process them, sending alerts on start/stop/crash."""
    send_status_email("Budget App Email Ingest Started", "The email ingestion process has started successfully.")
    config = load_config()
    last_heartbeat = 0
    try:
        while True:
            now = time.time()
            try:
                check_inbox_and_process(config, alive_event)
            except Exception as e:
                # If IMAP fails, log and wait before retry
                logger.error(f"Exception in email ingest loop: {e}\n{traceback.format_exc()}")
                send_status_email("Budget App Email Ingest Error", f"Exception in email ingest loop:\n{e}\n{traceback.format_exc()}")
                time.sleep(60)
                continue

            # Send heartbeat email every hour, with log URL if available
            if now - last_heartbeat > HEARTBEAT_INTERVAL:
                log_url = get_log_access_url()
                body = "Budget App email ingest is alive and working!"
                if log_url:
                    body += f"\nSee logs at: {log_url}"
                send_status_email("Budget App Email Ingest Heartbeat", body)
                logger.info("Heartbeat sent.")
                last_heartbeat = now

            time.sleep(30)  # Poll interval
    except KeyboardInterrupt:
        logger.info("Email ingest process received shutdown signal. Exiting.")
        send_status_email("Budget App Email Ingest Stopped", "The email ingestion process was stopped (KeyboardInterrupt).")
    except Exception as e:
        logger.error(f"Fatal error in email ingest main: {e}\n{traceback.format_exc()}")
        send_status_email("Budget App Email Ingest Crashed", f"Fatal error:\n{e}\n{traceback.format_exc()}")

if __name__ == "__main__":
    import threading
    main(threading.Event())
