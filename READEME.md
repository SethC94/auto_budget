# Budget Email Ingest

This project automates inserting bank transaction emails into a shared Google Sheet for live family budgeting.

## Features

- Polls a dedicated Gmail inbox for forwarded bank transaction emails
- Parses each email and inserts the transaction into your Google Sheet
- Sheet “learns” your spending with monthly category averages
- Archives each month's final budget as a snapshot
- Designed to run on Mac or Raspberry Pi with no user interaction

## Setup

### 1. Clone & Install Requirements

```bash
git clone <your_repo_url>
cd budget_email_ingest
pip install -r requirements.txt
```

### 2. Configure

- Copy `config.json.example` to `config.json` and edit for your setup:
  - Gmail login (app password recommended)
  - Google Sheets service account JSON path
  - Sheet and tab names

### 3. Gmail

- Create a new Gmail account (e.g., `yourbudgetnotifier@gmail.com`)
- Forward your transaction notifications to this email.

### 4. Google Sheets

- Share your Google Sheet with the service account email (from your service account JSON file).

### 5. Run

#### Poll Gmail and insert transactions:
```bash
python email_ingest.py
```

#### Update the budget sheet (typically run monthly):
```bash
python modify_budget_sheet.py
```

#### Test transaction parsing:
```bash
python transaction_parser.py test/sample_email_01.txt
```

## Architecture

- `email_ingest.py`: Polls Gmail, parses new transaction emails, inserts into sheet.
- `modify_budget_sheet.py`: Analyzes transactions, updates planned values, archives last month, wipes transactions.
- `insert_transaction.py`: Inserts a transaction into the sheet.
- `transaction_parser.py`: Parses email content into transaction dict.

## TODO

- Add more robust bank email parsing
- Add deduplication of emails/transactions
- Add cron job/Raspberry Pi setup guide

---

**Security:**  
Never check your `config.json` or service account JSON into public repos.  
Flush any PII from logs and code.

---

## License

MIT
