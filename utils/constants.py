import os

def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")

DATE_FORMAT = "%d-%m-%Y"
REPORT_PREFIX = "Report "
LANG = {1: ("en", "English"), 2: ("it", "Italiano")}

# Currency
CURRENCY_EUR = 1
CURRENCY_USD = 2
CURRENCY_CHOICES = {CURRENCY_EUR: "EUR", CURRENCY_USD: "USD"}
