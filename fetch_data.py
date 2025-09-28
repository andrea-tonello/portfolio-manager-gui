import requests
import re

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
}


def fetch_ter(isin):
    url = f"https://www.justetf.com/en/etf-profile.html?isin={isin}"
    r = requests.get(url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    html = r.text

    # regex
    m = re.search(r"(\d+(?:\.\d+)?%\s*p\.a\.?)", html)
    if m:
        return m.group(1), None

    return None, f"Non è stato possibile recuperare il TER per il prodotto {isin}"


def lookup_by_isin(isin):
    url = "https://api.openfigi.com/v3/mapping"
    headers = {"Content-Type": "application/json"}
    body = [
        {
            "idType": "ID_ISIN",
            "idValue": isin
        }
    ]
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