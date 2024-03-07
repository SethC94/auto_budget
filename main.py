# Importing required library
import pygsheets
import gspread
import datetime

# Create time/date
today = datetime.date.today()
# Create the Client
client = pygsheets.authorize(service_account_file='/Users/sethcreasman/src/gcp_tmp_keys/auto-budget-415622-10a45fd113c6.json')

# Open the doc and sheet for udpates
spreadsht = client.open('auto_budget_sheet')
worksht_transactions = spreadsht.worksheet('title', 'Transactions')
worksht_summary = spreadsht.worksheet('title', 'Summary')


# List of expense_categories
expense_categories_list = worksht_summary.get_values('B28', 'B49')
#print(*expense_categories_list[1], sep = '')


def update_cells(expense_value, expense_comment, expense_category):
    # #single cell value update for date amount and comment columns
    update_date = worksht_transactions.cell('B5').set_text_format('bold', True).value = today.strftime('%d, %b %Y')
    update_value = worksht_transactions.cell('C5').set_text_format('bold', True).value = expense_value
    update_comment = worksht_transactions.cell('D5').set_text_format('bold', True).value = expense_comment
    update_category = worksht_transactions.cell('E5').set_text_format('bold', True).value = expense_category
    print('added to cells')

def append_and_drop_row():
    worksht_transactions.insert_rows(4,number=1)
    print('Added new line to expenses')

#def trigger_insert():

## TODO: Create function that calls the others and get expense category arg pulling from list 


update_cells('100000','Used an arg this time', 'House Payment')
append_and_drop_row()
