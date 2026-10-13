"""Tests for scrolling a focused input into view (components/focus_chain.py).

On a phone the on-screen keyboard covers the bottom half of the screen, so
when an input gets the focus its column scrolls to bring it into view. Flet
finds the input to scroll to by its key, and only a key of type ft.ScrollKey
is registered for that: with a plain text key, scroll_to silently does nothing.
"""

import asyncio
from types import SimpleNamespace

import flet as ft
import pytest
from conftest import find_controls

from components.focus_chain import scroll_into_view_on_focus, scrolling_form
from views.operations_view import OperationsView


class FakeColumn:
    """Stand-in for a scrollable ft.Column that records the scroll_to calls it receives."""

    def __init__(self):
        """Start with no scroll requests."""
        self.scrolls = []

    async def scroll_to(self, **kwargs):
        """Record the request instead of scrolling."""
        self.scrolls.append(kwargs)


def _focus(field):
    """Simulate the user tapping into `field`, as Flet reports it, and run its focus handler."""
    asyncio.run(field.on_focus(SimpleNamespace(control=field)))


def test_focusing_a_field_scrolls_the_column_to_it():
    """Each field gets its own scroll key; focusing it asks the column to scroll to that key."""
    column = FakeColumn()
    amount, ticker = ft.TextField(), ft.TextField()

    scroll_into_view_on_focus(column, [amount, ticker], prefix="cash")
    _focus(ticker)

    assert amount.key == ft.ScrollKey("cash-0")
    assert ticker.key == ft.ScrollKey("cash-1")
    assert column.scrolls == [{"scroll_key": ft.ScrollKey("cash-1"), "duration": 300}]


def test_a_scrolling_form_starts_at_the_tabs_left_edge():
    """The space left and right of a form sits inside its scrolling column, not around it.

    Flet's scroll_to also slides the swipeable tabs until the scrolling column
    is at their left edge. With the column set 20 px in from the edge, the
    whole tab slid 20 px left and sprang back each time a field was focused.
    """
    form = ft.Column([ft.TextField()])

    tab = scrolling_form(form, form.controls, prefix="cash", padding=20,
                         button=ft.FilledButton("Add"), loading=ft.ProgressRing(width=30))

    scroller = tab.content.controls[0]
    assert scroller.scroll == ft.ScrollMode.AUTO
    assert (tab.padding.left, tab.padding.right) == (0, 0)
    assert (scroller.controls[0].padding.left, scroller.controls[0].content) == (20, form)


def test_a_scrolling_forms_button_stays_below_the_scrolling_column():
    """The button confirming a form isn't part of what scrolls, so it is in view however long the form is."""
    form = ft.Column([ft.TextField()])
    button = ft.FilledButton("Add")

    tab = scrolling_form(form, form.controls, prefix="cash", padding=20,
                         button=button, loading=ft.ProgressRing(width=30))

    scroller, pinned = tab.content.controls
    assert list(find_controls(scroller, ft.FilledButton)) == []
    assert list(find_controls(pinned, ft.FilledButton)) == [button]


def test_done_on_the_keyboard_moves_only_to_fields_that_are_shown(app, state):
    """Pressing Done moves to the next field on screen: the tax bracket after the TER, for a money-market ETF.

    The TER and the tax bracket are hidden on the Stock tab, where nothing
    follows the fee: asking Flet to focus a field that isn't on screen leaves
    the request hanging.
    """
    state.ops_acc_idx = 1
    view = OperationsView(app)
    view.build()
    focused = []
    for form in (view.etf, view.stock):
        for name in ("ter", "tax_bracket"):
            async def focus(form=form, name=name):
                """Stand-in for the field's focus(): record which field was asked for."""
                focused.append((form.product_type, name))
            getattr(form, name).focus = focus
    view.etf.etf_subtype.value = "ETF-M"
    view.etf._on_etf_subtype_change(None)

    asyncio.run(view.etf.ter.on_submit(None))
    asyncio.run(view.stock.fee.on_submit(None))

    assert focused == [("ETF", "tax_bracket")]


@pytest.mark.parametrize("tab, minimum", [(1, 19), (2, 11)], ids=["Operations", "Analysis"])
def test_screen_inputs_have_unique_scroll_keys(app, page, state, tab, minimum):
    """Every input that scrolls into view has an ft.ScrollKey, and no two on the same screen share one.

    Flet keeps one registry of scroll keys for the whole app, so a repeated key
    would make one of the two inputs unreachable.
    """
    state.ops_acc_idx = 1
    app.show_tab(tab)

    keys = [field.key for field in find_controls(page.controls[0], ft.TextField) if field.key is not None]

    assert len(keys) >= minimum
    assert all(isinstance(key, ft.ScrollKey) for key in keys), "plain text keys can't be scrolled to"
    values = [key.value for key in keys]
    assert len(set(values)) == len(values)
