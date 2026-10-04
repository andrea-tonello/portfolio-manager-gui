import flet as ft
import numpy as np
import pandas as pd
from datetime import date

from components.background import run_in_background
from components.date_field import DateField
from components.dialogs import show_info_dialog
from components.focus_chain import chain_focus, scroll_into_view_on_focus
from components.inputs import DECIMAL_INPUT_FILTER, account_selector, rounded_dropdown, rounded_text_field
from components.snack import show_snack
from components.ticker_search import TickerSearchField
from domain.ledger import Product
from domain.positions import held_tickers
from domain.tax import DEFAULT_CAPITAL_GAINS_TAX_RATE
from services import operations_service
from services.market_data import search_tickers
from utils.other_utils import round_half_up
from utils.constants import CURRENCIES, DATE_FORMAT


class OperationsView:
    def __init__(self, app):
        """Build the Operations tab for the controller's page and current state."""
        self.app = app
        self.page = app.page
        self.state = app.state


    def build(self) -> ft.Control:
        t = self.state.translator
        if not self.state.brokers:
            return ft.Text(t.get("home.no_account"), size=16)

        has_account = self.state.ops_acc_idx is not None
        self._ops_tab_index = 0
        self.form_container = ft.Container(disabled=not has_account, expand=True, width=800,)

        cash_content = self._build_cash_tab()
        etf_content = self._build_etf_stock_tab("ETF")
        stock_content = self._build_etf_stock_tab("Stock")

        self.form_container.content = ft.Tabs(
            length=3,
            selected_index=0,
            on_change=self._on_ops_tab_change,
            content=ft.Column([
                ft.TabBar(tabs=[
                    ft.Tab(label=t.get("operations.general.title")),
                    ft.Tab(label=t.get("operations.stock.title_etf")),
                    ft.Tab(label=t.get("operations.stock.title_stock")),
                ], scrollable=True, splash_border_radius=ft.BorderRadius.only(top_left=10, top_right=10)),
                ft.TabBarView(
                    controls=[cash_content, etf_content, stock_content],
                    expand=True,
                ),
            ], expand=True),
            expand=True, adaptive=True
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
        idx = self.state.ops_acc_idx
        return account_selector(self.state, None if idx is None else str(idx), self._on_account_selected,
                                hint_text=t.get("operations.select_account"))

    def _on_account_selected(self, e):
        idx = int(e.control.value)
        self.state.ops_acc_idx = idx
        self.app.refresh()

    def _on_ops_tab_change(self, e):
        self._ops_tab_index = e.control.selected_index

    def _get_ops_df(self):
        """Get the df for the currently selected operations account."""
        idx = self.state.ops_acc_idx
        if idx is None:
            return None
        account = self.state.get_account(idx)
        return account.df if account else None

    def _get_ops_broker(self):
        idx = self.state.ops_acc_idx
        if idx is None:
            return None
        return self.state.brokers.get(idx)

    def _is_before_last_entry(self, df, date_value) -> bool:
        """Return `True` if `date_value` is earlier than the last operation recorded in `df`.

        Operations must be entered in date order, because each new row builds on
        the totals of the previous one; `True` means the new entry must be refused.
        Same-day operations are accepted.
        """
        dates = pd.to_datetime(df["date"], dayfirst=True, errors="coerce").dropna()
        return not dates.empty and date_value < dates.max().date()

    # ── Cash Tab ──────────────────────────────────────────────────────

    def _build_cash_tab(self) -> ft.Control:
        t = self.state.translator
        no_account = self.state.ops_acc_idx is None
        df = self._get_ops_df()
        holdings = self._get_held_tickers(df) if df is not None else []
        header_color = ft.Colors.with_opacity(0.6, ft.Colors.ON_SURFACE)

        split_help = self._help_button("operations.split.title", "operations.split.descr")

        self.cash_type = ft.RadioGroup(
            value="deposit",
            disabled=no_account,
            content=ft.Column([
                ft.Text(t.get("operations.general.cash_section"),
                        size=16, weight=ft.FontWeight.BOLD, color=header_color),
                ft.Container(height=8),
                ft.Radio(value="deposit", label=t.get("operations.cash.op_deposit"), disabled=no_account),
                ft.Radio(value="withdrawal", label=t.get("operations.cash.op_withdrawal"), disabled=no_account),
                ft.Radio(value="charge", label=t.get("operations.cash.op_charge"), disabled=no_account),
                ft.Container(height=15),
                ft.Text(t.get("operations.general.corporate_section"),
                        size=16, weight=ft.FontWeight.BOLD, color=header_color),
                ft.Container(height=8),
                ft.Radio(value="dividend", label=t.get("operations.cash.op_dividend"), disabled=no_account),
                ft.Row([
                    ft.Radio(value="split", label=t.get("operations.split.title"), disabled=no_account),
                    ft.Container(expand=True),
                    split_help,
                ], spacing=0),
                ft.Divider(),
            ], spacing=0, opacity=0.4 if no_account else 1.0),
            on_change=self._on_cash_type_change,
        )
        self.cash_date = DateField(self.page, t.get("components.pick_date"), t.get("components.date_format_hint"))

        self.cash_amount = rounded_text_field(label=t.get("operations.cash.amount"),
                                              keyboard_type=ft.KeyboardType.NUMBER,
                                              input_filter=DECIMAL_INPUT_FILTER,
                                              col={"xs": 12, "md": 6})
        self.cash_ticker = TickerSearchField(
            self.page,
            label=t.get("operations.stock.ticker"),
            expand=True,
        )
        cash_ticker_help = self._help_button("operations.stock.ticker", "operations.stock.ticker_explained")
        self.cash_ticker_row = ft.Container(
            content=ft.Row([self.cash_ticker.control, cash_ticker_help]),
            visible=False, col={"xs": 12, "md": 6},
        )
        self.cash_descr = rounded_text_field(label=t.get("operations.cash.charge_descr"),
                                             visible=False, col={"xs": 12, "md": 6})

        split_ticker_options = [
            ft.dropdown.Option(key=tk, text=f"{tk}  ·  {name}" if name and name != tk else tk)
            for tk, name in holdings
        ]
        self.split_ticker_dd = rounded_dropdown(
            label=t.get("operations.split.ticker"),
            options=split_ticker_options,
            expand=True,
        )
        self.split_ticker_row = ft.Container(
            content=self.split_ticker_dd, visible=False, col={"xs": 12, "md": 6},
        )
        self.split_ratio_field = rounded_text_field(
            label=t.get("operations.split.ratio"),
            keyboard_type=ft.KeyboardType.NUMBER,
            input_filter=DECIMAL_INPUT_FILTER,
            expand=True,
        )
        split_ratio_help = self._help_button("operations.split.ratio_example", "operations.split.ratio_descr")
        self.split_ratio_row = ft.Container(
            content=ft.Row([self.split_ratio_field, split_ratio_help]),
            visible=False, col={"xs": 12, "md": 6},
        )

        self.cash_loading = ft.ProgressRing(visible=False, width=30, height=30)

        # Chain on_submit for keyboard "next field" navigation (skips hidden fields)
        # Tuples: (field_to_focus, control_to_check_visibility)
        cash_fields = [
            self.cash_date.field,
            (self.cash_amount, self.cash_amount),
            (self.cash_ticker._field, self.cash_ticker_row),
            (self.cash_descr, self.cash_descr),
            (self.split_ratio_field, self.split_ratio_row),
        ]
        chain_focus(cash_fields)

        cash_submit_btn = ft.FilledButton(
            t.get("operations.add_transaction"),
            icon=ft.Icons.ADD,
            on_click=self._submit_cash,
            disabled=no_account,
            style=ft.ButtonStyle(padding=ft.Padding.symmetric(horizontal=32, vertical=18)),
        )

        col = ft.Column([
            self.cash_type,
            self.cash_date.control,
            ft.ResponsiveRow([
                self.cash_amount, self.cash_ticker_row, self.cash_descr,
                self.split_ticker_row, self.split_ratio_row,
            ],),
            ft.Row([ft.Container(width=5), self.cash_loading]),
            ft.Row([cash_submit_btn], alignment=ft.MainAxisAlignment.CENTER),
            ft.Container(height=20),
        ], spacing=15, scroll=ft.ScrollMode.AUTO)

        scroll_into_view_on_focus(col, [
            self.cash_date.field, self.cash_amount, self.cash_ticker, self.cash_descr, self.split_ratio_field,
        ], prefix="cash")

        return ft.Container(content=col, padding=20, expand=True)

    def _on_cash_type_change(self, e):
        t = self.state.translator
        kind = self.cash_type.value

        if kind == "split" and not self._get_held_tickers(self._get_ops_df()):
            show_snack(self.page, t.get("operations.split.no_holdings"), error=True)
            self.cash_type.value = "deposit"
            kind = "deposit"

        is_split = (kind == "split")
        self.cash_amount.visible = not is_split
        self.cash_ticker_row.visible = (kind == "dividend")
        self.cash_descr.visible = (kind == "charge")
        self.split_ticker_row.visible = is_split
        self.split_ratio_row.visible = is_split
        self.cash_amount.label = (
            t.get("operations.cash.dividend_amount") if kind == "dividend"
            else t.get("operations.cash.amount")
        )
        self.page.update()

    def _submit_cash(self, e):
        s = self.state
        t = s.translator
        df = self._get_ops_df()
        broker = self._get_ops_broker()
        if df is None or broker is None:
            show_snack(self.page, t.get("operations.select_account"), error=True)
            return

        if self.cash_date.value is None:
            show_snack(self.page, t.get("misc_errors.nodate"), error=True)
            return
        if self.cash_date.value > date.today():
            show_snack(self.page, t.get("misc_errors.date_future"), error=True)
            return
        if self._is_before_last_entry(df, self.cash_date.value):
            show_snack(self.page, t.get("misc_errors.date_sequential"), error=True)
            return

        kind = self.cash_type.value
        if kind == "split":
            self._submit_split_from_general()
            return

        try:
            amount = float(self.cash_amount.value)
        except (ValueError, TypeError):
            show_snack(self.page, t.get("operations.cash.error_cash"), error=True)
            return

        if kind in ("deposit", "withdrawal") and amount <= 0:
            show_snack(self.page, t.get("operations.cash.error_cash"), error=True)
            return
        if kind == "dividend" and amount <= 0:
            show_snack(self.page, t.get("operations.cash.error_dividend"), error=True)
            return
        if kind == "charge" and amount <= 0:
            show_snack(self.page, t.get("operations.cash.error_charge"), error=True)
            return

        if kind == "withdrawal":
            amount = -amount
        service_kind = "deposit_withdrawal" if kind in ("deposit", "withdrawal") else kind

        date_str = self.cash_date.value.strftime(DATE_FORMAT)
        ref_date = self.cash_date.value
        ticker = self.cash_ticker.value if kind == "dividend" else None
        descr = self.cash_descr.value if kind == "charge" else None
        acc_idx = s.ops_acc_idx

        def save():
            """Record the cash operation, save the account and show the tab again."""
            new_df = operations_service.execute_cash_operation(
                df, broker, service_kind, date_str, ref_date, amount,
                ticker=ticker, description=descr,
            )
            s.commit(acc_idx, new_df)
            show_snack(self.page, t.get("operations.added_transaction"))
            self.app.refresh()

        run_in_background(self.page, t, save, loading=self.cash_loading)

    # ── ETF / Stock Tab ───────────────────────────────────────────────

    def _build_etf_stock_tab(self, product_type: str) -> ft.Control:
        t = self.state.translator

        no_account = self.state.ops_acc_idx is None
        buy_label = ft.Text(t.get("operations.stock.op_buy"), weight=ft.FontWeight.BOLD)
        sell_label = ft.Text(t.get("operations.stock.op_sell"))

        def _on_switch_toggle(e, bl=buy_label, sl=sell_label):
            is_sell = e.control.value
            bl.weight = ft.FontWeight.NORMAL if is_sell else ft.FontWeight.BOLD
            sl.weight = ft.FontWeight.BOLD if is_sell else ft.FontWeight.NORMAL
            e.control.thumb_icon = ft.Icons.REMOVE if is_sell else ft.Icons.ADD
            self.page.update()

        es_type = ft.Row(
            [
                buy_label,
                ft.Switch(
                    value=False, disabled=no_account, on_change=_on_switch_toggle,
                    thumb_color={
                        ft.ControlState.DEFAULT: ft.Colors.PRIMARY,
                        ft.ControlState.SELECTED: ft.Colors.SURFACE,
                    },
                    track_color=ft.Colors.PRIMARY_CONTAINER,
                    track_outline_color=ft.Colors.TRANSPARENT,
                    thumb_icon=ft.Icons.ADD,
                ),
                sell_label,
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            opacity=0.4 if no_account else 1.0,
        )

        date_input = DateField(self.page, t.get("components.pick_date"), t.get("components.date_format_hint"))
        date_row = ft.Container(
            content=date_input.control,
            col={"xs": 12, "md": 6},
        )


        ticker_field = TickerSearchField(
            self.page,
            label="Ticker",
            type_filter="etf" if product_type == "ETF" else "equity",
            expand=True,
        )
        ticker_help = self._help_button("operations.stock.ticker", "operations.stock.ticker_explained")
        ticker_row = ft.Container(
            content=ft.Row([ticker_field.control, ticker_help]),
            col={"xs": 12, "md": 6},
        )


        ter_field = rounded_text_field(
            label=t.get("operations.stock.ter"),
            keyboard_type=ft.KeyboardType.NUMBER,
            input_filter=DECIMAL_INPUT_FILTER,
            col={"xs":12, "md": 6},
            expand=True
        )
        ter_help = self._help_button("operations.stock.ter", "operations.stock.ter_explained")
        ter_row = ft.Container(
            content=ft.Row([ter_field, ter_help]),
            col={"xs": 12, "md": 6},
            visible=(product_type == "ETF"),
        )

        tax_bracket_field = rounded_text_field(
            label=t.get("operations.stock.tax_bracket"),
            keyboard_type=ft.KeyboardType.NUMBER,
            input_filter=DECIMAL_INPUT_FILTER,
            col={"xs": 12, "md": 6},
            expand=True
        )
        tax_help = self._help_button("operations.stock.tax_bracket", "operations.stock.tax_explained")
        tax_row = ft.Container(
            content=ft.Row([tax_bracket_field, tax_help]),
            col={"xs": 12, "md": 6},
            visible=False,
        )


        currency_dd = rounded_dropdown(
            label=t.get("operations.stock.currency"),
            options=[ft.dropdown.Option(key=code, text=code) for code in CURRENCIES],
            value="EUR",
            on_select=lambda e, pt=product_type: self._on_currency_change(e, pt),
            col={"xs": 6, "md": 6},
            expand=True,
        )
        exch_rate = rounded_text_field(label=t.get("operations.stock.exch_rate"),
            keyboard_type=ft.KeyboardType.NUMBER,
            input_filter=DECIMAL_INPUT_FILTER,
            visible=False, col={"xs": 6, "md": 6}
        )


        quantity_field = rounded_text_field(label=t.get("operations.stock.qt"),
                                            keyboard_type=ft.KeyboardType.NUMBER,
                                            input_filter=DECIMAL_INPUT_FILTER,
                                            col={"xs": 6, "md": 6})
        price_field = rounded_text_field(label=t.get("operations.stock.price"),
                                         keyboard_type=ft.KeyboardType.NUMBER,
                                         input_filter=DECIMAL_INPUT_FILTER,
                                         col={"xs": 6, "md": 6})


        fee_currency_dd = rounded_dropdown(
            label=t.get("operations.stock.currency_fee"),
            options=[ft.dropdown.Option(key=code, text=code) for code in CURRENCIES],
            value="EUR",
            visible=False, col={"xs": 6, "md": 6},
            expand=True,
        )
        fee_field = rounded_text_field(label=t.get("operations.stock.fee"),
                                       keyboard_type=ft.KeyboardType.NUMBER,
                                       input_filter=DECIMAL_INPUT_FILTER,
                                       col={"xs": 6, "md": 6})


        fee_mode_help = ft.FilledTonalIconButton(
            icon=ft.Icons.HELP_OUTLINE,
            on_click=self._show_fee_help,
        )
        fee_mode_title = ft.Row([
            ft.Text("  " + t.get("operations.stock.fee_mode_title"), size=18,
                    opacity=0.4 if no_account else 1.0),
            fee_mode_help
        ], expand=True, alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
        fee_mode_group = ft.RadioGroup(
            value=None,
            disabled=no_account,
            content=ft.Column([
                ft.Radio(value="abp", label=t.get("operations.stock.fee_mode_abp")),
                ft.Radio(value="buy_loss", label=t.get("operations.stock.fee_mode_buy_loss")),
                ft.Radio(value="sell_loss", label=t.get("operations.stock.fee_mode_sell_loss")),
            ], spacing=0, opacity=0.4 if no_account else 1.0),
        )
        fee_mode_container = ft.Container(
            content=ft.Column([
                fee_mode_title,
                fee_mode_group,
            ], spacing=10,),
            border=ft.Border.all(width=1, 
                color=ft.Colors.with_opacity(0.20, ft.Colors.GREY) if no_account else ft.Colors.with_opacity(0.40, ft.Colors.GREY)),
            border_radius=15,
            padding=10,
            visible=(product_type == "ETF"),
        )

        loading = ft.ProgressRing(visible=False, width=30, height=30)

        # Chain on_submit for keyboard "next field" navigation (skips hidden fields)
        es_fields = [
            date_input.field, ticker_field._field, exch_rate,
            quantity_field, price_field, fee_field, ter_field,
        ]
        chain_focus(es_fields)

        tab_data = {
            "es_type": es_type,
            "date": date_input,
            "currency_dd": currency_dd, "exch_rate": exch_rate,
            "ticker": ticker_field, "quantity": quantity_field, "price": price_field,
            "fee_currency_dd": fee_currency_dd, "fee": fee_field, "ter": ter_field,
            "tax_bracket": tax_bracket_field,
            "fee_mode": fee_mode_group,
            "loading": loading, "product_type": product_type,
        }
        if not hasattr(self, "_es_tabs"):
            self._es_tabs = {}
        self._es_tabs[product_type] = tab_data

        es_submit_btn = ft.FilledButton(
            t.get("operations.add_transaction"),
            icon=ft.Icons.ADD,
            on_click=lambda ev, pt=product_type: self._submit_es(ev, pt),
            disabled=no_account,
            style=ft.ButtonStyle(padding=ft.Padding.symmetric(horizontal=32, vertical=18)),
        )

        stock_etf_form = ft.Column([
            es_type,
            ft.Container(height=5),
            ft.ResponsiveRow([date_row, ticker_row]),
            ft.ResponsiveRow([currency_dd, exch_rate]),
            ft.ResponsiveRow([quantity_field, price_field]),
            ft.ResponsiveRow([fee_currency_dd, fee_field, ter_row, tax_row]),
            fee_mode_container,
            ft.Row([ft.Container(width=5), loading]),
            ft.Row([es_submit_btn], alignment=ft.MainAxisAlignment.CENTER),
            ft.Container(height=20),
        ], spacing=12)

        scrolling_fields = [date_input.field, exch_rate, ticker_field, quantity_field, price_field, fee_field, ter_field]
        if product_type != "ETF":
            stock_etf_form.scroll = ft.ScrollMode.AUTO
            scroll_into_view_on_focus(stock_etf_form, scrolling_fields, prefix=product_type)
            return ft.Container(content=stock_etf_form, padding=20, expand=True)

        # ── ETF sub-type selector ───────────────────────────────

        bond_text = ft.Text("\n\nBonds ETFs Rolling Maturity\n\nComing soon", size=16,
                            text_align=ft.TextAlign.CENTER)
        bond_placeholder = ft.Container(
            bond_text, alignment=ft.alignment.Alignment.CENTER, expand=True, visible=False,
        )

        def _on_bond_maturity_toggle(e):
            if e.control.value:
                bond_text.value = "\n\nBonds ETFs Fixed Maturity\n\nComing soon"
            else:
                bond_text.value = "\n\nBonds ETFs Rolling Maturity\n\nComing soon"
            tab_data["bond_fixed_maturity"] = e.control.value
            self.page.update()

        bond_maturity_switch = ft.Switch(label=t.get("operations.stock.fixed"), value=False,
                                         disabled=True,
                                         label_position=ft.LabelPosition.LEFT,
                                         on_change=_on_bond_maturity_toggle)

        # The radio values are the product codes stored in the CSV (e.g. "ETF-M").
        def _on_etf_subtype_change(e):
            val = e.control.value
            stock_etf_form.visible = val in (Product.ETF_STOCK, Product.ETF_MM)
            bond_placeholder.visible = val == Product.ETF_BOND
            bond_maturity_switch.disabled = val != Product.ETF_BOND
            tax_row.visible = val == Product.ETF_MM
            tab_data["etf_subtype"] = val
            self.page.update()

        etf_subtype_group = ft.RadioGroup(
            value=Product.ETF_STOCK,
            on_change=_on_etf_subtype_change,
            content=ft.Column([
                ft.Radio(value=Product.ETF_STOCK, label=t.get("operations.stock.stock_etf")),
                ft.Radio(value=Product.ETF_MM, label=t.get("operations.stock.mm_etf"),),
                ft.Row([
                    ft.Radio(value=Product.ETF_BOND, label=t.get("operations.stock.bonds_etf"),),
                    ft.Container(expand=True),
                    bond_maturity_switch,
                ], spacing=0),
            ], spacing=0, opacity=0.4 if no_account else 1.0),
        )
        tab_data["etf_subtype"] = Product.ETF_STOCK
        tab_data["bond_fixed_maturity"] = False

        outer = ft.Column([
            etf_subtype_group,
            stock_etf_form,
            bond_placeholder,
        ], spacing=12, scroll=ft.ScrollMode.AUTO)

        scroll_into_view_on_focus(outer, scrolling_fields, prefix=product_type)

        return ft.Container(content=outer, padding=20, expand=True)

    def _on_currency_change(self, e, product_type):
        tab = self._es_tabs[product_type]
        is_usd = (e.control.value == "USD")
        tab["exch_rate"].visible = is_usd
        tab["fee_currency_dd"].visible = is_usd
        self.page.update()

    def _submit_es(self, e, product_type):
        s = self.state
        t = s.translator
        tab = self._es_tabs[product_type]
        if product_type == "ETF" and tab["etf_subtype"] not in (Product.ETF_STOCK, Product.ETF_MM):
            show_snack(self.page, "Not yet implemented", error=True)
            return
        df = self._get_ops_df()
        broker = self._get_ops_broker()
        if df is None or broker is None:
            show_snack(self.page, t.get("operations.select_account"), error=True)
            return

        if tab["date"].value is None:
            show_snack(self.page, t.get("misc_errors.nodate"), error=True)
            return
        if tab["date"].value > date.today():
            show_snack(self.page, t.get("misc_errors.date_future"), error=True)
            return
        if self._is_before_last_entry(df, tab["date"].value):
            show_snack(self.page, t.get("misc_errors.date_sequential"), error=True)
            return

        currency = tab["currency_dd"].value

        ticker = tab["ticker"].value.strip()
        if not ticker:
            show_snack(self.page, t.get("operations.stock.ticker_error"), error=True)
            return

        try:
            quantity = int(tab["quantity"].value)
        except (ValueError, TypeError):
            show_snack(self.page, t.get("operations.stock.qt_error"), error=True)
            return
        if quantity <= 0:
            show_snack(self.page, t.get("operations.stock.qt_error"), error=True)
            return

        try:
            price = float(tab["price"].value)
        except (ValueError, TypeError):
            show_snack(self.page, t.get("operations.stock.price_error"), error=True)
            return
        if price <= 0:
            show_snack(self.page, t.get("operations.stock.price_error"), error=True)
            return

        fee_raw = tab["fee"].value.strip()
        if not fee_raw:
            fee = 0.0
        else:
            try:
                fee = float(fee_raw)
            except (ValueError, TypeError):
                show_snack(self.page, t.get("operations.stock.fee_error"), error=True)
                return
        if fee < 0:
            show_snack(self.page, t.get("operations.stock.fee_error"), error=True)
            return
        is_buy = not tab["es_type"].controls[1].value  # Switch off = Buy

        conv_rate = 1.0
        if currency == "USD":
            try:
                exch = float(tab["exch_rate"].value)
                if exch <= 0:
                    raise ValueError
                conv_rate = exch
            except (ValueError, TypeError):
                show_snack(self.page, t.get("operations.stock.exch_rate_error"), error=True)
                return
            if tab["fee_currency_dd"].value == "USD":
                fee = round_half_up(fee * conv_rate, decimal="0.000001")

        ter = np.nan
        if product_type == "ETF":
            ter_val = tab["ter"].value
            if ter_val:
                ter = ter_val.strip().rstrip("%") + "%"

        tax_rate = DEFAULT_CAPITAL_GAINS_TAX_RATE
        if product_type == "ETF" and tab["etf_subtype"] == Product.ETF_MM:
            try:
                tax_rate = float(tab["tax_bracket"].value)
                if not (0 <= tax_rate <= 100):
                    raise ValueError
                tax_rate = tax_rate / 100
            except (ValueError, TypeError):
                show_snack(self.page, t.get("operations.stock.tax_bracket_error"), error=True)
                return

        fee_mode = "abp"
        if product_type == "ETF":
            fee_mode = tab["fee_mode"].value
            if not fee_mode:
                show_snack(self.page, t.get("operations.stock.fee_mode_error"), error=True)
                return

        # The product stored in the CSV: the ETF type picked (already a product code), or Stock
        stored_product = tab["etf_subtype"] if product_type == "ETF" else Product.STOCK

        date_str = tab["date"].value.strftime(DATE_FORMAT)
        ref_date = tab["date"].value
        acc_idx = s.ops_acc_idx

        expected_type = "etf" if product_type == "ETF" else "equity"

        def save():
            """Check the ticker's kind with Yahoo, then record the trade, save the account and show the tab again."""
            results = search_tickers(ticker, quotes_count=1)
            if results and results[0]["symbol"].upper() == ticker.upper():
                if results[0]["quote_type"] != expected_type:
                    show_snack(self.page, t.get("operations.stock.ticker_wrong_type"), error=True)
                    return

            new_df = operations_service.execute_etf_stock(
                df, broker, date_str, ref_date,
                currency, conv_rate, ticker, quantity, price,
                fee, ter, stored_product, is_buy=is_buy, tax_rate=tax_rate, fee_mode=fee_mode,
            )
            s.commit(acc_idx, new_df)
            show_snack(self.page, t.get("operations.added_transaction"))
            self.app.refresh()

        run_in_background(self.page, t, save, loading=tab["loading"])

    def _help_button(self, title_key, body_key):
        """Return the round "?" button that opens a short explanation next to a field.

        Both texts come from the translations, e.g. ("operations.stock.ter",
        "operations.stock.ter_explained") explains what the TER of an ETF is.
        """
        t = self.state.translator
        return ft.FilledTonalIconButton(
            icon=ft.Icons.HELP_OUTLINE,
            on_click=lambda _: show_info_dialog(self.page, t.get(title_key), t.get(body_key)),
        )

    def _show_fee_help(self, e):
        """Explain the fee modes, with the longer text from fee_mode_help_<language>.txt."""
        t = self.state.translator
        show_info_dialog(self.page, t.get("operations.stock.fee_mode_title"),
                         t.load_text("fee_mode_help") or "Fee mode description not available.",
                         markdown=True, title_size=21)

    # ── Split helpers (shares the General tab layout) ────────────────

    def _get_held_tickers(self, df):
        """Return a list of (ticker, asset_name) for positions with qt_held > 0."""
        if df is None or df.empty:
            return []
        return [(ticker, name or ticker) for ticker, name in held_tickers(df).items()]

    def _submit_split_from_general(self):
        s = self.state
        t = s.translator
        df = self._get_ops_df()
        broker = self._get_ops_broker()

        ticker = self.split_ticker_dd.value
        if not ticker:
            show_snack(self.page, t.get("operations.stock.ticker_error"), error=True)
            return

        try:
            ratio = float(self.split_ratio_field.value)
        except (ValueError, TypeError):
            show_snack(self.page, t.get("operations.split.ratio_error"), error=True)
            return

        date_str = self.cash_date.value.strftime(DATE_FORMAT)
        ref_date = self.cash_date.value
        acc_idx = s.ops_acc_idx

        def save():
            """Record the split, save the account and show the tab again."""
            new_df = operations_service.execute_split(
                df, broker, date_str, ref_date, ticker, ratio,
            )
            s.commit(acc_idx, new_df)
            show_snack(self.page, t.get("operations.added_transaction"))
            self.app.refresh()

        run_in_background(self.page, t, save, loading=self.cash_loading)
