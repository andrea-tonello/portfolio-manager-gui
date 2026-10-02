"""Tests for services/market_data.py, run against canned Yahoo responses (no network)."""

import io
import json
import urllib.request

import pandas as pd
import pytest

from services import market_data
from services.market_data import download_close, download_prices_eur, search_tickers

# Shaped like Yahoo's search response, trimmed to the fields search_tickers reads.
# The quoteType / typeDisp values are what Yahoo returned for these two tickers:
# note the label capitalisation differs ("ETF" vs "Equity").
YAHOO_SEARCH_RESPONSE = {
    "quotes": [
        {"symbol": "MWEQ.MI", "shortname": "Invesco MSCI Wrld Equal Weight ", "exchDisp": "Milan",
         "quoteType": "ETF", "typeDisp": "ETF"},
        {"symbol": "ISP.MI", "shortname": "INTESA SANPAOLO", "exchDisp": "Milan",
         "quoteType": "EQUITY", "typeDisp": "Equity"},
    ]
}


def fake_yahoo(monkeypatch, response):
    """Make urllib.request.urlopen answer with `response` as JSON, as if Yahoo had sent it.

    This replaces the network guard's refusal for this test only, so no real
    request is made.
    """
    def urlopen(request, *args, **kwargs):
        """Stand-in for urlopen: ignore the URL and return the canned JSON body."""
        return io.BytesIO(json.dumps(response).encode("utf-8"))

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)


def test_quote_type_is_lowercase_code_for_comparisons(monkeypatch):
    """quote_type is 'etf' / 'equity', whatever capitalisation Yahoo uses.

    The ETF/Stock asset-class check compares against these lowercase codes;
    comparing Yahoo's display label instead rejected every valid ticker.
    """
    fake_yahoo(monkeypatch, YAHOO_SEARCH_RESPONSE)

    results = search_tickers(".MI", quotes_count=2)

    assert [(r["symbol"], r["quote_type"]) for r in results] == [
        ("MWEQ.MI", "etf"),
        ("ISP.MI", "equity"),
    ]


def test_type_keeps_yahoo_label_for_display(monkeypatch):
    """`type` stays Yahoo's readable label, shown in the ticker suggestions."""
    fake_yahoo(monkeypatch, YAHOO_SEARCH_RESPONSE)

    results = search_tickers(".MI", quotes_count=2)

    assert [r["type"] for r in results] == ["ETF", "Equity"]


# ── download_close ───────────────────────────────────────────────────

JAN_2_2024 = 1704153600  # Yahoo gives each price's day as seconds since 1970 (UTC)
CLOSES = {"AAA.MI": [10.0, 10.5], "BBB.MI": [20.0, 21.0]}


@pytest.fixture
def yahoo_charts(monkeypatch):
    """Make Yahoo's chart endpoint return two daily closes (2 and 3 January 2024) for each ticker in CLOSES.

    Any other ticker fails, as Yahoo does for an unknown symbol.
    """
    def fake_fetch_chart(ticker, **kwargs):
        """Return a chart shaped like Yahoo's, or fail for unknown tickers."""
        if ticker not in CLOSES:
            raise RuntimeError("There is no data for this ticker")
        return {
            "meta": {"longName": f"{ticker} Name"},
            "timestamp": [JAN_2_2024, JAN_2_2024 + 86400],
            "indicators": {"quote": [{"close": CLOSES[ticker]}]},
        }

    monkeypatch.setattr(market_data, "_fetch_chart", fake_fetch_chart)


@pytest.mark.parametrize("tickers", [["AAA.MI"], "AAA.MI", ["AAA.MI", "BBB.MI"], ["AAA.MI", "NOPE.MI"]],
                         ids=["one", "one-as-text", "two", "one-unknown"])
def test_download_close_always_returns_a_dataframe_with_one_column_per_known_ticker(yahoo_charts, tickers):
    """Prices come back as a DataFrame, one column per ticker Yahoo knows, even for a single ticker.

    Before D4 a single ticker gave a Series instead, and every caller had to
    convert it. Unknown tickers are left out.
    """
    prices, names = download_close(tickers)

    known = [t for t in ([tickers] if isinstance(tickers, str) else tickers) if t in CLOSES]
    assert isinstance(prices, pd.DataFrame)
    assert list(prices.columns) == known
    assert list(prices.index) == [pd.Timestamp("2024-01-02"), pd.Timestamp("2024-01-03")]
    assert prices["AAA.MI"].tolist() == [10.0, 10.5]
    assert names == {t: f"{t} Name" for t in known}


def test_download_close_with_no_known_ticker_returns_an_empty_dataframe(yahoo_charts):
    """If Yahoo knows none of the tickers, the result is an empty DataFrame and no names."""
    prices, names = download_close(["NOPE.MI"])

    assert isinstance(prices, pd.DataFrame) and prices.empty
    assert names == {}


# ── download_prices_eur ──────────────────────────────────────────────

FX = "USDEUR=X"  # Yahoo's ticker for the USD->EUR exchange rate
DAYS = pd.DatetimeIndex(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"], name="Date")
START, END = "2024-01-01", "2024-01-06"


@pytest.fixture
def closes(monkeypatch):
    """Make download_close serve canned prices; return the dict the test fills with them.

    Each entry is ticker -> closes on DAYS, None meaning no price that day.
    Days with no price at all are left out, as Yahoo does; tickers not in the
    dict are unknown. Each call's tickers are recorded under the key "_calls".
    """
    canned = {"_calls": []}

    def fake_download_close(tickers, start=None, end=None, **kwargs):
        """Return the canned closes of the requested tickers, shaped like download_close's result."""
        tickers = [tickers] if isinstance(tickers, str) else tickers
        canned["_calls"].append(list(tickers))
        known = {t: canned[t] for t in tickers if t in canned}
        if not known:
            return pd.DataFrame(), {}
        return pd.DataFrame(known, index=DAYS, dtype=float).dropna(how="all"), {t: t for t in known}

    monkeypatch.setattr(market_data, "download_close", fake_download_close)
    return canned


def test_usd_prices_are_converted_with_each_days_rate(closes):
    """A USD price is multiplied by that day's USD->EUR rate; EUR prices are left as they are."""
    closes.update({"AAA.MI": [10, 11, 12, 13], "UUU": [100, 100, 100, 100], FX: [0.90, 0.92, 0.94, 0.96]})

    prices = download_prices_eur([("AAA.MI", "EUR"), ("UUU", "USD")], START, END)

    assert list(prices.index) == list(DAYS)
    assert prices["AAA.MI"].tolist() == [10, 11, 12, 13]
    assert prices["UUU"].tolist() == pytest.approx([90, 92, 94, 96])


def test_days_without_an_exchange_rate_are_dropped(closes):
    """Only days with a USD->EUR rate are kept, even for EUR prices, so every column covers the same days."""
    closes.update({"AAA.MI": [10, 11, 12, 13], "UUU": [100, 100, 100, 100], FX: [0.90, None, 0.94, 0.96]})

    prices = download_prices_eur([("AAA.MI", "EUR"), ("UUU", "USD")], START, END)

    assert list(prices.index) == [DAYS[0], DAYS[2], DAYS[3]]


def test_gaps_are_filled_and_days_before_a_ticker_starts_are_dropped(closes):
    """A missing price repeats the day before; days before every ticker has a price are dropped.

    Example: AAA.MI has no price on the 3rd (it repeats 10) and BBB.MI starts
    on the 3rd, so the result starts on the 3rd.
    """
    closes.update({"AAA.MI": [10, None, 12, 13], "BBB.MI": [None, 20, 21, 22], FX: [0.9] * 4})

    prices = download_prices_eur([("AAA.MI", "EUR"), ("BBB.MI", "EUR")], START, END)

    assert list(prices.index) == list(DAYS[1:])
    assert prices["AAA.MI"].tolist() == [10, 12, 13]
    assert prices["BBB.MI"].tolist() == [20, 21, 22]


def test_eur_prices_do_not_need_an_exchange_rate(closes):
    """If the rate can't be downloaded, EUR-only prices are still returned."""
    closes.update({"AAA.MI": [10, 11, 12, 13]})

    prices = download_prices_eur([("AAA.MI", "EUR")], START, END)

    assert prices["AAA.MI"].tolist() == [10, 11, 12, 13]


def test_usd_prices_without_an_exchange_rate_raise(closes):
    """USD prices that can't be converted raise an error instead of being treated as EUR or as zero."""
    closes.update({"UUU": [100, 100, 100, 100]})

    with pytest.raises(RuntimeError):
        download_prices_eur([("UUU", "USD")], START, END)


@pytest.mark.parametrize("tickers", [[], [("NOPE.MI", "EUR")]], ids=["no-tickers", "unknown-ticker"])
def test_no_prices_gives_an_empty_dataframe(closes, tickers):
    """No tickers, or none Yahoo knows, gives an empty DataFrame; with no tickers nothing is downloaded."""
    closes.update({FX: [0.9] * 4})

    prices = download_prices_eur(tickers, START, END)

    assert isinstance(prices, pd.DataFrame) and prices.empty
    if not tickers:
        assert closes["_calls"] == []
