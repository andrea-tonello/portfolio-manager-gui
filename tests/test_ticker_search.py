"""Tests for components/ticker_search.TickerSearchField: the suggestion filter and where the suggestions show."""

import flet as ft
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
    """Minimal stand-in for ft.Page: the field reads the platform and calls page.update()."""

    def __init__(self, platform=ft.PagePlatform.LINUX):
        """Pretend to run on `platform` (a computer by default)."""
        self.platform = platform

    def update(self):
        """Do nothing: there is no real screen to redraw in tests."""


def shown_symbols(field: TickerSearchField) -> list[str]:
    """Return the ticker symbols currently listed in the field's suggestion panel.

    Each suggestion tile is Container > Column > Row > Text(symbol), as built
    by TickerSearchField._show_results.
    """
    return [tile.content.controls[0].controls[0].value for tile in field.field.controls]


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


@pytest.mark.parametrize("platform, full_screen", [
    (ft.PagePlatform.ANDROID, True),
    (ft.PagePlatform.IOS, True),
    (ft.PagePlatform.LINUX, False),
    (ft.PagePlatform.WINDOWS, False),
])
def test_on_a_phone_the_suggestions_cover_the_screen(platform, full_screen):
    """On a phone or tablet the suggestions take the whole screen, so the on-screen keyboard can't hide them.

    A panel next to the field ended up partly under the keyboard, with its
    list padded by the keyboard's height. Computers keep the floating panel.
    """
    field = TickerSearchField(FakePage(platform))

    assert field.field.full_screen is full_screen
