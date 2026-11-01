"""Tests for moving accounts recorded before the journal to it (services/migration_service.py, components/journal_migration.py).

Each ledger is recorded the old way, row by row, then migrated: it must turn
back into the very operations it was recorded from, and rebuild the same
ledger, even where a row kept a value only rounded.
"""

import os
from datetime import date
from pathlib import Path

import flet as ft
import numpy as np
import pytest
from conftest import FAKE_BASE_PRICES, snack_texts
from test_journal import csv_text
from test_ledger_snapshots import (BROKER, NAMES, SCENARIOS, STOCKS_EUR, _replay, buy, deposit, journal_of, sell, split,
                                   withdrawal)

from components.journal_migration import differences_text, migrate_accounts
from domain import rules
from domain.account import Account
from domain.journal import Operation, operation_to_dict
from domain.ledger import Op, Product
from domain.newrow import newrow_cash, newrow_split
from domain.positions import unrecorded_splits
from services import account_service, config_service, migration_service
from services.migration_service import Difference, migrate


def legacy_account(idx, name, ledger, folder):
    """Save `ledger` as account `name`'s CSV in `folder`, and load it back as the app does: an account without a journal."""
    os.makedirs(folder, exist_ok=True)
    ledger.to_csv(account_service.ledger_path(str(folder), name), index=False)
    return account_service.load_single_account({idx: name}, str(folder), idx)


def migrated(accounts):
    """Return the migrations of `accounts`, by account number, checking that none of them failed."""
    migrations, failures = migrate(accounts)
    assert failures == []
    return migrations


def entered(operations):
    """Return the operations as the journal file stores them, without the ids, which each migration draws anew."""
    return [{k: v for k, v in operation_to_dict(op).items() if k not in ("id", "transfer_id")} for op in operations]


@SCENARIOS
def test_a_ledger_migrates_to_the_operations_it_was_recorded_from(name, steps, tmp_path, fake_market):
    """A scenario recorded row by row, read back from its file, becomes the journal it was recorded from.

    Every value comes back, the fee mode of each ETF trade included, found
    by trying each one: the ETF buy and sale of ETFS_AND_USD in "loss" mode,
    its money-market ETF in "abp". The ledger rebuilt from it is the same.
    """
    ledger = _replay(steps, tmp_path / "recorded")
    account = legacy_account(1, BROKER, ledger, tmp_path / "resources")

    migration = migrated({1: account})[1]

    assert entered(migration.journal) == entered(journal_of(steps))
    assert migration.differences == []
    assert csv_text(migration.ledger) == ledger.to_csv(index=False)


def test_a_price_saved_rounded_is_recovered_from_its_amount(tmp_path, fake_market):
    """A price typed with more than 4 decimals comes back as typed, from the amount the row stores.

    1,000 shares at 100.12345 cost 100,123.45; at the stored 100.1235 they
    would cost 100,123.50, and the 99,874.55 left could no longer all be
    transferred out: rebuilding would refuse the transfer.
    """
    ledger = _replay([deposit(date(2024, 1, 2), 200_000), buy(date(2024, 1, 3), "AAA.MI", 1000, price=100.12345, fee=2.0)],
                     tmp_path / "recorded")
    ledger = newrow_cash(ledger, "04-01-2024", date(2024, 1, 4), BROKER, -99_874.55, Op.TRANSFER_OUT, Product.CASH,
                         np.nan, "Old Broker")

    migration = migrated({1: legacy_account(1, BROKER, ledger, tmp_path / "resources")})[1]

    assert migration.journal[1].price == 100.12345
    assert migration.differences == []


def test_a_split_ratio_saved_rounded_is_recovered(tmp_path, fake_market):
    """A 1:3 reverse split, saved as "0.333333", comes back as 1/3: the 30 shares become 10, and 10 can be sold.

    With 0.333333 they would become 9.99999, and the sale would be refused.
    """
    steps = [deposit(date(2024, 1, 2), 10_000), buy(date(2024, 1, 3), "AAA.MI", 30, price=100.0, fee=2.0),
             split(date(2024, 2, 1), "AAA.MI", 1 / 3), sell(date(2024, 3, 1), "AAA.MI", 10, price=300.0, fee=2.0)]

    migration = migrated({1: legacy_account(1, BROKER, _replay(steps, tmp_path / "recorded"), tmp_path / "resources")})[1]

    assert migration.journal[2].ratio == 1 / 3
    assert migration.differences == []


@pytest.fixture
def split_recorded_late(tmp_path, fake_market):
    """A ledger whose 2:1 split of AAA.MI, dated 02-01-2024, was recorded after its buy of 03-01-2024.

    As Home records a split found on Yahoo: with its own date, which can be
    the day before the first trade.
    """
    ledger = _replay([deposit(date(2024, 1, 2), 10_000), buy(date(2024, 1, 3), "AAA.MI", 10, price=100.0, fee=2.0)],
                     tmp_path / "recorded")
    return newrow_split(ledger, "02-01-2024", date(2024, 1, 2), BROKER, "AAA.MI", 2.0)


def test_a_split_dated_before_its_first_buy_goes_on_the_day_of_the_buy(split_recorded_late, tmp_path):
    """A split recorded after its ticker's first buy but dated the day before goes on the buy's day: the only change.

    By its own date the split would come before the buy, with no shares to
    split, and the migration could never finish. A day apart, Home still
    finds it recorded.
    """
    migration = migrated({1: legacy_account(1, BROKER, split_recorded_late, tmp_path / "resources")})[1]

    assert [op.kind for op in migration.journal] == ["deposit", "buy", "split"]
    assert migration.differences == [Difference("02-01-2024", "Split", "AAA.MI", "date", "02-01-2024", "03-01-2024")]
    assert unrecorded_splits(migration.ledger, "AAA.MI", [(date(2024, 1, 2), 2.0)]) == []


def test_a_split_recorded_after_later_operations_keeps_its_own_date(tmp_path, fake_market):
    """A split Home recorded after operations dated later keeps its date, before them: Home doesn't offer it again.

    BBB.MI, bought on 02-05, splits 2:1 on 15-08, recorded after a
    withdrawal of 02-09. Moved to 02-09 instead, Home would find no split
    near Yahoo's date, offer it again, and recording it would double the
    shares once more.
    """
    ledger = _replay([deposit(date(2024, 1, 2), 5000), buy(date(2024, 5, 2), "BBB.MI", 20, price=50.0, fee=1.0),
                      withdrawal(date(2024, 9, 2), 100)], tmp_path / "recorded")
    ledger = newrow_split(ledger, "15-08-2024", date(2024, 8, 15), BROKER, "BBB.MI", 2.0)

    migration = migrated({1: legacy_account(1, BROKER, ledger, tmp_path / "resources")})[1]

    assert migration.ledger["operation"].tolist()[1:] == ["Deposit", "Buy", "Split", "Withdrawal"]
    assert unrecorded_splits(migration.ledger, "BBB.MI", [(date(2024, 8, 15), 2.0)]) == []


def test_a_late_split_that_cant_go_on_its_date_keeps_its_place(tmp_path, fake_market):
    """If a split recorded late can't be applied on its own date, it keeps its place, as it was recorded.

    A 1:10 reverse split of AAA.MI on 01-02, recorded after a sale of 15 of
    its 20 shares on 01-03: on its date it would leave 2 shares, too few for
    that sale. Kept after the sale, the account migrates as it was.
    """
    ledger = _replay([deposit(date(2024, 1, 2), 5000), buy(date(2024, 1, 3), "AAA.MI", 20, price=100.0, fee=1.0),
                      sell(date(2024, 3, 1), "AAA.MI", 15, price=110.0, fee=1.0)], tmp_path / "recorded")
    ledger = newrow_split(ledger, "01-02-2024", date(2024, 2, 1), BROKER, "AAA.MI", 0.1)

    migration = migrated({1: legacy_account(1, BROKER, ledger, tmp_path / "resources")})[1]

    assert [op.kind for op in migration.journal][-2:] == ["sell", "split"]
    assert migration.differences == [Difference("01-02-2024", "Split", "AAA.MI", "date", "01-02-2024", "01-03-2024")]


def test_an_account_that_cant_be_migrated_doesnt_hold_back_the_others(tmp_path, fake_market):
    """One account with an operation that can't be converted fails alone, named; the others are migrated.

    Otherwise every account would stay unchangeable while that one does.
    """
    good = _replay([deposit(date(2024, 1, 2), 1000)], tmp_path / "good").assign(account="Fineco")
    bad = _replay([deposit(date(2024, 1, 2), 100)], tmp_path / "bad").assign(account="Directa")
    bad.loc[1, "operation"] = "Bonus"
    accounts = {1: legacy_account(1, "Fineco", good, tmp_path / "resources"),
                2: legacy_account(2, "Directa", bad, tmp_path / "resources")}

    migrations, failures = migrate(accounts)

    assert list(migrations) == [1]
    assert [failure.params["account"] for failure in failures] == ["Directa"]


def test_a_ticker_yahoo_no_longer_has_doesnt_block_the_migration(tmp_path, fake_market, monkeypatch):
    """An asset Yahoo has no prices for anymore (e.g. delisted) is valued at its own trade's price.

    Valuations aren't compared, so they mustn't stop the migration: without
    a price, rebuilding the rows that hold it would fail at every start.
    """
    monkeypatch.setitem(FAKE_BASE_PRICES, "ZZZ.MI", 20.0)
    monkeypatch.setitem(NAMES, "ZZZ.MI", "Zeta SpA")
    ledger = _replay([deposit(date(2024, 1, 2), 1000), buy(date(2024, 1, 3), "ZZZ.MI", 10, price=21.0, fee=0.0)],
                     tmp_path / "recorded")
    monkeypatch.delitem(FAKE_BASE_PRICES, "ZZZ.MI")  # delisted since

    migration = migrated({1: legacy_account(1, BROKER, ledger, tmp_path / "resources")})[1]

    assert migration.differences == []
    assert migration.ledger["assets_value"].iloc[-1] == 210.0


def test_transfers_are_paired_across_accounts(tmp_path, fake_market):
    """Each transfer's two halves get the same transfer_id; equal transfers on one day pair one to one.

    Fineco sends Directa 100 twice on 10-01-2024, and 50 to an account since
    deleted, whose half has a transfer_id of its own.
    """
    fineco = Account(1, "Fineco", "", _replay([deposit(date(2024, 1, 2), 1000)], tmp_path / "f").assign(account="Fineco"))
    directa = Account(2, "Directa", "", _replay([deposit(date(2024, 1, 2), 100)], tmp_path / "d").assign(account="Directa"))
    for _ in range(2):  # recorded as before the journal: a row in each account
        fineco.df = newrow_cash(fineco.df, "10-01-2024", date(2024, 1, 10), "Fineco", -100, Op.TRANSFER_OUT,
                                Product.CASH, np.nan, "Directa")
        directa.df = newrow_cash(directa.df, "10-01-2024", date(2024, 1, 10), "Directa", 100, Op.TRANSFER_IN,
                                 Product.CASH, np.nan, "Fineco")
    fineco.df = newrow_cash(fineco.df, "11-01-2024", date(2024, 1, 11), "Fineco", -50, Op.TRANSFER_OUT, Product.CASH,
                            np.nan, "Old Broker")
    accounts = {idx: legacy_account(idx, account.name, account.df, tmp_path / "resources")
                for idx, account in ((1, fineco), (2, directa))}

    migrations = migrated(accounts)

    sent = [op.transfer_id for op in migrations[1].journal if op.kind == "transfer_out"]
    received = [op.transfer_id for op in migrations[2].journal if op.kind == "transfer_in"]
    assert sent[:2] == received and len(set(sent)) == 3
    assert [m.ledger["cash_held"].iloc[-1] for m in migrations.values()] == [750, 300]


def test_a_transfer_half_takes_the_id_of_its_other_half_already_in_a_journal(tmp_path, fake_market):
    """A transfer whose other half is already in a journal (that account was migrated first) joins it.

    Otherwise the two halves would keep different ids for good, and
    deleting the transfer from one account would leave it in the other.
    """
    fineco = Account(1, "Fineco", "", _replay([deposit(date(2024, 1, 2), 1000)], tmp_path / "f").assign(account="Fineco"))
    fineco.df = newrow_cash(fineco.df, "10-01-2024", date(2024, 1, 10), "Fineco", -300, Op.TRANSFER_OUT, Product.CASH,
                            np.nan, "Directa")
    received = Operation(id="in", seq=1, date=date(2024, 1, 10), kind="transfer_in", amount=300.0,
                         counterpart="Fineco", transfer_id="already-there")
    directa = Account(2, "Directa", "", None, journal=[received])

    migration = migrated({1: legacy_account(1, "Fineco", fineco.df, tmp_path / "resources"), 2: directa})[1]

    assert [op.transfer_id for op in migration.journal if op.kind == "transfer_out"] == ["already-there"]


@pytest.fixture
def legacy_state(state, tmp_path):
    """Return a function turning the `state` fixture's account into one recorded before the journal, holding a ledger.

    As an existing install has it: the ledger's CSV alone, loaded again. The
    ledger defaults to the STOCKS_EUR history the account holds.
    """
    def make_legacy(ledger=None):
        """Give the account `ledger` (or its own history) and no journal, and load it again."""
        folder = state.config_res_folder
        os.remove(account_service.journal_path(folder, BROKER))
        ledger = _replay(STOCKS_EUR, tmp_path / "legacy") if ledger is None else ledger
        ledger.to_csv(account_service.ledger_path(folder, BROKER), index=False)
        state.load_all_accounts()
        return state

    return make_legacy


def test_a_migration_isnt_saved_over_an_account_changed_meanwhile(legacy_state, tmp_path):
    """If the account's ledger changed while the migration was worked out, nothing is saved: the change would be lost.

    The migration is then worked out again, from the account as it is now.
    """
    state = legacy_state()
    migrations = migrated(state.accounts)
    state.get_account(1).df = _replay([deposit(date(2024, 1, 2), 5)], tmp_path / "other")

    assert state.commit_migration(migrations) is False
    assert state.get_account(1).journal is None
    assert not os.path.exists(account_service.journal_path(state.config_res_folder, BROKER))


def test_a_migration_of_every_account_notes_the_current_rules(legacy_state, monkeypatch):
    """The migration rebuilds every row with the current rules: no recalculation is offered right after it.

    E.g. a user from before the journal updating to an app whose rules
    version is 2 would otherwise be asked to recalculate a history just rebuilt.
    """
    monkeypatch.setattr(rules, "RULES_VERSION", 2)
    state = legacy_state()

    assert state.commit_migration(migrated(state.accounts)) is True

    assert config_service.load_rules_version(state.user_config_folder) == 2


def test_more_differences_than_shown_are_counted_on_a_line_of_their_own(state):
    """Past the first 10 of an account's differences, "…and N more" is a paragraph of its own, not part of the 10th."""
    differences = [Difference("03-01-2024", "Buy", "AAA.MI", "fee", 1.0, 2.0)] * 12

    text = differences_text(state, {1: differences})

    assert text.endswith("→ 2.0\n\n…and 2 more")


def _run_now(page):
    """Make `page` run background work at once, so the migration finishes within the test."""
    page.run_thread = lambda fn, *args: fn(*args)


def _open(page):
    """The dialogs still open on `page`."""
    return [dialog for dialog in page.dialogs if dialog.open]


def test_values_that_changed_are_shown_and_the_accounts_saved_on_continue(app, page, legacy_state, split_recorded_late):
    """The user sees what differs, and continuing saves the journal, the rebuilt ledger and a copy of the old one.

    Until then nothing is saved: the dialog can't be dismissed otherwise.
    Home is shown once the accounts are saved.
    """
    state = legacy_state(split_recorded_late)
    folder = state.config_res_folder
    old_ledger = Path(account_service.ledger_path(folder, BROKER)).read_text(encoding="utf-8")
    shown = []
    _run_now(page)

    migrate_accounts(app, then=lambda: shown.append("Home"))

    [dialog] = _open(page)
    assert dialog.modal and "· Split AAA.MI · Date: 02-01-2024 → 03-01-2024" in dialog.content.content.value
    assert not os.path.exists(account_service.journal_path(folder, BROKER)) and shown == []

    dialog.actions[0].on_click(None)

    assert _open(page) == [] and shown == ["Home"]
    assert account_service.read_journal(account_service.journal_path(folder, BROKER)) == state.get_account(1).journal
    assert Path(account_service.before_journal_path(folder, BROKER)).read_text(encoding="utf-8") == old_ledger


def test_the_working_dialog_closes_though_another_opened_above_it(app, page, state):
    """The "updating" dialog closes itself, not whichever dialog was opened last, which would stay open for good."""
    work = []
    page.run_thread = lambda fn, *args: work.append(fn)
    migrate_accounts(app, then=lambda: None)
    working = page.dialogs[-1]
    other = ft.AlertDialog(title=ft.Text("Another dialog"))  # e.g. the update notice
    page.show_dialog(other)

    work[0]()

    assert other.open and not working.open


def test_an_operation_that_cant_be_converted_is_named_not_blamed_on_the_connection(app, page, legacy_state):
    """A row that can never be converted is named, with its account, instead of "are you offline?" at every start."""
    state = legacy_state()
    state.get_account(1).df.loc[1, "operation"] = "Bonus"
    shown = []
    _run_now(page)

    migrate_accounts(app, then=lambda: shown.append("Home"))

    [dialog] = _open(page)
    assert "02-01-2024" in dialog.content.content.value and "Test Broker" in dialog.content.content.value
    assert snack_texts(page) == [] and shown == ["Home"]


def test_a_migration_that_fails_saves_nothing_and_says_so(app, page, legacy_state, monkeypatch):
    """Offline, the migration can't price the rows: the user is told, Home is shown, and every file stays as it was."""
    state = legacy_state()
    folder = state.config_res_folder
    before = sorted(os.listdir(folder))
    shown = []

    def offline(accounts):
        """Fail like a migration with no prices."""
        raise LookupError("No close of AAA.MI in the 10 days up to 03-01-2024")

    monkeypatch.setattr(migration_service, "migrate", offline)
    _run_now(page)

    migrate_accounts(app, then=lambda: shown.append("Home"))

    assert _open(page) == [] and shown == ["Home"]
    assert snack_texts(page) == [state.translator.get("journal.migration.failed")]
    assert sorted(os.listdir(folder)) == before and state.get_account(1).journal is None
