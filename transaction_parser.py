import re

def parse_email_transaction(body):
    """
    Parse a USAA debit alert email body and extract transaction details.
    Designed to work with forwarded alert emails.
    TODO: Handle more email formats and edge cases as needed.
    """

    # Normalize newlines and strip leading/trailing whitespace
    lines = [line.strip() for line in body.replace('\r\n', '\n').replace('\r', '\n').split('\n')]

    # 1. Find amount by searching for the line ending with 'came out of your account ending in ...'
    amount = None
    for i, line in enumerate(lines):
        if "came out of your account ending in" in line:
            amount_match = re.search(r'\$([0-9,]+\.\d{2})', line)
            if amount_match:
                amount = amount_match.group(1)
                break  # Stop after first match

    # 2. Find merchant after '*To:*'
    merchant = None
    for i, line in enumerate(lines):
        if line == "*To:*":
            # Look for the next non-empty line
            for j in range(i+1, len(lines)):
                next_line = lines[j].strip()
                if next_line:
                    merchant = next_line
                    break
            break  # Stop after first match

    # 3. Find date after '*Date:*'
    date = None
    for i, line in enumerate(lines):
        if line == "*Date:*":
            for j in range(i+1, len(lines)):
                next_line = lines[j].strip()
                if next_line:
                    date = next_line
                    break
            break  # Stop after first match

    # TODO: Add more robust logging or error handling as needed
    if not amount or not merchant or not date:
        # print(f"Debug: amount={amount}, merchant={merchant}, date={date}")
        return None

    # Return with standard keys expected by the rest of the pipeline
    return {
        "amount": amount,
        "desc": merchant,  # Use 'desc' instead of 'merchant' for compatibility
        "date": date
        # TODO: Add any additional fields (e.g., account number) if desired
    }
