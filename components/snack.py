import flet as ft

from domain.errors import ValidationError


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


def error_message(translator, ex: Exception) -> str:
    """Return the text to show the user for an error caught by a screen.

    A ValidationError carries a locale key, translated here into the current
    language; any other error (network failure, bug) is shown with its own text.

    Example: ValidationError("operations.stock.sell_noqt", quantity=5, last_remaining_qt=3)
    becomes "Quantity sold (5) exceeds available quantity (3)" in English.
    """
    if isinstance(ex, ValidationError):
        return translator.get(ex.key, **ex.params)
    return str(ex)
