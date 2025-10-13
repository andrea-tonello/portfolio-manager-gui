import requests
import re
import yfinance as yf
from datetime import date, datetime, timedelta
from secret import OXCR_KEY


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
}

def fetch_name(ticker):
    try:
        t = yf.Ticker(ticker)
        name = t.info.get("longName")
        if not name:
            raise KeyError("longName not found")
        return name
    except (KeyError, AttributeError, ValueError) as e:
        print(f"Errore nel recupero del nome: {e}")
        return input("Servizio non raggiungibile. Inserire nome asset manualmente: ")



def fetch_exchange_rate(currency, ref_date=None):
    """
    Gather EOD exchange rate.
    """
    if datetime.strptime(ref_date, "%Y-%m-%d").date() == date.today():
        url = f"https://openexchangerates.org/api/latest.json?app_id={OXCR_KEY}"
    else:
        url = f"https://openexchangerates.org/api/historical/{ref_date}.json?app_id={OXCR_KEY}"

    response = requests.get(url)
    data = response.json()
    eur_rate = data["rates"][currency]    

    return eur_rate





def fetch_isin(ticker):
    pass







def name_by_ticker(ticker):
    try:
        t = yf.Ticker(ticker)
        return t.info["longName"]
    except:
        raise ValueError(f"Non è stato possibile recuperare il nome per il ticker {ticker}")


"""
def price_by_ticker(ticker, date_str):

    date_obj = datetime.strptime(date_str, "%d-%m-%Y").date()
    if date_obj == date.today():

    try:
        data = yf.download("1AVGO.MI", start=ref_date, end="2023-12-30")
    except:
        raise ValueError(f"Non è stato possibile recuperare il nome per il ticker {ticker}")
"""





# Per prendere il TER: dal ticker, prendi l'ISIN con OpenFIGI, 
#                      poi vai su JustETF e fai scraping

def get_isin_from_ticker(ticker, exch_code=None):
    url = "https://api.openfigi.com/v3/mapping"
    headers = {"Content-Type": "application/json"}
    body = [{"idType": "TICKER", "idValue": ticker}]
    if exch_code:
        body[0]["exchCode"] = exch_code
    
    resp = requests.post(url, headers=headers, json=body)
    resp.raise_for_status()
    data = resp.json()
    
    for d in data[0].get("data", []):
        if d.get("idType") == "ID_ISIN":
            return d.get("idValue")
    return None

def fetch_ter(isin):
    url = f"https://www.justetf.com/en/etf-profile.html?ticker={isin}"
    r = requests.get(url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    html = r.text

    # regex
    m = re.search(r"(\d+(?:\.\d+)?%\s*p\.a\.?)", html)
    if m:
        return m.group(1), None

    return None, f"Non è stato possibile recuperare il TER per il prodotto{isin}"





# Vecchie funzioni per recuperare nome da isin

def lookup_by_isin(isin):
    url = "https://api.openfigi.com/v3/mapping"
    headers = {"Content-Type": "application/json"}
    body = [{
            "idType": "ID_ISIN",
            "idValue": isin
    }]
    resp = requests.post(url, headers=headers, json=body)
    resp.raise_for_status()
    return resp.json()

def parse_response(response):
    # response is a list with dictionaries
    if not response or "data" not in response[0]:
        return None
    
    data = response[0]["data"][0]
    parsed = {
        "figi": data.get("figi"),
        "name": data.get("name"),
        "ticker": data.get("ticker"),
        "exchange": data.get("exchCode"),
        "securityType": data.get("securityType"),
        "marketSector": data.get("marketSector")
    }
    return parsed