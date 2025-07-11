import pygsheets
import json
import datetime
import shutil

CONFIG_PATH = "config.json"

def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)

def archive_current_sheet(config):
    gc = pygsheets.authorize(service_account_file=config["google_service_account_json"])
    sh = gc.open(config["sheet_name"])
    now = datetime.datetime.now()
    month_name = now.strftime("%Y%m")
    archive_title = f"auto_budget_{month_name}"
    # TODO: Confirm this doesn't overwrite an existing archive
    sh.copy(title=archive_title)
    print(f"Archived current sheet as {archive_title}")

def clear_transactions_tab(config):
    gc = pygsheets.authorize(service_account_file=config["google_service_account_json"])
    sh = gc.open(config["sheet_name"])
    wks = sh.worksheet('title', config["transactions_tab"])
    # TODO: Adjust range if your sheet has more/less columns
    wks.clear(start="B5", end="E1000")  # Wipe B5:E1000
    print("Cleared Transactions tab for new month.")

def update_budget_logic(config):
    # TODO: Implement logic to learn from past month's transactions and update planned values.
    # For now, print a placeholder.
    print("TODO: Implement budget 'learning' logic here.")

def main():
    config = load_config()
    archive_current_sheet(config)
    update_budget_logic(config)
    clear_transactions_tab(config)
    print("Monthly budget sheet updated.")

if __name__ == "__main__":
    main()
