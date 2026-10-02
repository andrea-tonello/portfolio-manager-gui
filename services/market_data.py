import http.client
import json
import logging
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, date, timedelta

import pandas as pd

from domain.errors import TickerNotFound
from utils.other_utils import round_half_up

logger = logging.getLogger(__name__)

# Errors meaning "Yahoo gave no usable answer", which the app treats as "no data":
# no network, a timeout or an HTTP error such as 404 for an unknown ticker
# (OSError, which includes urllib's URLError), a broken connection mid-reply
# (HTTPException), a reply that isn't JSON (ValueError), a reply without the
# expected fields (KeyError, IndexError), or a chart with no data (RuntimeError,
# raised by _fetch_chart). Anything else, e.g. a TypeError, is a bug and is raised.
_NO_DATA_ERRORS = (OSError, http.client.HTTPException, ValueError, KeyError, IndexError, RuntimeError)

_BASE_URL = "https://query1.finance.yahoo.com/v8/finance/chart"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
    ),
}
# Yahoo's ticker for the USD->EUR exchange rate (how many EUR one USD buys).
USDEUR_TICKER = "USDEUR=X"


def _to_unix(dt) -> int:
    """Convert a date/datetime/pd.Timestamp/string to unix timestamp."""
    if isinstance(dt, str):
        dt = datetime.strptime(dt, "%Y-%m-%d")
    if isinstance(dt, pd.Timestamp):
        dt = dt.to_pydatetime()
    if isinstance(dt, date) and not isinstance(dt, datetime):
        dt = datetime(dt.year, dt.month, dt.day)
    return int(dt.timestamp())


def _fetch_chart(ticker: str, start=None, end=None, period=None, interval="1d", events=None) -> dict:
    """Fetch raw chart data from Yahoo Finance v8 API.

    events: optional str like "split" or "split,div" to request corporate-action events.
    """
    url = f"{_BASE_URL}/{ticker}?"
    params = [f"interval={interval}"]
    if period:
        params.append(f"range={period}")
    else:
        if start:
            params.append(f"period1={_to_unix(start)}")
        if end:
            params.append(f"period2={_to_unix(end)}")
    if events:
        params.append(f"events={events}")
    url += "&".join(params)

    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    result = data.get("chart", {}).get("result")
    if not result:
        raise RuntimeError("There is no data for this ticker")
    return result[0]


def download_close(tickers, start=None, end=None, period=None, adjusted=False):
    """Fetch daily closing prices for one or more tickers.

    Returns (prices, names): `prices` is always a DataFrame with one row per
    day and one column per ticker Yahoo knows (unknown ones are left out;
    empty if none is known), and `names` maps each ticker to its full name.

    Example: download_close("ISP.MI", period="2d") -> a 2-row DataFrame with
    the single column "ISP.MI", and {"ISP.MI": "Intesa Sanpaolo S.p.A."}.

    When adjusted=True, reads from indicators.adjclose instead of raw close.
    Adjusted close reflects both splits and dividends — use only for cases where
    split continuity matters and dividends are not separately accounted for
    (e.g. prev_close lookup across a split boundary).
    """
    if isinstance(tickers, str):
        tickers = [tickers]

    def _fetch_one(ticker):
        try:
            chart = _fetch_chart(ticker, start=start, end=end, period=period)
            meta = chart.get("meta", {})
            name = meta.get("longName") or meta.get("shortName") or ticker
            timestamps = chart.get("timestamp", [])
            indicators = chart.get("indicators", {})
            if adjusted:
                adj = indicators.get("adjclose", [{}])
                closes = adj[0].get("adjclose", []) if adj else []
                if not closes:
                    closes = indicators.get("quote", [{}])[0].get("close", [])
            else:
                closes = indicators.get("quote", [{}])[0].get("close", [])
            if not timestamps or not closes:
                return None
            dates = pd.to_datetime(timestamps, unit="s", utc=True).tz_localize(None).normalize()
            s = pd.Series(closes, index=dates, name=ticker, dtype=float)
            s = s[~s.index.duplicated(keep="last")]
            return (ticker, s, name)
        except _NO_DATA_ERRORS as e:
            logger.warning("No prices for %s: %s", ticker, e)
            return None

    all_series = {}
    names = {}
    with ThreadPoolExecutor(max_workers=min(len(tickers), 8)) as pool:
        for result in pool.map(_fetch_one, tickers):
            if result is not None:
                all_series[result[0]] = result[1]
                names[result[0]] = result[2]

    if not all_series:
        return pd.DataFrame(), names

    df = pd.DataFrame(all_series)
    df.index.name = "Date"
    return df, names


def download_prices_eur(tickers_with_currency, start, end):
    """Download daily closing prices in EUR: one column per ticker, all on the same days.

    `tickers_with_currency` is a list of (ticker, currency) pairs, currency
    "EUR" or "USD". USD prices are multiplied by that day's USD->EUR rate.
    Only days with a rate are kept (when the rate can be downloaded), a
    missing price repeats the previous day's, and days before every ticker
    has a price are dropped. Returns an empty DataFrame when there are no
    tickers or no prices; raises RuntimeError when USD prices can't be
    converted because the rate is unavailable.

    Example: [("ISP.MI", "EUR"), ("AAPL", "USD")] -> columns ISP.MI and AAPL,
    where AAPL at 200 USD on a day the rate is 0.92 becomes 184 EUR.
    """
    if not tickers_with_currency:
        return pd.DataFrame()
    prices, _ = download_close([ticker for ticker, _ in tickers_with_currency], start=start, end=end)
    if prices.empty:
        return prices
    rates, _ = download_close(USDEUR_TICKER, start=start, end=end)

    if not rates.empty:
        common_dates = prices.index.intersection(rates.index)
        prices = prices.loc[common_dates]
        rates = rates.loc[common_dates].ffill().dropna()
    prices = prices.ffill().dropna()
    if prices.empty:
        return prices

    usd_tickers = [t for t, currency in tickers_with_currency if currency == "USD" and t in prices.columns]
    if usd_tickers:
        if rates.empty:
            raise RuntimeError("No USD->EUR exchange rate available to convert USD prices")
        prices[usd_tickers] = prices[usd_tickers].mul(rates[USDEUR_TICKER], axis=0)
    return prices


def fetch_ticker_name(ticker: str) -> str:
    """Fetch the long name for a ticker symbol (e.g. "ISP.MI" -> "Intesa Sanpaolo S.p.A.").

    Raises TickerNotFound when Yahoo returns no name for it.
    """
    try:
        chart = _fetch_chart(ticker, period="1d")
        meta = chart.get("meta", {})
        name = meta.get("longName") or meta.get("shortName")
        if name:
            return name
    except _NO_DATA_ERRORS as e:
        logger.warning("No name for %s: %s", ticker, e)
    raise TickerNotFound(ticker)


def fetch_exchange_rate(ref_date=None) -> float:
    """Fetch the USDEUR exchange rate for a given date."""
    if ref_date is None:
        ref_date = date.today().strftime("%Y-%m-%d")

    ref_dt = datetime.strptime(ref_date, "%Y-%m-%d").date()

    if ref_dt == date.today():
        chart = _fetch_chart(USDEUR_TICKER, period="2d", interval="1m")
    else:
        # Widen window to cover weekends and holidays
        start_day = (ref_dt - timedelta(days=5)).strftime("%Y-%m-%d")
        next_day = (ref_dt + timedelta(days=1)).strftime("%Y-%m-%d")
        chart = _fetch_chart(USDEUR_TICKER, start=start_day, end=next_day)

    closes = chart.get("indicators", {}).get("quote", [{}])[0].get("close", [])
    if not closes:
        raise RuntimeError("No exchange rate data available")

    # Filter out None values and take last valid
    valid = [c for c in closes if c is not None]
    if not valid:
        raise RuntimeError("No valid exchange rate data")

    return round_half_up(valid[-1], decimal="0.000001")


def fetch_splits(ticker: str, start, end) -> list[tuple]:
    """Return the stock splits Yahoo reports for `ticker` between `start` and `end`, oldest first.

    Each split is (date, ratio), ratio being new shares per old share: 4.0 for
    a 4:1 split, 0.1 for a 1:10 reverse split. Returns [] when there are none
    or Yahoo can't be reached.
    """
    try:
        chart = _fetch_chart(ticker, start=start, end=end, events="split")
    except _NO_DATA_ERRORS as e:
        logger.warning("No splits for %s: %s", ticker, e)
        return []

    splits = []
    for event in chart.get("events", {}).get("splits", {}).values():
        ts = event.get("date")
        num = event.get("numerator")
        den = event.get("denominator")
        if not ts or not num or not den:
            continue
        splits.append((datetime.fromtimestamp(ts).date(), float(num) / float(den)))
    return sorted(splits)


def search_tickers(query: str, quotes_count: int = 5) -> list[dict]:
    """Search Yahoo Finance for matching tickers.

    Returns a list of dicts with keys: symbol, name, exchange, type, quote_type.
    - `type` is Yahoo's human-readable label, for display only (e.g. "ETF", "Equity").
    - `quote_type` is Yahoo's machine code in lowercase, for comparisons
      (e.g. "etf", "equity"). Compare this one: the label's capitalisation
      differs between asset classes and is not guaranteed to stay the same.

    Example: search_tickers("ISP.MI", 1) ->
        [{"symbol": "ISP.MI", "name": "INTESA SANPAOLO", "exchange": "Milan",
          "type": "Equity", "quote_type": "equity"}]
    """
    url = (
        f"https://query2.finance.yahoo.com/v1/finance/search"
        f"?q={urllib.request.quote(query)}&quotesCount={quotes_count}&newsCount=0"
    )
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    results = []
    for q in data.get("quotes", []):
        results.append({
            "symbol": q.get("symbol", ""),
            "name": q.get("shortname") or q.get("longname", ""),
            "exchange": q.get("exchDisp", ""),
            "type": q.get("typeDisp", ""),
            "quote_type": q.get("quoteType", "").lower(),
        })
    return results
