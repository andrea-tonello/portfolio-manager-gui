import os

APP_VERSION = "0.1.0"
GITHUB_URL = "https://github.com/andrea-tonello/portfolio-manager-gui"

DATE_FORMAT = "%d-%m-%Y"
REPORT_PREFIX = "Report "
# Language code -> name shown in the language pickers, in display order.
LANGUAGES = {"en": "English", "it": "Italiano"}
DEFAULT_LANG = "en"
# Translations: <language>.json holds the UI strings, <name>_<language>.txt the longer help texts.
I18N_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "i18n")

# Currencies a stock or ETF can be traded in, as stored in the CSV's `curr` column.
CURRENCIES = ("EUR", "USD")

ETF_PRODUCTS = {"ETF-S", "ETF-M", "ETF-B"}
