"""Tests for HomeView's background work when it fails (e.g. offline).

Home fetches live prices, the watchlist and unrecorded splits in background
threads. When that fails, the screen keeps what it shows (last values, a
watchlist without prices, no split prompt), and the reason must be logged
instead of being silently dropped.
"""

import logging
import urllib.error

import pytest

import views.home_view
from views.home_view import HomeView


def _offline(*args, **kwargs):
    """Stand-in for a network call that fails as it does without a connection."""
    raise urllib.error.URLError("offline")


@pytest.fixture
def home(page, state, monkeypatch):
    """A built HomeView for the test account, whose background work then runs immediately."""
    view = HomeView(page, state)
    view.build()
    monkeypatch.setattr(page, "run_thread", lambda fn, *args: fn(*args))
    return view


def test_failed_live_refresh_is_logged(home, state, monkeypatch, caplog):
    """If live prices can't be fetched, Home keeps its last values and logs why."""
    state._split_checked_session = True  # skip the split check that follows a refresh
    monkeypatch.setattr(views.home_view, "priced_positions", _offline)

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
