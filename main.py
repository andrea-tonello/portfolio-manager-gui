import flet as ft

from app_state import AppState
from services import config_service
from views import _rebuild_page
from views.settings_view import PALETTE_COLORS
from utils.constants import LANG


def _apply_theme(page: ft.Page, state):
    mode_map = {"system": ft.ThemeMode.SYSTEM, "light": ft.ThemeMode.LIGHT, "dark": ft.ThemeMode.DARK}
    page.theme_mode = mode_map.get(state.theme_mode, ft.ThemeMode.SYSTEM)
    color = PALETTE_COLORS.get(state.color_seed, ft.Colors.BLUE)
    page.theme = ft.Theme(color_scheme_seed=color)
    page.dark_theme = ft.Theme(color_scheme_seed=color)


def _do_restart(page: ft.Page):
    page.appbar = None
    page.navigation_bar = None
    state = AppState(base_path=".")
    state.load_config()
    state.init_haptic(page)
    _apply_theme(page, state)

    if state.lang_code is None:
        _show_language_picker(page, state)
        return

    if not state.brokers:
        _show_broker_onboarding(page, state)
        return

    state.ensure_defaults()
    state.load_all_accounts()
    _rebuild_page(page, state)


def main(page: ft.Page):
    page.title = "Portfolio Manager"
    page.padding = 10
    page.window.width = 420
    page.window.height = 800
    page.data = {"restart": lambda: _do_restart(page)}

    _do_restart(page)


def _show_language_picker(page: ft.Page, state: AppState):
    t = state.translator
    options = [
        ft.dropdown.Option(key=code, text=name)
        for _, (code, name) in sorted(LANG.items())
    ]
    dd = ft.Dropdown(
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


def _show_broker_onboarding(page: ft.Page, state: AppState):
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
        config_service.save_brokers(state.config_folder, state.brokers, reset=True)
        state.ensure_defaults()
        state.load_config()
        page.controls.clear()
        main(page)

    page.controls.clear()
    page.controls.append(
        ft.SafeArea(
            ft.Column([
                ft.Container([], height=100),
                ft.Text(t.get("settings.new_acc"), size=20),
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
