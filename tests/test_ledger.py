"""Tests for domain/ledger.py: the names stored in the account CSV's `operation` and `product` columns.

Op and Product are StrEnums, so Op.BUY == "Buy": code can use the names while
the CSV keeps storing the same plain strings it always has.
"""

from pathlib import Path

import pandas as pd
import pytest

from domain.ledger import ETF_PRODUCTS, Op, Product, holding_rows
from utils.columns import OPERATION_LOCALE_KEYS, PRODUCT_LOCALE_KEYS

SNAPSHOTS = Path(__file__).resolve().parent / "snapshots"


@pytest.mark.parametrize("name", ["stocks_eur.csv", "etfs_and_usd.csv"])
def test_names_match_what_the_csv_stores(name):
    """Every operation and product in the snapshot ledgers is one of the names.

    The exception is a Tax row's product, which holds the user's own
    description of the charge (here "Stamp duty").
    """
    df = pd.read_csv(SNAPSHOTS / name)

    assert set(df["operation"].dropna()) <= set(Op)
    not_tax = df["operation"] != Op.TAX
    assert set(df.loc[not_tax, "product"].dropna()) <= set(Product)


def test_every_name_can_be_translated():
    """Each operation and product has a locale key, so the Transactions table and CSV export can show it."""
    assert set(OPERATION_LOCALE_KEYS) == set(Op)
    assert set(PRODUCT_LOCALE_KEYS) == set(Product)


def test_etf_products_are_the_three_etf_types():
    """ETF_PRODUCTS holds the equity, money-market and bond ETF codes (they share special tax rules)."""
    assert ETF_PRODUCTS == {"ETF-S", "ETF-M", "ETF-B"}


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
