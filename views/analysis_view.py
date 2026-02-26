import io
import flet as ft
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

from components.snack import show_snack
from services import analysis_service, chart_service
from utils.constants import DATE_FORMAT
from utils.date_utils import parse_date_input


class AnalysisView:
    def __init__(self, page: ft.Page, state):
        self.page = page
        self.state = state

    def build(self) -> ft.Control:
        t = self.state.translator
        if not self.state.brokers:
            return ft.Text(t.get("home.no_account"), size=16)

        # Set up FilePicker service for export
        self.file_picker = ft.FilePicker()
        self.page.services[:] = [
            s for s in self.page.services if not isinstance(s, ft.FilePicker)
        ]
        self.page.services.append(self.file_picker)

        # Data storage for CSV export
        self._sum_history = None
        self._corr_matrix = None
        self._rolling_corr = None
        self._dd_data = None
        self._var_data = None

        has_account = self.state.analysis_acc_idx is not None or len(self.state.accounts) > 0

        self.form_container = ft.Container(disabled=not has_account, expand=True)

        summary_content = self._build_summary_tab()
        corr_content = self._build_correlation_tab()
        dd_content = self._build_drawdown_tab()
        var_content = self._build_var_tab()

        self.form_container.content = ft.Tabs(
            length=4,
            selected_index=getattr(self.state, "_analysis_tab_index", 0),
            on_change=self._on_tab_change,
            content=ft.Column([
                ft.TabBar(tabs=[
                    ft.Tab(label=t.get("analysis.op_statistics")),
                    ft.Tab(label=t.get("analysis.op_correlation")),
                    ft.Tab(label=t.get("analysis.op_drawdown")),
                    ft.Tab(label=t.get("analysis.op_var")),
                ], scrollable=True),
                ft.TabBarView(
                    controls=[summary_content, corr_content, dd_content, var_content],
                    expand=True,
                ),
            ], expand=True),
            expand=True,
        )

        confirm_btn = ft.FilledButton(
            ft.Row([
                    ft.Text(t.get("components.calculate")),
                    ft.Icon(ft.Icons.KEYBOARD_DOUBLE_ARROW_RIGHT),]),
            on_click=self._on_analysis_confirm,
            disabled=not has_account,
            style=ft.ButtonStyle(padding=ft.padding.symmetric(horizontal=32, vertical=18)),
        )
        return ft.Stack([
            ft.Column([
                ft.Container(self._build_account_dropdown(), padding=ft.padding.only(top=5, left=5, right=5)),
                self.form_container,
            ], expand=True),
            ft.Container(
                ft.Row([confirm_btn], alignment=ft.MainAxisAlignment.CENTER),
                left=0, right=0, bottom=20,
            ),
        ], expand=True)

    def _build_account_dropdown(self) -> ft.Control:
        t = self.state.translator
        options = [
            ft.dropdown.Option(key="all", text=t.get("analysis.all_accounts")),
        ]
        for k, v in sorted(self.state.brokers.items()):
            options.append(ft.dropdown.Option(key=str(k), text=v))

        # Determine current value
        if self.state.analysis_acc_idx is None:
            current = "all"
        else:
            current = str(self.state.analysis_acc_idx)

        return ft.Dropdown(
            value=current,
            options=options,
            on_select=self._on_account_selected,
            expand=True,
            border_width=2.5,
            border_radius=ft.border_radius.all(15),
            border_color=ft.Colors.SECONDARY_CONTAINER,
            bgcolor=ft.Colors.SECONDARY_CONTAINER,
        )

    def _on_tab_change(self, e):
        self.state._analysis_tab_index = e.control.selected_index

    def _on_analysis_confirm(self, e):
        idx = getattr(self.state, "_analysis_tab_index", 0)
        if idx == 0:
            self._submit_summary(e)
        elif idx == 1:
            self._submit_correlation(e)
        elif idx == 2:
            self._submit_drawdown(e)
        else:
            self._submit_var(e)

    def _on_account_selected(self, e):
        val = e.control.value
        if val == "all":
            self.state.analysis_acc_idx = None
        else:
            self.state.analysis_acc_idx = int(val)
        from views import _rebuild_page
        _rebuild_page(self.page, self.state, selected_index=2)

    def _get_analysis_data(self):
        """Build the data list for analysis functions based on current selection."""
        s = self.state
        if s.analysis_acc_idx is None:
            # All accounts
            data = []
            for idx in sorted(s.accounts.keys()):
                acc = s.accounts[idx]
                data.append([idx, acc["df"]])
            return data
        else:
            acc = s.get_account(s.analysis_acc_idx)
            if acc is None:
                return []
            return [[s.analysis_acc_idx, acc["df"]]]

    # ── Statistics Tab ────────────────────────────────────────────────

    def _build_summary_tab(self) -> ft.Control:
        t = self.state.translator
        self.sum_date_field = ft.TextField(
            label=t.get("components.pick_date"),
            hint_text=t.get("components.date_format_hint"),
            border_radius=ft.border_radius.all(15),
            border_color=ft.Colors.with_opacity(0.40, ft.Colors.GREY),
            keyboard_type=ft.KeyboardType.DATETIME,
            on_change=self._on_sum_date_typed,
            expand=True,
        )
        self.sum_date_icon = ft.FilledTonalIconButton(
            icon=ft.Icons.CALENDAR_MONTH,
            on_click=self._open_sum_date_picker,
        )
        self.sum_date_value = None
        self.sum_loading = ft.ProgressRing(visible=False, width=30, height=30)
        self.sum_results = ft.Column([], spacing=5)
        self.sum_chart = ft.Container()
        self.sum_export_row = ft.Row([
            ft.ElevatedButton(t.get("analysis.export_plot_csv"), icon=ft.Icons.ASSESSMENT,
                          on_click=lambda _: self.page.run_task(self._export_sum_csv)),
        ], visible=False)

        return ft.Container(
            content=ft.Column([
                ft.Row([self.sum_date_field, self.sum_date_icon]),
                self.sum_loading,
                self.sum_results,
                self.sum_chart,
                self.sum_export_row,
                ft.Container(height=80),
            ], spacing=12, scroll=ft.ScrollMode.AUTO),
            padding=10,
            expand=True,
        )

    def _open_sum_date_picker(self, e):
        dp = ft.DatePicker(
            first_date=datetime(2000, 1, 1),
            last_date=datetime.now(),
            on_change=self._on_sum_date_picked,
        )
        self.page.show_dialog(dp)

    def _on_sum_date_typed(self, e):
        self.sum_date_value = parse_date_input(e.control.value)

    def _on_sum_date_picked(self, e):
        picked = e.control.value
        if isinstance(picked, datetime):
            picked = (picked + timedelta(hours=12)).date()
        self.sum_date_value = picked
        self.sum_date_field.value = picked.strftime(DATE_FORMAT)
        self.page.update()

    def _submit_summary(self, e):
        s = self.state
        t = s.translator
        if self.sum_date_value is None:
            show_snack(self.page, t.get("misc_errors.nodate"), error=True)
            return

        data = self._get_analysis_data()
        if not data:
            show_snack(self.page, t.get("operations.select_account"), error=True)
            return

        self.sum_loading.visible = True
        self.page.update()

        def worker():
            try:
                ref_date = self.sum_date_value
                dt_str = ref_date.strftime(DATE_FORMAT)
                import os
                save_path = os.path.join(s.user_folder, "Storico Portafoglio.csv")

                result = analysis_service.compute_summary(
                    t, s.brokers, data, ref_date, dt_str, save_path=save_path
                )
                self._display_summary(result, dt_str)
            except Exception as ex:
                show_snack(self.page, str(ex), error=True)
            finally:
                self.sum_loading.visible = False
                self.page.update()

        self.page.run_thread(worker)

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
                    acc_text += f"    {pos['ticker']}\n"
                    acc_text += f"      {t.get('analysis.summary.assets_recap.avg_price')}{pos['pmc']:.4f}\n"
                    acc_text += f"      {t.get('analysis.summary.assets_recap.current_price')}{pos['price']:.4f}\n"
                    acc_text += f"      {t.get('analysis.summary.assets_recap.value')}{pos['value']:.2f}\n"

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
            min_date_str = min_date.strftime(DATE_FORMAT)
            self.sum_chart.content = chart_service.chart_summary(
                self.state.translator, pf_history, min_date_str, dt_str
            )
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
            content=ft.Row([
                ft.Radio(value="simple", label=t.get("analysis.corr.simple")),
                ft.Radio(value="rolling", label=t.get("analysis.corr.rolling_label")),
            ], wrap=True),
            on_change=self._on_corr_type_change,
        )

        self.corr_start_field = ft.TextField(
            label=t.get("analysis.corr.start_dt").strip(),
            hint_text=t.get("components.date_format_hint"),
            border_radius=ft.border_radius.all(15),
            border_color=ft.Colors.with_opacity(0.40, ft.Colors.GREY),
            keyboard_type=ft.KeyboardType.DATETIME,
            on_change=lambda e: self._on_corr_date_typed(e, "start"),
            expand=True,
        )
        self.corr_start_icon = ft.FilledTonalIconButton(
            icon=ft.Icons.CALENDAR_MONTH,
            on_click=lambda e: self._open_corr_date_picker(e, "start"),
        )
        self.corr_start_value = None

        self.corr_end_field = ft.TextField(
            label=t.get("analysis.corr.end_dt").strip(),
            hint_text=t.get("components.date_format_hint"),
            border_radius=ft.border_radius.all(15),
            border_color=ft.Colors.with_opacity(0.40, ft.Colors.GREY),
            keyboard_type=ft.KeyboardType.DATETIME,
            on_change=lambda e: self._on_corr_date_typed(e, "end"),
            expand=True,
        )
        self.corr_end_icon = ft.FilledTonalIconButton(
            icon=ft.Icons.CALENDAR_MONTH,
            on_click=lambda e: self._open_corr_date_picker(e, "end"),
        )
        self.corr_end_value = None

        self.corr_asset1 = ft.TextField(
            label=t.get("analysis.corr.asset1"),
            border_radius=ft.border_radius.all(15),
            border_color=ft.Colors.with_opacity(0.40, ft.Colors.GREY),
            col={"xs": 12, "md": 4})
        self.corr_asset2 = ft.TextField(
            label=t.get("analysis.corr.asset2"),
            border_radius=ft.border_radius.all(15),
            border_color=ft.Colors.with_opacity(0.40, ft.Colors.GREY),
            col={"xs": 12, "md": 4})
        self.corr_window = ft.TextField(
            label=t.get("analysis.corr.window"),
            border_radius=ft.border_radius.all(15),
            border_color=ft.Colors.with_opacity(0.40, ft.Colors.GREY),
            keyboard_type=ft.KeyboardType.NUMBER, value="100",
            col={"xs": 12, "md": 4})

        self.corr_rolling_fields = ft.ResponsiveRow(
            [self.corr_asset1, self.corr_asset2, self.corr_window],
            visible=False,
        )

        self.corr_loading = ft.ProgressRing(visible=False, width=30, height=30)
        self.corr_results = ft.Column([], spacing=5)
        self.corr_heatmap = ft.Container()
        self.corr_rolling_chart = ft.Container()
        self.corr_export_row = ft.Row([
            ft.ElevatedButton(t.get("analysis.export_plot_csv"), icon=ft.Icons.ASSESSMENT,
                          on_click=lambda _: self.page.run_task(self._export_corr_csv)),
        ], visible=False)

        return ft.Container(
            content=ft.Column([
                self.corr_type,
                ft.Row([self.corr_start_field, self.corr_start_icon]),
                ft.Row([self.corr_end_field, self.corr_end_icon]),
                self.corr_rolling_fields,
                self.corr_loading,
                self.corr_results,
                self.corr_heatmap,
                self.corr_rolling_chart,
                self.corr_export_row,
                ft.Container(height=80),
            ], spacing=12, scroll=ft.ScrollMode.AUTO),
            padding=10,
            expand=True,
        )

    def _on_corr_type_change(self, e):
        self.corr_rolling_fields.visible = (self.corr_type.value == "rolling")
        self.corr_results.controls = []
        self.corr_heatmap.content = None
        self.corr_rolling_chart.content = None
        self.page.update()

    def _open_corr_date_picker(self, e, which):
        first = datetime(2000, 1, 1)
        last = datetime.now()
        if which == "start" and self.corr_end_value:
            last = datetime.combine(self.corr_end_value, datetime.min.time()) - timedelta(days=1)
        elif which == "end" and self.corr_start_value:
            first = datetime.combine(self.corr_start_value, datetime.min.time()) + timedelta(days=1)
        dp = ft.DatePicker(
            first_date=first,
            last_date=last,
            on_change=lambda ev, w=which: self._on_corr_date_picked(ev, w),
        )
        self.page.show_dialog(dp)

    def _on_corr_date_typed(self, e, which):
        parsed = parse_date_input(e.control.value)
        if which == "start":
            self.corr_start_value = parsed
        else:
            self.corr_end_value = parsed

    def _on_corr_date_picked(self, e, which):
        picked = e.control.value
        if isinstance(picked, datetime):
            picked = (picked + timedelta(hours=12)).date()
        if which == "start":
            self.corr_start_value = picked
            self.corr_start_field.value = picked.strftime(DATE_FORMAT)
        else:
            self.corr_end_value = picked
            self.corr_end_field.value = picked.strftime(DATE_FORMAT)
        self.page.update()

    def _submit_correlation(self, e):
        s = self.state
        t = s.translator
        if self.corr_start_value is None or self.corr_end_value is None:
            show_snack(self.page, t.get("misc_errors.nodate"), error=True)
            return

        is_rolling = self.corr_type.value == "rolling"
        asset1 = asset2 = None
        window = None

        if is_rolling:
            asset1 = self.corr_asset1.value.strip()
            asset2 = self.corr_asset2.value.strip()
            if not asset1 or not asset2:
                show_snack(self.page, "Tickers required", error=True)
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

        self.corr_loading.visible = True
        self.page.update()

        def worker():
            try:
                start_dt = self.corr_start_value.strftime("%Y-%m-%d")
                end_dt = self.corr_end_value.strftime("%Y-%m-%d")

                result = analysis_service.compute_correlation(
                    t, data, start_dt, end_dt, asset1, asset2, window
                )
                self._display_correlation(result, start_dt, end_dt, asset1, asset2, window)
            except Exception as ex:
                show_snack(self.page, str(ex), error=True)
            finally:
                self.corr_loading.visible = False
                self.page.update()

        self.page.run_thread(worker)

    def _display_correlation(self, result, start_dt, end_dt, asset1, asset2, window):
        t = self.state.translator
        controls = []
        is_simple = asset1 is None

        if is_simple:
            corr_matrix = result.get("correlation_matrix")
            if corr_matrix is not None:
                self.corr_heatmap.content = chart_service.chart_correlation_heatmap(
                    t, corr_matrix, start_dt, end_dt
                )
                self._corr_matrix = corr_matrix
                self._rolling_corr = None
                self.corr_export_row.visible = True
            else:
                controls.append(ft.Text(t.get("analysis.corr.simple_error").strip(), size=12))
                self.corr_heatmap.content = None
                self._corr_matrix = None
                self.corr_export_row.visible = False
            self.corr_rolling_chart.content = None
        else:
            rolling_corr = result.get("rolling_corr")
            if rolling_corr is not None and not rolling_corr.empty:
                self.corr_rolling_chart.content = chart_service.chart_rolling_correlation(
                    t, rolling_corr, window, asset1, asset2, start_dt, end_dt
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
        self.dd_start_field = ft.TextField(
            label=t.get("analysis.drawdown.start_dt").strip(),
            hint_text=t.get("components.date_format_hint"),
            border_radius=ft.border_radius.all(15),
            border_color=ft.Colors.with_opacity(0.40, ft.Colors.GREY),
            keyboard_type=ft.KeyboardType.DATETIME,
            on_change=lambda e: self._on_dd_date_typed(e, "start"),
            expand=True,
        )
        self.dd_start_icon = ft.FilledTonalIconButton(
            icon=ft.Icons.CALENDAR_MONTH,
            on_click=lambda e: self._open_dd_date_picker(e, "start"),
        )
        self.dd_start_value = None

        self.dd_end_field = ft.TextField(
            label=t.get("analysis.drawdown.end_dt").strip(),
            hint_text=t.get("components.date_format_hint"),
            border_radius=ft.border_radius.all(15),
            border_color=ft.Colors.with_opacity(0.40, ft.Colors.GREY),
            keyboard_type=ft.KeyboardType.DATETIME,
            on_change=lambda e: self._on_dd_date_typed(e, "end"),
            expand=True,
        )
        self.dd_end_icon = ft.FilledTonalIconButton(
            icon=ft.Icons.CALENDAR_MONTH,
            on_click=lambda e: self._open_dd_date_picker(e, "end"),
        )
        self.dd_end_value = None

        self.dd_loading = ft.ProgressRing(visible=False, width=30, height=30)
        self.dd_result_text = ft.Text("", size=14, selectable=True)
        self.dd_chart = ft.Container()
        self.dd_export_row = ft.Row([
            ft.ElevatedButton(t.get("analysis.export_plot_csv"), icon=ft.Icons.ASSESSMENT,
                          on_click=lambda _: self.page.run_task(self._export_dd_csv)),
        ], visible=False)

        return ft.Container(
            content=ft.Column([
                ft.Row([self.dd_start_field, self.dd_start_icon]),
                ft.Row([self.dd_end_field, self.dd_end_icon]),
                self.dd_loading,
                self.dd_result_text,
                self.dd_chart,
                self.dd_export_row,
                ft.Container(height=80),
            ], spacing=12, scroll=ft.ScrollMode.AUTO),
            padding=10,
            expand=True,
        )

    def _open_dd_date_picker(self, e, which):
        first = datetime(2000, 1, 1)
        last = datetime.now()
        if which == "start" and self.dd_end_value:
            last = datetime.combine(self.dd_end_value, datetime.min.time()) - timedelta(days=1)
        elif which == "end" and self.dd_start_value:
            first = datetime.combine(self.dd_start_value, datetime.min.time()) + timedelta(days=1)
        dp = ft.DatePicker(
            first_date=first,
            last_date=last,
            on_change=lambda ev, w=which: self._on_dd_date_picked(ev, w),
        )
        self.page.show_dialog(dp)

    def _on_dd_date_typed(self, e, which):
        parsed = parse_date_input(e.control.value)
        if which == "start":
            self.dd_start_value = parsed
        else:
            self.dd_end_value = parsed

    def _on_dd_date_picked(self, e, which):
        picked = e.control.value
        if isinstance(picked, datetime):
            picked = (picked + timedelta(hours=12)).date()
        if which == "start":
            self.dd_start_value = picked
            self.dd_start_field.value = picked.strftime(DATE_FORMAT)
        else:
            self.dd_end_value = picked
            self.dd_end_field.value = picked.strftime(DATE_FORMAT)
        self.page.update()

    def _submit_drawdown(self, e):
        s = self.state
        t = s.translator
        if self.dd_start_value is None or self.dd_end_value is None:
            show_snack(self.page, t.get("misc_errors.nodate"), error=True)
            return

        data = self._get_analysis_data()
        if not data:
            show_snack(self.page, t.get("operations.select_account"), error=True)
            return

        self.dd_loading.visible = True
        self.page.update()

        def worker():
            try:
                start_dt = self.dd_start_value
                end_dt = self.dd_end_value

                result = analysis_service.compute_drawdown(t, data, start_dt, end_dt)

                if not result["has_data"]:
                    self.dd_result_text.value = t.get("analysis.drawdown.error").strip()
                    self.dd_chart.content = None
                    self._dd_data = None
                    self.dd_export_row.visible = False
                else:
                    start_str = start_dt.strftime(DATE_FORMAT)
                    end_str = end_dt.strftime(DATE_FORMAT)
                    self.dd_result_text.value = t.get(
                        "analysis.drawdown.result",
                        start_dt=start_str, end_dt=end_str, mdd=result["mdd"] * 100
                    ).strip()
                    self.dd_chart.content = chart_service.chart_drawdown(
                        t, result["pf_history"], result["drawdown"],
                        result["mdd"], start_str, end_str
                    )
                    self._dd_data = {
                        "pf_history": result["pf_history"],
                        "drawdown": result["drawdown"],
                    }
                    self.dd_export_row.visible = True
            except Exception as ex:
                show_snack(self.page, str(ex), error=True)
            finally:
                self.dd_loading.visible = False
                self.page.update()

        self.page.run_thread(worker)

    # ── VaR Tab ───────────────────────────────────────────────────────

    def _build_var_tab(self) -> ft.Control:
        t = self.state.translator
        self.var_ci = ft.TextField(
            label=t.get("analysis.var.ci"),
            border_color=ft.Colors.with_opacity(0.40, ft.Colors.GREY),
            border_radius=ft.border_radius.all(15),
            keyboard_type=ft.KeyboardType.NUMBER, value="0.99",
            col={"xs": 6, "md": 4})
        self.var_days = ft.TextField(
            label=t.get("analysis.var.days"),
            border_radius=ft.border_radius.all(15),
            border_color=ft.Colors.with_opacity(0.40, ft.Colors.GREY),
            keyboard_type=ft.KeyboardType.NUMBER, value="10",
            col={"xs": 6, "md": 4})
        self.var_loading = ft.ProgressRing(visible=False, width=30, height=30)
        self.var_result_text = ft.Text("", size=14, selectable=True)
        self.var_chart = ft.Container()
        self.var_export_row = ft.Row([
            ft.ElevatedButton(t.get("analysis.export_plot_csv"), icon=ft.Icons.ASSESSMENT,
                          on_click=lambda _: self.page.run_task(self._export_var_csv)),
        ], visible=False)

        return ft.Container(
            content=ft.Column([
                ft.ResponsiveRow([self.var_ci, self.var_days]),
                self.var_loading,
                self.var_result_text,
                self.var_chart,
                self.var_export_row,
                ft.Container(height=80),
            ], spacing=12, scroll=ft.ScrollMode.AUTO),
            padding=10,
            expand=True,
        )

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

        self.var_loading.visible = True
        self.page.update()

        def worker():
            try:
                result = analysis_service.compute_var_mc(t, data, ci, days)

                if not result["has_positions"]:
                    self.var_result_text.value = t.get("analysis.var.error").strip()
                    self.var_chart.content = None
                    self._var_data = None
                    self.var_export_row.visible = False
                else:
                    self.var_result_text.value = t.get(
                        "analysis.var.result",
                        ci=ci, days=days, var=result["var"]
                    ).strip()
                    self.var_chart.content = chart_service.chart_var_mc(
                        t, result["scenario_return"], result["var"], ci, days
                    )
                    self._var_data = {
                        "scenario_return": result["scenario_return"],
                        "var": result["var"],
                        "ci": ci,
                        "days": days,
                    }
                    self.var_export_row.visible = True
            except Exception as ex:
                show_snack(self.page, str(ex), error=True)
            finally:
                self.var_loading.visible = False
                self.page.update()

        self.page.run_thread(worker)

    # ── Export helpers ────────────────────────────────────────────────

    async def _save_csv(self, file_name, csv_bytes):
        t = self.state.translator
        path = await self.file_picker.save_file(
            file_name=file_name,
            allowed_extensions=["csv"],
            src_bytes=csv_bytes,
        )
        if path:
            if not self.page.web and not self.page.platform.is_mobile():
                with open(path, "wb") as f:
                    f.write(csv_bytes)
            show_snack(self.page, t.get("home.export_success"))

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
