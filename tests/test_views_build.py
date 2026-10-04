"""Smoke tests: every screen of the app can be built without errors.

They build the four tabs through the real navigation code (app bar, drawer,
navigation bar included), the Settings page and every dialog, using a real
account (the `state` fixture), a stand-in for Flet's Page (the `page`
fixture) and the AppController on top of them (the `app` fixture), all in
conftest.py. Nothing is drawn on screen: the point is to catch Flet API
mistakes (a removed control, a renamed argument, a deprecated helper) as soon
as a screen is built, e.g. after upgrading Flet. With the pyproject.toml
warning filter, any Flet deprecation fails the test.
"""

import flet as ft
import pytest
from conftest import find_controls

from components.dialogs import show_contacts, show_privacy_policy, show_user_manager
from utils.constants import LANGUAGES
from views import onboarding_view
from views.operations_view import OperationsView
from views.shell import show_glossary

TABS = {0: "Home", 1: "Operations", 2: "Analysis", 3: "Transactions"}


@pytest.mark.parametrize("selection", ["overview", "1"])
@pytest.mark.parametrize("tab", TABS, ids=TABS.values())
def test_tab_builds(tab, selection, app, page, state):
    """Each tab builds, both for all accounts together and for a single account."""
    state.home_selection = state.tx_selection = selection
    state.ops_acc_idx = 1
    state.analysis_acc_idx = None if selection == "overview" else 1

    app.show_tab(tab)

    assert page.controls, "the tab should put its content on the page"
    assert page.appbar is not None and page.navigation_bar is not None
    assert page.end_drawer is not None


def test_switching_tabs_reuses_the_page(app, page):
    """Moving between tabs after the first build (the path taken on every tap) also works."""
    for tab in [0, 1, 2, 3, 0]:
        app.show_tab(tab)
    assert page.navigation_bar.selected_index == 0


def test_settings_page_builds(app, page):
    """The Settings page opens as a pushed view on top of the tabs."""
    app.show_tab(0)

    app.show_settings()

    assert page.views[-1].route == "/settings"


@pytest.mark.parametrize("glossary_page", range(1, 7))
def test_glossary_dialogs_build(glossary_page, app, page):
    """Each Info-button glossary page (1-6) builds its dialog, with its title."""
    show_glossary(app, glossary_page)

    assert len(page.dialogs) == 1
    assert page.dialogs[0].title.value


@pytest.mark.parametrize("show", [
    show_user_manager,
    lambda app: show_privacy_policy(app.page, app.state),
    lambda app: show_contacts(app.page, app.state),
], ids=["user manager", "privacy policy", "contacts"])
def test_drawer_dialogs_build(show, app, page):
    """The dialogs opened from the side drawer build."""
    show(app)
    assert len(page.dialogs) == 1


@pytest.mark.parametrize("screen", [
    onboarding_view.show_language_picker,
    onboarding_view.show_user_creation,
    onboarding_view.show_broker_onboarding,
], ids=["language", "user", "accounts"])
def test_first_launch_screens_build(screen, app, page):
    """The first-launch screens (language, user name, accounts) build."""
    screen(app)

    assert page.controls, "the screen should put its content on the page"


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


@pytest.mark.parametrize("language", LANGUAGES)
def test_help_texts_are_read_from_their_files(language, app, page, state):
    """The privacy policy and the fee-mode help show the text of their per-language files.

    Both dialogs fall back to a "not available" sentence when the file can't be
    opened, so a wrong path (e.g. after moving the translation folder) would
    otherwise go unnoticed.
    """
    fallbacks = {"Privacy policy not available.", "Fee mode description not available."}
    state.translator.load_language(language)

    show_privacy_policy(page, state)
    OperationsView(app)._show_fee_help(None)

    texts = [dialog.content.content.controls[0].value for dialog in page.dialogs]
    assert len(texts) == 2
    assert not fallbacks & set(texts)
    assert all(texts)
