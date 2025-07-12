import json
import os
import pygsheets
import difflib
from insert_transaction import insert_transaction

CONFIG_PATH = "config.json"
BACKFILL_FILE = "back_fill.txt"

def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)

def get_allowed_categories(config):
    """I need to fetch allowed categories from the Summary tab, B28:B71."""
    gc = pygsheets.authorize(service_account_file=config["google_service_account_json"])
    sh = gc.open(config["sheet_name"])
    summary_wks = sh.worksheet('title', config["summary_tab"])
    cats = summary_wks.get_values('B28', 'B71')
    return [c[0].strip() for c in cats if c and c[0].strip()]

def normalize_category(cat):
    """I need to normalize category names so I can compare them without worrying about case, punctuation, or common substitutions."""
    if not cat:
        return ""
    cat = cat.lower()
    cat = cat.replace("&", "and")
    cat = cat.replace("’", "'")
    cat = cat.replace("‘", "'")
    cat = cat.replace("-", " ")
    cat = cat.replace("_", " ")
    cat = cat.replace(".", "")
    cat = cat.replace(",", "")
    cat = cat.replace("/", " ")
    cat = cat.replace("\\", " ")
    cat = cat.replace("$", "")
    cat = cat.replace("  ", " ")
    cat = cat.strip()
    return cat

def best_category_match(raw_cat, allowed_categories):
    """
    I need to match the raw category from the backfill file to the closest allowed category.
    Always return an allowed category, even if not an exact match.
    """
    norm_raw = normalize_category(raw_cat)
    norm_allowed = [normalize_category(a) for a in allowed_categories]
    # First, try exact normalized match
    for i, norm_a in enumerate(norm_allowed):
        if norm_raw == norm_a:
            return allowed_categories[i]
    # Try best fuzzy match (difflib returns closest matches)
    matches = difflib.get_close_matches(norm_raw, norm_allowed, n=1, cutoff=0.7)
    if matches:
        idx = norm_allowed.index(matches[0])
        return allowed_categories[idx]
    # As a last resort, return the first allowed category (should never hit this)
    # TODO: Log this if it ever happens, that means something is very wrong
    return allowed_categories[0] if allowed_categories else "Uncategorized"

def parse_backfill_line(line):
    """
    I need to parse a line in the format:
    Jul 10, 2025<TAB>SAFEWAY #2600 TRACY CA, Groceries<TAB>-$70.44

    I need to return the amount always as positive, e.g. $70.44, never -$70.44.
    """
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    fields = line.split('\t')
    if len(fields) != 3:
        print(f"Skipped line (malformed): {line}")
        return None

    date_str = fields[0].strip()
    desc_cat = fields[1].strip()
    amount = fields[2].strip()

    # Split desc_cat on last comma to get desc and category
    if ',' in desc_cat:
        desc, category = desc_cat.rsplit(',', 1)
        desc = desc.strip()
        category = category.strip()
    else:
        desc = desc_cat.strip()
        category = ""

    # Clean up amount: always remove negative sign, ensure $ is present
    amount = amount.replace(" ", "")
    if amount.startswith('-$'):
        amount = amount[1:]  # Remove the negative sign, keep the $
    elif not amount.startswith('$'):
        amount = "$" + amount.lstrip("-")  # Remove any leading "-" and add $
    # TODO: If I ever get wonky amount formats, I need to check here

    txn = {
        "date": date_str,
        "amount": amount,
        "desc": desc,
        "category": category
    }
    return txn

def main():
    config = load_config()
    allowed_categories = get_allowed_categories(config)
    if not os.path.exists(BACKFILL_FILE):
        print(f"[!] {BACKFILL_FILE} not found. Please add it and try again.")
        return

    with open(BACKFILL_FILE, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f, 1):
            txn = parse_backfill_line(line)
            if txn:
                # Always match to the closest allowed category
                txn['category'] = best_category_match(txn['category'], allowed_categories)
                print(f"Processing line {idx}: {txn}")
                try:
                    insert_transaction(txn, config)
                except Exception as e:
                    print(f"Error inserting transaction on line {idx}: {e}")
                    # TODO: Add retry logic or log to file if needed
            else:
                print(f"Skipped invalid or empty line {idx}")

    print("Backfill complete. All valid transactions have been added.")
    # TODO: If I want duplicate-checking, I need to add that logic here.

if __name__ == "__main__":
    main()
