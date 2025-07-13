import re

def parse_email_transaction(body):
    """
    Parse a USAA debit alert email body and extract transaction details.
    I need to handle more formats and edge cases if USAA changes their email.
    TODO: Add HTML parsing if emails come as HTML only.
    """
    lines = [line.strip() for line in body.replace('\r\n', '\n').replace('\r', '\n').split('\n') if line.strip()]

    amount = None
    amount_pattern_1 = re.compile(r'\$([0-9,]+\.\d{2}) came out of your account')
    amount_pattern_2 = re.compile(r'for \$([0-9,]+\.\d{2})')
    for line in lines:
        match = amount_pattern_1.search(line)
        if match:
            amount = match.group(1)
            break
        match = amount_pattern_2.search(line)
        if match:
            amount = match.group(1)
            break

    merchant = None
    for i, line in enumerate(lines):
        if "*To:*" in line or "To:" in line:
            if line.strip() in ("*To:*", "To:"):
                for j in range(i+1, len(lines)):
                    next_line = lines[j].strip()
                    if next_line:
                        merchant = next_line
                        break
                break
            else:
                merchant = line.split(":", 1)[-1].strip("*").strip()
                break
    if not merchant:
        for line in lines:
            if line.lower().startswith("merchant:"):
                merchant = line.split(":", 1)[-1].strip()
                break

    date = None
    for i, line in enumerate(lines):
        if "*Date:*" in line or "Date:" in line:
            if line.strip() in ("*Date:*", "Date:"):
                for j in range(i+1, len(lines)):
                    next_line = lines[j].strip()
                    if next_line:
                        date = next_line
                        break
                break
            else:
                date = line.split(":", 1)[-1].strip("*").strip()
                break

    if not amount or not merchant or not date:
        return None

    return {
        "amount": amount,
        "desc": merchant,
        "date": date
    }
