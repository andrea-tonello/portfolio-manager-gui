"""Tests for how buys and sells are passed to the account builder (REFACTORING.md, D2 point 1).

Callers say which side the trade is on with `is_buy` and always pass the
price as a positive number. The account CSV keeps its long-standing format:
a buy row stores a negative price and negative amounts (money leaving the
account), a sell row positive ones. The conversion happens in one place,
newrow_etf_stock.
"""

from datetime import date

import numpy as np
import pytest
from test_ledger_snapshots import BROKER, NAMES, _replay, deposit

from services.operations_service import execute_etf_stock
from utils.constants import CURRENCY_EUR, DATE_FORMAT


def _trade(df, day, quantity, price, fee, *, is_buy):
    """Record a trade of AAA.MI in EUR through execute_etf_stock, the function the Operations screen calls."""
    return execute_etf_stock(
        df, BROKER, day.strftime(DATE_FORMAT), day, CURRENCY_EUR, 1.0, "AAA.MI",
        quantity, price, fee, np.nan, "Stock", is_buy=is_buy, asset_name=NAMES["AAA.MI"],
    )


@pytest.fixture
def account(tmp_path, fake_market):
    """A new account holding 5000 EUR of cash, deposited on 2 January 2024."""
    return _replay([deposit(date(2024, 1, 2), 5000)], tmp_path)


def test_buy_is_stored_with_negative_price_and_amounts(account):
    """Buying 10 shares at 100 EUR plus a 2 EUR fee stores price -100 and amounts -1000 / -1002, and spends 1002 EUR."""
    df = _trade(account, date(2024, 1, 3), 10, 100.0, 2.0, is_buy=True)

    row = df.iloc[-1]
    assert row["operation"] == "Buy"
    assert row["qt_exch"] == "+10"
    assert (row["price"], row["price_eur"]) == (-100.0, -100.0)
    assert (row["nominal_amount"], row["effective_amount"]) == (-1000.0, -1002.0)
    assert row["cash_held"] == 5000.0 - 1002.0


def test_sell_is_stored_with_positive_price_and_amounts(account):
    """Selling 5 of those shares at 120 EUR minus a 2 EUR fee stores price 120 and amounts 600 / 598."""
    df = _trade(account, date(2024, 1, 3), 10, 100.0, 2.0, is_buy=True)
    df = _trade(df, date(2024, 3, 1), 5, 120.0, 2.0, is_buy=False)

    row = df.iloc[-1]
    assert row["operation"] == "Sell"
    assert row["qt_exch"] == "-5"
    assert (row["price"], row["price_eur"]) == (120.0, 120.0)
    assert (row["nominal_amount"], row["effective_amount"]) == (600.0, 598.0)


@pytest.mark.parametrize("is_buy", [True, False], ids=["buy", "sell"])
@pytest.mark.parametrize("price", [-100.0, 0.0])
def test_price_must_be_positive(account, price, is_buy):
    """A zero or negative price is refused instead of being stored with the wrong sign.

    A caller still using the old convention (negative price for a buy) would
    otherwise write a buy with a positive price into the CSV.
    """
    with pytest.raises(ValueError):
        _trade(account, date(2024, 1, 3), 10, price, 2.0, is_buy=is_buy)
