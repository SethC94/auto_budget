import subprocess
import re
import sys
import time
import shutil
import os
import smtplib
import signal
from email.mime.text import MIMEText
from colorama import init as colorama_init, Fore, Style
import json
import requests

colorama_init(autoreset=True)

NGROK_BIN = "ngrok"  # Or provide full path if not in PATH
LOCAL_PORT = 8080
NGROK_URL_FILE = "ngrok_url.txt"
CONFIG_FILE = "config.json"

def log(msg, color=Fore.RESET):
    print(color + f"[ngrok_server] {time.strftime('%Y-%m-%d %H:%M:%S')} {msg}" + Style.RESET_ALL, flush=True)

def print_startup_banner():
    print(Fore.CYAN + Style.BRIGHT + "\n=== ngrok Log Server Startup ===\n" + Style.RESET_ALL)
    print(Fore.GREEN + Style.BRIGHT + f"✓ Target: http://localhost:{LOCAL_PORT}" + Style.RESET_ALL)
    print(Fore.CYAN + f"\nPID: {os.getpid()}  |  Kill command: {Fore.YELLOW}kill {os.getpid()}{Style.RESET_ALL}")
    print(Fore.CYAN + "Waiting for ngrok public URL...\n" + Style.RESET_ALL)

def print_success_banner(public_url):
    print(Fore.CYAN + Style.BRIGHT + f"\nngrok public URL: {Style.BRIGHT + Fore.YELLOW}{public_url}{Style.RESET_ALL}")
    print(Fore.GREEN + "Server will keep running in the foreground. Check ngrok_url.txt or your heartbeat email for the public URL.\n" + Style.RESET_ALL)

def send_heartbeat_email(public_url):
    """I need to send an email with the ngrok public URL as a heartbeat."""
    try:
        with open(CONFIG_FILE) as f:
            config = json.load(f)
        gmail_user = config["gmail_user"]
        gmail_app_password = config["gmail_app_password"]
        to_email = config["my_alert_email"]
    except Exception as e:
        log(f"ERROR: Could not load email config: {e}", Fore.RED)
        return

    subject = "ngrok Log Server Started"
    body = (
        f"ngrok log server is now running and publicly available.\n\n"
        f"Public URL: {public_url}\n"
        f"Target: http://localhost:{LOCAL_PORT}\n"
    )
    try:
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = gmail_user
        msg['To'] = to_email

        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(gmail_user, gmail_app_password)
        server.sendmail(gmail_user, [to_email], msg.as_string())
        server.quit()
        log("Heartbeat email sent with ngrok public URL.", Fore.GREEN)
    except smtplib.SMTPAuthenticationError as e:
        log(f"ERROR: SMTP authentication failed when sending email: {e}", Fore.RED)
    except Exception as e:
        log(f"ERROR: Failed to send heartbeat email: {e}", Fore.RED)

def extract_public_url(ngrok_output_line):
    """I need to extract the first public HTTPS ngrok URL that's not localhost."""
    https_urls = re.findall(r"(https://[a-zA-Z0-9\-\.]+\.ngrok[^ ]*)", ngrok_output_line)
    for url in https_urls:
        if not url.startswith("https://localhost") and not url.startswith("https://127.0.0.1"):
            return url
    return None

def wait_for_log_server(timeout=10):
    """I need to check that the log server is up before sending the heartbeat email."""
    log(f"Checking if log server is up at http://localhost:{LOCAL_PORT}/...", Fore.GREEN)
    for _ in range(timeout):
        try:
            resp = requests.get(f"http://localhost:{LOCAL_PORT}/", timeout=1)
            if resp.status_code == 200:
                log("Log server is up and responding.", Fore.GREEN)
                return True
        except Exception:
            time.sleep(1)
    log("WARNING: Log server did not respond after waiting. Email will still be sent.", Fore.YELLOW)
    return False

def main():
    print_startup_banner()

    if not shutil.which(NGROK_BIN):
        log(f"ERROR: ngrok not found in PATH as '{NGROK_BIN}'", Fore.RED)
        sys.exit(1)

    ngrok_cmd = [NGROK_BIN, "http", str(LOCAL_PORT), "--log", "stdout"]
    log(f"Starting ngrok with command: {' '.join(ngrok_cmd)}", Fore.GREEN)

    try:
        ngrok_proc = subprocess.Popen(
            ngrok_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1
        )
    except Exception as e:
        log(f"Failed to start ngrok: {e}", Fore.RED)
        sys.exit(1)

    public_url = None
    try:
        # Read ngrok stdout until we find the public URL
        for line in ngrok_proc.stdout:
            log(f"ngrok output: {line.strip()}", Fore.GREEN)
            url = extract_public_url(line)
            if url:
                public_url = url
                log(f"ngrok public URL: {public_url}", Fore.CYAN + Style.BRIGHT)
                try:
                    with open(NGROK_URL_FILE, "w") as f:
                        f.write(public_url + "\n")
                    log(f"Wrote public URL to {NGROK_URL_FILE}", Fore.GREEN)
                except Exception as e:
                    log(f"ERROR: Failed to write to {NGROK_URL_FILE}: {e}", Fore.RED)
                break

        if not public_url:
            log("ERROR: Could not parse public ngrok URL from output. Is ngrok running already? Is there a network issue?", Fore.RED)
            ngrok_proc.terminate()
            sys.exit(1)

        wait_for_log_server(timeout=10)
        print_success_banner(public_url)
        send_heartbeat_email(public_url)

        # TODO: I might want to catch SIGTERM and forward it to ngrok for clean shutdown
        def shutdown_handler(signum, frame):
            log("Shutting down ngrok server...", Fore.CYAN)
            ngrok_proc.terminate()
            sys.exit(0)

        signal.signal(signal.SIGINT, shutdown_handler)
        signal.signal(signal.SIGTERM, shutdown_handler)

        # Keep printing ngrok output and keep the process running
        for line in ngrok_proc.stdout:
            log(f"ngrok output: {line.strip()}", Fore.GREEN)
        ngrok_proc.wait()

    except KeyboardInterrupt:
        log("ngrok server stopped by user", Fore.CYAN)
        try:
            ngrok_proc.terminate()
        except Exception:
            pass
        sys.exit(0)
    except Exception as e:
        log(f"Error running ngrok: {e}", Fore.RED)
        try:
            ngrok_proc.terminate()
        except Exception:
            pass
        sys.exit(1)

if __name__ == "__main__":
    main()
