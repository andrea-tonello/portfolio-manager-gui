"""Tests for the XIRR calculation (annualised return of a series of cash flows).

XIRR is the yearly interest rate at which all deposits (negative) and
withdrawals / final value (positive) balance out to zero. The app finds that
rate with a small secant-method solver (_secant) instead of SciPy, to keep
the app small.
"""

from datetime import date

import numpy as np
import pytest

from services.analysis_service import _secant, xirr


# ── xirr ─────────────────────────────────────────────────────────────

def test_one_year_gain_of_ten_percent():
    """Investing 1000 and getting back 1100 exactly 365 days later is a 10% yearly return."""
    rate = xirr([-1000, 1100], [date(2023, 1, 1), date(2024, 1, 1)])
    assert rate == pytest.approx(0.10, abs=1e-6)


@pytest.mark.parametrize("annualization, expected", [
    (365, 0.10),   # yearly rate: 1.10 x 1.10 = 1.21 over two years
    (730, 0.21),   # rate over the whole period, as compute_summary does for "xirr_full"
])
def test_annualization_sets_the_period_the_rate_refers_to(annualization, expected):
    """`annualization` is the number of days one "period" lasts.

    Example: 1000 grows to 1210 in 730 days. Per 365-day year that is 10%
    (1.1 x 1.1 = 1.21); over the whole 730-day period it is 21%.
    """
    rate = xirr([-1000, 1210], [date(2021, 1, 1), date(2023, 1, 1)], annualization=annualization)
    assert rate == pytest.approx(expected, abs=1e-6)


def test_no_solution_gives_nan():
    """With only positive cash flows no rate can balance them, so xirr returns NaN instead of failing."""
    rate = xirr([100, 100], [date(2023, 1, 1), date(2024, 1, 1)])
    assert np.isnan(rate)


# ── _secant ──────────────────────────────────────────────────────────

def test_secant_finds_a_root():
    """It finds x where f(x) = 0: for f(x) = x² - 2 that is √2 ≈ 1.41421."""
    assert _secant(lambda x: x * x - 2, 1, 2) == pytest.approx(2 ** 0.5, abs=1e-6)


def test_secant_raises_zero_division_on_a_flat_function():
    """A flat function has no slope to follow, so the solver gives up with ZeroDivisionError."""
    with pytest.raises(ZeroDivisionError):
        _secant(lambda x: 5.0, 1, 2)


def test_secant_raises_runtime_error_when_it_never_converges():
    """x² + 1 is never zero, so after max_iter attempts the solver gives up with RuntimeError."""
    with pytest.raises(RuntimeError):
        _secant(lambda x: x * x + 1, 1, 2)
