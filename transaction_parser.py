import re

def parse_email_transaction(body):
    """
    Parse a USAA debit alert email body and extract transaction details.
    Designed to work with forwarded alert emails, but I need to handle more formats and edge cases.
    TODO: If USAA changes email wording, I need to update these patterns.
    """

    # Normalize newlines and strip leading/trailing whitespace
    lines = [line.strip() for line in body.replace('\r\n', '\n').replace('\r', '\n').split('\n') if line.strip()]
    # TODO: If emails come in as HTML only, I need to add HTML parsing.

    # Try to find the amount using different patterns
    amount = None
    # Common USAA: "A debit card transaction for $12.34 came out of your account ending in 1234."
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
    # TODO: If there are other phrasings, I need to add more patterns here.

    # Try to find the merchant
    merchant = None
    # USAA often: "*To:*" followed by merchant name
    for i, line in enumerate(lines):
        if "*To:*" in line or "To:" in line:
            # Look for the next non-empty line if "*To:*" is by itself
            if line.strip() in ("*To:*", "To:"):
                for j in range(i+1, len(lines)):
                    next_line = lines[j].strip()
                    if next_line:
                        merchant = next_line
                        break
                break
            else:
                # "*To:* Merchant Name" on the same line
                merchant = line.split(":", 1)[-1].strip("*").strip()
                break
    # If not found, look for "Merchant:" or similar
    if not merchant:
        for line in lines:
            if line.lower().startswith("merchant:"):
                merchant = line.split(":", 1)[-1].strip()
                break

    # Try to find the date
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
                # "*Date:* 07/10/2025" on same line
                date = line.split(":", 1)[-1].strip("*").strip()
                break

    # TODO: If parsing fails, I need to log the body for future pattern updates.
    if not amount or not merchant or not date:
        # print(f"Debug: lines={lines}")
        # print(f"Debug: amount={amount}, merchant={merchant}, date={date}")
        return None

    # Return with standard keys expected by the rest of the pipeline
    return {
        "amount": amount,
        "desc": merchant,  # Use 'desc' instead of 'merchant' for compatibility
        "date": date
        # TODO: Add any additional fields (e.g., account number) if desired
    }
