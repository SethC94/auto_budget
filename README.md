# Budget App

## Overview

This app automates your transaction tracking and budget management with Google Sheets, Gmail, and remote monitoring. It is designed to run as a resilient service on your Windows machine, with a single `main.py` entry point that manages everything: email ingestion, sheet updates, a log server, ngrok tunnel, self-updating, and remote restart.

---

## Features

- **Automated Transaction Ingestion:**  
  Pulls transaction alert emails from Gmail and logs them to your Google Sheet budget.
- **Self-Updating:**  
  Automatically checks for updates to `main.py` in your repo and upgrades itself—if an update fails, it reverts and keeps running!
- **Resilience:**  
  A watcher ensures the app recovers from crashes and always stays live.
- **Live Log Server:**  
  View live logs from anywhere via your ngrok URL, with password protection.
- **Remote Restart:**  
  Touch a `restart.flag` file in the app folder to trigger a full app restart.

---

## Setup

### 1. **Clone the repo and install dependencies**

```sh
git clone https://github.com/SethC94/auto_budget.git
cd auto_budget
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 2. **Configure your app**

- Place your `config.json` and your Google service account JSON in the app folder (see samples).
- Edit `config.json` with your Gmail/app password, Google Sheet info, etc.

### 3. **Set up Gmail for IMAP and App Passwords**

- Enable IMAP in Gmail settings.
- Generate an [App Password](https://myaccount.google.com/apppasswords) for your Gmail account and use it in `config.json`.

### 4. **ngrok Setup (for remote logs)**

- [Download ngrok](https://ngrok.com/download) and sign up for a free account.
- Reserve a custom domain (e.g., `mackerel-live-roughly.ngrok-free.app`) in your ngrok dashboard.
- Install ngrok and add it to your PATH.

---

## Running the App

### **Start Everything at Once**

```sh
python main.py
```

- This starts:
  - Email ingest, log server, ngrok tunnel, self-updating, and all monitoring threads.
- The Flask log server is always running on port 5000.
- ngrok automatically exposes it at your reserved URL.

### **Remote Log Viewing**

Visit from your phone or anywhere:

```
https://mackerel-live-roughly.ngrok-free.app/logs
```
- Enter the username/password in `log_server.py` (change these for security!).

### **Remote Restart**

- To restart the app remotely, create a file named `restart.flag` in the app directory. The app will detect it and restart itself, logging the reason.

---

## How Self-Updating Works

- Every 30 minutes the app checks if `main.py` has changed in the repo.
- If so, it does a `git pull` and restarts itself.
- If the update fails (crash on startup), it reverts to the last known-good commit and restarts.
- All update/revert steps are logged and emailed.

---

## How to Monitor Health

- Logs go to `budget_app_logs.txt` (live) and `app_incidents.log` (warnings/errors).
- Heartbeat log entries and periodic status emails confirm the app is alive.
- You can view logs remotely at `/logs` on your ngrok domain.

---

## Security Notes

- Change all default passwords immediately!
- Do not share your service account or email credentials.
- For maximum safety, use a private repo and restrict access to your ngrok domain.

---

## Troubleshooting & Recovery

- If the app crashes, it will try to restart and revert automatically.
- If you need to roll back manually, `git reset --hard <commit>` and restart.
- All incidents (crashes, update failures) are logged and emailed.

---

## TODO

- [ ] Add more robust parsing for other email formats.
- [ ] Consider a more secure remote control mechanism.
- [ ] Switch to OAuth for Gmail if app passwords are deprecated.

---

Enjoy your super-cool, always-on, self-updating budget app!
