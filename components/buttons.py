import flet as ft

from components.inputs import RADIUS


def action_card_btn(icon, label, on_click, *, horizontal=False, padding=20, height=None, **card_kwargs) -> ft.Card:
    """Return a raised, tappable card with a large icon above a short label, or to its left with `horizontal`.

    The two layouts are a style choice: the card keeps the one asked for
    whatever its size. Side by side, the label takes only the width it needs,
    so icon and label stay centred together, and wraps when the card is too
    narrow for it on one line.

    Settings uses it for "Export backup" and "Import backup", Transactions for "Filters".
    `label` is a string, or an ft.Text for a label that changes later (e.g. the
    fee choices in Operations). Any other keyword goes to the card itself, to say
    how it fits in its row, e.g. expand=True to share the row's width, or
    col={"xs": 4} inside a ResponsiveRow.
    """
    if isinstance(label, str):
        label = ft.Text(label, text_align=ft.TextAlign.START if horizontal else ft.TextAlign.CENTER)
    if horizontal:
        label.expand, label.expand_loose = True, True  # only the width it needs, and no more than there is
        content = ft.Row([ft.Icon(icon, size=32), label], alignment=ft.MainAxisAlignment.CENTER,
                         vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=12)
    else:
        content = ft.Column([ft.Icon(icon, size=32), label], horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                            alignment=ft.MainAxisAlignment.CENTER, spacing=8)
    return ft.Card(
        content=ft.Container(
            content=content,
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


def mark_card_selected(card, label, selected):
    """Outline a card from action_card_btn and make its `label` (the ft.Text passed to it) bold, or undo both.

    For cards the user picks one of, e.g. Operations' fee choices: the one
    picked is outlined, the others are left plain.
    """
    card.content.border = ft.Border.all(4, ft.Colors.PRIMARY) if selected else None
    label.weight = ft.FontWeight.BOLD if selected else None


def squircle_add_btn(on_click):
    return ft.FilledButton(
        content=ft.Icon(ft.Icons.ADD_CIRCLE_OUTLINE, size=26),
        height=46,
        width=46,
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=RADIUS), padding=0),
        on_click=on_click,
    )


# How Material greys out a disabled filled button. A pill given its own colours
# needs them spelled out: a colour set on a button otherwise shows in every state.
_DISABLED_BGCOLOR = ft.Colors.with_opacity(0.12, ft.Colors.ON_SURFACE)
_DISABLED_COLOR = ft.Colors.with_opacity(0.38, ft.Colors.ON_SURFACE)


def pill_style(bgcolor=None, color=None) -> ft.ButtonStyle:
    """Return the style of a pill button: its padding, and `bgcolor` and `color` if given (see pill_btn).

    Assign it to a pill's `style` to change its colours once it is on screen.
    Example: add_btn.style = pill_style(bgcolor=ft.Colors.RED) turns the pill
    red; pill_style() gives it back the theme's colours.
    """
    return ft.ButtonStyle(
        padding=ft.Padding.symmetric(horizontal=32, vertical=18),
        bgcolor=bgcolor and {ft.ControlState.DISABLED: _DISABLED_BGCOLOR, ft.ControlState.DEFAULT: bgcolor},
        color=color and {ft.ControlState.DISABLED: _DISABLED_COLOR, ft.ControlState.DEFAULT: color},
    )


def pill_btn(label, on_click, *, icon=None, icon_after=False, bgcolor=None, color=None,
             **button_kwargs) -> ft.FilledButton:
    """Return the pill-shaped button that confirms a screen: Apply, Confirm, Add transaction, Calculate.

    It is as wide as its `label`, with `icon` before it, or after it with
    icon_after=True. `bgcolor` (the background) and `color` (the text and
    icon) default to the theme's; a button with its own colours still greys out
    when disabled. Any other keyword goes to the button itself, e.g.
    disabled=True or width=150.

    Example: pill_btn("Delete", on_delete, icon=ft.Icons.DELETE, bgcolor=ft.Colors.RED,
    color=ft.Colors.WHITE, disabled=True) is a grey pill until its `disabled` is set to False.
    """
    if icon_after:
        # tight: without it the row, and the pill with it, takes all the width it is given.
        content, icon = ft.Row([ft.Text(label), ft.Icon(icon)], tight=True), None
    else:
        content = label
    return ft.FilledButton(
        content,
        icon=icon,
        on_click=on_click,
        style=pill_style(bgcolor, color),
        **button_kwargs,
    )