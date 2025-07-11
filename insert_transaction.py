import pygsheets
import json

# TODO: Add more robust category logic if needed

def get_allowed_categories(wks):
    cats = wks.get_values('B28', 'B79')
    return [c[0] for c in cats if c and c[0].strip()]

def classify_category(desc, allowed_categories):
    # TODO: Smarter mapping as needed
    desc_low = desc.lower()
    rules = [
        (r'safeway|save mart|grocery|foodmaxx|winco|whalers|grocery outlet|costco', 'Groceries'),
        (r'mcdonald|wendy|taco bell|in-n-out|sonic|popeyes|little caesars|chick[- ]fil[- ]a|arby|jack in the box|burger', 'Fast Food'),
        (r'amazon', 'Shopping'),
        (r'target|wal[- ]?mart|ross|macys|abc stores|dollar tree', 'Shopping'),
        (r'starbucks|dunkin', 'Coffee Shops'),
        (r'chevron|arco|shell|gas|fuel|7-eleven', 'Gas'),
        (r'cinemark|movies|theatre', 'Movies & DVDs'),
        # TODO: Add more as needed!
    ]
    import re
    for regex, mapped in rules:
        if re.search(regex, desc_low):
            if mapped in allowed_categories:
                return mapped
    if "Uncategorized" in allowed_categories:
        return "Uncategorized"
    if "Shopping" in allowed_categories:
        return "Shopping"
    return allowed_categories[0] if allowed_categories else ""

def insert_transaction(txn, config):
    """
    Insert a transaction at row 5 in Transactions tab.
    """
    gc = pygsheets.authorize(service_account_file=config["google_service_account_json"])
    sh = gc.open(config["sheet_name"])
    wks = sh.worksheet('title', config["transactions_tab"])
    summary_wks = sh.worksheet('title', config["summary_tab"])
    allowed_categories = get_allowed_categories(summary_wks)
    txn['category'] = classify_category(txn['desc'], allowed_categories)

    # Insert new row at 5 (index 4)
    wks.insert_rows(4, number=1, values=None)
    row = 5
    wks.update_value((row, 2), txn['date'])       # B = Date
    wks.update_value((row, 3), txn['amount'])     # C = Amount
    wks.update_value((row, 4), txn['desc'])       # D = Description
    wks.update_value((row, 5), txn['category'])   # E = Category

    print(f"Inserted transaction at row {row}: {txn}")
