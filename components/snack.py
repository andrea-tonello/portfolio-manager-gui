import flet as ft


def show_snack(page: ft.Page, message: str, error: bool = False):
    # Remove previous snackbars to prevent unbounded growth
    page.overlay[:] = [c for c in page.overlay if not isinstance(c, ft.SnackBar)]
    snack = ft.SnackBar(
        content=ft.Text(message),
        bgcolor=ft.Colors.RED_200 if error else ft.Colors.GREEN_200,
        duration=2500,
        open=True,
    )
    page.overlay.append(snack)
    page.update()
