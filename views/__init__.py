import asyncio
import flet as ft

from views.home_view import HomeView
from views.operations_view import OperationsView
from views.analysis_view import AnalysisView
from views.transactions_view import TransactionsView
from views.settings_view import SettingsView


_NAV_LABELS = ["nav.home", "nav.operations", "nav.analysis", "nav.transactions"]
_VIEW_BUILDERS = [HomeView, OperationsView, AnalysisView, TransactionsView]

# analysis:   tab 0 -> glossary page 2,   tab 1 -> page 3, etc.
_TRANSACTIONS_GLOSSARY_PAGE = 1
_ANALYSIS_GLOSSARY_PAGE_OFFSET = 2  

def _rebuild_page(page: ft.Page, state, selected_index: int = 0):
    t = state.translator
    state._last_nav_index = selected_index
    page.on_view_pop = None
    if page.views:
        page.views[0].can_pop = True
        page.views[0].on_confirm_pop = None

    current_view = _VIEW_BUILDERS[selected_index](page, state).build()

    page_title = t.get(_NAV_LABELS[selected_index])

    if selected_index == 0:
        appbar_title = ft.Row([
            ft.Image(src="appbar-icon.jpg", width=44, height=44, border_radius=30),
            ft.Text("Portfolio Manager"),
        ], spacing=10)
    else:
        appbar_title = ft.Text(page_title)

    page.appbar = ft.AppBar(
        title=appbar_title,
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
                p = getattr(state, "_analysis_tab_index", 0) + _ANALYSIS_GLOSSARY_PAGE_OFFSET
                _show_glossary(page, state, p)
            info_handler = _info_click
        else:
            info_handler = lambda _: _show_glossary(page, state, _TRANSACTIONS_GLOSSARY_PAGE)
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

    # Persistent wrapper with animate_opacity + animate_scale for zoom-fade transitions
    wrapper = page.data.get("_nav_wrapper")

    if wrapper is None:
        # First call — build the full page structure
        wrapper = ft.Container(
            content=current_view,
            opacity=1,
            scale=1,
            animate_opacity=ft.Animation(70, ft.AnimationCurve.EASE_OUT),
            animate_scale=ft.Animation(70, ft.AnimationCurve.EASE_OUT),
            expand=True,
        )
        page.data["_nav_wrapper"] = wrapper
        page.controls.clear()
        page.controls.append(
            ft.SafeArea(ft.Column([wrapper], expand=True), expand=True)
        )
        page.navigation_bar = nav_bar

        # Hide navigation bar when the on-screen keyboard is open
        def _on_keyboard_visibility(e):
            keyboard_open = page.media.view_insets.bottom > 0
            page.navigation_bar.visible = not keyboard_open
            page.update()
        page.on_media_change = _on_keyboard_visibility
    else:
        # Subsequent calls — swap content and fade in
        wrapper.content = current_view
        wrapper.opacity = 1
        wrapper.scale = 1
        page.navigation_bar.selected_index = selected_index

    page.update()


def _show_settings(page: ft.Page, state):
    """Show the settings page as a pushed View with a theme transition."""
    t = state.translator

    def _go_back(e=None):
        if len(page.views) > 1:
            page.views.pop()
        page.update()
        _rebuild_page(page, state, selected_index=state._last_nav_index)

    page.on_view_pop = lambda _: _go_back()

    settings_content = SettingsView(page, state).build()

    settings_view = ft.View(
        route="/settings",
        appbar=ft.AppBar(
            leading=ft.IconButton(
                icon=ft.Icons.ARROW_BACK,
                on_click=lambda _: _go_back(),
            ),
            title=ft.Text(t.get("nav.settings")),
        ),
        controls=[
            ft.SafeArea(ft.Column([settings_content], expand=True), expand=True)
        ],
    )
    # Replace existing settings view if already on settings (e.g. language change)
    if len(page.views) > 1 and getattr(page.views[-1], "route", None) == "/settings":
        page.views.pop()
    page.views.append(settings_view)
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
        content=ft.Container(
            content=ft.Column(controls, scroll=ft.ScrollMode.AUTO, tight=True, spacing=3),
        height=300 if page_num in [2, 3] else 150, width=600),
        actions=[ft.TextButton("OK", on_click=lambda e: page.pop_dialog())],
    )
    page.show_dialog(dlg)


def _on_nav_change(e, page, state):
    idx = e.control.selected_index
    if idx != 0:
        state._home_nav_count += 1

    wrapper = page.data.get("_nav_wrapper")
    if wrapper is not None:
        # Fade out + scale down, then swap content
        wrapper.opacity = 0
        wrapper.scale = 0.96
        page.update()

        async def _finish():
            await asyncio.sleep(0.15)
            _rebuild_page(page, state, selected_index=idx)
        page.run_task(_finish)
    else:
        _rebuild_page(page, state, selected_index=idx)
