"""Tests for the inputs of the Analysis tools: their default dates, the checks on dates, tickers,
windows and the VaR settings, the Allocation tool calculating by itself (it has no Calculate button),
and the Statistics tool's two cards (chart and figures) sharing what they calculate.

A refused input shows its message, and the calculation doesn't start.
"""

from datetime import date, timedelta
from types import SimpleNamespace

import flet as ft
import flet_charts as fch
import pytest
from conftest import find_controls, snack_texts
from test_ledger_snapshots import _replay, deposit

from services import analysis_service
from views.analysis_view import AllocationTool, AnalysisView, CorrelationTool, DrawdownTool, SummaryTool, VarTool

TOMORROW = date.today() + timedelta(days=1)
ROLLING = {"start": date(2024, 1, 2), "end": date(2024, 6, 3), "kind": "rolling",
           "asset1": "AAA.MI", "asset2": "BBB.MI"}


@pytest.mark.parametrize("tool, inputs, message", [
    (SummaryTool, {"date": None}, "Date is missing"),
    (SummaryTool, {"date": TOMORROW}, "Cannot insert future dates"),
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
], ids=["summary-no-date", "summary-future", "correlation-no-end",
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

    assert tools[SummaryTool].date.value == today
    for tool in (CorrelationTool, DrawdownTool):
        assert (tools[tool].start.value, tools[tool].end.value) == (first_day, today)

    correlation = tools[CorrelationTool]
    correlation.kind.value = "rolling"
    correlation.kind.on_change(None)
    assert (correlation.start.value, correlation.end.value) == (None, today)


def test_allocation_calculates_as_soon_as_it_is_shown(app, page, state, monkeypatch):
    """The Allocation tab starts calculating when shown, so it opens on the pie instead of an empty tab.

    It starts when the screen opens on it and when the user switches to it, but
    not a second time while its result is still coming. The other tools wait for Calculate.
    """
    started = []
    monkeypatch.setattr(page, "run_thread", lambda fn, *args: started.append(fn))

    def show(index):
        """Switch the Analysis screen to tab `index`, as tapping its label does."""
        view._on_tab_change(SimpleNamespace(control=SimpleNamespace(selected_index=index)))

    state.analysis_tab_index = 0
    AnalysisView(app).build()
    assert len(started) == 1  # opened on Allocation

    state.analysis_tab_index = 1
    view = AnalysisView(app)
    view.build()
    assert len(started) == 1  # opened on Statistics
    show(0)
    assert len(started) == 2  # switched to Allocation
    show(1)
    show(0)
    assert len(started) == 2  # back on Allocation before its result arrived


def test_allocation_recalculates_when_another_split_is_picked(app, page, state, monkeypatch):
    """Picking "Sector" in the dropdown calculates the sectors straight away: the tab has no Calculate button.

    The dropdown is greyed out while a result is coming, so the user can't
    start a second calculation whose older result could arrive last.
    """
    started = []
    monkeypatch.setattr(page, "run_thread", lambda fn, *args: started.append(fn))
    monkeypatch.setattr(analysis_service, "compute_allocation", lambda accounts, day: {"Cash": 100.0})
    monkeypatch.setattr(analysis_service, "compute_sector_allocation",
                        lambda accounts, day: ({"technology": 60.0}, 100.0))
    state.analysis_tab_index = 0
    view = AnalysisView(app)
    view.build()
    [tab] = [tab for tab in view.tabs if isinstance(tab.tool, AllocationTool)]
    dropdown = tab.tool.group
    assert dropdown.disabled  # the asset classes are being calculated
    started.pop()()
    assert not dropdown.disabled

    dropdown.value = "sector"
    dropdown.on_select(None)

    assert dropdown.disabled and tab.result.controls == []
    started.pop()()
    texts = [text.value for text in find_controls(tab.result, ft.Text)]
    assert "Stocks and equity ETFs: 60.00€ of 100.00€ (60.0%)" in texts
    assert not dropdown.disabled


def test_statistics_chart_and_figures_download_the_price_history_once(app, page, state, monkeypatch):
    """Each Statistics card shows only its own result, and the slow price history is downloaded once for both.

    The figures shown after the chart reuse its history, and match those
    calculated from scratch. Going back to the chart downloads nothing; another
    day does. The cards are greyed out while a result is coming, so a second
    one can't be started and then be replaced by the first, arriving late.
    """
    started = []
    monkeypatch.setattr(page, "run_thread", lambda fn, *args: started.append(fn))
    downloads = []
    real_history = analysis_service.portfolio_history
    monkeypatch.setattr(analysis_service, "portfolio_history",
                        lambda *args: downloads.append(args) or real_history(*args))

    def statistics_tab():
        """A freshly built Analysis screen's Statistics tab, set on 31-12-2024, and its two cards."""
        view = AnalysisView(app)
        view.build()
        [tab] = [tab for tab in view.tabs if isinstance(tab.tool, SummaryTool)]
        tab.tool.date.value = date(2024, 12, 31)
        return tab, *find_controls(tab.content, ft.Card)

    def press(tab, card):
        """Tap `card`, check the cards are greyed out until its result arrives, and return what is then shown."""
        [cards] = [row for row in find_controls(tab.content, ft.Row) if card in row.controls]
        card.content.on_click(None)
        assert cards.disabled
        started.pop()()
        assert not cards.disabled
        return {"chart": any(find_controls(tab.result, fch.LineChart)),
                "texts": [text.value for text in find_controls(tab.result, ft.Text)],
                "export": tab.export_row.visible}

    tab, chart_card, figures_card = statistics_tab()
    chart = press(tab, chart_card)
    assert chart["chart"] and chart["export"] and len(downloads) == 1
    assert not any("Portfolio total" in text for text in chart["texts"])

    figures = press(tab, figures_card)
    assert not figures["chart"] and not figures["export"]
    assert any("Portfolio total" in text for text in figures["texts"])
    assert len(downloads) == 1  # the chart's history was reused

    assert press(tab, chart_card) == chart
    assert len(downloads) == 1

    tab.tool.date.value = date(2024, 11, 29)
    press(tab, chart_card)
    assert len(downloads) == 2

    tab, _, figures_card = statistics_tab()
    assert press(tab, figures_card)["texts"] == figures["texts"]  # calculated from scratch, same figures
    assert len(downloads) == 3
