"""Tests for the suggestion filter of components/ticker_search.TickerSearchField."""

import pytest

from components.ticker_search import TickerSearchField

# What search_tickers returns for an ETF and a stock (see test_market_data.py).
SEARCH_RESULTS = [
    {"symbol": "MWEQ.MI", "name": "Invesco MSCI Wrld Equal Weight ", "exchange": "Milan",
     "type": "ETF", "quote_type": "etf"},
    {"symbol": "ISP.MI", "name": "INTESA SANPAOLO", "exchange": "Milan",
     "type": "Equity", "quote_type": "equity"},
]


class FakePage:
    """Minimal stand-in for ft.Page: the field only calls page.update() here."""

    def update(self):
        """Do nothing: there is no real screen to redraw in tests."""


def shown_symbols(field: TickerSearchField) -> list[str]:
    """Return the ticker symbols currently listed in the field's suggestion dropdown.

    Each suggestion tile is Container > Column > Row > Text(symbol), as built
    by TickerSearchField._show_results.
    """
    if not field._overlay.visible:
        return []
    return [tile.content.controls[0].controls[0].value for tile in field._suggestions.controls]


@pytest.mark.parametrize("type_filter, expected", [
    ("etf", ["MWEQ.MI"]),              # ETF tab
    ("equity", ["ISP.MI"]),            # Stock tab
    (None, ["MWEQ.MI", "ISP.MI"]),     # fields without a filter (dividend, watchlist, ...)
])
def test_suggestions_are_filtered_by_asset_class(type_filter, expected):
    """The ETF tab suggests only ETFs, the Stock tab only stocks, other fields everything."""
    field = TickerSearchField(FakePage(), type_filter=type_filter)

    field._show_results(SEARCH_RESULTS)

    assert shown_symbols(field) == expected
