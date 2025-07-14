import imaplib
import email
import time
import json
import os
import sys
import threading
import subprocess
import logging
import signal
from logging.handlers import RotatingFileHandler
import smtplib
from email.mime.text import MIMEText
import re
import pygsheets
import requests
from flask import Flask, Response, request
from datetime import datetime
from colorama import init as colorama_init, Fore, Style
import shutil

colorama_init(autoreset=True)

CONFIG_FILE = "config.json"
LOG_FILE = "budget_app_logs.txt"
LAST_TXN_FILE = "last_transaction.json"
HEARTBEAT_INTERVAL = 1800
EMAIL_POLL_INTERVAL = 60
LOG_SERVER_PORT = 8080
LOG_SERVER_USERNAME = "admin"
LOG_SERVER_PASSWORD = "changeme"
NGROK_URL_FILE = "ngrok_url.txt"
NGROK_LOG_FILE = "ngrok_stdout.log"
NGROK_BIN_CANDIDATES = [
    "/usr/local/bin/ngrok",
    "/usr/bin/ngrok",
    "/opt/homebrew/bin/ngrok",
    "/snap/bin/ngrok"
]

APPSTATE_TAB = "AppState"
APPSTATE_UID_CELL = "A1"
APPSTATE_LAST_UP_CELL = "B1"
APPSTATE_LAST_DOWN_CELL = "B2"

NGROK_PUBLIC_URL = None
NGROK_STATUS = "unknown"
APP_RUNNING = True
NGROK_PROCESS = None

def print_startup_banner():
    print(Fore.CYAN + Style.BRIGHT + "\n=== Budget App Startup ===\n" + Style.RESET_ALL)
    print(Fore.GREEN + Style.BRIGHT + "✓ Health: OK" + Style.RESET_ALL)
    print(f"Log server: {Fore.YELLOW}http://localhost:{LOG_SERVER_PORT}/logs{Style.RESET_ALL}")
    print(f"Username: {Fore.YELLOW}{LOG_SERVER_USERNAME}{Style.RESET_ALL}")
    print(f"Password: {Fore.YELLOW}{LOG_SERVER_PASSWORD}{Style.RESET_ALL}")
    print(Fore.BLUE + f"\nPID: {os.getpid()}  |  Kill command: {Fore.YELLOW}kill {os.getpid()}{Style.RESET_ALL}")
    print(Fore.MAGENTA + "App will now run in the background. Check logs for ongoing status.\n" + Style.RESET_ALL)

def ensure_python_and_deps():
    if sys.version_info < (3, 7):
        print(Fore.RED + "Python 3.7 or later is required. Please upgrade your Python runtime." + Style.RESET_ALL)
        sys.exit(1)
    try:
        import pip
    except ImportError:
        print(Fore.RED + "pip is not installed. Please install pip for Python 3." + Style.RESET_ALL)
        sys.exit(1)
    required = ["pygsheets", "flask", "requests", "colorama"]
    missing = []
    for pkg in required:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        print(Fore.YELLOW + "Some required Python packages are missing: " + ", ".join(missing) + Style.RESET_ALL)
        print("You can install them with:")
        print(Fore.CYAN + f"python3 -m pip install {' '.join(missing)}" + Style.RESET_ALL)
        sys.exit(1)

def find_ngrok_binary():
    env_ngrok = os.environ.get("NGROK_BIN")
    if env_ngrok and shutil.which(env_ngrok):
        return env_ngrok
    for candidate in NGROK_BIN_CANDIDATES:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    path_ngrok = shutil.which("ngrok")
    if path_ngrok:
        return path_ngrok
    return None

def daemonize():
    if os.name != "posix":
        print(Fore.RED + "WARNING: Daemon mode only supported on Linux/Mac right now. Running in foreground." + Style.RESET_ALL)
        return
    if os.fork() > 0:
        os._exit(0)
    os.setsid()
    if os.fork() > 0:
        os._exit(0)
    sys.stdout.flush()
    sys.stderr.flush()
    with open('/dev/null', 'rb', 0) as devnull:
        os.dup2(devnull.fileno(), sys.stdin.fileno())
    with open('budget_app_stdout.log', 'ab', 0) as out:
        os.dup2(out.fileno(), sys.stdout.fileno())
    with open('budget_app_stderr.log', 'ab', 0) as err:
        os.dup2(err.fileno(), sys.stderr.fileno())

try:
    with open(CONFIG_FILE) as f:
        CONFIG = json.load(f)
except Exception as e:
    print(f"{Fore.RED}Error loading config: {e}{Style.RESET_ALL}")
    sys.exit(1)

def setup_logging():
    logger = logging.getLogger("BudgetApp")
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s', datefmt='%Y-%m-%d %I:%M:%S %p')
    fh = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3)
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(formatter)
    logger.addHandler(sh)
    return logger

logger = setup_logging()

def log_ngrok_output_to_logger():
    try:
        with open(NGROK_LOG_FILE, "rt", encoding="utf-8", errors="replace") as logf:
            for line in logf:
                line = line.rstrip()
                if line:
                    logger.debug("ngrok: %s", line)
    except Exception as ex:
        logger.error("Failed to read ngrok log: %s", ex)

def extract_tunnel_from_log():
    """Extract the ngrok tunnel URL directly from the log file as a fallback"""
    try:
        with open(NGROK_LOG_FILE, "rt", encoding="utf-8", errors="replace") as logf:
            for line in logf:
                if "started tunnel" in line and "url=" in line:
                    url_part = line.split("url=")[-1].strip()
                    return url_part
    except Exception:
        return None
    return None

def start_ngrok(port):
    global NGROK_PROCESS, NGROK_PUBLIC_URL
    ngrok_bin = find_ngrok_binary()
    if ngrok_bin is None:
        logger.error("ngrok binary not found. Please install ngrok and ensure it is in your PATH or set NGROK_BIN environment variable.")
        logger.error("Download ngrok from https://ngrok.com/download, then run 'ngrok config add-authtoken <YOUR_TOKEN>'")
        return
    logger.info(f"Starting ngrok at {ngrok_bin} on port {port}...")
    stop_ngrok()
    ngrok_log = open(NGROK_LOG_FILE, "w", encoding="utf-8")
    NGROK_PROCESS = subprocess.Popen(
        [ngrok_bin, "http", str(port), "--log=stdout", "--log-format=logfmt"],
        stdout=ngrok_log, stderr=subprocess.STDOUT
    )

    api_url = "http://127.0.0.1:4040/api/tunnels"
    tunnel_url = None
    found_tunnel = False
    for attempt in range(60):  # Up to 60 seconds
        if NGROK_PROCESS.poll() is not None:
            logger.error("ngrok process exited unexpectedly. Check ngrok_stdout.log for details.")
            ngrok_log.flush()
            ngrok_log.close()
            log_ngrok_output_to_logger()
            return
        try:
            resp = requests.get(api_url, timeout=2)
            if resp.status_code == 200:
                tunnels = resp.json().get("tunnels", [])
                for tunnel in tunnels:
                    # Accept both http and https tunnels
                    if tunnel["proto"] in ["http", "https"]:
                        tunnel_url = tunnel["public_url"]
                        with open(NGROK_URL_FILE, "w") as f:
                            f.write(tunnel_url)
                        logger.info(f"ngrok public URL: {tunnel_url}")
                        NGROK_PUBLIC_URL = tunnel_url
                        found_tunnel = True
                        break
            if found_tunnel:
                break
        except Exception as ex:
            logger.debug(f"ngrok API not up yet: {ex}")
        time.sleep(1)
        ngrok_log.flush()

    # If we couldn't get the tunnel from the API, try to extract it from the log file
    if not found_tunnel:
        ngrok_log.flush()
        # Try to extract the URL from the log file directly
        tunnel_url = extract_tunnel_from_log()
        if tunnel_url:
            logger.info(f"Extracted ngrok URL from logs: {tunnel_url}")
            with open(NGROK_URL_FILE, "w") as f:
                f.write(tunnel_url)
            NGROK_PUBLIC_URL = tunnel_url
            found_tunnel = True

    ngrok_log.close()

    if not found_tunnel:
        logger.error("ngrok did not start or public URL not found after 60 seconds. Is ngrok installed and configured? Check ngrok_stdout.log for details.")
        log_ngrok_output_to_logger()

def stop_ngrok():
    global NGROK_PROCESS
    if NGROK_PROCESS and NGROK_PROCESS.poll() is None:
        NGROK_PROCESS.terminate()
        try:
            NGROK_PROCESS.wait(timeout=5)
        except Exception:
            NGROK_PROCESS.kill()
    NGROK_PROCESS = None

def cleanup_and_exit():
    stop_ngrok()
    logger.info("Cleaned up ngrok process.")

def get_appstate_sheet(gc, sh):
    try:
        wks = sh.worksheet('title', APPSTATE_TAB)
    except pygsheets.WorksheetNotFound:
        wks = sh.add_worksheet(APPSTATE_TAB, rows=10, cols=2)
        wks.update_value(APPSTATE_UID_CELL, "0")
        wks.update_value(APPSTATE_LAST_UP_CELL, "")
        wks.update_value(APPSTATE_LAST_DOWN_CELL, "")
    return wks

def save_last_uid(uid):
    try:
        gc = pygsheets.authorize(service_account_file=CONFIG["google_service_account_json"])
        sh = gc.open(CONFIG["sheet_name"])
        wks = get_appstate_sheet(gc, sh)
        wks.update_value(APPSTATE_UID_CELL, str(uid))
        logger.info(f"Saved last UID {uid} to Google Sheet AppState tab")
    except Exception as e:
        logger.error(f"Failed to save last UID to Google Sheet: {e}")

def load_last_uid():
    try:
        gc = pygsheets.authorize(service_account_file=CONFIG["google_service_account_json"])
        sh = gc.open(CONFIG["sheet_name"])
        wks = get_appstate_sheet(gc, sh)
        val = wks.get_value(APPSTATE_UID_CELL)
        return int(val) if val and val.strip().isdigit() else None
    except Exception as e:
        logger.error(f"Failed to load last UID from Google Sheet: {e}")
        return None

def save_last_up():
    try:
        gc = pygsheets.authorize(service_account_file=CONFIG["google_service_account_json"])
        sh = gc.open(CONFIG["sheet_name"])
        wks = get_appstate_sheet(gc, sh)
        now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
        wks.update_value(APPSTATE_LAST_UP_CELL, now_str)
        logger.info(f"Saved last up time {now_str} to Google Sheet AppState tab")
    except Exception as e:
        logger.error(f"Failed to save last up time to Google Sheet: {e}")

def load_last_up():
    try:
        gc = pygsheets.authorize(service_account_file=CONFIG["google_service_account_json"])
        sh = gc.open(CONFIG["sheet_name"])
        wks = get_appstate_sheet(gc, sh)
        val = wks.get_value(APPSTATE_LAST_UP_CELL)
        return val.strip() if val else "N/A"
    except Exception as e:
        logger.error(f"Failed to load last up time from Google Sheet: {e}")
        return "N/A"

def save_last_down():
    try:
        gc = pygsheets.authorize(service_account_file=CONFIG["google_service_account_json"])
        sh = gc.open(CONFIG["sheet_name"])
        wks = get_appstate_sheet(gc, sh)
        now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
        wks.update_value(APPSTATE_LAST_DOWN_CELL, now_str)
        logger.info(f"Saved last down time {now_str} to Google Sheet AppState tab")
    except Exception as e:
        logger.error(f"Failed to save last down time to Google Sheet: {e}")

def load_last_down():
    try:
        gc = pygsheets.authorize(service_account_file=CONFIG["google_service_account_json"])
        sh = gc.open(CONFIG["sheet_name"])
        wks = get_appstate_sheet(gc, sh)
        val = wks.get_value(APPSTATE_LAST_DOWN_CELL)
        return val.strip() if val else "N/A"
    except Exception as e:
        logger.error(f"Failed to load last down time from Google Sheet: {e}")
        return "N/A"

def send_email(subject, body):
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
        logger.info(f"Email sent: {subject}")
    except Exception as e:
        logger.error(f"Failed to send email: {e}")

def parse_email_transaction(body):
    lines = [line.strip() for line in body.replace('\r\n', '\n').replace('\r', '\n').split('\n') if line.strip()]
    amount = None
    amount_pattern_1 = re.compile(r'\$([0-9,]+\.\d{2}) came out of your account')
    amount_pattern_2 = re.compile(r'for \$([0-9,]+\.\d{2})')
    for line in lines:
        match = amount_pattern_1.search(line)
        if match:
            amount = match.group(1)
            break
        match = amount_pattern_2.search(line)
        if match:
            amount = match.group(1)
            break

    merchant = None
    for i, line in enumerate(lines):
        if "*To:*" in line or "To:" in line:
            if line.strip() in ("*To:*", "To:"):
                for j in range(i+1, len(lines)):
                    next_line = lines[j].strip()
                    if next_line:
                        merchant = next_line
                        break
                break
            else:
                merchant = line.split(":", 1)[-1].strip("*").strip()
                break

    if not merchant:
        for line in lines:
            if line.lower().startswith("merchant:"):
                merchant = line.split(":", 1)[-1].strip()
                break

    date = None
    for i, line in enumerate(lines):
        if "*Date:*" in line or "Date:" in line:
            if line.strip() in ("*Date:*", "Date:"):
                for j in range(i+1, len(lines)):
                    next_line = lines[j].strip()
                    if next_line:
                        date = next_line
                        break
                break
            else:
                date = line.split(":", 1)[-1].strip("*").strip()
                break

    if not amount or not merchant or not date:
        return None

    return {
        "amount": amount,
        "desc": merchant,
        "date": date
    }

def get_allowed_categories(wks):
    cats = wks.get_values('B28', 'B79')
    return [c[0] for c in cats if c and c[0].strip()]

def classify_category(desc, allowed_categories):
    desc_low = desc.lower()
    rules = [
        (r'safeway|save mart|grocery|foodmaxx|winco|whalers|grocery outlet|costco', 'Groceries'),
        (r'mcdonald|wendy|taco bell|in-n-out|sonic|popeyes|little caesars|chick[- ]fil[- ]a|arby|jack in the box|burger', 'Fast Food'),
        (r'amazon', 'Shopping'),
        (r'target|wal[- ]?mart|ross|macys|abc stores|dollar tree', 'Shopping'),
        (r'starbucks|dunkin', 'Coffee Shops'),
        (r'chevron|arco|shell|gas|fuel|7-eleven', 'Gas'),
        (r'cinemark|movies|theatre', 'Movies & DVDs'),
    ]
    for regex, mapped in rules:
        if re.search(regex, desc_low):
            if mapped in allowed_categories:
                return mapped
    if "Uncategorized" in allowed_categories:
        return "Uncategorized"
    if "Shopping" in allowed_categories:
        return "Shopping"
    return allowed_categories[0] if allowed_categories else ""

def insert_transaction(txn):
    gc = pygsheets.authorize(service_account_file=CONFIG["google_service_account_json"])
    sh = gc.open(CONFIG["sheet_name"])
    wks = sh.worksheet('title', CONFIG["transactions_tab"])
    summary_wks = sh.worksheet('title', CONFIG["summary_tab"])
    allowed_categories = get_allowed_categories(summary_wks)
    txn['category'] = classify_category(txn['desc'], allowed_categories)
    wks.insert_rows(4, number=1, values=None)
    row = 5
    wks.update_value((row, 2), txn['date'])
    wks.update_value((row, 3), txn['amount'])
    wks.update_value((row, 4), txn['desc'])
    wks.update_value((row, 5), txn['category'])
    save_last_transaction(txn)
    logger.info(f"Inserted transaction at row {row}: {txn}")

def save_last_transaction(txn):
    with open(LAST_TXN_FILE, "w") as f:
        json.dump(txn, f)

def load_last_transaction():
    try:
        with open(LAST_TXN_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return None

def run_log_server():
    app = Flask(__name__)
    def get_recent_log_lines():
        try:
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                return f.readlines()[-100:]
        except Exception:
            return ["Error reading log file"]
    @app.route("/")
    def index():
        return (
            "<h1>Budget App Log Server</h1>"
            "<p>Go to <a href='/logs'>/logs</a> (authentication required).</p>"
        )
    @app.route("/logs")
    def logs_route():
        auth = request.authorization
        if not auth or not (auth.username == LOG_SERVER_USERNAME and auth.password == LOG_SERVER_PASSWORD):
            return Response("Authentication required", 401, {"WWW-Authenticate": 'Basic realm="Login Required"'})
        return Response("".join(get_recent_log_lines()), mimetype="text/plain")
    app.run(host="0.0.0.0", port=LOG_SERVER_PORT, use_reloader=False)

def check_ngrok_status():
    global NGROK_PUBLIC_URL, NGROK_STATUS
    NGROK_PUBLIC_URL = None
    NGROK_STATUS = "unknown"
    try:
        if os.path.exists(NGROK_URL_FILE):
            with open(NGROK_URL_FILE, "r") as f:
                url = f.read().strip()
                if url:
                    NGROK_PUBLIC_URL = url
                    try:
                        resp = requests.get(url, timeout=5)
                        if resp.status_code == 200:
                            NGROK_STATUS = "up"
                        else:
                            NGROK_STATUS = f"down (HTTP {resp.status_code})"
                    except Exception as e:
                        NGROK_STATUS = f"down ({e})"
    except Exception as e:
        NGROK_STATUS = f"error ({e})"

def check_inbox_and_process():
    last_uid = load_last_uid()
    transactions_processed = 0
    emails_skipped = 0
    imap = None
    try:
        imap = imaplib.IMAP4_SSL(CONFIG["imap_server"])
        imap.login(CONFIG["gmail_user"], CONFIG["gmail_app_password"])
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
                logger.info(f"Transaction email found (UID {uid}): {subject}")
                insert_transaction(txn)
                transactions_processed += 1
            else:
                emails_skipped += 1
                logger.debug(f"Skipped non-transaction email UID {uid}")
            save_last_uid(uid)
        imap.logout()
        return transactions_processed, emails_skipped
    except Exception as e:
        if imap:
            try:
                imap.logout()
            except Exception:
                pass
        logger.error(f"IMAP error: {e}")
        return 0, 0

def send_down_email_and_save():
    try:
        save_last_down()
        last_up = load_last_up()
        now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
        msg = (
            f"Budget App is going down at {now_str} (UTC).\n"
            f"Last up time was: {last_up}\n"
        )
        send_email("Budget App Down", msg)
        logger.info("Shutdown notification email sent")
    except Exception as e:
        logger.error(f"Failed to send down email or update last down time: {e}")

def shutdown_handler(signum, frame):
    global APP_RUNNING
    logger.info(f"Received shutdown signal ({signum}), preparing to exit.")
    APP_RUNNING = False
    send_down_email_and_save()
    cleanup_and_exit()
    sys.exit(0)

def run_health_checks():
    last_heartbeat = 0
    total_transactions = 0
    total_skipped = 0
    logger.info("Health checks started. Monitoring every 30 minutes...")
    try:
        while APP_RUNNING:
            now = time.time()
            save_last_up()
            check_ngrok_status()
            heartbeat_msg = (
                f"Budget App is running normally.\n\n"
                f"Status Summary:\n"
                f"• App uptime: {int((now - START_TIME) // 3600)} hours\n"
                f"• Last up time: {load_last_up()}\n"
                f"• Last down time: {load_last_down()}\n"
                f"• Total transactions: {total_transactions}\n"
                f"• Emails skipped: {total_skipped}\n"
                f"• Last transaction: {str(load_last_transaction())}\n"
            )
            heartbeat_msg += (
                f"\n• Log server local URL: http://localhost:{LOG_SERVER_PORT}/logs\n"
                f"  Username: {LOG_SERVER_USERNAME}\n"
                f"  Password: {LOG_SERVER_PASSWORD}\n"
            )
            if NGROK_PUBLIC_URL:
                heartbeat_msg += (
                    f"\n• ngrok public URL: {NGROK_PUBLIC_URL}\n"
                    f"  ngrok status: {NGROK_STATUS}\n"
                )
            else:
                heartbeat_msg += (
                    f"\n• ngrok public URL: (not found in {NGROK_URL_FILE})\n"
                )
            send_email("Budget App Health Check", heartbeat_msg)
            logger.info("Health check email sent")
            for _ in range(HEARTBEAT_INTERVAL):
                if not APP_RUNNING:
                    break
                time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Health check stopped by user")
        send_down_email_and_save()
    except Exception as e:
        logger.error(f"Fatal error in health check: {e}")
        send_email("Budget App Error", f"The budget app encountered an error: {e}")
        send_down_email_and_save()
        raise

def run_email_ingest():
    logger.info("Email ingest started. Monitoring for transaction emails...")
    try:
        while APP_RUNNING:
            check_inbox_and_process()
            time.sleep(EMAIL_POLL_INTERVAL)
    except KeyboardInterrupt:
        logger.info("Email ingest stopped by user")
        send_down_email_and_save()
    except Exception as e:
        logger.error(f"Fatal error in email ingest: {e}")
        send_email("Budget App Error", f"The budget app encountered an error: {e}")
        send_down_email_and_save()
        raise

def main():
    global START_TIME
    START_TIME = time.time()
    ensure_python_and_deps()
    print_startup_banner()
    time.sleep(2)
    # Comment out daemonize() for foreground debugging
    daemonize()
    logger.info("Budget App starting up. Let's get to work!")
    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)
    ngrok_thread = threading.Thread(target=start_ngrok, args=(LOG_SERVER_PORT,), daemon=True)
    ngrok_thread.start()
    log_server_thread = threading.Thread(target=run_log_server, daemon=True)
    log_server_thread.start()
    health_thread = threading.Thread(target=run_health_checks, daemon=True)
    health_thread.start()
    try:
        run_email_ingest()
    finally:
        cleanup_and_exit()

if __name__ == "__main__":
    main()
