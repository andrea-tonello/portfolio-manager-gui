"""The Analysis tab: five tools (allocation, statistics, correlation, drawdown, Value at Risk) on one or all accounts.

Every tool sits in the same frame, AnalysisTab: its inputs, the Calculate
button, a spinner, the result and, when the result has data behind it, a
button exporting that data as CSV. Each tool, a subclass of AnalysisTool,
only says what is particular to it. Adding a tool means writing one class
and listing it in TOOLS.
"""

from datetime import date

import flet as ft
import numpy as np
import pandas as pd

from components.background import run_in_background
from components.charts import (
    chart_allocation,
    chart_correlation_heatmap,
    chart_drawdown,
    chart_rolling_correlation,
    chart_summary,
    chart_var_mc,
)
from components.date_field import DateField, date_range_fields
from components.file_export import get_file_picker, save_bytes
from components.focus_chain import chain_focus, scroll_into_view_on_focus
from components.inputs import DECIMAL_INPUT_FILTER, account_selector, rounded_text_field
from components.snack import error_message, show_snack
from components.ticker_search import TickerSearchField
from domain.errors import ValidationError
from domain.ledger import get_pf_date
from services import analysis_service
from services.validation import parse_positive, validate_date, validate_date_range
from utils.constants import DATE_FORMAT

_INT_FILTER = ft.NumbersOnlyInputFilter()


def calculate_button(t, on_click) -> ft.FilledButton:
    """Return the "Calculate »" button that each analysis tab puts under its inputs."""
    return ft.FilledButton(
        ft.Row([
            ft.Text(t.get("components.calculate")),
            ft.Icon(ft.Icons.KEYBOARD_DOUBLE_ARROW_RIGHT),
        ]),
        on_click=on_click,
        style=ft.ButtonStyle(padding=ft.Padding.symmetric(horizontal=32, vertical=18)),
    )


def _csv_bytes(df, index=False):
    """Return `df` as the bytes of a UTF-8 CSV file, ready to save."""
    return df.to_csv(index=index).encode("utf-8")


def _accounts_to_analyse(state):
    """Return the accounts to analyse: every account, or only the one selected at the top."""
    if state.analysis_acc_idx is None:
        return [state.accounts[idx] for idx in sorted(state.accounts)]
    account = state.get_account(state.analysis_acc_idx)
    return [account] if account is not None else []


class AnalysisTool:
    """One tool of the Analysis tab. Subclasses fill in its inputs, its calculation and how its result looks.

    AnalysisTab uses a tool in this order: build_inputs() once; then, each time
    Calculate is pressed, read_inputs(), compute() in a background thread,
    and render() and export() on what compute() returned.
    """

    title_key = ""      # translation key of the tool's tab label
    glossary_page = 0   # glossary page the info button opens while the tool is shown
    scroll_prefix = ""  # start of its inputs' scroll keys, unique on the screen

    def __init__(self, page, translator, first_day=None):
        """Keep the page (date pickers and ticker search need it), the translator, and the default start of a period.

        `first_day` is the day of the first operation in the accounts analysed (None before any).
        """
        self.page = page
        self.t = translator
        self.first_day = first_day

    def build_inputs(self, clear_result) -> list[ft.Control]:
        """Create the input controls and return them in screen order.

        `clear_result` empties the result area: call it when an input change
        makes the result shown meaningless.
        """
        raise NotImplementedError

    def text_fields(self) -> list:
        """The text boxes, in screen order, that scroll into view when focused."""
        return []

    def read_inputs(self):
        """Check the inputs and return what compute() needs; raise ValidationError for the first problem."""
        raise NotImplementedError

    def compute(self, accounts, inputs):
        """Calculate the result for `accounts` (runs in a background thread); may raise ValidationError."""
        raise NotImplementedError

    def render(self, result, inputs) -> list[ft.Control]:
        """Return the controls showing `result`."""
        raise NotImplementedError

    def export(self, result, inputs):
        """Return (file name, CSV bytes) of the data behind `result`, or None when there is nothing to export."""
        return None


class AnalysisTab:
    """The frame shared by every Analysis tool: inputs, Calculate button, spinner, result and CSV export."""

    def __init__(self, page, state, tool, save_csv):
        """Frame `tool`; `save_csv(file_name, csv_bytes)` is how its export is saved (AnalysisView._save_csv)."""
        self.page = page
        self.state = state
        self.tool = tool
        self._save_csv = save_csv
        self._export = None  # (file name, CSV bytes) of the result shown, when it can be exported

    def build(self) -> ft.Control:
        """Create the tab's controls around the tool's inputs and return its layout."""
        t = self.state.translator
        inputs = self.tool.build_inputs(self.clear)
        self.loading = ft.ProgressRing(visible=False, width=30, height=30)
        self.result = ft.Column([], spacing=12)
        self.export_row = ft.Row([
            ft.Button(t.get("analysis.export_plot_csv"), icon=ft.Icons.ASSESSMENT,
                      on_click=lambda _: self.page.run_task(self._on_export)),
        ], visible=False)

        col = ft.Column([
            *inputs,
            ft.Row([ft.Container(width=5), self.loading]),
            ft.Row([calculate_button(t, self.submit)], alignment=ft.MainAxisAlignment.CENTER),
            self.result,
            self.export_row,
            ft.Container(height=20),
        ], spacing=12, scroll=ft.ScrollMode.AUTO)

        scroll_into_view_on_focus(col, self.tool.text_fields(), prefix=self.tool.scroll_prefix)

        self.content = ft.Container(content=col, padding=10, expand=True)
        return self.content

    def submit(self, e):
        """Check the inputs, then calculate and show the result in the background."""
        t = self.state.translator
        try:
            inputs = self.tool.read_inputs()
        except ValidationError as ex:
            show_snack(self.page, error_message(t, ex), error=True)
            return

        accounts = _accounts_to_analyse(self.state)
        if not accounts:
            show_snack(self.page, t.get("operations.select_account"), error=True)
            return

        def calculate():
            """Run the tool's calculation and show its result; a failed one leaves the result area empty."""
            try:
                result = self.tool.compute(accounts, inputs)
            except Exception:
                self.clear()
                raise
            self._show(self.tool.render(result, inputs), self.tool.export(result, inputs))

        run_in_background(self.page, t, calculate, loading=self.loading)

    def clear(self):
        """Empty the result area and hide the export button."""
        self._show([], None)

    def _show(self, controls, export):
        """Put the result's controls in the result area, and offer `export` (file name, CSV bytes) if given."""
        self.result.controls = controls
        self._export = export
        self.export_row.visible = export is not None

    async def _on_export(self):
        """Let the user save the data behind the result shown."""
        if self._export is not None:
            await self._save_csv(*self._export)


# ── Allocation ───────────────────────────────────────────────────────

class AllocationTool(AnalysisTool):
    """How the portfolio is split between cash, stocks and the kinds of ETF on a date, as a pie chart."""

    title_key = "analysis.op_allocation"
    glossary_page = 2
    scroll_prefix = "alloc"

    def build_inputs(self, clear_result):
        """A date, today to start with."""
        self.date = DateField(self.page, self.t.get("components.pick_date"), self.t.get("components.date_format_hint"))
        self.date.value = date.today()
        return [ft.Container(height=5), self.date.control]

    def text_fields(self):
        """The date box."""
        return [self.date.field]

    def read_inputs(self):
        """The date, if it is given and not in the future."""
        return validate_date(self.date.value)

    def compute(self, accounts, day):
        """The allocation of `accounts` on `day`."""
        return analysis_service.compute_allocation(accounts, day)

    def render(self, allocation, day):
        """The pie chart and its legend."""
        return [chart_allocation(self.t, allocation)]


# ── Statistics ───────────────────────────────────────────────────────

def _format_common_stats(stats, t, dt_str):
    """The lines an account's statistics and the portfolio's have in common: NAV, cash, assets, committed cash, P&L."""
    text = t.get("analysis.summary.nav", dt=dt_str, nav=stats["nav"])
    text += "\n" + t.get("analysis.summary.cash", current_liq=stats["current_liq"])
    text += "\n" + t.get("analysis.summary.assets_value", asset_value=stats["asset_value"])
    text += "\n" + t.get("analysis.summary.historic_cash", historic_liq=stats["historic_liq"])
    text += "\n" + t.get("analysis.summary.pl", pl=stats["pl"])
    text += "\n" + t.get("analysis.summary.pl_unrealized", pl_unrealized=stats["pl_unrealized"])
    return text


def _history(result):
    """The portfolio's value over time from a statistics result, or None when there is none to draw."""
    pf_history = result.get("pf_history")
    if pf_history is not None and not pf_history.empty and result.get("min_date") is not None:
        return pf_history
    return None


class SummaryTool(AnalysisTool):
    """Statistics on a date: each account's and the whole portfolio's value, P&L and returns, plus a chart."""

    title_key = "analysis.op_statistics"
    glossary_page = 3
    scroll_prefix = "sum"

    def build_inputs(self, clear_result):
        """A date, today to start with."""
        self.date = DateField(self.page, self.t.get("components.pick_date"), self.t.get("components.date_format_hint"))
        self.date.value = date.today()
        return [ft.Container(height=5), self.date.control]

    def text_fields(self):
        """The date box."""
        return [self.date.field]

    def read_inputs(self):
        """The date, if it is given and not in the future."""
        return validate_date(self.date.value)

    def compute(self, accounts, day):
        """The statistics of `accounts` on `day`."""
        return analysis_service.compute_summary(accounts, day, day.strftime(DATE_FORMAT))

    def render(self, result, day):
        """One text per account, one in bold for the portfolio, and the chart of its value over time."""
        t = self.t
        dt_str = day.strftime(DATE_FORMAT)
        texts = []

        for acc in result["accounts"]:
            acc_text = f"\n{t.get('analysis.summary.account_literal')}: {acc['broker_name']}"
            acc_text += _format_common_stats(acc, t, dt_str)
            if not np.isnan(acc["xirr_full"]):
                acc_text += "\n" + t.get("analysis.summary.return_account",
                                         xirr_full=acc["xirr_full"], xirr_ann=acc["xirr_ann"])

            if acc["positions"]:
                acc_text += "\n" + t.get("analysis.summary.assets_recap.held_assets", dt=dt_str)
                for pos in acc["positions"]:
                    acc_text += f"        {pos['ticker']}\n"
                    acc_text += f"        {t.get('analysis.summary.assets_recap.avg_price')}{pos['pmc']:.4f}\n"
                    acc_text += f"        {t.get('analysis.summary.assets_recap.current_price')}{pos['price']:.4f}\n"
                    acc_text += f"        {t.get('analysis.summary.assets_recap.value')}{pos['value']:.2f}\n"

            texts.append(ft.Text(acc_text, size=12, selectable=True))

        pf = result["portfolio"]
        pf_text = f"\n{t.get('analysis.summary.portfolio_literal')}"
        pf_text += _format_common_stats(pf, t, dt_str)
        if pf.get("has_positions"):
            pf_text += "\n" + t.get("analysis.summary.return_portfolio",
                                     xirr_full=pf["xirr_full"], xirr_ann=pf["xirr_ann"],
                                     twrr_full=pf["twrr_full"], twrr_ann=pf["twrr_ann"])
            pf_text += t.get("analysis.summary.volatility", volatility=pf["volatility"])
            pf_text += "\n" + t.get("analysis.summary.sharpe_ratio", sharpe_ratio=pf["sharpe_ratio"])
        texts.append(ft.Text(pf_text, size=12, weight=ft.FontWeight.BOLD, selectable=True))

        controls = [ft.Column(texts, spacing=5)]
        pf_history = _history(result)
        if pf_history is not None:
            controls.append(chart_summary(t, pf_history))
        return controls

    def export(self, result, day):
        """The portfolio's value over time."""
        pf_history = _history(result)
        return None if pf_history is None else ("Portfolio History.csv", _csv_bytes(pf_history))


# ── Correlation ──────────────────────────────────────────────────────

class CorrelationTool(AnalysisTool):
    """How the held assets moved together over a period: all of them at once, or two tickers over a rolling window."""

    title_key = "analysis.op_correlation"
    glossary_page = 4
    scroll_prefix = "corr"

    def build_inputs(self, clear_result):
        """The kind of correlation, a start and end date, and for the rolling one two tickers and a window.

        The period starts as the whole history: from the first operation to today. The
        rolling correlation leaves the start empty instead, to be chosen for the two tickers.
        """
        t = self.t

        def on_kind_change(e):
            """Show the rolling correlation's fields only for it, set its default start, and drop the old result."""
            rolling = (self.kind.value == "rolling")
            self.rolling_fields.visible = rolling
            self.start.value = None if rolling else self.first_day
            clear_result()
            self.page.update()

        self.kind = ft.RadioGroup(
            value="simple",
            content=ft.Column([
                ft.Radio(value="simple", label=t.get("analysis.corr.simple")),
                ft.Radio(value="rolling", label=t.get("analysis.corr.rolling")),
            ], spacing=0),
            on_change=on_kind_change,
        )

        self.start, self.end = date_range_fields(
            self.page, t.get("analysis.corr.start_dt").strip(), t.get("analysis.corr.end_dt").strip(),
            t.get("components.date_format_hint"),
        )
        self.start.value, self.end.value = self.first_day, date.today()

        self.asset1 = TickerSearchField(
            self.page,
            label=t.get("analysis.corr.asset1"),
            col={"xs": 12, "md": 4})
        self.asset2 = TickerSearchField(
            self.page,
            label=t.get("analysis.corr.asset2"),
            col={"xs": 12, "md": 4})
        self.window = rounded_text_field(
            label=t.get("analysis.corr.window"),
            keyboard_type=ft.KeyboardType.NUMBER, input_filter=_INT_FILTER, value="100",
            col={"xs": 12, "md": 4})

        self.rolling_fields = ft.ResponsiveRow(
            [self.asset1.control, self.asset2.control, self.window],
            visible=False,
        )

        # Chain on_submit for keyboard "next field" navigation
        chain_focus([
            self.start.field,
            self.end.field,
            (self.asset1.field, self.rolling_fields),
            (self.asset2.field, self.rolling_fields),
            (self.window, self.rolling_fields),
        ])

        return [self.kind, ft.Container(height=5), self.start.control, self.end.control, self.rolling_fields]

    def text_fields(self):
        """The dates, the tickers and the window."""
        return [self.start.field, self.end.field, self.asset1.field, self.asset2.field, self.window]

    def read_inputs(self):
        """(start, end, asset1, asset2, window); the last three are None for the correlation of all assets."""
        start, end = validate_date_range(self.start.value, self.end.value)
        if self.kind.value != "rolling":
            return start, end, None, None, None
        asset1 = self.asset1.value.strip()
        asset2 = self.asset2.value.strip()
        if not asset1 or not asset2:
            raise ValidationError("analysis.corr.ticker_error")
        window = parse_positive(self.window.value, "analysis.corr.window_error", integer=True)
        return start, end, asset1, asset2, window

    def compute(self, accounts, inputs):
        """The correlation matrix of the held assets, or the rolling correlation of the two tickers."""
        start, end, asset1, asset2, window = inputs
        return analysis_service.compute_correlation(
            accounts, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"), asset1, asset2, window,
        )

    def render(self, result, inputs):
        """The heatmap (or why there is none), or the rolling correlation chart."""
        _, _, asset1, asset2, window = inputs
        if asset1 is None:
            corr_matrix = result.get("correlation_matrix")
            if corr_matrix is None:
                return [ft.Text(self.t.get("analysis.corr.simple_error"), size=14)]
            return [chart_correlation_heatmap(self.t, corr_matrix)]
        rolling_corr = result.get("rolling_corr")
        if rolling_corr is None or rolling_corr.empty:
            return []
        return [chart_rolling_correlation(self.t, rolling_corr, window, asset1, asset2)]

    def export(self, result, inputs):
        """The correlation matrix, or the rolling correlation day by day."""
        if inputs[2] is None:
            corr_matrix = result.get("correlation_matrix")
            return None if corr_matrix is None else ("Correlation Matrix.csv", _csv_bytes(corr_matrix, index=True))
        rolling_corr = result.get("rolling_corr")
        if rolling_corr is None or rolling_corr.empty:
            return None
        df = pd.DataFrame({"Date": rolling_corr.index, "Correlation": rolling_corr.values})
        return "Rolling Correlation.csv", _csv_bytes(df)


# ── Drawdown ─────────────────────────────────────────────────────────

class DrawdownTool(AnalysisTool):
    """The portfolio's largest fall from a peak (maximum drawdown) over a period, with its chart."""

    title_key = "analysis.op_drawdown"
    glossary_page = 5
    scroll_prefix = "dd"

    def build_inputs(self, clear_result):
        """A start and end date, the whole history to start with: from the first operation to today."""
        t = self.t
        self.start, self.end = date_range_fields(
            self.page, t.get("analysis.drawdown.start_dt").strip(), t.get("analysis.drawdown.end_dt").strip(),
            t.get("components.date_format_hint"),
        )
        self.start.value, self.end.value = self.first_day, date.today()
        # Chain on_submit for keyboard "next field" navigation
        chain_focus([self.start.field, self.end.field])
        return [ft.Container(height=5), self.start.control, self.end.control]

    def text_fields(self):
        """The two date boxes."""
        return [self.start.field, self.end.field]

    def read_inputs(self):
        """(start, end), if both are given, not in the future, and start comes first."""
        return validate_date_range(self.start.value, self.end.value)

    def compute(self, accounts, inputs):
        """The drawdown over the period; refused when it covers fewer than 10 days of history."""
        result = analysis_service.compute_drawdown(accounts, *inputs)
        if result["has_data"] and len(result["pf_history"]) < 10:
            raise ValidationError("analysis.drawdown.min_range")
        return result

    def render(self, result, inputs):
        """The maximum drawdown and its chart, or why there is none."""
        if not result["has_data"]:
            return [ft.Text(self.t.get("analysis.drawdown.error"), size=14, selectable=True)]
        start, end = inputs
        text = self.t.get("analysis.drawdown.result", start_dt=start.strftime(DATE_FORMAT),
                          end_dt=end.strftime(DATE_FORMAT), mdd=result["mdd"] * 100)
        return [
            ft.Text(text, size=14, selectable=True),
            chart_drawdown(self.t, result["pf_history"], result["drawdown"], result["mdd"]),
        ]

    def export(self, result, inputs):
        """The portfolio's value day by day, with its drawdown in percent."""
        if not result["has_data"]:
            return None
        pf = result["pf_history"].copy()
        pf["Drawdown %"] = result["drawdown"].values * 100
        return "Drawdown.csv", _csv_bytes(pf)


# ── Value at Risk ────────────────────────────────────────────────────

class VarTool(AnalysisTool):
    """Value at Risk: the loss not exceeded with the given confidence over the next days, by Monte Carlo simulation."""

    title_key = "analysis.op_var"
    glossary_page = 6
    scroll_prefix = "var"

    def build_inputs(self, clear_result):
        """The confidence level (e.g. 0.99) and the number of days ahead."""
        t = self.t
        self.ci = rounded_text_field(
            label=t.get("analysis.var.ci"),
            keyboard_type=ft.KeyboardType.NUMBER, input_filter=DECIMAL_INPUT_FILTER, value="0.99",
            col={"xs": 6, "md": 6})
        self.days = rounded_text_field(
            label=t.get("analysis.var.days"),
            keyboard_type=ft.KeyboardType.NUMBER, input_filter=_INT_FILTER, value="10",
            col={"xs": 6, "md": 6})
        # Chain on_submit for keyboard "next field" navigation
        chain_focus([self.ci, self.days])
        return [ft.Container(height=5), ft.ResponsiveRow([self.ci, self.days])]

    def text_fields(self):
        """The confidence level and the days."""
        return [self.ci, self.days]

    def read_inputs(self):
        """(confidence, days): a confidence strictly between 0 and 1, and a whole number of days above 0."""
        ci = parse_positive(self.ci.value, "analysis.var.ci_error")
        if ci >= 1:
            raise ValidationError("analysis.var.ci_error")
        days = parse_positive(self.days.value, "analysis.var.days_error", integer=True)
        return ci, days

    def compute(self, accounts, inputs):
        """The simulated outcomes and the Value at Risk."""
        return analysis_service.compute_var_mc(accounts, *inputs)

    def render(self, result, inputs):
        """The Value at Risk and the histogram of the simulated outcomes, or why there is none."""
        if not result["has_positions"]:
            return [ft.Text(self.t.get("analysis.var.error"), size=14, selectable=True)]
        ci, days = inputs
        return [
            ft.Text(self.t.get("analysis.var.result", ci=ci, days=days, var=result["var"]), size=14, selectable=True),
            chart_var_mc(self.t, result["scenario_return"], result["var"], ci),
        ]

    def export(self, result, inputs):
        """The simulated outcomes."""
        if not result["has_positions"]:
            return None
        return "VaR Monte Carlo.csv", _csv_bytes(pd.DataFrame({"Scenario Return": result["scenario_return"]}))


# The tools, in tab order. The info button opens the glossary page of the one shown.
TOOLS = (AllocationTool, SummaryTool, CorrelationTool, DrawdownTool, VarTool)


class AnalysisView:
    def __init__(self, app):
        """Build the Analysis tab for the controller's page and current state."""
        self.app = app
        self.page = app.page
        self.state = app.state

    def build(self) -> ft.Control:
        t = self.state.translator
        if not self.state.brokers:
            return ft.Text(t.get("home.no_account"), size=16)

        self.file_picker = get_file_picker(self.page)  # for the CSV exports
        # Periods start on the first operation of the accounts analysed (the earliest of their first
        # operations), unless that is less than 20 days ago: too short a period, the user picks the start.
        today = date.today()
        first_days = [first.date() for account in _accounts_to_analyse(self.state)
                      if (first := get_pf_date(account, today, today)[1]) is not None]
        first_day = min(first_days, default=None)
        if first_day is not None and (today - first_day).days < 20:
            first_day = None
        self.tabs = [AnalysisTab(self.page, self.state, tool(self.page, t, first_day), self._save_csv)
                     for tool in TOOLS]

        has_account = self.state.analysis_acc_idx is not None or len(self.state.accounts) > 0
        form_container = ft.Container(
            content=ft.Tabs(
                length=len(self.tabs),
                selected_index=self.state.analysis_tab_index,
                on_change=self._on_tab_change,
                content=ft.Column([
                    ft.TabBar(tabs=[ft.Tab(label=t.get(tab.tool.title_key)) for tab in self.tabs],
                              scrollable=True, splash_border_radius=ft.BorderRadius.only(top_left=10, top_right=10)),
                    ft.TabBarView(
                        controls=[tab.build() for tab in self.tabs],
                        expand=True,
                    ),
                ], expand=True),
                expand=True,
            ),
            disabled=not has_account, expand=True, width=800,
        )

        return ft.Row(
            controls=[
                ft.Column([
                    ft.Container(self._build_account_dropdown(), padding=ft.Padding.only(top=5, left=5, right=5)),
                    form_container,
                ],
                expand=True,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER)
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            expand=True,
        )

    def _build_account_dropdown(self) -> ft.Control:
        t = self.state.translator
        idx = self.state.analysis_acc_idx
        return account_selector(self.state, "all" if idx is None else str(idx), self._on_account_selected,
                                all_option=("all", t.get("analysis.all_accounts")))

    def _on_tab_change(self, e):
        self.state.analysis_tab_index = e.control.selected_index

    def _on_account_selected(self, e):
        val = e.control.value
        if val == "all":
            self.state.analysis_acc_idx = None
        else:
            self.state.analysis_acc_idx = int(val)
        self.app.refresh()

    async def _save_csv(self, file_name, csv_bytes):
        """Let the user save a chart's data as `file_name`, confirming once saved."""
        t = self.state.translator
        await save_bytes(self.page, self.file_picker, file_name, csv_bytes, "csv", t.get("transactions.export_success"))
