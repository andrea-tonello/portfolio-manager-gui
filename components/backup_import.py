"""Restoring a backup: pick a .zip, check it, confirm, then replace the app's data with it and start over.

Settings offers it at any time, and the first-launch import screen offers it
instead of setting the app up from scratch.
"""

import flet as ft

from components.snack import error_message, show_snack
from domain.errors import ValidationError
from services import config_service


async def import_backup(app, picker, is_onboarding=False) -> None:
    """Let the user pick a backup .zip and, once they confirm, replace the app's data with it and restart.

    A file that can't be read or isn't a valid backup is refused with a
    message in a red snack bar, and nothing changes.
    """
    page = app.page
    t = app.state.translator
    files = await picker.pick_files(allowed_extensions=["zip"], allow_multiple=False, with_data=True)
    if not files:
        return
    picked = files[0]

    # with_data=True makes every platform return the file contents in
    # picked.bytes (Android may give no usable path); the path is a fallback.
    zip_bytes = picked.bytes
    if not zip_bytes and picked.path:
        try:
            with open(picked.path, "rb") as f:
                zip_bytes = f.read()
        except OSError:
            pass

    if not zip_bytes:
        show_snack(page, t.get("settings.account.import_error"), error=True)
        return

    try:
        config_service.validate_backup(zip_bytes)
    except ValidationError as ex:
        show_snack(page, error_message(t, ex), error=True)
        return

    def confirm(e):
        """Replace the app's data with the backup and start over with it."""
        page.pop_dialog()
        try:
            config_service.import_backup(app.state.config_folder, zip_bytes)
            app.restart()
        except Exception as ex:
            show_snack(page, str(ex), error=True)

    import_dialog_content = (
        ft.Text(t.get("onboarding.import_warning_onboarding")) if is_onboarding
        else ft.Text(t.get("settings.account.import_warning") + t.get("settings.account.suggest_backup"))
    )
    confirmation_color = None if is_onboarding else ft.ButtonStyle(color=ft.Colors.RED)

    page.show_dialog(ft.AlertDialog(
        title=ft.Text(t.get("settings.account.import_backup")),
        content=import_dialog_content,
        actions=[
            ft.TextButton(t.get("components.cancel"), on_click=lambda e: page.pop_dialog()),
            ft.TextButton(
                t.get("settings.account.import_backup"),
                style=confirmation_color,
                on_click=confirm,
            ),
        ],
    ))
