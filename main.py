# Importing required library
import pygsheets
import gspread
import datetime

# Create time/date
today = datetime.date.today()
# Create the Client
client = pygsheets.authorize(service_account_file="/Users/sethcreasman/src/gcp/sa_secrets/auto-budget-415622-670aa95d3ac5.json")

# Open the doc and sheet for udpates
spreadsht = client.open("auto_budget_sheet")
worksht = spreadsht.worksheet("title", "Transactions")

# Test Cell Values
## TODO: turn this into function args populated from text message etl
expense_value = "5"
expense_comment = "I updated this with python"
expense_category = "House Payment"
clear_cell_value = ""

def update_cells():
    # #single cell value update for date amount and comment columns
    update_date = worksht.cell("B5").set_text_format("bold", True).value = today.strftime('%d, %b %Y')
    update_value = worksht.cell("C5").set_text_format("bold", True).value = expense_value
    update_comment = worksht.cell("D5").set_text_format("bold", True).value = expense_comment
    update_category = worksht.cell("E5").set_text_format("bold", True).value = expense_category
    print("added to cells")

def append_and_drop_row():
    worksht.insert_rows(4,number=1)

update_cells()
append_and_drop_row()
