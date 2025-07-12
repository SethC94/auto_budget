import pygsheets
import json
import argparse
import os

CONFIG_PATH = "config.json"
BACKUP_FILE = "planned_backup.json"

def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)

def get_sheet_handles(config):
    gc = pygsheets.authorize(service_account_file=config["google_service_account_json"])
    sh = gc.open(config["sheet_name"])
    summary_wks = sh.worksheet('title', config["summary_tab"])
    return summary_wks

def get_category_rows():
    """I need to get the row numbers for B28:B78 and D28:D78."""
    # pygsheets is 1-indexed, so row 28 to 78 inclusive
    return list(range(28, 79))

def get_planned_values(summary_wks, cat_rows):
    """I need to get all planned values and their categories."""
    planned = []
    cats = summary_wks.get_values(f'B{cat_rows[0]}', f'B{cat_rows[-1]}')
    vals = summary_wks.get_values(f'D{cat_rows[0]}', f'D{cat_rows[-1]}')
    for i, row in enumerate(cat_rows):
        cat = cats[i][0].strip() if cats[i] else ""
        val_str = vals[i][0].replace("$", "").replace(",", "").strip() if vals[i] else "0"
        try:
            val = float(val_str)
        except Exception:
            val = 0.0
        planned.append({"row": row, "category": cat, "planned": val})
    return planned

def set_planned_values(summary_wks, planned_list):
    """I need to update planned values in the sheet given a list of dicts with row and planned."""
    for item in planned_list:
        row = item["row"]
        val = item["planned"]
        cell = f"D{row}"
        summary_wks.update_value(cell, f"${val:.2f}")

def get_total_paycheck(summary_wks):
    """I need to grab the paycheck value from cell J30."""
    val_str = summary_wks.get_value("J30").replace("$", "").replace(",", "").strip()
    try:
        return float(val_str)
    except Exception:
        return 0.0

def save_backup(planned_list):
    """I need to save a backup of the original planned values so I can revert."""
    with open(BACKUP_FILE, "w", encoding="utf-8") as f:
        json.dump(planned_list, f)

def load_backup():
    if not os.path.exists(BACKUP_FILE):
        return None
    with open(BACKUP_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def scale_planned_to_income(planned_list, target_sum):
    """I need to scale all planned values so their sum is target_sum, keeping category weights the same."""
    original_sum = sum(item["planned"] for item in planned_list)
    if original_sum == 0:
        return planned_list  # avoid divide by zero
    scale = target_sum / original_sum
    # TODO: If any categories should never be changed, add an exclude list here
    for item in planned_list:
        item["planned"] = round(item["planned"] * scale, 2)
    # Adjust last category so the total is exact (to fix rounding drift)
    diff = target_sum - sum(item["planned"] for item in planned_list)
    if planned_list:
        planned_list[-1]["planned"] += round(diff, 2)
    return planned_list

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--revert", action="store_true", help="Revert planned values to backup")
    args = parser.parse_args()

    config = load_config()
    summary_wks = get_sheet_handles(config)
    cat_rows = get_category_rows()

    if args.revert:
        backup = load_backup()
        if not backup:
            print("No backup found. Cannot revert.")
            return
        set_planned_values(summary_wks, backup)
        print("Planned values reverted from backup.")
        # TODO: If I want to delete the backup after reverting, uncomment below
        # os.remove(BACKUP_FILE)
        return

    planned = get_planned_values(summary_wks, cat_rows)
    save_backup(planned)
    print("Saved backup of planned values to planned_backup.json.")

    income = get_total_paycheck(summary_wks)
    if income == 0:
        print("Paycheck value in J30 is zero or invalid. Aborting.")
        return
    target = round(income * 0.95, 2)
    print(f"Scaling all planned categories so their sum is 80% of monthly income: ${target:.2f}")

    scaled = scale_planned_to_income(planned, target)
    set_planned_values(summary_wks, scaled)
    print("Planned values updated in sheet.")

if __name__ == "__main__":
    main()
