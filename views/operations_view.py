import flet as ft
import numpy as np
import pandas as pd
from datetime import date, datetime, timedelta

from components.focus_chain import chain_focus
from components.snack import show_snack

_DATE_FILTER = ft.InputFilter(r"^[0-9\-]*$")
_DECIMAL_FILTER = ft.InputFilter(r"^[0-9\.]*$")
from components.ticker_search import TickerSearchField
from services import account_service, operations_service
from utils.other_utils import round_half_up, ValidationError
from utils.constants import DATE_FORMAT, CURRENCY_EUR, CURRENCY_USD
from utils.date_utils import parse_date_input


class OperationsView:
    def __init__(self, page: ft.Page, state):
        self.page = page
        self.state = state


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
                    ft.Tab(label=t.get("operations.cash.title")),
                    ft.Tab(label=t.get("operations.stock.title_etf")),
                    ft.Tab(label=t.get("operations.stock.title_stock")),
                ], scrollable=True),
                ft.TabBarView(
                    controls=[cash_content, etf_content, stock_content],
                    expand=True,
                ),
            ], expand=True),
            expand=True,
        )

        add_btn = ft.FilledButton(
            t.get("operations.add_transaction"),
            icon=ft.Icons.ADD,
            on_click=self._on_add_transaction,
            disabled=not has_account,
            style=ft.ButtonStyle(
                padding=ft.padding.symmetric(horizontal=32, vertical=18),
            ),
        )

        return ft.Stack([
            # 1. Wrap the main Column in a Row to force full-screen width
            ft.Row(
                controls=[
                    ft.Column([
                        # Added width=600 here so the dropdown matches the form width
                        ft.Container(self._build_account_dropdown(), padding=ft.padding.only(top=5, left=5, right=5)),
                        self.form_container,
                    ], 
                    expand=True, 
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER)
                ],
                alignment=ft.MainAxisAlignment.CENTER, # 2. Force the inner Column dead center
                expand=True # 3. Ensure the Row takes up the entire horizontal space
            ),
            # Add button remains pinned to the bottom
            ft.Container(
                ft.Row([add_btn], alignment=ft.MainAxisAlignment.CENTER),
                left=0, right=0, bottom=20,
            ),
        ], expand=True)



    def _build_account_dropdown(self) -> ft.Control:
        t = self.state.translator
        options = [
            ft.dropdown.Option(key=str(k), text=v)
            for k, v in sorted(self.state.brokers.items())
        ]
        return ft.Dropdown(
            menu_style=ft.MenuStyle(
                shape=ft.RoundedRectangleBorder(radius=15),
            ),
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

    def _on_ops_tab_change(self, e):
        self._ops_tab_index = e.control.selected_index

    def _on_add_transaction(self, e):
        if self._ops_tab_index == 0:
            self._submit_cash(e)
        elif self._ops_tab_index == 1:
            self._submit_es(e, "ETF")
        else:
            self._submit_es(e, "Stock")

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

    def _check_date_sequential(self, df, date_value) -> bool:
        """Return True if date_value is before the last recorded date."""
        dates = pd.to_datetime(df["date"], dayfirst=True, errors="coerce").dropna()
        return not dates.empty and date_value < dates.max().date()

    # ── Cash Tab ──────────────────────────────────────────────────────

    def _build_cash_tab(self) -> ft.Control:
        t = self.state.translator
        no_account = self.state.ops_acc_idx is None
        self.cash_type = ft.RadioGroup(
            value="deposit",
            disabled=no_account,
            content=ft.Column([
                ft.Radio(value="deposit", label=t.get("operations.cash.op_deposit"), disabled=no_account),
                ft.Radio(value="withdrawal", label=t.get("operations.cash.op_withdrawal"), disabled=no_account),
                ft.Radio(value="dividend", label=t.get("operations.cash.op_dividend"), disabled=no_account),
                ft.Radio(value="charge", label=t.get("operations.cash.op_charge"), disabled=no_account),
            ], spacing=0, opacity=0.4 if no_account else 1.0),
            on_change=self._on_cash_type_change,
        )
        self.cash_date_field = ft.TextField(
            label=t.get("components.pick_date"),
            hint_text=t.get("components.date_format_hint"),
            border_radius=ft.border_radius.all(15),
            border_color=ft.Colors.with_opacity(0.40, ft.Colors.GREY),
            keyboard_type=ft.KeyboardType.DATETIME,
            input_filter=_DATE_FILTER,
            on_change=self._on_cash_date_typed,
            expand=True,
        )
        self.cash_date_icon = ft.FilledTonalIconButton(
            icon=ft.Icons.CALENDAR_MONTH,
            on_click=self._open_cash_date_picker,
        )
        self.cash_date_value = None

        self.cash_amount = ft.TextField(label=t.get("operations.cash.amount"),
                                        keyboard_type=ft.KeyboardType.NUMBER,
                                        input_filter=_DECIMAL_FILTER,
                                        border_radius=ft.border_radius.all(15),
                                        border_color=ft.Colors.with_opacity(0.40, ft.Colors.GREY),
                                        col={"xs": 12, "md": 6})
        self.cash_ticker = TickerSearchField(
            self.page,
            label=t.get("operations.stock.ticker"),
            border_radius=ft.border_radius.all(15),
            border_color=ft.Colors.with_opacity(0.40, ft.Colors.GREY),
            expand=True,
        )
        self.cash_ticker_help = ft.FilledTonalIconButton(
            icon=ft.Icons.HELP_OUTLINE,
            on_click=self._show_ticker_help,
        )
        self.cash_ticker_row = ft.Container(
            content=ft.Row([self.cash_ticker.control, self.cash_ticker_help]),
            visible=False, col={"xs": 12, "md": 6},
        )
        self.cash_descr = ft.TextField(label=t.get("operations.cash.charge_descr"),
                                       border_radius=ft.border_radius.all(15),
                                       border_color=ft.Colors.with_opacity(0.40, ft.Colors.GREY),
                                       visible=False, col={"xs": 12, "md": 6})
        self.cash_loading = ft.ProgressRing(visible=False, width=30, height=30)

        # Chain on_submit for keyboard "next field" navigation (skips hidden fields)
        # Tuples: (field_to_focus, control_to_check_visibility)
        cash_fields = [
            self.cash_date_field,
            self.cash_amount,
            (self.cash_ticker._field, self.cash_ticker_row),
            (self.cash_descr, self.cash_descr),
        ]
        chain_focus(cash_fields)

        col = ft.Column([
            self.cash_type,
            ft.Row([self.cash_date_field, self.cash_date_icon],),
            ft.ResponsiveRow([self.cash_amount, self.cash_ticker_row, self.cash_descr],),
            ft.Row([ft.Container(width=5), self.cash_loading]),
            ft.Container(height=80),
        ], spacing=15, scroll=ft.ScrollMode.AUTO)

        async def on_focus(e):
            if hasattr(e.control, "key") and e.control.key:
                await col.scroll_to(scroll_key=e.control.key, duration=300)

        self.cash_date_field.key = "cash_date"
        self.cash_date_field.on_focus = on_focus
        self.cash_amount.key = "cash_amount"
        self.cash_amount.on_focus = on_focus
        self.cash_ticker.key = "cash_ticker"
        self.cash_ticker.on_focus = on_focus
        self.cash_descr.key = "cash_descr"
        self.cash_descr.on_focus = on_focus

        return ft.Container(content=col, padding=20, expand=True)

    def _on_cash_type_change(self, e):
        t = self.state.translator
        kind = self.cash_type.value
        self.cash_ticker_row.visible = (kind == "dividend")
        self.cash_descr.visible = (kind == "charge")
        self.cash_amount.label = (
            t.get("operations.cash.dividend_amount") if kind == "dividend"
            else t.get("operations.cash.amount")
        )
        self.page.update()

    def _open_cash_date_picker(self, e):
        dp = ft.DatePicker(
            first_date=datetime(2000, 1, 1),
            last_date=datetime.now(),
            on_change=self._on_cash_date_picked,
        )
        self.page.show_dialog(dp)

    def _on_cash_date_typed(self, e):
        self.cash_date_value = parse_date_input(e.control.value)

    def _on_cash_date_picked(self, e):
        picked = e.control.value
        if isinstance(picked, datetime):
            picked = (picked + timedelta(hours=12)).date()
        self.cash_date_value = picked
        self.cash_date_field.value = picked.strftime(DATE_FORMAT)
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
            show_snack(self.page, t.get("misc_errors.nodate"), error=True)
            return
        if self.cash_date_value > date.today():
            show_snack(self.page, t.get("misc_errors.date_future"), error=True)
            return
        if self._check_date_sequential(df, self.cash_date_value):
            show_snack(self.page, t.get("misc_errors.date_sequential"), error=True)
            return
        try:
            amount = float(self.cash_amount.value)
        except (ValueError, TypeError):
            show_snack(self.page, t.get("operations.cash.error_cash"), error=True)
            return

        kind = self.cash_type.value
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
                    t, df, broker, service_kind, date_str, ref_date, amount,
                    ticker=ticker, description=descr,
                )
                s.accounts[acc_idx]["df"] = new_df
                account_service.save_account(new_df, s.get_account(acc_idx)["path"])
                show_snack(self.page, t.get("operations.added_transaction"))
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

        date_field = ft.TextField(
            label=t.get("components.pick_date"),
            hint_text=t.get("components.date_format_hint"),
            border_radius=ft.border_radius.all(15),
            border_color=ft.Colors.with_opacity(0.40, ft.Colors.GREY),
            keyboard_type=ft.KeyboardType.DATETIME,
            input_filter=_DATE_FILTER,
            on_change=lambda e, pt=product_type: self._on_es_date_typed(e, pt),
            expand=True,
        )
        date_icon = ft.FilledTonalIconButton(
            icon=ft.Icons.CALENDAR_MONTH,
            on_click=lambda e, pt=product_type: self._open_es_date_picker(e, pt),
        )
        date_row = ft.Container(
            content=ft.Row([date_field, date_icon]),
            col={"xs": 12, "md": 6},
        )


        ticker_field = TickerSearchField(
            self.page,
            label="Ticker",
            type_filter="etf" if product_type == "ETF" else "equity",
            border_radius=ft.border_radius.all(15),
            border_color=ft.Colors.with_opacity(0.40, ft.Colors.GREY),
            expand=True,
        )
        ticker_help = ft.FilledTonalIconButton(
            icon=ft.Icons.HELP_OUTLINE,
            on_click=self._show_ticker_help,
        )
        ticker_row = ft.Container(
            content=ft.Row([ticker_field.control, ticker_help]),
            col={"xs": 12, "md": 6},
        )


        ter_field = ft.TextField(
            label=t.get("operations.stock.ter"),
            keyboard_type=ft.KeyboardType.NUMBER,
            input_filter=_DECIMAL_FILTER,
            border_radius=ft.border_radius.all(15),
            border_color=ft.Colors.with_opacity(0.40, ft.Colors.GREY),
            col={"xs":12, "md": 6},
            expand=True
        )
        ter_help = ft.FilledTonalIconButton(
            icon=ft.Icons.HELP_OUTLINE,
            on_click=self._show_ter_help,
        )
        ter_row = ft.Container(
            content=ft.Row([ter_field, ter_help]),
            col={"xs": 12, "md": 6},
            visible=(product_type == "ETF"),
        )

        tax_bracket_field = ft.TextField(
            label=t.get("operations.stock.tax_bracket"),
            keyboard_type=ft.KeyboardType.NUMBER,
            input_filter=_DECIMAL_FILTER,
            border_radius=ft.border_radius.all(15),
            border_color=ft.Colors.with_opacity(0.40, ft.Colors.GREY),
            col={"xs": 12, "md": 6},
            expand=True
        )
        tax_help = ft.FilledTonalIconButton(
            icon=ft.Icons.HELP_OUTLINE,
            on_click=self._show_tax_help,
        )
        tax_row = ft.Container(
            content=ft.Row([tax_bracket_field, tax_help]),
            col={"xs": 12, "md": 6},
            visible=False,
        )


        currency_dd = ft.Dropdown(
            menu_style=ft.MenuStyle(
                shape=ft.RoundedRectangleBorder(radius=15),
            ),
            label=t.get("operations.stock.currency"),
            options=[
                ft.dropdown.Option(key=str(CURRENCY_EUR), text="EUR"),
                ft.dropdown.Option(key=str(CURRENCY_USD), text="USD"),
            ],
            value=str(CURRENCY_EUR),
            on_select=lambda e, pt=product_type: self._on_currency_change(e, pt),
            col={"xs": 6, "md": 6},
            border_radius=ft.border_radius.all(15),
            border_color=ft.Colors.with_opacity(0.40, ft.Colors.GREY),
            expand=True,
        )
        exch_rate = ft.TextField(label=t.get("operations.stock.exch_rate"),
            keyboard_type=ft.KeyboardType.NUMBER,
            input_filter=_DECIMAL_FILTER,
            border_radius=ft.border_radius.all(15),
            border_color=ft.Colors.with_opacity(0.40, ft.Colors.GREY),
            visible=False, col={"xs": 6, "md": 6}
        )
        
        
        quantity_field = ft.TextField(label=t.get("operations.stock.qt"),
                                     border_radius=ft.border_radius.all(15),
                                     keyboard_type=ft.KeyboardType.NUMBER,
                                     input_filter=_DECIMAL_FILTER,
                                     border_color=ft.Colors.with_opacity(0.40, ft.Colors.GREY),
                                     col={"xs": 6, "md": 6})
        price_field = ft.TextField(label=t.get("operations.stock.price"),
                                   border_radius=ft.border_radius.all(15),
                                   border_color=ft.Colors.with_opacity(0.40, ft.Colors.GREY),
                                   keyboard_type=ft.KeyboardType.NUMBER,
                                   input_filter=_DECIMAL_FILTER,
                                   col={"xs": 6, "md": 6})
        
        
        fee_currency_dd = ft.Dropdown(
            menu_style=ft.MenuStyle(
                shape=ft.RoundedRectangleBorder(radius=15),
            ),
            label=t.get("operations.stock.currency_fee"),
            options=[
                ft.dropdown.Option(key=str(CURRENCY_EUR), text="EUR"),
                ft.dropdown.Option(key=str(CURRENCY_USD), text="USD"),
            ],
            value=str(CURRENCY_EUR),
            visible=False, col={"xs": 6, "md": 6},
            border_radius=ft.border_radius.all(15),
            border_color=ft.Colors.with_opacity(0.40, ft.Colors.GREY),
            expand=True,
        )
        fee_field = ft.TextField(label=t.get("operations.stock.fee"),
                                 border_radius=ft.border_radius.all(15),
                                 border_color=ft.Colors.with_opacity(0.40, ft.Colors.GREY),
                                 keyboard_type=ft.KeyboardType.NUMBER,
                                 input_filter=_DECIMAL_FILTER,
                                 col={"xs": 6, "md": 6})


        loading = ft.ProgressRing(visible=False, width=30, height=30)

        # Chain on_submit for keyboard "next field" navigation (skips hidden fields)
        es_fields = [
            date_field, ticker_field._field, exch_rate,
            quantity_field, price_field, fee_field, ter_field,
        ]
        chain_focus(es_fields)

        tab_data = {
            "es_type": es_type,
            "date_field": date_field, "date_icon": date_icon, "date_value": None,
            "currency_dd": currency_dd, "exch_rate": exch_rate,
            "ticker": ticker_field, "quantity": quantity_field, "price": price_field,
            "fee_currency_dd": fee_currency_dd, "fee": fee_field, "ter": ter_field,
            "tax_bracket": tax_bracket_field,
            "loading": loading, "product_type": product_type,
        }
        if not hasattr(self, "_es_tabs"):
            self._es_tabs = {}
        self._es_tabs[product_type] = tab_data

        stock_etf_form = ft.Column([
            es_type,
            ft.Container(height=5),
            ft.ResponsiveRow([date_row, ticker_row]),
            ft.ResponsiveRow([currency_dd, exch_rate]),
            ft.ResponsiveRow([quantity_field, price_field]),
            ft.ResponsiveRow([fee_currency_dd, fee_field, ter_row, tax_row]),
            ft.Row([ft.Container(width=5), loading]),
            ft.Container(height=80),
        ], spacing=12)

        if product_type != "ETF":
            stock_etf_form.scroll = ft.ScrollMode.AUTO

            async def on_focus_stock(e):
                if hasattr(e.control, "key") and e.control.key:
                    await stock_etf_form.scroll_to(scroll_key=e.control.key, duration=300)

            for name, field in [
                ("date", date_field), ("exch_rate", exch_rate),
                ("ticker", ticker_field), ("quantity", quantity_field),
                ("price", price_field), ("fee", fee_field), ("ter", ter_field),
            ]:
                field.key = f"{product_type}_{name}"
                field.on_focus = on_focus_stock
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

        def _on_etf_subtype_change(e):
            val = e.control.value
            stock_etf_form.visible = val in ("stock_etf", "mm_etf")
            bond_placeholder.visible = val == "bond_etf"
            bond_maturity_switch.disabled = val != "bond_etf"
            #ter_field.visible = val in ("stock_etf", "mm_etf")
            tax_row.visible = val == "mm_etf"
            tab_data["etf_subtype"] = val
            self.page.update()

        etf_subtype_group = ft.RadioGroup(
            value="stock_etf",
            on_change=_on_etf_subtype_change,
            content=ft.Column([
                ft.Radio(value="stock_etf", label=t.get("operations.stock.stock_etf")),
                ft.Radio(value="mm_etf", label=t.get("operations.stock.mm_etf"),),
                ft.Row([
                    ft.Radio(value="bond_etf", label=t.get("operations.stock.bonds_etf"),),
                    ft.Container(expand=True),
                    bond_maturity_switch,
                ], spacing=0),
            ], spacing=0, opacity=0.4 if no_account else 1.0),
        )
        tab_data["etf_subtype"] = "stock_etf"
        tab_data["bond_fixed_maturity"] = False

        outer = ft.Column([
            etf_subtype_group,
            stock_etf_form,
            bond_placeholder,
        ], spacing=12, scroll=ft.ScrollMode.AUTO)

        async def on_focus_etf(e):
            if hasattr(e.control, "key") and e.control.key:
                await outer.scroll_to(scroll_key=e.control.key, duration=300)

        for name, field in [
            ("date", date_field), ("exch_rate", exch_rate),
            ("ticker", ticker_field), ("quantity", quantity_field),
            ("price", price_field), ("fee", fee_field), ("ter", ter_field),
        ]:
            field.key = f"{product_type}_{name}"
            field.on_focus = on_focus_etf

        return ft.Container(content=outer, padding=20, expand=True)

    def _open_es_date_picker(self, e, product_type):
        dp = ft.DatePicker(
            first_date=datetime(2000, 1, 1),
            last_date=datetime.now(),
            on_change=lambda ev, pt=product_type: self._on_es_date_picked(ev, pt),
        )
        self.page.show_dialog(dp)

    def _on_es_date_typed(self, e, product_type):
        tab = self._es_tabs[product_type]
        tab["date_value"] = parse_date_input(e.control.value)

    def _on_es_date_picked(self, e, product_type):
        picked = e.control.value
        if isinstance(picked, datetime):
            picked = (picked + timedelta(hours=12)).date()
        tab = self._es_tabs[product_type]
        tab["date_value"] = picked
        tab["date_field"].value = picked.strftime(DATE_FORMAT)
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
        if product_type == "ETF" and tab.get("etf_subtype", "stock_etf") not in ("stock_etf", "mm_etf"):
            show_snack(self.page, "Not yet implemented", error=True)
            return
        df = self._get_ops_df()
        broker = self._get_ops_broker()
        if df is None or broker is None:
            show_snack(self.page, t.get("operations.select_account"), error=True)
            return

        if tab["date_value"] is None:
            show_snack(self.page, t.get("misc_errors.nodate"), error=True)
            return
        if tab["date_value"] > date.today():
            show_snack(self.page, t.get("misc_errors.date_future"), error=True)
            return
        if self._check_date_sequential(df, tab["date_value"]):
            show_snack(self.page, t.get("misc_errors.date_sequential"), error=True)
            return

        currency_int = int(tab["currency_dd"].value)

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
        if not tab["es_type"].controls[1].value:  # Switch off = Buy
            price = -price

        conv_rate = 1.0
        if currency_int == CURRENCY_USD:
            try:
                exch = float(tab["exch_rate"].value)
                if exch <= 0:
                    raise ValueError
                conv_rate = exch
            except (ValueError, TypeError):
                show_snack(self.page, t.get("operations.stock.exch_rate_error"), error=True)
                return
            fee_currency = int(tab["fee_currency_dd"].value)
            if fee_currency == CURRENCY_USD:
                fee = round_half_up(fee * conv_rate, decimal="0.000001")

        ter = np.nan
        if product_type == "ETF":
            ter_val = tab["ter"].value
            if ter_val:
                ter = ter_val.strip().rstrip("%") + "%"

        tax_rate = 0.26
        if product_type == "ETF" and tab.get("etf_subtype") == "mm_etf":
            try:
                tax_rate = float(tab["tax_bracket"].value)
                if not (0 <= tax_rate <= 100):
                    raise ValueError
                tax_rate = tax_rate / 100
            except (ValueError, TypeError):
                show_snack(self.page, t.get("operations.stock.tax_bracket_error"), error=True)
                return

        date_str = tab["date_value"].strftime(DATE_FORMAT)
        ref_date = tab["date_value"]
        acc_idx = s.ops_acc_idx

        tab["loading"].visible = True
        self.page.update()

        expected_type = "etf" if product_type == "ETF" else "equity"

        def worker():
            try:
                from services.market_data import search_tickers as _search
                results = _search(ticker, quotes_count=1)
                if results and results[0]["symbol"].upper() == ticker.upper():
                    actual_type = results[0]["type"]
                    if actual_type != expected_type:
                        label = "an ETF" if expected_type == "etf" else "a Stock"
                        msg = t.get("operations.stock.ticker_wrong_type")
                        show_snack(self.page, msg, error=True)
                        tab["loading"].visible = False
                        self.page.update()
                        return

                new_df = operations_service.execute_etf_stock(
                    t, df, broker, date_str, ref_date,
                    currency_int, conv_rate, ticker, quantity, price,
                    fee, ter, product_type, tax_rate=tax_rate,
                )
                s.accounts[acc_idx]["df"] = new_df
                account_service.save_account(new_df, s.get_account(acc_idx)["path"])
                show_snack(self.page, t.get("operations.added_transaction"))
                self._refresh_page()
            except (RuntimeError, ValidationError, Exception) as ex:
                show_snack(self.page, str(ex), error=True)
            finally:
                tab["loading"].visible = False
                self.page.update()

        self.page.run_thread(worker)

    def _show_ticker_help(self, e):
        t = self.state.translator
        dlg = ft.AlertDialog(
            title=ft.Text(t.get("operations.stock.ticker")),
            content=ft.Text(t.get("operations.stock.ticker_explained")),
            actions=[ft.TextButton("OK", on_click=lambda e: self.page.pop_dialog())],
        )
        self.page.show_dialog(dlg)

    def _show_ter_help(self, e):
        t = self.state.translator
        dlg = ft.AlertDialog(
            title=ft.Text(t.get("operations.stock.ter")),
            content=ft.Text(t.get("operations.stock.ter_explained")),
            actions=[ft.TextButton("OK", on_click=lambda e: self.page.pop_dialog())],
        )
        self.page.show_dialog(dlg)

    def _show_tax_help(self, e):
        t = self.state.translator
        dlg = ft.AlertDialog(
            title=ft.Text(t.get("operations.stock.tax_bracket")),
            content=ft.Text(t.get("operations.stock.tax_explained")),
            actions=[ft.TextButton("OK", on_click=lambda e: self.page.pop_dialog())],
        )
        self.page.show_dialog(dlg)

    def _refresh_page(self):
        from views import _rebuild_page
        _rebuild_page(self.page, self.state, selected_index=1)
