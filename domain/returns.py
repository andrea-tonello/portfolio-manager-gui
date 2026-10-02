"""Money-weighted return of a series of cash flows (XIRR).

XIRR is the yearly interest rate at which all deposits, withdrawals and the
final portfolio value balance out, so it accounts for when money went in and out.
"""

import numpy as np


def _secant(f, x0, x1, tol=1e-7, max_iter=100):
    """Find a value x where f(x) = 0, starting from two guesses x0 and x1 (secant method).

    Each step draws a straight line through the last two points of f and uses
    the spot where that line crosses zero as the next guess, until |f(x)| < tol.
    xirr uses it to find the rate at which the cash flows balance out. It
    replaces scipy.optimize.newton, which runs this same method when no
    derivative is given, so the app does not need SciPy (a large download).

    Example: _secant(lambda x: x * x - 2, 1, 2) -> 1.41421... (the square root of 2)

    Raises:
        ZeroDivisionError: the last two guesses give (almost) the same f value,
            so there is no slope to follow.
        RuntimeError: no guess got close enough to zero within max_iter steps.
    """
    x_prev, x = x0, x1
    for _ in range(max_iter):
        fx = f(x)
        if abs(fx) < tol:
            return x
        denominator = fx - f(x_prev)
        if abs(denominator) < 1e-10:
            raise ZeroDivisionError("secant method: flat function, no slope to follow")
        x_prev, x = x, x - fx * (x - x_prev) / denominator
    raise RuntimeError(f"secant method: no convergence after {max_iter} iterations")


def xirr(cash_flows, flows_dates, annualization=365, x0=0.1, x1=0.2, max_iter=100):
    days = [(day - flows_dates[0]).days for day in flows_dates]
    years = np.array(days) / annualization

    def npv_formula(rate):
        return sum(
            cf / (1 + rate) ** t
            for cf, t in zip(cash_flows, years)
        )

    try:
        xirr_rate = _secant(npv_formula, x0=x0, x1=x1, max_iter=max_iter)
        return xirr_rate
    except (ZeroDivisionError, RuntimeError):
        return np.nan
