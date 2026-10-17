"""Tests for the Account dataclass (domain/account.py).

An account's ledger always starts with a synthetic opening row (dated
01-01-2000, every running total at zero); `transactions` gives the real
operations without it.
"""

from datetime import date

import pandas as pd
import pytest
from test_ledger_snapshots import BROKER, _replay, deposit

from domain.account import Account
from domain.history import portfolio_history


@pytest.fixture
def ledger(tmp_path, fake_market):
    """A ledger with the opening row and two deposits (1000 and 500 EUR) in January 2024."""
    return _replay([deposit(date(2024, 1, 2), 1000), deposit(date(2024, 1, 3), 500)], tmp_path)


def test_transactions_leave_out_the_opening_row(ledger):
    """transactions are the two deposits; the opening row is not one of them."""
    account = Account(1, BROKER, "", ledger)

    assert list(account.transactions["operation"]) == ["Deposit", "Deposit"]
    assert account.has_transactions


def test_a_new_account_has_no_transactions(ledger):
    """An account holding only its opening row has no transactions."""
    account = Account(1, BROKER, "", ledger.iloc[:1])

    assert account.transactions.empty
    assert not account.has_transactions


def test_last_reads_the_latest_running_total(ledger):
    """last(column) is the value in the latest row: 1500 EUR of cash after both deposits."""
    account = Account(1, BROKER, "", ledger)

    assert account.last("cash_held") == 1500.0
    assert account.last("committed_cash") == 1500.0


@pytest.mark.parametrize("df", [pd.DataFrame(), pd.DataFrame({"date": ["01-01-2000"]})],
                         ids=["empty-ledger", "missing-column"])
def test_last_is_zero_when_there_is_nothing_to_read(df):
    """With no rows, or no such column, last() gives 0.0."""
    assert Account(1, BROKER, "", df).last("cash_held") == 0.0


def test_history_keeps_an_operation_dated_on_the_ledger_start_day(tmp_path, fake_market):
    """A deposit on 01-01-2000, the opening rows' own date, still counts in the portfolio history.

    The history used to drop the first row of each account after sorting
    everything by date. With a real operation on 01-01-2000 in the first
    account, that dropped the deposit instead of the second account's
    opening row: the cash below was 500 EUR instead of 1500.
    """
    # Each ledger names its own account in every row, as real ones do.
    first_df = _replay([deposit(date(2000, 1, 1), 1000)], tmp_path / "first").assign(account="First")
    second_df = _replay([deposit(date(2024, 1, 2), 500)], tmp_path / "second").assign(account="Second")
    first = Account(1, "First", "", first_df)
    second = Account(2, "Second", "", second_df)

    history = portfolio_history("2024-01-01", "2024-01-31", [first, second])

    assert history["cash"].iloc[-1] == 1500.0
