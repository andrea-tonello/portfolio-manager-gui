"""The app's look: light or dark mode, the colour palette, and how pages slide in.

The app controller applies the saved choice at every start, and Settings
applies a new one; both go through apply_theme, so they can't drift apart.
"""

import flet as ft

# The colour palettes offered in Settings, by the key saved in config.ini, in the order listed.
PALETTE_COLORS = {
    "blue": ft.Colors.BLUE,
    "teal": ft.Colors.TEAL,
    "green": ft.Colors.GREEN,
    "yellow": ft.Colors.YELLOW,
    "orange": ft.Colors.ORANGE,
    "red": ft.Colors.RED,
    "purple": ft.Colors.PURPLE,
    "indigo": ft.Colors.INDIGO,
}

# The light/dark choices offered in Settings, by the key saved in config.ini; "system" follows the device.
THEME_MODES = {
    "system": ft.ThemeMode.SYSTEM,
    "light": ft.ThemeMode.LIGHT,
    "dark": ft.ThemeMode.DARK,
}

# Pages slide in the iOS way on every platform (e.g. when Settings opens).
PAGE_TRANSITIONS = ft.PageTransitionsTheme(
    android=ft.PageTransitionTheme.CUPERTINO,
    ios=ft.PageTransitionTheme.CUPERTINO,
    linux=ft.PageTransitionTheme.CUPERTINO,
    macos=ft.PageTransitionTheme.CUPERTINO,
    windows=ft.PageTransitionTheme.CUPERTINO,
)


# How round the corners of every button are. Inputs use a larger radius, but on a computer buttons
# are only 32 px tall, where 15 would look like a pill. Pills set their own shape (components.buttons).
BUTTON_RADIUS = 10


def _page_theme(color):
    """The theme of a page, light or dark, whose colours derive from `color`: its transitions, its buttons' shape and its chips' border.

    A button that sets a style without a shape (e.g. its padding) still takes this shape.
    A chip has an outline, selected or not, like an OutlinedButton: a selected
    chip's pale fill alone is almost the colour of a dialog, where the chips are
    (the Transactions filters). They then look like the filter buttons, plain or marked.
    """
    buttons = ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=BUTTON_RADIUS))
    return ft.Theme(
        color_scheme_seed=color,
        page_transitions=PAGE_TRANSITIONS,
        button_theme=ft.ButtonTheme(style=buttons),
        filled_button_theme=ft.FilledButtonTheme(style=buttons),  # also FilledTonalButton
        outlined_button_theme=ft.OutlinedButtonTheme(style=buttons),
        text_button_theme=ft.TextButtonTheme(style=buttons),
        icon_button_theme=ft.IconButtonTheme(style=buttons),
        segmented_button_theme=ft.SegmentedButtonTheme(style=buttons),
        chip_theme=ft.ChipTheme(border_side=ft.BorderSide(1, ft.Colors.OUTLINE)),
    )


def apply_theme(page, mode, palette):
    """Give `page` the light/dark `mode` and the colour `palette` (keys of the dicts above).

    Unknown keys fall back to the device's mode and blue. The caller redraws
    the page. Example: apply_theme(page, "dark", "teal") gives a dark page
    whose colours derive from teal.
    """
    page.theme_mode = THEME_MODES.get(mode, ft.ThemeMode.SYSTEM)
    color = PALETTE_COLORS.get(palette, ft.Colors.BLUE)
    page.theme = _page_theme(color)
    page.dark_theme = _page_theme(color)
