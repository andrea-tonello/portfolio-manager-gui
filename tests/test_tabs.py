"""Tests for what each of the four tabs shows around its content: navigation bar, app bar, info button.

The tabs are Home, Operations, Analysis and Transactions, in that order.
Analysis and Transactions have a floating info button opening a glossary,
assets/i18n/glossary_<name>_<language>.txt: in Analysis, the one of the tool
currently selected; in Transactions, the one describing the table's columns.
"""

from pathlib import Path

import flet as ft
import pytest
from conftest import find_controls

from utils.columns import COLUMNS
from utils.constants import I18N_DIR, LANGUAGES
from views.analysis_view import TOOLS as ANALYSIS_TOOLS

TAB_LABELS = ["Home", "Operations", "Analysis", "Transactions"]


def _info_button(page):
    """The floating info button of the tab shown, or None if it has none."""
    return next(find_controls(page.controls[0], ft.FloatingActionButton), None)


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
def test_app_bar_shows_the_app_name_on_home_and_the_tab_name_elsewhere(app, page, tab):
    """Home's app bar shows the app's name next to its icon; the other tabs show their own name."""
    app.show_tab(tab)

    texts = [text.value for text in find_controls(page.appbar.title, ft.Text)]
    assert texts == ["Portfolio Manager" if tab == 0 else TAB_LABELS[tab]]


@pytest.mark.parametrize("tab", [0, 1], ids=["Home", "Operations"])
def test_home_and_operations_have_no_info_button(app, page, tab):
    """Only Analysis and Transactions have the floating info button."""
    app.show_tab(tab)

    assert _info_button(page) is None


@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.parametrize("tool", ANALYSIS_TOOLS, ids=[tool.glossary for tool in ANALYSIS_TOOLS])
def test_analysis_info_button_explains_the_selected_tool(tool, language, app, page, state):
    """In Analysis the info button explains the tool shown, in the user's language.

    The text must be the tool's own file in that language: one missing would
    otherwise go unnoticed, shown in English instead.
    """
    t = state.translator
    t.load_language(language)
    state.analysis_tab_index = ANALYSIS_TOOLS.index(tool)
    app.show_tab(2)

    _info_button(page).on_click(None)

    dialog = page.dialogs[-1]
    [text] = find_controls(dialog.content, ft.Markdown)
    assert dialog.title.value == t.get(f"glossary.{tool.glossary}_title") and not dialog.title.value.startswith("<")
    assert text.value == (Path(I18N_DIR) / f"glossary_{tool.glossary}_{language}.txt").read_text(encoding="utf-8")


@pytest.mark.parametrize("language", LANGUAGES)
def test_transactions_info_button_explains_every_column(language, app, page, state):
    """In Transactions the info button explains the table's columns, in the user's language, with a heading for each.

    The headings must be the columns' names ("columns" in the locale file): a
    column renamed there but not in glossary_columns_<language>.txt fails here.
    """
    t = state.translator
    t.load_language(language)
    app.show_tab(3)

    _info_button(page).on_click(None)

    dialog = page.dialogs[-1]
    [text] = find_controls(dialog.content, ft.Markdown)
    assert dialog.title.value == t.get("glossary.columns_title")
    missing = [col for col in COLUMNS if f"### {t.get(f'columns.{col}')}\n" not in text.value]
    assert missing == []
