"""Tests for components/inputs.py: the styled text fields and dropdowns every screen uses.

Inputs have a rounded grey outline that gets thicker, keeping its colour, when
the field is focused. It is set through Flet 1.0's `border` property; the older
border_radius / border_color / border_width properties are removed in Flet 1.3.
"""

import flet as ft
import pytest
from conftest import find_controls

from components.inputs import account_selector, rounded_dropdown, rounded_text_field
from views import onboarding_view

GREY = ft.Colors.with_opacity(0.40, ft.Colors.GREY)
LEGACY_BORDER_PROPS = ("border_radius", "border_color", "border_width", "focused_border_color", "focused_border_width")


def _sides(control):
    """(colour, width) of the control's outline normally and when focused, plus the corner radius."""
    border = control.border
    default, focused = border[ft.ControlState.DEFAULT], border[ft.ControlState.FOCUSED]
    return (default.side.color, default.side.width), (focused.side.color, focused.side.width), default.border_radius


@pytest.mark.parametrize("make", [rounded_text_field, rounded_dropdown], ids=["text field", "dropdown"])
def test_rounded_inputs_have_a_grey_outline_thicker_when_focused(make):
    """Rounded corners (15), a light grey outline, and the same grey twice as thick on focus."""
    control = make(label="Amount")

    assert _sides(control) == ((GREY, 1), (GREY, 2), 15)
    assert control.label == "Amount"
    assert all(getattr(control, prop) is None for prop in LEGACY_BORDER_PROPS)


def test_rounded_dropdown_also_rounds_its_menu():
    """The list that opens from the dropdown has the same rounded corners."""
    assert rounded_dropdown().menu_style.shape.radius == 15


def test_account_selector_lists_the_accounts_after_the_optional_all_entry(state):
    """The selector offers an "all accounts" entry first when asked, then every account, and starts on `value`."""
    with_all = account_selector(state, "overview", on_select=None, all_option=("overview", "All Accounts"))
    without = account_selector(state, None, on_select=None, hint_text="Select account")

    assert [(o.key, o.text) for o in with_all.options] == [("overview", "All Accounts"), ("1", "Test Broker")]
    assert with_all.value == "overview"
    assert [o.key for o in without.options] == ["1"]
    assert without.hint_text == "Select account"


def test_account_selector_is_filled_with_a_thick_outline_in_the_same_colour(state):
    """The header selector is filled and outlined in the secondary container colour, 2.5 wide even when focused."""
    selector = account_selector(state, None, on_select=None)

    colour = ft.Colors.SECONDARY_CONTAINER
    assert _sides(selector) == ((colour, 2.5), (colour, 2.5), 15)
    assert selector.bgcolor == colour
    assert all(getattr(selector, prop) is None for prop in LEGACY_BORDER_PROPS)
