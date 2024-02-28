# Importing required library
import pygsheets
import datetime

# Create time/date
today = datetime.date.today()
# Create the Client
client = pygsheets.authorize(service_account_file="/Users/sethcreasman/src/gcp/auto_budget/auto-budget-415622-767a226dbf8f.json")

# Open the doc and sheet for udpates
spreadsht = client.open("auto_budget_sheet")
worksht = spreadsht.worksheet("title", "Transactions")


# #single cell value update for date amount and comment columns
update_date = worksht.cell("B6").set_text_format("bold", False).value = today.strftime('%d, %b %Y')
update_value = worksht.cell("C6").set_text_format("bold", False).value = "2650"
update_comment = worksht.cell("D6").set_text_format("bold", False).value = "I updated this with Python"
update_category = worksht.cell("E6").set_text_format("bold", False).value = "House Payment"
