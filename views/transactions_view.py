import flet as ft
import pandas as pd
from datetime import datetime, timedelta

from components.snack import show_snack
from services import account_service
from utils.other_utils import _GLOSSARY_KEYS


class TransactionsView:
    def __init__(self, page: ft.Page, state):
        self.page = page
        self.state = state

    def build(self) -> ft.Control:
        t = self.state.translator
        if not self.state.brokers:
            return ft.Column([ft.Text(t.get("home.no_account"), size=16)])

        df = self._get_tx_df()
        sel = self.state.tx_selection

        children = [
            ft.Container(
                self._build_dropdown(),
                padding=ft.padding.only(top=5, left=5, right=5),
            ),
            self._build_transactions_section(df),
        ]

        if sel != "overview":
            children.append(ft.Divider())
            children.append(self._build_action_buttons(int(sel)))

        return ft.Column(children, scroll=ft.ScrollMode.AUTO, expand=True)

    def _build_dropdown(self) -> ft.Control:
        t = self.state.translator
        options = [
            ft.dropdown.Option(key="overview", text=t.get("home.overview")),
        ]
        for k, v in sorted(self.state.brokers.items()):
            options.append(ft.dropdown.Option(key=str(k), text=v))

        return ft.Dropdown(
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

    # ── Transactions Section (filter + table) ─────────────────────────

    def _build_transactions_section(self, df) -> ft.Control:
        t = self.state.translator

        self._tx_df = df
        self._tx_filter_mode = "count"
        self._tx_filter_value = 5

        self.tx_table_container = ft.Container()

        self.filter_radio = ft.RadioGroup(
            value="count",
            on_change=self._on_filter_mode_change,
            content=ft.Row([
                ft.Radio(value="count", label=t.get("home.filter_by_count")),
                ft.Radio(value="days", label=t.get("home.filter_by_days")),
            ], spacing=16),
        )
        self.tx_filter_field = ft.TextField(
            value="5",
            keyboard_type=ft.KeyboardType.NUMBER,
            width=80,
            on_submit=self._on_filter_apply,
            border_radius=ft.border_radius.all(15),
        )
        filter_btn = ft.FilledButton(
            content=t.get("components.apply"),
            on_click=self._on_filter_apply,
        )

        self._update_tx_table()

        return ft.Column([
            ft.Container(height=10),
            ft.Row([
                ft.Text(t.get("review.title").strip(), weight=ft.FontWeight.BOLD, size=20),
                self._build_info_button(),
            ], spacing=8),
            ft.Row([
                self.filter_radio,
                self.tx_filter_field,
                filter_btn,
            ], spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER, wrap=True),
            self.tx_table_container,
        ], spacing=20)

    def _on_filter_mode_change(self, e):
        self._tx_filter_mode = self.filter_radio.value
        if self.filter_radio.value == "count":
            self.tx_filter_field.value = "5"
        else:
            self.tx_filter_field.value = "90"
        self._update_tx_table()
        self.page.update()

    def _on_filter_apply(self, e):
        try:
            val = int(self.tx_filter_field.value)
            if val <= 0:
                raise ValueError
            self._tx_filter_value = val
        except (ValueError, TypeError):
            return
        self._update_tx_table()
        self.page.update()

    def _update_tx_table(self):
        df = self._tx_df
        if df is None or df.empty:
            self.tx_table_container.content = ft.Text("No data", size=12, italic=True)
            return

        df_sorted = df.copy()
        df_sorted["_date_parsed"] = pd.to_datetime(df_sorted["Data"], dayfirst=True, errors="coerce")
        df_sorted["_orig_idx"] = range(len(df_sorted))
        df_sorted = df_sorted.sort_values(["_date_parsed", "_orig_idx"], ascending=[False, False])

        if self._tx_filter_mode == "days":
            cutoff = pd.Timestamp(datetime.now() - timedelta(days=self._tx_filter_value))
            df_sorted = df_sorted[df_sorted["_date_parsed"] >= cutoff]
        else:
            df_sorted = df_sorted.head(self._tx_filter_value)

        df_sorted = df_sorted.drop(columns=["_date_parsed", "_orig_idx"])
        self.tx_table_container.content = self._build_transactions_table(df_sorted)

    # ── Info / Glossary ─────────────────────────────────────────────

    def _build_info_button(self) -> ft.Control:
        return ft.IconButton(
            icon=ft.Icons.INFO_OUTLINE,
            icon_size=24,
            tooltip="Info",
            on_click=lambda e: self._show_glossary(1),
        )

    def _show_glossary(self, page_num):
        t = self.state.translator
        keys = _GLOSSARY_KEYS.get(page_num, [])
        keys = keys[1:]     # remove title
        text = "\n".join(t.get(k) for k in keys)
        dlg = ft.AlertDialog(
            title=ft.Text(t.get(f"glossary.page_{page_num}.title")),
            content=ft.Column([
                ft.Text(text, size=12, selectable=True),
            ], scroll=ft.ScrollMode.AUTO, tight=True),
            actions=[ft.TextButton("OK", on_click=lambda e: self.page.pop_dialog())],
        )
        self.page.show_dialog(dlg)

    # ── Table ──────────────────────────────────────────────────────

    def _build_transactions_table(self, df) -> ft.Control:
        if df is None or df.empty:
            return ft.Text("No data", size=12, italic=True)

        display_cols = ["Data", "Conto", "Operazione", "Prodotto", "Ticker", "QT. Scambio",
                        "Prezzo EUR", "Commissioni", "Imp. Effettivo Operaz.", "P&L"]
        available_cols = [c for c in display_cols if c in df.columns]

        columns = [ft.DataColumn(ft.Text(col, size=11, weight=ft.FontWeight.BOLD)) for col in available_cols]
        rows = []
        for _, row in df.iterrows():
            cells = []
            for col in available_cols:
                val = row.get(col, "")
                if pd.isna(val) or val is None:
                    val = ""
                cells.append(ft.DataCell(ft.Text(str(val), size=10)))
            rows.append(ft.DataRow(cells=cells))

        return ft.Row([
            ft.DataTable(
                columns=columns,
                rows=rows,
                horizontal_lines=ft.BorderSide(1, ft.Colors.GREY_300),
                column_spacing=12,
            ),
        ], scroll=ft.ScrollMode.ALWAYS)

    # ── Action Buttons (single account only) ──────────────────────

    def _build_action_buttons(self, idx: int) -> ft.Control:
        t = self.state.translator
        return ft.Row([
            ft.ElevatedButton(
                t.get("components.export"),
                icon=ft.Icons.SAVE,
                on_click=lambda e, i=idx: self._on_export(e, i),
            ),
            ft.OutlinedButton(
                t.get("components.remove_row"),
                icon=ft.Icons.UNDO,
                on_click=lambda e, i=idx: self._on_remove_row(e, i),
            ),
        ], wrap=True)

    def _on_export(self, e, idx):
        s = self.state
        t = s.translator
        acc = s.get_account(idx)
        if acc is None:
            return
        try:
            account_service.export_account(acc["df"], acc["path"], s.user_folder, acc["file"])
            s.mark_account_saved(idx)
            show_snack(self.page, t.get("home.export_success"))
            from views import _rebuild_page
            _rebuild_page(self.page, s, selected_index=3)
        except Exception as ex:
            show_snack(self.page, str(ex), error=True)

    def _on_remove_row(self, e, idx):
        s = self.state
        t = s.translator
        acc = s.get_account(idx)
        if acc and len(acc["df"]) > 1:
            acc["df"] = acc["df"].iloc[:-1]
            show_snack(self.page, t.get("remove_row.row_removed"))
            from views import _rebuild_page
            _rebuild_page(self.page, s, selected_index=3)
        else:
            show_snack(self.page, t.get("remove_row.no_rows"), error=True)
