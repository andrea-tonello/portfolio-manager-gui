"""Tests for recording, deleting and editing operations through the journal (services/journal_service.py).

The accounts are kept in memory, as the app holds them. Each change returns
the new journal and rebuilt ledger of every account it touches, which
AppState.commit_changes then saves; here `applied` stands in for it.
"""

import json
from dataclasses import replace
from datetime import date

import pandas as pd
import pytest
from conftest import account_of, applied
from test_journal import csv_text
from test_ledger_snapshots import BROKER, STOCKS_EUR, buy, deposit, journal_of

from components.snack import error_message
from domain.account import Account
from domain.errors import ValidationError
from domain.journal import Kind, OperationRefused, rebuild
from services import journal_service, market_data
from utils.columns import OP_ID


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


def test_an_account_not_yet_moved_to_the_journal_cant_change(fake_market, translator):
    """An account whose migration hasn't succeeded yet (e.g. the app started offline) refuses changes, saying why.

    Recorded the old way, its ledger would be rebuilt without them once it gets its journal.
    """
    journal = journal_of([deposit(date(2024, 1, 2), 1000)])
    accounts = {1: Account(1, BROKER, path="", df=rebuild(BROKER, journal))}

    with pytest.raises(ValidationError) as refused:
        journal_service.record(accounts, accounts[1], Kind.DEPOSIT, date(2024, 2, 1), amount=10.0)

    assert error_message(translator, refused.value).startswith("Test Broker hasn't been updated to the new format yet")


def test_recording_offline_is_refused_rather_than_valued_at_old_trade_prices(fake_market, monkeypatch, translator):
    """With no answer from Yahoo at all, recording in an account holding shares fails, saying so.

    Valued at the shares' own trade prices instead, the new rows would look
    up to date and never be priced again. A ticker Yahoo no longer has,
    while it answers for others, does fall back to its trade price.
    """
    accounts = {1: account_of(1, BROKER, STOCKS_EUR)}
    monkeypatch.setattr(market_data, "download_close", lambda tickers, **kwargs: (pd.DataFrame(), {}))

    with pytest.raises(ValidationError) as refused:
        journal_service.record(accounts, accounts[1], Kind.DEPOSIT, date(2024, 10, 1), amount=10.0)

    assert error_message(translator, refused.value) == translator.get("misc_errors.prices_unavailable")


def test_a_transfer_whose_other_account_isnt_migrated_yet_isnt_removed_by_half(fake_market):
    """Removing a transfer whose other account has no journal yet is refused: its half would be left for good."""
    accounts = {1: account_of(1, "Fineco", [deposit(date(2024, 1, 2), 1000)]),
                2: account_of(2, "Directa", [deposit(date(2024, 1, 2), 100)])}
    applied(accounts, journal_service.record(accounts, accounts[1], Kind.TRANSFER_OUT, date(2024, 1, 10),
                                             amount=300.0, counterpart="Directa"))
    accounts[2].journal = None  # as if Directa's migration hadn't succeeded

    with pytest.raises(ValidationError) as refused:
        journal_service.delete(accounts, accounts[1], accounts[1].journal[-1].id)

    assert (refused.value.key, refused.value.params) == ("journal.partner_unavailable", {"account": "Directa"})


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


def _first_deposit(account):
    """The first operation of `account`: in STOCKS_EUR, the deposit of 10,000 on 02-01-2024 that pays for every buy."""
    return account.journal[0]


@pytest.mark.parametrize("change, message", [
    (lambda accounts, account: journal_service.delete(accounts, account, _first_deposit(account).id),
     "This would leave Test Broker short of cash: -1,002.00€ on 03-01-2024."),
    (lambda accounts, account: journal_service.edit(accounts, account, _first_deposit(account).id, amount=2_000.0),
     "This would leave Test Broker short of cash: -104.00€ on 01-02-2024."),
], ids=["removed", "lowered"])
def test_a_change_leaving_a_later_operation_short_of_cash_is_refused(fake_market, translator, change, message):
    """Removing the deposit of 10,000, or lowering it to 2,000, leaves the buys it paid for below zero: refused.

    The message names the first row left short: the buy of 1,002 on
    03-01-2024 without the deposit, the buy of 1,102 on 01-02-2024 with 2,000
    (998 - 1,102). Recording a buy beyond the cash is still allowed: only
    removals and edits are checked, as transfers are.
    """
    accounts = {1: account_of(1, BROKER, STOCKS_EUR)}

    with pytest.raises(ValidationError) as refused:
        change(accounts, accounts[1])

    assert error_message(translator, refused.value) == message


# 100 deposited, then a buy of 501: the buy's row is 401 below zero, as recording allows.
SHORT_ALREADY = [deposit(date(2024, 1, 2), 100), buy(date(2024, 1, 3), "BBB.MI", 10, price=50.0, fee=1.0)]


@pytest.mark.parametrize("steps, edited, amount, last_cash", [
    (SHORT_ALREADY, 0, 200.0, -301),
    (STOCKS_EUR, -1, 10_000.0, -776.88),
], ids=["raised-but-still-below-zero", "its-own-row"])
def test_an_edit_that_takes_no_other_operation_below_zero_is_allowed(fake_market, steps, edited, amount, last_cash):
    """An edit may leave cash below zero on a row already below zero, and on the own row of an operation spending cash.

    A buy of 501 paid with 100 is already 401 short: raising the deposit to
    200 leaves it 301 short, which is allowed, so a history short of cash
    can still be corrected. Raising STOCKS_EUR's last withdrawal from 500 to
    10,000 takes its own row below zero, as recording it would.
    """
    accounts = {1: account_of(1, BROKER, steps)}

    applied(accounts, journal_service.edit(accounts, accounts[1], accounts[1].journal[edited].id, amount=amount))

    assert accounts[1].last("cash_held") == pytest.approx(last_cash)


def test_undoing_a_deposit_under_a_row_already_short_is_allowed(fake_market):
    """A deposit of 50 recorded by mistake under the buy already short can be removed: the buy is back at -401.

    It only puts the account back as it was. Refused, a history short of
    cash somewhere could never be undone.
    """
    accounts = {1: account_of(1, BROKER, SHORT_ALREADY)}
    applied(accounts, journal_service.record(accounts, accounts[1], Kind.DEPOSIT, date(2024, 1, 2), amount=50.0))

    applied(accounts, journal_service.delete(accounts, accounts[1], journal_service.last_entered(accounts[1]).id))

    assert accounts[1].last("cash_held") == pytest.approx(-401)


def test_lowering_the_last_deposit_below_what_was_spent_is_refused(fake_market, translator):
    """A deposit of 600 that brings the account back to 199 can't be lowered to 100, though no operation follows it.

    Its own row would be 301 below zero. Only an operation spending cash (a
    buy, a withdrawal) may take its own row below zero, as when recorded.
    """
    accounts = {1: account_of(1, BROKER, [*SHORT_ALREADY, deposit(date(2024, 1, 4), 600)])}

    with pytest.raises(ValidationError) as refused:
        journal_service.edit(accounts, accounts[1], accounts[1].journal[-1].id, amount=100.0)

    assert error_message(translator, refused.value) == "This would leave Test Broker short of cash: -301.00€ on 04-01-2024."


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


def test_removing_a_transfer_the_receiver_has_spent_is_refused(transfer, translator):
    """Directa withdraws 350 of the 400 it holds after the transfer: removing the transfer would leave it 250 short.

    Refused, though Fineco, which removes it, gets its 300 back.
    """
    applied(transfer, journal_service.record(transfer, transfer[2], Kind.WITHDRAWAL, date(2024, 2, 1), amount=350.0))

    with pytest.raises(ValidationError) as refused:
        journal_service.delete(transfer, transfer[1], transfer[1].journal[-1].id)

    assert error_message(translator, refused.value) == "This would leave Directa short of cash: -250.00€ on 01-02-2024."


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


def test_several_operations_are_deleted_at_once_and_a_buy_goes_only_with_the_sales_it_paid_for(fake_market):
    """Deleting the buy of 10 AAA.MI on 01-02-2024 alone is refused: the sale of 03-06-2024 needs those shares.

    Deleted with that sale, the split and the sale of 01-08-2024 after it,
    the account is rebuilt once, as if they had never been recorded. The 6
    operations after the buy that stay are recalculated, and nothing else.
    """
    accounts = {1: account_of(1, BROKER, STOCKS_EUR)}
    journal = accounts[1].journal
    buy_feb, sale_jun, split_jul, sale_aug = journal[2], journal[8], journal[9], journal[10]

    with pytest.raises(OperationRefused) as refused:
        journal_service.delete_many(accounts, journal_service.picked_operations(accounts, [(accounts[1], buy_feb.id)]))
    assert refused.value.operation == sale_jun

    picked = journal_service.picked_operations(
        accounts, [(accounts[1], op.id) for op in (sale_aug, buy_feb, split_jul, sale_jun)])
    assert journal_service.later_operations_deleting_many(accounts, picked) == 6
    applied(accounts, journal_service.delete_many(accounts, picked))

    kept = [op for op in journal if op not in (buy_feb, sale_jun, split_jul, sale_aug)]
    assert accounts[1].journal == kept
    assert csv_text(accounts[1].df) == csv_text(rebuild(BROKER, kept))


def test_a_transfer_picked_by_both_halves_is_deleted_once(transfer):
    """In the list of every account, both rows of a transfer can be ticked: it goes from both accounts, as for one half."""
    sent, received = transfer[1].journal[-1], transfer[2].journal[-1]

    picked = journal_service.picked_operations(transfer, [(transfer[1], sent.id), (transfer[2], received.id)])
    applied(transfer, journal_service.delete_many(transfer, picked))

    assert [op.kind for op in transfer[1].journal + transfer[2].journal] == ["deposit", "deposit"]
    assert (transfer[1].last("cash_held"), transfer[2].last("cash_held")) == (1000, 100)


def test_a_transfer_whose_other_account_couldnt_be_loaded_isnt_deleted_by_half(transfer):
    """Directa exists but couldn't be loaded (not in the accounts, its name among the unavailable): refused, naming it.

    Deleted from Fineco alone, its half in Directa would stay for good. With
    Directa really gone (deleted, so not unavailable), Fineco's half alone goes.
    """
    sent = transfer[1].journal[-1]
    fineco_only = {1: transfer[1]}

    with pytest.raises(ValidationError) as refused:
        journal_service.picked_operations(fineco_only, [(transfer[1], sent.id)], unavailable=frozenset({"Directa"}))
    assert (refused.value.key, refused.value.params) == ("journal.partner_unavailable", {"account": "Directa"})

    [(_, _, half)] = journal_service.picked_operations(fineco_only, [(transfer[1], sent.id)])
    assert half is None
