import io
import flet as ft
import numpy as np
import pandas as pd
from datetime import date

from components.background import run_in_background
from components.date_field import DateField, date_range_fields
from components.file_export import get_file_picker, save_bytes
from components.focus_chain import chain_focus, scroll_into_view_on_focus
from components.inputs import DECIMAL_INPUT_FILTER, account_selector, rounded_text_field
from components.snack import show_snack
from components.ticker_search import TickerSearchField
from services import analysis_service, chart_service
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

        # Data storage for CSV export
        self._sum_history = None
        self._corr_matrix = None
        self._rolling_corr = None
        self._dd_data = None
        self._var_data = None

        has_account = self.state.analysis_acc_idx is not None or len(self.state.accounts) > 0

        self.form_container = ft.Container(disabled=not has_account, expand=True, width=800)

        alloc_content = self._build_allocation_tab()
        summary_content = self._build_summary_tab()
        corr_content = self._build_correlation_tab()
        dd_content = self._build_drawdown_tab()
        var_content = self._build_var_tab()

        self.form_container.content = ft.Tabs(
            length=5,
            selected_index=self.state.analysis_tab_index,
            on_change=self._on_tab_change,
            content=ft.Column([
                ft.TabBar(tabs=[
                    ft.Tab(label=t.get("analysis.op_allocation")),
                    ft.Tab(label=t.get("analysis.op_statistics")),
                    ft.Tab(label=t.get("analysis.op_correlation")),
                    ft.Tab(label=t.get("analysis.op_drawdown")),
                    ft.Tab(label=t.get("analysis.op_var")),
                ], scrollable=True, splash_border_radius=ft.BorderRadius.only(top_left=10, top_right=10)),
                ft.TabBarView(
                    controls=[alloc_content, summary_content, corr_content, dd_content, var_content],
                    expand=True,
                ),
            ], expand=True),
            expand=True,
        )

        return ft.Row(
            controls=[
                ft.Column([
                    ft.Container(self._build_account_dropdown(), padding=ft.Padding.only(top=5, left=5, right=5)),
                    self.form_container,
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

    def _get_analysis_data(self):
        """Return the accounts to analyse: every account, or only the selected one."""
        s = self.state
        if s.analysis_acc_idx is None:
            return [s.accounts[idx] for idx in sorted(s.accounts)]
        account = s.get_account(s.analysis_acc_idx)
        return [account] if account is not None else []

    # ── Statistics Tab ────────────────────────────────────────────────

    def _build_summary_tab(self) -> ft.Control:
        t = self.state.translator
        self.sum_date = DateField(self.page, t.get("components.pick_date"), t.get("components.date_format_hint"))
        self.sum_loading = ft.ProgressRing(visible=False, width=30, height=30)
        self.sum_results = ft.Column([], spacing=5)
        self.sum_chart = ft.Container()
        self.sum_export_row = ft.Row([
            ft.Button(t.get("analysis.export_plot_csv"), icon=ft.Icons.ASSESSMENT,
                          on_click=lambda _: self.page.run_task(self._export_sum_csv)),
        ], visible=False)

        sum_submit_btn = calculate_button(t, self._submit_summary)

        col = ft.Column([
            ft.Container(height=5),
            self.sum_date.control,
            ft.Row([ft.Container(width=5), self.sum_loading]),
            ft.Row([sum_submit_btn], alignment=ft.MainAxisAlignment.CENTER),
            self.sum_results,
            self.sum_chart,
            self.sum_export_row,
            ft.Container(height=20),
        ], spacing=12, scroll=ft.ScrollMode.AUTO)

        scroll_into_view_on_focus(col, [self.sum_date.field], prefix="sum")

        return ft.Container(content=col, padding=10, expand=True)

    def _submit_summary(self, e):
        s = self.state
        t = s.translator
        if self.sum_date.value is None:
            show_snack(self.page, t.get("misc_errors.nodate"), error=True)
            return
        if self.sum_date.value > date.today():
            show_snack(self.page, t.get("misc_errors.date_future"), error=True)
            return

        data = self._get_analysis_data()
        if not data:
            show_snack(self.page, t.get("operations.select_account"), error=True)
            return

        def calculate():
            """Compute the statistics on the chosen date and show them."""
            ref_date = self.sum_date.value
            dt_str = ref_date.strftime(DATE_FORMAT)

            result = analysis_service.compute_summary(data, ref_date, dt_str)
            self._display_summary(result, dt_str)

        run_in_background(self.page, t, calculate, loading=self.sum_loading)

    def _display_summary(self, result, dt_str):
        t = self.state.translator
        controls = []

        for acc in result["accounts"]:
            acc_text = f"\n{t.get('analysis.summary.account_literal')}: {acc['broker_name']}"
            acc_text += t.get("analysis.summary.nav", dt=dt_str, nav=acc["nav"])
            acc_text += "\n" + t.get("analysis.summary.cash", current_liq=acc["current_liq"])
            acc_text += "\n" + t.get("analysis.summary.assets_value", asset_value=acc["asset_value"])
            acc_text += "\n" + t.get("analysis.summary.historic_cash", historic_liq=acc["historic_liq"])
            acc_text += "\n" + t.get("analysis.summary.pl", pl=acc["pl"])
            acc_text += "\n" + t.get("analysis.summary.pl_unrealized", pl_unrealized=acc["pl_unrealized"])
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

            controls.append(ft.Text(acc_text, size=12, selectable=True))

        pf = result["portfolio"]
        pf_text = f"\n{t.get('analysis.summary.portfolio_literal')}"
        pf_text += t.get("analysis.summary.nav", dt=dt_str, nav=pf["nav"])
        pf_text += "\n" + t.get("analysis.summary.cash", current_liq=pf["current_liq"])
        pf_text += "\n" + t.get("analysis.summary.assets_value", asset_value=pf["asset_value"])
        pf_text += "\n" + t.get("analysis.summary.historic_cash", historic_liq=pf["historic_liq"])
        pf_text += "\n" + t.get("analysis.summary.pl", pl=pf["pl"])
        pf_text += "\n" + t.get("analysis.summary.pl_unrealized", pl_unrealized=pf["pl_unrealized"])

        if pf.get("has_positions"):
            pf_text += "\n" + t.get("analysis.summary.return_portfolio",
                                     xirr_full=pf["xirr_full"], xirr_ann=pf["xirr_ann"],
                                     twrr_full=pf["twrr_full"], twrr_ann=pf["twrr_ann"])
            pf_text += t.get("analysis.summary.volatility", volatility=pf["volatility"])
            pf_text += "\n" + t.get("analysis.summary.sharpe_ratio", sharpe_ratio=pf["sharpe_ratio"])

        controls.append(ft.Text(pf_text, size=12, weight=ft.FontWeight.BOLD, selectable=True))

        self.sum_results.controls = controls

        pf_history = result.get("pf_history")
        min_date = result.get("min_date")
        if pf_history is not None and not pf_history.empty and min_date is not None:
            self.sum_chart.content = chart_service.chart_summary(self.state.translator, pf_history)
            self._sum_history = pf_history
            self.sum_export_row.visible = True
        else:
            self.sum_chart.content = None
            self._sum_history = None
            self.sum_export_row.visible = False

        self.page.update()

    # ── Correlation Tab ───────────────────────────────────────────────

    def _build_correlation_tab(self) -> ft.Control:
        t = self.state.translator

        self.corr_type = ft.RadioGroup(
            value="simple",
            content=ft.Column([
                ft.Radio(value="simple", label=t.get("analysis.corr.simple")),
                ft.Radio(value="rolling", label=t.get("analysis.corr.rolling")),
            ], spacing=0),
            on_change=self._on_corr_type_change,
        )

        self.corr_start, self.corr_end = date_range_fields(
            self.page, t.get("analysis.corr.start_dt").strip(), t.get("analysis.corr.end_dt").strip(),
            t.get("components.date_format_hint"),
        )

        self.corr_asset1 = TickerSearchField(
            self.page,
            label=t.get("analysis.corr.asset1"),
            col={"xs": 12, "md": 4})
        self.corr_asset2 = TickerSearchField(
            self.page,
            label=t.get("analysis.corr.asset2"),
            col={"xs": 12, "md": 4})
        self.corr_window = rounded_text_field(
            label=t.get("analysis.corr.window"),
            keyboard_type=ft.KeyboardType.NUMBER, input_filter=_INT_FILTER, value="100",
            col={"xs": 12, "md": 4})

        self.corr_rolling_fields = ft.ResponsiveRow(
            [self.corr_asset1.control, self.corr_asset2.control, self.corr_window],
            visible=False,
        )

        # Chain on_submit for keyboard "next field" navigation
        chain_focus([
            self.corr_start.field,
            self.corr_end.field,
            (self.corr_asset1.field, self.corr_rolling_fields),
            (self.corr_asset2.field, self.corr_rolling_fields),
            (self.corr_window, self.corr_rolling_fields),
        ])

        self.corr_loading = ft.ProgressRing(visible=False, width=30, height=30)
        self.corr_results = ft.Column([], spacing=5)
        self.corr_heatmap = ft.Container()
        self.corr_rolling_chart = ft.Container()
        self.corr_export_row = ft.Row([
            ft.Button(t.get("analysis.export_plot_csv"), icon=ft.Icons.ASSESSMENT,
                          on_click=lambda _: self.page.run_task(self._export_corr_csv)),
        ], visible=False)

        corr_submit_btn = calculate_button(t, self._submit_correlation)

        col = ft.Column([
            self.corr_type,
            ft.Container(height=5),
            self.corr_start.control,
            self.corr_end.control,
            self.corr_rolling_fields,
            ft.Row([ft.Container(width=5), self.corr_loading]),
            ft.Row([corr_submit_btn], alignment=ft.MainAxisAlignment.CENTER),
            self.corr_results,
            self.corr_heatmap,
            self.corr_rolling_chart,
            self.corr_export_row,
            ft.Container(height=20),
        ], spacing=12, scroll=ft.ScrollMode.AUTO)

        scroll_into_view_on_focus(col, [
            self.corr_start.field, self.corr_end.field, self.corr_asset1.field, self.corr_asset2.field,
            self.corr_window,
        ], prefix="corr")

        return ft.Container(content=col, padding=10, expand=True)

    def _on_corr_type_change(self, e):
        self.corr_rolling_fields.visible = (self.corr_type.value == "rolling")
        self.corr_results.controls = []
        self.corr_heatmap.content = None
        self.corr_rolling_chart.content = None
        self._corr_matrix = None
        self._rolling_corr = None
        self.corr_export_row.visible = False
        self.page.update()

    def _submit_correlation(self, e):
        s = self.state
        t = s.translator
        if self.corr_start.value is None or self.corr_end.value is None:
            show_snack(self.page, t.get("misc_errors.nodate"), error=True)
            return
        if self.corr_start.value > date.today() or self.corr_end.value > date.today():
            show_snack(self.page, t.get("misc_errors.date_future"), error=True)
            return
        if self.corr_start.value >= self.corr_end.value:
            show_snack(self.page, t.get("misc_errors.date_start_end"), error=True)
            return

        is_rolling = self.corr_type.value == "rolling"
        asset1 = asset2 = None
        window = None

        if is_rolling:
            asset1 = self.corr_asset1.value.strip()
            asset2 = self.corr_asset2.value.strip()
            if not asset1 or not asset2:
                show_snack(self.page, t.get("analysis.corr.ticker_error"), error=True)
                return
            try:
                window = int(self.corr_window.value)
                if window <= 0:
                    raise ValueError
            except (ValueError, TypeError):
                show_snack(self.page, t.get("analysis.corr.window_error"), error=True)
                return

        data = self._get_analysis_data()
        if not data:
            show_snack(self.page, t.get("operations.select_account"), error=True)
            return

        def calculate():
            """Compute the correlation over the chosen period and show it."""
            start_dt = self.corr_start.value.strftime("%Y-%m-%d")
            end_dt = self.corr_end.value.strftime("%Y-%m-%d")

            result = analysis_service.compute_correlation(
                data, start_dt, end_dt, asset1, asset2, window
            )
            self._display_correlation(result, asset1, asset2, window)

        run_in_background(self.page, t, calculate, loading=self.corr_loading)

    def _display_correlation(self, result, asset1, asset2, window):
        t = self.state.translator
        controls = []
        is_simple = asset1 is None

        if is_simple:
            corr_matrix = result.get("correlation_matrix")
            if corr_matrix is not None:
                self.corr_heatmap.content = chart_service.chart_correlation_heatmap(t, corr_matrix)
                self._corr_matrix = corr_matrix
                self._rolling_corr = None
                self.corr_export_row.visible = True
            else:
                controls.append(ft.Text(t.get("analysis.corr.simple_error"), size=14))
                self.corr_heatmap.content = None
                self._corr_matrix = None
                self.corr_export_row.visible = False
            self.corr_rolling_chart.content = None
        else:
            rolling_corr = result.get("rolling_corr")
            if rolling_corr is not None and not rolling_corr.empty:
                self.corr_rolling_chart.content = chart_service.chart_rolling_correlation(
                    t, rolling_corr, window, asset1, asset2
                )
                self._rolling_corr = rolling_corr
                self._corr_matrix = None
                self.corr_export_row.visible = True
            else:
                self.corr_rolling_chart.content = None
                self._rolling_corr = None
                self.corr_export_row.visible = False
            self.corr_heatmap.content = None

        self.corr_results.controls = controls
        self.page.update()

    # ── Drawdown Tab ──────────────────────────────────────────────────

    def _build_drawdown_tab(self) -> ft.Control:
        t = self.state.translator
        self.dd_start, self.dd_end = date_range_fields(
            self.page, t.get("analysis.drawdown.start_dt").strip(), t.get("analysis.drawdown.end_dt").strip(),
            t.get("components.date_format_hint"),
        )

        # Chain on_submit for keyboard "next field" navigation
        chain_focus([self.dd_start.field, self.dd_end.field])

        self.dd_loading = ft.ProgressRing(visible=False, width=30, height=30)
        self.dd_result_text = ft.Text("", size=14, selectable=True)
        self.dd_chart = ft.Container()
        self.dd_export_row = ft.Row([
            ft.Button(t.get("analysis.export_plot_csv"), icon=ft.Icons.ASSESSMENT,
                          on_click=lambda _: self.page.run_task(self._export_dd_csv)),
        ], visible=False)

        dd_submit_btn = calculate_button(t, self._submit_drawdown)

        col = ft.Column([
            ft.Container(height=5),
            self.dd_start.control,
            self.dd_end.control,
            ft.Row([ft.Container(width=5), self.dd_loading]),
            ft.Row([dd_submit_btn], alignment=ft.MainAxisAlignment.CENTER),
            self.dd_result_text,
            self.dd_chart,
            self.dd_export_row,
            ft.Container(height=20),
        ], spacing=12, scroll=ft.ScrollMode.AUTO)

        scroll_into_view_on_focus(col, [self.dd_start.field, self.dd_end.field], prefix="dd")

        return ft.Container(content=col, padding=10, expand=True)

    def _submit_drawdown(self, e):
        s = self.state
        t = s.translator
        if self.dd_start.value is None or self.dd_end.value is None:
            show_snack(self.page, t.get("misc_errors.nodate"), error=True)
            return
        if self.dd_start.value > date.today() or self.dd_end.value > date.today():
            show_snack(self.page, t.get("misc_errors.date_future"), error=True)
            return
        if self.dd_start.value >= self.dd_end.value:
            show_snack(self.page, t.get("misc_errors.date_start_end"), error=True)
            return
        data = self._get_analysis_data()
        if not data:
            show_snack(self.page, t.get("operations.select_account"), error=True)
            return

        def calculate():
            """Compute the drawdown over the chosen period and show the result and chart."""
            start_dt = self.dd_start.value
            end_dt = self.dd_end.value

            result = analysis_service.compute_drawdown(data, start_dt, end_dt)

            if not result["has_data"]:
                self.dd_result_text.value = t.get("analysis.drawdown.error")
                self.dd_chart.content = None
                self._dd_data = None
                self.dd_export_row.visible = False
            elif len(result["pf_history"]) < 10:
                show_snack(self.page, t.get("analysis.drawdown.min_range"), error=True)
                self.dd_result_text.value = ""
                self.dd_chart.content = None
                self._dd_data = None
                self.dd_export_row.visible = False
            else:
                start_str = start_dt.strftime(DATE_FORMAT)
                end_str = end_dt.strftime(DATE_FORMAT)
                self.dd_result_text.value = t.get(
                    "analysis.drawdown.result",
                    start_dt=start_str, end_dt=end_str, mdd=result["mdd"] * 100
                )
                self.dd_chart.content = chart_service.chart_drawdown(
                    t, result["pf_history"], result["drawdown"], result["mdd"]
                )
                self._dd_data = {
                    "pf_history": result["pf_history"],
                    "drawdown": result["drawdown"],
                }
                self.dd_export_row.visible = True

        run_in_background(self.page, t, calculate, loading=self.dd_loading)

    # ── VaR Tab ───────────────────────────────────────────────────────

    def _build_var_tab(self) -> ft.Control:
        t = self.state.translator
        self.var_ci = rounded_text_field(
            label=t.get("analysis.var.ci"),
            keyboard_type=ft.KeyboardType.NUMBER, input_filter=DECIMAL_INPUT_FILTER, value="0.99",
            col={"xs": 6, "md": 6})
        self.var_days = rounded_text_field(
            label=t.get("analysis.var.days"),
            keyboard_type=ft.KeyboardType.NUMBER, input_filter=_INT_FILTER, value="10",
            col={"xs": 6, "md": 6})
        # Chain on_submit for keyboard "next field" navigation
        chain_focus([self.var_ci, self.var_days])

        self.var_loading = ft.ProgressRing(visible=False, width=30, height=30)
        self.var_result_text = ft.Text("", size=14, selectable=True)
        self.var_chart = ft.Container()
        self.var_export_row = ft.Row([
            ft.Button(t.get("analysis.export_plot_csv"), icon=ft.Icons.ASSESSMENT,
                          on_click=lambda _: self.page.run_task(self._export_var_csv)),
        ], visible=False)

        var_submit_btn = calculate_button(t, self._submit_var)

        col = ft.Column([
            ft.Container(height=5),
            ft.ResponsiveRow([self.var_ci, self.var_days]),
            ft.Row([ft.Container(width=5), self.var_loading]),
            ft.Row([var_submit_btn], alignment=ft.MainAxisAlignment.CENTER),
            self.var_result_text,
            self.var_chart,
            self.var_export_row,
            ft.Container(height=20),
        ], spacing=12, scroll=ft.ScrollMode.AUTO)

        scroll_into_view_on_focus(col, [self.var_ci, self.var_days], prefix="var")

        return ft.Container(content=col, padding=10, expand=True)

    def _submit_var(self, e):
        s = self.state
        t = s.translator

        try:
            ci = float(self.var_ci.value)
            if ci <= 0 or ci >= 1:
                raise ValueError
        except (ValueError, TypeError):
            show_snack(self.page, t.get("analysis.var.ci_error"), error=True)
            return
        try:
            days = int(self.var_days.value)
            if days <= 0:
                raise ValueError
        except (ValueError, TypeError):
            show_snack(self.page, t.get("analysis.var.days_error"), error=True)
            return

        data = self._get_analysis_data()
        if not data:
            show_snack(self.page, t.get("operations.select_account"), error=True)
            return

        def calculate():
            """Run the Value at Risk simulation and show the result and chart."""
            result = analysis_service.compute_var_mc(data, ci, days)

            if not result["has_positions"]:
                self.var_result_text.value = t.get("analysis.var.error")
                self.var_chart.content = None
                self._var_data = None
                self.var_export_row.visible = False
            else:
                self.var_result_text.value = t.get(
                    "analysis.var.result",
                    ci=ci, days=days, var=result["var"]
                )
                self.var_chart.content = chart_service.chart_var_mc(
                    t, result["scenario_return"], result["var"], ci
                )
                self._var_data = {
                    "scenario_return": result["scenario_return"],
                    "var": result["var"],
                    "ci": ci,
                    "days": days,
                }
                self.var_export_row.visible = True

        run_in_background(self.page, t, calculate, loading=self.var_loading)

    # ── Allocation Tab ───────────────────────────────────────────────

    def _build_allocation_tab(self) -> ft.Control:
        t = self.state.translator
        self.alloc_date = DateField(self.page, t.get("components.pick_date"), t.get("components.date_format_hint"))
        self.alloc_loading = ft.ProgressRing(visible=False, width=30, height=30)
        self.alloc_chart = ft.Container()

        alloc_submit_btn = calculate_button(t, self._submit_allocation)

        col = ft.Column([
            ft.Container(height=5),
            self.alloc_date.control,
            ft.Row([ft.Container(width=5), self.alloc_loading]),
            ft.Row([alloc_submit_btn], alignment=ft.MainAxisAlignment.CENTER),
            self.alloc_chart,
            ft.Container(height=20),
        ], spacing=12, scroll=ft.ScrollMode.AUTO)

        scroll_into_view_on_focus(col, [self.alloc_date.field], prefix="alloc")

        return ft.Container(content=col, padding=10, expand=True)

    def _submit_allocation(self, e):
        s = self.state
        t = s.translator
        if self.alloc_date.value is None:
            show_snack(self.page, t.get("misc_errors.nodate"), error=True)
            return
        if self.alloc_date.value > date.today():
            show_snack(self.page, t.get("misc_errors.date_future"), error=True)
            return

        data = self._get_analysis_data()
        if not data:
            show_snack(self.page, t.get("operations.select_account"), error=True)
            return

        def calculate():
            """Compute the allocation on the chosen date and draw the pie chart."""
            allocation = analysis_service.compute_allocation(data, self.alloc_date.value)
            self.alloc_chart.content = chart_service.chart_allocation(allocation, t)

        run_in_background(self.page, t, calculate, loading=self.alloc_loading)

    # ── Export helpers ────────────────────────────────────────────────

    async def _save_csv(self, file_name, csv_bytes):
        """Let the user save a chart's data as `file_name`, confirming once saved."""
        t = self.state.translator
        await save_bytes(self.page, self.file_picker, file_name, csv_bytes, "csv", t.get("transactions.export_success"))

    def _df_to_csv_bytes(self, df):
        buf = io.StringIO()
        df.to_csv(buf, index=False)
        return buf.getvalue().encode("utf-8")

    async def _export_sum_csv(self):
        if self._sum_history is None:
            return
        csv_bytes = self._df_to_csv_bytes(self._sum_history)
        await self._save_csv("Portfolio History.csv", csv_bytes)

    async def _export_corr_csv(self):
        if self._corr_matrix is not None:
            buf = io.StringIO()
            self._corr_matrix.to_csv(buf)
            csv_bytes = buf.getvalue().encode("utf-8")
            await self._save_csv("Correlation Matrix.csv", csv_bytes)
        elif self._rolling_corr is not None:
            df = pd.DataFrame({"Date": self._rolling_corr.index, "Correlation": self._rolling_corr.values})
            csv_bytes = self._df_to_csv_bytes(df)
            await self._save_csv("Rolling Correlation.csv", csv_bytes)

    async def _export_dd_csv(self):
        if self._dd_data is None:
            return
        pf = self._dd_data["pf_history"].copy()
        pf["Drawdown %"] = self._dd_data["drawdown"].values * 100
        csv_bytes = self._df_to_csv_bytes(pf)
        await self._save_csv("Drawdown.csv", csv_bytes)

    async def _export_var_csv(self):
        if self._var_data is None:
            return
        df = pd.DataFrame({"Scenario Return": self._var_data["scenario_return"]})
        csv_bytes = self._df_to_csv_bytes(df)
        await self._save_csv("VaR Monte Carlo.csv", csv_bytes)
