from services.market_data import fetch_ticker_name, fetch_exchange_rate as _fetch_rate


def fetch_name(ticker):
    return fetch_ticker_name(ticker)


def fetch_exchange_rate(ref_date=None):
    return _fetch_rate(ref_date)
