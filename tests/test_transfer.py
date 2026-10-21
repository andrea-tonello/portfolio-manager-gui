"""Tests for transfers of cash between two of the user's accounts (services/operations_service.py).

A transfer writes a Transfer Out row in the account sending and a Transfer In
row in the one receiving, on the same day. For each account it is money going
out or coming in, like a withdrawal or a deposit; across all accounts the two
rows cancel out, so the portfolio's figures don't change.
"""

from datetime import date

import pytest
from test_ledger_snapshots import _replay, buy, deposit

from domain.account import Account
from domain.errors import ValidationError
from services.analysis_service import compute_summary
from services.operations_service import execute_transfer, parse_transfer

DAY = date(2024, 6, 3)


@pytest.fixture
def accounts(tmp_path, fake_market):
    """Fineco (10,000 deposited, 1,000 of it in BBB.MI) and Directa (1,000 deposited), as (fineco, directa).

    Each ledger names its own account in every row, as real ones do: the
    portfolio's history tells the accounts apart by it.
    """
    fineco_df = _replay([deposit(date(2024, 1, 2), 10_000), buy(date(2024, 1, 3), "BBB.MI", 20, price=50.0, fee=0.0)],
                        tmp_path / "fineco").assign(account="Fineco")
    directa_df = _replay([deposit(date(2024, 1, 2), 1_000)], tmp_path / "directa").assign(account="Directa")
    return Account(1, "Fineco", "", fineco_df), Account(2, "Directa", "", directa_df)


def test_a_transfer_moves_cash_between_the_two_accounts(accounts):
    """2,000 from Fineco to Directa: Fineco's cash and committed cash go down by 2,000, Directa's up, in total unchanged.

    Each new row says which way the cash went and names the other account.
    """
    fineco, directa = accounts

    fineco_df, directa_df = execute_transfer(fineco, directa, DAY.strftime("%d-%m-%Y"), DAY, 2_000)

    sent, received = fineco_df.iloc[-1], directa_df.iloc[-1]
    assert (sent["operation"], sent["asset_name"], sent["cash_held"], sent["committed_cash"]) == \
        ("Transfer Out", "Directa", 7_000, 8_000)
    assert (received["operation"], received["asset_name"], received["cash_held"], received["committed_cash"]) == \
        ("Transfer In", "Fineco", 3_000, 3_000)


def test_a_transfer_leaves_the_portfolio_figures_unchanged(accounts):
    """With all accounts together, NAV, committed cash, XIRR and TWRR are the same with or without a transfer.

    The two rows are a cash flow of their own account each, but cancel out in the portfolio.
    """
    fineco, directa = accounts
    fineco_df, directa_df = execute_transfer(fineco, directa, DAY.strftime("%d-%m-%Y"), DAY, 2_000)
    after = [Account(1, "Fineco", "", fineco_df), Account(2, "Directa", "", directa_df)]

    without = compute_summary([fineco, directa], date(2024, 12, 31), "31-12-2024")["portfolio"]
    with_transfer = compute_summary(after, date(2024, 12, 31), "31-12-2024")["portfolio"]

    for figure in ("nav", "historic_liq", "xirr_full", "twrr_full"):
        assert with_transfer[figure] == pytest.approx(without[figure]), figure


def test_cash_sent_away_is_not_a_loss_for_the_account(accounts):
    """Fineco's own return stays positive (about +4%) after sending 2,000 to Directa: money out, not money lost.

    Transfers are cash flows of each account, like withdrawals and deposits.
    Counted as nothing, the 2,000 gone would make Fineco's return about -16%.
    """
    fineco, directa = accounts
    fineco_df, _ = execute_transfer(fineco, directa, DAY.strftime("%d-%m-%Y"), DAY, 2_000)

    summary = compute_summary([Account(1, "Fineco", "", fineco_df)], date(2024, 12, 31), "31-12-2024")

    assert summary["accounts"][0]["xirr_full"] == pytest.approx(0.0412, abs=0.001)


@pytest.mark.parametrize("recipient, day, amount, key, params", [
    (None, DAY, "100", "operations.transfer.no_recipient", {}),
    ("directa", date(2024, 1, 1), "100", "operations.transfer.date_recipient", {"account": "Directa"}),
    ("directa", DAY, "0", "operations.cash.error_cash", {}),
    ("directa", DAY, "9000.01", "operations.transfer.not_enough_cash", {"available": "9,000.00€"}),
], ids=["no-recipient", "before-the-recipients-last-operation", "zero", "more-than-held"])
def test_a_transfer_is_refused_with_its_reason(accounts, recipient, day, amount, key, params):
    """Each problem gives its own message: no recipient, a date before the recipient's last operation,
    an amount that isn't above 0, or more than the 9,000 of cash Fineco holds."""
    fineco, directa = accounts

    with pytest.raises(ValidationError) as info:
        parse_transfer(fineco.df, directa if recipient else None, day, amount)

    assert (info.value.key, info.value.params) == (key, params)
