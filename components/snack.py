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
    A value that is itself a ValidationError, such as the reason inside a
    journal's OperationRefused, is translated too and put in its place.

    Example: ValidationError("operations.stock.sell_noqt", quantity=5, last_remaining_qt=3)
    becomes "Quantity sold (5) exceeds available quantity (3)" in English.
    """
    if isinstance(ex, ValidationError):
        params = {name: error_message(translator, value) if isinstance(value, ValidationError) else value
                  for name, value in ex.params.items()}
        return translator.get(ex.key, **params)
    return str(ex)
