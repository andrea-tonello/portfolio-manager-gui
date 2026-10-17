"""Tests for domain/ledger.py: the names stored in the account CSV's `operation` and `product` columns.

Op and Product are StrEnums, so Op.BUY == "Buy": code can use the names while
the CSV keeps storing the same plain strings it always has.
"""

import pandas as pd

from domain.ledger import Op, Product, holding_rows
from utils.columns import OPERATION_LOCALE_KEYS, PRODUCT_LOCALE_KEYS


def test_every_name_can_be_translated():
    """Each operation and product has a locale key, so the Transactions table and CSV export can show it."""
    assert set(OPERATION_LOCALE_KEYS) == set(Op)
    assert set(PRODUCT_LOCALE_KEYS) == set(Product)


LEDGER = pd.DataFrame({
    "operation": ["Deposit", "Buy", "Buy", "Dividend", "Split", "Sell", "Tax", "Withdrawal"],
    "ticker": [None, "AAA.MI", "BBB.MI", "AAA.MI", "AAA.MI", "BBB.MI", None, None],
})


def test_holding_rows_keeps_buys_sells_and_splits():
    """Only rows that change how many units are held are kept (a dividend doesn't), with their original index."""
    rows = holding_rows(LEDGER)

    assert list(rows.index) == [1, 2, 4, 5]


def test_holding_rows_for_one_ticker():
    """With a ticker, only that asset's buys, sells and splits are kept."""
    rows = holding_rows(LEDGER, "AAA.MI")

    assert list(rows.index) == [1, 4]
