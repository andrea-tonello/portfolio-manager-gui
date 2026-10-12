import flet as ft

from components.inputs import RADIUS


def action_card_btn(icon, label, on_click, *, padding=20, height=None, **card_kwargs) -> ft.Card:
    """Return a raised, tappable card with a large icon above a short label.

    Settings uses it for "Export backup" and "Import backup", Transactions for "Filters".
    `label` is a string, or an ft.Text for a label that changes later (e.g. the
    fee choices in Operations). Any other keyword goes to the card itself, to say
    how it fits in its row, e.g. expand=True to share the row's width, or
    col={"xs": 4} inside a ResponsiveRow.
    """
    if isinstance(label, str):
        label = ft.Text(label, text_align=ft.TextAlign.CENTER)
    return ft.Card(
        content=ft.Container(
            content=ft.Column([
                ft.Icon(icon, size=32),
                label,
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, alignment=ft.MainAxisAlignment.CENTER, spacing=8),
            padding=padding,
            height=height,
            border_radius=15,
            bgcolor=ft.Colors.SECONDARY_CONTAINER,
            on_click=on_click,
            ink=True,
        ),
        elevation=3,
        **card_kwargs,
    )


def squircle_add_btn(on_click):
    return ft.FilledButton(
        content=ft.Icon(ft.Icons.ADD_CIRCLE_OUTLINE, size=26),
        height=46,
        width=46,
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=RADIUS), padding=0),
        on_click=on_click,
    )