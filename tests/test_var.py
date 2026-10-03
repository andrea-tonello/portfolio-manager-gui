"""Tests for the Value at Risk (VaR) simulation in services/analysis_service.py.

VaR answers: "over the next N days, how much could the portfolio lose, in all
but the worst 1% of cases?" The app simulates many possible outcomes and reads
the loss at the worst-1% mark. Every outcome follows one bell curve whose centre
and spread are known in advance, so the simulation can be checked against them.
"""

import json
from datetime import date, datetime
from statistics import NormalDist

import numpy as np
import pytest
from conftest import FX_TICKER, fake_download_close
from test_ledger_snapshots import _replay, buy, deposit
from test_summary import round_floats

from domain.account import Account
from services import analysis_service, market_data
from services.analysis_service import _simulate_outcomes

# A 20,000 EUR portfolio, +0.04% per day on average, 1.1% daily volatility, 10 days.
VALUE, DAILY_RETURN, DAILY_STD, DAYS = 20_000, 0.0004, 0.011, 10
CENTRE = VALUE * DAILY_RETURN * DAYS                  # +80 EUR
SPREAD = VALUE * DAILY_STD * np.sqrt(DAYS)            # ≈ 695.7 EUR
EXACT_VAR_99 = -(CENTRE + SPREAD * NormalDist().inv_cdf(0.01))   # ≈ 1,538.4 EUR


def test_simulated_outcomes_follow_the_expected_bell_curve():
    """With many draws, the outcomes have the predicted centre, spread and 99% VaR.

    The worst-1% outcome is the 1st percentile; the VaR is that loss as a
    positive number (≈ 1,538 EUR here).
    """
    outcomes = _simulate_outcomes(VALUE, DAILY_RETURN, DAILY_STD, DAYS, 200_000,
                                  rng=np.random.default_rng(0))

    assert len(outcomes) == 200_000
    assert np.mean(outcomes) == pytest.approx(CENTRE, abs=10)
    assert np.std(outcomes) == pytest.approx(SPREAD, rel=0.01)
    assert -np.percentile(outcomes, 1) == pytest.approx(EXACT_VAR_99, rel=0.02)


def test_same_seed_gives_the_same_outcomes():
    """Passing a generator with a fixed seed makes the simulation repeatable (used by tests)."""
    first = _simulate_outcomes(VALUE, DAILY_RETURN, DAILY_STD, DAYS, 1_000, rng=np.random.default_rng(42))
    second = _simulate_outcomes(VALUE, DAILY_RETURN, DAILY_STD, DAYS, 1_000, rng=np.random.default_rng(42))

    assert np.array_equal(first, second)


# ── compute_var_mc: what the simulation is fed ───────────────────────

class _FixedNow(datetime):
    """A datetime whose now() is always 31 December 2024, so the VaR is computed on a fixed day."""

    @classmethod
    def now(cls, tz=None):
        """Return 31 December 2024 instead of the current time."""
        return cls(2024, 12, 31)


def _varying_fx_download_close(tickers, **kwargs):
    """fake_download_close, but with a USD->EUR rate that changes every day (between 0.90 and 0.96).

    With the fake market's constant rate, converting USD prices to EUR would
    not change their daily returns, so a mistake in the conversion would go
    unnoticed by the VaR.
    """
    prices, names = fake_download_close(tickers, **kwargs)
    if FX_TICKER in prices.columns:
        prices[FX_TICKER] = [0.90 + 0.01 * (day.day % 7) for day in prices.index]
    return prices, names


def test_var_inputs_match_snapshot(tmp_path, fake_market, monkeypatch, snapshot):
    """What compute_var_mc feeds the simulation is identical to tests/snapshots/var_inputs.json.

    The account holds a EUR stock (AAA.MI) and a USD stock (UUU) on
    31-12-2024, and a year of fake prices is used (from 2024-01-01). The
    simulation is random, so it is replaced by a stand-in that records its
    inputs: portfolio value, mean daily return, daily volatility, days.
    """
    monkeypatch.setattr(analysis_service, "datetime", _FixedNow)
    monkeypatch.setattr(analysis_service, "VAR_HISTORY_START", "2024-01-01")
    monkeypatch.setattr(market_data, "download_close", _varying_fx_download_close)
    # analysis_service imports download_close by name (its correlation tool uses it).
    monkeypatch.setattr(analysis_service, "download_close", _varying_fx_download_close)
    received = {}

    def record_inputs(value, daily_return, daily_std, days, num_simulations, rng=None):
        """Stand-in for _simulate_outcomes: remember the inputs and return flat outcomes."""
        received.update(value=value, daily_return=daily_return, daily_std=daily_std, days=days)
        return np.zeros(num_simulations)

    monkeypatch.setattr(analysis_service, "_simulate_outcomes", record_inputs)
    df = _replay([
        deposit(date(2024, 1, 2), 10_000),
        buy(date(2024, 1, 3), "AAA.MI", 10, 100.0, 2.0),
        buy(date(2024, 1, 4), "UUU", 5, 200.0, 1.0, currency="USD", conv_rate=0.9),
    ], tmp_path)

    analysis_service.compute_var_mc([Account(1, "Test Broker", "", df)], 0.99, 10)

    snapshot("var_inputs.json", json.dumps(round_floats(received), indent=2, sort_keys=True))
