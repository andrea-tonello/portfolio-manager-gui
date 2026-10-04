"""The styled text fields and dropdowns every screen uses, so they all look the same.

Their outline is set through Flet 1.0's `border` property, as a rounded
OutlineInputBorder per state. The older border_radius / border_color /
border_width properties are deprecated and removed in Flet 1.3.
"""

import flet as ft

# What can be typed: digits and dashes for dates, digits and a dot for amounts.
DATE_INPUT_FILTER = ft.InputFilter(r"^[0-9\-]*$")
DECIMAL_INPUT_FILTER = ft.InputFilter(r"^[0-9\.]*$")

_RADIUS = 15
_GREY = ft.Colors.with_opacity(0.40, ft.Colors.GREY)


def outlined_border(color, width=1.0, focused_width=2.0) -> dict:
    """Return the per-state `border` value for an input: a rounded outline in `color`, `focused_width` wide on focus.

    Giving the focused state its own entry keeps `color` when the field is
    focused, as the old border_color property did; a single border would
    switch to the theme's primary colour instead.

    Example: outlined_border(GREY) -> 1-wide grey outline, 2-wide grey on focus.
    """
    return {
        ft.ControlState.DEFAULT: ft.OutlineInputBorder(border_radius=_RADIUS, side=ft.BorderSide(width, color)),
        ft.ControlState.FOCUSED: ft.OutlineInputBorder(border_radius=_RADIUS, side=ft.BorderSide(focused_width, color)),
    }


def _rounded_menu() -> ft.MenuStyle:
    """The rounded shape of the list a dropdown opens."""
    return ft.MenuStyle(shape=ft.RoundedRectangleBorder(radius=_RADIUS))


def rounded_text_field(**kwargs) -> ft.TextField:
    """A TextField with the app's rounded grey outline; accepts every TextField option."""
    return ft.TextField(border=outlined_border(_GREY), **kwargs)


def rounded_dropdown(**kwargs) -> ft.Dropdown:
    """A Dropdown with the app's rounded grey outline and rounded menu; accepts every Dropdown option."""
    return ft.Dropdown(border=outlined_border(_GREY), menu_style=_rounded_menu(), **kwargs)


def account_selector(state, value, on_select, all_option=None, hint_text=None) -> ft.Dropdown:
    """The dropdown at the top of a tab choosing which account the tab shows.

    Lists the accounts in number order, after an optional first entry for all
    accounts together: `all_option` is its (key, label), e.g.
    ("overview", "All Accounts"); None means no such entry. `value` is the key
    selected at the start, or None to show `hint_text` instead.
    """
    options = [ft.dropdown.Option(key=key, text=label) for key, label in ([all_option] if all_option else [])]
    options += [ft.dropdown.Option(key=str(idx), text=name) for idx, name in sorted(state.brokers.items())]
    return ft.Dropdown(
        menu_style=_rounded_menu(),
        hint_text=hint_text,
        hint_style=ft.TextStyle(color=ft.Colors.GREY_500),
        value=value,
        options=options,
        on_select=on_select,
        expand=True,
        border=outlined_border(ft.Colors.SECONDARY_CONTAINER, width=2.5, focused_width=2.5),
        bgcolor=ft.Colors.SECONDARY_CONTAINER,
    )
