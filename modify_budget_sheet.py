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
    print(f"Archived current sheet as {archive_title}")

def clear_transactions_tab(config):
    gc = pygsheets.authorize(service_account_file=config["google_service_account_json"])
    sh = gc.open(config["sheet_name"])
    wks = sh.worksheet('title', config["transactions_tab"])
    # TODO: Adjust range if my sheet has more/less columns
    wks.clear(start="B5", end="E1000")  # Wipe B5:E1000
    print("Cleared Transactions tab for new month.")

def update_budget_logic(config):
    """
    I need to set each Summary category's planned value based on a rolling YTD average.
    That means:
    - For each category, sum up all of this year's transaction amounts for that category.
    - Divide by the number of months in my YTD data.
    - Update the Planned column for that category with the new average.
    """
    gc = pygsheets.authorize(service_account_file=config["google_service_account_json"])
    sh = gc.open(config["sheet_name"])
    summary_wks = sh.worksheet('title', config["summary_tab"])
    transactions_wks = sh.worksheet('title', config["transactions_tab"])

    # Get all categories from summary (B28:B71)
    categories = summary_wks.get_values('B28', 'B71')
    categories = [c[0].strip() for c in categories if c and c[0].strip()]

    # The planned values are now in D28:D71 (column D)
    planned_rows = list(range(28, 28 + len(categories)))  # rows in the sheet

    # Get all transactions YTD (assuming B5:E1000; adjust if I keep YTD elsewhere)
    txn_values = transactions_wks.get_values('B5', 'E1000')
    # TODO: If I want to use a different sheet/range for YTD, change above

    # Build category totals
    category_totals = {cat: 0.0 for cat in categories}
    category_counts = {cat: 0 for cat in categories}

    # Figure out how many months are represented in the data
    months_set = set()
    for row in txn_values:
        if len(row) < 4:
            continue
        date, amount, desc, cat = row
        try:
            # Parse month from date (assume format like 7/10/2025 or Jul 10, 2025)
            if "/" in date:
                month = int(date.split("/")[0])
            elif "," in date:
                month_str = date.split(",")[0]
                if " " in month_str:
                    # "Jul 10"
                    month = datetime.datetime.strptime(month_str.split(" ")[0], "%b").month
                else:
                    month = 1  # fallback
            else:
                month = 1  # fallback
            months_set.add(month)
        except Exception:
            # TODO: If I get a weird date, log it
            continue
        try:
            amt = float(amount.replace("$", "").replace(",", ""))
            if cat in category_totals:
                category_totals[cat] += amt
                category_counts[cat] += 1
        except Exception:
            # TODO: Log/skip transactions with bad amount values
            continue

    num_months = len(months_set) if months_set else 1  # avoid divide by zero

    # Update planned values with rolling average in column D
    for idx, cat in enumerate(categories):
        total = category_totals[cat]
        avg = total / num_months if num_months else 0
        # TODO: Maybe round to 2 decimal places
        planned_cell = f"D{planned_rows[idx]}"
        summary_wks.update_value(planned_cell, f"${avg:.2f}")

    print("Updated planned values for all categories based on YTD rolling average.")

def main():
    config = load_config()
    archive_current_sheet(config)
    update_budget_logic(config)
    clear_transactions_tab(config)
    print("Monthly budget sheet updated.")

if __name__ == "__main__":
    main()
