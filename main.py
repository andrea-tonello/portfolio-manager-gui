import os
import flet as ft

from app_state import AppState
from components.snack import show_snack

_DATA_DIR = os.getenv("FLET_APP_STORAGE_DATA", ".")
from services import config_service
from views import _rebuild_page
from views.settings_view import PALETTE_COLORS
from utils.constants import LANG

_PAGE_TRANSITIONS = ft.PageTransitionsTheme(
    android=ft.PageTransitionTheme.CUPERTINO,
    ios=ft.PageTransitionTheme.CUPERTINO,
    linux=ft.PageTransitionTheme.CUPERTINO,
    macos=ft.PageTransitionTheme.CUPERTINO,
    windows=ft.PageTransitionTheme.CUPERTINO,
)

def _apply_theme(page: ft.Page, state):
    mode_map = {"system": ft.ThemeMode.SYSTEM, "light": ft.ThemeMode.LIGHT, "dark": ft.ThemeMode.DARK}
    page.theme_mode = mode_map.get(state.theme_mode, ft.ThemeMode.SYSTEM)
    color = PALETTE_COLORS.get(state.color_seed, ft.Colors.BLUE)
    page.theme = ft.Theme(color_scheme_seed=color, page_transitions=_PAGE_TRANSITIONS)
    page.dark_theme = ft.Theme(color_scheme_seed=color, page_transitions=_PAGE_TRANSITIONS)


def _do_restart(page: ft.Page):
    page.appbar = None
    page.navigation_bar = None
    # Close any open dialogs
    try:
        page.pop_dialog()
    except Exception:
        pass
    # Clear stale nav transition wrapper so _rebuild_page creates a fresh one
    if isinstance(page.data, dict):
        page.data.pop("_nav_wrapper", None)
    state = AppState(base_path=_DATA_DIR)
    state.load_config()
    state.init_haptic(page)
    _apply_theme(page, state)

    if state.lang_code is None:
        _show_language_picker(page, state)
        return

    # Existing install with no users: prompt for username, then migrate data
    if config_service.needs_user_migration(state.config_folder):
        _show_user_creation(page, state, migration=True)
        return

    if not state.users:
        _show_user_creation(page, state)
        return

    if not state.brokers:
        _show_broker_onboarding(page, state)
        return

    state.ensure_defaults()
    state.load_all_accounts()
    _rebuild_page(page, state)


def main(page: ft.Page):
    page.title = "Portfolio Manager"
    page.adaptive = False
    page.padding = 10
    page.window.width = 400
    page.window.height = 780
    page.data = {
        "restart": lambda: _do_restart(page),
        "show_user_creation": _show_user_creation,
        "show_broker_onboarding": _show_broker_onboarding,
    }
    _do_restart(page)


def _show_language_picker(page: ft.Page, state: AppState):
    t = state.translator
    options = [
        ft.dropdown.Option(key=code, text=name)
        for _, (code, name) in sorted(LANG.items())
    ]
    dd = ft.Dropdown(
        menu_style=ft.MenuStyle(
            shape=ft.RoundedRectangleBorder(radius=15),
        ),
        label=t.get("settings.language.title"),
        options=options,
        border_radius=ft.border_radius.all(15),
        border_color=ft.Colors.with_opacity(0.40, ft.Colors.GREY),
        expand=True,
    )

    def on_submit(e):
        if not dd.value:
            return
        config_service.save_language(state.config_folder, dd.value)
        state.lang_code = dd.value
        state.translator.load_language(dd.value)
        state.load_config()
        page.controls.clear()
        main(page)

    page.controls.clear()
    page.controls.append(
        ft.SafeArea(
            ft.Container(
                ft.Column([
                    ft.Container([], height=200),
                    ft.Text(t.get("settings.language.select"), size=20, weight=ft.FontWeight.BOLD),
                    dd,
                    ft.Container(height=100, expand=True),
                    ft.FilledButton(t.get("components.apply"), icon=ft.Icons.CHECK,
                                    width=150, height=50, on_click=on_submit),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True, spacing=30),
                expand=True,
                padding=15,
            )
        )
    )
    page.update()


def _show_user_creation(page: ft.Page, state: AppState, migration=False, on_complete=None, first_time=True):
    """User creation screen. Used at first boot, migration, and when adding users in-app."""
    t = state.translator
    username_field = ft.TextField(
        label=t.get("settings.user_mgmt.username_hint"),
        border_radius=ft.border_radius.all(15),
        border_color=ft.Colors.with_opacity(0.40, ft.Colors.GREY),
        expand=True,
    )

    def on_submit(e):
        name = username_field.value.strip()
        if not name:
            return
        if name in state.users.values():
            show_snack(page, t.get("settings.user_mgmt.duplicate"), error=True)
            return

        if migration:
            config_service.migrate_to_multi_user(state.config_folder, name)
            state.load_config()
            page.controls.clear()
            _do_restart(page)
            return

        next_idx = max(state.users.keys(), default=0) + 1
        state.users[next_idx] = name
        config_service.save_users(state.config_folder, state.users)
        config_service.save_active_user(state.config_folder, next_idx)
        # Create user folder structure
        user_res = config_service.get_user_res_folder(state.config_folder, name)
        os.makedirs(user_res, exist_ok=True)
        state.load_config()

        if on_complete:
            on_complete()
        else:
            page.controls.clear()
            _show_broker_onboarding(page, state)

    page.controls.clear()
    page.controls.append(
        ft.SafeArea(
            ft.Container(
                ft.Column([
                    ft.Container(height=80),
                    ft.Icon(ft.Icons.PERSON, size=80),
                    ft.Container(height=30),
                    ft.Text(t.get("settings.user_mgmt.add_title"), size=20, weight=ft.FontWeight.BOLD),
                    username_field,
                    ft.Container(expand=True),
                    ft.Text(t.get("settings.user_mgmt.add_later") if first_time else t.get("settings.user_mgmt.duplicate_hint"), 
                            size=14, color=ft.Colors.GREY, text_align=ft.TextAlign.CENTER),
                    ft.Container(height=20),
                    ft.FilledButton(t.get("components.confirm"), icon=ft.Icons.CHECK,
                                    width=150, height=50, on_click=on_submit),
                    ft.Container(height=30),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True, spacing=15),
                expand=True,
                padding=15,
            )
        )
    )
    page.update()


def _show_broker_onboarding(page: ft.Page, state: AppState, on_complete=None):
    t = state.translator
    broker_field = ft.TextField(
        label=t.get("settings.account.add_account"),
        border_radius=ft.border_radius.all(15),
        border_color=ft.Colors.with_opacity(0.40, ft.Colors.GREY),
        expand=True,
    )
    broker_list = ft.Column([], spacing=5)
    brokers_temp = {}

    def on_add(e):
        name = broker_field.value.strip()
        if not name:
            return
        next_idx = max(brokers_temp.keys(), default=0) + 1
        brokers_temp[next_idx] = name

        def on_remove(ev, idx=next_idx):
            brokers_temp.pop(idx, None)
            broker_list.controls[:] = [
                c for c in broker_list.controls
                if c.data != idx
            ]
            page.update()

        broker_list.controls.append(ft.Row([
            ft.Text(f"  {next_idx}. {name}", expand=True),
            ft.IconButton(icon=ft.Icons.DELETE, icon_size=18, on_click=on_remove),
        ], data=next_idx, alignment=ft.MainAxisAlignment.CENTER))
        broker_field.value = ""
        page.update()

    def on_done(e):
        if not brokers_temp:
            snack = ft.SnackBar(
                content=ft.Text(t.get("settings.account.op_denied")),
                bgcolor=ft.Colors.RED_200,
                open=True,
            )
            page.overlay.append(snack)
            page.update()
            return
        state.brokers = brokers_temp
        config_service.save_brokers(state.user_config_folder, state.brokers, reset=True)
        state.ensure_defaults()
        state.load_config()
        if on_complete:
            page.controls.clear()
            on_complete()
        else:
            page.controls.clear()
            main(page)

    page.controls.clear()
    page.controls.append(
        ft.SafeArea(
            ft.Column([
                ft.Container([], height=100),
                ft.Text(t.get("settings.new_acc", username=state.active_user_name or ""), size=20),
                ft.Text(t.get("settings.new_acc_example"), size=14),
                ft.ResponsiveRow([
                    broker_field,
                    ft.ElevatedButton(t.get("components.add"), icon=ft.Icons.ADD, on_click=on_add,
                    width=150, height=35)
                ]),
                broker_list,
                ft.Container(height=50),
                ft.FilledButton(t.get("components.confirm"), icon=ft.Icons.CHECK,
                                width=150, height=50, on_click=on_done),
                ft.Container(height=30),
            ], spacing=15, horizontal_alignment=ft.CrossAxisAlignment.CENTER,
               scroll=ft.ScrollMode.AUTO, expand=True),
            expand=True,
            minimum_padding=15,
        )
    )
    page.update()


ft.app(target=main)
