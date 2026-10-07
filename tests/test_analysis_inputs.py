"""Tests for the inputs of the Analysis tools: their default dates, and the checks on dates, tickers,
windows and the VaR settings.

A refused input shows its message, and the calculation doesn't start.
"""

from datetime import date, timedelta

import pytest
from conftest import snack_texts
from test_ledger_snapshots import _replay, deposit

from views.analysis_view import AllocationTool, AnalysisView, CorrelationTool, DrawdownTool, SummaryTool, VarTool

TOMORROW = date.today() + timedelta(days=1)
ROLLING = {"start": date(2024, 1, 2), "end": date(2024, 6, 3), "kind": "rolling",
           "asset1": "AAA.MI", "asset2": "BBB.MI"}


@pytest.mark.parametrize("tool, inputs, message", [
    (SummaryTool, {"date": None}, "Date is missing"),
    (SummaryTool, {"date": TOMORROW}, "Cannot insert future dates"),
    (AllocationTool, {"date": None}, "Date is missing"),
    (CorrelationTool, {"start": date(2024, 1, 2), "end": None}, "Date is missing"),
    (CorrelationTool, {"start": date(2024, 1, 2), "end": TOMORROW}, "Cannot insert future dates"),
    (CorrelationTool, {"start": date(2024, 5, 2), "end": date(2024, 5, 2)},
     "Start date must be before end date"),
    (CorrelationTool, {**ROLLING, "asset2": " "}, "Missing ticker/s"),
    (CorrelationTool, {**ROLLING, "window": "0"},
     "The number of days must be an integer greater than 0."),
    (DrawdownTool, {"start": date(2024, 6, 1), "end": date(2024, 5, 2)},
     "Start date must be before end date"),
    (VarTool, {"ci": "1"}, "The Confidence Interval is defined between 0 and 1, extrema excluded."),
    (VarTool, {"ci": "0.95", "days": "0"},
     "The number of days for the forecast must be an integer greater than 0"),
], ids=["summary-no-date", "summary-future", "allocation-no-date", "correlation-no-end",
        "correlation-future-end", "correlation-same-day", "rolling-without-second-ticker", "rolling-zero-window",
        "drawdown-end-before-start", "var-confidence-of-1", "var-zero-days"])
def test_analysis_refuses_invalid_inputs(app, page, tool, inputs, message):
    """Each tool shows the message for its first invalid input, and starts no calculation."""
    view = AnalysisView(app)
    view.build()
    [tab] = [tab for tab in view.tabs if isinstance(tab.tool, tool)]
    started = []
    page.run_thread = lambda fn, *args: started.append(fn)
    for field, value in inputs.items():
        getattr(tab.tool, field).value = value

    tab.submit(None)

    assert snack_texts(page) == [message]
    assert started == []


@pytest.mark.parametrize("selection, second_deposit, first_day", [
    (None, date(2023, 6, 1), date(2023, 6, 1)),
    (1, date(2023, 6, 1), date(2024, 1, 2)),
    (2, date.today() - timedelta(days=5), None),
], ids=["all-accounts", "one-account", "under-20-days"])
def test_default_dates(app, state, tmp_path, selection, second_deposit, first_day):
    """Single dates start as today; periods run from the first operation of the accounts analysed to today.

    A second account makes its first deposit on `second_deposit`. On
    01-06-2023 it is before the test account's first operation (02-01-2024),
    so the period starts there only with all accounts. Five days ago is too
    short a period, so the start is left empty. The rolling correlation always
    leaves the start empty, for the two tickers.
    """
    idx = state.add_broker("Second Broker")
    state.commit(idx, _replay([deposit(second_deposit, 1000)], tmp_path / "second"))
    state.analysis_acc_idx = selection
    view = AnalysisView(app)
    view.build()
    tools = {type(tab.tool): tab.tool for tab in view.tabs}
    today = date.today()

    assert tools[AllocationTool].date.value == tools[SummaryTool].date.value == today
    for tool in (CorrelationTool, DrawdownTool):
        assert (tools[tool].start.value, tools[tool].end.value) == (first_day, today)

    correlation = tools[CorrelationTool]
    correlation.kind.value = "rolling"
    correlation.kind.on_change(None)
    assert (correlation.start.value, correlation.end.value) == (None, today)
