"""The file picker the screens share, and saving bytes to a file the user chooses."""

import flet as ft

from components.snack import show_snack


def get_file_picker(page: ft.Page) -> ft.FilePicker:
    """Return the page's FilePicker, registering one the first time it is needed.

    A FilePicker is a page service (it shows the system's save and open
    dialogs), so one is enough for the whole app: every screen reuses it.
    """
    for service in page.services:
        if isinstance(service, ft.FilePicker):
            return service
    picker = ft.FilePicker()
    page.services.append(picker)
    return picker


async def save_bytes(page: ft.Page, picker, file_name: str, data: bytes, extension: str, success_message: str) -> bool:
    """Ask the user where to save `data` as `file_name`; show `success_message` once saved.

    Flet writes the bytes to the chosen place itself, on every platform. The
    path it returns is only a confirmation and must never be opened: on
    Android it is a document reference such as "/document/753", not a file
    path. Returns False, showing nothing, if the user cancels the dialog.

    Example: save_bytes(page, picker, "Drawdown.csv", csv_bytes, "csv", "Exported")
    """
    path = await picker.save_file(file_name=file_name, allowed_extensions=[extension], src_bytes=data)
    if path:
        show_snack(page, success_message)
    return bool(path)
