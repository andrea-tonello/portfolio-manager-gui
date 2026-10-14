import threading
import time

import flet as ft

from components.inputs import BORDER_GREY, RADIUS
from services.market_data import search_tickers


class TickerSearchField:
    """A ticker field with live Yahoo Finance suggestions, shown over the screen rather than in the form.

    Built on Flet's SearchBar, styled like the other fields. The suggestions
    appear in a search panel; picking one, or pressing Done, closes it and
    fills in the field.
    - On a phone or tablet the panel covers the whole screen and opens on a
      tap, with the suggestions at the top, above the on-screen keyboard. A
      panel next to the field would sit partly under the keyboard: Flutter
      places it ignoring the keyboard, and pads its list by the keyboard's
      height, so it would always be as tall as allowed.
    - On a computer the panel floats under the field, as tall as its
      suggestions, without moving the form. It opens on the first key typed
      rather than on a tap: the form first scrolls the focused field into view
      (scroll_into_view_on_focus), and a panel opened at once would stay where
      the field was before the scroll.

    Like DateField: put `control` on the screen, give `field` to the focus and
    scroll helpers, and read or set the ticker through `value`. `on_select`
    is called with the ticker picked, `on_submit` when Done is pressed.
    `type_filter` ("etf", "equity" or None) limits the suggestions to one kind.
    """

    def __init__(self, page: ft.Page, *, label: str = "Ticker", on_select=None, on_submit=None,
                 type_filter=None, expand=False, col=None, height=None):
        self._page = page
        self._on_select = on_select
        self._on_submit_callback = on_submit
        self._type_filter = type_filter
        self._req_id = 0
        self._lock = threading.Lock()
        full_screen = page.platform in (ft.PagePlatform.ANDROID, ft.PagePlatform.IOS)

        self.field = ft.SearchBar(
            bar_hint_text=label,
            capitalization=ft.TextCapitalization.CHARACTERS,
            # Styled like rounded_text_field: a thin grey outline, no fill or shadow.
            bar_shape=ft.RoundedRectangleBorder(radius=RADIUS),
            bar_border_side=ft.BorderSide(1, BORDER_GREY),
            bar_bgcolor=ft.Colors.TRANSPARENT,
            bar_overlay_color=ft.Colors.TRANSPARENT,
            bar_elevation=0,
            bar_size_constraints=height and ft.BoxConstraints(min_height=height, max_height=height),
            # The panel (see above). Shape, size and shrinking apply to the floating one only.
            full_screen=full_screen,
            shrink_wrap=True,
            view_shape=ft.RoundedRectangleBorder(radius=RADIUS),
            view_size_constraints=ft.BoxConstraints(max_height=320),
            on_tap=(lambda _: self._page.run_task(self.field.open_view)) if full_screen else None,
            on_change=self._on_change,
            on_submit=self._on_submit,
            controls=[],
        )
        self.control = ft.Container(self.field, expand=expand, col=col)

    # ── public interface ────────────────────────────────────────

    @property
    def value(self):
        return self.field.value or ""

    @value.setter
    def value(self, v):
        self.field.value = v

    # ── internal ────────────────────────────────────────────────

    def _on_change(self, e):
        """Open the panel on the first key typed in the field itself, and look the text up after a short pause."""
        self._page.run_task(self.field.open_view)
        text = (e.control.value or "").strip()
        with self._lock:
            self._req_id += 1
            req_id = self._req_id
        if len(text) < 2:
            self._show_results([])
            return

        def worker():
            """Search once the typing pauses, and show the results unless newer text came in meanwhile."""
            time.sleep(0.3)
            with self._lock:
                if req_id != self._req_id:
                    return
            try:
                results = search_tickers(text, quotes_count=5)
            except Exception:
                results = []
            with self._lock:
                if req_id != self._req_id:
                    return
            self._show_results(results)

        self._page.run_thread(worker)

    async def _on_submit(self, e):
        """Done: close the panel keeping the text typed, then hand over to `on_submit`, if any."""
        await self.field.close_view(self.value)
        if self._on_submit_callback:
            self._on_submit_callback(e)

    def _show_results(self, results):
        """List `results` (search_tickers' dicts) in the panel, keeping only `type_filter`'s kind."""
        if self._type_filter:
            results = [r for r in results if r["quote_type"] == self._type_filter]
        tiles = []
        for r in results:
            symbol = r["symbol"]
            subtitle_parts = [p for p in [r["name"], r["exchange"]] if p]
            tiles.append(
                ft.Container(
                    content=ft.Column([
                        ft.Row([
                            ft.Text(symbol, weight=ft.FontWeight.BOLD, size=13),
                            ft.Text(r["type"], size=11,
                                    color=ft.Colors.with_opacity(0.6, ft.Colors.ON_SURFACE)),
                        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                        ft.Text(" · ".join(subtitle_parts), size=11,
                                color=ft.Colors.with_opacity(0.7, ft.Colors.ON_SURFACE)),
                    ], spacing=0, tight=True),
                    padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                    on_click=lambda _, s=symbol: self._page.run_task(self._pick, s),
                    ink=True,
                    border_radius=ft.BorderRadius.all(6),
                )
            )
        self.field.controls = tiles
        self._page.update()

    async def _pick(self, symbol):
        """Close the panel with `symbol` in the field, and tell `on_select`."""
        await self.field.close_view(symbol)
        if self._on_select:
            self._on_select(symbol)
