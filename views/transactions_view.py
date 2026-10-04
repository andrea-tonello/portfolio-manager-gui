import flet as ft
import pandas as pd
from datetime import datetime, timedelta

from components.action_card import action_card
from components.file_export import get_file_picker, save_bytes
from components.inputs import account_selector, rounded_text_field
from components.snack import show_snack
from services import account_service, config_service
from utils.columns import COLUMNS, rename_for_export, export_headers, OPERATION_LOCALE_KEYS, PRODUCT_LOCALE_KEYS
from utils.constants import DEFAULT_TX_FILTER, REPORT_PREFIX

_DEFAULT_DISPLAY_COLS = [
    "date", "account", "operation", "product", "ticker", "qt_exch",
    "price_eur", "fee", "effective_amount", "pl",
]

_ALL_COLS = COLUMNS
_PAGE_SIZE = 20


class TransactionsView:
    def __init__(self, app):
        """Build the Transactions tab for the controller's page and current state."""
        self.app = app
        self.page = app.page
        self.state = app.state

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
        saved_mode, saved_value = config_service.load_tx_filter(self.state.user_config_folder)
        self._tx_filter_mode = saved_mode
        self._tx_filter_value = saved_value

        self.tx_table_container = ft.Container(padding=ft.Padding.only(top=10))
        self._update_tx_table()

        return ft.Column([
            self._build_button_row(acc_idx),
            self.tx_table_container,
        ], spacing=15, horizontal_alignment=ft.CrossAxisAlignment.CENTER)

    def _build_button_row(self, acc_idx) -> ft.Control:
        t = self.state.translator

        filters_btn = action_card(ft.Icons.FILTER_LIST, t.get("transactions.filters"), self._on_open_filters,
                                  padding=15, height=90, col={"xs": 4, "md": 4})

        if acc_idx is not None:
            async def on_export(e):
                await self._on_export(e, acc_idx)
            export_click = on_export
            remove_click = lambda e, i=acc_idx: self._on_remove_row(e, i)
        else:
            export_click = self._on_export_overview
            remove_click = None

        export_btn = ft.FilledButton(
            t.get("transactions.export_csv"),
            icon=ft.Icons.SAVE,
            on_click=export_click,
            height=40,
            width=600,
            expand=True,
        )
        remove_btn = ft.OutlinedButton(
            t.get("transactions.remove_row"),
            icon=ft.Icons.UNDO,
            on_click=remove_click,
            disabled=(acc_idx is None),
            height=40,
            width=600,
            expand=True,
        )

        right_col = ft.Column([export_btn, remove_btn], spacing=8, expand=True, col={"xs": 8, "md": 8},)

        return ft.Container(
            ft.ResponsiveRow([filters_btn, right_col], spacing=20, width=400, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.Padding.only(left=20, right=20, top=30),
        )

    # ── Filters Dialog ────────────────────────────────────────────────

    def _on_open_filters(self, e):
        t = self.state.translator
        col_labels = export_headers(t)

        # Row filter controls
        dlg_radio = ft.RadioGroup(
            value=self._tx_filter_mode,
            content=ft.Column([
                ft.Radio(value="count", label=t.get("transactions.filter_by_count")),
                ft.Radio(value="days", label=t.get("transactions.filter_by_days")),
            ], spacing=0),
        )
        dlg_filter_field = rounded_text_field(
            value=str(self._tx_filter_value),
            keyboard_type=ft.KeyboardType.NUMBER,
            input_filter=ft.NumbersOnlyInputFilter(),
            width=100,
        )

        def on_radio_change(ev):
            dlg_filter_field.value = str(DEFAULT_TX_FILTER[dlg_radio.value])
            self.page.update()
        dlg_radio.on_change = on_radio_change

        # Column visibility checkboxes (one per column in COLUMNS)
        saved_cols = config_service.load_tx_columns(self.state.user_config_folder)
        visible_set = set(saved_cols) if saved_cols else set(_DEFAULT_DISPLAY_COLS)

        checkboxes = {}
        for col in _ALL_COLS:
            label = col_labels.get(col, col)
            cb = ft.Checkbox(label=label, value=(col in visible_set))
            checkboxes[col] = cb

        def on_cancel(ev):
            self.page.pop_dialog()

        def on_apply(ev):
            # Save row filter
            mode = dlg_radio.value
            try:
                val = int(dlg_filter_field.value)
                if val <= 0:
                    raise ValueError
            except (ValueError, TypeError):
                val = DEFAULT_TX_FILTER[mode]
            self._tx_filter_mode = mode
            self._tx_filter_value = val
            config_service.save_tx_filter(self.state.user_config_folder, mode, val)

            # Save column visibility
            visible = [col for col, cb in checkboxes.items() if cb.value]
            if not visible:
                visible = list(_DEFAULT_DISPLAY_COLS)
            config_service.save_tx_columns(self.state.user_config_folder, visible)

            self.page.pop_dialog()
            self._update_tx_table()
            self.page.update()

        dlg = ft.AlertDialog(
            title=ft.Text(t.get("transactions.filters")),
            content=ft.Container(
                content=ft.Column([
                    ft.Text(t.get("transactions.filter_by"), size=14, weight=ft.FontWeight.BOLD),
                    ft.Row([
                        dlg_radio,
                        dlg_filter_field,
                    ], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    ft.Divider(),
                    ft.Text(t.get("transactions.filter_columns"), size=14, weight=ft.FontWeight.BOLD),
                    ft.Column([checkboxes[col] for col in _ALL_COLS], spacing=0),
                ], scroll=ft.ScrollMode.AUTO, spacing=10),
                height=400,
                width=400,
            ),
            actions=[
                ft.TextButton(t.get("components.cancel"), on_click=on_cancel),
                ft.FilledButton(t.get("components.apply"), on_click=on_apply),
            ],
        )
        self.page.show_dialog(dlg)

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

        df_sorted = df.copy()
        df_sorted["_date_parsed"] = pd.to_datetime(df_sorted["date"], dayfirst=True, errors="coerce")
        df_sorted["_orig_idx"] = range(len(df_sorted))
        df_sorted = df_sorted.sort_values(["_date_parsed", "_orig_idx"], ascending=[False, False])

        if self._tx_filter_mode == "days":
            cutoff = pd.Timestamp(datetime.now() - timedelta(days=self._tx_filter_value))
            df_sorted = df_sorted[df_sorted["_date_parsed"] >= cutoff]
        else:
            df_sorted = df_sorted.head(self._tx_filter_value)

        df_sorted = df_sorted.drop(columns=["_date_parsed", "_orig_idx"])
        self._tx_filtered_df = df_sorted

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

        saved_cols = config_service.load_tx_columns(self.state.user_config_folder)
        display_cols = saved_cols if saved_cols else list(_DEFAULT_DISPLAY_COLS)
        available_cols = [c for c in display_cols if c in df.columns]

        col_labels = export_headers(t)
        op_map = {k: t.get(v).strip() for k, v in OPERATION_LOCALE_KEYS.items()}
        prod_map = {k: t.get(v).strip() for k, v in PRODUCT_LOCALE_KEYS.items()}

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
                    if col == "operation":
                        val = op_map.get(val, val)
                    elif col == "product":
                        val = prod_map.get(val, val)
                cells.append(ft.DataCell(ft.Text(val, size=10)))
            rows.append(ft.DataRow(cells=cells))

        return ft.Row([
            ft.DataTable(
                columns=columns,
                rows=rows,
                horizontal_lines=ft.BorderSide(1, ft.Colors.GREY_300),
                column_spacing=12,
            ),
        ], scroll=ft.ScrollMode.ALWAYS,)

    # ── Export / Remove ───────────────────────────────────────────────

    def _prepare_export_csv(self, df):
        """Sort df by date descending, rename to locale headers, return CSV bytes."""
        df = df.copy()
        df["_date_parsed"] = pd.to_datetime(df["date"], dayfirst=True, errors="coerce")
        df = df.sort_values("_date_parsed", ascending=False).drop(columns=["_date_parsed"])
        df = rename_for_export(df, self.state.translator)
        return df.to_csv(index=False).encode("utf-8")

    async def _on_export(self, e, idx):
        account = self.state.get_account(idx)
        if account is None:
            return
        csv_bytes = self._prepare_export_csv(account.transactions)
        await self._save_via_picker(account_service.report_filename(account.name), csv_bytes)

    async def _on_export_overview(self, e):
        t = self.state.translator
        df = self._tx_df
        if df is None or df.empty:
            show_snack(self.page, t.get("transactions.no_data"), error=True)
            return
        csv_bytes = self._prepare_export_csv(df)
        await self._save_via_picker(REPORT_PREFIX + "All Accounts.csv", csv_bytes)

    async def _save_via_picker(self, file_name, csv_bytes):
        """Let the user save the transactions as `file_name`, confirming once saved."""
        t = self.state.translator
        await save_bytes(self.page, self.file_picker, file_name, csv_bytes, "csv", t.get("transactions.export_success"))

    def _on_remove_row(self, e, idx):
        s = self.state
        t = s.translator
        account = s.get_account(idx)
        if account and account.has_transactions:
            s.commit(idx, account.df.iloc[:-1])
            show_snack(self.page, t.get("transactions.row_removed"))
            self.app.refresh()
        else:
            show_snack(self.page, t.get("transactions.no_rows"), error=True)
