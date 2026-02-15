import flet as ft

from app_state import AppState
from services import config_service
from views import _rebuild_page
from utils.constants import LANG


_PALETTE_COLORS = {
    "blue": ft.Colors.BLUE,
    "teal": ft.Colors.TEAL,
    "green": ft.Colors.GREEN,
    "yellow": ft.Colors.YELLOW,
    "orange": ft.Colors.ORANGE,
    "red": ft.Colors.RED,
    "purple": ft.Colors.PURPLE,
    "indigo": ft.Colors.INDIGO,
}


def _apply_theme(page: ft.Page, state):
    mode_map = {"system": ft.ThemeMode.SYSTEM, "light": ft.ThemeMode.LIGHT, "dark": ft.ThemeMode.DARK}
    page.theme_mode = mode_map.get(state.theme_mode, ft.ThemeMode.SYSTEM)
    color = _PALETTE_COLORS.get(state.color_seed, ft.Colors.BLUE)
    page.theme = ft.Theme(color_scheme_seed=color)
    page.dark_theme = ft.Theme(color_scheme_seed=color)


def main(page: ft.Page):
    page.title = "Portfolio Manager"
    page.padding = 10
    page.window.width = 420
    page.window.height = 800

    state = AppState(base_path=".")
    state.load_config()
    _apply_theme(page, state)

    # First boot: no language set
    if state.lang_code is None:
        _show_language_picker(page, state)
        return

    # First boot: no brokers
    if not state.brokers:
        _show_broker_onboarding(page, state)
        return

    state.ensure_defaults()
    state.load_all_accounts()

    _rebuild_page(page, state)


def _show_language_picker(page: ft.Page, state: AppState):
    t = state.translator
    options = [
        ft.dropdown.Option(key=code, text=name)
        for _, (code, name) in sorted(LANG.items())
    ]
    dd = ft.Dropdown(
        label=t.get("settings.language.select_language"),
        options=options,
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
        ft.Column([
            ft.Text(t.get("settings.language.select_language"), size=20, weight=ft.FontWeight.BOLD),
            dd,
            ft.ElevatedButton(t.get("components.submit"), on_click=on_submit),
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER,
           alignment=ft.MainAxisAlignment.CENTER,
           expand=True)
    )
    page.update()


def _show_broker_onboarding(page: ft.Page, state: AppState):
    t = state.translator
    broker_field = ft.TextField(
        label=t.get("settings.account.add_account").strip().split("\n")[0],
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
        broker_list.controls.append(ft.Text(f"  {next_idx}. {name}"))
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
        ft.Column([
            ft.Text(t.get("main_menu.first_boot").strip(), size=14),
            ft.ResponsiveRow([
                broker_field,
                ft.ElevatedButton(t.get("components.submit"), icon=ft.Icons.ADD, on_click=on_add,
                                  col={"xs": 12, "sm": 4}),
            ]),
            broker_list,
            ft.Divider(),
            ft.ElevatedButton("Done", icon=ft.Icons.CHECK, on_click=on_done),
        ], spacing=15, expand=True)
    )
    page.update()


ft.app(target=main)
