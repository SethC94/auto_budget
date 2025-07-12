import imaplib
import email
import os
import json
import time
import sys
import socket
from datetime import datetime, timedelta
from email.header import decode_header
from email.mime.text import MIMEText
import smtplib
from insert_transaction import insert_transaction
from transaction_parser import parse_email_transaction

CONFIG_PATH = "config.json"
LAST_UID_FILE = "last_email_uid.txt"
LOG_FILE = "app_incidents.log"
BUDGET_APP_LOG = "budget_app_logs.txt"
SHUTDOWN_FILE = "last_shutdown.json"
LAST_TXN_FILE = "last_transaction.json"

RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RESET = "\033[0m"

def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)

def connect_gmail(config):
    """I need to connect to Gmail and select the inbox."""
    mail = imaplib.IMAP4_SSL(config["imap_server"])
    mail.login(config["gmail_user"], config["gmail_app_password"])
    mail.select("inbox")
    return mail

def get_last_processed_uid():
    if os.path.exists(LAST_UID_FILE):
        with open(LAST_UID_FILE, "r") as f:
            try:
                return int(f.read().strip())
            except Exception:
                # TODO: If the file is corrupted, I need to handle it better
                return 0
    return 0

def set_last_processed_uid(uid):
    with open(LAST_UID_FILE, "w") as f:
        f.write(str(uid))

def log_incident(message):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open(LOG_FILE, "a", encoding="utf-8") as logf:
        logf.write(f"[{timestamp}] {message}\n")

def log_budget_app(message):
    """I need to log all general activity to my main budget app log."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open(BUDGET_APP_LOG, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")

def fetch_transaction_emails_since(mail, last_uid):
    if last_uid > 0:
        criteria = f"(UID {last_uid+1}:*)"
    else:
        criteria = "ALL"
    status, messages = mail.uid('search', None, criteria)
    if status != "OK":
        return []
    return messages[0].split()

def get_email_body(msg):
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition"))
            if ctype == "text/plain" and "attachment" not in disp:
                charset = part.get_content_charset() or "utf-8"
                return part.get_payload(decode=True).decode(charset, errors="ignore")
    else:
        charset = msg.get_content_charset() or "utf-8"
        return msg.get_payload(decode=True).decode(charset, errors="ignore")
    return ""

def send_email(config, subject, body):
    if "my_alert_email" not in config:
        print(f"{RED}No 'my_alert_email' found in config; cannot send email.{RESET}")
        log_budget_app("Attempted to send email but 'my_alert_email' not found in config.")
        return False
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = config["gmail_user"]
    msg['To'] = config["my_alert_email"]

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(config["gmail_user"], config["gmail_app_password"])
            server.sendmail(msg['From'], [msg['To']], msg.as_string())
        log_incident(f"Sent email: {subject}")
        log_budget_app(f"Sent email: {subject}")
        return True
    except Exception as e:
        log_incident(f"Failed to send email '{subject}': {e}")
        log_budget_app(f"Failed to send email '{subject}': {e}")
        print(f"{RED}Failed to send email '{subject}': {e}{RESET}")
        return False

def send_heartbeat_email(config, extra_message=None):
    body = "Budget app heartbeat: I'm still running."
    if extra_message:
        body += "\n\n" + extra_message
    send_email(config, "Budget App Heartbeat", body)

def send_startup_email(config, startup_time, prev_shutdown=None, last_txn=None):
    body = f"Budget app has STARTED.\n\nStartup time: {startup_time}\n"
    if prev_shutdown:
        body += f"Previous shutdown: {prev_shutdown.get('shutdown_time', 'unknown')}\n"
        if prev_shutdown.get("reason"):
            body += f"Last shutdown reason: {prev_shutdown['reason']}\n"
        if prev_shutdown.get("shutdown_time"):
            try:
                prev = datetime.strptime(prev_shutdown["shutdown_time"], "%Y-%m-%d %H:%M:%S")
                now = datetime.strptime(startup_time, "%Y-%m-%d %H:%M:%S")
                downtime = now - prev
                mins = int(downtime.total_seconds() // 60)
                secs = int(downtime.total_seconds() % 60)
                body += f"Downtime: {mins} min {secs} sec\n"
            except Exception:
                body += "Downtime: unknown (couldn't parse timestamps)\n"
    if last_txn:
        body += f"\nLast Transaction Processed:\n{json.dumps(last_txn, indent=2)}"
    body += "\n\nLast several log lines:\n" + get_last_log_lines(LOG_FILE, 10)
    send_email(config, "Budget App Started", body)

def send_shutdown_email(config, shutdown_time, reason=None, last_txn=None):
    log_tail = get_last_log_lines(LOG_FILE, 10)
    body = f"Budget app SHUTDOWN ALERT!\n\nShutdown time: {shutdown_time}\n"
    if reason:
        body += f"Reason: {reason}\n"
    if last_txn:
        body += f"\nLast Transaction Processed:\n{json.dumps(last_txn, indent=2)}"
    body += "\nLast several log lines:\n" + log_tail
    send_email(config, "Budget App Shutdown", body)

def get_last_log_lines(filename, num_lines=10):
    if not os.path.exists(filename):
        return "(No log file found)"
    try:
        with open(filename, "r", encoding="utf-8") as f:
            lines = f.readlines()
        return "".join(lines[-num_lines:])
    except Exception:
        return "(Error reading log file)"

def record_shutdown(shutdown_time, reason=None):
    data = {
        "shutdown_time": shutdown_time,
        "reason": reason if reason else "",
        "was_clean": reason is None
    }
    with open(SHUTDOWN_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f)

def read_shutdown_record():
    if not os.path.exists(SHUTDOWN_FILE):
        return None
    try:
        with open(SHUTDOWN_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except Exception:
        return None

def clear_shutdown_record():
    if os.path.exists(SHUTDOWN_FILE):
        os.remove(SHUTDOWN_FILE)

def save_last_transaction(txn):
    with open(LAST_TXN_FILE, "w", encoding="utf-8") as f:
        json.dump(txn, f)

def load_last_transaction():
    if not os.path.exists(LAST_TXN_FILE):
        return None
    try:
        with open(LAST_TXN_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def should_parse_email(subject, body):
    subject = (subject or "").lower()
    body = (body or "").lower()
    triggers = [
        "debit alert for your usaa bank account",
        "debit is more than amount set",
        "came out of your account ending in",
        "you asked us to let you know when there’s a debit over a certain amount.",
    ]
    for t in triggers:
        if t in subject or t in body:
            return True
    return False

def print_color(msg, color):
    print(f"{color}{msg}{RESET}")

def main():
    config = load_config()
    print_color("Starting email listener. Press Ctrl+C to stop.", CYAN)
    log_budget_app("Started email listener.")

    POLL_INTERVAL = 30  # seconds
    heartbeat_subject = "Budget App Heartbeat"

    last_processed_uid = get_last_processed_uid()
    last_txn = load_last_transaction()
    shutdown_info = read_shutdown_record()
    startup_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    print_color(f"Last processed email UID: {last_processed_uid}", CYAN)
    log_budget_app(f"Last processed email UID: {last_processed_uid}")
    if shutdown_info:
        print_color(f"Detected previous shutdown at {shutdown_info.get('shutdown_time', '?')}", YELLOW)
        log_budget_app(f"Detected previous shutdown at {shutdown_info.get('shutdown_time', '?')}")
        if shutdown_info.get("reason"):
            print_color(f"Last shutdown reason: {shutdown_info['reason']}", YELLOW)
            log_budget_app(f"Last shutdown reason: {shutdown_info['reason']}")
        if last_txn:
            print_color(f"Last transaction processed before downtime:\n{json.dumps(last_txn, indent=2)}", YELLOW)
            log_budget_app(f"Last transaction processed before downtime: {last_txn}")
    else:
        print_color("No previous shutdown detected.", CYAN)
        log_budget_app("No previous shutdown detected.")
    send_startup_email(config, startup_time, shutdown_info, last_txn)
    log_budget_app("Sent startup email.")
    clear_shutdown_record()

    last_heartbeat_time = datetime.now() - timedelta(hours=1)

    while True:
        try:
            now = datetime.now()
            now_str = now.strftime('%Y-%m-%d %H:%M:%S')

            # Connect/disconnect on every poll for max reliability
            try:
                mail = connect_gmail(config)
                log_budget_app("Connected to Gmail inbox.")
                email_uids = fetch_transaction_emails_since(mail, last_processed_uid)

                if not email_uids:
                    pass
                else:
                    for uid_bytes in email_uids:
                        uid = int(uid_bytes)
                        if uid <= last_processed_uid:
                            continue

                        res, data = mail.uid('fetch', uid_bytes, '(RFC822)')
                        if res != "OK":
                            msg_log = f"Failed to fetch email UID {uid}"
                            print_color(msg_log, RED)
                            log_incident(msg_log)
                            log_budget_app(msg_log)
                            set_last_processed_uid(uid)
                            last_processed_uid = uid
                            continue

                        msg = email.message_from_bytes(data[0][1])
                        subject, encoding = decode_header(msg["Subject"])[0]
                        if isinstance(subject, bytes):
                            subject = subject.decode(encoding or "utf-8", errors="ignore")
                        subject = subject.strip() if subject else ""
                        body = get_email_body(msg)

                        if subject == heartbeat_subject:
                            print_color(f"Skipped heartbeat email UID {uid}.", YELLOW)
                            log_incident(f"Skipped heartbeat email UID {uid}.")
                            log_budget_app(f"Skipped heartbeat email UID {uid}.")
                            mail.uid('store', uid_bytes, '+FLAGS', '\\Seen')
                            set_last_processed_uid(uid)
                            last_processed_uid = uid
                            continue
                        if not subject and not body:
                            print_color(f"Skipped email UID {uid} (no subject or body).", YELLOW)
                            log_incident(f"Skipped email UID {uid} (no subject or body).")
                            log_budget_app(f"Skipped email UID {uid} (no subject or body).")
                            mail.uid('store', uid_bytes, '+FLAGS', '\\Seen')
                            set_last_processed_uid(uid)
                            last_processed_uid = uid
                            continue

                        if should_parse_email(subject, body):
                            print_color(f"Transaction email detected (UID {uid}). Subject: {subject}", GREEN)
                            log_budget_app(f"Transaction email detected (UID {uid}). Subject: {subject}")
                            txn = parse_email_transaction(body)
                            if txn:
                                print_color(f"Parsed transaction: {txn}", GREEN)
                                log_budget_app(f"Parsed transaction: {txn}")
                                insert_transaction(txn, config)
                                save_last_transaction(txn)
                                log_incident(f"Processed transaction from email UID {uid}: {txn}")
                                log_budget_app(f"Processed transaction from email UID {uid}: {txn}")
                            else:
                                msg_log = f"Failed to parse transaction in email (UID {uid})."
                                print_color(msg_log, RED)
                                log_incident(msg_log)
                                log_budget_app(msg_log)
                        else:
                            print_color(f"Skipped email UID {uid} (not a transaction alert). Subject: {subject}", YELLOW)
                            log_incident(f"Skipped email UID {uid} (not a transaction alert).")
                            log_budget_app(f"Skipped email UID {uid} (not a transaction alert).")
                        mail.uid('store', uid_bytes, '+FLAGS', '\\Seen')
                        set_last_processed_uid(uid)
                        last_processed_uid = uid

                mail.logout()
                log_budget_app("Logged out from Gmail.")

            except (imaplib.IMAP4.abort, imaplib.IMAP4.error, socket.error, ConnectionResetError) as e:
                # Recoverable IMAP/network error: log, wait, and retry
                print_color(f"IMAP/network error: {e}, will retry in 60 seconds.", RED)
                log_incident(f"IMAP/network error: {e}, will retry in 60 seconds.")
                log_budget_app(f"IMAP/network error: {e}, will retry in 60 seconds.")
                time.sleep(60)
                continue

            if (now - last_heartbeat_time).total_seconds() >= 3600:
                send_heartbeat_email(config)
                last_heartbeat_time = now
                print_color("Heartbeat sent.", CYAN)
                log_budget_app("Heartbeat sent.")

            time.sleep(POLL_INTERVAL)

        except KeyboardInterrupt:
            shutdown_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            print_color("KeyboardInterrupt: Shutting down gracefully...", YELLOW)
            log_incident("Received KeyboardInterrupt. Shutting down gracefully.")
            log_budget_app("Received KeyboardInterrupt. Shutting down gracefully.")
            record_shutdown(shutdown_time)
            send_shutdown_email(config, shutdown_time, reason="Clean shutdown (KeyboardInterrupt)", last_txn=load_last_transaction())
            print_color("Budget app shut down cleanly.", CYAN)
            log_budget_app("Budget app shut down cleanly.")
            sys.exit(0)
        except Exception as e:
            shutdown_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            print_color(f"Crash: {e}", RED)
            log_incident(f"Crash: {e}")
            log_budget_app(f"Crash: {e}")
            record_shutdown(shutdown_time, reason=str(e))
            send_shutdown_email(config, shutdown_time, reason=str(e), last_txn=load_last_transaction())
            print_color("Budget app crashed and alert sent.", RED)
            log_budget_app("Budget app crashed and alert sent.")
            sys.exit(1)

if __name__ == "__main__":
    main()
