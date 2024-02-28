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

# Cell Values
# expense_value =
# expense_comment =
# expense_category =

def update_cells():
    # #single cell value update for date amount and comment columns
    update_date = worksht.cell("B5").set_text_format("bold", False).value = today.strftime('%d, %b %Y')
    update_value = worksht.cell("C5").set_text_format("bold", False).value = "5"
    update_comment = worksht.cell("D5").set_text_format("bold", False).value = "I updated this with Python"
    update_category = worksht.cell("E5").set_text_format("bold", False).value = "House Payment"

    print("added to cells")

def clear_cell_updates():
    list_of_cells = ["B5","C5","D5","E5"]
    for a_cell in list_of_cells:
    # Add ability to clear cells after inserting
        clear_cell_updates = worksht.cell(a_cell).value = ""
    print("cleared cells")

# TODO:
# Add values to row and move entire row down
#update_expense_row = worksht.append_table(values=['B5','C5','D5','E5'], start='B6', end=None, dimension='ROWS', overwrite=True, **kwargs)

update_cells()
clear_cell_updates()
