import flet as ft

from utils.constants import GITHUB_URL


def show_info_dialog(page: ft.Page, title, body, *, markdown=False, height=None, title_size=None):
    """Show a read-only dialog: a title, an explanation and an OK button that closes it.

    Used by the "?" help buttons, the privacy policy and the contacts. With markdown=True the
    body can contain formatting and links (opened in the browser), and it scrolls when it is
    taller than the dialog; pass `height` to fix the dialog's height instead of fitting the text.
    """
    if markdown:
        content = ft.Column([
            ft.Markdown(body, auto_follow_links=True, extension_set=ft.MarkdownExtensionSet.GITHUB_WEB),
        ], scroll=ft.ScrollMode.AUTO, tight=True)
    else:
        content = ft.Text(body)
    page.show_dialog(ft.AlertDialog(
        title=ft.Text(title, size=title_size),
        content=ft.Container(content=content, width=450, height=height),
        actions=[ft.TextButton("OK", on_click=lambda _: page.pop_dialog())],
    ))


def show_privacy_policy(page: ft.Page, state):
    """Show the privacy policy, read from privacy_policy_<language>.txt."""
    t = state.translator
    show_info_dialog(page, t.get("settings.privacy_policy"),
                     t.load_text("privacy_policy") or "Privacy policy not available.",
                     markdown=True, height=450)


def show_contacts(page: ft.Page, state):
    """Show how to reach the developer, with clickable links."""
    t = state.translator
    show_info_dialog(page, t.get("settings.contacts"), t.get("settings.contacts_content"), markdown=True)


def show_user_manager(app):
    """Show the list of users: switch to one, delete one, or add a new one (which takes over the screen)."""
    page, state = app.page, app.state
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
                    padding=ft.Padding.symmetric(horizontal=16, vertical=12),
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
                    padding=ft.Padding.symmetric(horizontal=16, vertical=4),
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
        state.remove_user(user_idx)
        show_user_manager(app)

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
        state.switch_user(user_idx)
        app.restart()

    def _on_add_user():
        page.pop_dialog()
        # Take over full screen: hide appbar and navbar
        page.appbar = None
        page.navigation_bar = None
        app.nav_wrapper = None
        original_user_idx = state.active_user_idx

        def _restore_and_restart():
            state.switch_user(original_user_idx)
            app.restart()

        def cancel_broker(created_idx):
            # Switch back first: the new user is still the active one, and can't be removed while active.
            state.switch_user(original_user_idx)
            state.remove_user(created_idx)
            app.restart()

        def after_user_created():
            created_idx = state.active_user_idx
            page.controls.clear()
            app.show_broker_onboarding(
                on_complete=app.restart,
                on_cancel=lambda: cancel_broker(created_idx),
            )

        app.show_user_creation(on_complete=after_user_created, first_time=False, on_cancel=_restore_and_restart)

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
            padding=ft.Padding.only(top=8, bottom=9, left=7, right=7),
            border_radius=15,
        ),
        actions=[
            ft.FilledButton(content=ft.Icon(ft.Icons.ADD, size=26), 
                            style=ft.ButtonStyle(shape=ft.CircleBorder(), padding=20), 
                            on_click=lambda _: page.run_task(_drawer_tap, _on_add_user)),
        ],
        actions_alignment=ft.MainAxisAlignment.CENTER,
    )
    page.show_dialog(dlg)


def build_github_repo(state, img_size=44, font_size=16, font_bold=True):
    t = state.translator
    github_icon = ft.Image(src="imgs/github-logo.png", width=img_size, height=img_size, border_radius=30)
    icon_and_text = ft.Row([github_icon, ft.Text(t.get("settings.repo"), 
                            size=font_size, weight=ft.FontWeight.BOLD if font_bold else None),])

    return ft.Container(
        content=ft.Row([
            icon_and_text,
            ft.Icon(ft.Icons.OPEN_IN_NEW),
        ], spacing=15, alignment=ft.MainAxisAlignment.SPACE_BETWEEN, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        padding=ft.Padding.only(left=16, right=16, top=4, bottom=4),
        url=GITHUB_URL,
        border_radius=15,
        ink=True
    )


