import flet as ft
import pandas as pd
from datetime import datetime

from components.snack import show_snack
from services import config_service
from services.market_data import download_close
from utils.other_utils import round_half_up
from utils.account import get_asset_value


class HomeView:
    def __init__(self, page: ft.Page, state):
        self.page = page
        self.state = state

    def build(self) -> ft.Control:
        t = self.state.translator
        if not self.state.brokers:
            return ft.Column([ft.Text(t.get("home.no_account"), size=16)])

        return ft.Column([
            ft.Container(
                ft.Row([
                    self._build_dropdown(),
                    ft.IconButton(
                        icon=ft.Icons.REFRESH,
                        tooltip=t.get("components.loading"),
                        on_click=self._on_refresh,
                    ),
                ]),
                padding=ft.padding.only(top=5, left=5, right=5),
            ),
            self._build_content(),
        ], scroll=ft.ScrollMode.AUTO, expand=True)

    def _build_dropdown(self) -> ft.Control:
        t = self.state.translator
        options = [
            ft.dropdown.Option(
                key="overview",
                text=t.get("home.overview"),
            ),
        ]
        for k, v in sorted(self.state.brokers.items()):
            options.append(ft.dropdown.Option(key=str(k), text=v))

        return ft.Dropdown(
            #label=t.get("nav.home"),
            value=self.state.home_selection,
            options=options,
            on_select=self._on_selection_change,
            expand=True,
            border_width=2.5,
            border_radius=ft.border_radius.all(15),
            border_color=ft.Colors.SECONDARY_CONTAINER,
            bgcolor=ft.Colors.SECONDARY_CONTAINER,
        )

    def _on_selection_change(self, e):
        self.state.home_selection = e.control.value
        from views import _rebuild_page
        _rebuild_page(self.page, self.state, selected_index=0)

    def _on_refresh(self, e):
        self._fetch_live_values()

    def _build_content(self) -> ft.Control:
        sel = self.state.home_selection
        if sel == "overview":
            return self._build_overview()
        else:
            idx = int(sel)
            return self._build_single_account(idx)
        
    # ── Watchlist (independent of Overview vs. specific account) ──────

    def _build_watchlist(self) -> ft.Control:
        t = self.state.translator
        expanded = getattr(self.state, '_watchlist_expanded', False)

        self._watchlist_toggle_icon = ft.Icon(
            ft.Icons.KEYBOARD_ARROW_DOWN if expanded else ft.Icons.KEYBOARD_ARROW_RIGHT,
            size=24,
        )
        header = ft.Container(
            content=ft.Row([
                ft.Text(t.get("home.watchlist"), size=16, weight=ft.FontWeight.BOLD),
                self._watchlist_toggle_icon,
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            on_click=self._toggle_watchlist,
            padding=ft.padding.symmetric(horizontal=16, vertical=8),
            ink=True,
        )

        self._watchlist_ticker_field = ft.TextField(
            label=t.get("home.watchlist_add"),
            border_radius=ft.border_radius.all(15),
            expand=True,
            on_submit=self._on_watchlist_add,
        )
        add_row = ft.Row([
            self._watchlist_ticker_field,
            ft.IconButton(
                icon=ft.Icons.ADD_CIRCLE_OUTLINE,
                on_click=self._on_watchlist_add,
            ),
        ], spacing=8)

        self._watchlist_items_container = ft.Column([], spacing=4)
        self._watchlist_loading = ft.ProgressRing(visible=False, width=14, height=14)

        self._watchlist_body = ft.Column([
            add_row,
            ft.Row([self._watchlist_loading], alignment=ft.MainAxisAlignment.CENTER),
            self._watchlist_items_container,
        ], spacing=8, visible=expanded)

        if expanded and self.state.watchlist:
            self._fetch_watchlist_prices()

        return ft.Column([
            ft.Divider(),
            header,
            ft.Container(self._watchlist_body, padding=ft.padding.only(left=16, right=16, bottom=8)),
        ], spacing=0)

    def _toggle_watchlist(self, e):
        expanded = not getattr(self.state, '_watchlist_expanded', False)
        self.state._watchlist_expanded = expanded
        self._watchlist_body.visible = expanded
        self._watchlist_toggle_icon.name = (
            ft.Icons.KEYBOARD_ARROW_DOWN if expanded else ft.Icons.KEYBOARD_ARROW_RIGHT
        )
        if expanded and self.state.watchlist:
            self._fetch_watchlist_prices()
        self.page.update()

    def _on_watchlist_add(self, e):
        t = self.state.translator
        ticker = self._watchlist_ticker_field.value.strip().upper()
        if not ticker:
            return
        if ticker in self.state.watchlist:
            show_snack(self.page, t.get("home.watchlist_duplicate"))
            return
        self.state.watchlist.append(ticker)
        config_service.save_watchlist(self.state.config_folder, self.state.watchlist)
        self._watchlist_ticker_field.value = ""
        show_snack(self.page, t.get("home.watchlist_added"))
        self._fetch_watchlist_prices()
        self.page.update()

    def _on_watchlist_remove(self, ticker):
        t = self.state.translator
        if ticker in self.state.watchlist:
            self.state.watchlist.remove(ticker)
            config_service.save_watchlist(self.state.config_folder, self.state.watchlist)
            show_snack(self.page, t.get("home.watchlist_removed"))
            self._fetch_watchlist_prices()
            self.page.update()

    def _fetch_watchlist_prices(self):
        tickers = self.state.watchlist[:]
        if not tickers:
            self._watchlist_items_container.controls = []
            return
        self._watchlist_loading.visible = True
        self.page.update()

        def worker():
            try:
                data = download_close(tickers, period="2d")
                if isinstance(data, pd.Series):
                    data = data.to_frame(name=tickers[0])
                data = data.dropna(how="all")

                rows = []
                for tk in tickers:
                    if tk not in data.columns or data[tk].dropna().empty:
                        rows.append(self._build_watchlist_item(tk, None, None))
                        continue
                    series = data[tk].dropna()
                    price = float(series.iloc[-1])
                    prev_close = float(series.iloc[-2]) if len(series) >= 2 else None
                    rows.append(self._build_watchlist_item(tk, price, prev_close))

                self._watchlist_items_container.controls = rows
            except Exception:
                self._watchlist_items_container.controls = [
                    self._build_watchlist_item(tk, None, None) for tk in tickers
                ]
            finally:
                self._watchlist_loading.visible = False
                self.page.update()

        self.page.run_thread(worker)

    def _build_watchlist_item(self, ticker: str, price, prev_close) -> ft.Control:
        chip = ft.Container(
            content=ft.Text(ticker, weight=ft.FontWeight.BOLD, size=13),
            bgcolor=ft.Colors.with_opacity(0.12, ft.Colors.GREY),
            border_radius=10,
            padding=ft.padding.symmetric(vertical=8, horizontal=14),
        )

        if price is not None:
            price_text = ft.Text(f"{price:.2f}", size=13)
            if prev_close is not None and prev_close != 0:
                change_pct = (price - prev_close) / prev_close * 100
                if change_pct > 0:
                    indicator = ft.Text(f"+{change_pct:.2f}%", size=11, color=ft.Colors.GREEN)
                elif change_pct < 0:
                    indicator = ft.Text(f"{change_pct:.2f}%", size=11, color=ft.Colors.RED)
                else:
                    indicator = ft.Text("0.00%", size=11, color=ft.Colors.GREY)
            else:
                indicator = ft.Text("", size=11)
        else:
            price_text = ft.Text("---", size=13, color=ft.Colors.GREY)
            indicator = ft.Text("", size=11)

        delete_btn = ft.IconButton(
            icon=ft.Icons.CLOSE,
            icon_size=16,
            on_click=lambda e, tk=ticker: self._on_watchlist_remove(tk),
        )

        return ft.Container(
            content=ft.Row([
                chip,
                ft.Column([price_text, indicator], spacing=0, horizontal_alignment=ft.CrossAxisAlignment.END),
                delete_btn,
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
               vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.padding.only(left=4),
        )

    # ── Overview ──────────────────────────────────────────────────────

    # (also shared with single accounts)
    def _open_positions_header(self) -> ft.Control:
        t = self.state.translator
        header = ft.Container(
            content=ft.Row([
                ft.Column([
                    ft.Text(t.get("home.open_positions"), size=16, weight=ft.FontWeight.BOLD),
                    ft.Text(t.get("home.open_positions_descr"), size=11, color=ft.Colors.GREY_400),
                ], spacing=1),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            padding=ft.padding.symmetric(horizontal=16, vertical=8),
            ink=True,
        ) 
        return header


    def _build_overview(self) -> ft.Control:
        t = self.state.translator
        accounts = self.state.accounts
        if not accounts:
            return ft.Text(t.get("home.no_account"), size=14)

        # Start with stale values from DataFrame
        total_nav = 0.0
        total_cash = 0.0
        total_assets = 0.0

        for idx, acc in accounts.items():
            df = acc["df"]
            if df is not None and not df.empty:
                last_row = df.iloc[-1]
                total_nav += float(last_row.get("NAV", 0) or 0)
                total_cash += float(last_row.get("Liquidita Attuale", 0) or 0)
                total_assets += float(last_row.get("Valore Titoli", 0) or 0)

        cards = self._build_stats_cards(total_nav, total_cash, total_assets)
        self._positions_container = ft.Column([], spacing=6)
        watchlist = self._build_watchlist()
        header = self._open_positions_header()

        content = ft.Column([
            cards,
            header,
            self._positions_container,
            watchlist,
        ], spacing=10)

        # Auto-fetch live values
        self._fetch_live_values()

        return content

    # ── Single Account ────────────────────────────────────────────────

    def _build_single_account(self, idx: int) -> ft.Control:
        t = self.state.translator
        acc = self.state.get_account(idx)
        if acc is None:
            return ft.Text(t.get("home.no_account"), size=14)

        df = acc["df"]
        broker_name = self.state.brokers.get(idx, "")
        edited = self.state.is_account_edited(idx)
        status_text = t.get("main_menu.unsaved_changes") if edited else t.get("main_menu.no_changes")
        status_color = ft.Colors.ORANGE if edited else ft.Colors.GREEN

        # Start with stale values
        nav = float(df.iloc[-1].get("NAV", 0) or 0) if not df.empty else 0
        cash = float(df.iloc[-1].get("Liquidita Attuale", 0) or 0) if not df.empty else 0
        assets = float(df.iloc[-1].get("Valore Titoli", 0) or 0) if not df.empty else 0

        cards = self._build_stats_cards(nav, cash, assets)
        self._positions_container = ft.Column([], spacing=6)
        watchlist = self._build_watchlist()

        content = ft.Column([
            ft.Text(
                t.get("main_menu.operating_on",
                       account_name=broker_name,
                       file=acc["file"],
                       rows=acc["len_df_init"] - 1),
                size=14,
            ),
            ft.Text(status_text, italic=True, color=status_color, size=13),
            cards,
            self._positions_container,
            watchlist,
        ], spacing=10)

        # Auto-fetch live values
        self._fetch_live_values()

        return content

    # ── Live Value Fetch ──────────────────────────────────────────────

    def _fetch_live_values(self):
        """Fetch live asset values from yfinance in background and update cards."""
        self._refresh_loading.visible = True
        self.page.update()

        def worker():
            try:
                s = self.state
                t = s.translator
                ref_date = pd.Timestamp(datetime.now())
                sel = s.home_selection
                all_positions = []

                if sel == "overview":
                    total_cash = 0.0
                    total_assets = 0.0
                    aggr = {}  # ticker -> {quantity, total_cost, price}
                    for idx, acc in s.accounts.items():
                        df = acc["df"]
                        if df is None or df.empty:
                            continue
                        total_cash += float(df.iloc[-1].get("Liquidita Attuale", 0) or 0)
                        positions = get_asset_value(t, df, ref_date=ref_date, suppress_progress=True)
                        if positions:
                            total_assets += round_half_up(sum(p["value"] for p in positions))
                            for p in positions:
                                tk = p["ticker"]
                                if tk in aggr:
                                    aggr[tk]["quantity"] += p["quantity"]
                                    aggr[tk]["total_cost"] += p["quantity"] * p["pmc"]
                                else:
                                    aggr[tk] = {
                                        "quantity": p["quantity"],
                                        "total_cost": p["quantity"] * p["pmc"],
                                        "price": p["price"],
                                    }
                    for tk, d in aggr.items():
                        all_positions.append({
                            "ticker": tk,
                            "quantity": d["quantity"],
                            "pmc": d["total_cost"] / d["quantity"] if d["quantity"] else 0,
                            "price": d["price"],
                        })
                    total_nav = total_cash + total_assets
                    self._current_nav_str = f"{total_nav:,.2f}\u20ac"
                    self._current_assets_str = f"{total_assets:,.2f}\u20ac"
                    self._current_cash_str = f"{total_cash:,.2f}\u20ac"
                else:
                    idx = int(sel)
                    acc = s.get_account(idx)
                    if acc is None:
                        return
                    df = acc["df"]
                    cash = float(df.iloc[-1].get("Liquidita Attuale", 0) or 0) if not df.empty else 0
                    positions = get_asset_value(t, df, ref_date=ref_date, suppress_progress=True)
                    assets = round_half_up(sum(p["value"] for p in positions)) if positions else 0.0
                    nav = cash + assets
                    self._current_nav_str = f"{nav:,.2f}\u20ac"
                    self._current_assets_str = f"{assets:,.2f}\u20ac"
                    self._current_cash_str = f"{cash:,.2f}\u20ac"
                    all_positions = [
                        {"ticker": p["ticker"], "quantity": p["quantity"],
                         "pmc": p["pmc"], "price": p["price"]}
                        for p in (positions or [])
                    ]

                hidden = getattr(s, '_home_values_hidden', False)
                if not hidden:
                    self._nav_text.value = self._current_nav_str
                    self._assets_text.value = f"Assets   {self._current_assets_str}"
                    self._cash_text.value = f"Cash   {self._current_cash_str}"

                self._update_positions(all_positions, hidden)
            except Exception:
                pass  # Silently fail - stale values remain
            finally:
                self._refresh_loading.visible = False
                self.page.update()

        self.page.run_thread(worker)

    # ── Shared Components ─────────────────────────────────────────────

    def _build_stats_cards(self, nav, cash, assets) -> ft.Control:
        t = self.state.translator
        hidden = getattr(self.state, '_home_values_hidden', False)
        hidden_mask = "\u2022\u2022\u2022\u2022\u2022\u2022"
        loading_str = "---"

        self._current_nav_str = loading_str
        self._current_assets_str = loading_str
        self._current_cash_str = loading_str

        self._nav_text = ft.Text(
            hidden_mask if hidden else loading_str, size=48,
            weight=ft.FontWeight.BOLD,
            visible=not hidden,
        )
        self._hidden_placeholder = ft.Container(
            content=ft.Text(
                t.get("home.hidden"), size=18,
                color=ft.Colors.GREY_500, text_align=ft.TextAlign.CENTER,
            ),
            bgcolor=ft.Colors.with_opacity(0.15, ft.Colors.GREY),
            border_radius=10,
            padding=ft.padding.symmetric(vertical=15, horizontal=30),
            alignment=ft.alignment.Alignment.CENTER,
            visible=hidden,
        )
        self._assets_text = ft.Text(
            f"Assets   {hidden_mask if hidden else loading_str}",
            size=14,
        )
        self._cash_text = ft.Text(
            f"Cash   {hidden_mask if hidden else loading_str}",
            size=14,
        )
        self._visibility_btn = ft.IconButton(
            icon=ft.Icons.VISIBILITY_OFF if hidden else ft.Icons.VISIBILITY,
            icon_size=24, on_click=self._toggle_visibility,
            style=ft.ButtonStyle(
                bgcolor=ft.Colors.with_opacity(0.2, ft.Colors.GREY),
                shape=ft.CircleBorder(),
            ),
        )
        self._refresh_loading = ft.ProgressRing(visible=False, width=16, height=16)

        return ft.Column([
            ft.Card(
                content=ft.Container(
                    content=ft.Column([
                        self._nav_text,
                        self._hidden_placeholder,
                        ft.Row([
                            self._visibility_btn,
                            ft.Column([
                                self._assets_text,
                                self._cash_text,
                            ], spacing=2),
                        ], spacing=12),
                    ], spacing=8),
                    padding=20,
                ),
            ),
            ft.Row([self._refresh_loading], alignment=ft.MainAxisAlignment.CENTER),
        ], spacing=4)

    def _toggle_visibility(self, e):
        hidden = not getattr(self.state, '_home_values_hidden', False)
        self.state._home_values_hidden = hidden
        hidden_mask = "\u2022\u2022\u2022\u2022\u2022\u2022"

        self._nav_text.visible = not hidden
        self._hidden_placeholder.visible = hidden
        self._visibility_btn.icon = ft.Icons.VISIBILITY_OFF if hidden else ft.Icons.VISIBILITY

        if hidden:
            self._assets_text.value = f"Assets   {hidden_mask}"
            self._cash_text.value = f"Cash   {hidden_mask}"
            self._positions_container.visible = False
        else:
            self._assets_text.value = f"Assets   {self._current_assets_str}"
            self._cash_text.value = f"Cash   {self._current_cash_str}"
            self._positions_container.visible = True
        self.page.update()

    def _update_positions(self, positions, hidden=False):
        """Build position rows from fetched data."""
        if not positions:
            self._positions_container.controls = []
            return
        rows = []
        for pos in positions:
            ticker = pos["ticker"]
            qty = pos["quantity"]
            pmc = pos["pmc"]
            price = pos["price"]
            qty_str = f"{int(qty)}" if qty == int(qty) else f"{qty:.2f}"
            chip = ft.Container(
                content=ft.Column([
                    ft.Text(ticker, weight=ft.FontWeight.BOLD, size=13),
                    ft.Text("\u00d7"+qty_str, size=11, color=ft.Colors.GREY_400),
                ], spacing=1, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                bgcolor=ft.Colors.with_opacity(0.12, ft.Colors.GREY),
                border_radius=10,
                padding=ft.padding.symmetric(vertical=6, horizontal=12),
            )
            row = ft.Row([
                ft.Container(chip, expand=2, padding=ft.padding.only(left=15, right=45)),
                ft.Container(ft.Text(f"{pmc:.4f}", size=14), expand=1),
                ft.Container(ft.Text(f"{price:.4f}", size=14), expand=1, padding=ft.padding.only(right=30)),
            ], vertical_alignment=ft.CrossAxisAlignment.CENTER)
            rows.append(row)
        self._positions_container.controls = rows
        self._positions_container.visible = not hidden
