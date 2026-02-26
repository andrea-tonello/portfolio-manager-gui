import flet as ft

from views.home_view import HomeView
from views.operations_view import OperationsView
from views.analysis_view import AnalysisView
from views.transactions_view import TransactionsView
from views.settings_view import SettingsView


_NAV_LABELS = ["nav.home", "nav.operations", "nav.analysis", "nav.transactions"]
_VIEW_BUILDERS = [HomeView, OperationsView, AnalysisView, TransactionsView]
_TAB_TO_GLOSSARY = {0: 2, 1: 3, 2: 4, 3: 5}


def _rebuild_page(page: ft.Page, state, selected_index: int = 0):
    t = state.translator
    state._last_nav_index = selected_index
    page.on_view_pop = None
    if page.views:
        page.views[0].can_pop = True
        page.views[0].on_confirm_pop = None

    current_view = _VIEW_BUILDERS[selected_index](page, state).build()

    page_title = t.get(_NAV_LABELS[selected_index])

    page.appbar = ft.AppBar(
        title=ft.Text(page_title),
        actions=[
            ft.Container(
                ft.IconButton(
                    icon=ft.Icons.SETTINGS,
                    tooltip=t.get("nav.settings"),
                    on_click=lambda e: _show_settings(page, state),
                ),
                padding=ft.padding.only(right=8),
            ),
        ],
    )

    nav_bar = ft.NavigationBar(
        selected_index=selected_index,
        destinations=[
            ft.NavigationBarDestination(icon=ft.Icons.HOME_OUTLINED, label=t.get("nav.home"),
                                        selected_icon=ft.Icons.HOME),
            ft.NavigationBarDestination(icon=ft.Icons.SWAP_HORIZ, label=t.get("nav.operations")),
            ft.NavigationBarDestination(icon=ft.Icons.ANALYTICS_OUTLINED, label=t.get("nav.analysis"),
                                        selected_icon=ft.Icons.ANALYTICS),
            ft.NavigationBarDestination(icon=ft.Icons.RECEIPT_LONG_OUTLINED, label=t.get("nav.transactions"),
                                        selected_icon=ft.Icons.RECEIPT_LONG),
        ],
        on_change=lambda e: _on_nav_change(e, page, state),
    )

    # Wrap analysis/transactions views in a Stack with a floating info button
    if selected_index in (2, 3):
        if selected_index == 2:
            def _info_click(_):
                p = _TAB_TO_GLOSSARY.get(getattr(state, "_analysis_tab_index", 0), 2)
                _show_glossary(page, state, p)
            info_handler = _info_click
        else:
            info_handler = lambda _: _show_glossary(page, state, 1)
        current_view = ft.Stack([
            ft.Column([current_view], expand=True),
            ft.Container(
                content=ft.FloatingActionButton(
                    icon=ft.Icons.INFO_OUTLINE,
                    mini=True,
                    on_click=info_handler,
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

    def _go_back(e):
        _rebuild_page(page, state, selected_index=state._last_nav_index)

    page.on_view_pop = _go_back
    if page.views:
        page.views[0].can_pop = False
        page.views[0].on_confirm_pop = _go_back
    page.appbar = ft.AppBar(
        leading=ft.IconButton(
            icon=ft.Icons.ARROW_BACK,
            on_click=_go_back,
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
    page_data = t.strings.get("glossary", {}).get(f"page_{page_num}", {})
    controls = []
    has_title = False
    for key, value in page_data.items():
        if key == "title":
            continue
        if key.endswith("_title"):
            padding = ft.padding.only(top=10) if has_title else None
            controls.append(ft.Container(
                ft.Text(value, size=13, weight=ft.FontWeight.BOLD),
                padding=padding,
            ))
            has_title = True
        else:
            controls.append(ft.Text(value, size=12, selectable=True))
    dlg = ft.AlertDialog(
        title=ft.Text(page_data.get("title", "")),
        content=ft.Column(controls, scroll=ft.ScrollMode.AUTO, tight=True, spacing=3),
        actions=[ft.TextButton("OK", on_click=lambda e: page.pop_dialog())],
    )
    page.show_dialog(dlg)


def _on_nav_change(e, page, state):
    idx = e.control.selected_index
    if idx != 0:
        state._home_nav_count += 1
    _rebuild_page(page, state, selected_index=idx)
