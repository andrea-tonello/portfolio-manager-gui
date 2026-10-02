"""Tests for the automatic split check on the Home screen.

When a held stock has split (e.g. each share became 2) and the user hasn't
recorded it, the app offers to add the Split row. Yahoo Finance reports the
splits (market_data.fetch_splits); the account's ledger says which ones are
already recorded (domain.positions.unrecorded_splits);
operations_service.detect_unrecorded_splits puts the two together.
"""

from datetime import date, datetime, timezone

import pandas as pd
import pytest

from domain.positions import first_trade_date, unrecorded_splits
from services import market_data
from services.market_data import fetch_splits
from services.operations_service import detect_unrecorded_splits


def _noon_utc(day):
    """Unix timestamp of 12:00 UTC on `day`, the form in which Yahoo dates events.

    Noon keeps the same calendar date in every European and American time zone.
    """
    return int(datetime(day.year, day.month, day.day, 12, tzinfo=timezone.utc).timestamp())


# AAA.MI was bought on 3 January 2024 and a 2:1 split was recorded on 1 July.
LEDGER = pd.DataFrame({
    "date": ["01-01-2000", "03-01-2024", "01-07-2024", "05-01-2024"],
    "operation": [None, "Buy", "Split", "Buy"],
    "ticker": [None, "AAA.MI", "AAA.MI", "BBB.MI"],
})


@pytest.fixture
def yahoo_requests(monkeypatch):
    """Make Yahoo report three split events for any ticker, and record each request.

    The events: 2:1 on 2 July 2024, 1:10 (reverse) on 15 October 2024, and
    an incomplete one on 1 August 2024 without a numerator. They are listed
    out of date order, as Yahoo may send them.
    """
    requests = []

    def fake_fetch_chart(ticker, **kwargs):
        """Remember the request and return Yahoo-shaped split events."""
        requests.append((ticker, kwargs))
        return {"events": {"splits": {
            "a": {"date": _noon_utc(date(2024, 10, 15)), "numerator": 1, "denominator": 10},
            "b": {"date": _noon_utc(date(2024, 7, 2)), "numerator": 2, "denominator": 1},
            "c": {"date": _noon_utc(date(2024, 8, 1)), "numerator": None, "denominator": 1},
        }}}

    monkeypatch.setattr(market_data, "_fetch_chart", fake_fetch_chart)
    return requests


def test_only_splits_not_yet_recorded_are_reported(yahoo_requests):
    """The 2 July split counts as recorded (the Split row is dated within a day of it); 15 October is reported.

    The incomplete event is ignored. Each split comes as (ISO date, new shares per old share).
    """
    assert detect_unrecorded_splits(LEDGER, "AAA.MI") == [("2024-10-15", 0.1)]


def test_yahoo_is_asked_from_the_day_before_the_first_purchase(yahoo_requests):
    """Only splits from when the ticker was first bought (minus a day) are requested."""
    detect_unrecorded_splits(LEDGER, "AAA.MI")

    ticker, kwargs = yahoo_requests[0]
    assert ticker == "AAA.MI"
    assert kwargs["start"] == datetime(2024, 1, 2)
    assert kwargs["events"] == "split"


def test_a_ticker_never_traded_is_not_looked_up(yahoo_requests):
    """A ticker with no buy, sell or split in the ledger reports nothing, without asking Yahoo."""
    assert detect_unrecorded_splits(LEDGER, "ZZZ.MI") == []
    assert yahoo_requests == []


def test_yahoo_unreachable_reports_no_split(monkeypatch):
    """If Yahoo can't be reached, no split is reported (the check is retried on the next app start)."""
    def unreachable(ticker, **kwargs):
        """Fail like a request without network."""
        raise RuntimeError("no network")

    monkeypatch.setattr(market_data, "_fetch_chart", unreachable)

    assert detect_unrecorded_splits(LEDGER, "AAA.MI") == []


# ── The two halves on their own ──────────────────────────────────────

def test_fetch_splits_returns_every_complete_event_oldest_first(yahoo_requests):
    """fetch_splits only talks to Yahoo: every complete split event as (date, ratio), oldest first."""
    splits = fetch_splits("AAA.MI", datetime(2024, 1, 2), datetime(2024, 12, 31))

    assert splits == [(date(2024, 7, 2), 2.0), (date(2024, 10, 15), 0.1)]


def test_unrecorded_splits_compares_with_the_ledger_without_network():
    """Splits within a day of a recorded Split row are left out; the others come back with ISO dates.

    30 June is a day before the split recorded on 1 July; 3 July is two days after.
    """
    splits = [(date(2024, 6, 30), 2.0), (date(2024, 7, 3), 3.0)]

    assert unrecorded_splits(LEDGER, "AAA.MI", splits) == [("2024-07-03", 3.0)]


def test_first_trade_date():
    """The date of a ticker's first buy, sell or split, or None if it was never traded."""
    assert first_trade_date(LEDGER, "AAA.MI") == datetime(2024, 1, 3)
    assert first_trade_date(LEDGER, "ZZZ.MI") is None
