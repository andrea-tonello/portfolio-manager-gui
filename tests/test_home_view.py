"""Tests for HomeView: the values it shows, and its background work when it fails (e.g. offline).

Home fetches live prices, the watchlist and unrecorded splits in background
threads. When that fails, the screen keeps what it shows (last values, a
watchlist without prices, no split prompt), and the reason must be logged
instead of being silently dropped.
"""

import json
import logging
import urllib.error
from datetime import date, datetime

import flet as ft
import pytest
from conftest import find_controls
from test_ledger_snapshots import _replay, buy, deposit

import services.portfolio_service
import views.home_view
from views.home_view import HomeView

# A second account that also holds BBB.MI, bought at a higher price, plus a USD stock.
SECOND_ACCOUNT = [
    deposit(date(2024, 1, 2), 5_000),
    buy(date(2024, 5, 10), "BBB.MI", 10, price=55.0, fee=1.0),
    buy(date(2024, 6, 3), "UUU", 3, price=210.0, fee=1.0, currency="USD", conv_rate=0.9),
]


class _FrozenNow(datetime):
    """A datetime whose now() is always 1 October 2024 at noon, so the fake prices are always the same."""

    @classmethod
    def now(cls, tz=None):
        """Return the fixed moment instead of the current time."""
        return cls(2024, 10, 1, 12, 0)


def _texts(control):
    """Each ft.Text inside `control`, in screen order, as "value" or "value (colour)"."""
    return [f"{t.value} ({getattr(t.color, 'value', t.color)})" if t.color else t.value
            for t in find_controls(control, ft.Text)]


def _offline(*args, **kwargs):
    """Stand-in for a network call that fails as it does without a connection."""
    raise urllib.error.URLError("offline")


@pytest.mark.parametrize("selection", ["overview", "1"])
def test_home_shows_the_values_of_the_accounts(selection, app, page, state, monkeypatch, tmp_path, snapshot):
    """NAV, assets and cash, the three P&L modes and the position rows match tests/snapshots/home_<selection>.json.

    Prices are the fake ones, on a fixed day. The overview adds the second account
    above, so its BBB.MI row merges both accounts at their average buy price, and
    the USD stock is valued through the exchange rate.
    """
    idx = state.add_broker("Second Broker")
    state.commit(idx, _replay(SECOND_ACCOUNT, tmp_path / "second"))
    state.home_selection = selection
    state.split_checked_session = True  # skip the split check that follows a refresh
    monkeypatch.setattr(views.home_view, "datetime", _FrozenNow)
    monkeypatch.setattr(page, "run_thread", lambda fn, *args: fn(*args))

    view = HomeView(app)
    view.build()  # nothing cached yet, so building fetches the values (right away, here)

    shown = {"nav": view._nav_text.value, "subtotals": [view._assets_text.value, view._cash_text.value],
             "pnl": [], "positions": []}
    for _ in range(3):
        shown["pnl"].append(_texts(view._pnl_container))
        view._cycle_pnl_mode(None)
    for _ in range(3):
        shown["positions"].append(_texts(view._positions_container))
        view._cycle_pos_display(None)

    snapshot(f"home_{selection}.json", json.dumps(shown, indent=2, ensure_ascii=False) + "\n")


@pytest.mark.parametrize("selection", ["overview", "1"])
def test_no_refresh_button_when_no_account_could_be_loaded(selection, app, state):
    """With accounts configured but none of their files loaded, Home says so and offers no refresh.

    The button used to stay, and tapping it raised an AttributeError, since the
    cards it updates were never built (REFACTORING.md, Appendix A item 7).
    """
    state.accounts.clear()
    state.home_selection = selection

    root = HomeView(app).build()

    assert ft.Icons.REFRESH not in [button.icon for button in find_controls(root, ft.IconButton)]
    assert state.translator.get("home.no_account") in [text.value for text in find_controls(root, ft.Text)]


@pytest.fixture
def home(app, page, monkeypatch):
    """A built HomeView for the test account, whose background work then runs immediately."""
    view = HomeView(app)
    view.build()
    monkeypatch.setattr(page, "run_thread", lambda fn, *args: fn(*args))
    return view


def test_failed_live_refresh_is_logged(home, state, monkeypatch, caplog):
    """If live prices can't be fetched, Home keeps its last values and logs why."""
    state.split_checked_session = True  # skip the split check that follows a refresh
    monkeypatch.setattr(services.portfolio_service, "priced_positions", _offline)

    with caplog.at_level(logging.ERROR):
        home._fetch_live_values()

    assert "Could not refresh live values" in caplog.text
    assert "offline" in caplog.text


def test_failed_watchlist_fetch_is_logged(home, state, monkeypatch, caplog):
    """If watchlist prices can't be fetched, the tickers are listed without prices and the reason is logged."""
    state.watchlist = ["AAA.MI"]
    monkeypatch.setattr(views.home_view, "download_close", _offline)

    with caplog.at_level(logging.ERROR):
        home._fetch_watchlist_prices()

    assert "Could not fetch watchlist prices" in caplog.text


def test_failed_split_check_is_logged(home, state, monkeypatch, caplog):
    """If the split check fails for a ticker, no prompt appears and the reason is logged."""
    state.home_selection = "1"
    monkeypatch.setattr(views.home_view.operations_service, "detect_unrecorded_splits", _offline)

    with caplog.at_level(logging.ERROR):
        home._check_splits_async()

    assert "Could not check BBB.MI for splits" in caplog.text
