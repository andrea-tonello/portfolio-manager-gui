"""Tests for the Value at Risk (VaR) simulation in services/analysis_service.py.

VaR answers: "over the next N days, how much could the portfolio lose, in all
but the worst 1% of cases?" The app simulates many possible outcomes and reads
the loss at the worst-1% mark. Every outcome follows one bell curve whose centre
and spread are known in advance, so the simulation can be checked against them.
"""

from statistics import NormalDist

import numpy as np
import pytest

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
