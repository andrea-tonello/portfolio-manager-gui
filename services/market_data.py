import http.client
import json
import logging
import threading
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, date, timedelta

import pandas as pd

from domain.errors import TickerNotFound
from utils.date_utils import DateLike
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

# Yahoo's company profiles (quoteSummary) only answer requests carrying a cookie
# and a matching token Yahoo calls the "crumb": fc.yahoo.com sets the cookie,
# getcrumb returns the crumb for it.
_SUMMARY_URL = "https://query2.finance.yahoo.com/v10/finance/quoteSummary"
_COOKIE_URL = "https://fc.yahoo.com"
_CRUMB_URL = "https://query1.finance.yahoo.com/v1/test/getcrumb"
_auth = None  # (cookie, crumb) once fetched, shared by every quoteSummary request
_auth_lock = threading.Lock()

# Yahoo's 11 sectors, by the key the app uses for each. Stocks name theirs
# "Financial Services", ETFs "financial_services" and "realestate" (no
# underscore): _sector_key reads every spelling as the same key.
SECTORS = (
    "basic_materials", "communication_services", "consumer_cyclical", "consumer_defensive", "energy",
    "financial_services", "healthcare", "industrials", "real_estate", "technology", "utilities",
)
_SECTOR_BY_LETTERS = {key.replace("_", ""): key for key in SECTORS}


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


def download_close(tickers: str | list[str], start: DateLike | None = None, end: DateLike | None = None,
                   period: str | None = None, adjusted: bool = False) -> tuple[pd.DataFrame, dict[str, str]]:
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
            # Each day as the exchange's own clock tells it, not UTC's: Yahoo stamps the USD->EUR rate at
            # midnight London time, which in British summer time is 23:00 UTC of the day before.
            timezone = meta.get("exchangeTimezoneName") or "UTC"
            dates = pd.to_datetime(timestamps, unit="s", utc=True).tz_convert(timezone).tz_localize(None).normalize()
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


def fetch_quotes(tickers: list[str]) -> dict[str, tuple[float, float | None, str]]:
    """Return {ticker: (price, previous_close, name)}: each ticker's latest price and the previous session's close.

    Both come from Yahoo's quote data, not from the daily closes: Yahoo
    sometimes has no daily close for a ticker on a day (e.g. some ETFs on
    Borsa Italiana), while the previous close it reports is still there.
    previous_close is None when Yahoo gives none. Unknown tickers are left out.

    Example: fetch_quotes(["VWCE.MI"]) -> {"VWCE.MI": (170.98, 170.88, "Vanguard FTSE All-World ...")}
    even on a day after one whose daily close is missing.
    """
    def _fetch_one(ticker):
        """Fetch one ticker's quote, or None when Yahoo gives no usable answer."""
        try:
            meta = _fetch_chart(ticker, period="1d").get("meta", {})
        except _NO_DATA_ERRORS as e:
            logger.warning("No quote for %s: %s", ticker, e)
            return None
        price, previous = meta.get("regularMarketPrice"), meta.get("chartPreviousClose")
        if price is None:
            return None
        name = meta.get("longName") or meta.get("shortName") or ticker
        return ticker, (float(price), None if previous is None else float(previous), name)

    if not tickers:
        return {}
    with ThreadPoolExecutor(max_workers=min(len(tickers), 8)) as pool:
        return dict(result for result in pool.map(_fetch_one, tickers) if result is not None)


def download_prices_eur(tickers_with_currency: list[tuple[str, str]], start: DateLike, end: DateLike) -> pd.DataFrame:
    """Download daily closing prices in EUR: one column per ticker, all on the same days.

    `tickers_with_currency` is a list of (ticker, currency) pairs, currency
    "EUR" or "USD". USD prices are multiplied by that day's USD->EUR rate, or
    the last one before it when that day has none: the rate never removes a
    day of prices, and is only downloaded when a USD ticker needs it. A
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
    prices = prices.ffill().dropna()
    if prices.empty:
        return prices

    usd_tickers = [t for t, currency in tickers_with_currency if currency == "USD" and t in prices.columns]
    if usd_tickers:
        rates, _ = download_close(USDEUR_TICKER, start=start, end=end)
        if rates.empty:
            raise RuntimeError("No USD->EUR exchange rate available to convert USD prices")
        rate = rates[USDEUR_TICKER].dropna()
        rate = rate.reindex(rate.index.union(prices.index)).ffill().reindex(prices.index)
        prices[usd_tickers] = prices[usd_tickers].mul(rate, axis=0)
        prices = prices.dropna()  # days before the first rate: their USD prices can't be converted
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


def fetch_exchange_rate(ref_date: str | None = None) -> float:
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


def fetch_splits(ticker: str, start: DateLike, end: DateLike) -> list[tuple[date, float]]:
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


def _yahoo_auth(stale=None) -> tuple[str, str]:
    """Return the (cookie, crumb) pair Yahoo's quoteSummary requires, fetching it the first time.

    The pair is kept for later requests. Pass the pair Yahoo just refused as
    `stale` to fetch a new one; when another request already replaced it,
    that newer pair is returned instead of fetching yet another.
    """
    global _auth
    with _auth_lock:
        if _auth is None or _auth == stale:
            try:
                with urllib.request.urlopen(urllib.request.Request(_COOKIE_URL, headers=_HEADERS), timeout=10) as resp:
                    headers = resp.headers
            except urllib.error.HTTPError as e:
                headers = e.headers  # fc.yahoo.com answers 404, but still sets the cookie
            # Each Set-Cookie header is "A3=value; Expires=...; Domain=...": keep "A3=value".
            cookie = "; ".join(c.split(";", 1)[0] for c in headers.get_all("Set-Cookie") or [])
            request = urllib.request.Request(_CRUMB_URL, headers={**_HEADERS, "Cookie": cookie})
            with urllib.request.urlopen(request, timeout=10) as resp:
                _auth = (cookie, resp.read().decode("utf-8"))
        return _auth


def _fetch_summary(ticker: str, modules: str) -> dict:
    """Fetch the parts `modules` (comma-separated, e.g. "assetProfile,topHoldings") of Yahoo's profile of `ticker`.

    Returns a dict with one entry per part Yahoo has for the ticker. Raises
    one of _NO_DATA_ERRORS when Yahoo gives no usable answer, e.g.
    urllib.error.HTTPError 404 for an unknown ticker.
    """
    def request(auth):
        """Send the request with the (cookie, crumb) pair `auth` and return Yahoo's JSON answer."""
        cookie, crumb = auth
        url = f"{_SUMMARY_URL}/{urllib.request.quote(ticker)}?modules={modules}&crumb={urllib.request.quote(crumb)}"
        with urllib.request.urlopen(urllib.request.Request(url, headers={**_HEADERS, "Cookie": cookie}),
                                    timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))

    auth = _yahoo_auth()
    try:
        data = request(auth)
    except urllib.error.HTTPError as e:
        if e.code != 401:
            raise
        data = request(_yahoo_auth(stale=auth))  # Yahoo no longer accepts the pair: try once with a new one
    result = data["quoteSummary"]["result"]
    if not result:
        raise RuntimeError("There is no profile for this ticker")
    return result[0]


def _sector_key(name: str) -> str | None:
    """Return the app's key (one of SECTORS) for a Yahoo sector name in any spelling, or None for one it doesn't know.

    Example: "Financial Services" and "financial_services" -> "financial_services",
    "realestate" -> "real_estate".
    """
    return _SECTOR_BY_LETTERS.get("".join(ch for ch in name.lower() if ch.isalpha()))


def fetch_sector_weights(tickers: list[str]) -> dict[str, dict[str, float]]:
    """Return how the value of each of `tickers` splits between sectors, as fractions adding up to 1.

    A stock is wholly in its one sector. An equity ETF is split like the
    companies it holds: Yahoo's own fractions may add up to a little more or
    less than 1 (rounding), so they are scaled to add up to exactly 1.
    Tickers Yahoo has no sectors for (bond and money-market ETFs, unknown
    tickers, no network) are left out. The fractions are today's.

    Example: ["ISP.MI", "SWDA.MI"] -> {"ISP.MI": {"financial_services": 1.0},
    "SWDA.MI": {"technology": 0.325, "financial_services": 0.156, ...}}.
    """
    def _fetch_one(ticker):
        """Return (ticker, its sector fractions), or None when Yahoo has none."""
        try:
            summary = _fetch_summary(ticker, "assetProfile,topHoldings")
            sector = summary.get("assetProfile", {}).get("sector")
            if sector:
                raw = {sector: 1.0}
            else:
                # [{"technology": {"raw": 0.3248, "fmt": "32.48%"}}, {"realestate": {...}}, ...]
                raw = {name: value["raw"]
                       for item in summary.get("topHoldings", {}).get("sectorWeightings", [])
                       for name, value in item.items()}
        except _NO_DATA_ERRORS as e:
            logger.warning("No sectors for %s: %s", ticker, e)
            return None
        weights = {}
        for name, weight in raw.items():
            key = _sector_key(name)
            if key is not None and weight > 0:
                weights[key] = weights.get(key, 0) + weight
        total = sum(weights.values())
        if total <= 0:
            return None
        return ticker, {key: weight / total for key, weight in weights.items()}

    if not tickers:
        return {}
    with ThreadPoolExecutor(max_workers=min(len(tickers), 8)) as pool:
        return dict(result for result in pool.map(_fetch_one, tickers) if result is not None)
