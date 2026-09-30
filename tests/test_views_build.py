"""Smoke tests: every screen of the app can be built without errors.

They build the four tabs through the real navigation code (app bar, drawer,
navigation bar included), the Settings page and every dialog, using a real
account and a small stand-in for Flet's Page. Nothing is drawn on screen: the
point is to catch Flet API mistakes (a removed control, a renamed argument, a
deprecated helper) as soon as a screen is built, e.g. after upgrading Flet.
With the pyproject.toml warning filter, any Flet deprecation fails the test.
"""

import os

import flet as ft
import pytest

from app_state import AppState
from services import config_service
from test_ledger_snapshots import STOCKS_EUR, _replay
from utils.dialogs import show_contacts, show_privacy_policy, show_user_manager
from views import _rebuild_page, _show_glossary, _show_settings
from views.operations_view import OperationsView

TABS = {0: "Home", 1: "Operations", 2: "Analysis", 3: "Transactions"}


class FakePage:
    """Stand-in for ft.Page with the attributes the app's screens use.

    Background work (run_thread / run_task) is recorded but never run, so no
    live prices are fetched; dialogs are collected in `dialogs` instead of shown.
    """

    def __init__(self):
        """Start as an empty page with one root view, like a freshly opened app."""
        self.width = 400
        self.data = {}
        self.views = [ft.View(route="/")]
        self.controls = []
        self.overlay = []
        self.services = []
        self.dialogs = []
        self.appbar = self.navigation_bar = self.end_drawer = None
        self.on_view_pop = self.on_media_change = None
        self.web = False

    def update(self):
        """Do nothing: there is no screen to redraw."""

    def run_thread(self, fn, *args):
        """Ignore background work (it would fetch live prices)."""

    def run_task(self, fn, *args):
        """Ignore async background work."""

    def show_dialog(self, dialog):
        """Record the dialog instead of displaying it."""
        self.dialogs.append(dialog)

    def pop_dialog(self):
        """Close the most recent dialog, if any."""
        if self.dialogs:
            self.dialogs.pop()


@pytest.fixture
def state(tmp_path, translator, fake_market):
    """An AppState for user "Tester" with one account holding the STOCKS_EUR history.

    Built the same way the app stores data: config.ini files for language,
    users and brokers, and the account CSV in the user's resources folder.
    """
    config = str(tmp_path / "config")
    os.makedirs(config)
    config_service.save_language(config, "en")
    config_service.save_users(config, {1: "Tester"})
    config_service.save_active_user(config, 1)
    user_folder = config_service.get_user_folder(config, "Tester")
    resources = config_service.get_user_res_folder(config, "Tester")
    os.makedirs(resources)
    config_service.save_brokers(user_folder, {1: "Test Broker"}, reset=True)
    df = _replay(STOCKS_EUR, translator, tmp_path / "config" / "users" / "Tester" / "resources")
    df.to_csv(os.path.join(resources, "Report Test Broker.csv"), index=False)

    app_state = AppState(base_path=str(tmp_path))
    app_state.load_config()
    app_state.load_all_accounts()
    assert app_state.accounts, "the test account should have loaded"
    return app_state


@pytest.mark.parametrize("selection", ["overview", "1"])
@pytest.mark.parametrize("tab", TABS, ids=TABS.values())
def test_tab_builds(tab, selection, state):
    """Each tab builds, both for all accounts together and for a single account."""
    state.home_selection = state.tx_selection = selection
    state.ops_acc_idx = 1
    state.analysis_acc_idx = None if selection == "overview" else 1
    page = FakePage()

    _rebuild_page(page, state, selected_index=tab)

    assert page.controls, "the tab should put its content on the page"
    assert page.appbar is not None and page.navigation_bar is not None
    assert page.end_drawer is not None


def test_switching_tabs_reuses_the_page(state):
    """Moving between tabs after the first build (the path taken on every tap) also works."""
    page = FakePage()
    for tab in [0, 1, 2, 3, 0]:
        _rebuild_page(page, state, selected_index=tab)
    assert page.navigation_bar.selected_index == 0


def test_settings_page_builds(state):
    """The Settings page opens as a pushed view on top of the tabs."""
    page = FakePage()
    _rebuild_page(page, state, selected_index=0)

    _show_settings(page, state)

    assert page.views[-1].route == "/settings"


@pytest.mark.parametrize("glossary_page", range(1, 7))
def test_glossary_dialogs_build(glossary_page, state):
    """Each Info-button glossary page (1-6) builds its dialog."""
    page = FakePage()
    _show_glossary(page, state, glossary_page)
    assert len(page.dialogs) == 1


@pytest.mark.parametrize("show", [show_user_manager, show_privacy_policy, show_contacts],
                         ids=["user manager", "privacy policy", "contacts"])
def test_drawer_dialogs_build(show, state):
    """The dialogs opened from the side drawer build."""
    page = FakePage()
    show(page, state)
    assert len(page.dialogs) == 1


@pytest.mark.parametrize("screen", ["_show_language_picker", "_show_user_creation", "_show_broker_onboarding"])
def test_first_launch_screens_build(screen, state):
    """The first-launch screens in main.py (language, user name, accounts) build."""
    import main  # imported here: main.py only starts the app when run directly

    page = FakePage()
    getattr(main, screen)(page, state)

    assert page.controls, "the screen should put its content on the page"


@pytest.mark.parametrize("method", ["_show_ticker_help", "_show_ter_help", "_show_tax_help",
                                    "_show_fee_help", "_show_split_help", "_show_split_ratio_help"])
def test_operations_help_dialogs_build(method, state):
    """Every "?" help dialog in the Operations tab builds."""
    page = FakePage()
    view = OperationsView(page, state)
    view.build()

    getattr(view, method)(None)

    assert len(page.dialogs) == 1
