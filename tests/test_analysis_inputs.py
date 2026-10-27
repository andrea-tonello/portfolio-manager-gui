"""Tests for the inputs of the Analysis tools: their default dates, the checks on dates, tickers,
windows and the VaR settings, the tabs that calculate as soon as they are shown (Allocation, which
has no Calculate button, recalculates by itself too), and the Statistics tool's two cards (chart
and figures) sharing what they calculate.

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
    (SummaryTool, {"start": date(2024, 1, 2), "end": None}, "Date is missing"),
    (SummaryTool, {"start": date(2024, 1, 2), "end": TOMORROW}, "Cannot insert future dates"),
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
    """Periods run from the first operation of the accounts analysed to today.

    A second account makes its first deposit on `second_deposit`. On
    01-06-2023 it is before the test account's first operation (02-01-2024),
    so the period starts there only with all accounts. Five days ago is too
    short a period, so the start is left empty, except for Statistics, whose
    figures make sense from the first day. The rolling correlation always
    leaves the start empty, for the two tickers.
    """
    idx = state.add_broker("Second Broker")
    state.commit(idx, _replay([deposit(second_deposit, 1000)], tmp_path / "second"))
    state.analysis_acc_idx = selection
    view = AnalysisView(app)
    view.build()
    tools = {type(tab.tool): tab.tool for tab in view.tabs}
    today = date.today()

    statistics = tools[SummaryTool]
    assert (statistics.start.value, statistics.end.value) == (first_day or second_deposit, today)
    for tool in (CorrelationTool, DrawdownTool):
        assert (tools[tool].start.value, tools[tool].end.value) == (first_day, today)

    correlation = tools[CorrelationTool]
    correlation.kind.value = "rolling"
    correlation.kind.on_change(None)
    assert (correlation.start.value, correlation.end.value) == (None, today)


def test_date_pickers_start_at_the_first_operation_even_in_a_short_history(app, page, state, tmp_path):
    """The Performance and Drawdown start calendars offer no day before the first operation, here five days ago.

    Under 20 days of history the Drawdown start is left empty (too short a
    period to fill in), but its picker still starts at the first operation.
    """
    first = date.today() - timedelta(days=5)
    idx = state.add_broker("Second Broker")
    state.commit(idx, _replay([deposit(first, 1000)], tmp_path / "second"))
    state.analysis_acc_idx = idx
    view = AnalysisView(app)
    view.build()
    tools = {type(tab.tool): tab.tool for tab in view.tabs}

    for tool in (tools[SummaryTool], tools[DrawdownTool]):
        tool.dates.button.on_click(None)
        start_row = page.dialogs[-1].content.controls[0]
        start_row.controls[1].on_click(None)  # the start's calendar button, in the range's dialog
        assert page.dialogs[-1].first_date.date() == first


def test_tabs_calculate_as_soon_as_they_are_shown(app, page, state, monkeypatch):
    """Allocation, Performance, Drawdown and VaR start calculating when shown, so they don't open on an empty tab.

    They start when the screen opens on them and when the user switches to
    them, but not a second time while their result is still coming.
    Performance shows its chart over the whole history (MAX). Correlation
    waits for Calculate.
    """
    started = []
    monkeypatch.setattr(page, "run_thread", lambda fn, *args: started.append(fn))

    def show(index):
        """Switch the Analysis screen to tab `index`, as tapping its label does."""
        view._on_tab_change(SimpleNamespace(control=SimpleNamespace(selected_index=index)))

    state.analysis_tab_index = 0
    view = AnalysisView(app)
    view.build()
    assert len(started) == 1  # opened on Allocation

    for index, calculates in [(1, True), (2, False), (3, True), (4, True)]:
        before = len(started)
        show(index)
        assert len(started) == before + calculates, type(view.tabs[index].tool).__name__
    show(0)
    show(1)
    assert len(started) == 4  # back on tabs whose results are still coming

    started[1]()  # Performance's calculation
    assert any(find_controls(view.tabs[1].result, fch.LineChart))


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
    """Each Performance card shows only its own result, and the slow price history is downloaded once for both.

    The figures shown after the chart reuse its history, and match those
    calculated from scratch. Going back to the chart downloads nothing; another
    day does, through the Calculate icon button, which shows the card last
    picked again. Only the card whose result is shown is outlined. The cards
    are greyed out while a result is coming, so another one can't be started
    and then be replaced by the first, arriving late.
    """
    started = []
    monkeypatch.setattr(page, "run_thread", lambda fn, *args: started.append(fn))
    downloads = []
    real_history = analysis_service.portfolio_history
    monkeypatch.setattr(analysis_service, "portfolio_history",
                        lambda *args: downloads.append(args) or real_history(*args))

    def statistics_tab():
        """A freshly built Analysis screen's Statistics tab, from the first operation to 31-12-2024, and its two cards."""
        view = AnalysisView(app)
        view.build()
        [tab] = [tab for tab in view.tabs if isinstance(tab.tool, SummaryTool)]
        tab.tool.end.value = date(2024, 12, 31)
        return tab, *find_controls(tab.content, ft.Card)

    def press(tab, card, button=None):
        """Tap `card` (or `button`), check the cards are greyed out until the result arrives; return what is shown."""
        [cards] = [row for row in find_controls(tab.content, ft.Row) if card in row.controls]
        (button or card.content).on_click(None)
        assert cards.disabled
        started.pop()()
        assert not cards.disabled
        assert [other.content.border is not None for other in cards.controls] == [other is card for other in cards.controls]
        return {"chart": any(find_controls(tab.result, fch.LineChart)),
                "texts": [text.value for text in find_controls(tab.result, ft.Text)],
                "export": tab.export_row.visible}

    tab, chart_card, figures_card = statistics_tab()
    chart = press(tab, chart_card)
    assert chart["chart"] and chart["export"] and len(downloads) == 1
    assert not any("NAV (on" in text for text in chart["texts"])

    figures = press(tab, figures_card)
    assert not figures["chart"] and not figures["export"]
    assert any("NAV (on" in text for text in figures["texts"])
    assert len(downloads) == 1  # the chart's history was reused

    assert press(tab, chart_card) == chart
    assert len(downloads) == 1

    tab.tool.end.value = date(2024, 11, 29)
    assert press(tab, chart_card, button=tab.tool.calculate_button)["chart"]  # the chart, for the new day
    assert len(downloads) == 2

    tab, _, figures_card = statistics_tab()
    assert press(tab, figures_card)["texts"] == figures["texts"]  # calculated from scratch, same figures
    assert len(downloads) == 3


def test_statistics_show_the_figures_of_the_accounts_picked_only(app, page, state, tmp_path, monkeypatch):
    """The figures say which accounts they are for, and show only theirs.

    With all accounts picked, only their total is shown, not each account's
    figures before it. Both list what is held (BBB.MI, in the test account).
    A second account holding just 1000€ of cash makes the total 1000€ more.
    """
    monkeypatch.setattr(page, "run_thread", lambda fn, *args: fn(*args))
    idx = state.add_broker("Second Broker")
    state.commit(idx, _replay([deposit(date(2024, 1, 2), 1000)], tmp_path / "second"))

    def figures(selection):
        """Show the figures on 31-12-2024 with `selection` picked (None: all accounts); return (header, figures)."""
        state.analysis_acc_idx = selection
        view = AnalysisView(app)
        view.build()
        [tab] = [tab for tab in view.tabs if isinstance(tab.tool, SummaryTool)]
        tab.tool.end.value = date(2024, 12, 31)
        _, figures_card = find_controls(tab.content, ft.Card)
        figures_card.content.on_click(None)
        return [text.value for text in find_controls(tab.result, ft.Text)]

    def nav(figures):
        """The NAV written in `figures`, e.g. 10088.12 from "NAV (on 31-12-2024): 10088.12€"."""
        return float(figures.split("NAV (on 31-12-2024): ")[1].split("€")[0])

    header, all_figures = figures(None)
    assert header == "Account: all accounts"
    assert all_figures.count("NAV") == 1 and "Assets held on 31-12-2024" in all_figures
    assert all_figures.count("BBB.MI") == 1

    header, one_figures = figures(1)
    assert header == "Account: Test Broker"
    assert one_figures.count("NAV") == 1 and "Assets held on 31-12-2024" in one_figures
    assert one_figures.count("BBB.MI") == 1

    assert nav(all_figures) - nav(one_figures) == pytest.approx(1000)
