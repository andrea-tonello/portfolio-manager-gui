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

from components.focus_chain import scroll_into_view_on_focus


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
