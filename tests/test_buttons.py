"""Tests for the shared buttons (components/buttons.py)."""

import flet as ft

from components.buttons import pill_btn


def test_a_coloured_pill_still_greys_out_when_disabled():
    """A pill given its own colours keeps them for normal use only, with greys for when it is disabled.

    A colour set plainly on a Flet button shows in every state, so a red
    "Delete" would stay red while it can't be tapped. A pill without colours
    sets none, leaving both looks to the theme.
    """
    red = pill_btn("Delete", None, bgcolor=ft.Colors.RED, color=ft.Colors.WHITE).style
    plain = pill_btn("Confirm", None).style

    assert red.bgcolor[ft.ControlState.DEFAULT] == ft.Colors.RED
    assert red.color[ft.ControlState.DEFAULT] == ft.Colors.WHITE
    assert red.bgcolor[ft.ControlState.DISABLED] not in (None, ft.Colors.RED)
    assert red.color[ft.ControlState.DISABLED] not in (None, ft.Colors.WHITE)
    assert (plain.bgcolor, plain.color) == (None, None)
