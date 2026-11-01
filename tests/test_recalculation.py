"""Tests for recalculating the history: every ledger rebuilt from its journal with the app's current rules.

A ledger is only rebuilt from where its journal changes, so values computed
by older rules stay until the history is recalculated: from Settings, or
offered at start when the rules version (domain/rules.py) is newer than the
one the user's accounts were last recalculated with. Here a value "computed
by older rules" is a stored one changed by hand: its row's fingerprint still
matches, so nothing else would ever rebuild it.
"""

from datetime import date

import pandas as pd
import pytest
from conftest import account_of, snack_texts
from test_ledger_snapshots import BROKER, STOCKS_EUR, deposit, journal_of, sell

from components.recalculation import offer_recalculation, recalculate_history
from components.snack import error_message
from domain import rules
from domain.account import Account
from domain.errors import ValidationError
from domain.ledger import opening_ledger
from services import account_service, config_service, market_data, recalculation_service
from services.migration_service import Difference

SALE = 4  # STOCKS_EUR's row of the sale of 01-03-2024, taxed 31.72 (row 0 is the opening row)


def _as_older_rules_left_it(account):
    """Give the sale of 01-03-2024 the tax older rules might have computed: 30 instead of 31.72."""
    account.df.loc[SALE, "tax"] = 30.0


def test_a_recalculation_rebuilds_every_row_and_lists_what_changed(fake_market, monkeypatch):
    """Every account is rebuilt from its first operation, with one download of prices for all.

    The tax older rules left on the sale is computed again, and listed as
    the one value changing: the valuations, re-priced, aren't compared.
    """
    accounts = {1: account_of(1, BROKER, STOCKS_EUR), 2: account_of(2, "Directa", [deposit(date(2024, 1, 2), 100)])}
    _as_older_rules_left_it(accounts[1])
    downloads = []
    download_closes = market_data.download_closes
    monkeypatch.setattr(market_data, "download_closes",
                        lambda *args, **kwargs: downloads.append(args) or download_closes(*args, **kwargs))

    changes = recalculation_service.recalculate(accounts)

    assert changes[1][1].loc[SALE, "tax"] == pytest.approx(31.72)
    assert recalculation_service.differences(accounts, changes) == {
        1: [Difference("01-03-2024", "Sell", "AAA.MI", "tax", 30.0, pytest.approx(31.72))]}
    assert len(downloads) == 1


def test_an_operation_the_current_rules_refuse_names_its_account(fake_market, translator):
    """A journal whose sale the rules refuse (more shares than held) can't be recalculated, and the message says which account.

    Nothing is recalculated: the error comes before anything is returned.
    """
    journal = journal_of([deposit(date(2024, 1, 2), 1_000), sell(date(2024, 1, 3), "AAA.MI", 5, price=100.0, fee=0.0)])
    accounts = {1: Account(1, BROKER, "", opening_ledger(BROKER), journal=journal)}

    with pytest.raises(ValidationError) as refused:
        recalculation_service.recalculate(accounts)

    assert error_message(translator, refused.value).startswith(
        "Test Broker can't be recalculated: The sale of AAA.MI on 03-01-2024 would no longer be possible")


def _sale_tax_in(path):
    """The tax stored on the sale of 01-03-2024 in the ledger file at `path`."""
    return pd.read_csv(path).loc[SALE, "tax"]


@pytest.fixture
def newer_rules(monkeypatch):
    """Make the app's rules version 2, its change described by an existing sentence ("History recalculated")."""
    monkeypatch.setattr(rules, "RULES_VERSION", 2)
    monkeypatch.setattr(rules, "RULES_CHANGES", {2: "journal.recalculate.done"})


def test_saving_keeps_the_ledger_it_replaces_and_notes_the_current_rules(state, newer_rules):
    """Saved, the ledger whose tax changed is kept as before-recalculation-<account>.csv, and the rules version becomes the app's.

    The ledger kept is the one in memory, which the recalculation replaced
    (the file may be older). Unless an account couldn't be loaded: it
    wasn't recalculated, so the version stays and the recalculation is
    offered again.
    """
    account = state.get_account(1)
    _as_older_rules_left_it(account)  # in memory only: the file still says 31.72
    kept = account_service.before_recalculation_path(state.config_res_folder, account.name)

    state.brokers[9] = "Not Loaded"
    state.commit_recalculation(recalculation_service.recalculate(state.accounts))

    assert (_sale_tax_in(kept), _sale_tax_in(account.path)) == (30.0, pytest.approx(31.72))
    assert config_service.load_rules_version(state.user_config_folder) == 1
    del state.brokers[9]
    state.commit_recalculation(recalculation_service.recalculate(state.accounts))
    assert config_service.load_rules_version(state.user_config_folder) == 2


def _disk_full(*args):
    """Stand-in for account_service.save_accounts failing as on a full disk, before anything is saved."""
    raise OSError("disk full")


def test_the_ledger_kept_is_only_replaced_by_one_a_saved_recalculation_changed(state, monkeypatch):
    """The copy holding the values from before a rule change stays through a recalculation that changes nothing, or fails.

    Replaced then, it would hold values the new rules computed already, and
    the old ones would be lost.
    """
    account = state.get_account(1)
    _as_older_rules_left_it(account)
    state.commit_recalculation(recalculation_service.recalculate(state.accounts))  # keeps the 30.0
    kept = account_service.before_recalculation_path(state.config_res_folder, account.name)

    state.commit_recalculation(recalculation_service.recalculate(state.accounts))  # nothing changes
    _as_older_rules_left_it(account)
    monkeypatch.setattr(account_service, "save_accounts", _disk_full)
    with pytest.raises(OSError):
        state.commit_recalculation(recalculation_service.recalculate(state.accounts))

    assert _sale_tax_in(kept) == 30.0


def test_recalculating_from_settings_asks_lists_and_saves(app, page, state, immediately):
    """Settings' Recalculate asks first, then lists the changed tax, and saves once the user agrees.

    A dialog says the recalculation is under way meanwhile, and closes when it is done.
    """
    _as_older_rules_left_it(state.get_account(1))

    recalculate_history(app)
    assert page.dialogs[-1].title.value == "Recalculate history?"
    page.dialogs[-1].actions[1].on_click(None)  # Recalculate
    working, listed = page.dialogs[-2:]
    assert not working.open
    assert "01-03-2024 · Sell AAA.MI · Tax: 30.0 → 31.72" in listed.content.content.value
    listed.actions[1].on_click(None)  # Save

    assert snack_texts(page) == ["History recalculated"]
    assert state.get_account(1).df.loc[SALE, "tax"] == pytest.approx(31.72)


def test_after_an_update_changing_the_rules_the_start_offers_to_recalculate(app, page, state, immediately, newer_rules):
    """Accounts last recalculated with rules 1, the app at 2: the start offers it, listing what changed.

    "Later" leaves the rules noted as they were, so the next start offers it
    again; recalculated, they are noted as 2, and nothing is offered after.
    The texts around the list keep their line breaks: only the list is Markdown.
    """
    offer_recalculation(app)
    offer = page.dialogs[-1]
    assert (offer.title.value, offer.actions[0].content) == ("Calculations updated", "Later")
    texts = offer.content.content.controls
    assert [type(text).__name__ for text in texts] == ["Text", "Markdown", "Text"]
    assert texts[1].value == "- History recalculated"
    offer.actions[0].on_click(None)  # Later
    assert config_service.load_rules_version(state.user_config_folder) == 1

    offer_recalculation(app)
    page.dialogs[-1].actions[1].on_click(None)  # Recalculate: nothing changed, so saved at once

    assert config_service.load_rules_version(state.user_config_folder) == 2
    offered = len(page.dialogs)
    offer_recalculation(app)
    assert len(page.dialogs) == offered


def test_an_offer_accepted_while_another_change_saves_comes_back(app, page, state, immediately, newer_rules):
    """Accepted while e.g. a split found on Yahoo is being recorded, the offer says so and is made again, not dropped.

    Dropped, it would only come back at the next start.
    """
    offer_recalculation(app)
    state.changing = True  # another change is under way

    page.dialogs[-1].actions[1].on_click(None)  # Recalculate

    assert snack_texts(page) == ["Another change is being saved: try again in a moment."]
    assert page.dialogs[-1].open and page.dialogs[-1].title.value == "Calculations updated"


def test_nothing_is_offered_to_a_user_whose_accounts_have_no_operation_or_who_is_new(app, page, state, immediately,
                                                                                     newer_rules):
    """A user without operations has nothing to recalculate: the current rules are noted at once, without asking.

    Unless an account couldn't be loaded: it may hold operations, so the
    rules aren't noted. A user created by this version starts with them noted.
    """
    state.get_account(1).journal = []
    state.brokers[9] = "Not Loaded"
    offer_recalculation(app)
    assert config_service.load_rules_version(state.user_config_folder) == 1

    del state.brokers[9]
    offer_recalculation(app)

    assert not page.dialogs
    assert config_service.load_rules_version(state.user_config_folder) == 2
    state.add_user("Newcomer")
    assert config_service.load_rules_version(state.user_config_folder) == 2


def test_a_rules_version_that_isnt_a_whole_number_counts_as_the_first(state):
    """A version typed by hand as "2.0" reads as 1: the start offers the recalculation instead of failing."""
    config_service.save_rules_version(state.user_config_folder, "2.0")

    assert config_service.load_rules_version(state.user_config_folder) == 1
