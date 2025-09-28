import requests

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