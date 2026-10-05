"""Tests for the input checks of the Analysis tools: dates, tickers, windows and the VaR settings.

A refused input shows its message, and the calculation doesn't start.
"""

from datetime import date, timedelta

import pytest
from conftest import snack_texts

from views.analysis_view import AnalysisView

TOMORROW = date.today() + timedelta(days=1)
ROLLING = {"corr_start": date(2024, 1, 2), "corr_end": date(2024, 6, 3), "corr_type": "rolling",
           "corr_asset1": "AAA.MI", "corr_asset2": "BBB.MI"}


@pytest.mark.parametrize("submit, inputs, message", [
    ("_submit_summary", {"sum_date": None}, "Date is missing"),
    ("_submit_summary", {"sum_date": TOMORROW}, "Cannot insert future dates"),
    ("_submit_allocation", {"alloc_date": None}, "Date is missing"),
    ("_submit_correlation", {"corr_start": date(2024, 1, 2), "corr_end": None}, "Date is missing"),
    ("_submit_correlation", {"corr_start": date(2024, 1, 2), "corr_end": TOMORROW}, "Cannot insert future dates"),
    ("_submit_correlation", {"corr_start": date(2024, 5, 2), "corr_end": date(2024, 5, 2)},
     "Start date must be before end date"),
    ("_submit_correlation", {**ROLLING, "corr_asset2": " "}, "Missing ticker/s"),
    ("_submit_correlation", {**ROLLING, "corr_window": "0"},
     "The number of days must be an integer greater than 0."),
    ("_submit_drawdown", {"dd_start": date(2024, 6, 1), "dd_end": date(2024, 5, 2)},
     "Start date must be before end date"),
    ("_submit_var", {"var_ci": "1"}, "The Confidence Interval is defined between 0 and 1, extrema excluded."),
    ("_submit_var", {"var_ci": "0.95", "var_days": "0"},
     "The number of days for the forecast must be an integer greater than 0"),
], ids=["summary-no-date", "summary-future", "allocation-no-date", "correlation-no-end",
        "correlation-future-end", "correlation-same-day", "rolling-without-second-ticker", "rolling-zero-window",
        "drawdown-end-before-start", "var-confidence-of-1", "var-zero-days"])
def test_analysis_refuses_invalid_inputs(app, page, submit, inputs, message):
    """Each tool shows the message for its first invalid input, and starts no calculation."""
    view = AnalysisView(app)
    view.build()
    started = []
    page.run_thread = lambda fn, *args: started.append(fn)
    for field, value in inputs.items():
        getattr(view, field).value = value

    getattr(view, submit)(None)

    assert snack_texts(page) == [message]
    assert started == []
