import threading
import time

import flet as ft

from components.inputs import rounded_text_field
from services.market_data import search_tickers


class TickerSearchField:
    """TextField with live Yahoo Finance ticker search suggestions.

    Like DateField: put `control` on the screen, give `field` (the text box) to the
    focus and scroll helpers, and read or set the ticker through `value`.
    """

    def __init__(self, page: ft.Page, *, label: str = "Ticker",
                 on_select=None, type_filter=None, **kwargs):
        self._page = page
        self._on_select = on_select
        self._type_filter = type_filter  # e.g. "etf", "equity", or None for no filter
        self._req_id = 0
        self._lock = threading.Lock()

        expand = kwargs.pop("expand", False)
        col = kwargs.pop("col", None)

        self.field = rounded_text_field(
            label=label,
            on_change=self._on_change,
            on_blur=self._on_blur,
            capitalization=ft.TextCapitalization.CHARACTERS,
            **kwargs,
        )

        self._suggestions = ft.Column([], spacing=0, tight=True,
                                       scroll=ft.ScrollMode.AUTO)
        self._overlay = ft.Container(
            content=self._suggestions,
            bgcolor=ft.Colors.SURFACE,
            border=ft.Border.all(1, ft.Colors.with_opacity(0.3, ft.Colors.GREY)),
            border_radius=ft.BorderRadius.all(10),
            shadow=ft.BoxShadow(
                spread_radius=0, blur_radius=8,
                color=ft.Colors.with_opacity(0.15, ft.Colors.BLACK),
                offset=ft.Offset(0, 4),
            ),
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            visible=False,
        )

        self.control = ft.Container(
            content=ft.Column([self.field, self._overlay], spacing=2, tight=True,
                              horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
            expand=expand,
            col=col,
        )

    # ── public interface ────────────────────────────────────────

    @property
    def value(self):
        return self.field.value or ""

    @value.setter
    def value(self, v):
        self.field.value = v

    # ── internal ────────────────────────────────────────────────

    def _on_change(self, e):
        text = (e.control.value or "").strip()
        if len(text) < 2:
            self._hide()
            return
        with self._lock:
            self._req_id += 1
            req_id = self._req_id

        def worker():
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
            if not results:
                self._hide()
                return
            self._show_results(results)

        self._page.run_thread(worker)

    def _on_blur(self, e):
        # Tapping a suggestion also blurs the field: wait before hiding the list,
        # so the tap reaches _pick first. This delay is the only protection.
        def _delayed():
            time.sleep(0.15)
            self._hide()
        self._page.run_thread(_delayed)

    def _show_results(self, results):
        if self._type_filter:
            results = [r for r in results if r["quote_type"] == self._type_filter]
        if not results:
            self._hide()
            return
        tiles = []
        for r in results:
            symbol = r["symbol"]
            name = r["name"]
            exchange = r["exchange"]
            type_disp = r["type"]
            subtitle_parts = [p for p in [name, exchange] if p]
            tiles.append(
                ft.Container(
                    content=ft.Column([
                        ft.Row([
                            ft.Text(symbol, weight=ft.FontWeight.BOLD, size=13),
                            ft.Text(type_disp, size=11,
                                    color=ft.Colors.with_opacity(0.6, ft.Colors.ON_SURFACE)),
                        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                        ft.Text(" · ".join(subtitle_parts), size=11,
                                color=ft.Colors.with_opacity(0.7, ft.Colors.ON_SURFACE)),
                    ], spacing=0, tight=True),
                    padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                    on_click=lambda _, s=symbol: self._pick(s),
                    ink=True,
                    border_radius=ft.BorderRadius.all(6),
                )
            )
        self._suggestions.controls = tiles
        self._overlay.height = min(len(tiles) * 52, 260)
        self._overlay.visible = True
        self._page.update()

    def _hide(self):
        if self._overlay.visible:
            self._overlay.visible = False
            self._suggestions.controls = []
            self._page.update()

    def _pick(self, symbol):
        self.field.value = symbol
        self._overlay.visible = False
        self._suggestions.controls = []
        self._page.update()
        if self._on_select:
            self._on_select(symbol)
