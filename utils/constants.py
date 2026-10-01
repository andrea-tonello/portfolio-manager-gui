import os

APP_VERSION = "0.1.0"
GITHUB_URL = "https://github.com/andrea-tonello/portfolio-manager-gui"

DATE_FORMAT = "%d-%m-%Y"
REPORT_PREFIX = "Report "
LANG = {1: ("en", "English"), 2: ("it", "Italiano")}
# Translations: <language>.json holds the UI strings, <name>_<language>.txt the longer help texts.
I18N_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "i18n")

CURRENCY_EUR = 1
CURRENCY_USD = 2
CURRENCY_CHOICES = {CURRENCY_EUR: "EUR", CURRENCY_USD: "USD"}

ETF_PRODUCTS = {"ETF-S", "ETF-M", "ETF-B"}
