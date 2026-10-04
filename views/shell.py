"""The app shell around the four tabs: side drawer, app bar, navigation bar, Settings page and glossary dialogs.

AppController calls these functions; screens never import them, they ask the
controller instead (app.refresh(), app.show_settings(), ...).
"""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass

import flet as ft

from components.dialogs import show_contacts, show_privacy_policy, show_user_manager
from views.home_view import HomeView
from views.operations_view import OperationsView
from views.analysis_view import AnalysisView
from views.transactions_view import TransactionsView
from views.settings_view import SettingsView
from utils.constants import APP_VERSION, GITHUB_URL


@dataclass(frozen=True)
class TabSpec:
    """One tab of the bottom navigation bar: its name, icons, screen and info button.

    `glossary_page` receives the AppState and returns the glossary page the
    tab's floating info button opens; None means the tab has no info button.
    """

    label_key: str
    icon: str
    selected_icon: str | None
    view: type
    glossary_page: Callable[..., int] | None = None


# Analysis tool 0 is explained on glossary page 2, tool 1 on page 3, and so on.
_ANALYSIS_FIRST_GLOSSARY_PAGE = 2

# The tabs, in navigation-bar order. Everything about a tab is on its line.
TABS = (
    TabSpec("nav.home", ft.Icons.HOME_OUTLINED, ft.Icons.HOME, HomeView),
    TabSpec("nav.operations", ft.Icons.SWAP_HORIZ, None, OperationsView),
    TabSpec("nav.analysis", ft.Icons.ANALYTICS_OUTLINED, ft.Icons.ANALYTICS, AnalysisView,
            glossary_page=lambda state: _ANALYSIS_FIRST_GLOSSARY_PAGE + state.analysis_tab_index),
    TabSpec("nav.transactions", ft.Icons.RECEIPT_LONG_OUTLINED, ft.Icons.RECEIPT_LONG, TransactionsView,
            glossary_page=lambda state: 1),  # the page explaining the table's columns
)

# Where Home is in TABS: the app opens on it, and its app bar shows the user's name.
HOME_TAB = [tab.view for tab in TABS].index(HomeView)


def show_tab(app, selected_index: int = HOME_TAB):
    """Show tab `selected_index` (its position in TABS) inside the shell.

    The first call, or the first after app.nav_wrapper is cleared, builds the
    whole page: drawer, navigation bar and the animated wrapper holding the
    tab. Later calls only swap the tab's content and the app bar.
    """
    page, state = app.page, app.state
    state.last_nav_index = selected_index
    page.on_view_pop = None
    if page.views:
        page.views[0].can_pop = True
        page.views[0].on_confirm_pop = None

    current_view = _with_info_button(app, selected_index, TABS[selected_index].view(app).build())

    # Build the drawer only when the page structure is being (re)initialized.
    # Replacing page.end_drawer on every tab switch caused the Flutter client
    # to lose the drawer reference, hanging show_end_drawer for 10s.
    # nav_wrapper is cleared on restart / back-from-settings, so the drawer is
    # naturally refreshed when any of those occur (e.g. after a language change).
    if app.nav_wrapper is None:
        page.end_drawer = _build_drawer(app)
    page.appbar = _build_appbar(app, selected_index)

    if app.nav_wrapper is None:
        # First call — build the full page structure. The persistent wrapper
        # animates opacity and scale for the zoom-fade between tabs.
        app.nav_wrapper = ft.Container(
            content=current_view,
            opacity=1,
            scale=1,
            animate_opacity=ft.Animation(70, ft.AnimationCurve.EASE_OUT),
            animate_scale=ft.Animation(70, ft.AnimationCurve.EASE_OUT),
            expand=True,
        )
        page.controls.clear()
        page.controls.append(
            ft.SafeArea(ft.Column([app.nav_wrapper], expand=True), expand=True)
        )
        page.navigation_bar = _build_nav_bar(app, selected_index)

        # Hide navigation bar when the on-screen keyboard is open
        def _on_keyboard_visibility(e):
            if page.navigation_bar is None:
                return
            page.navigation_bar.visible = page.media.view_insets.bottom == 0
            page.update()
        page.on_media_change = _on_keyboard_visibility
    else:
        # Subsequent calls — swap content and fade in
        app.nav_wrapper.content = current_view
        app.nav_wrapper.opacity = 1
        app.nav_wrapper.scale = 1
        page.navigation_bar.selected_index = selected_index

    page.update()


def _build_drawer(app) -> ft.NavigationDrawer:
    """The side menu: Settings, the user manager, privacy policy, contacts, the GitHub link and the version."""
    page, state = app.page, app.state
    t = state.translator
    return ft.NavigationDrawer(
        selected_index=None,
        controls=[
            ft.Container(
                content=ft.Row([
                    ft.Image(src="imgs/appbar-icon.png", width=44, height=44, border_radius=30),
                    ft.Text("Portfolio Manager", size=20),
                ], spacing=10, expand=True),
                padding=ft.Padding.only(left=15, top=10)
            ),
            ft.Divider(),
            ft.ListTile(
                leading=ft.Icon(ft.Icons.SETTINGS),
                trailing=ft.Icon(ft.Icons.KEYBOARD_ARROW_RIGHT),
                title=ft.Text(t.get("nav.settings")),
                on_click=lambda: app.show_settings(),
                min_height=60,
                content_padding=ft.Padding.only(left=25, right=15),
            ),
            ft.ListTile(
                leading=ft.Icon(ft.Icons.PERSON),
                title=ft.Text(state.active_user_name or t.get("settings.user")),
                on_click=lambda: show_user_manager(app),
                min_height=60,
                content_padding=ft.Padding.only(left=25),
            ),
            ft.ListTile(
                leading=ft.Icon(ft.Icons.PRIVACY_TIP),
                title=ft.Text(t.get("settings.privacy_policy")),
                on_click=lambda: show_privacy_policy(page, app.state),
                min_height=60,
                content_padding=ft.Padding.only(left=25),
            ),
            ft.ListTile(
                leading=ft.Icon(ft.Icons.COMMENT),
                title=ft.Text(t.get("settings.contacts")),
                on_click=lambda: show_contacts(page, app.state),
                min_height=60,
                content_padding=ft.Padding.only(left=25),
            ),
            ft.Divider(),
            ft.ListTile(
                trailing=ft.Icon(ft.Icons.OPEN_IN_NEW),
                title=ft.Text(t.get("settings.repo")),
                url=GITHUB_URL,
                min_height=60,
                content_padding=ft.Padding.only(left=25, right=15),
            ),
            ft.Container(
                ft.Text(t.get("components.version") + f" {APP_VERSION}", size=14, color=ft.Colors.GREY, text_align=ft.TextAlign.CENTER),
                alignment=ft.alignment.Alignment.CENTER,
                padding=ft.Padding.only(top=10),
            )
        ],
    )


def _build_appbar(app, selected_index: int) -> ft.AppBar:
    """The top bar: the user's name on Home, the tab's name elsewhere, and the button opening the drawer."""
    page, state = app.page, app.state
    t = state.translator

    async def handle_show_drawer():
        await page.show_end_drawer()

    if selected_index == HOME_TAB:
        appbar_title = ft.Text(state.active_user_name or t.get("settings.user"))
    else:
        appbar_title = ft.Text(t.get(TABS[selected_index].label_key))

    return ft.AppBar(
        title=appbar_title,
        actions=[
            ft.Container(
                ft.IconButton(
                    icon=ft.Icons.MENU,
                    on_click=handle_show_drawer,
                ),
                padding=ft.Padding.only(right=8),
            ),
        ],
    )


def _build_nav_bar(app, selected_index: int) -> ft.NavigationBar:
    """The bottom bar with the four tabs; tapping one switches to it with a short fade."""
    t = app.state.translator
    return ft.NavigationBar(
        selected_index=selected_index,
        destinations=[
            ft.NavigationBarDestination(icon=tab.icon, label=t.get(tab.label_key), selected_icon=tab.selected_icon)
            for tab in TABS
        ],
        on_change=lambda e: _on_nav_change(app, e),
    )


def _with_info_button(app, selected_index: int, view: ft.Control) -> ft.Control:
    """Add the floating info button opening the tab's glossary page; tabs without one are returned unchanged."""
    glossary_page = TABS[selected_index].glossary_page
    if glossary_page is None:
        return view

    def info_handler(_):
        show_glossary(app, glossary_page(app.state))

    return ft.Stack([
        ft.Column([view], expand=True),
        ft.Container(
            content=ft.FloatingActionButton(
                icon=ft.Icons.INFO_OUTLINE,
                mini=app.page.width < 600,
                on_click=info_handler,
            ),
            right=16,
            bottom=8,
        ),
    ], expand=True)


def show_settings(app):
    """Show the settings page as a pushed View with a theme transition."""
    page, t = app.page, app.state.translator

    def _go_back(e=None):
        if len(page.views) > 1:
            page.views.pop()
        # Force full rebuild so navbar/drawer pick up any locale changes
        app.nav_wrapper = None
        page.update()
        app.refresh()

    page.on_view_pop = lambda _: _go_back()

    settings_content = SettingsView(app).build()

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


def show_glossary(app, page_num):
    """Show glossary page `page_num` (1-6) of the locale file, explaining the terms used on screen."""
    page = app.page
    page_data = app.state.translator.section(f"glossary.page_{page_num}")

    controls = []
    has_title = False
    for key, value in page_data.items():
        if key == "title":
            continue
        if key.endswith("_title"):
            padding = ft.Padding.only(top=10) if has_title else None
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
        height=320 if page_num in [1, 3, 4] else 150,
        width=550),
        actions=[ft.TextButton("OK", on_click=lambda e: page.pop_dialog())],
    )
    page.show_dialog(dlg)


def _on_nav_change(app, e):
    """Switch to the tab tapped in the navigation bar: fade the current one out, then show the new one."""
    page, state = app.page, app.state
    idx = e.control.selected_index
    if idx != HOME_TAB:
        state.home_nav_count += 1

    wrapper = app.nav_wrapper
    if wrapper is not None:
        # Fade out + scale down, then swap content
        wrapper.opacity = 0
        wrapper.scale = 0.96
        page.update()

        async def _finish():
            await asyncio.sleep(0.15)
            app.show_tab(idx)
        page.run_task(_finish)
    else:
        app.show_tab(idx)
