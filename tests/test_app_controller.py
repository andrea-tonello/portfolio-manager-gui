"""Tests for AppController (app_controller.py): the app's top-level navigation.

Screens receive the controller and ask it to restart, show a tab, re-render
the current one or open Settings, instead of reaching into page.data or
importing navigation functions from the views package.
"""

import asyncio
import os
from datetime import date
from types import SimpleNamespace

import flet as ft
import pytest
from conftest import find_controls
from test_errors import FakeImportPicker
from test_ledger_snapshots import _replay, deposit

from app_controller import AppController
from components.dialogs import show_user_manager
from services import config_service
from views import onboarding_view
from utils.translator import Translator
from views.analysis_view import AnalysisView
from views.home_view import HomeView
from views.operations_view import OperationsView
from views.settings_view import SettingsView
from views.transactions_view import TransactionsView

# The setup steps saved so far, as {file inside config/: text}, and the screen restart must show next.
LANGUAGE = {"config.ini": "[Language]\ncode = en\n"}
USER = {"config.ini": "[Language]\ncode = en\n[Users]\n1 = Ann\n[Active]\nuser = 1\n"}
ACCOUNTS = {**USER, "users/Ann/config.ini": "[Brokers]\n1 = Main\n"}


def _write(base, files):
    """Write `files` ({path inside config/: text}) under base/config."""
    for name, text in files.items():
        path = base / "config" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)


def _shown(page):
    """Name the screen the page shows: one of the four first-launch screens, or the tabs."""
    if page.navigation_bar is not None:
        return f"tab {page.navigation_bar.selected_index}"
    screen = page.controls[0]
    if next(find_controls(screen, ft.Dropdown), None) is not None:
        return "language picker"
    if ft.Icons.ARCHIVE in [icon.icon for icon in find_controls(screen, ft.Icon)]:
        return "backup import"
    label = next(find_controls(screen, ft.TextField)).label
    return {"Your username...": "user creation", "Add account...": "account setup"}[label]


@pytest.mark.parametrize("saved, expected", [
    ({}, "language picker"),
    (LANGUAGE, "backup import"),
    (USER, "account setup"),
    (ACCOUNTS, "tab 0"),
], ids=["nothing", "language", "user", "accounts"])
def test_restart_continues_the_setup_where_it_stopped(tmp_path, page, saved, expected):
    """restart loads the saved settings and shows the first setup step still missing, or Home once setup is complete."""
    _write(tmp_path, saved)
    app = AppController(page, base_path=str(tmp_path))

    app.restart()

    assert _shown(page) == expected
    assert app.state.base_path == str(tmp_path)


def test_restart_moves_an_account_from_before_the_journal_to_it_before_home(tmp_path, page, fake_market):
    """An account saved before the journal (its CSV alone, under its old name) gets its journal, then Home is shown.

    Until it has one, nothing can be recorded in it: this runs at every
    start until it succeeds, before Home. The old CSV is kept as a copy.
    """
    _write(tmp_path, ACCOUNTS)
    resources = tmp_path / "config" / "users" / "Ann" / "resources"
    resources.mkdir(parents=True)
    _replay([deposit(date(2024, 1, 2), 1000)], tmp_path / "recorded").assign(account="Main").to_csv(
        resources / "Report Main.csv", index=False)
    page.run_thread = lambda fn, *args: fn(*args)
    app = AppController(page, base_path=str(tmp_path))

    app.restart()

    assert _shown(page) == "tab 0"
    assert [op.kind for op in app.state.get_account(1).journal] == ["deposit"]
    assert sorted(os.listdir(resources)) == ["before-journal-Main.csv", "journal-Main.json", "report-Main.csv"]


def test_choosing_a_language_moves_on_to_the_backup_import_in_that_language(tmp_path, page):
    """On first launch, applying a language saves it and restarts into the backup-import screen, translated."""
    app = AppController(page, base_path=str(tmp_path))
    app.restart()
    screen = page.controls[0]
    next(find_controls(screen, ft.Dropdown)).value = "it"

    next(find_controls(screen, ft.FilledButton)).on_click(None)

    assert _shown(page) == "backup import"
    title = Translator("it").get("onboarding.import_title")
    assert title in [text.value for text in find_controls(page.controls[0], ft.Text)]


def test_skipping_the_backup_import_moves_on_to_user_creation(tmp_path, page):
    """"No, proceed with setup" continues the usual setup: the user screen, then the account screen."""
    _write(tmp_path, LANGUAGE)
    app = AppController(page, base_path=str(tmp_path))
    app.restart()

    next(find_controls(page.controls[0], ft.FilledButton)).on_click(None)

    assert _shown(page) == "user creation"


def test_importing_a_backup_on_first_launch_skips_the_rest_of_the_setup(tmp_path, page, state, monkeypatch):
    """Restoring a backup from the import screen restarts straight into Home, with the backup's user and accounts."""
    backup = config_service.export_backup(state.config_folder)
    fresh = tmp_path / "fresh"
    _write(fresh, LANGUAGE)
    monkeypatch.setattr(onboarding_view, "get_file_picker", lambda page: FakeImportPicker(backup))
    app = AppController(page, base_path=str(fresh))
    app.restart()

    card = next(find_controls(page.controls[0], ft.Card))
    asyncio.run(card.content.on_click(None))
    page.dialogs[-1].actions[1].on_click(None)  # confirm the import

    assert _shown(page) == "tab 0"
    assert (app.state.active_user_name, app.state.brokers) == ("Tester", {1: "Test Broker"})


def _event(value):
    """A stand-in for the event Flet passes to a dropdown handler, with the chosen `value`."""
    return SimpleNamespace(control=SimpleNamespace(value=value))


@pytest.mark.parametrize("tab, view_cls, handler, value, field, expected", [
    (0, HomeView, "_on_selection_change", "1", "home_selection", "1"),
    (1, OperationsView, "_on_account_selected", "1", "ops_acc_idx", 1),
    (2, AnalysisView, "_on_account_selected", "1", "analysis_acc_idx", 1),
    (3, TransactionsView, "_on_selection_change", "1", "tx_selection", "1"),
], ids=["home", "operations", "analysis", "transactions"])
def test_choosing_an_account_re_renders_the_same_tab(app, page, state, tab, view_cls, handler, value, field, expected):
    """Picking an account in a tab's dropdown stores the choice and shows that same tab again, through app.refresh()."""
    app.show_tab(tab)
    view = view_cls(app)
    view.build()

    getattr(view, handler)(_event(value))

    assert getattr(state, field) == expected
    assert page.navigation_bar.selected_index == tab


def test_leaving_settings_returns_to_the_tab_it_was_opened_from(app, page):
    """Settings opens on top of the tabs; going back rebuilds the tab that was showing, with a fresh drawer."""
    app.show_tab(2)
    drawer = page.end_drawer
    app.show_settings()
    assert page.views[-1].route == "/settings"

    page.on_view_pop(None)

    assert len(page.views) == 1
    assert page.navigation_bar.selected_index == 2
    assert page.end_drawer is not drawer, "the drawer is rebuilt, e.g. to show a new language"


def _restart_with_the_drawer_open(page, app):
    """Restart from Settings, opened over the drawer, as a reset does; return what is left to run, and a list of closes.

    Background work is kept for the test to run after the restart, because on
    a real page it can finish later than the rest of the restart. Each drawer
    closed adds the number of views there are then to the list.
    """
    closes, tasks = [], []

    async def close_end_drawer():
        """Stand-in for closing the drawer, which Flet asks of the view on top."""
        closes.append(len(page.views))

    page.close_end_drawer = close_end_drawer
    page.run_task = lambda fn, *args: tasks.append(fn)
    app.show_settings()
    app.restart()
    return tasks, closes


def test_a_reset_closes_the_drawer_and_leaves_the_setup_screens_without_one(tmp_path, page):
    """The drawer stays open under Settings. A reset from there mustn't leave it over the language choice.

    Left in place, even closed, a swipe from the screen's edge would still open
    it, with the Settings of a user who no longer exists.
    """
    _write(tmp_path, ACCOUNTS)
    app = AppController(page, base_path=str(tmp_path))
    app.restart()
    config_service.reset_application(app.state.config_folder)

    tasks, closes = _restart_with_the_drawer_open(page, app)
    assert _shown(page) == "language picker"
    for task in tasks:
        asyncio.run(task())

    assert closes == [1], "closed on the first view, which holds it, not on Settings"
    assert page.end_drawer is None
    page.on_resize(None)  # e.g. turning a tablet on the setup screen, with no drawer to resize


def test_changing_user_closes_the_drawer_and_keeps_the_new_one_of_home(tmp_path, page):
    """A restart into Home, e.g. after switching user from the drawer, gives Home a new drawer, closed.

    The old one is closed later than Home is shown, and that mustn't take away the new one.
    """
    _write(tmp_path, ACCOUNTS)
    app = AppController(page, base_path=str(tmp_path))
    app.restart()
    old_drawer = page.end_drawer

    tasks, closes = _restart_with_the_drawer_open(page, app)
    new_drawer = page.end_drawer
    for task in tasks:
        asyncio.run(task())

    assert closes == [1]
    assert new_drawer is not old_drawer
    assert page.end_drawer is new_drawer


def test_adding_a_user_removes_the_drawer_until_home_is_back(tmp_path, page):
    """The user-creation screen has no drawer, and giving up on it returns to Home with a new one.

    Left in place, a swipe from the screen's edge would open it over that
    screen, with Settings and the rest of the menu a step away.
    """
    _write(tmp_path, ACCOUNTS)
    app = AppController(page, base_path=str(tmp_path))
    app.restart()

    async def close_end_drawer():
        """Stand-in for closing the drawer, which the "+" button does first."""

    page.close_end_drawer = close_end_drawer
    page.run_task = lambda fn, *args: asyncio.run(fn(*args))
    show_user_manager(app)

    page.dialogs[-1].actions[0].on_click(None)  # "+": add a user

    assert _shown(page) == "user creation"
    assert page.end_drawer is None
    page.on_resize(None)  # e.g. turning a tablet on this screen, with no drawer to resize

    next(find_controls(page.controls[0], ft.IconButton)).on_click(None)  # close the screen

    assert _shown(page) == "tab 0"
    assert page.end_drawer is not None


def test_the_drawer_rebuilt_after_settings_still_leaves_room_for_the_status_bar(page, state):
    """The drawer's column is the page minus the status bar, also when rebuilt on leaving Settings.

    Flet reports the status bar's height (page.media.padding.top) only until a
    screen with an app bar is shown; after that it reports 0. The drawer
    rebuilt on the way back from Settings was then 45 px too tall on a phone
    with a 45 px status bar: it scrolled, and its logo and version sat too low.
    """
    page.media.padding = ft.Padding.only(top=45)  # as at launch, before any app bar is shown
    app = AppController(page, base_path=state.base_path)
    app.state = state
    app.show_tab(0)
    page.media.padding = ft.Padding.zero()  # what Flet reports once the tabs' app bar is on screen
    app.show_settings()

    page.on_view_pop(None)

    assert page.end_drawer.controls[0].height == page.height - 45


def test_changing_language_in_settings_shows_settings_again_translated(app, page, state):
    """After a language change Settings is rebuilt in the new language, replacing the old Settings page."""
    app.show_tab(0)
    app.show_settings()
    view = SettingsView(app)
    view.build()

    view._on_language_change(_event("it"))

    assert [v.route for v in page.views] == ["/", "/settings"]
    assert page.views[-1].appbar.title.value == "Impostazioni"


def test_translator_longer_text_falls_back_to_english(tmp_path):
    """A longer text (<name>_<language>.txt) missing in the user's language is read in English; missing in both, None."""
    (tmp_path / "both_it.txt").write_text("In italiano", encoding="utf-8")
    (tmp_path / "both_en.txt").write_text("In English", encoding="utf-8")
    (tmp_path / "english_only_en.txt").write_text("Only in English", encoding="utf-8")
    t = Translator("it", locales_dir=str(tmp_path))

    assert t.load_text("both") == "In italiano"
    assert t.load_text("english_only") == "Only in English"
    assert t.load_text("nowhere") is None
