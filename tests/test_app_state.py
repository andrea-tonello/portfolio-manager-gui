"""Tests for the AppState methods that change accounts, brokers and users.

Screens call these instead of editing AppState's fields themselves, so each
change happens in one place, together with what must follow it: saving the
files, and forgetting Home's cached values when an account changes.
"""

import asyncio
import configparser
import os

import flet as ft
import pandas as pd
import pytest

import main
from domain.errors import ValidationError
from services import account_service
from utils.dialogs import show_user_manager
from views.home_view import HomeView
from views.settings_view import SettingsView

STALE_CACHE = {"selection": "overview", "nav_str": "1.00€"}


def read_section(folder, section):
    """Return the entries of `section` in folder/config.ini as a dict, e.g. {"1": "Fineco"}."""
    config = configparser.ConfigParser()
    config.read(f"{folder}/config.ini")
    return dict(config.items(section)) if config.has_section(section) else {}


# ── commit ───────────────────────────────────────────────────────────

def test_commit_stores_and_saves_the_new_ledger(state):
    """commit makes the new ledger the account's, and writes it to the account's CSV."""
    account = state.get_account(1)
    new_df = account.df.iloc[:-1]

    state.commit(1, new_df)

    assert state.get_account(1).df is new_df
    assert len(pd.read_csv(account.path)) == len(new_df)


def test_commit_makes_home_fetch_fresh_values(state, page, monkeypatch):
    """After a commit, Home recomputes its totals instead of showing the cached ones from before.

    It used to keep showing the old NAV and P&L until the user tapped refresh
    (REFACTORING.md, Appendix A item 1).
    """
    state.home_cache = dict(STALE_CACHE)
    state.commit(1, state.get_account(1).df.iloc[:-1])
    fetched = []
    monkeypatch.setattr(HomeView, "_fetch_live_values", lambda self: fetched.append(True))
    monkeypatch.setattr(HomeView, "_restore_from_cache", lambda self, cache: pytest.fail("used stale cache"))

    HomeView(page, state).build()

    assert fetched == [True]


# ── add_broker ───────────────────────────────────────────────────────

def test_add_broker_saves_it_and_creates_its_account(state):
    """A new broker gets the next number, is written to config.ini, and has an account with an opening row."""
    idx = state.add_broker("  Directa ")

    assert idx == 2
    assert state.brokers == {1: "Test Broker", 2: "Directa"}
    assert read_section(state.user_config_folder, "Brokers") == {"1": "Test Broker", "2": "Directa"}
    assert len(state.get_account(2).df) == 1


@pytest.mark.parametrize("name", ["Test Broker", "test broker", " TEST BROKER "])
def test_a_broker_name_already_in_use_is_refused(state, name):
    """Names differing only in capitals or spaces count as the same: their CSVs would collide on Windows and macOS.

    Duplicates used to be accepted, so two accounts shared one CSV
    (REFACTORING.md, Appendix A item 3).
    """
    with pytest.raises(ValidationError) as info:
        state.add_broker(name)

    assert info.value.key == "settings.account.duplicate"
    assert state.brokers == {1: "Test Broker"}


def test_an_empty_broker_name_is_refused(state):
    """A blank name is a mistake in the calling screen, which must check it first."""
    with pytest.raises(ValueError):
        state.add_broker("   ")


# ── remove_broker ────────────────────────────────────────────────────

def test_remove_broker_deletes_it_everywhere(state):
    """The broker leaves config.ini, its CSV is deleted, its account is unloaded, and Home's cache is cleared."""
    idx = state.add_broker("Directa")
    path = account_service.report_path(state.config_res_folder, "Directa")
    state.home_cache = dict(STALE_CACHE)

    state.remove_broker(idx)

    assert state.brokers == {1: "Test Broker"}
    assert read_section(state.user_config_folder, "Brokers") == {"1": "Test Broker"}
    assert idx not in state.accounts
    assert not os.path.exists(path)
    assert state.home_cache is None


def test_screens_showing_the_removed_account_go_back_to_their_default(state):
    """Selections pointing at the removed account reset; others are kept."""
    idx = state.add_broker("Directa")
    state.ops_acc_idx = idx
    state.analysis_acc_idx = idx
    state.home_selection = str(idx)
    state.tx_selection = "1"

    state.remove_broker(idx)

    assert (state.ops_acc_idx, state.analysis_acc_idx, state.home_selection) == (None, None, "overview")
    assert state.tx_selection == "1"


# ── add_user ─────────────────────────────────────────────────────────

def test_add_user_saves_it_and_makes_it_active(state):
    """A new user gets the next number, becomes the active user and has its own folders."""
    idx = state.add_user(" Bob ")

    assert idx == 2
    assert state.users == {1: "Tester", 2: "Bob"}
    assert (state.active_user_idx, state.active_user_name) == (2, "Bob")
    assert (state.brokers, state.accounts) == ({}, {}), "the previous user's accounts must not stay loaded"
    assert os.path.isdir(state.config_res_folder)


def test_a_user_name_already_in_use_is_refused(state):
    """Names differing only in capitals or spaces count as the same, since each user has a folder named after them."""
    with pytest.raises(ValidationError) as info:
        state.add_user(" tester")

    assert info.value.key == "settings.user_mgmt.duplicate"
    assert state.users == {1: "Tester"}


# ── switch_user / remove_user ────────────────────────────────────────

def test_switch_user_loads_the_other_users_settings_and_accounts(state):
    """Switching saves the choice in config.ini and loads that user's brokers and accounts; Home's cache is cleared."""
    state.add_user("Bob")
    state.add_broker("Directa")
    state.home_cache = dict(STALE_CACHE)

    state.switch_user(1)

    assert read_section(state.config_folder, "Active") == {"user": "1"}
    assert (state.active_user_name, state.brokers) == ("Tester", {1: "Test Broker"})
    assert list(state.accounts) == [1]
    assert state.home_cache is None


def test_remove_user_deletes_their_folder_and_entry(state):
    """Removing another user deletes their folder (settings and CSVs) and their config.ini entry."""
    state.add_user("Bob")
    bob_folder = state.user_config_folder
    state.switch_user(1)

    state.remove_user(2)

    assert state.users == {1: "Tester"}
    assert read_section(state.config_folder, "Users") == {"1": "Tester"}
    assert not os.path.exists(bob_folder)
    assert state.active_user_name == "Tester"


def test_the_active_user_cant_be_removed(state):
    """Removing the active user raises ValueError and changes nothing: switch to another user first."""
    with pytest.raises(ValueError):
        state.remove_user(1)

    assert state.users == {1: "Tester"}
    assert os.path.isdir(state.user_config_folder)


# ── From the screens ─────────────────────────────────────────────────

def _find(control, kind):
    """Yield every control of exactly type `kind` inside `control`, depth first, in screen order."""
    if type(control) is kind:
        yield control
    for child in [getattr(control, "content", None), *(getattr(control, "controls", None) or [])]:
        if isinstance(child, ft.Control):
            yield from _find(child, kind)


def _snack_texts(page):
    """The messages of the snack bars currently on the page."""
    return [c.content.value for c in page.overlay if isinstance(c, ft.SnackBar)]


def test_first_launch_saves_the_accounts_and_refuses_a_duplicate(state, page):
    """On the first-launch account screen, a repeated name is refused, and Confirm saves the others with their CSVs."""
    state.add_user("Bob")  # a new user, still without accounts
    main._show_broker_onboarding(page, state, on_complete=lambda: None)
    screen = page.controls[0]
    field = next(_find(screen, ft.TextField))
    add, confirm = next(_find(screen, ft.Button)), next(_find(screen, ft.FilledButton))

    for name in ["Fineco", "fineco", "Directa"]:
        field.value = name
        add.on_click(None)
    confirm.on_click(None)

    assert _snack_texts(page) == ['An account called "fineco" already exists']
    assert state.brokers == {1: "Fineco", 2: "Directa"}
    assert read_section(state.user_config_folder, "Brokers") == {"1": "Fineco", "2": "Directa"}
    assert set(state.accounts) == {1, 2}


def test_settings_refuses_a_duplicate_account_name(state, page):
    """Adding an account in Settings with a name already in use shows the error and adds nothing."""
    view = SettingsView(page, state)
    view.build()
    view.new_broker_field.value = "test broker"

    view._on_add_broker(None)

    assert _snack_texts(page) == ['An account called "test broker" already exists']
    assert state.brokers == {1: "Test Broker"}


def test_user_creation_refuses_a_name_already_in_use(state, page):
    """The user-creation screen shows an error for a name already in use and adds nothing."""
    main._show_user_creation(page, state)
    screen = page.controls[0]
    next(_find(screen, ft.TextField)).value = "tester"

    next(_find(screen, ft.FilledButton)).on_click(None)

    assert _snack_texts(page) == ["Username already exists"]
    assert state.users == {1: "Tester"}


def test_user_manager_deletes_another_user(state, page):
    """In the user manager, tapping delete on another user and confirming removes them; the list reopens."""
    state.add_user("Bob")
    bob_folder = state.user_config_folder
    state.switch_user(1)
    show_user_manager(page, state)

    next(_find(page.dialogs[-1].content, ft.IconButton)).on_click(None)  # Bob's delete button
    page.dialogs[-1].actions[1].on_click(None)                             # confirm "Delete user"

    assert state.users == {1: "Tester"}
    assert not os.path.exists(bob_folder)
    assert len(page.dialogs) == 1, "the user manager should be open again"


def test_cancelling_the_new_users_accounts_removes_the_new_user(state, page, monkeypatch):
    """Adding a user and then closing their first-launch account screen deletes that user and goes back to the previous one.

    Drives the real flow: user manager → "+" → user creation → account screen → close.
    """
    restarts = []
    page.data = {
        "restart": lambda: restarts.append(True),
        "show_user_creation": main._show_user_creation,
        "show_broker_onboarding": main._show_broker_onboarding,
    }

    async def close_end_drawer():
        """Stand-in for closing the side drawer, which the "+" button does first."""

    page.close_end_drawer = close_end_drawer
    monkeypatch.setattr(page, "run_task", lambda fn, *args: asyncio.run(fn(*args)))
    show_user_manager(page, state)

    page.dialogs[-1].actions[0].on_click(None)                    # "+": add a user
    next(_find(page.controls[0], ft.TextField)).value = "Bob"
    next(_find(page.controls[0], ft.FilledButton)).on_click(None)  # confirm the name
    created_folder = state.user_config_folder
    next(_find(page.controls[0], ft.IconButton)).on_click(None)    # close the account screen

    assert state.users == {1: "Tester"}
    assert (state.active_user_idx, state.active_user_name) == (1, "Tester")
    assert read_section(state.config_folder, "Active") == {"user": "1"}
    assert not os.path.exists(created_folder)
    assert restarts == [True]
