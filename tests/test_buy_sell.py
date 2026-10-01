"""Tests for how buys and sells are passed to the account builder (REFACTORING.md, D2 points 1-2).

Callers say which side the trade is on with `is_buy` and always pass the
price as a positive number. The account CSV keeps its long-standing format:
a buy row stores a negative price and negative amounts (money leaving the
account), a sell row positive ones. The conversion happens in one place,
newrow_etf_stock.

The currency is passed as its code, "EUR" or "USD", from the Operations
screen's dropdown down to the CSV's `curr` column.
"""

from datetime import date

import numpy as np
import pytest
from test_ledger_snapshots import BROKER, NAMES, _replay, deposit

import views.operations_view
from services import operations_service
from services.operations_service import execute_etf_stock
from utils.constants import DATE_FORMAT
from views.operations_view import OperationsView


def _trade(df, day, quantity, price, fee, *, is_buy, currency="EUR"):
    """Record a trade of AAA.MI through execute_etf_stock, the function the Operations screen calls."""
    return execute_etf_stock(
        df, BROKER, day.strftime(DATE_FORMAT), day, currency, 1.0, "AAA.MI",
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
    assert row["curr"] == "EUR"
    assert row["qt_exch"] == "+10"
    assert (row["price"], row["price_eur"]) == (-100.0, -100.0)
    assert (row["nominal_amount"], row["effective_amount"]) == (-1000.0, -1002.0)
    assert row["cash_held"] == 5000.0 - 1002.0


def test_sell_is_stored_with_positive_price_and_amounts(account):
    """Selling 5 of those shares at 120 EUR minus a 2 EUR fee stores price 120 and amounts 600 / 598.

    No tax rate is passed, so the standard 26% capital gains tax applies.
    """
    df = _trade(account, date(2024, 1, 3), 10, 100.0, 2.0, is_buy=True)
    df = _trade(df, date(2024, 3, 1), 5, 120.0, 2.0, is_buy=False)

    row = df.iloc[-1]
    assert row["operation"] == "Sell"
    assert row["qt_exch"] == "-5"
    assert (row["price"], row["price_eur"]) == (120.0, 120.0)
    assert (row["nominal_amount"], row["effective_amount"]) == (600.0, 598.0)
    assert row["tax_bracket"] == 26.0


@pytest.mark.parametrize("is_buy", [True, False], ids=["buy", "sell"])
@pytest.mark.parametrize("price", [-100.0, 0.0])
def test_price_must_be_positive(account, price, is_buy):
    """A zero or negative price is refused instead of being stored with the wrong sign.

    A caller still using the old convention (negative price for a buy) would
    otherwise write a buy with a positive price into the CSV.
    """
    with pytest.raises(ValueError):
        _trade(account, date(2024, 1, 3), 10, price, 2.0, is_buy=is_buy)


@pytest.mark.parametrize("currency", ["GBP", 1])
def test_unknown_currency_is_refused(account, currency):
    """Only "EUR" and "USD" are accepted; anything else (including the old code 1 for EUR) raises ValueError."""
    with pytest.raises(ValueError):
        _trade(account, date(2024, 1, 3), 10, 100.0, 2.0, is_buy=True, currency=currency)


# ── From the Operations screen ───────────────────────────────────────

@pytest.fixture
def open_trade_form(monkeypatch, page, state):
    """Return a function that opens one of the Operations screen's trade forms, filled in, with submitted trades recorded.

    Background work runs straight away instead of in a thread, the ticker
    check against Yahoo is skipped, and execute_etf_stock only records its
    arguments.
    """
    calls = []

    def record_trade(*args, **kwargs):
        """Stand-in for execute_etf_stock: remember the arguments and leave the account unchanged."""
        calls.append((args, kwargs))
        return args[0]

    monkeypatch.setattr(operations_service, "execute_etf_stock", record_trade)
    monkeypatch.setattr(views.operations_view, "search_tickers", lambda *args, **kwargs: [])
    monkeypatch.setattr(page, "run_thread", lambda fn, *args: fn(*args))

    state.ops_acc_idx = 1
    view = OperationsView(page, state)
    view.build()

    def open_form(tab):
        """Fill in the `tab` form ("Stock" or "ETF") with a buy of 5 UUU at 200 plus a 2 EUR fee.

        Returns (form fields, submit function, recorded calls).
        """
        form = view._es_tabs[tab]
        form["date_value"] = date(2025, 1, 10)   # after the account's last operation
        form["ticker"].value = "UUU"
        form["quantity"].value = "5"
        form["price"].value = "200"
        form["fee"].value = "2"
        return form, lambda: view._submit_es(None, tab), calls

    return open_form


@pytest.fixture
def stock_form(open_trade_form):
    """The Stock form, filled in and ready to submit (see open_trade_form)."""
    return open_trade_form("Stock")


def test_form_sends_eur_by_default(stock_form):
    """With the default currency, the trade goes out as "EUR" with exchange rate 1 and the fee unchanged."""
    form, submit, calls = stock_form

    submit()

    args, kwargs = calls[0]
    currency, conv_rate, ticker, quantity, price, fee = args[4:10]
    assert (currency, conv_rate, ticker, quantity, price, fee) == ("EUR", 1.0, "UUU", 5, 200.0, 2.0)
    assert kwargs["is_buy"] is True


def test_form_sends_usd_and_converts_a_usd_fee_to_eur(stock_form):
    """Choosing USD sends "USD" with the typed exchange rate, and a fee paid in USD is converted to EUR.

    Example: rate 0.9 USD->EUR, fee 2 USD -> 1.8 EUR.
    """
    form, submit, calls = stock_form
    form["currency_dd"].value = "USD"
    form["exch_rate"].value = "0.9"
    form["fee_currency_dd"].value = "USD"

    submit()

    args, _ = calls[0]
    currency, conv_rate, _, _, _, fee = args[4:10]
    assert (currency, conv_rate, fee) == ("USD", 0.9, 1.8)


def test_stock_form_sends_the_stock_product(stock_form):
    """A trade from the Stock form is stored with product "Stock"."""
    _, submit, calls = stock_form

    submit()

    args, _ = calls[0]
    assert args[11] == "Stock"


@pytest.mark.parametrize("picked, tax_bracket, tax_rate", [
    ("ETF-S", None, 0.26),     # equity ETF: standard 26% rate
    ("ETF-M", "12.5", 0.125),  # money-market ETF: the rate typed in the form
])
def test_etf_form_sends_the_product_code_picked(open_trade_form, picked, tax_bracket, tax_rate):
    """The ETF type picked in the form is sent as the CSV's product code, with its tax rate.

    The radio buttons' values are the product codes themselves, so no
    translation table sits between the form and the CSV. The value is set as
    the plain string the screen hands back when the user picks a type.
    """
    form, submit, calls = open_trade_form("ETF")
    form["etf_subtype"] = picked
    form["fee_mode"].value = "abp"
    if tax_bracket:
        form["tax_bracket"].value = tax_bracket

    submit()

    args, kwargs = calls[0]
    assert (args[11], kwargs["tax_rate"]) == (picked, tax_rate)
