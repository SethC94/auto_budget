import pygsheets
import json
import datetime

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
    # TODO: Confirm this doesn't overwrite an existing archive; check for duplicates
    sh.copy(title=archive_title)
    import logging
    logging.getLogger("BudgetApp").info(f"Archived current sheet as {archive_title}")

def clear_transactions_tab(config):
    gc = pygsheets.authorize(service_account_file=config["google_service_account_json"])
    sh = gc.open(config["sheet_name"])
    wks = sh.worksheet('title', config["transactions_tab"])
    wks.clear(start="B5", end="E1000")
    import logging
    logging.getLogger("BudgetApp").info("Cleared Transactions tab for new month.")

def update_budget_logic(config):
    gc = pygsheets.authorize(service_account_file=config["google_service_account_json"])
    sh = gc.open(config["sheet_name"])
    summary_wks = sh.worksheet('title', config["summary_tab"])
    transactions_wks = sh.worksheet('title', config["transactions_tab"])

    categories = summary_wks.get_values('B28', 'B71')
    categories = [c[0].strip() for c in categories if c and c[0].strip()]
    planned_rows = list(range(28, 28 + len(categories)))
    txn_values = transactions_wks.get_values('B5', 'E1000')

    category_totals = {cat: 0.0 for cat in categories}
    category_counts = {cat: 0 for cat in categories}
    months_set = set()
    for row in txn_values:
        if len(row) < 4:
            continue
        date, amount, desc, cat = row
        try:
            if "/" in date:
                month = int(date.split("/")[0])
            elif "," in date:
                month_str = date.split(",")[0]
                if " " in month_str:
                    month = datetime.datetime.strptime(month_str.split(" ")[0], "%b").month
                else:
                    month = 1
            else:
                month = 1
            months_set.add(month)
        except Exception:
            continue
        try:
            amt = float(amount.replace("$", "").replace(",", ""))
            if cat in category_totals:
                category_totals[cat] += amt
                category_counts[cat] += 1
        except Exception:
            continue

    num_months = len(months_set) if months_set else 1
    for idx, cat in enumerate(categories):
        total = category_totals[cat]
        avg = total / num_months if num_months else 0
        planned_cell = f"D{planned_rows[idx]}"
        summary_wks.update_value(planned_cell, f"${avg:.2f}")

    import logging
    logging.getLogger("BudgetApp").info("Updated planned values for all categories based on YTD rolling average.")

def main():
    config = load_config()
    archive_current_sheet(config)
    update_budget_logic(config)
    clear_transactions_tab(config)
    import logging
    logging.getLogger("BudgetApp").info("Monthly budget sheet updated.")

if __name__ == "__main__":
    main()
