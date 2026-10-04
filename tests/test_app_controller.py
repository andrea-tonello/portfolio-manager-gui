"""Tests for AppController (app_controller.py): the app's top-level navigation.

Screens receive the controller and ask it to restart, show a tab, re-render
the current one or open Settings, instead of reaching into page.data or
importing navigation functions from the views package.
"""

from types import SimpleNamespace

import flet as ft
import pytest
from conftest import find_controls

from app_controller import AppController
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
    """Name the screen the page shows: one of the three first-launch screens, or the tabs."""
    if page.navigation_bar is not None:
        return f"tab {page.navigation_bar.selected_index}"
    screen = page.controls[0]
    if next(find_controls(screen, ft.Dropdown), None) is not None:
        return "language picker"
    label = next(find_controls(screen, ft.TextField)).label
    return {"Your username...": "user creation", "Add account...": "account setup"}[label]


@pytest.mark.parametrize("saved, expected", [
    ({}, "language picker"),
    (LANGUAGE, "user creation"),
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


def test_choosing_a_language_moves_on_to_user_creation_in_that_language(tmp_path, page):
    """On first launch, applying a language saves it and restarts into the user-creation screen, translated."""
    app = AppController(page, base_path=str(tmp_path))
    app.restart()
    screen = page.controls[0]
    next(find_controls(screen, ft.Dropdown)).value = "it"

    next(find_controls(screen, ft.FilledButton)).on_click(None)

    assert next(find_controls(page.controls[0], ft.TextField)).label == "Il tuo nome utente..."


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


def test_changing_language_in_settings_shows_settings_again_translated(app, page, state):
    """After a language change Settings is rebuilt in the new language, replacing the old Settings page."""
    app.show_tab(0)
    app.show_settings()
    view = SettingsView(app)
    view.build()

    view._on_language_change(_event("it"))

    assert [v.route for v in page.views] == ["/", "/settings"]
    assert page.views[-1].appbar.title.value == "Impostazioni"


def test_translator_section_returns_a_group_of_messages():
    """Translator.section gives the messages under a key as a dict, or {} for a key that doesn't exist."""
    t = Translator("en")

    assert t.section("glossary.page_1")["title"]
    assert t.section("glossary.no_such_page") == {}
