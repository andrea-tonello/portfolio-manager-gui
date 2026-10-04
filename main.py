import os
import flet as ft

from app_controller import AppController

_DATA_DIR = os.getenv("FLET_APP_STORAGE_DATA", ".")


def main(page: ft.Page):
    """Set up the window and start the app (Flet calls this once the page is ready)."""
    page.title = "Portfolio Manager"
    page.adaptive = True
    page.padding = 10
    page.window.width = 400
    page.window.height = 780
    AppController(page, base_path=_DATA_DIR).restart()


if __name__ == "__main__":
    ft.run(main)
