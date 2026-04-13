import os
import flet as ft

from services import config_service

GITHUB_URL = "https://github.com/andrea-tonello/portfolio-manager-gui"


def show_privacy_policy(page: ft.Page, state):
    t = state.translator
    lang = state.lang_code or "en"
    pp_path = os.path.join(os.path.dirname(__file__), "..", "locales", f"privacy_policy_{lang}.txt")
    try:
        with open(pp_path, encoding="utf-8") as f:
            pp_text = f.read()
    except FileNotFoundError:
        pp_text = "Privacy policy not available."
    dlg = ft.AlertDialog(
        title=ft.Text(t.get("settings.privacy_policy")),
        content=ft.Container(
            content=ft.Column([
                ft.Markdown(pp_text, auto_follow_links=True,
                            extension_set=ft.MarkdownExtensionSet.GITHUB_WEB),
            ], scroll=ft.ScrollMode.AUTO, tight=True),
            width=450, height=450,
        ),
        actions=[ft.TextButton("OK", on_click=lambda _: page.pop_dialog())],
    )
    page.show_dialog(dlg)


def show_contacts(page: ft.Page, state):
    t = state.translator
    dlg = ft.AlertDialog(
        title=ft.Text(t.get("settings.contacts")),
        content=ft.Container(
            content=ft.Markdown(
                t.get("settings.contacts_content"),
                auto_follow_links=True,
                extension_set=ft.MarkdownExtensionSet.GITHUB_WEB
            ),
            width=450,
        ),
        actions=[ft.TextButton("OK", on_click=lambda _: page.pop_dialog())],
    )
    page.show_dialog(dlg)


def show_user_manager(page: ft.Page, state):
    t = state.translator

    def _build_user_list():
        rows = []
        for idx in sorted(state.users.keys()):
            name = state.users[idx]
            is_active = (idx == state.active_user_idx)
            if is_active:
                row = ft.Container(
                    ft.Row([
                        ft.Text(name, size=16, expand=True, color=ft.Colors.ON_PRIMARY),
                        ft.Text(t.get("settings.user_mgmt.active"), size=14, color=ft.Colors.SURFACE_CONTAINER),
                    ]),
                    bgcolor=ft.Colors.PRIMARY,
                    border_radius=10,
                    padding=ft.padding.symmetric(horizontal=16, vertical=12),
                )
            else:
                row = ft.Container(
                    ft.Row([
                        ft.Text(name, size=16, expand=True, ),
                        ft.IconButton(
                            icon=ft.Icons.DELETE,
                            icon_color=ft.Colors.RED,
                            icon_size=20,
                            on_click=lambda _, i=idx: _confirm_delete(i),
                        ),
                    ]),
                    padding=ft.padding.symmetric(horizontal=16, vertical=4),
                    on_click=lambda _, i=idx: _confirm_switch(i),
                    ink=True,
                    border_radius=10,
                )
            rows.append(row)
        return rows

    def _confirm_delete(user_idx):
        name = state.users[user_idx]
        confirm_dlg = ft.AlertDialog(
            title=ft.Text(t.get("settings.user_mgmt.delete_title")),
            content=ft.Text(t.get("settings.user_mgmt.delete_confirm", username=name)),
            actions=[
                ft.TextButton(t.get("components.cancel"), on_click=lambda _: page.pop_dialog()),
                ft.TextButton(
                    t.get("settings.user_mgmt.delete_title"),
                    style=ft.ButtonStyle(color=ft.Colors.RED),
                    on_click=lambda _: _do_delete(user_idx),
                ),
            ],
        )
        page.show_dialog(confirm_dlg)

    def _do_delete(user_idx):
        page.pop_dialog()  # pop confirm dialog
        page.pop_dialog()  # pop stale user manager underneath
        config_service.delete_user(state.config_folder, state.users, user_idx)
        state.load_config()
        show_user_manager(page, state)

    def _confirm_switch(user_idx):
        name = state.users[user_idx]
        switch_dlg = ft.AlertDialog(
            content=ft.Text(t.get("settings.user_mgmt.switch_confirm", username=name), size=16),
            actions=[
                ft.TextButton(t.get("components.cancel"), on_click=lambda _: page.pop_dialog()),
                ft.TextButton("OK", on_click=lambda _: _do_switch(user_idx)),
            ],
        )
        page.show_dialog(switch_dlg)

    def _do_switch(user_idx):
        page.pop_dialog()
        config_service.save_active_user(state.config_folder, user_idx)
        page.data["restart"]()

    def _on_add_user():
        page.pop_dialog()
        # Take over full screen: hide appbar and navbar
        page.appbar = None
        page.navigation_bar = None
        if isinstance(page.data, dict):
            page.data.pop("_nav_wrapper", None)

        show_user_creation = page.data.get("show_user_creation")
        show_broker_onboarding = page.data.get("show_broker_onboarding")
        restart = page.data["restart"]
        original_user_idx = state.active_user_idx

        def _restore_and_restart():
            config_service.save_active_user(state.config_folder, original_user_idx)
            state.load_config()
            restart()

        def cancel_broker(created_idx):
            config_service.delete_user(state.config_folder, state.users, created_idx)
            _restore_and_restart()

        def after_user_created():
            created_idx = state.active_user_idx
            page.controls.clear()
            show_broker_onboarding(
                page, state,
                on_complete=lambda: page.data["restart"](),
                on_cancel=lambda: cancel_broker(created_idx),
            )

        show_user_creation(page, state, on_complete=after_user_created, first_time=False, on_cancel=_restore_and_restart)

    user_rows = _build_user_list()

    async def _drawer_tap(action):
        await page.close_end_drawer()
        action()

    dlg = ft.AlertDialog(
        title=ft.Column([
            ft.Icon(ft.Icons.PERSON, size=48),
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
        content=ft.Container(
            ft.Column(user_rows, scroll=ft.ScrollMode.AUTO, spacing=4),
            width=300,
            height=240,
            bgcolor=ft.Colors.SURFACE_DIM,
            padding=ft.padding.only(top=8, bottom=9, left=7, right=7),
            border_radius=15,
        ),
        actions=[
            ft.IconButton(icon=ft.Icons.ADD, icon_size=32, on_click=lambda _: page.run_task(_drawer_tap, _on_add_user)),
        ],
        actions_alignment=ft.MainAxisAlignment.CENTER,
    )
    page.show_dialog(dlg)


def build_github_repo(state, img_size=44, font_size=16, font_bold=True):
    t = state.translator
    github_icon = ft.Image(src="github-logo.png", width=img_size, height=img_size, border_radius=30)
    icon_and_text = ft.Row([github_icon, ft.Text(t.get("settings.repo"), 
                            size=font_size, weight=ft.FontWeight.BOLD if font_bold else None),])

    return ft.Container(
        content=ft.Row([
            icon_and_text,
            ft.Icon(ft.Icons.OPEN_IN_NEW),
        ], spacing=15, alignment=ft.MainAxisAlignment.SPACE_BETWEEN, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        padding=ft.padding.only(left=16, right=16, top=4, bottom=4),
        url="https://github.com/andrea-tonello/portfolio-manager-gui",
        border_radius=15,
        ink=True
    )


