"""Tests for changing the theme (light / dark / device) and the colour palette in Settings.

The app slides every page in the iOS way on all platforms. That is part of the
page's theme, so each theme change must keep it.
"""

import flet as ft
import pytest

from views.settings_view import SettingsView


@pytest.mark.parametrize("button, choice", [("_theme_btn", "dark"), ("_palette_btn", "teal")],
                         ids=["theme", "palette"])
def test_changing_the_theme_keeps_the_page_transitions(app, page, state, button, choice):
    """Picking a theme or a palette applies it to both the light and dark themes, which keep the iOS-style transitions.

    Settings used to rebuild the themes without them, so pages stopped sliding
    in until the app was restarted (REFACTORING.md, Appendix A item 2).
    """
    view = SettingsView(app)
    view.build()

    getattr(view, button).on_click(None)
    choices = page.dialogs[-1].content
    choices.value = choice
    choices.on_change(None)

    assert (state.theme_mode, state.color_seed) == (("dark", "blue") if choice == "dark" else ("system", "teal"))
    assert page.theme_mode == (ft.ThemeMode.DARK if choice == "dark" else ft.ThemeMode.SYSTEM)
    for theme in (page.theme, page.dark_theme):
        assert theme.color_scheme_seed == (ft.Colors.BLUE if choice == "dark" else ft.Colors.TEAL)
        assert theme.page_transitions is not None
        assert theme.page_transitions.android == ft.PageTransitionTheme.CUPERTINO
