import yfinance as yf
from datetime import date, datetime, timedelta

from utils.other_utils import round_half_up

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
        raise RuntimeError(f"Could not fetch name for {ticker}: {e}")


def fetch_exchange_rate(ref_date=None):
    if datetime.strptime(ref_date, "%Y-%m-%d").date() == date.today():
        rate = yf.download("USDEUR=X", period="2d", interval="1m", progress=False)
    else:
        next_day = datetime.strptime(ref_date, "%Y-%m-%d") + timedelta(days=1)
        next_ref_date = next_day.strftime("%Y-%m-%d")
        rate = yf.download("USDEUR=X", start=ref_date, end=next_ref_date, progress=False)

    return round_half_up(rate["Close"].iloc[-1][0], decimal="0.000001")
