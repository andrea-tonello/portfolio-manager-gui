import flet as ft

from views.home_view import HomeView
from views.operations_view import OperationsView
from views.analysis_view import AnalysisView
from views.transactions_view import TransactionsView
from views.settings_view import SettingsView
from utils.other_utils import _GLOSSARY_KEYS


_NAV_LABELS = ["nav.home", "nav.operations", "nav.analysis", "nav.transactions"]


def _rebuild_page(page: ft.Page, state, selected_index: int = 0):
    t = state.translator
    state._last_nav_index = selected_index

    views = [
        HomeView(page, state).build(),
        OperationsView(page, state).build(),
        AnalysisView(page, state).build(),
        TransactionsView(page, state).build(),
    ]

    page_title = t.get(_NAV_LABELS[selected_index])

    page.appbar = ft.AppBar(
        title=ft.Text(page_title),
        actions=[
            ft.IconButton(
                icon=ft.Icons.SETTINGS,
                tooltip=t.get("nav.settings"),
                on_click=lambda e: _show_settings(page, state),
            ),
        ],
    )

    nav_bar = ft.NavigationBar(
        selected_index=selected_index,
        destinations=[
            ft.NavigationBarDestination(icon=ft.Icons.HOME, label=t.get("nav.home")),
            ft.NavigationBarDestination(icon=ft.Icons.SWAP_HORIZ, label=t.get("nav.operations")),
            ft.NavigationBarDestination(icon=ft.Icons.ANALYTICS, label=t.get("nav.analysis")),
            ft.NavigationBarDestination(icon=ft.Icons.RECEIPT_LONG, label=t.get("nav.transactions")),
        ],
        on_change=lambda e: _on_nav_change(e, page, state, views),
    )

    current_view = views[selected_index]

    # Wrap analysis view (index 2) in a Stack with a floating info button
    if selected_index == 2:
        current_view = ft.Stack([
            ft.Column([current_view], expand=True),
            ft.Container(
                content=ft.FloatingActionButton(
                    icon=ft.Icons.INFO_OUTLINE,
                    on_click=lambda e: _show_glossary(page, state, 2),
                ),
                right=16,
                bottom=8,
            ),
        ], expand=True)

    page.controls.clear()
    page.controls.append(
        ft.SafeArea(ft.Column([current_view], expand=True), expand=True)
    )
    page.navigation_bar = nav_bar
    page.update()


def _show_settings(page: ft.Page, state):
    """Show the settings page with a back button in the AppBar."""
    t = state.translator

    page.appbar = ft.AppBar(
        leading=ft.IconButton(
            icon=ft.Icons.ARROW_BACK,
            on_click=lambda e: _rebuild_page(page, state, selected_index=state._last_nav_index),
        ),
        title=ft.Text(t.get("nav.settings")),
    )

    settings_view = SettingsView(page, state).build()

    page.controls.clear()
    page.controls.append(
        ft.SafeArea(ft.Column([settings_view], expand=True), expand=True)
    )
    page.navigation_bar = None
    page.update()


def _show_glossary(page, state, page_num):
    t = state.translator
    keys = _GLOSSARY_KEYS.get(page_num, [])
    keys = keys[1:]     # remove title
    text = "\n".join(t.get(k) for k in keys)
    dlg = ft.AlertDialog(
        title=ft.Text(t.get(f"glossary.page_{page_num}.title")),
        content=ft.Column([
            ft.Text(text, size=12, selectable=True),
        ], scroll=ft.ScrollMode.AUTO, tight=True),
        actions=[ft.TextButton("OK", on_click=lambda e: page.pop_dialog())],
    )
    page.show_dialog(dlg)


def _on_nav_change(e, page, state, views):
    idx = e.control.selected_index
    _rebuild_page(page, state, selected_index=idx)
