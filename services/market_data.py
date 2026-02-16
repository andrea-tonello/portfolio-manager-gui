import json
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, date, timedelta

import pandas as pd

from utils.other_utils import round_half_up

_BASE_URL = "https://query1.finance.yahoo.com/v8/finance/chart"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
    ),
}


def _to_unix(dt) -> int:
    """Convert a date/datetime/pd.Timestamp/string to unix timestamp."""
    if isinstance(dt, str):
        dt = datetime.strptime(dt, "%Y-%m-%d")
    if isinstance(dt, pd.Timestamp):
        dt = dt.to_pydatetime()
    if isinstance(dt, date) and not isinstance(dt, datetime):
        dt = datetime(dt.year, dt.month, dt.day)
    return int(dt.timestamp())


def _fetch_chart(ticker: str, start=None, end=None, period=None, interval="1d") -> dict:
    """Fetch raw chart data from Yahoo Finance v8 API."""
    url = f"{_BASE_URL}/{ticker}?"
    params = [f"interval={interval}"]
    if period:
        params.append(f"range={period}")
    else:
        if start:
            params.append(f"period1={_to_unix(start)}")
        if end:
            params.append(f"period2={_to_unix(end)}")
    url += "&".join(params)

    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    result = data.get("chart", {}).get("result")
    if not result:
        raise RuntimeError(f"No data returned for {ticker}")
    return result[0]


def download_close(tickers, start=None, end=None, period=None) -> pd.DataFrame:
    """Fetch closing prices for one or more tickers.

    Returns a DataFrame with DatetimeIndex and one column per ticker,
    matching the shape of yf.download(...)["Close"].
    For a single ticker, returns a pd.Series.
    """
    if isinstance(tickers, str):
        tickers = [tickers]

    def _fetch_one(ticker):
        try:
            chart = _fetch_chart(ticker, start=start, end=end, period=period)
            timestamps = chart.get("timestamp", [])
            closes = chart.get("indicators", {}).get("quote", [{}])[0].get("close", [])
            if not timestamps or not closes:
                return None
            dates = pd.to_datetime(timestamps, unit="s", utc=True).tz_localize(None).normalize()
            s = pd.Series(closes, index=dates, name=ticker, dtype=float)
            s = s[~s.index.duplicated(keep="last")]
            return (ticker, s)
        except Exception:
            return None

    all_series = {}
    with ThreadPoolExecutor(max_workers=min(len(tickers), 8)) as pool:
        for result in pool.map(_fetch_one, tickers):
            if result is not None:
                all_series[result[0]] = result[1]

    if not all_series:
        return pd.DataFrame()

    df = pd.DataFrame(all_series)
    df.index.name = "Date"

    if len(tickers) == 1 and tickers[0] in df.columns:
        return df[tickers[0]]
    return df


def fetch_ticker_name(ticker: str) -> str:
    """Fetch the long name for a ticker symbol."""
    try:
        chart = _fetch_chart(ticker, period="1d")
        meta = chart.get("meta", {})
        name = meta.get("longName") or meta.get("shortName")
        if name:
            return name
    except Exception:
        pass
    raise RuntimeError(f"Could not fetch name for {ticker}")


def fetch_exchange_rate(ref_date=None) -> float:
    """Fetch the USDEUR exchange rate for a given date."""
    if ref_date is None:
        ref_date = date.today().strftime("%Y-%m-%d")

    ref_dt = datetime.strptime(ref_date, "%Y-%m-%d").date()

    if ref_dt == date.today():
        chart = _fetch_chart("USDEUR=X", period="2d", interval="1m")
    else:
        next_day = (ref_dt + timedelta(days=1)).strftime("%Y-%m-%d")
        chart = _fetch_chart("USDEUR=X", start=ref_date, end=next_day)

    closes = chart.get("indicators", {}).get("quote", [{}])[0].get("close", [])
    if not closes:
        raise RuntimeError("No exchange rate data available")

    # Filter out None values and take last valid
    valid = [c for c in closes if c is not None]
    if not valid:
        raise RuntimeError("No valid exchange rate data")

    return round_half_up(valid[-1], decimal="0.000001")
