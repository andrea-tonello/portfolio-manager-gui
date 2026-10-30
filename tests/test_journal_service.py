"""Tests for recording, deleting and editing operations through the journal (services/journal_service.py).

The accounts are kept in memory, as the app holds them. Each change returns
the new journal and rebuilt ledger of every account it touches, which
AppState.commit_changes then saves; here `applied` stands in for it.
"""

import json
from dataclasses import replace
from datetime import date

import pytest
from test_journal import csv_text, journal_of
from test_ledger_snapshots import BROKER, STOCKS_EUR, deposit

from domain.account import Account
from domain.errors import ValidationError
from domain.journal import Kind, OperationRefused, rebuild
from services import journal_service
from utils.columns import OP_ID


def account_of(idx, name, steps):
    """Return an account called `name`, numbered `idx`, whose journal holds `steps`, with the ledger rebuilt from it."""
    journal = journal_of(steps)
    return Account(idx, name, path="", df=rebuild(name, journal), journal=journal)


def applied(accounts, changes):
    """Make `changes` the accounts' journals and ledgers, as AppState.commit_changes does, without saving them."""
    for idx, (journal, ledger) in changes.items():
        accounts[idx].journal, accounts[idx].df = journal, ledger


def test_an_operation_recorded_in_the_past_takes_its_place_by_date(fake_market):
    """A deposit dated before later operations goes in its place, and every row after it counts its cash.

    It is entered last (the highest seq), and only the rows from its
    position on are built again: the ledger is the one a full rebuild gives.
    """
    accounts = {1: account_of(1, BROKER, STOCKS_EUR)}
    last_cash = accounts[1].last("cash_held")

    journal, ledger = journal_service.record(accounts, accounts[1], Kind.DEPOSIT, date(2024, 3, 15),
                                             amount=1000.0)[1]

    assert journal[-1].seq == len(STOCKS_EUR) + 1
    assert ledger.loc[ledger[OP_ID] == journal[-1].id, "date"].tolist() == ["15-03-2024"]
    assert ledger["cash_held"].iloc[-1] == last_cash + 1000
    assert csv_text(ledger) == csv_text(rebuild(BROKER, journal))


def test_rows_built_from_an_operation_since_edited_are_built_again(fake_market):
    """A ledger out of step with its journal is rebuilt from where they differ, though its rows name the same operations.

    E.g. an edit was saved in the journal but the ledger wasn't rebuilt (no
    prices offline when the app started): its rows still show the first
    deposit as 10,000 while the journal now says 15,000. Recording a
    withdrawal must not build on those rows, or the wrong cash would be
    saved for good.
    """
    journal = journal_of(STOCKS_EUR)
    edited = [replace(journal[0], amount=15_000), *journal[1:]]
    accounts = {1: Account(1, BROKER, path="", df=rebuild(BROKER, journal), journal=edited)}

    new_journal, ledger = journal_service.record(accounts, accounts[1], Kind.WITHDRAWAL, date(2024, 10, 1),
                                                 amount=10.0)[1]

    assert csv_text(ledger) == csv_text(rebuild(BROKER, new_journal))
    assert ledger["cash_held"].iloc[-1] == accounts[1].last("cash_held") + 5_000 - 10


@pytest.mark.parametrize("damage", [
    {"version": 2},                                         # written by a newer version
    {"operations": [{"seq": "3"}]},                         # an order of entry that can't be compared
    {"operations": [{"id": 5}]},                            # an id the ledger's text op_id never matches
    {"operations": [{}, {}]},                               # two operations with the same id
    {"operations": [{"date": None}]},
], ids=["version", "seq-text", "id-number", "same-id", "no-date"])
def test_a_damaged_journal_file_is_refused_when_read(fake_market, damage):
    """A journal file that isn't one this version wrote raises ValueError when read, not later when used.

    Each case changes a valid file holding one deposit.
    """
    stored = json.loads(journal_service.journal_to_json(journal_of([deposit(date(2024, 1, 2), 1000)])))
    if "operations" in damage:
        stored["operations"] = [{**stored["operations"][0], **change} for change in damage["operations"]]
    else:
        stored.update(damage)

    with pytest.raises(ValueError):
        journal_service.journal_from_json(json.dumps(stored))


def test_an_operation_that_cant_be_recorded_raises_and_changes_nothing(fake_market):
    """A sale that can't be recorded raises its own error; one that makes a later sale impossible names that one.

    STOCKS_EUR holds 20 BBB.MI at the end: selling 30 raises "Quantity sold
    (30) exceeds...". Selling 10 AAA.MI on 15-05-2024 is possible, but leaves
    none for the sale of 03-06-2024. Neither changes the account in memory.
    """
    accounts = {1: account_of(1, BROKER, STOCKS_EUR)}
    account = accounts[1]
    journal, ledger = list(account.journal), account.df.copy()
    sale = {"asset_name": "Beta SpA", "product": "Stock", "currency": "EUR", "conv_rate": 1.0, "price": 50.0,
            "fee": 1.0, "fee_mode": "abp", "tax_rate": 0.26, "ter": None}

    with pytest.raises(ValidationError) as own:
        journal_service.record(accounts, account, Kind.SELL, date(2024, 10, 1), ticker="BBB.MI", quantity=30, **sale)
    with pytest.raises(OperationRefused) as later:
        journal_service.record(accounts, account, Kind.SELL, date(2024, 5, 15),
                               **{**sale, "ticker": "AAA.MI", "asset_name": "Alpha SpA", "quantity": 10})

    assert not isinstance(own.value, OperationRefused) and own.value.key == "operations.stock.sell_noqt"
    assert later.value.operation == journal[8]  # the sale of AAA.MI on 03-06-2024
    assert account.journal == journal
    assert account.df.equals(ledger)


@pytest.fixture
def transfer(fake_market):
    """Fineco (1,000 EUR deposited) sends 300 to Directa (100 deposited) on 10-01-2024; return the two accounts."""
    accounts = {1: account_of(1, "Fineco", [deposit(date(2024, 1, 2), 1000)]),
                2: account_of(2, "Directa", [deposit(date(2024, 1, 2), 100)])}
    applied(accounts, journal_service.record(accounts, accounts[1], Kind.TRANSFER_OUT, date(2024, 1, 10),
                                             amount=300.0, counterpart="Directa"))
    return accounts


def test_a_transfer_is_recorded_in_both_accounts_and_deleted_from_both(transfer):
    """A transfer goes in both journals, as two halves sharing a transfer_id; deleting either half deletes both."""
    sent, received = transfer[1].journal[-1], transfer[2].journal[-1]

    assert (sent.kind, sent.counterpart, received.kind, received.counterpart) == (
        "transfer_out", "Directa", "transfer_in", "Fineco")
    assert sent.transfer_id == received.transfer_id
    assert (transfer[1].last("cash_held"), transfer[2].last("cash_held")) == (700, 400)

    applied(transfer, journal_service.delete(transfer, transfer[2], received.id))

    assert [op.kind for op in transfer[1].journal + transfer[2].journal] == ["deposit", "deposit"]
    assert (transfer[1].last("cash_held"), transfer[2].last("cash_held")) == (1000, 100)


def test_editing_a_transfer_changes_both_halves(transfer):
    """A transfer's new amount and date go to its other half too, each keeping its id and order of entry.

    The edited transfer stays in the same place in both ledgers, so only
    knowing which operation changed tells its rows to be built again.
    """
    sent, received = transfer[1].journal[-1], transfer[2].journal[-1]

    applied(transfer, journal_service.edit(transfer, transfer[1], sent.id, amount=200.0, date=date(2024, 1, 5)))

    edited = [transfer[1].journal[-1], transfer[2].journal[-1]]
    assert [(op.id, op.seq, op.amount, op.date) for op in edited] == [
        (sent.id, sent.seq, 200.0, date(2024, 1, 5)), (received.id, received.seq, 200.0, date(2024, 1, 5))]
    assert (transfer[1].last("cash_held"), transfer[2].last("cash_held")) == (800, 300)
