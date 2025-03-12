import requests
from secret import API_TOKEN
BASE_URL = "https://financialmodelingprep.com/stable"
BASE_URL_OLD = "https://financialmodelingprep.com/api/v3"
SYMBOL = "AAPL"


# Company base profile
def company_profile(symbol=SYMBOL):
    url = f'{BASE_URL}/profile?symbol={symbol}&apikey={API_TOKEN}'
    return requests.get(url).json()


# Batch company base profile
def batch_company_profile(symbols: list):
    url = f'{BASE_URL_OLD}/quote/{symbols}?apikey={API_TOKEN}'
    return requests.get(url).json()


# Financial ratings (snapshot)
def ratings_snap(symbol=SYMBOL):
    url = f'{BASE_URL}/ratings-snapshot?symbol={symbol}&apikey={API_TOKEN}'
    return requests.get(url).json()


# Financial ratings (historical)
def ratings_hist(symbol=SYMBOL):
    url = f'{BASE_URL}/ratings-historical?symbol={symbol}&apikey={API_TOKEN}'
    return requests.get(url).json()


# IPOs calendar
def ipos():
    url = f'{BASE_URL}/ipos-calendar?apikey={API_TOKEN}'
    return requests.get(url).json()