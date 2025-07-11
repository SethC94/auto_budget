import imaplib
import email
import os
import json
import time
from datetime import datetime
from email.header import decode_header
from insert_transaction import insert_transaction
from transaction_parser import parse_email_transaction

CONFIG_PATH = "config.json"

def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)

def connect_gmail(config):
    mail = imaplib.IMAP4_SSL(config["imap_server"])
    mail.login(config["gmail_user"], config["gmail_app_password"])
    mail.select("inbox")
    return mail

def fetch_unseen_transaction_emails(mail):
    status, messages = mail.search(None, '(UNSEEN)')
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

def main():
    config = load_config()
    print("Starting email listener. Press Ctrl+C to stop.")
    subject_trigger = "Debit Alert for Your USAA Bank Account"  # Only process emails with this in the subject

    POLL_INTERVAL = 30  # seconds

    while True:
        try:
            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            print(f"[{now_str}] Checking for new emails...")  # Regular heartbeat log

            mail = connect_gmail(config)
            email_ids = fetch_unseen_transaction_emails(mail)
            print(f"[{now_str}] Found {len(email_ids)} new email(s).")  # Always log found count

            for e_id in email_ids:
                res, data = mail.fetch(e_id, "(RFC822)")
                if res != "OK":
                    print(f"Failed to fetch email id {e_id}")
                    continue
                msg = email.message_from_bytes(data[0][1])
                subject, encoding = decode_header(msg["Subject"])[0]
                if isinstance(subject, bytes):
                    subject = subject.decode(encoding or "utf-8", errors="ignore")
                print(f"Processing email with subject: {subject}")
                if subject_trigger.lower() in subject.lower():
                    body = get_email_body(msg)
                    # TODO: Consider more robust email parsing for different banks/formats
                    print("----- EMAIL BODY START -----")
                    print(body)
                    print("----- EMAIL BODY END -----")
                    txn = parse_email_transaction(body)
                    if txn:
                        print(f"Parsed transaction: {txn}")
                        insert_transaction(txn, config)
                    else:
                        print("No transaction found in email. TODO: Improve parser.")
                else:
                    print("Skipped email (subject does not match trigger phrase).")
                # Mark email as seen so it's not processed again
                mail.store(e_id, '+FLAGS', '\\Seen')
            mail.logout()
        except Exception as e:
            # TODO: Add more robust error handling and possibly alerting
            print(f"Error: {e}")

        # Wait before polling again
        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
