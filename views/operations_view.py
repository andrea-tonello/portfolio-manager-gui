import flet as ft

from components.background import run_in_background
from components.date_field import DateField
from components.dialogs import show_info_dialog
from components.focus_chain import chain_focus, scroll_into_view_on_focus
from components.inputs import DECIMAL_INPUT_FILTER, account_selector, rounded_dropdown, rounded_text_field
from components.snack import error_message, show_snack
from components.ticker_search import TickerSearchField
from domain.errors import ValidationError
from domain.ledger import Product
from domain.positions import held_tickers
from services import operations_service
from services.market_data import search_tickers
from services.validation import parse_positive, validate_date
from utils.constants import CURRENCIES, DATE_FORMAT


def _selected_account(state):
    """The account picked at the top of Operations, or None when none is picked (or its file isn't loaded)."""
    idx = state.ops_acc_idx
    return None if idx is None else state.get_account(idx)


def _held_tickers(df):
    """Return a list of (ticker, asset_name) for positions with qt_held > 0."""
    if df is None or df.empty:
        return []
    return [(ticker, name or ticker) for ticker, name in held_tickers(df).items()]


def _help_button(page, t, title_key, body_key):
    """Return the round "?" button that opens a short explanation next to a field.

    Both texts come from the translations, e.g. ("operations.stock.ter",
    "operations.stock.ter_explained") explains what the TER of an ETF is.
    """
    return ft.FilledTonalIconButton(
        icon=ft.Icons.HELP_OUTLINE,
        on_click=lambda _: show_info_dialog(page, t.get(title_key), t.get(body_key)),
    )


def _show_fee_help(page, t):
    """Explain the fee modes, with the longer text from fee_mode_help_<language>.txt."""
    show_info_dialog(page, t.get("operations.stock.fee_mode_title"),
                     t.load_text("fee_mode_help") or "Fee mode description not available.",
                     markdown=True, title_size=21)


def _add_button(t, on_click, disabled):
    """Return the "Add transaction" button at the bottom of each form."""
    return ft.FilledButton(
        t.get("operations.add_transaction"),
        icon=ft.Icons.ADD,
        on_click=on_click,
        disabled=disabled,
        style=ft.ButtonStyle(padding=ft.Padding.symmetric(horizontal=32, vertical=18)),
    )


class OperationsView:
    def __init__(self, app):
        """Build the Operations tab for the controller's page and current state."""
        self.app = app
        self.page = app.page
        self.state = app.state
        self.general = GeneralForm(app)
        self.etf = EtfStockForm(app, "ETF")
        self.stock = EtfStockForm(app, "Stock")

    def build(self) -> ft.Control:
        t = self.state.translator
        if not self.state.brokers:
            return ft.Text(t.get("home.no_account"), size=16)

        has_account = self.state.ops_acc_idx is not None
        form_container = ft.Container(
            content=ft.Tabs(
                length=3,
                selected_index=0,
                content=ft.Column([
                    ft.TabBar(tabs=[
                        ft.Tab(label=t.get("operations.general.title")),
                        ft.Tab(label=t.get("operations.stock.title_etf")),
                        ft.Tab(label=t.get("operations.stock.title_stock")),
                    ], scrollable=True, splash_border_radius=ft.BorderRadius.only(top_left=10, top_right=10)),
                    ft.TabBarView(
                        controls=[self.general.build(), self.etf.build(), self.stock.build()],
                        expand=True,
                    ),
                ], expand=True),
                expand=True, adaptive=True
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
        idx = self.state.ops_acc_idx
        return account_selector(self.state, None if idx is None else str(idx), self._on_account_selected,
                                hint_text=t.get("operations.select_account"))

    def _on_account_selected(self, e):
        idx = int(e.control.value)
        self.state.ops_acc_idx = idx
        self.app.refresh()


class GeneralForm:
    """The General tab of Operations: cash movements (deposit, withdrawal, charge), dividends and splits."""

    def __init__(self, app):
        """Keep what the form needs; build() creates its controls."""
        self.app = app
        self.page = app.page
        self.state = app.state

    def build(self) -> ft.Control:
        """Create the form's controls (kept as attributes, e.g. self.amount) and return its layout."""
        t = self.state.translator
        no_account = self.state.ops_acc_idx is None
        account = _selected_account(self.state)
        holdings = _held_tickers(account.df if account else None)
        header_color = ft.Colors.with_opacity(0.6, ft.Colors.ON_SURFACE)

        split_help = _help_button(self.page, t, "operations.split.title", "operations.split.descr")

        self.kind = ft.RadioGroup(
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
            on_change=self._on_kind_change,
        )
        self.date = DateField(self.page, t.get("components.pick_date"), t.get("components.date_format_hint"))

        self.amount = rounded_text_field(label=t.get("operations.cash.amount"),
                                         keyboard_type=ft.KeyboardType.NUMBER,
                                         input_filter=DECIMAL_INPUT_FILTER,
                                         col={"xs": 12, "md": 6})
        self.ticker = TickerSearchField(
            self.page,
            label=t.get("operations.stock.ticker"),
            expand=True,
        )
        ticker_help = _help_button(self.page, t, "operations.stock.ticker", "operations.stock.ticker_explained")
        self.ticker_row = ft.Container(
            content=ft.Row([
                self.ticker.control, 
                ft.Container(content=ticker_help, padding=ft.Padding.only(top=4)),
            ], vertical_alignment=ft.CrossAxisAlignment.START), visible=False, col={"xs": 12, "md": 6},
        )
        self.description = rounded_text_field(label=t.get("operations.cash.charge_descr"),
                                              visible=False, col={"xs": 12, "md": 6})

        split_ticker_options = [
            ft.dropdown.Option(key=tk, text=f"{tk}  ·  {name}" if name and name != tk else tk)
            for tk, name in holdings
        ]
        self.split_ticker = rounded_dropdown(
            label=t.get("operations.split.ticker"),
            options=split_ticker_options,
            expand=True,
        )
        self.split_ticker_row = ft.Container(
            content=self.split_ticker, visible=False, col={"xs": 12, "md": 6},
        )
        self.split_ratio = rounded_text_field(
            label=t.get("operations.split.ratio"),
            keyboard_type=ft.KeyboardType.NUMBER,
            input_filter=DECIMAL_INPUT_FILTER,
            expand=True,
        )
        split_ratio_help = _help_button(self.page, t, "operations.split.ratio_example", "operations.split.ratio_descr")
        self.split_ratio_row = ft.Container(
            content=ft.Row([self.split_ratio, split_ratio_help]),
            visible=False, col={"xs": 12, "md": 6},
        )

        self.loading = ft.ProgressRing(visible=False, width=30, height=30)

        # Chain on_submit for keyboard "next field" navigation (skips hidden fields)
        # Tuples: (field_to_focus, control_to_check_visibility)
        chain_focus([
            self.date.field,
            (self.amount, self.amount),
            (self.ticker.field, self.ticker_row),
            (self.description, self.description),
            (self.split_ratio, self.split_ratio_row),
        ])

        col = ft.Column([
            self.kind,
            self.date.control,
            ft.ResponsiveRow([
                self.amount, self.ticker_row, self.description,
                self.split_ticker_row, self.split_ratio_row,
            ],),
            ft.Row([ft.Container(width=5), self.loading]),
            ft.Row([_add_button(t, self.submit, no_account)], alignment=ft.MainAxisAlignment.CENTER),
            ft.Container(height=20),
        ], spacing=15, scroll=ft.ScrollMode.AUTO)

        scroll_into_view_on_focus(col, [
            self.date.field, self.amount, self.ticker.field, self.description, self.split_ratio,
        ], prefix="cash")

        return ft.Container(content=col, padding=20, expand=True)

    def _on_kind_change(self, e):
        """Show the fields the chosen operation needs; a split needs something held to split."""
        t = self.state.translator
        kind = self.kind.value
        account = _selected_account(self.state)

        if kind == "split" and not _held_tickers(account.df if account else None):
            show_snack(self.page, t.get("operations.split.no_holdings"), error=True)
            self.kind.value = "deposit"
            kind = "deposit"

        is_split = (kind == "split")
        self.amount.visible = not is_split
        self.ticker_row.visible = (kind == "dividend")
        self.description.visible = (kind == "charge")
        self.split_ticker_row.visible = is_split
        self.split_ratio_row.visible = is_split
        self.amount.label = (
            t.get("operations.cash.dividend_amount") if kind == "dividend"
            else t.get("operations.cash.amount")
        )
        self.page.update()

    def submit(self, e):
        """Check the operation typed and record it in the background, or show what is wrong."""
        s = self.state
        t = s.translator
        account = _selected_account(s)
        if account is None:
            show_snack(self.page, t.get("operations.select_account"), error=True)
            return

        try:
            day = validate_date(self.date.value, ledger_df=account.df)
            if self.kind.value == "split":
                build_ledger = self._checked_split(account, day)
            else:
                build_ledger = self._checked_cash_operation(account, day)
        except ValidationError as ex:
            show_snack(self.page, error_message(t, ex), error=True)
            return
        acc_idx = s.ops_acc_idx

        def save():
            """Record the operation, save the account and show the tab again."""
            s.commit(acc_idx, build_ledger())
            show_snack(self.page, t.get("operations.added_transaction"))
            self.app.refresh()

        run_in_background(self.page, t, save, loading=self.loading)

    def _checked_cash_operation(self, account, day):
        """Check the amount of a cash operation or dividend; return a function building the ledger with it."""
        kind = self.kind.value
        amount = operations_service.parse_cash_amount(kind, self.amount.value)
        service_kind = "deposit_withdrawal" if kind in ("deposit", "withdrawal") else kind
        ticker = self.ticker.value if kind == "dividend" else None
        description = self.description.value if kind == "charge" else None
        df = account.df
        return lambda: operations_service.execute_cash_operation(
            df, account.name, service_kind, day.strftime(DATE_FORMAT), day, amount,
            ticker=ticker, description=description,
        )

    def _checked_split(self, account, day):
        """Check the ticker and ratio of a split; return a function building the ledger with it."""
        ticker = self.split_ticker.value
        if not ticker:
            raise ValidationError("operations.stock.ticker_error")
        ratio = parse_positive(self.split_ratio.value, "operations.split.ratio_error")
        df = account.df
        return lambda: operations_service.execute_split(
            df, account.name, day.strftime(DATE_FORMAT), day, ticker, ratio,
        )


class EtfStockForm:
    """The ETF or the Stock tab of Operations: a buy or a sell, and the details of the trade.

    The ETF tab also asks which kind of ETF it is, its yearly cost (TER), how the
    fee is accounted for, and the tax bracket of money-market ETFs. Bond ETFs
    aren't supported yet: picking them shows a "coming soon" note instead of the form.
    """

    def __init__(self, app, product_type):
        """Keep what the form needs; `product_type` is "ETF" or "Stock". build() creates the controls."""
        self.app = app
        self.page = app.page
        self.state = app.state
        self.product_type = product_type
        self.etf_subtype = None  # the ETF type picked (a RadioGroup of product codes); ETF tab only

    def build(self) -> ft.Control:
        """Create the form's controls (kept as attributes, e.g. self.quantity) and return its layout."""
        t = self.state.translator
        is_etf = self.product_type == "ETF"
        no_account = self.state.ops_acc_idx is None

        self._buy_label = ft.Text(t.get("operations.stock.op_buy"), weight=ft.FontWeight.BOLD)
        self._sell_label = ft.Text(t.get("operations.stock.op_sell"))
        self.side_switch = ft.Switch(  # off = buy, on = sell
            value=False, disabled=no_account, on_change=self._on_side_change,
            thumb_color={
                ft.ControlState.DEFAULT: ft.Colors.PRIMARY,
                ft.ControlState.SELECTED: ft.Colors.SURFACE,
            },
            track_color=ft.Colors.PRIMARY_CONTAINER,
            track_outline_color=ft.Colors.TRANSPARENT,
            thumb_icon=ft.Icons.ADD,
        )
        side_row = ft.Row(
            [self._buy_label, self.side_switch, self._sell_label],
            alignment=ft.MainAxisAlignment.CENTER,
            opacity=0.4 if no_account else 1.0,
        )

        self.date = DateField(self.page, t.get("components.pick_date"), t.get("components.date_format_hint"))
        date_row = ft.Container(
            content=self.date.control,
            col={"xs": 12, "md": 6},
        )

        self.ticker = TickerSearchField(
            self.page,
            label=t.get("operations.stock.ticker"),
            type_filter="etf" if is_etf else "equity",
            expand=True,
        )
        ticker_help = _help_button(self.page, t, "operations.stock.ticker", "operations.stock.ticker_explained")
        ticker_row = ft.Container(
            content=ft.Row([
                self.ticker.control, 
                ft.Container(content=ticker_help, padding=ft.Padding.only(top=4)),
            ], vertical_alignment=ft.CrossAxisAlignment.START), col={"xs": 12, "md": 6},
        )

        self.ter = rounded_text_field(
            label=t.get("operations.stock.ter"),
            keyboard_type=ft.KeyboardType.NUMBER,
            input_filter=DECIMAL_INPUT_FILTER,
            col={"xs":12, "md": 6},
            expand=True
        )
        ter_help = _help_button(self.page, t, "operations.stock.ter", "operations.stock.ter_explained")
        ter_row = ft.Container(
            content=ft.Row([self.ter, ter_help]),
            col={"xs": 12, "md": 6},
            visible=is_etf,
        )

        self.tax_bracket = rounded_text_field(
            label=t.get("operations.stock.tax_bracket"),
            keyboard_type=ft.KeyboardType.NUMBER,
            input_filter=DECIMAL_INPUT_FILTER,
            col={"xs": 12, "md": 6},
            expand=True
        )
        tax_help = _help_button(self.page, t, "operations.stock.tax_bracket", "operations.stock.tax_explained")
        self._tax_row = ft.Container(
            content=ft.Row([self.tax_bracket, tax_help]),
            col={"xs": 12, "md": 6},
            visible=False,
        )

        self.currency = rounded_dropdown(
            label=t.get("operations.stock.currency"),
            options=[ft.dropdown.Option(key=code, text=code) for code in CURRENCIES],
            value="EUR",
            on_select=self._on_currency_change,
            col={"xs": 6, "md": 6},
            expand=True,
        )
        self.exch_rate = rounded_text_field(label=t.get("operations.stock.exch_rate"),
            keyboard_type=ft.KeyboardType.NUMBER,
            input_filter=DECIMAL_INPUT_FILTER,
            visible=False, col={"xs": 6, "md": 6}
        )

        self.quantity = rounded_text_field(label=t.get("operations.stock.qt"),
                                           keyboard_type=ft.KeyboardType.NUMBER,
                                           input_filter=DECIMAL_INPUT_FILTER,
                                           col={"xs": 6, "md": 6})
        self.price = rounded_text_field(label=t.get("operations.stock.price"),
                                        keyboard_type=ft.KeyboardType.NUMBER,
                                        input_filter=DECIMAL_INPUT_FILTER,
                                        col={"xs": 6, "md": 6})

        self.fee_currency = rounded_dropdown(
            label=t.get("operations.stock.currency_fee"),
            options=[ft.dropdown.Option(key=code, text=code) for code in CURRENCIES],
            value="EUR",
            visible=False, col={"xs": 6, "md": 6},
            expand=True,
        )
        self.fee = rounded_text_field(label=t.get("operations.stock.fee"),
                                      keyboard_type=ft.KeyboardType.NUMBER,
                                      input_filter=DECIMAL_INPUT_FILTER,
                                      col={"xs": 6, "md": 6})

        fee_mode_help = ft.FilledTonalIconButton(
            icon=ft.Icons.HELP_OUTLINE,
            on_click=lambda _: _show_fee_help(self.page, t),
        )
        fee_mode_title = ft.Row([
            ft.Text("  " + t.get("operations.stock.fee_mode_title"), size=18,
                    opacity=0.4 if no_account else 1.0),
            fee_mode_help
        ], expand=True, alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
        self.fee_mode = ft.RadioGroup(
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
                self.fee_mode,
            ], spacing=10,),
            border=ft.Border.all(width=1,
                color=ft.Colors.with_opacity(0.20, ft.Colors.GREY) if no_account else ft.Colors.with_opacity(0.40, ft.Colors.GREY)),
            border_radius=15,
            padding=10,
            visible=is_etf,
        )

        self.loading = ft.ProgressRing(visible=False, width=30, height=30)

        # Chain on_submit for keyboard "next field" navigation (skips hidden fields)
        chain_focus([
            self.date.field, self.ticker.field, self.exch_rate,
            self.quantity, self.price, self.fee, self.ter,
        ])

        self._trade_fields = ft.Column([
            side_row,
            ft.Container(height=5),
            ft.ResponsiveRow([date_row, ticker_row]),
            ft.ResponsiveRow([self.currency, self.exch_rate]),
            ft.ResponsiveRow([self.quantity, self.price]),
            ft.ResponsiveRow([self.fee_currency, self.fee, ter_row, self._tax_row]),
            fee_mode_container,
            ft.Row([ft.Container(width=5), self.loading]),
            ft.Row([_add_button(t, self.submit, no_account)], alignment=ft.MainAxisAlignment.CENTER),
            ft.Container(height=20),
        ], spacing=12)

        scrolling_fields = [self.date.field, self.exch_rate, self.ticker.field, self.quantity, self.price,
                            self.fee, self.ter]
        if not is_etf:
            self._trade_fields.scroll = ft.ScrollMode.AUTO
            scroll_into_view_on_focus(self._trade_fields, scrolling_fields, prefix=self.product_type)
            return ft.Container(content=self._trade_fields, padding=20, expand=True)

        # ── ETF sub-type selector ───────────────────────────────

        self._bond_text = ft.Text("\n\n" + t.get("operations.stock.bonds_rolling_soon"), size=16,
                                  text_align=ft.TextAlign.CENTER)
        self._bond_placeholder = ft.Container(
            self._bond_text, alignment=ft.alignment.Alignment.CENTER, expand=True, visible=False,
        )
        self._bond_maturity_switch = ft.Switch(label=t.get("operations.stock.fixed"), value=False,
                                               disabled=True,
                                               label_position=ft.LabelPosition.LEFT,
                                               on_change=self._on_bond_maturity_change)

        # The radio values are the product codes stored in the CSV (e.g. "ETF-M").
        self.etf_subtype = ft.RadioGroup(
            value=Product.ETF_STOCK,
            on_change=self._on_etf_subtype_change,
            content=ft.Column([
                ft.Radio(value=Product.ETF_STOCK, label=t.get("operations.stock.stock_etf")),
                ft.Radio(value=Product.ETF_MM, label=t.get("operations.stock.mm_etf"),),
                ft.Row([
                    ft.Radio(value=Product.ETF_BOND, label=t.get("operations.stock.bonds_etf"),),
                    ft.Container(expand=True),
                    self._bond_maturity_switch,
                ], spacing=0),
            ], spacing=0, opacity=0.4 if no_account else 1.0),
        )

        outer = ft.Column([
            self.etf_subtype,
            self._trade_fields,
            self._bond_placeholder,
        ], spacing=12, scroll=ft.ScrollMode.AUTO)

        scroll_into_view_on_focus(outer, scrolling_fields, prefix=self.product_type)

        return ft.Container(content=outer, padding=20, expand=True)

    def _on_side_change(self, e):
        """Bold the side picked, buy or sell, and show + or - on the switch."""
        is_sell = self.side_switch.value
        self._buy_label.weight = ft.FontWeight.NORMAL if is_sell else ft.FontWeight.BOLD
        self._sell_label.weight = ft.FontWeight.BOLD if is_sell else ft.FontWeight.NORMAL
        self.side_switch.thumb_icon = ft.Icons.REMOVE if is_sell else ft.Icons.ADD
        self.page.update()

    def _on_currency_change(self, e):
        """Ask for the exchange rate and the fee's currency only for trades in USD."""
        is_usd = (self.currency.value == "USD")
        self.exch_rate.visible = is_usd
        self.fee_currency.visible = is_usd
        self.page.update()

    def _on_etf_subtype_change(self, e):
        """Show the trade fields (with the tax bracket for money-market ETFs), or the note for bond ETFs."""
        val = self.etf_subtype.value
        self._trade_fields.visible = val in (Product.ETF_STOCK, Product.ETF_MM)
        self._bond_placeholder.visible = val == Product.ETF_BOND
        self._bond_maturity_switch.disabled = val != Product.ETF_BOND
        self._tax_row.visible = val == Product.ETF_MM
        self.page.update()

    def _on_bond_maturity_change(self, e):
        """Switch the bond ETF note between rolling and fixed maturity."""
        key = "operations.stock.bonds_fixed_soon" if e.control.value else "operations.stock.bonds_rolling_soon"
        self._bond_text.value = "\n\n" + self.state.translator.get(key)
        self.page.update()

    def submit(self, e):
        """Check the trade typed and record it in the background, or show what is wrong.

        Before recording, Yahoo is asked what kind of security the ticker is, so
        an ETF can't be bought from the Stock tab or the other way round.
        """
        s = self.state
        t = s.translator
        account = _selected_account(s)
        if account is None:
            show_snack(self.page, t.get("operations.select_account"), error=True)
            return

        try:
            trade = operations_service.parse_trade(
                product=self.etf_subtype.value if self.etf_subtype is not None else Product.STOCK,
                is_buy=not self.side_switch.value,
                day=self.date.value,
                ticker=self.ticker.value,
                quantity=self.quantity.value,
                price=self.price.value,
                fee=self.fee.value,
                currency=self.currency.value,
                exch_rate=self.exch_rate.value,
                fee_currency=self.fee_currency.value,
                ter=self.ter.value,
                tax_bracket=self.tax_bracket.value,
                fee_mode=self.fee_mode.value,
                ledger_df=account.df,
            )
        except ValidationError as ex:
            show_snack(self.page, error_message(t, ex), error=True)
            return
        df = account.df
        acc_idx = s.ops_acc_idx
        expected_type = "etf" if self.product_type == "ETF" else "equity"

        def save():
            """Check the ticker's kind with Yahoo, then record the trade, save the account and show the tab again."""
            results = search_tickers(trade.ticker, quotes_count=1)
            if (results and results[0]["symbol"].upper() == trade.ticker.upper()
                    and results[0]["quote_type"] != expected_type):
                show_snack(self.page, t.get("operations.stock.ticker_wrong_type"), error=True)
                return

            new_df = operations_service.execute_etf_stock(
                df, account.name, trade.date.strftime(DATE_FORMAT), trade.date,
                trade.currency, trade.conv_rate, trade.ticker, trade.quantity, trade.price,
                trade.fee, trade.ter, trade.product,
                is_buy=trade.is_buy, tax_rate=trade.tax_rate, fee_mode=trade.fee_mode,
            )
            s.commit(acc_idx, new_df)
            show_snack(self.page, t.get("operations.added_transaction"))
            self.app.refresh()

        run_in_background(self.page, t, save, loading=self.loading)
