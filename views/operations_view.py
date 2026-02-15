import flet as ft
import numpy as np
from datetime import datetime, timedelta

from components.snack import show_snack
from services import operations_service
from utils.other_utils import round_half_up, ValidationError
from utils.constants import DATE_FORMAT, CURRENCY_EUR, CURRENCY_USD


class OperationsView:
    def __init__(self, page: ft.Page, state):
        self.page = page
        self.state = state

    def build(self) -> ft.Control:
        t = self.state.translator
        if not self.state.brokers:
            return ft.Text(t.get("home.no_account"), size=16)

        has_account = self.state.ops_acc_idx is not None
        self.form_container = ft.Container(disabled=not has_account)

        cash_content = self._build_cash_tab()
        etf_content = self._build_etf_stock_tab("ETF")
        stock_content = self._build_etf_stock_tab("Azioni")

        self.form_container.content = ft.Tabs(
            length=3,
            selected_index=0,
            content=ft.Column([
                ft.TabBar(tabs=[
                    ft.Tab(label=t.get("cash.title")),
                    ft.Tab(label=t.get("stock.title_etf")),
                    ft.Tab(label=t.get("stock.title_stock")),
                ], scrollable=True),
                ft.TabBarView(
                    controls=[cash_content, etf_content, stock_content],
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
            ft.dropdown.Option(key=str(k), text=v)
            for k, v in sorted(self.state.brokers.items())
        ]
        return ft.Dropdown(
            hint_text=t.get("operations.select_account"),
            hint_style=ft.TextStyle(color=ft.Colors.GREY_500),
            value=str(self.state.ops_acc_idx) if self.state.ops_acc_idx is not None else None,
            options=options,
            on_select=self._on_account_selected,
            expand=True,
            border_width=2.5,
            border_radius=ft.border_radius.all(15),
            border_color=ft.Colors.SECONDARY_CONTAINER,
            bgcolor=ft.Colors.SECONDARY_CONTAINER,
        )

    def _on_account_selected(self, e):
        idx = int(e.control.value)
        self.state.ops_acc_idx = idx
        from views import _rebuild_page
        _rebuild_page(self.page, self.state, selected_index=1)

    def _get_ops_df(self):
        """Get the df for the currently selected operations account."""
        idx = self.state.ops_acc_idx
        if idx is None:
            return None
        acc = self.state.get_account(idx)
        return acc["df"] if acc else None

    def _get_ops_broker(self):
        idx = self.state.ops_acc_idx
        if idx is None:
            return None
        return self.state.brokers.get(idx)

    # ── Cash Tab ──────────────────────────────────────────────────────

    def _build_cash_tab(self) -> ft.Control:
        t = self.state.translator
        no_account = self.state.ops_acc_idx is None
        self.cash_type = ft.RadioGroup(
            value="deposit",
            disabled=no_account,
            content=ft.Row([
                ft.Radio(value="deposit", label=t.get("cash.op_deposit"), disabled=no_account),
                ft.Radio(value="withdrawal", label=t.get("cash.op_withdrawal"), disabled=no_account),
                ft.Radio(value="dividend", label=t.get("cash.op_dividend"), disabled=no_account),
                ft.Radio(value="charge", label=t.get("cash.op_charge"), disabled=no_account),
            ], wrap=True, opacity=0.4 if no_account else 1.0),
            on_change=self._on_cash_type_change,
        )
        self.cash_date_btn = ft.ElevatedButton(
            t.get("components.pick_date"), icon=ft.Icons.CALENDAR_TODAY,
            on_click=self._open_cash_date_picker,
        )
        self.cash_date_label = ft.Text("")
        self.cash_date_value = None

        self.cash_amount = ft.TextField(label=t.get("cash.amount"),
                                        keyboard_type=ft.KeyboardType.NUMBER,
                                        border_radius=ft.border_radius.all(15),
                                        col={"xs": 12, "md": 6})
        self.cash_ticker = ft.TextField(label=t.get("cash.dividend_ticker"),
                                        border_radius=ft.border_radius.all(15),
                                        visible=False, col={"xs": 12, "md": 6})
        self.cash_descr = ft.TextField(label=t.get("cash.charge_verbose"),
                                       border_radius=ft.border_radius.all(15),
                                       visible=False, col={"xs": 12, "md": 6})
        self.cash_loading = ft.ProgressRing(visible=False, width=30, height=30)

        return ft.Container(
            content=ft.Column([
                self.cash_type,
                ft.Row([self.cash_date_btn, self.cash_date_label]),
                ft.ResponsiveRow([self.cash_amount, self.cash_ticker, self.cash_descr]),
                ft.Row([
                    ft.ElevatedButton(
                        t.get("operations.add_transaction"),
                        icon=ft.Icons.ADD,
                        on_click=self._submit_cash),
                    self.cash_loading,
                ]),
            ], spacing=15),
            padding=20,
        )

    def _on_cash_type_change(self, e):
        kind = self.cash_type.value
        self.cash_ticker.visible = (kind == "dividend")
        self.cash_descr.visible = (kind == "charge")
        self.page.update()

    def _open_cash_date_picker(self, e):
        dp = ft.DatePicker(
            first_date=datetime(2000, 1, 1),
            last_date=datetime.now(),
            on_change=self._on_cash_date_picked,
        )
        self.page.show_dialog(dp)

    def _on_cash_date_picked(self, e):
        picked = e.control.value
        if isinstance(picked, datetime):
            picked = (picked + timedelta(hours=12)).date()
        self.cash_date_value = picked
        self.cash_date_label.value = picked.strftime(DATE_FORMAT)
        self.page.update()

    def _submit_cash(self, e):
        s = self.state
        t = s.translator
        df = self._get_ops_df()
        broker = self._get_ops_broker()
        if df is None or broker is None:
            show_snack(self.page, t.get("operations.select_account"), error=True)
            return

        if self.cash_date_value is None:
            show_snack(self.page, t.get("dates.error"), error=True)
            return
        try:
            amount = float(self.cash_amount.value)
        except (ValueError, TypeError):
            show_snack(self.page, t.get("cash.cash_error"), error=True)
            return

        kind = self.cash_type.value
        if kind == "deposit_withdrawal" and amount == 0:
            show_snack(self.page, t.get("cash.cash_error"), error=True)
            return
        if kind == "dividend" and amount <= 0:
            show_snack(self.page, t.get("cash.dividend_error"), error=True)
            return
        if kind == "charge" and amount <= 0:
            show_snack(self.page, t.get("cash.charge_error"), error=True)
            return

        date_str = self.cash_date_value.strftime(DATE_FORMAT)
        ref_date = self.cash_date_value
        ticker = self.cash_ticker.value if kind == "dividend" else None
        descr = self.cash_descr.value if kind == "charge" else None
        acc_idx = s.ops_acc_idx

        self.cash_loading.visible = True
        self.page.update()

        def worker():
            try:
                new_df = operations_service.execute_cash_operation(
                    t, df, broker, kind, date_str, ref_date, amount,
                    ticker=ticker, description=descr,
                )
                s.accounts[acc_idx]["df"] = new_df
                show_snack(self.page, "OK")
                self._refresh_page()
            except (RuntimeError, ValidationError, Exception) as ex:
                show_snack(self.page, str(ex), error=True)
            finally:
                self.cash_loading.visible = False
                self.page.update()

        self.page.run_thread(worker)

    # ── ETF / Stock Tab ───────────────────────────────────────────────

    def _build_etf_stock_tab(self, product_type: str) -> ft.Control:
        t = self.state.translator

        date_btn = ft.ElevatedButton(
            t.get("components.pick_date"), icon=ft.Icons.CALENDAR_TODAY,
            on_click=lambda e, pt=product_type: self._open_es_date_picker(e, pt),
        )
        date_label = ft.Text("")

        currency_dd = ft.Dropdown(
            label=t.get("stock.currency"),
            options=[
                ft.dropdown.Option(key=str(CURRENCY_EUR), text="EUR"),
                ft.dropdown.Option(key=str(CURRENCY_USD), text="USD"),
            ],
            value=str(CURRENCY_EUR),
            on_select=lambda e, pt=product_type: self._on_currency_change(e, pt),
            col={"xs": 6, "md": 4},
        )
        exch_rate = ft.TextField(label=t.get("stock.exch_rate"),
                                 keyboard_type=ft.KeyboardType.NUMBER,
                                 border_radius=ft.border_radius.all(15),
                                 visible=False, col={"xs": 6, "md": 4})
        ticker_field = ft.TextField(label="Ticker",
                                    border_radius=ft.border_radius.all(15),
                                    col={"xs": 12, "md": 6})
        quantity_field = ft.TextField(label=t.get("stock.qt"),
                                      border_radius=ft.border_radius.all(15),
                                     keyboard_type=ft.KeyboardType.NUMBER,
                                     col={"xs": 6, "md": 3})
        price_field = ft.TextField(label=t.get("stock.price"),
                                   border_radius=ft.border_radius.all(15),
                                   keyboard_type=ft.KeyboardType.NUMBER,
                                   col={"xs": 6, "md": 3})
        fee_currency_dd = ft.Dropdown(
            label=t.get("stock.currency_fee").strip().split("\n")[0],
            options=[
                ft.dropdown.Option(key=str(CURRENCY_EUR), text="EUR"),
                ft.dropdown.Option(key=str(CURRENCY_USD), text="USD"),
            ],
            value=str(CURRENCY_EUR),
            visible=False, col={"xs": 6, "md": 4},
        )
        fee_field = ft.TextField(label=t.get("stock.fee"),
                                 border_radius=ft.border_radius.all(15),
                                 keyboard_type=ft.KeyboardType.NUMBER,
                                 col={"xs": 6, "md": 3})
        ter_field = ft.TextField(label="TER (%)",
                                 border_radius=ft.border_radius.all(15),
                                 visible=(product_type == "ETF"),
                                 col={"xs": 6, "md": 3})
        loading = ft.ProgressRing(visible=False, width=30, height=30)

        tab_data = {
            "date_btn": date_btn, "date_label": date_label, "date_value": None,
            "currency_dd": currency_dd, "exch_rate": exch_rate,
            "ticker": ticker_field, "quantity": quantity_field, "price": price_field,
            "fee_currency_dd": fee_currency_dd, "fee": fee_field, "ter": ter_field,
            "loading": loading, "product_type": product_type,
        }
        if not hasattr(self, "_es_tabs"):
            self._es_tabs = {}
        self._es_tabs[product_type] = tab_data

        return ft.Container(
            content=ft.Column([
                ft.Row([date_btn, date_label]),
                ft.ResponsiveRow([currency_dd, exch_rate]),
                ft.ResponsiveRow([ticker_field, quantity_field, price_field]),
                ft.Text(t.get("stock.price_error"), size=11, italic=True, color=ft.Colors.GREY_500),
                ft.ResponsiveRow([fee_currency_dd, fee_field, ter_field]),
                ft.Row([
                    ft.ElevatedButton(
                        t.get("operations.add_transaction"),
                        icon=ft.Icons.ADD,
                        on_click=lambda e, 
                        pt=product_type: self._submit_es(e, pt)),
                    loading,
                ]),
            ], spacing=12),
            padding=20,
        )

    def _open_es_date_picker(self, e, product_type):
        dp = ft.DatePicker(
            first_date=datetime(2000, 1, 1),
            last_date=datetime.now(),
            on_change=lambda ev, pt=product_type: self._on_es_date_picked(ev, pt),
        )
        self.page.show_dialog(dp)

    def _on_es_date_picked(self, e, product_type):
        picked = e.control.value
        if isinstance(picked, datetime):
            picked = (picked + timedelta(hours=12)).date()
        tab = self._es_tabs[product_type]
        tab["date_value"] = picked
        tab["date_label"].value = picked.strftime(DATE_FORMAT)
        self.page.update()

    def _on_currency_change(self, e, product_type):
        tab = self._es_tabs[product_type]
        is_usd = (e.control.value == str(CURRENCY_USD))
        tab["exch_rate"].visible = is_usd
        tab["fee_currency_dd"].visible = is_usd
        self.page.update()

    def _submit_es(self, e, product_type):
        s = self.state
        t = s.translator
        tab = self._es_tabs[product_type]
        df = self._get_ops_df()
        broker = self._get_ops_broker()
        if df is None or broker is None:
            show_snack(self.page, t.get("operations.select_account"), error=True)
            return

        if tab["date_value"] is None:
            show_snack(self.page, t.get("dates.error"), error=True)
            return

        try:
            currency_int = int(tab["currency_dd"].value)
            ticker = tab["ticker"].value.strip()
            quantity = int(tab["quantity"].value)
            price = float(tab["price"].value)
            fee = float(tab["fee"].value)
        except (ValueError, TypeError) as ex:
            show_snack(self.page, str(ex), error=True)
            return

        if not ticker:
            show_snack(self.page, "Ticker required", error=True)
            return
        if quantity <= 0:
            show_snack(self.page, t.get("stock.qt_error"), error=True)
            return
        if price == 0:
            show_snack(self.page, t.get("stock.price_error"), error=True)
            return
        if fee < 0:
            show_snack(self.page, t.get("stock.fee_error"), error=True)
            return

        conv_rate = 1.0
        if currency_int == CURRENCY_USD:
            try:
                exch = float(tab["exch_rate"].value)
                if exch <= 0:
                    raise ValueError
                conv_rate = round_half_up(1.0 / exch, decimal="0.000001")
            except (ValueError, TypeError):
                show_snack(self.page, t.get("stock.exch_rate_error"), error=True)
                return
            fee_currency = int(tab["fee_currency_dd"].value)
            if fee_currency == CURRENCY_USD:
                fee = round_half_up(fee / conv_rate, decimal="0.000001")

        ter = np.nan
        if product_type == "ETF":
            ter_val = tab["ter"].value
            if ter_val:
                ter = ter_val.strip().rstrip("%") + "%"

        date_str = tab["date_value"].strftime(DATE_FORMAT)
        ref_date = tab["date_value"]
        acc_idx = s.ops_acc_idx

        tab["loading"].visible = True
        self.page.update()

        def worker():
            try:
                new_df = operations_service.execute_etf_stock(
                    t, df, broker, date_str, ref_date,
                    currency_int, conv_rate, ticker, quantity, price,
                    fee, ter, product_type,
                )
                s.accounts[acc_idx]["df"] = new_df
                show_snack(self.page, "OK")
                self._refresh_page()
            except (RuntimeError, ValidationError, Exception) as ex:
                show_snack(self.page, str(ex), error=True)
            finally:
                tab["loading"].visible = False
                self.page.update()

        self.page.run_thread(worker)

    def _refresh_page(self):
        from views import _rebuild_page
        _rebuild_page(self.page, self.state, selected_index=1)
