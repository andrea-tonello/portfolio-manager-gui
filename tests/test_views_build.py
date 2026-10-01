"""Smoke tests: every screen of the app can be built without errors.

They build the four tabs through the real navigation code (app bar, drawer,
navigation bar included), the Settings page and every dialog, using a real
account (the `state` fixture) and a stand-in for Flet's Page (the `page`
fixture), both in conftest.py. Nothing is drawn on screen: the point is to
catch Flet API mistakes (a removed control, a renamed argument, a deprecated
helper) as soon as a screen is built, e.g. after upgrading Flet. With the
pyproject.toml warning filter, any Flet deprecation fails the test.
"""

import pytest

from utils.dialogs import show_contacts, show_privacy_policy, show_user_manager
from views import _rebuild_page, _show_glossary, _show_settings
from views.operations_view import OperationsView

TABS = {0: "Home", 1: "Operations", 2: "Analysis", 3: "Transactions"}


@pytest.mark.parametrize("selection", ["overview", "1"])
@pytest.mark.parametrize("tab", TABS, ids=TABS.values())
def test_tab_builds(tab, selection, page, state):
    """Each tab builds, both for all accounts together and for a single account."""
    state.home_selection = state.tx_selection = selection
    state.ops_acc_idx = 1
    state.analysis_acc_idx = None if selection == "overview" else 1

    _rebuild_page(page, state, selected_index=tab)

    assert page.controls, "the tab should put its content on the page"
    assert page.appbar is not None and page.navigation_bar is not None
    assert page.end_drawer is not None


def test_switching_tabs_reuses_the_page(page, state):
    """Moving between tabs after the first build (the path taken on every tap) also works."""
    for tab in [0, 1, 2, 3, 0]:
        _rebuild_page(page, state, selected_index=tab)
    assert page.navigation_bar.selected_index == 0


def test_settings_page_builds(page, state):
    """The Settings page opens as a pushed view on top of the tabs."""
    _rebuild_page(page, state, selected_index=0)

    _show_settings(page, state)

    assert page.views[-1].route == "/settings"


@pytest.mark.parametrize("glossary_page", range(1, 7))
def test_glossary_dialogs_build(glossary_page, page, state):
    """Each Info-button glossary page (1-6) builds its dialog."""
    _show_glossary(page, state, glossary_page)
    assert len(page.dialogs) == 1


@pytest.mark.parametrize("show", [show_user_manager, show_privacy_policy, show_contacts],
                         ids=["user manager", "privacy policy", "contacts"])
def test_drawer_dialogs_build(show, page, state):
    """The dialogs opened from the side drawer build."""
    show(page, state)
    assert len(page.dialogs) == 1


@pytest.mark.parametrize("screen", ["_show_language_picker", "_show_user_creation", "_show_broker_onboarding"])
def test_first_launch_screens_build(screen, page, state):
    """The first-launch screens in main.py (language, user name, accounts) build."""
    import main  # imported here: main.py only starts the app when run directly

    getattr(main, screen)(page, state)

    assert page.controls, "the screen should put its content on the page"


@pytest.mark.parametrize("method", ["_show_ticker_help", "_show_ter_help", "_show_tax_help",
                                    "_show_fee_help", "_show_split_help", "_show_split_ratio_help"])
def test_operations_help_dialogs_build(method, page, state):
    """Every "?" help dialog in the Operations tab builds."""
    view = OperationsView(page, state)
    view.build()

    getattr(view, method)(None)

    assert len(page.dialogs) == 1
