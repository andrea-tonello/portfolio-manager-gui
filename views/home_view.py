import logging

import flet as ft
import pandas as pd
from datetime import datetime

from components.background import run_in_background
from components.inputs import account_selector
from components.snack import show_snack
from components.ticker_search import TickerSearchField
from domain.positions import held_tickers, split_ratio_label
from services import config_service, operations_service
from services.market_data import download_close
from services.portfolio_service import compute_snapshot
from utils.constants import DATE_FORMAT
from utils.formatting import HIDDEN_MASK, LOADING, fmt_eur, fmt_pct

logger = logging.getLogger(__name__)

WIDTH_CARD = 600
WIDTH_POSITIONS = 800
WIDTH_WATCHLIST = 800

# Home reuses its last values until the user has switched tabs this many times, then fetches live ones.
REFRESH_AFTER_TAB_SWITCHES = 10

# What the P&L card shows, in the order a tap cycles through them (the user's choice is saved as
# the index): the label's translation key, and how to read (amount, percentage) from a Snapshot.
PNL_MODES = [
    ("home.pnl_unrealized_daily", lambda snap: (snap.daily_pnl, snap.daily_pct)),
    ("home.pnl_unrealized_total", lambda snap: (snap.unrealized_pnl, snap.unrealized_pct)),
    ("home.pnl_total", lambda snap: (snap.total_pnl, snap.total_pct)),
]


def _pnl_color(amount):
    """Green for a gain (or zero), red for a loss."""
    return ft.Colors.GREEN if amount >= 0 else ft.Colors.RED


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
    def __init__(self, app):
        """Build the Home tab for the controller's page and current state."""
        self.app = app
        self.page = app.page
        self.state = app.state
        self._snapshot = None  # the values shown (a Snapshot); None until the first fetch ends
        self._pnl_mode = self.state.home_pnl_mode  # index in PNL_MODES, saved per user
        self._pos_display_mode = 0  # 0 = value, 1 = total %, 2 = daily %
        self._active_section_tab = 0  # 0 = open positions, 1 = watchlist
        self._watchlist_fetched = False

    def build(self) -> ft.Control:
        t = self.state.translator
        if not self.state.brokers:
            return ft.Column([ft.Text(t.get("home.no_account"), size=16)])

        accounts = self._selected_accounts()
        header = [self._build_dropdown()]
        if accounts:  # with no account file loaded there are no cards, so nothing to refresh
            header.append(ft.IconButton(
                icon=ft.Icons.REFRESH,
                tooltip=t.get("components.loading"),
                on_click=self._on_refresh,
            ))

        return ft.Column([
            ft.Container(
                ft.Row(header),
                padding=ft.Padding.only(top=5, left=5, right=5),
            ),
            ft.Container(
                content=self._build_content() if accounts else ft.Text(t.get("home.no_account"), size=14),
                alignment=ft.alignment.Alignment.TOP_CENTER,
            ),
        ], scroll=ft.ScrollMode.AUTO, expand=True,)

    def _build_dropdown(self) -> ft.Control:
        t = self.state.translator
        return account_selector(self.state, self.state.home_selection, self._on_selection_change,
                                all_option=("overview", t.get("home.overview")))

    def _on_selection_change(self, e):
        self.state.home_selection = e.control.value
        self.state.home_cache = None
        self.app.refresh()

    def _on_refresh(self, e):
        self._fetch_live_values()

    def _selected_accounts(self) -> list:
        """The loaded accounts Home shows: all of them for the overview, or just the selected one."""
        sel = self.state.home_selection
        if sel == "overview":
            return list(self.state.accounts.values())
        account = self.state.get_account(int(sel))
        return [account] if account is not None else []

    # ── Section Tab Switcher ─────────────────────────────────────────

    def _build_section_tabs(self) -> ft.Control:
        t = self.state.translator

        self._tab_positions_text = ft.Text(
            t.get("home.open_positions"), size=14,
            weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER,
        )
        self._tab_watchlist_text = ft.Text(
            t.get("home.watchlist"), size=14,
            text_align=ft.TextAlign.CENTER,
        )

        self._tab_positions = ft.Container(
            content=self._tab_positions_text,
            bgcolor=ft.Colors.SECONDARY_CONTAINER,
            border_radius=12,
            padding=ft.Padding.symmetric(horizontal=20, vertical=10),
            on_click=lambda _: self._switch_section_tab(0),
            ink=True,
            expand=True,
            alignment=ft.alignment.Alignment.CENTER,
        )
        self._tab_watchlist = ft.Container(
            content=self._tab_watchlist_text,
            bgcolor=None,
            border_radius=12,
            padding=ft.Padding.symmetric(horizontal=20, vertical=10),
            on_click=lambda _: self._switch_section_tab(1),
            ink=True,
            expand=True,
            alignment=ft.alignment.Alignment.CENTER,
        )

        return ft.Container(
            ft.Row([self._tab_positions, self._tab_watchlist], spacing=8),
            width=WIDTH_POSITIONS,
            padding=ft.Padding.only(top=10, right=5, left=5, bottom=15),
        )

    def _switch_section_tab(self, tab_idx):
        if tab_idx == self._active_section_tab:
            return
        self.state.haptic(self.page)
        self._active_section_tab = tab_idx
        is_pos = (tab_idx == 0)

        # Update tab styling
        self._tab_positions.bgcolor = ft.Colors.SECONDARY_CONTAINER if is_pos else None
        self._tab_positions_text.weight = ft.FontWeight.BOLD if is_pos else None
        self._tab_watchlist.bgcolor = ft.Colors.SECONDARY_CONTAINER if not is_pos else None
        self._tab_watchlist_text.weight = ft.FontWeight.BOLD if not is_pos else None

        # Toggle section visibility
        self._positions_section.visible = is_pos
        self._watchlist_section.visible = not is_pos

        # Lazy-load watchlist prices on first switch
        if not is_pos and self.state.watchlist and not self._watchlist_fetched:
            self._watchlist_fetched = True
            self._fetch_watchlist_prices()

        self.page.update()

    # ── Watchlist ────────────────────────────────────────────────────

    def _build_watchlist_content(self) -> ft.Control:
        t = self.state.translator

        self._watchlist_ticker_search = TickerSearchField(
            self.page,
            label=t.get("home.watchlist_add"),
            expand=True,
            height=40,
            on_submit=self._on_watchlist_add,
        )
        add_row = ft.Row([
            self._watchlist_ticker_search.control,
            ft.IconButton(
                icon=ft.Icons.ADD_CIRCLE_OUTLINE,
                on_click=self._on_watchlist_add,
            ),
        ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.START)

        self._watchlist_items_container = ft.ReorderableListView(
            [], spacing=4, on_reorder=self._on_watchlist_reorder,
            show_default_drag_handles=False,
        )
        self._watchlist_loading = ft.ProgressRing(visible=False, width=14, height=14)

        return ft.Column([
            add_row,
            ft.Row([self._watchlist_loading], alignment=ft.MainAxisAlignment.CENTER),
            self._watchlist_items_container,
        ], spacing=8, width=WIDTH_WATCHLIST,
           horizontal_alignment=ft.CrossAxisAlignment.CENTER)

    def _on_watchlist_add(self, e):
        t = self.state.translator
        ticker = self._watchlist_ticker_search.value.strip().upper()
        if not ticker:
            return
        self.state.haptic(self.page)
        if ticker in self.state.watchlist:
            show_snack(self.page, t.get("home.watchlist_duplicate"), error=True)
            return
        self.state.watchlist.append(ticker)
        config_service.save_watchlist(self.state.user_config_folder, self.state.watchlist)
        self._watchlist_ticker_search.value = ""
        self._fetch_watchlist_prices()
        self.page.update()

    def _on_watchlist_remove(self, ticker):
        if ticker in self.state.watchlist:
            self.state.watchlist.remove(ticker)
            config_service.save_watchlist(self.state.user_config_folder, self.state.watchlist)
            self._fetch_watchlist_prices()
            self.page.update()

    def _on_watchlist_reorder(self, e):
        old_idx, new_idx = e.old_index, e.new_index
        wl = self.state.watchlist
        item = wl.pop(old_idx)
        wl.insert(new_idx, item)
        config_service.save_watchlist(self.state.user_config_folder, wl)
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
                # Show the tickers without prices (e.g. offline), and log why.
                logger.exception("Could not fetch watchlist prices")
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
            padding=ft.Padding.symmetric(vertical=8, horizontal=14),
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
            padding=ft.Padding.only(left=4),
            key=ticker,
        )

    # ── Open Positions ────────────────────────────────────────────────

    def _open_positions_header(self) -> ft.Control:
        t = self.state.translator
        self._pos_mode_labels = [
            t.get("home.pos_value"),
            t.get("home.pos_total_pct"),
            t.get("home.pos_daily_pct"),
        ]
        self._pos_mode_btn = ft.FilledTonalButton(
            self._pos_mode_labels[0],
            on_click=self._cycle_pos_display,
            style=ft.ButtonStyle(padding=ft.Padding.symmetric(horizontal=12, vertical=6)),
            height=35,
            elevation=2,
        )
        header = ft.Container(
            content=ft.Row([
                ft.Column([
                    ft.Text(t.get("home.open_positions_descr"), size=14, color=ft.Colors.GREY_500),
                ], spacing=1),
                self._pos_mode_btn,
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, width=WIDTH_POSITIONS),
            padding=ft.Padding.symmetric(horizontal=16, vertical=8),
            ink=True,
        )
        return header

    def _cycle_pos_display(self, e):
        self.state.haptic(self.page)
        self._pos_display_mode = (self._pos_display_mode + 1) % 3
        self._pos_mode_btn.content = ft.Text(self._pos_mode_labels[self._pos_display_mode])
        self._update_positions()
        self.page.update()

    # ── Content (the overview or a single account) ────────────────────

    def _build_content(self) -> ft.Control:
        """Build the cards, the positions/watchlist switcher and both sections, then fill in the values."""
        cards = self._build_stats_cards()
        tabs = self._build_section_tabs()
        self._positions_container = ft.Column([], spacing=6, width=WIDTH_POSITIONS)
        header = self._open_positions_header()
        watchlist_content = self._build_watchlist_content()

        self._positions_section = ft.Column([header, self._positions_container], spacing=6)
        self._watchlist_section = ft.Container(
            content=watchlist_content,
            visible=False,
            padding=ft.Padding.only(left=16, right=16, bottom=8),
        )

        content = ft.Column([
            cards,
            tabs,
            self._positions_section,
            self._watchlist_section,
        ], spacing=10, horizontal_alignment=ft.CrossAxisAlignment.CENTER)

        self._auto_fetch_or_restore()

        return content

    # ── Live Value Fetch ──────────────────────────────────────────────

    def _auto_fetch_or_restore(self):
        """Use cached data if fresh enough, otherwise fetch live values."""
        s = self.state
        selection, snapshot = s.home_cache or (None, None)
        if (snapshot is not None
                and selection == s.home_selection
                and s.home_nav_count < REFRESH_AFTER_TAB_SWITCHES):
            self._render(snapshot)
        else:
            self._fetch_live_values()

    def _render(self, snapshot):
        """Show `snapshot` on the cards and in the positions list (amounts stay masked while hidden)."""
        self._snapshot = snapshot
        self._apply_subtotals()
        if not self.state.home_values_hidden:
            self._show_nav_and_pnl()
        self._update_positions()

    def _fetch_live_values(self):
        """Fetch live prices in the background, show the new values and keep them for the next visits."""
        self._refresh_loading.visible = True
        self.page.update()

        def worker():
            s = self.state
            try:
                snapshot = compute_snapshot(self._selected_accounts(), pd.Timestamp(datetime.now()))
                self._render(snapshot)
                s.home_cache = (s.home_selection, snapshot)
                s.home_nav_count = 0
            except Exception:
                # Keep showing the last values (e.g. offline), and log why.
                logger.exception("Could not refresh live values on Home")
            finally:
                self._refresh_loading.visible = False
                self.page.update()

            self._check_splits_async()

        self.page.run_thread(worker)

    def _check_splits_async(self):
        """Look for unrecorded splits on held tickers and prompt the user. Runs once per session."""
        s = self.state
        if s.split_checked_session:
            return
        sel = s.home_selection
        if sel == "overview":
            return
        try:
            acc_idx = int(sel)
        except (ValueError, TypeError):
            return
        account = s.get_account(acc_idx)
        if account is None:
            return
        df = account.df
        if df is None or df.empty:
            return

        tickers = list(held_tickers(df))
        if not tickers:
            return

        def worker():
            s.split_checked_session = True
            for ticker in tickers:
                if f"{ticker}|*" in s.split_ignores:
                    continue
                try:
                    unrecorded = operations_service.detect_unrecorded_splits(df, ticker)
                except Exception:
                    # Skip this ticker (no prompt), and log why.
                    logger.exception("Could not check %s for splits", ticker)
                    continue
                for ev_date, ratio in unrecorded:
                    if f"{ticker}|{ev_date}" in s.split_ignores:
                        continue
                    # Marshal dialog back to the event loop — show_dialog
                    # mutates page.overlay and must not run on a worker thread
                    # while the main thread may be computing an update patch.
                    async def _show(t=ticker, d=ev_date, r=ratio):
                        self._prompt_split(acc_idx, t, d, r)
                    self.page.run_task(_show)
                    return

        self.page.run_thread(worker)

    def _prompt_split(self, acc_idx, ticker, ev_date, ratio):
        s = self.state
        t = s.translator
        msg = t.get("operations.split.detected_msg",
                    ticker=ticker, ratio=split_ratio_label(ratio), date=ev_date)

        def on_record(e):
            self.page.pop_dialog()
            s.split_checked_session = False
            self._record_detected_split(acc_idx, ticker, ev_date, ratio)

        dlg = ft.AlertDialog(
            title=ft.Text(t.get("operations.split.detected_title")),
            content=ft.Container(content=ft.Text(msg), width=450),
            actions=[
                ft.TextButton(t.get("operations.split.detected_ignore_always"),
                              on_click=lambda _: self._ignore_split(f"{ticker}|*")),
                ft.TextButton(t.get("operations.split.detected_ignore_once"),
                              on_click=lambda _: self._ignore_split(f"{ticker}|{ev_date}")),
                ft.FilledButton(t.get("operations.split.detected_record"), on_click=on_record),
            ],
        )
        self.page.show_dialog(dlg)

    def _ignore_split(self, key):
        """Close the split prompt, remember not to ask again, and look for the next unrecorded split.

        `key` is "TICKER|YYYY-MM-DD" to skip that one split, or "TICKER|*" to skip every split of the ticker.
        """
        s = self.state
        self.page.pop_dialog()
        s.split_ignores.add(key)
        if s.user_config_folder:
            config_service.save_split_ignores(s.user_config_folder, s.split_ignores)
        s.split_checked_session = False
        self._check_splits_async()

    def _record_detected_split(self, acc_idx, ticker, ev_date, ratio):
        s = self.state
        t = s.translator
        account = s.get_account(acc_idx)
        if account is None:
            return
        ref_date = datetime.strptime(ev_date, "%Y-%m-%d").date()
        date_str = ref_date.strftime(DATE_FORMAT)

        def save():
            """Record the split, save the account and refresh Home's values."""
            new_df = operations_service.execute_split(
                account.df, account.name, date_str, ref_date, ticker, ratio,
            )
            s.commit(acc_idx, new_df)
            show_snack(self.page, t.get("operations.added_transaction"))
            self._fetch_live_values()

        run_in_background(self.page, t, save)

    # ── Shared Components ─────────────────────────────────────────────

    def _compute_nav_size(self, text: str) -> int:
        """Pick the largest font size (up to 48) that keeps `text` on one line
        given the current effective card width."""
        length = len(text or "")
        if length == 0:
            return 48
        page_w = self.page.width or WIDTH_CARD
        # Card is capped at WIDTH_CARD, but narrower on phones. Subtract padding + shadow.
        effective = min(page_w, WIDTH_CARD) - 80
        # Bold sans-serif digit/punct glyph width ≈ 0.64 × font size (conservative).
        max_size = int(effective / (length * 0.64))
        return max(min(max_size, 48), 14)

    def _set_nav_value(self, value: str):
        self._nav_text.value = value
        self._nav_text.size = self._compute_nav_size(value)

    def _apply_subtotals(self):
        """Write assets/cash subtitle texts from current state, honoring hidden mode."""
        t = self.state.translator
        snap = self._snapshot
        if self.state.home_values_hidden:
            assets_val = cash_val = HIDDEN_MASK
        elif snap is None:
            assets_val = cash_val = LOADING
        else:
            assets_val, cash_val = fmt_eur(snap.assets), fmt_eur(snap.cash)
        self._assets_text.value = "  " + t.get("home.subt_assets") + f"   {assets_val}"
        self._cash_text.value = "  " + t.get("home.subt_cash") + f"   {cash_val}"
        
        negative = snap is not None and not self.state.home_values_hidden and snap.cash < 0
        self._cash_text.color = ft.Colors.RED if negative else None

    def _build_stats_cards(self) -> ft.Control:
        t = self.state.translator
        hidden = self.state.home_values_hidden

        initial_nav = HIDDEN_MASK if hidden else LOADING
        self._nav_text = ft.Text(
            initial_nav, size=self._compute_nav_size(initial_nav),
            weight=ft.FontWeight.BOLD,
            visible=not hidden,
            max_lines=1,
            no_wrap=True,
            overflow=ft.TextOverflow.CLIP,
        )
        self._hidden_placeholder = ft.Container(
            content=ft.Text(
                t.get("home.hidden"), size=18,
                color=ft.Colors.ON_SECONDARY_CONTAINER, text_align=ft.TextAlign.CENTER,
            ),
            bgcolor=ft.Colors.with_opacity(0.15, ft.Colors.SECONDARY),
            border_radius=10,
            padding=ft.Padding.all(16.5),
            margin=ft.Margin.only(left=4.5),
            alignment=ft.alignment.Alignment.CENTER,
            visible=hidden,
            col={"xs": 10, "md": 10}
        )
        self._assets_text = ft.Text(size=14)
        self._cash_text = ft.Text(size=14)
        self._apply_subtotals()

        self._pnl_label = ft.Text("P&L", size=14)
        self._pnl_type = ft.Text(t.get(PNL_MODES[self._pnl_mode][0]), size=14,
                                 weight=ft.FontWeight.BOLD, color=ft.Colors.ON_SECONDARY_CONTAINER)
        self._pnl_value = ft.Text(
            HIDDEN_MASK if hidden else LOADING,
            size=14, weight=ft.FontWeight.BOLD,
        )
        self._pnl_pct = ft.Text("" if hidden else LOADING, size=12)
        self._pnl_container = ft.Card(
            content=ft.Container(
                content=ft.Row([
                    ft.Column([
                        self._pnl_label,
                        self._pnl_type
                    ], horizontal_alignment=ft.CrossAxisAlignment.START, spacing=5),
                    ft.Column([
                        self._pnl_value,
                        self._pnl_pct,
                    ], horizontal_alignment=ft.CrossAxisAlignment.END, spacing=1),
                ], spacing=1, alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                padding=ft.Padding.symmetric(horizontal=15, vertical=10),
                border_radius=10,
                bgcolor=ft.Colors.with_opacity(0.10, ft.Colors.SECONDARY),
                on_click=self._cycle_pnl_mode,
                ink=True,
            ),
            elevation=3, col={"xs": 12, "md": 7}
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
                        ft.ResponsiveRow([
                            ft.Container(self._nav_text, col={"xs": 10, "md": 10}),
                            self._hidden_placeholder,
                            ft.Container(self._visibility_btn, col={"xs": 2, "md": 2}),                        ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        ft.ResponsiveRow([
                            ft.Column([
                                self._assets_text,
                                self._cash_text,
                            ], spacing=2, col={"xs": 12, "md": 5}, expand=True),
                            self._pnl_container,
                        ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    ], spacing=10),
                    padding=ft.Padding.only(top=15, bottom=17, left=20, right=20),
                ),
                elevation=5,
            ),
            ft.Row([self._refresh_loading], alignment=ft.MainAxisAlignment.CENTER),
        ], spacing=5, width=WIDTH_CARD,)

    def _toggle_visibility(self, e):
        self.state.haptic(self.page)
        hidden = not self.state.home_values_hidden
        self.state.home_values_hidden = hidden
        config_service.save_home_hidden(self.state.user_config_folder, hidden)

        self._nav_text.visible = not hidden
        self._hidden_placeholder.visible = hidden
        self._visibility_btn.icon = ft.Icons.VISIBILITY_OFF if hidden else ft.Icons.VISIBILITY
        self._apply_subtotals()

        if hidden:
            self._pnl_value.value = HIDDEN_MASK
            self._pnl_value.color = None
            self._pnl_pct.value = ""
            self._positions_container.visible = False
        else:
            self._show_nav_and_pnl()
            self._positions_container.visible = True
        self.page.update()

    def _show_nav_and_pnl(self):
        """Write the NAV and the P&L card from the values shown ("---" while they are still loading)."""
        self._set_nav_value(fmt_eur(self._snapshot.nav) if self._snapshot else LOADING)
        self._update_pnl_display()

    def _update_pnl_display(self):
        """Show the P&L of the current mode on its card: label, amount and percentage."""
        t = self.state.translator
        label_key, read = PNL_MODES[self._pnl_mode]
        self._pnl_type.value = t.get(label_key)
        if self._snapshot is None:
            amount_str = pct_str = LOADING
            color = None
        else:
            amount, pct = read(self._snapshot)
            amount_str, pct_str, color = fmt_eur(amount, signed=True), fmt_pct(pct), _pnl_color(amount)
        self._pnl_value.value = amount_str
        self._pnl_value.color = color
        self._pnl_pct.value = pct_str
        self._pnl_pct.color = color

    def _cycle_pnl_mode(self, e):
        self.state.haptic(self.page)
        self._pnl_mode = (self._pnl_mode + 1) % len(PNL_MODES)
        self.state.home_pnl_mode = self._pnl_mode
        config_service.save_home_pnl_mode(self.state.user_config_folder, self._pnl_mode)
        hidden = self.state.home_values_hidden
        if not hidden:
            self._update_pnl_display()
        self.page.update()

    def _update_positions(self):
        """Build one row per position shown, in the chosen display mode (value, total % or daily %)."""
        positions = self._snapshot.positions if self._snapshot else []
        if not positions:
            self._positions_container.controls = []
            return
        mode = self._pos_display_mode
        rows = []
        for pos in positions:
            qty = pos.quantity
            qty_str = f"{int(qty)}" if qty == int(qty) else f"{qty:.2f}"
            chip = ft.Container(
                content=ft.Column([
                    ft.Text(pos.ticker, weight=ft.FontWeight.BOLD, size=13),
                    ft.Text("\u00d7"+qty_str, size=11, color=ft.Colors.GREY_500),
                ], spacing=1, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                bgcolor=ft.Colors.with_opacity(0.12, ft.Colors.GREY),
                border_radius=10,
                padding=ft.Padding.symmetric(vertical=6, horizontal=12),
            )
            if mode == 0:
                extra_ctrl = ft.Text(fmt_eur(pos.value), size=14, weight=ft.FontWeight.BOLD)
            elif mode == 1:
                clr = _pnl_color(pos.unrealized_pnl)
                extra_ctrl = ft.Column([
                    ft.Text(fmt_pct(pos.unrealized_pct), size=14, weight=ft.FontWeight.BOLD, color=clr),
                    ft.Text(fmt_eur(pos.unrealized_pnl, signed=True), size=11, color=clr),
                ], spacing=1, horizontal_alignment=ft.CrossAxisAlignment.START)
            else:
                extra_ctrl = ft.Text(fmt_pct(pos.daily_pct), size=14, weight=ft.FontWeight.BOLD,
                                     color=_pnl_color(pos.daily_pnl))
            chip_with_tooltip = _longpress_tooltip(chip, pos.name)
            row = ft.ResponsiveRow([
                ft.Container(chip_with_tooltip, width=100, col={"xs": 4, "md": 4},
                             padding=ft.Padding.only(left=10, right=10)),
                ft.ResponsiveRow([
                    ft.Container(ft.Text(f"{pos.pmc:.3f}", size=14), col={"xs": 3, "md": 3}, alignment=ft.alignment.Alignment.CENTER_RIGHT),
                    ft.Container(ft.Text(f"{pos.price:.3f}", size=14), col={"xs": 4, "md": 4}, alignment=ft.alignment.Alignment.CENTER_RIGHT),
                    ft.Container(extra_ctrl, padding=ft.Padding.only(right=10), col={"xs": 5, "md": 5}, alignment=ft.alignment.Alignment.CENTER_RIGHT),
                ], col={"xs": 8, "md": 8})
            ], vertical_alignment=ft.CrossAxisAlignment.CENTER)
            rows.append(row)
        self._positions_container.controls = rows
        self._positions_container.visible = not self.state.home_values_hidden
