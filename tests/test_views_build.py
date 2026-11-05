"""Smoke tests: the tabs and the dialogs of the drawer and of Operations can be built without errors.

They build the four tabs through the real navigation code (app bar, drawer,
navigation bar included) and those dialogs, using a real account (the `state`
fixture), a stand-in for Flet's Page (the `page` fixture) and the
AppController on top of them (the `app` fixture), all in conftest.py. Nothing
is drawn on screen: the point is to catch Flet API mistakes (a removed control,
a renamed argument, a deprecated helper) as soon as a screen is built, e.g.
after upgrading Flet. With the pyproject.toml warning filter, any Flet
deprecation fails the test. The Settings page and the first-launch screens are
built, for the same catch, by test_app_controller.py and test_app_state.py.
"""

import flet as ft
import pytest
from conftest import find_controls

from components.dialogs import show_contacts, show_privacy_policy, show_user_manager
from utils.constants import LANGUAGES
from views.operations_view import OperationsView

TABS = {0: "Home", 1: "Operations", 2: "Analysis", 3: "Transactions"}
# Each tab for all accounts and for one, except Operations: it always works on one account.
TAB_SELECTIONS = [(tab, selection) for tab in TABS for selection in ("overview", "1")
                  if (TABS[tab], selection) != ("Operations", "overview")]


@pytest.mark.parametrize("tab, selection", TAB_SELECTIONS,
                         ids=[f"{TABS[tab]}-{selection}" for tab, selection in TAB_SELECTIONS])
def test_tab_builds(tab, selection, app, page, state):
    """Each tab builds, both for all accounts together and for a single account (Operations: a single one)."""
    state.home_selection = state.tx_selection = selection
    state.ops_acc_idx = 1
    state.analysis_acc_idx = None if selection == "overview" else 1

    app.show_tab(tab)

    assert page.controls, "the tab should put its content on the page"
    assert page.appbar is not None and page.navigation_bar is not None
    assert page.end_drawer is not None


@pytest.mark.parametrize("show", [
    show_user_manager,
    lambda app: show_privacy_policy(app.page, app.state),
    lambda app: show_contacts(app.page, app.state),
], ids=["user manager", "privacy policy", "contacts"])
def test_drawer_dialogs_build(show, app, page):
    """The dialogs opened from the side drawer build."""
    show(app)
    assert len(page.dialogs) == 1


@pytest.mark.parametrize("language", LANGUAGES)
def test_every_operations_help_button_opens_its_explanation(language, app, page, state):
    """Each "?" button in the Operations tab opens a dialog whose title and text are translated.

    A key missing from the translation file shows "<the.key>" on screen instead of
    raising an error, so a mistyped or forgotten key would otherwise go unnoticed.
    """
    state.translator.load_language(language)
    buttons = [b for b in find_controls(OperationsView(app).build(), ft.FilledTonalIconButton)
               if b.icon == ft.Icons.HELP_OUTLINE]
    assert len(buttons) == 11  # 3 in General, 4 each in ETF and Stock

    for button in buttons:
        button.on_click(None)
        dialog = page.dialogs.pop()
        texts = [dialog.title.value] + [c.value for kind in (ft.Text, ft.Markdown)
                                        for c in find_controls(dialog.content, kind)]
        assert len(texts) == 2
        assert all(text and not (text.startswith("<") and text.endswith(">")) for text in texts), texts
