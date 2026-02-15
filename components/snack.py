import flet as ft


def show_snack(page: ft.Page, message: str, error: bool = False):
    snack = ft.SnackBar(
        content=ft.Text(message),
        bgcolor=ft.Colors.RED_200 if error else ft.Colors.GREEN_200,
        duration=2500,
        open=True,
    )
    page.overlay.append(snack)
    page.update()
