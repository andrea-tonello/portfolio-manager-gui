import flet as ft
import pandas as pd

from components.date_field import DateRange, PeriodShortcuts, periods_and_dates
from components.dialogs import close_dialog
from components.file_export import get_file_picker, save_bytes
from components.inputs import account_selector
from components.journal_change import change_accounts, recalculated_text
from components.repaint_boundary import repaint_boundary
from components.snack import error_message, show_snack
from domain.errors import ValidationError
from domain.journal import Kind
from domain.ledger import Product
from services import account_service, config_service, journal_service
from utils.columns import (
    COLUMNS, OP_ID, OPERATION_LOCALE_KEYS, PRODUCT_LOCALE_KEYS, export_headers, localized_value_maps, operation_title,
    rename_for_export, show_transfer_counterparts,
)
from utils.constants import DATE_FORMAT

_DEFAULT_DISPLAY_COLS = [
    "date", "account", "operation", "product", "ticker", "qt_exch",
    "price_eur", "fee", "effective_amount", "pl",
]

_ALL_COLS = COLUMNS
_PAGE_SIZE = 20
# The controls above the table are no wider than this, centred: on a large screen they would spread too far apart.
_CONTROLS_WIDTH = 700
# The products named in the Products popup. Every other value of the column (a dividend, a tax, the
# user's own description of a charge such as "Stamp duty") comes under the popup's "Other".
_NAMED_PRODUCTS = (Product.CASH, Product.STOCK, Product.ETF_STOCK, Product.ETF_MM, Product.ETF_BOND)
_OTHER_PRODUCT = "other"


def _parsed_dates(df):
    """The `date` column of `df` as timestamps (dates stored as DD-MM-YYYY); NaT where unreadable."""
    return pd.to_datetime(df["date"], dayfirst=True, errors="coerce")


def _first_day(df):
    """The day of the earliest operation in `df`, where the MAX period starts; None when there is none."""
    first = None if df is None else _parsed_dates(df).min()
    return None if pd.isna(first) else first.date()


def _shown_rows(df, start, end, hidden_operations, hidden_products):
    """Return the rows of `df` from `start` to `end` included, without the operations and products hidden.

    `hidden_products` holds values of _NAMED_PRODUCTS, or _OTHER_PRODUCT for
    all the others. Example: with {"Buy"} and {"other"} hidden, a sale of a
    stock is listed, but not a buy of it, a dividend or a tax.
    """
    products = df["product"].where(df["product"].isin(_NAMED_PRODUCTS), _OTHER_PRODUCT)
    return df[_parsed_dates(df).between(pd.Timestamp(start), pd.Timestamp(end))
              & ~df["operation"].isin(hidden_operations)
              & ~products.isin(hidden_products)]


def _row_button(button, label, **options):
    """Return a `button` (e.g. ft.Button) labelled `label`, for a row of buttons that together fill the row's width."""
    return button(label, expand=len(label) + 6, style=ft.ButtonStyle(padding=ft.Padding.zero()), **options)


def _show_filter_state(button, filtering):
    """Show on a filter button whether its choice hides something: a check and a filled tonal button's colours, or its plain look."""
    button.icon = ft.Icons.CHECK if filtering else ft.Icons.FILTER_LIST
    button.style = ft.ButtonStyle(
        padding=ft.Padding.zero(),
        bgcolor=ft.Colors.SECONDARY_CONTAINER if filtering else None,
        color=ft.Colors.ON_SECONDARY_CONTAINER if filtering else None,
    )


def _newest_first(df):
    """Return `df` sorted newest first; operations of the same day go from the last entered to the first.

    Same order on screen and in the export, so running totals (cash held,
    quantity held) read in sequence. Example: deposits A, B, C entered in this
    order on the same day are listed C, B, A.
    """
    ordered = df.assign(_date=_parsed_dates(df), _position=range(len(df)))
    return ordered.sort_values(["_date", "_position"], ascending=False).drop(columns=["_date", "_position"])


class TransactionsView:
    def __init__(self, app):
        """Build the Transactions tab for the controller's page and current state."""
        self.app = app
        self.page = app.page
        self.state = app.state

    def _unloaded_accounts(self) -> set[str]:
        """Return the names of the user's accounts that couldn't be loaded (e.g. a journal from a newer version)."""
        return set(self.state.brokers.values()) - {account.name for account in self.state.accounts.values()}

    def build(self) -> ft.Control:
        t = self.state.translator
        if not self.state.brokers:
            return ft.Column([ft.Text(t.get("home.no_account"), size=16)])

        self.file_picker = get_file_picker(self.page)  # for the CSV exports

        df = self._get_tx_df()
        sel = self.state.tx_selection

        acc_idx = None if sel == "overview" else int(sel)

        children = [
            ft.Container(
                self._build_dropdown(),
                padding=ft.Padding.only(top=5, left=5, right=5),
            ),
            self._build_transactions_section(df, acc_idx),
        ]

        return ft.Column(children, scroll=ft.ScrollMode.AUTO, expand=True,
                         horizontal_alignment=ft.CrossAxisAlignment.CENTER)

    def _build_dropdown(self) -> ft.Control:
        t = self.state.translator
        return account_selector(self.state, self.state.tx_selection, self._on_selection_change,
                                all_option=("overview", t.get("home.overview")))

    def _on_selection_change(self, e):
        self.state.tx_selection = e.control.value
        self.app.refresh()

    def _get_tx_df(self):
        sel = self.state.tx_selection
        if sel == "overview":
            all_rows = [account.transactions.copy()
                        for account in self.state.accounts.values() if account.has_transactions]
            if all_rows:
                return pd.concat(all_rows, ignore_index=True)
            return None
        else:
            account = self.state.get_account(int(sel))
            if account is None:
                return None
            return account.transactions.copy() if account.has_transactions else None

    # ── Transactions Section ─────────────────────────────────────────

    def _build_transactions_section(self, df, acc_idx=None) -> ft.Control:
        self._tx_df = df
        self._acc_idx = acc_idx
        self._visible_cols = (config_service.load_tx_columns(self.state.user_config_folder)
                              or list(_DEFAULT_DISPLAY_COLS))

        controls = ft.Container(
            ft.Column([self._build_period_row(df), self._build_filters_and_actions_row(acc_idx)], spacing=20),
            width=_CONTROLS_WIDTH,
            padding=ft.Padding.only(left=5, right=5, top=5),
        )
        self.tx_table_container = ft.Container(padding=ft.Padding.only(top=10))
        self._update_tx_table()

        return ft.Column([
            controls,
            self.tx_table_container,
        ], spacing=15, horizontal_alignment=ft.CrossAxisAlignment.CENTER)

    def _build_period_row(self, df) -> ft.Control:
        """The period shortcuts, then the dates as text, the button changing them and ">>", a placeholder doing nothing yet.

        Two rows on a phone, one on a larger screen. The table follows a period
        or dates as soon as they are chosen (_on_period_change).
        """
        s = self.state
        t = s.translator
        first_day = _first_day(df)
        self.dates = DateRange(self.page, t)
        self.dates.start.min_date = first_day  # the picker: nothing to list before the first operation
        self.periods = PeriodShortcuts(t, self.dates.start, self.dates.end, first_day)
        self.periods.restore(s.tx_period, s.tx_dates)
        self.periods.on_change = self._on_period_change
        return periods_and_dates(self.periods, self.dates)

    def _on_period_change(self):
        """A period was picked or dates set by hand: keep them for when the tab is shown again, and list their rows."""
        self.state.tx_period = self.periods.period
        self.state.tx_dates = (self.dates.start.value, self.dates.end.value)
        self._update_tx_table()
        self.page.update()

    def _build_filters_and_actions_row(self, acc_idx) -> ft.Control:
        """The filter buttons opening their popups, then the actions: two rows on a phone, one split by a line on a larger screen.

        The row counts 25 columns on a larger screen: 12 for each group, and 1 for the line.
        "Select..." is a placeholder for a bulk delete, doing nothing yet.
        """
        t = self.state.translator
        self.columns_button = _row_button(ft.OutlinedButton, t.get("transactions.columns"), on_click=self._on_open_columns)
        self.operations_button = _row_button(ft.OutlinedButton, t.get("transactions.operations"), on_click=self._on_open_operations)
        self.products_button = _row_button(ft.OutlinedButton, t.get("transactions.products"), on_click=self._on_open_products)
        self._update_filter_buttons()
        filters = ft.Row([self.columns_button, self.operations_button, self.products_button],
                         spacing=8, col={"xs": 25, "md": 12})

        if acc_idx is not None:
            async def on_export(e):
                """Save the CSV of the account selected."""
                await self._on_export(e, acc_idx)
            export_click = on_export
            remove_click = lambda e, i=acc_idx: self._on_remove_row(e, i)
        else:
            export_click = self._on_export_overview
            remove_click = None

        actions = ft.Row([
            _row_button(
                ft.Button,
                t.get("transactions.remove"),
                icon=ft.Icons.UNDO,
                on_click=remove_click,
                disabled=(acc_idx is None),
                tooltip=t.get("transactions.remove_row"),
            ),
            _row_button(ft.Button, t.get("transactions.select"), icon=ft.Icons.DELETE),
            _row_button(ft.FilledButton, t.get("transactions.export"), icon=ft.Icons.SAVE, on_click=export_click),
        ], spacing=8, col={"xs": 25, "md": 12})

        line = ft.Container(ft.VerticalDivider(width=1), height=44, col={"xs": 0, "md": 1})

        return ft.ResponsiveRow([filters, line, actions], columns={"xs": 25, "md": 25}, spacing=0, run_spacing=20,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER)

    def _update_filter_buttons(self):
        """Mark each filter button that hides something: a column left out, or an operation or product unticked.

        Showing every column is what counts as no filter on columns. A new user's
        usual columns leave some out, so Columns starts marked, which also
        shows them from the start that the table can be filtered.
        """
        _show_filter_state(self.columns_button, not set(_ALL_COLS) <= set(self._visible_cols))
        _show_filter_state(self.operations_button, bool(self.state.tx_hidden_operations))
        _show_filter_state(self.products_button, bool(self.state.tx_hidden_products))

    # ── Popups of the filter buttons ──────────────────────────────────

    def _open_checklist(self, title_key, options, ticked, on_apply):
        """Open a popup with one checkbox per option, those in `ticked` ticked; Apply passes on the choice and lists the rows.

        `options` is {value: label}, and `on_apply` receives the set of values ticked.
        """
        t = self.state.translator
        boxes = {value: ft.Checkbox(label=label, value=value in ticked) for value, label in options.items()}

        def apply(_):
            """Close the popup, pass on what is ticked, and show the buttons and the table that follow from it."""
            self.page.pop_dialog()
            on_apply({value for value, box in boxes.items() if box.value})
            self._update_filter_buttons()
            self._update_tx_table()
            self.page.update()

        self.page.show_dialog(ft.AlertDialog(
            title=ft.Text(t.get(title_key)),
            content=ft.Column(list(boxes.values()), tight=True, spacing=0, width=400),
            actions=[
                ft.TextButton(t.get("components.cancel"), on_click=lambda _: self.page.pop_dialog()),
                ft.FilledButton(t.get("components.apply"), on_click=apply),
            ],
            # The dialog scrolls, not a Column inside it: in Flet 1.0 a scrolling Column stretches the dialog.
            scrollable=True,
        ))

    def _on_open_columns(self, e):
        """Let the user pick the columns the table shows, saved for the next time; with none ticked, the usual ones."""
        t = self.state.translator
        labels = export_headers(t)

        def apply(ticked):
            """Show and save the columns ticked, in their usual order."""
            self._visible_cols = [col for col in _ALL_COLS if col in ticked] or list(_DEFAULT_DISPLAY_COLS)
            config_service.save_tx_columns(self.state.user_config_folder, self._visible_cols)

        self._open_checklist("transactions.columns", {col: labels.get(col, col) for col in _ALL_COLS},
                             self._visible_cols, apply)

    def _on_open_operations(self, e):
        """Let the user pick the kinds of operation the table lists, kept until the app closes."""
        t = self.state.translator
        options = {operation: t.get(key).strip() for operation, key in OPERATION_LOCALE_KEYS.items()}

        def apply(ticked):
            """Hide the operations not ticked."""
            self.state.tx_hidden_operations = set(options) - ticked

        self._open_checklist("transactions.operations", options, set(options) - self.state.tx_hidden_operations, apply)

    def _on_open_products(self, e):
        """Let the user pick the products the table lists, kept until the app closes; "Other" stands for all the unnamed ones."""
        t = self.state.translator
        options = {product: t.get(PRODUCT_LOCALE_KEYS[product]).strip() for product in _NAMED_PRODUCTS}
        options[_OTHER_PRODUCT] = t.get("transactions.other")

        def apply(ticked):
            """Hide the products not ticked."""
            self.state.tx_hidden_products = set(options) - ticked

        self._open_checklist("transactions.products", options, set(options) - self.state.tx_hidden_products, apply)

    # ── Table update ──────────────────────────────────────────────────

    def _update_tx_table(self, reset_page=True):
        t = self.state.translator
        df = self._tx_df
        if df is None or df.empty:
            self.tx_table_container.content = ft.Column([
                ft.Container(height=80),
                ft.Text(t.get("transactions.empty"), size=16)
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER)
            return

        self._tx_filtered_df = _shown_rows(_newest_first(df), self.dates.start.value, self.dates.end.value,
                                           self.state.tx_hidden_operations, self.state.tx_hidden_products)

        if reset_page:
            self._tx_page = 0

        self._render_page()

    def _render_page(self):
        df = self._tx_filtered_df
        total = len(df)
        total_pages = max(1, (total + _PAGE_SIZE - 1) // _PAGE_SIZE)
        self._tx_page = min(self._tx_page, total_pages - 1)

        start = self._tx_page * _PAGE_SIZE
        page_df = df.iloc[start:start + _PAGE_SIZE]

        table = self._build_transactions_table(page_df)

        if total_pages > 1:
            pagination = ft.Row([
                ft.IconButton(
                    ft.Icons.CHEVRON_LEFT,
                    on_click=self._on_prev_page,
                    disabled=self._tx_page == 0,
                ),
                ft.Text(f"{self._tx_page + 1} / {total_pages}", size=13),
                ft.IconButton(
                    ft.Icons.CHEVRON_RIGHT,
                    on_click=self._on_next_page,
                    disabled=self._tx_page >= total_pages - 1,
                ),
            ], alignment=ft.MainAxisAlignment.CENTER, spacing=4)
            self.tx_table_container.content = ft.Column(
                [table, pagination], spacing=5,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            )
        else:
            self.tx_table_container.content = table

    def _on_prev_page(self, e):
        if self._tx_page > 0:
            self._tx_page -= 1
            self._render_page()
            self.page.update()

    def _on_next_page(self, e):
        self._tx_page += 1
        self._render_page()
        self.page.update()

    # ── Table ──────────────────────────────────────────────────────

    def _build_transactions_table(self, df) -> ft.Control:
        t = self.state.translator
        if df is None or df.empty:
            return ft.Text(t.get("transactions.empty"), size=16)
        df = show_transfer_counterparts(df, t)  # "verso: Directa" rather than the bare name stored

        available_cols = [c for c in self._visible_cols if c in df.columns]

        col_labels = export_headers(t)
        value_maps = localized_value_maps(t)

        columns = [ft.DataColumn(ft.Text(col_labels.get(col, col), size=11, weight=ft.FontWeight.BOLD)) for col in available_cols]
        rows = []
        for _, row in df.iterrows():
            cells = []
            for col in available_cols:
                val = row.get(col, "")
                if pd.isna(val) or val is None:
                    val = ""
                else:
                    val = str(val)
                    val = value_maps.get(col, {}).get(val, val)
                cells.append(ft.DataCell(ft.Text(val, size=10)))
            # A tap on a row offers to edit or remove its operation, named by the row's op_id.
            op_id = row.get(OP_ID)
            on_tap = (lambda e, name=row["account"], op_id=op_id: self._on_row_tap(name, op_id)) \
                if isinstance(op_id, str) and op_id else None
            rows.append(ft.DataRow(cells=cells, on_select_change=on_tap))

        # Inside the horizontal scroll, the repaint boundary spares redrawing every cell at each frame of a scroll in either direction.
        return ft.Row([
            repaint_boundary(ft.DataTable(
                columns=columns,
                rows=rows,
                horizontal_lines=ft.BorderSide(1, ft.Colors.GREY_300),
                column_spacing=12,
            )),
        ], scroll=ft.ScrollMode.ALWAYS, alignment=ft.MainAxisAlignment.CENTER)

    # ── Export / Remove ───────────────────────────────────────────────

    def _prepare_export_csv(self, df):
        """Sort df newest first (as on screen), rename to locale headers, return CSV bytes."""
        df = rename_for_export(_newest_first(df), self.state.translator)
        return df.to_csv(index=False).encode("utf-8")

    async def _on_export(self, e, idx):
        account = self.state.get_account(idx)
        if account is None:
            return
        csv_bytes = self._prepare_export_csv(account.transactions)
        await self._save_via_picker(account_service.export_filename(account.name), csv_bytes)

    async def _on_export_overview(self, e):
        t = self.state.translator
        df = self._tx_df
        if df is None or df.empty:
            show_snack(self.page, t.get("transactions.no_data"), error=True)
            return
        csv_bytes = self._prepare_export_csv(df)
        await self._save_via_picker(account_service.export_filename("All Accounts"), csv_bytes)

    async def _save_via_picker(self, file_name, csv_bytes):
        """Let the user save the transactions as `file_name`, confirming once saved."""
        t = self.state.translator
        await save_bytes(self.page, self.file_picker, file_name, csv_bytes, "csv", t.get("transactions.export_success"))

    def _on_remove_row(self, e, idx):
        """Remove the operation recorded last in account `idx`, asking first and naming it (see _remove).

        That is the one entered last, whatever its date: a split found on
        Yahoo goes on its own past date, and is still the one undone. The
        filters may hide it from the table, hence the question.
        """
        s = self.state
        t = s.translator
        account = s.get_account(idx)
        if not (account and account.has_transactions):
            show_snack(self.page, t.get("transactions.no_rows"), error=True)
            return
        try:
            op = journal_service.last_entered(account)
        except ValidationError as ex:  # an account not moved to the journal yet
            show_snack(self.page, error_message(t, ex), error=True)
            return
        self._remove(account, op, named=True)

    def _on_row_tap(self, account_name, op_id):
        """Offer what can be done with the operation of a row tapped: edit it (in Operations) or remove it (_remove).

        A transfer in is edited from the account sending it, where its form
        records it. A transfer whose other account is gone can only be
        removed. A row whose operation isn't in the journal (just removed,
        the list not shown again yet; or a ledger left out of step by a
        rebuild that failed offline) says so, and the list is shown again.
        """
        s = self.state
        t = s.translator
        account = next((acc for acc in s.accounts.values() if acc.name == account_name), None)
        if account is None:
            return
        try:
            op = journal_service.find_operation(account, op_id)
            half = journal_service.transfer_half(s.accounts, account, op_id)
        except ValidationError as ex:  # an account (or the other of a transfer) not moved to the journal yet
            show_snack(self.page, error_message(t, ex), error=True)
            return
        except ValueError:  # no such operation in the journal
            show_snack(self.page, t.get("journal.row_outdated"), error=True)
            self.app.refresh()
            return
        if op.kind == Kind.TRANSFER_IN:
            edited = None if half is None else (half[0].idx, half[1].id)
        else:
            edited = None if op.transfer_id and half is None else (account.idx, op.id)
        row = account.df[account.df[OP_ID] == op_id].iloc[0]

        def edit(_):
            """Close the dialog and edit the operation in Operations."""
            close_dialog(self.page, dialog)
            self.app.edit_operation(*edited)

        def remove(_):
            """Close the dialog and remove the operation."""
            close_dialog(self.page, dialog)
            self._remove(account, op)

        dialog = ft.AlertDialog(
            title=ft.Text(operation_title(row, t)),
            content=ft.Text(f"{row['date']} · {account.name}"),
            actions=[
                ft.TextButton(t.get("components.cancel"), on_click=lambda _: close_dialog(self.page, dialog)),
                *([ft.TextButton(t.get("journal.edit.action"), on_click=edit)] if edited else []),
                ft.TextButton(t.get("journal.delete.confirm"), style=ft.ButtonStyle(color=ft.Colors.RED),
                              on_click=remove),
            ],
        )
        self.page.show_dialog(dialog)

    def _describe(self, account, op) -> str:
        """Name `op` for a question, e.g. "Buy VGLA.DE · 20-10-2026 · Fineco".

        Without its row (a ledger left out of step by a rebuild that failed
        offline, see _on_row_tap) only its date and account are named.
        """
        rows = account.df[account.df[OP_ID] == op.id]
        title = [operation_title(rows.iloc[0], self.state.translator)] if not rows.empty else []
        return " · ".join([*title, op.date.strftime(DATE_FORMAT), account.name])

    def _remove(self, account, op, named=False):
        """Delete `op` from `account` (journal_service.delete) in the background; a transfer from both its accounts.

        The operations after it are rebuilt. When it is a transfer, or others
        come after it, the user is asked first: which accounts it is removed
        from, and how many operations will be recalculated. With `named`, the
        user is always asked first, and told which operation it is. The question
        comes once the change is worked out (change_accounts), so a removal
        that would make a later operation impossible (e.g. a sale of shares
        whose buy it is) or leave it short of cash (a buy paid with the
        deposit removed) is refused instead, saying which.
        """
        s = self.state
        t = s.translator
        try:
            half = journal_service.transfer_half(s.accounts, account, op.id)
            if op.transfer_id and half is None and op.counterpart in self._unloaded_accounts():
                raise ValidationError("journal.partner_unavailable", account=op.counterpart)
            later = journal_service.later_operations_deleting(s.accounts, account, op.id)
        except ValidationError as ex:  # an account not moved to the journal, or not loaded
            show_snack(self.page, error_message(t, ex), error=True)
            return

        is_transfer = op.transfer_id is not None
        texts = []
        if is_transfer:
            texts.append(t.get("transactions.transfer_undo_both", first=account.name, second=half[0].name) if half
                         else t.get("transactions.transfer_undo_one", account=account.name))
        if later:
            texts.append(recalculated_text(t, later, "journal.delete"))
        question = None
        if texts or named:
            title = t.get("transactions.transfer_undo_title" if is_transfer else "journal.delete.title")
            text = " ".join(texts)
            if named:
                text = f"{self._describe(account, op)}\n\n{text}".strip()
            question = (title, text, t.get("journal.delete.confirm"))
        change_accounts(self.app, lambda: journal_service.delete(s.accounts, account, op.id), question=question,
                        saved_message=t.get("transactions.transfer_removed" if is_transfer else "transactions.row_removed"))
