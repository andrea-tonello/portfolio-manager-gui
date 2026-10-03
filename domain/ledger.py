"""What an account ledger contains: its rows, the names it stores, and how to select rows.

Each account is a CSV file with one row per operation (columns in
utils/columns.py), starting with an opening row. Op and Product list the
exact strings stored in its `operation` and `product` columns. They are
StrEnums, so Op.BUY == "Buy" is True: values read back from a CSV compare
equal to them, and writing them stores the same plain strings as before.
"""

from datetime import datetime
from enum import StrEnum

import numpy as np
import pandas as pd

from domain.errors import ValidationError
from utils.columns import COLUMNS
from utils.constants import DATE_FORMAT

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


def base_row():
    """Return an empty ledger row: every column of utils/columns.py set to NaN, ready to be filled in."""
    return {col: np.nan for col in COLUMNS}


def opening_row(broker_name):
    """Return the first row of a new account called `broker_name`: dated LEDGER_START_DATE, every total at zero."""
    row = base_row()
    row.update({
        "date": LEDGER_START_DATE.strftime(DATE_FORMAT),
        "account": broker_name,
        "carryforward": 0.0,
        "cash_held": 0,
        "assets_value": 0,
        "nav": 0.0,
        "committed_cash": 0.0,
    })
    return row


def get_pf_date(account, dt, ref_date):
    """Returns (account's rows up to `ref_date`, date of its first operation).

    The rows are a copy, with the "date" column parsed to datetimes. The first
    operation is the account's first transaction; it is None if there is none
    on or before `ref_date`. `dt` is only used in the error message raised
    when no row is on or before `ref_date`.
    """
    df = account.df.copy()
    df["date"] = pd.to_datetime(df["date"], dayfirst=True, errors="coerce")
    ref_date = pd.Timestamp(ref_date)
    df_valid = df[df["date"] <= ref_date]
    if df_valid.empty:
        raise ValidationError("misc_errors.nodates", dt=dt)
    first_dates = pd.to_datetime(account.transactions["date"].iloc[:1], dayfirst=True, errors="coerce")
    first_date = first_dates.iloc[0] if not first_dates.empty and first_dates.iloc[0] <= ref_date else None
    return df_valid, first_date
