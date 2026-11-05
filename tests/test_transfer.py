"""Tests for transfers of cash between two of the user's accounts (services/journal_service.py, operations_service).

A transfer writes a Transfer Out row in the account sending and a Transfer In
row in the one receiving, on the same day. For each account it is money going
out or coming in, like a withdrawal or a deposit; across all accounts the two
rows cancel out, so the portfolio's figures don't change. In the journal its
two halves share a transfer_id, so undoing it from either account undoes both.
"""

from datetime import date

import pytest
from conftest import account_of, applied
from test_ledger_snapshots import buy, deposit

from domain.errors import ValidationError
from domain.journal import Kind
from services import journal_service
from services.analysis_service import compute_summary
from services.operations_service import parse_transfer
from utils.columns import OP_ID

DAY = date(2024, 6, 3)


@pytest.fixture
def accounts(fake_market):
    """Fineco (10,000 deposited, 1,000 of it in BBB.MI) and Directa (1,000 deposited), by account number."""
    return {1: account_of(1, "Fineco", [deposit(date(2024, 1, 2), 10_000),
                                        buy(date(2024, 1, 3), "BBB.MI", 20, price=50.0, fee=0.0)]),
            2: account_of(2, "Directa", [deposit(date(2024, 1, 2), 1_000)])}


def transfer(accounts, amount=2_000, day=DAY):
    """Record `amount` sent from Fineco to Directa on `day`, as the Operations screen does."""
    applied(accounts, journal_service.record(accounts, accounts[1], Kind.TRANSFER_OUT, day,
                                             amount=float(amount), counterpart="Directa"))


def undo_last(accounts, idx=1):
    """Remove the operation recorded last in account `idx`, as Transactions does: both halves of a transfer."""
    account = accounts[idx]
    applied(accounts, journal_service.delete(accounts, account, journal_service.last_entered(account).id))


def test_a_transfer_moves_cash_between_the_two_accounts(accounts):
    """2,000 from Fineco to Directa: Fineco's cash and committed cash go down by 2,000, Directa's up, in total unchanged.

    Each new row says which way the cash went and names the other account.
    """
    transfer(accounts)

    sent, received = accounts[1].df.iloc[-1], accounts[2].df.iloc[-1]
    assert (sent["operation"], sent["asset_name"], sent["cash_held"], sent["committed_cash"]) == \
        ("Transfer Out", "Directa", 7_000, 8_000)
    assert (received["operation"], received["asset_name"], received["cash_held"], received["committed_cash"]) == \
        ("Transfer In", "Fineco", 3_000, 3_000)


def test_a_transfer_leaves_the_portfolio_figures_unchanged(accounts):
    """With all accounts together, NAV, committed cash, XIRR and TWRR are the same with or without a transfer.

    The two rows are a cash flow of their own account each, but cancel out in the portfolio.
    """
    without = compute_summary(list(accounts.values()), date(2024, 12, 31), "31-12-2024")["portfolio"]
    transfer(accounts)
    with_transfer = compute_summary(list(accounts.values()), date(2024, 12, 31), "31-12-2024")["portfolio"]

    for figure in ("nav", "historic_liq", "xirr_full", "twrr_full"):
        assert with_transfer[figure] == pytest.approx(without[figure]), figure


def test_cash_sent_away_is_not_a_loss_for_the_account(accounts):
    """Fineco's own return stays positive (about +4%) after sending 2,000 to Directa: money out, not money lost.

    Transfers are cash flows of each account, like withdrawals and deposits.
    Counted as nothing, the 2,000 gone would make Fineco's return about -16%.
    """
    transfer(accounts)

    summary = compute_summary([accounts[1]], date(2024, 12, 31), "31-12-2024")

    assert summary["accounts"][0]["xirr_full"] == pytest.approx(0.0412, abs=0.001)


@pytest.mark.parametrize("recipient, day, amount, key, params", [
    (None, DAY, "100", "operations.transfer.no_recipient", {}),
    ("directa", DAY, "0", "operations.cash.error_cash", {}),
    ("directa", DAY, "9000.01", "operations.transfer.not_enough_cash", {"available": "9,000.00€"}),
    ("directa", date(2024, 1, 2), "9000.01", "operations.transfer.not_enough_cash", {"available": "9,000.00€"}),
    ("directa", date(2024, 1, 1), "100", "operations.transfer.not_enough_cash", {"available": "0.00€"}),
], ids=["no-recipient", "zero", "more-than-held", "more-than-a-later-buy-leaves", "before-the-deposit"])
def test_a_transfer_is_refused_with_its_reason(accounts, recipient, day, amount, key, params):
    """Each problem gives its own message: no recipient, an amount that isn't above 0, or more than Fineco can send.

    That is the least cash Fineco holds from the transfer's day on: 9,000
    on 03-06-2024. On 02-01-2024 it holds 10,000, but sending more than
    9,000 would leave the buy of 03-01-2024 short of cash. On 01-01-2024,
    before its deposit, it holds nothing.
    """
    with pytest.raises(ValidationError) as info:
        parse_transfer(accounts[1], accounts[2] if recipient else None, day, amount)

    assert (info.value.key, info.value.params) == (key, params)


def test_an_edited_transfer_can_send_only_the_cash_held_before_it_on_its_day(accounts):
    """Fineco sends 8,000 of its 9,000 on 03-06-2024, then deposits 5,000 that day: edited, the transfer can send 9,000.

    It keeps its order of entry, before the deposit, as its rebuild will
    check. Counting the deposit, the form would offer 14,000, and the
    rebuild then refuse with another figure.
    """
    transfer(accounts, 8_000)
    applied(accounts, journal_service.record(accounts, accounts[1], Kind.DEPOSIT, DAY, amount=5_000.0))
    sent = next(op for op in accounts[1].journal if op.kind == Kind.TRANSFER_OUT)

    with pytest.raises(ValidationError) as info:
        parse_transfer(accounts[1], accounts[2], DAY, "9000.01", edited=sent)

    assert info.value.params == {"available": "9,000.00€"}


# ── Undoing a transfer ───────────────────────────────────────────────

def test_a_transfer_is_undone_from_both_accounts_though_the_other_has_newer_operations(accounts):
    """With a deposit in Directa after the transfer, undoing it from Fineco removes both halves and rebuilds the deposit.

    Before the journal, this was refused until Directa's newer operations were
    undone first: removing a row from the middle broke the totals after it.
    """
    transfer(accounts, 500)
    applied(accounts, journal_service.record(accounts, accounts[2], Kind.DEPOSIT, date(2024, 6, 4), amount=100.0))

    undo_last(accounts)

    assert [op.kind for op in accounts[2].journal] == ["deposit", "deposit"]
    assert accounts[2].last("cash_held") == 1_100


@pytest.mark.parametrize("other_half", ["account-deleted", "row-already-removed"])
def test_a_transfer_whose_other_half_is_gone_is_removed_alone(accounts, other_half):
    """If Directa was deleted, or its half already removed, undoing from Fineco removes Fineco's row only."""
    transfer(accounts, 500)
    if other_half == "account-deleted":
        del accounts[2]
    else:
        accounts[2] = account_of(2, "Directa", [deposit(date(2024, 1, 2), 1_000)])

    changes = journal_service.delete(accounts, accounts[1], accounts[1].df.iloc[-1][OP_ID])

    assert set(changes) == {1}
    assert changes[1][1].iloc[-1]["operation"] == "Buy"
