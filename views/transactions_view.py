import flet as ft
import pandas as pd
from datetime import datetime, timedelta

from components.snack import show_snack
from services import account_service, config_service
from utils.columns import COLUMNS, rename_for_export, export_headers, OPERATION_LOCALE_KEYS, PRODUCT_LOCALE_KEYS
from utils.constants import REPORT_PREFIX

_DEFAULT_DISPLAY_COLS = [
    "date", "account", "operation", "product", "ticker", "qt_exch",
    "price_eur", "fee", "effective_amount", "pl",
]

_ALL_COLS = COLUMNS


class TransactionsView:
    def __init__(self, page: ft.Page, state):
        self.page = page
        self.state = state

    def build(self) -> ft.Control:
        t = self.state.translator
        if not self.state.brokers:
            return ft.Column([ft.Text(t.get("home.no_account"), size=16)])

        # Set up FilePicker service for export
        self.file_picker = ft.FilePicker()
        self.page.services[:] = [
            s for s in self.page.services if not isinstance(s, ft.FilePicker)
        ]
        self.page.services.append(self.file_picker)

        df = self._get_tx_df()
        sel = self.state.tx_selection

        acc_idx = None if sel == "overview" else int(sel)

        children = [
            ft.Container(
                self._build_dropdown(),
                padding=ft.padding.only(top=5, left=5, right=5),
            ),
            self._build_transactions_section(df, acc_idx),
        ]

        return ft.Column(children, scroll=ft.ScrollMode.AUTO, expand=True,
                         horizontal_alignment=ft.CrossAxisAlignment.CENTER)

    def _build_dropdown(self) -> ft.Control:
        t = self.state.translator
        options = [
            ft.dropdown.Option(key="overview", text=t.get("home.overview")),
        ]
        for k, v in sorted(self.state.brokers.items()):
            options.append(ft.dropdown.Option(key=str(k), text=v))

        return ft.Dropdown(
            menu_style=ft.MenuStyle(
                shape=ft.RoundedRectangleBorder(radius=15),
            ),
            value=self.state.tx_selection,
            options=options,
            on_select=self._on_selection_change,
            expand=True,
            border_width=2.5,
            border_radius=ft.border_radius.all(15),
            border_color=ft.Colors.SECONDARY_CONTAINER,
            bgcolor=ft.Colors.SECONDARY_CONTAINER,
        )

    def _on_selection_change(self, e):
        self.state.tx_selection = e.control.value
        from views import _rebuild_page
        _rebuild_page(self.page, self.state, selected_index=3)

    def _get_tx_df(self):
        sel = self.state.tx_selection
        if sel == "overview":
            all_rows = []
            for idx, acc in self.state.accounts.items():
                df = acc["df"]
                if df is not None and not df.empty and len(df) > 1:
                    all_rows.append(df.iloc[1:].copy())
            if all_rows:
                return pd.concat(all_rows, ignore_index=True)
            return None
        else:
            idx = int(sel)
            acc = self.state.get_account(idx)
            if acc is None:
                return None
            df = acc["df"]
            return df.iloc[1:].copy() if len(df) > 1 else None

    # ── Transactions Section ─────────────────────────────────────────

    def _build_transactions_section(self, df, acc_idx=None) -> ft.Control:
        t = self.state.translator

        self._tx_df = df
        self._acc_idx = acc_idx
        saved_mode, saved_value = config_service.load_tx_filter(self.state.config_folder)
        self._tx_filter_mode = saved_mode
        self._tx_filter_value = saved_value

        self.tx_table_container = ft.Container(padding=ft.padding.only(top=10))
        self._update_tx_table()

        return ft.Column([
            self._build_button_row(acc_idx),
            self.tx_table_container,
        ], spacing=15, horizontal_alignment=ft.CrossAxisAlignment.CENTER)

    def _build_button_row(self, acc_idx) -> ft.Control:
        t = self.state.translator

        filters_btn = ft.Card(
            content=ft.Container(
                content=ft.Column([
                    ft.Icon(ft.Icons.FILTER_LIST, size=32),
                    ft.Text(t.get("transactions.filters"), text_align=ft.TextAlign.CENTER),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
                padding=15,
                border_radius=15,
                height=90,
                bgcolor=ft.Colors.SECONDARY_CONTAINER,
                on_click=self._on_open_filters,
                ink=True,
                #expand=True,
            ),
            elevation=3,
            col={"xs": 4, "md": 4},
        )

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
            padding=ft.padding.only(left=20, right=20, top=30),
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
        dlg_filter_field = ft.TextField(
            value=str(self._tx_filter_value),
            keyboard_type=ft.KeyboardType.NUMBER,
            input_filter=ft.NumbersOnlyInputFilter(),
            width=100,
            border_radius=ft.border_radius.all(15),
            border_color=ft.Colors.with_opacity(0.40, ft.Colors.GREY),
        )

        def on_radio_change(ev):
            if dlg_radio.value == "count":
                dlg_filter_field.value = "5"
            else:
                dlg_filter_field.value = "90"
            self.page.update()
        dlg_radio.on_change = on_radio_change

        # Column visibility checkboxes (all 29 columns)
        saved_cols = config_service.load_tx_columns(self.state.config_folder)
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
                val = 5 if mode == "count" else 90
            self._tx_filter_mode = mode
            self._tx_filter_value = val
            config_service.save_tx_filter(self.state.config_folder, mode, val)

            # Save column visibility
            visible = [col for col, cb in checkboxes.items() if cb.value]
            if not visible:
                visible = list(_DEFAULT_DISPLAY_COLS)
            config_service.save_tx_columns(self.state.config_folder, visible)

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

    def _update_tx_table(self):
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
        self.tx_table_container.content = self._build_transactions_table(df_sorted)

    # ── Table ──────────────────────────────────────────────────────

    def _build_transactions_table(self, df) -> ft.Control:
        t = self.state.translator
        if df is None or df.empty:
            return ft.Text(t.get("transactions.empty"), size=16)

        saved_cols = config_service.load_tx_columns(self.state.config_folder)
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
        acc = self.state.get_account(idx)
        if acc is None:
            return
        csv_bytes = self._prepare_export_csv(acc["df"].iloc[1:])
        await self._save_via_picker(acc["file"], csv_bytes)

    async def _on_export_overview(self, e):
        t = self.state.translator
        df = self._tx_df
        if df is None or df.empty:
            show_snack(self.page, t.get("transactions.no_data"), error=True)
            return
        csv_bytes = self._prepare_export_csv(df)
        await self._save_via_picker(REPORT_PREFIX + "All Accounts.csv", csv_bytes)

    async def _save_via_picker(self, file_name, csv_bytes):
        t = self.state.translator
        path = await self.file_picker.save_file(
            file_name=file_name,
            allowed_extensions=["csv"],
            src_bytes=csv_bytes,
        )
        if path:
            # On desktop, save_file() only returns the path — we must write the file
            if not self.page.web and not self.page.platform.is_mobile():
                with open(path, "wb") as f:
                    f.write(csv_bytes)
            show_snack(self.page, t.get("transactions.export_success"))

    def _on_remove_row(self, e, idx):
        s = self.state
        t = s.translator
        acc = s.get_account(idx)
        if acc and len(acc["df"]) > 1:
            acc["df"] = acc["df"].iloc[:-1]
            account_service.save_account(acc["df"], acc["path"])
            show_snack(self.page, t.get("transactions.row_removed"))
            from views import _rebuild_page
            _rebuild_page(self.page, s, selected_index=3)
        else:
            show_snack(self.page, t.get("transactions.no_rows"), error=True)
