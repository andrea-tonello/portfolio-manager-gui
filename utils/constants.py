import os

# The release workflow replaces it with the version being released. "dev" marks a copy
# run from the source code, which never offers to update (see update_service).
APP_VERSION = "dev"
GITHUB_URL = "https://github.com/andrea-tonello/portfolio-manager-gui"

DATE_FORMAT = "%d-%m-%Y"
# Each account's files in the user's resources folder: its journal, journal-<account>.json (the
# operations as entered), and its ledger, report-<account>.csv (rebuilt from the journal).
JOURNAL_PREFIX = "journal-"
LEDGER_PREFIX = "report-"
# A copy of an account's ledger as it was before the journal: before-journal-<account>.csv.
BEFORE_JOURNAL_PREFIX = "before-journal-"
# The CSVs the user exports from Transactions: "Report <account>.csv" and "Report All Accounts.csv".
# Ledgers were saved under this name too, before the journal.
REPORT_PREFIX = "Report "
# Language code -> name shown in the language pickers, in display order.
LANGUAGES = {"en": "English", "it": "Italiano"}
DEFAULT_LANG = "en"
# Translations: <language>.json holds the UI strings, <name>_<language>.txt the longer help texts.
I18N_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "i18n")

# Currencies a stock or ETF can be traded in, as stored in the CSV's `curr` column.
CURRENCIES = ("EUR", "USD")

# Transactions screen filter: mode -> default N. "count" lists the last N
# operations, "days" the operations of the last N days.
DEFAULT_TX_FILTER = {"count": 5, "days": 90}
