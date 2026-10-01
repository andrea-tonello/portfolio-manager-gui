"""Focused tests for the Italian tax rules on capital losses.

compute_carryforward(df, day) answers: "how much carryforward (zainetto fiscale,
i.e. past capital losses not used yet) is available on this day?"
add_solar_years(day) answers: "until when can a loss created on this day be used?"

Each test checks one rule with a tiny hand-made account table, so a failure
names the rule that broke. The full-scenario snapshots live in
test_ledger_snapshots.py.
"""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from domain.ledger import ETF_PRODUCTS
from utils.account import compute_carryforward
from utils.date_utils import add_solar_years


# ── Helpers ──────────────────────────────────────────────────────────

def loss(day, amount, *, expiry="default", product="Stock"):
    """A row where a sale generated a capital loss of `amount` EUR on `day` (DD-MM-YYYY).

    The expiry defaults to what the app writes (31 December, 4 years later).
    Pass expiry=np.nan to simulate a row without an expiry date.
    """
    if expiry == "default":
        expiry = add_solar_years(pd.to_datetime(day, dayfirst=True))
    return {"date": day, "product": product, "generated_loss": amount,
            "expiry": expiry, "gross_gain": np.nan}


def gain(day, amount, *, product="Stock"):
    """A row where a sale realised a capital gain of `amount` EUR on `day` (DD-MM-YYYY)."""
    return {"date": day, "product": product, "generated_loss": np.nan,
            "expiry": np.nan, "gross_gain": amount}


def other(day):
    """A row for any operation that neither creates a loss nor realises a gain (deposit, buy, ...)."""
    return {"date": day, "product": "Stock", "generated_loss": np.nan,
            "expiry": np.nan, "gross_gain": np.nan}


def history(*rows):
    """Turn loss()/gain()/other() rows into the account table compute_carryforward reads.

    Only the columns compute_carryforward uses are included; rows must be in
    date order, as in a real account CSV.
    """
    return pd.DataFrame(list(rows))


# ── compute_carryforward ─────────────────────────────────────────────────

def test_no_losses_means_no_carryforward():
    """Gains alone never create a carryforward."""
    df = history(gain("10-01-2024", 100))
    assert compute_carryforward(df, date(2024, 12, 31)) == 0


def test_loss_adds_to_carryforward():
    """A loss of 78 EUR makes 78 EUR available to offset future gains."""
    df = history(loss("02-04-2024", 78))
    assert compute_carryforward(df, date(2024, 12, 31)) == 78


def test_later_gain_uses_up_carryforward():
    """A gain of 72 after a loss of 78 consumes 72, leaving 6."""
    df = history(loss("02-04-2024", 78), gain("03-06-2024", 72))
    assert compute_carryforward(df, date(2024, 12, 31)) == 6


def test_carryforward_never_goes_negative():
    """A gain bigger than the available losses empties the carryforward, it does not go below 0."""
    df = history(loss("02-04-2024", 50), gain("03-06-2024", 200))
    assert compute_carryforward(df, date(2024, 12, 31)) == 0


def test_gain_before_loss_does_not_consume_it():
    """Only gains realised *after* a loss can use it: order in time matters."""
    df = history(gain("01-03-2024", 100), loss("02-04-2024", 50))
    assert compute_carryforward(df, date(2024, 12, 31)) == 50


def test_oldest_loss_is_used_first():
    """Losses are consumed oldest first (FIFO), so the ones expiring soonest are used up.

    Example: 100 lost in 2024 (valid to 31-12-2028) and 100 lost in 2025
    (valid to 31-12-2029), then a 100 gain in 2025. The gain uses the 2024
    loss, so in mid-2029 the 2025 loss is still fully available.
    """
    df = history(
        loss("01-03-2024", 100),
        loss("03-03-2025", 100),
        gain("02-06-2025", 100),
    )
    assert compute_carryforward(df, date(2029, 6, 1)) == 100


def test_loss_still_counts_on_its_expiry_day():
    """A 2024 loss expires on 31-12-2028 and is still usable on that very day."""
    df = history(loss("02-04-2024", 78))
    assert compute_carryforward(df, date(2028, 12, 31)) == 78


def test_loss_is_gone_the_day_after_expiry():
    """On 01-01-2029 the 2024 loss can no longer be used."""
    df = history(loss("02-04-2024", 78))
    assert compute_carryforward(df, date(2029, 1, 1)) == 0


def test_gain_is_offset_only_by_losses_not_yet_expired():
    """An expired loss is skipped: a later gain consumes the still-valid losses instead.

    Example: 100 lost in 2024 (expired after 2028) and 100 lost in 2028, then
    a 100 gain in 2029. The gain must use the 2028 loss, leaving nothing.
    """
    df = history(
        loss("01-03-2024", 100),
        loss("01-06-2028", 100),
        gain("01-03-2029", 100),
    )
    assert compute_carryforward(df, date(2029, 6, 1)) == 0


def test_rows_after_the_requested_day_are_ignored():
    """Asking for the carryforward on a past day ignores later operations."""
    df = history(loss("01-03-2024", 30), loss("03-06-2024", 50))
    assert compute_carryforward(df, date(2024, 4, 1)) == 30


def test_same_day_operations_are_applied_in_the_order_entered():
    """A loss and a gain on the same day are applied in the order they were entered, even in long histories.

    Example: 100 lost in January; later, on a busy day, a 500 loss is entered
    before a 300 gain. The gain uses the oldest losses first: all of the 100,
    then 200 of the 500, leaving 300. Applying the gain before the 500 loss
    would use only the 100 and wrongly report 500. A plain sort reordered
    same-day rows only in histories longer than about 16 rows, hence the padding.
    """
    busy_day = "04-01-2024"
    df = history(
        loss("01-01-2024", 100),
        *[other(day) for day in ("02-01-2024", "03-01-2024") for _ in range(2)],
        *[other(busy_day) for _ in range(5)],
        loss(busy_day, 500),
        gain(busy_day, 300),
        *[other(busy_day) for _ in range(5)],
    )
    assert compute_carryforward(df, date(2024, 12, 31)) == 300


def test_as_of_index_ignores_rows_from_that_position_on():
    """With as_of_index=n, only the first n rows of the table are considered.

    The app passes as_of_index=len(df), i.e. "every row recorded so far".
    """
    df = history(loss("01-03-2024", 30), loss("01-03-2024", 50))
    assert compute_carryforward(df, date(2024, 12, 31), as_of_index=1) == 30


def test_loss_without_expiry_date_expires_the_same_day():
    """A loss row with no expiry date is treated as usable only on the day it was made."""
    df = history(loss("02-04-2024", 78, expiry=np.nan))
    assert compute_carryforward(df, date(2024, 4, 2)) == 78
    assert compute_carryforward(df, date(2024, 4, 3)) == 0


@pytest.mark.parametrize("etf_product", sorted(ETF_PRODUCTS))
def test_etf_gain_does_not_use_carryforward(etf_product):
    """Gains on ETFs are taxed in full and must leave the carryforward untouched.

    Under Italian rules ETF gains cannot be offset by past losses, so a 100
    loss followed by a 60 ETF gain still leaves 100 available for stocks.
    """
    df = history(loss("02-04-2024", 100), gain("03-06-2024", 60, product=etf_product))
    assert compute_carryforward(df, date(2024, 12, 31)) == 100


# ── add_solar_years ──────────────────────────────────────────────────

@pytest.mark.parametrize("loss_day, expected_expiry", [
    (date(2024, 6, 15), "31-12-2028"),   # mid-year
    (date(2024, 1, 1), "31-12-2028"),    # first day of the year
    (date(2024, 12, 31), "31-12-2028"),  # last day of the year
    (date(2024, 2, 29), "31-12-2028"),   # leap day
    (date(2023, 7, 10), "31-12-2027"),   # a different year
])
def test_loss_expires_on_31_december_four_years_later(loss_day, expected_expiry):
    """A loss can be used until 31 December of the 4th year after it was made (DD-MM-YYYY)."""
    assert add_solar_years(loss_day) == expected_expiry
