"""Tests for what each of the four tabs shows around its content: navigation bar, app bar, info button.

The tabs are Home, Operations, Analysis and Transactions, in that order.
Analysis and Transactions have a floating info button opening a page of the
glossary (assets/i18n/<language>.json, "glossary"); Analysis opens the page
of the tool currently selected.
"""

import flet as ft
import pytest
from conftest import find_controls

TAB_LABELS = ["Home", "Operations", "Analysis", "Transactions"]


def _info_button(page):
    """The floating info button of the tab shown, or None if it has none."""
    return next(find_controls(page.controls[0], ft.FloatingActionButton), None)


def _glossary_title(state, page_num):
    """The title of glossary page `page_num` in the current language."""
    return state.translator.section(f"glossary.page_{page_num}")["title"]


def test_navigation_bar_lists_the_tabs_in_order(app, page):
    """The bar has one destination per tab, with its label and icons."""
    app.show_tab(0)

    destinations = page.navigation_bar.destinations
    assert [d.label for d in destinations] == TAB_LABELS
    assert [(d.icon, d.selected_icon) for d in destinations] == [
        (ft.Icons.HOME_OUTLINED, ft.Icons.HOME),
        (ft.Icons.SWAP_HORIZ, None),
        (ft.Icons.ANALYTICS_OUTLINED, ft.Icons.ANALYTICS),
        (ft.Icons.RECEIPT_LONG_OUTLINED, ft.Icons.RECEIPT_LONG),
    ]


@pytest.mark.parametrize("tab", range(4), ids=TAB_LABELS)
def test_app_bar_shows_the_user_on_home_and_the_tab_name_elsewhere(app, page, tab):
    """Home's app bar shows the active user's name; the other tabs show their own name."""
    app.show_tab(tab)

    assert page.appbar.title.value == ("Tester" if tab == 0 else TAB_LABELS[tab])


@pytest.mark.parametrize("tab", [0, 1], ids=["Home", "Operations"])
def test_home_and_operations_have_no_info_button(app, page, tab):
    """Only Analysis and Transactions have the floating info button."""
    app.show_tab(tab)

    assert _info_button(page) is None


@pytest.mark.parametrize("analysis_tool, page_num", [(0, 2), (1, 3), (3, 5)])
def test_analysis_info_button_explains_the_selected_tool(app, page, state, analysis_tool, page_num):
    """In Analysis the info button opens the glossary page of the tool shown: tool 0 → page 2, tool 1 → page 3, ..."""
    state.analysis_tab_index = analysis_tool
    app.show_tab(2)

    _info_button(page).on_click(None)

    assert page.dialogs[-1].title.value == _glossary_title(state, page_num)


def test_transactions_info_button_explains_the_columns(app, page, state):
    """In Transactions the info button opens glossary page 1, which explains the table's columns."""
    app.show_tab(3)

    _info_button(page).on_click(None)

    assert page.dialogs[-1].title.value == _glossary_title(state, 1)
