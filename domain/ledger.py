"""The names an account ledger stores, and how to pick out the rows that hold assets.

Each account is a CSV file with one row per operation (columns in
utils/columns.py). Op and Product list the exact strings stored in its
`operation` and `product` columns. They are StrEnums, so Op.BUY == "Buy" is
True: values read back from a CSV compare equal to them, and writing them
stores the same plain strings as before.
"""

from datetime import datetime
from enum import StrEnum

# Date of every account's opening row (all totals at zero). Nothing can be
# recorded before it, so the app's date pickers start here too.
LEDGER_START_DATE = datetime(2000, 1, 1)


class Op(StrEnum):
    """Values of the `operation` column: what a row records."""

    DEPOSIT = "Deposit"
    WITHDRAWAL = "Withdrawal"
    BUY = "Buy"
    SELL = "Sell"
    SPLIT = "Split"
    DIVIDEND = "Dividend"
    TAX = "Tax"  # a tax or fee paid from cash, e.g. stamp duty


class Product(StrEnum):
    """Values of the `product` column: the kind of asset (or cash movement) a row is about.

    A Tax row may instead hold the user's own description of the charge,
    e.g. "Stamp duty".
    """

    CASH = "Cash"
    STOCK = "Stock"
    ETF_STOCK = "ETF-S"  # equity ETF
    ETF_MM = "ETF-M"     # money-market ETF
    ETF_BOND = "ETF-B"   # bond ETF
    DIVIDEND = "Dividend"
    TAX = "Tax"


# ETFs follow their own Italian tax rules: their gains can't be offset by the
# carryforward (past losses), and their fees can be recorded as losses.
ETF_PRODUCTS = {Product.ETF_STOCK, Product.ETF_MM, Product.ETF_BOND}

# Operations that change how many units of an asset are held.
_HOLDING_OPS = (Op.BUY, Op.SELL, Op.SPLIT)


def holding_rows(df, ticker=None):
    """Return the rows of `df` that change how many units are held: buys, sells and splits.

    With `ticker`, only that asset's rows. Rows keep their original index. The
    last of an asset's rows holds its current quantity (`qt_held`) and average
    buy price (`abp`).
    """
    rows = df[df["operation"].isin(_HOLDING_OPS)]
    if ticker is not None:
        rows = rows[rows["ticker"] == ticker]
    return rows
