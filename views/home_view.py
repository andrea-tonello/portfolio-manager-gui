import flet as ft
import pandas as pd
from datetime import datetime

from components.snack import show_snack
from components.ticker_search import TickerSearchField
from services import config_service
from services.market_data import download_close
from utils.other_utils import round_half_up
from utils.account import get_asset_value

WIDTH_CARD = 600
WIDTH_POSITIONS = 800
WIDTH_WATCHLIST = 800


def _longpress_tooltip(control: ft.Control, name: str) -> ft.Control:
    """Add a long-press tooltip showing the product's full name to a control."""
    control.tooltip = ft.Tooltip(
        message=name,
        trigger_mode=ft.TooltipTriggerMode.LONG_PRESS,
        enable_feedback=True,
        prefer_below=False,
    )
    return control


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
        ], scroll=ft.ScrollMode.AUTO, expand=True,)

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
            menu_style=ft.MenuStyle(
                shape=ft.RoundedRectangleBorder(radius=15),
            ),
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
        self.state._home_cache = None
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
            padding=ft.padding.only(left=16, right=16, top=10, bottom=14),
            border_radius=15,
            width=WIDTH_WATCHLIST,
            ink=True,
        )

        self._watchlist_ticker_search = TickerSearchField(
            self.page,
            label=t.get("home.watchlist_add"),
            expand=True,
            border_radius=ft.border_radius.all(15),
            height=40,
            border_color=ft.Colors.with_opacity(0.40, ft.Colors.GREY),
        )
        self._watchlist_ticker_search.on_submit = self._on_watchlist_add
        add_row = ft.Row([
            self._watchlist_ticker_search.control,
            ft.IconButton(
                icon=ft.Icons.ADD_CIRCLE_OUTLINE,
                on_click=self._on_watchlist_add,
            ),
        ], spacing=8)

        self._watchlist_items_container = ft.ReorderableListView(
            [], spacing=4, on_reorder=self._on_watchlist_reorder,
            show_default_drag_handles=False, expand=True,
        )
        self._watchlist_loading = ft.ProgressRing(visible=False, width=14, height=14)

        self._watchlist_body = ft.Column([
            add_row,
            ft.Row([self._watchlist_loading], alignment=ft.MainAxisAlignment.CENTER),
            self._watchlist_items_container,
        ], spacing=8, visible=expanded, width=WIDTH_WATCHLIST, horizontal_alignment=ft.CrossAxisAlignment.CENTER)

        if expanded and self.state.watchlist:
            self._fetch_watchlist_prices()

        return ft.Column([
            ft.Container(padding=ft.padding.only(top=15)),
            ft.Container(ft.Divider(), width=950, padding=ft.padding.only(bottom=10)),
            header,
            ft.Container(self._watchlist_body, padding=ft.padding.only(left=16, right=16, bottom=8)),
        ], spacing=0, horizontal_alignment=ft.CrossAxisAlignment.CENTER)

    def _toggle_watchlist(self, e):
        self.state.haptic(self.page)
        expanded = not getattr(self.state, '_watchlist_expanded', False)
        self.state._watchlist_expanded = expanded
        self._watchlist_body.visible = expanded
        self._watchlist_toggle_icon.icon = (
            ft.Icons.KEYBOARD_ARROW_DOWN if expanded else ft.Icons.KEYBOARD_ARROW_RIGHT
        )
        if expanded and self.state.watchlist:
            self._fetch_watchlist_prices()
        self.page.update()

    def _on_watchlist_add(self, e):
        t = self.state.translator
        ticker = self._watchlist_ticker_search.value.strip().upper()
        if not ticker:
            return
        if ticker in self.state.watchlist:
            show_snack(self.page, t.get("home.watchlist_duplicate"), error=True)
            return
        self.state.watchlist.append(ticker)
        config_service.save_watchlist(self.state.config_folder, self.state.watchlist)
        self._watchlist_ticker_search.value = ""
        self._fetch_watchlist_prices()
        self.page.update()

    def _on_watchlist_remove(self, ticker):
        t = self.state.translator
        if ticker in self.state.watchlist:
            self.state.watchlist.remove(ticker)
            config_service.save_watchlist(self.state.config_folder, self.state.watchlist)
            self._fetch_watchlist_prices()
            self.page.update()

    def _on_watchlist_reorder(self, e):
        old_idx, new_idx = e.old_index, e.new_index
        wl = self.state.watchlist
        item = wl.pop(old_idx)
        wl.insert(new_idx, item)
        config_service.save_watchlist(self.state.config_folder, wl)
        # Sync the controls list to match
        ctrls = self._watchlist_items_container.controls
        ctrl = ctrls.pop(old_idx)
        ctrls.insert(new_idx, ctrl)

    def _fetch_watchlist_prices(self):
        tickers = self.state.watchlist[:]
        if not tickers:
            self._watchlist_items_container.controls = []
            return
        self._watchlist_loading.visible = True
        self.page.update()

        def worker():
            try:
                data, names = download_close(tickers, period="2d")
                if isinstance(data, pd.Series):
                    data = data.to_frame(name=tickers[0])
                data = data.dropna(how="all")

                rows = []
                for tk in tickers:
                    name = names.get(tk, tk)
                    if tk not in data.columns or data[tk].dropna().empty:
                        rows.append(self._build_watchlist_item(tk, None, None, name))
                        continue
                    series = data[tk].dropna()
                    price = float(series.iloc[-1])
                    prev_close = float(series.iloc[-2]) if len(series) >= 2 else None
                    rows.append(self._build_watchlist_item(tk, price, prev_close, name))

                self._watchlist_items_container.controls = rows
            except Exception:
                self._watchlist_items_container.controls = [
                    self._build_watchlist_item(tk, None, None) for tk in tickers
                ]
            finally:
                self._watchlist_loading.visible = False
                self.page.update()

        self.page.run_thread(worker)

    def _build_watchlist_item(self, ticker: str, price, prev_close,
                              name: str = "") -> ft.Control:
        chip = ft.Container(
            content=ft.Text(ticker, weight=ft.FontWeight.BOLD, size=13),
            bgcolor=ft.Colors.with_opacity(0.12, ft.Colors.GREY),
            border_radius=10,
            padding=ft.padding.symmetric(vertical=8, horizontal=14),
        )
        chip_with_tooltip = _longpress_tooltip(chip, name or ticker)

        # Full name on tablets, empty spacer on phones
        wide = bool(name and self.page.width and self.page.width >= 600)
        name_text = ft.Text(
            name if wide else "", size=12, max_lines=1,
            overflow=ft.TextOverflow.ELLIPSIS,
            color=ft.Colors.with_opacity(0.6, ft.Colors.ON_SURFACE),
            expand=True,
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

        drag_handle = ft.ReorderableDragHandle(
            content=ft.Icon(ft.Icons.DRAG_INDICATOR, size=20,
                            color=ft.Colors.with_opacity(0.4, ft.Colors.ON_SURFACE)),
        )

        return ft.Container(
            content=ft.Row([
                drag_handle,
                chip_with_tooltip,
                name_text,
                ft.Column([price_text, indicator], spacing=0, horizontal_alignment=ft.CrossAxisAlignment.END),
                delete_btn,
            ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.padding.only(left=4),
            key=ticker,
        )

    # ── Overview ──────────────────────────────────────────────────────

    # (also shared with single accounts)
    def _open_positions_header(self) -> ft.Control:
        t = self.state.translator
        self._pos_display_mode = 0
        self._positions_data = []
        self._pos_mode_labels = [
            t.get("home.pos_value"),
            t.get("home.pos_total_pct"),
            t.get("home.pos_daily_pct"),
        ]
        self._pos_mode_btn = ft.FilledTonalButton(
            self._pos_mode_labels[0],
            on_click=self._cycle_pos_display,
            style=ft.ButtonStyle(padding=ft.padding.symmetric(horizontal=12, vertical=6)),
            height=35,
        )
        header = ft.Container(
            content=ft.Row([
                ft.Column([
                    ft.Text(t.get("home.open_positions"), size=16, weight=ft.FontWeight.BOLD),
                    ft.Text(t.get("home.open_positions_descr"), size=11, color=ft.Colors.GREY_500),
                ], spacing=1),
                self._pos_mode_btn,
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, width=WIDTH_POSITIONS),
            padding=ft.padding.symmetric(horizontal=16, vertical=8),
            ink=True,
        )
        return header

    def _cycle_pos_display(self, e):
        self.state.haptic(self.page)
        self._pos_display_mode = (self._pos_display_mode + 1) % 3
        self._pos_mode_btn.content = ft.Text(self._pos_mode_labels[self._pos_display_mode])
        hidden = getattr(self.state, '_home_values_hidden', False)
        self._update_positions(self._positions_data, hidden)
        self.page.update()


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
                total_nav += float(last_row.get("nav", 0) or 0)
                total_cash += float(last_row.get("cash_held", 0) or 0)
                total_assets += float(last_row.get("assets_value", 0) or 0)

        cards = self._build_stats_cards(total_nav, total_cash, total_assets)
        self._positions_container = ft.Column([], spacing=6, width=WIDTH_POSITIONS)
        watchlist = self._build_watchlist()
        header = self._open_positions_header()

        content = ft.Column([
            cards,
            header,
            self._positions_container,
            watchlist,
        ], spacing=10, horizontal_alignment=ft.CrossAxisAlignment.CENTER)

        self._auto_fetch_or_restore()

        return content

    # ── Single Account ────────────────────────────────────────────────

    def _build_single_account(self, idx: int) -> ft.Control:
        t = self.state.translator
        acc = self.state.get_account(idx)
        if acc is None:
            return ft.Text(t.get("home.no_account"), size=14)

        df = acc["df"]

        # Start with stale values
        nav = float(df.iloc[-1].get("nav", 0) or 0) if not df.empty else 0
        cash = float(df.iloc[-1].get("cash_held", 0) or 0) if not df.empty else 0
        assets = float(df.iloc[-1].get("assets_value", 0) or 0) if not df.empty else 0

        cards = self._build_stats_cards(nav, cash, assets)
        self._positions_container = ft.Column([], spacing=6)
        watchlist = self._build_watchlist()
        header = self._open_positions_header()

        content = ft.Column([
            cards,
            header,
            self._positions_container,
            watchlist,
        ], spacing=10, horizontal_alignment=ft.CrossAxisAlignment.CENTER)

        self._auto_fetch_or_restore()

        return content

    # ── Live Value Fetch ──────────────────────────────────────────────

    def _auto_fetch_or_restore(self):
        """Use cached data if fresh enough, otherwise fetch live values."""
        s = self.state
        cache = s._home_cache
        if (cache is not None
                and cache.get("selection") == s.home_selection
                and s._home_nav_count < s._home_nav_threshold):
            self._restore_from_cache(cache)
        else:
            self._fetch_live_values()

    def _restore_from_cache(self, cache):
        t = self.state.translator
        """Populate widgets from cached data without network fetch."""
        self._current_nav_str = cache["nav_str"]
        self._current_assets_str = cache["assets_str"]
        self._current_cash_str = cache["cash_str"]
        self._current_upnl_str = cache["upnl_str"]
        self._current_upnl_color = cache["upnl_color"]
        self._current_tpnl_str = cache["tpnl_str"]
        self._current_tpnl_color = cache["tpnl_color"]

        hidden = self.state._home_values_hidden
        if not hidden:
            self._nav_text.value = self._current_nav_str
            self._assets_text.value = t.get("home.subt_assets") + f"   {self._current_assets_str}"
            self._cash_text.value = t.get("home.subt_cash") + f"   {self._current_cash_str}"
            self._update_pnl_display()

        self._update_positions(cache["positions"], hidden)

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
                    total_committed = 0.0
                    aggr = {}  # ticker -> {quantity, total_cost, price}
                    for idx, acc in s.accounts.items():
                        df = acc["df"]
                        if df is None or df.empty:
                            continue
                        total_cash += float(df.iloc[-1].get("cash_held", 0) or 0)
                        total_committed += float(df.iloc[-1].get("committed_cash", 0) or 0)
                        positions = get_asset_value(t, df, ref_date=ref_date)
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
                                        "prev_close": p.get("prev_close", p["price"]),
                                        "name": p.get("name", tk),
                                    }
                    for tk, d in aggr.items():
                        all_positions.append({
                            "ticker": tk,
                            "quantity": d["quantity"],
                            "pmc": d["total_cost"] / d["quantity"] if d["quantity"] else 0,
                            "price": d["price"],
                            "prev_close": d["prev_close"],
                            "name": d["name"],
                        })
                    total_nav = total_cash + total_assets
                    nav_num = total_nav
                    self._current_nav_str = f"{total_nav:,.2f}\u20ac"
                    self._current_assets_str = f"{total_assets:,.2f}\u20ac"
                    self._current_cash_str = f"{total_cash:,.2f}\u20ac"
                else:
                    idx = int(sel)
                    acc = s.get_account(idx)
                    if acc is None:
                        return
                    df = acc["df"]
                    cash = float(df.iloc[-1].get("cash_held", 0) or 0) if not df.empty else 0
                    total_committed = float(df.iloc[-1].get("committed_cash", 0) or 0) if not df.empty else 0
                    positions = get_asset_value(t, df, ref_date=ref_date)
                    assets = round_half_up(sum(p["value"] for p in positions)) if positions else 0.0
                    nav = cash + assets
                    nav_num = nav
                    self._current_nav_str = f"{nav:,.2f}\u20ac"
                    self._current_assets_str = f"{assets:,.2f}\u20ac"
                    self._current_cash_str = f"{cash:,.2f}\u20ac"
                    all_positions = [
                        {"ticker": p["ticker"], "quantity": p["quantity"],
                         "pmc": p["pmc"], "price": p["price"],
                         "prev_close": p.get("prev_close", p["price"]),
                         "name": p.get("name", p["ticker"])}
                        for p in (positions or [])
                    ]

                # Compute unrealized P&L
                unrealized_pnl = sum(
                    p["quantity"] * (p["price"] - p["pmc"])
                    for p in all_positions
                )
                self._current_upnl_str = f"{unrealized_pnl:+,.2f}\u20ac"
                self._current_upnl_color = ft.Colors.GREEN if unrealized_pnl >= 0 else ft.Colors.RED

                # Compute total P&L (NAV - Committed Cash)
                total_pnl = nav_num - total_committed
                self._current_tpnl_str = f"{total_pnl:+,.2f}\u20ac"
                self._current_tpnl_color = ft.Colors.GREEN if total_pnl >= 0 else ft.Colors.RED

                hidden = getattr(s, '_home_values_hidden', False)
                if not hidden:
                    self._nav_text.value = self._current_nav_str
                    self._assets_text.value = t.get("home.subt_assets") + f"   {self._current_assets_str}"
                    self._cash_text.value = t.get("home.subt_cash") + f"   {self._current_cash_str}"
                    self._update_pnl_display()

                self._update_positions(all_positions, hidden)

                # Save to cache
                s._home_cache = {
                    "selection": s.home_selection,
                    "nav_str": self._current_nav_str,
                    "assets_str": self._current_assets_str,
                    "cash_str": self._current_cash_str,
                    "upnl_str": self._current_upnl_str,
                    "upnl_color": self._current_upnl_color,
                    "tpnl_str": self._current_tpnl_str,
                    "tpnl_color": self._current_tpnl_color,
                    "positions": all_positions,
                }
                s._home_nav_count = 0
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
        self._current_upnl_str = loading_str
        self._current_upnl_color = None
        self._current_tpnl_str = loading_str
        self._current_tpnl_color = None
        self._pnl_mode = 0  # 0 = unrealized, 1 = total

        self._nav_text = ft.Text(
            hidden_mask if hidden else loading_str, size=48,
            weight=ft.FontWeight.BOLD,
            visible=not hidden,
        )
        self._hidden_placeholder = ft.Container(
            content=ft.Text(
                t.get("home.hidden"), size=18,
                color=ft.Colors.ON_SECONDARY_CONTAINER, text_align=ft.TextAlign.CENTER,
            ),
            bgcolor=ft.Colors.with_opacity(0.15, ft.Colors.SECONDARY),
            border_radius=10,
            height=69,
            padding=ft.padding.all(10),
            alignment=ft.alignment.Alignment.CENTER,
            visible=hidden,
        )
        self._assets_text = ft.Text(
            t.get("home.subt_assets") + f"   {hidden_mask if hidden else loading_str}",
            size=14,
        )
        self._cash_text = ft.Text(
            t.get("home.subt_cash") + f"   {hidden_mask if hidden else loading_str}",
            size=14,
        )
        self._pnl_label = ft.Text(
            t.get("home.pnl_unrealized"), size=11, color=ft.Colors.ON_SECONDARY_CONTAINER,
        )
        self._pnl_value = ft.Text(
            hidden_mask if hidden else loading_str,
            size=14, weight=ft.FontWeight.BOLD,
        )
        self._pnl_container = ft.Container(
            content=ft.Column([
                self._pnl_label,
                self._pnl_value,
            ], spacing=1, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.padding.symmetric(horizontal=12, vertical=8),
            border_radius=10,
            bgcolor=ft.Colors.with_opacity(0.10, ft.Colors.SECONDARY),
            shadow=ft.BoxShadow(
                spread_radius=0, blur_radius=1, offset=ft.Offset(3, 3),
                color=ft.Colors.with_opacity(0.1, ft.Colors.BLACK),
            ),
            on_click=self._cycle_pnl_mode,
            ink=True,
        )
        self._visibility_btn = ft.IconButton(
            icon=ft.Icons.VISIBILITY_OFF if hidden else ft.Icons.VISIBILITY,
            icon_size=28, on_click=self._toggle_visibility,
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
                            ft.Container(self._visibility_btn, expand=1),
                            ft.Container(ft.Column([
                                self._assets_text,
                                self._cash_text,
                            ], spacing=2), expand=3),
                            ft.Container(self._pnl_container, expand=3),
                        ], spacing=12, alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    ], spacing=15),
                    padding=20,
                ),
            ),
            ft.Row([self._refresh_loading], alignment=ft.MainAxisAlignment.CENTER),
        ], spacing=4, width=WIDTH_CARD,)

    def _toggle_visibility(self, e):
        t = self.state.translator
        self.state.haptic(self.page)
        hidden = not self.state._home_values_hidden
        self.state._home_values_hidden = hidden
        config_service.save_home_hidden(self.state.config_folder, hidden)
        hidden_mask = "\u2022\u2022\u2022\u2022\u2022\u2022"

        self._nav_text.visible = not hidden
        self._hidden_placeholder.visible = hidden
        self._visibility_btn.icon = ft.Icons.VISIBILITY_OFF if hidden else ft.Icons.VISIBILITY

        if hidden:
            self._assets_text.value = t.get("home.subt_assets") + f"   {hidden_mask}",
            self._cash_text.value = t.get("home.subt_cash") + f"   {hidden_mask}",
            self._pnl_value.value = hidden_mask
            self._pnl_value.color = None
            self._positions_container.visible = False
        else:
            self._nav_text.value = self._current_nav_str
            self._assets_text.value = t.get("home.subt_assets") + f"   {self._current_assets_str}"
            self._cash_text.value = t.get("home.subt_cash") + f"   {self._current_cash_str}"
            self._update_pnl_display()
            self._positions_container.visible = True
        self.page.update()

    def _update_pnl_display(self):
        """Update P&L label and value based on current mode."""
        t = self.state.translator
        if self._pnl_mode == 0:
            self._pnl_label.value = t.get("home.pnl_unrealized")
            self._pnl_value.value = self._current_upnl_str
            self._pnl_value.color = self._current_upnl_color
        else:
            self._pnl_label.value = t.get("home.pnl_total")
            self._pnl_value.value = self._current_tpnl_str
            self._pnl_value.color = self._current_tpnl_color

    def _cycle_pnl_mode(self, e):
        self.state.haptic(self.page)
        self._pnl_mode = (self._pnl_mode + 1) % 2
        hidden = getattr(self.state, '_home_values_hidden', False)
        if not hidden:
            self._update_pnl_display()
        self.page.update()

    def _update_positions(self, positions, hidden=False):
        """Build position rows from fetched data."""
        self._positions_data = positions
        if not positions:
            self._positions_container.controls = []
            return
        mode = getattr(self, '_pos_display_mode', 0)
        rows = []
        for pos in positions:
            ticker = pos["ticker"]
            name = pos.get("name", ticker)
            qty = pos["quantity"]
            pmc = pos["pmc"]
            price = pos["price"]
            prev_close = pos.get("prev_close", price)
            qty_str = f"{int(qty)}" if qty == int(qty) else f"{qty:.2f}"
            chip = ft.Container(
                content=ft.Column([
                    ft.Text(ticker, weight=ft.FontWeight.BOLD, size=13),
                    ft.Text("\u00d7"+qty_str, size=11, color=ft.Colors.GREY_500),
                ], spacing=1, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                bgcolor=ft.Colors.with_opacity(0.12, ft.Colors.GREY),
                border_radius=10,
                padding=ft.padding.symmetric(vertical=6, horizontal=12),
            )
            if mode == 0:
                value = qty * price
                extra_ctrl = ft.Text(f"{value:,.2f}\u20ac", size=14, weight=ft.FontWeight.BOLD)
            elif mode == 1:
                pct = (price - pmc) / pmc * 100 if pmc else 0
                val_change = qty * (price - pmc)
                clr = ft.Colors.GREEN if pct >= 0 else ft.Colors.RED
                extra_ctrl = ft.Column([
                    ft.Text(f"{pct:+.2f}%", size=14, weight=ft.FontWeight.BOLD, color=clr),
                    ft.Text(f"{val_change:+,.2f}\u20ac", size=11, color=clr),
                ], spacing=1, horizontal_alignment=ft.CrossAxisAlignment.START)
            else:
                pct = (price - prev_close) / prev_close * 100 if prev_close else 0
                clr = ft.Colors.GREEN if pct >= 0 else ft.Colors.RED
                extra_ctrl = ft.Text(f"{pct:+.2f}%", size=14, weight=ft.FontWeight.BOLD, color=clr)
            chip_with_tooltip = _longpress_tooltip(chip, name)
            row = ft.Row([
                ft.Container(chip_with_tooltip, expand=4, padding=ft.padding.only(left=10, right=10)),
                ft.Container(ft.Text(f"{pmc:.3f}", size=14), expand=2),
                ft.Container(ft.Text(f"{price:.3f}", size=14), expand=2),
                ft.Container(extra_ctrl, expand=3, padding=ft.padding.only(left=22, right=10)),
            ], vertical_alignment=ft.CrossAxisAlignment.CENTER)
            rows.append(row)
        self._positions_container.controls = rows
        self._positions_container.visible = not hidden
