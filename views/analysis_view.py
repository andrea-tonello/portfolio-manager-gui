import flet as ft
import numpy as np
from datetime import datetime, timedelta

from components.snack import show_snack
from services import analysis_service, chart_service
from utils.constants import DATE_FORMAT


class AnalysisView:
    def __init__(self, page: ft.Page, state):
        self.page = page
        self.state = state

    def build(self) -> ft.Control:
        t = self.state.translator
        if not self.state.brokers:
            return ft.Text(t.get("home.no_account"), size=16)

        has_account = self.state.analysis_acc_idx is not None or len(self.state.accounts) > 0

        self.form_container = ft.Container(disabled=not has_account, expand=True)

        summary_content = self._build_summary_tab()
        corr_content = self._build_correlation_tab()
        dd_content = self._build_drawdown_tab()
        var_content = self._build_var_tab()

        self.state._analysis_tab_index = 0

        self.form_container.content = ft.Tabs(
            length=4,
            selected_index=0,
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

        return ft.Column([
            ft.Container(self._build_account_dropdown(), padding=ft.padding.only(top=5, left=5, right=5),),
            self.form_container,
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
        self.sum_date_btn = ft.ElevatedButton(
            t.get("components.pick_date"), icon=ft.Icons.CALENDAR_TODAY,
            on_click=self._open_sum_date_picker,
        )
        self.sum_date_label = ft.Text("")
        self.sum_date_value = None
        self.sum_loading = ft.ProgressRing(visible=False, width=30, height=30)
        self.sum_results = ft.Column([], spacing=5)
        self.sum_chart = ft.Container()

        return ft.Container(
            content=ft.Column([
                ft.Row([self.sum_date_btn, self.sum_date_label]),
                ft.Row([
                    ft.ElevatedButton(
                        t.get("components.confirm"),                         
                        on_click=self._submit_summary
                    ),
                    self.sum_loading,
                ]),
                self.sum_results,
                self.sum_chart,
            ], spacing=12, scroll=ft.ScrollMode.AUTO),
            padding=20,
            expand=True,
        )

    def _open_sum_date_picker(self, e):
        dp = ft.DatePicker(
            first_date=datetime(2000, 1, 1),
            last_date=datetime.now(),
            on_change=self._on_sum_date_picked,
        )
        self.page.show_dialog(dp)

    def _on_sum_date_picked(self, e):
        picked = e.control.value
        if isinstance(picked, datetime):
            picked = (picked + timedelta(hours=12)).date()
        self.sum_date_value = picked
        self.sum_date_label.value = picked.strftime(DATE_FORMAT)
        self.page.update()

    def _submit_summary(self, e):
        s = self.state
        t = s.translator
        if self.sum_date_value is None:
            show_snack(self.page, t.get("dates.error"), error=True)
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
        else:
            self.sum_chart.content = None

        self.page.update()

    # ── Correlation Tab ───────────────────────────────────────────────

    def _build_correlation_tab(self) -> ft.Control:
        t = self.state.translator
        self.corr_start_btn = ft.ElevatedButton(
            t.get("analysis.corr.start_dt").strip(), icon=ft.Icons.CALENDAR_TODAY,
            on_click=lambda e: self._open_corr_date_picker(e, "start"),
        )
        self.corr_start_label = ft.Text("")
        self.corr_start_value = None

        self.corr_end_btn = ft.ElevatedButton(
            t.get("analysis.corr.end_dt").strip(), icon=ft.Icons.CALENDAR_TODAY,
            on_click=lambda e: self._open_corr_date_picker(e, "end"),
        )
        self.corr_end_label = ft.Text("")
        self.corr_end_value = None

        self.corr_asset1 = ft.TextField(
            label=t.get("analysis.corr.asset1"),
            border_radius=ft.border_radius.all(15),
            col={"xs": 12, "md": 4})
        self.corr_asset2 = ft.TextField(
            label=t.get("analysis.corr.asset2"),
            border_radius=ft.border_radius.all(15),
            col={"xs": 12, "md": 4})
        self.corr_window = ft.TextField(
            label=t.get("analysis.corr.window"),
            border_radius=ft.border_radius.all(15),
            keyboard_type=ft.KeyboardType.NUMBER, value="100",
            col={"xs": 12, "md": 4})
        self.corr_loading = ft.ProgressRing(visible=False, width=30, height=30)
        self.corr_results = ft.Column([], spacing=5)
        self.corr_heatmap = ft.Container()
        self.corr_rolling_chart = ft.Container()

        return ft.Container(
            content=ft.Column([
                ft.Row([self.corr_start_btn, self.corr_start_label]),
                ft.Row([self.corr_end_btn, self.corr_end_label]),
                ft.ResponsiveRow([self.corr_asset1, self.corr_asset2, self.corr_window]),
                ft.Row([
                    ft.ElevatedButton(
                        t.get("components.confirm"),
                        on_click=self._submit_correlation
                    ),
                    self.corr_loading,
                ]),
                self.corr_results,
                self.corr_heatmap,
                self.corr_rolling_chart,
            ], spacing=12, scroll=ft.ScrollMode.AUTO),
            padding=20,
            expand=True,
        )

    def _open_corr_date_picker(self, e, which):
        dp = ft.DatePicker(
            first_date=datetime(2000, 1, 1),
            last_date=datetime.now(),
            on_change=lambda ev, w=which: self._on_corr_date_picked(ev, w),
        )
        self.page.show_dialog(dp)

    def _on_corr_date_picked(self, e, which):
        picked = e.control.value
        if isinstance(picked, datetime):
            picked = (picked + timedelta(hours=12)).date()
        if which == "start":
            self.corr_start_value = picked
            self.corr_start_label.value = picked.strftime(DATE_FORMAT)
        else:
            self.corr_end_value = picked
            self.corr_end_label.value = picked.strftime(DATE_FORMAT)
        self.page.update()

    def _submit_correlation(self, e):
        s = self.state
        t = s.translator
        if self.corr_start_value is None or self.corr_end_value is None:
            show_snack(self.page, t.get("dates.error"), error=True)
            return
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

        if result["active_tickers"]:
            controls.append(ft.Text(
                t.get("analysis.corr.simple").strip(),
                weight=ft.FontWeight.BOLD, size=14
            ))

        corr_matrix = result.get("correlation_matrix")
        if corr_matrix is not None:
            self.corr_heatmap.content = chart_service.chart_correlation_heatmap(
                t, corr_matrix, start_dt, end_dt
            )
        else:
            controls.append(ft.Text(t.get("analysis.corr.simple_error").strip(), size=12))
            self.corr_heatmap.content = None

        rolling_corr = result.get("rolling_corr")
        if rolling_corr is not None and not rolling_corr.empty:
            self.corr_rolling_chart.content = chart_service.chart_rolling_correlation(
                t, rolling_corr, window, asset1, asset2, start_dt, end_dt
            )
        else:
            self.corr_rolling_chart.content = None

        self.corr_results.controls = controls
        self.page.update()

    # ── Drawdown Tab ──────────────────────────────────────────────────

    def _build_drawdown_tab(self) -> ft.Control:
        t = self.state.translator
        self.dd_start_btn = ft.ElevatedButton(
            t.get("analysis.drawdown.start_dt").strip(), icon=ft.Icons.CALENDAR_TODAY,
            on_click=lambda e: self._open_dd_date_picker(e, "start"),
        )
        self.dd_start_label = ft.Text("")
        self.dd_start_value = None

        self.dd_end_btn = ft.ElevatedButton(
            t.get("analysis.drawdown.end_dt").strip(), icon=ft.Icons.CALENDAR_TODAY,
            on_click=lambda e: self._open_dd_date_picker(e, "end"),
        )
        self.dd_end_label = ft.Text("")
        self.dd_end_value = None

        self.dd_loading = ft.ProgressRing(visible=False, width=30, height=30)
        self.dd_result_text = ft.Text("", size=14, selectable=True)
        self.dd_chart = ft.Container()

        return ft.Container(
            content=ft.Column([
                ft.Row([self.dd_start_btn, self.dd_start_label]),
                ft.Row([self.dd_end_btn, self.dd_end_label]),
                ft.Row([
                    ft.ElevatedButton(
                        t.get("components.confirm"),
                        on_click=self._submit_drawdown
                    ),
                    self.dd_loading,
                ]),
                self.dd_result_text,
                self.dd_chart,
            ], spacing=12, scroll=ft.ScrollMode.AUTO),
            padding=20,
            expand=True,
        )

    def _open_dd_date_picker(self, e, which):
        dp = ft.DatePicker(
            first_date=datetime(2000, 1, 1),
            last_date=datetime.now(),
            on_change=lambda ev, w=which: self._on_dd_date_picked(ev, w),
        )
        self.page.show_dialog(dp)

    def _on_dd_date_picked(self, e, which):
        picked = e.control.value
        if isinstance(picked, datetime):
            picked = (picked + timedelta(hours=12)).date()
        if which == "start":
            self.dd_start_value = picked
            self.dd_start_label.value = picked.strftime(DATE_FORMAT)
        else:
            self.dd_end_value = picked
            self.dd_end_label.value = picked.strftime(DATE_FORMAT)
        self.page.update()

    def _submit_drawdown(self, e):
        s = self.state
        t = s.translator
        if self.dd_start_value is None or self.dd_end_value is None:
            show_snack(self.page, t.get("dates.error"), error=True)
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
            border_radius=ft.border_radius.all(15),
            keyboard_type=ft.KeyboardType.NUMBER, value="0.99",
            col={"xs": 6, "md": 4})
        self.var_days = ft.TextField(
            label=t.get("analysis.var.days"),
            border_radius=ft.border_radius.all(15),
            keyboard_type=ft.KeyboardType.NUMBER, value="10",
            col={"xs": 6, "md": 4})
        self.var_loading = ft.ProgressRing(visible=False, width=30, height=30)
        self.var_result_text = ft.Text("", size=14, selectable=True)
        self.var_chart = ft.Container()

        return ft.Container(
            content=ft.Column([
                ft.ResponsiveRow([self.var_ci, self.var_days]),
                ft.Row([
                    ft.ElevatedButton(
                        t.get("components.confirm"),
                        on_click=self._submit_var
                    ),
                    self.var_loading,
                ]),
                self.var_result_text,
                self.var_chart,
            ], spacing=12, scroll=ft.ScrollMode.AUTO),
            padding=20,
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
                else:
                    self.var_result_text.value = t.get(
                        "analysis.var.result",
                        ci=ci, days=days, var=result["var"]
                    ).strip()
                    self.var_chart.content = chart_service.chart_var_mc(
                        t, result["scenario_return"], result["var"], ci, days
                    )
            except Exception as ex:
                show_snack(self.page, str(ex), error=True)
            finally:
                self.var_loading.visible = False
                self.page.update()

        self.page.run_thread(worker)
