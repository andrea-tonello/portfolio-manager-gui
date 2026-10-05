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


def apply_theme(page, mode, palette):
    """Give `page` the light/dark `mode` and the colour `palette` (keys of the dicts above).

    Unknown keys fall back to the device's mode and blue. The caller redraws
    the page. Example: apply_theme(page, "dark", "teal") gives a dark page
    whose colours derive from teal.
    """
    page.theme_mode = THEME_MODES.get(mode, ft.ThemeMode.SYSTEM)
    color = PALETTE_COLORS.get(palette, ft.Colors.BLUE)
    page.theme = ft.Theme(color_scheme_seed=color, page_transitions=PAGE_TRANSITIONS)
    page.dark_theme = ft.Theme(color_scheme_seed=color, page_transitions=PAGE_TRANSITIONS)
