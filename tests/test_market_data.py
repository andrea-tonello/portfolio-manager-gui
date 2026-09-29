"""Tests for services/market_data.py, run against canned Yahoo responses (no network)."""

import io
import json
import urllib.request

from services.market_data import search_tickers

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
