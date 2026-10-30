"""Tests for how buys and sells are recorded (REFACTORING.md, D2 points 1-2).

Callers say which side the trade is on with the operation's kind, buy or
sell, and always pass the price as a positive number. The account CSV keeps
its long-standing format: a buy row stores a negative price and negative
amounts (money leaving the account), a sell row positive ones. The
conversion happens in one place, newrow_etf_stock.

The currency is passed as its code, "EUR" or "USD", from the Operations
screen's dropdown down to the CSV's `curr` column.
"""

from datetime import date, timedelta

import pytest
from conftest import account_of, applied, snack_texts
from test_ledger_snapshots import BROKER, NAMES, _replay, buy, deposit

import views.operations_view
from domain.journal import Kind
from services import journal_service
from views.operations_view import OperationsView


def _trade(account, day, quantity, price, fee, *, is_buy, currency="EUR"):
    """Record a trade of AAA.MI through journal_service.record, as the Operations screen does; return the new ledger."""
    accounts = {account.idx: account}
    applied(accounts, journal_service.record(
        accounts, account, Kind.BUY if is_buy else Kind.SELL, day,
        ticker="AAA.MI", asset_name=NAMES["AAA.MI"], product="Stock", currency=currency, conv_rate=1.0,
        quantity=quantity, price=price, fee=fee, fee_mode="abp", tax_rate=0.26, ter=None,
    ))
    return account.df


@pytest.fixture
def account(fake_market):
    """A new account holding 5000 EUR of cash, deposited on 2 January 2024."""
    return account_of(1, BROKER, [deposit(date(2024, 1, 2), 5000)])


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
    """Selling 5 of those shares at 120 EUR minus a 2 EUR fee stores price 120 and amounts 600 / 598, taxed at 26%."""
    _trade(account, date(2024, 1, 3), 10, 100.0, 2.0, is_buy=True)
    df = _trade(account, date(2024, 3, 1), 5, 120.0, 2.0, is_buy=False)

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
def open_trade_form(monkeypatch, app, page, state):
    """Return a function that opens one of the Operations screen's trade forms, filled in, with submitted trades recorded.

    Background work runs straight away instead of in a thread, the checks
    against Yahoo (the ticker's kind and name) are skipped, and
    journal_service.record only records its arguments.
    """
    calls = []

    def record(accounts, account, kind, day, **fields):
        """Stand-in for journal_service.record: remember the operation and change no account."""
        calls.append((kind, fields))
        return {}

    monkeypatch.setattr(journal_service, "record", record)
    monkeypatch.setattr(views.operations_view, "search_tickers", lambda *args, **kwargs: [])
    monkeypatch.setattr(views.operations_view, "fetch_ticker_name", lambda ticker: NAMES[ticker])
    monkeypatch.setattr(page, "run_thread", lambda fn, *args: fn(*args))

    state.ops_acc_idx = 1
    view = OperationsView(app)
    view.build()

    def open_form(tab):
        """Fill in the `tab` form ("Stock" or "ETF") with a buy of 5 UUU at 200 plus a 2 EUR fee.

        Returns (form, submit function, recorded calls).
        """
        form = {"ETF": view.etf, "Stock": view.stock}[tab]
        form.date.value = date(2025, 1, 10)   # after the account's last operation
        form.ticker.value = "UUU"
        form.quantity.value = "5"
        form.price.value = "200"
        form.fee.value = "2"
        return form, lambda: form.submit(None), calls

    return open_form


@pytest.fixture
def stock_form(open_trade_form):
    """The Stock form, filled in and ready to submit (see open_trade_form)."""
    return open_trade_form("Stock")


def _sent(calls, *names):
    """The values of the fields `names` of the one trade recorded."""
    [(_, fields)] = calls
    return tuple(fields[name] for name in names)


def test_form_sends_eur_by_default(stock_form):
    """With the default currency, the trade goes out as a buy in "EUR" with exchange rate 1 and the fee unchanged.

    The asset's name comes from Yahoo.
    """
    form, submit, calls = stock_form

    submit()

    assert calls[0][0] == Kind.BUY
    assert _sent(calls, "currency", "conv_rate", "ticker", "asset_name", "quantity", "price", "fee") == (
        "EUR", 1.0, "UUU", "Uniform Corp", 5, 200.0, 2.0)


def test_form_sends_usd_and_converts_a_usd_fee_to_eur(stock_form):
    """Choosing USD sends "USD" with the typed exchange rate, and a fee paid in USD is converted to EUR.

    Example: rate 0.9 USD->EUR, fee 2 USD -> 1.8 EUR.
    """
    form, submit, calls = stock_form
    form.currency.value = "USD"
    form.exch_rate.value = "0.9"
    form.fee_currency.value = "USD"

    submit()

    assert _sent(calls, "currency", "conv_rate", "fee") == ("USD", 0.9, 1.8)


@pytest.mark.parametrize("picked, tax_bracket, tax_rate", [
    ("ETF-S", None, 0.26),     # equity ETF: standard 26% rate
    ("ETF-M", "12.5", 0.125),  # money-market ETF: the rate typed in the form
])
def test_etf_form_sends_the_product_code_picked(open_trade_form, picked, tax_bracket, tax_rate):
    """The ETF type picked in the form is sent as the CSV's product code, with its tax rate.

    The segments' values are the product codes themselves, so no
    translation table sits between the form and the CSV. The value is set as
    the plain string the screen hands back when the user picks a type.
    """
    form, submit, calls = open_trade_form("ETF")
    form.etf_subtype.selected = [picked]
    form.fee_mode.value = "abp"
    if tax_bracket:
        form.tax_bracket.value = tax_bracket

    submit()

    assert _sent(calls, "product", "tax_rate") == (picked, tax_rate)


@pytest.mark.parametrize("is_sell, card, fee_mode", [
    (False, "_fee_now_card", "loss"),
    (False, "_fee_later_card", "pending"),
    (True, None, "loss"),
], ids=["buy-now", "buy-when-selling", "sell"])
def test_etf_form_sends_the_tax_carryforward_choice(open_trade_form, is_sell, card, fee_mode):
    """With the Tax Carryforward option, a buy sends the card tapped and a sale always "loss".

    The buy's cards: add the fee to the carryforward now ("loss"), or when the
    ETF is sold ("pending"). A sale has no cards: its fee, and any pending
    ones, are worked out by sell_asset.
    """
    form, submit, calls = open_trade_form("ETF")
    form.fee_mode.value = "loss"
    form.side_switch.value = is_sell
    form.sell_ticker.value = "UUU"  # a sale reads its ticker from the list of assets held
    if card:
        getattr(form, card).content.on_click(None)

    submit()

    assert _sent(calls, "fee_mode") == (fee_mode,)


def _flip_to_sell(form):
    """Move the form's switch to Sell, as a tap on it does."""
    form.side_switch.value = True
    form.side_switch.on_change(None)


def test_a_sale_offers_only_the_assets_still_held(open_trade_form, page):
    """On a sale the ticker is picked among the tab's assets held; with none, the form says so and stays on buy.

    The test account still holds 20 BBB.MI and has sold all its AAA.MI, both
    stocks: the Stock tab lists BBB.MI alone, and the ETF tab has nothing to sell.
    """
    stock, _, _ = open_trade_form("Stock")
    etf, _, _ = open_trade_form("ETF")

    _flip_to_sell(stock)
    _flip_to_sell(etf)

    assert [option.key for option in stock.sell_ticker.options] == ["BBB.MI"]
    assert (stock.sell_ticker.visible, stock.ticker.control.visible) == (True, False)
    assert etf.side_switch.value is False
    assert snack_texts(page) == ["Nothing to sell: this account holds no ETFs"]


def test_picking_the_asset_to_sell_sets_its_etf_type_and_currency(app, state, tmp_path, fake_market):
    """Each tab lists its own kind of asset, and picking one sets the form to how it was bought.

    The account holds a money-market ETF and a stock in USD. Picking the ETF
    selects the money-market type (which shows the tax bracket field); picking
    the stock selects USD (which asks for the exchange rate).
    """
    state.get_account(1).df = _replay([
        deposit(date(2024, 1, 2), 5000),
        buy(date(2024, 1, 3), "MMM.MI", 100, price=10.0, fee=0.0, product="ETF-M", ter="0.1%"),
        buy(date(2024, 1, 4), "UUU", 5, price=200.0, fee=1.0, currency="USD", conv_rate=0.9),
    ], tmp_path / "held")
    state.ops_acc_idx = 1
    view = OperationsView(app)
    view.build()
    for form, ticker in ((view.etf, "MMM.MI"), (view.stock, "UUU")):
        _flip_to_sell(form)
        assert [option.key for option in form.sell_ticker.options] == [ticker]
        form.sell_ticker.value = ticker
        form.sell_ticker.on_select(None)

    assert (view.etf.etf_subtype.selected, view.etf._tax_row.visible) == (["ETF-M"], True)
    assert (view.stock.currency.value, view.stock.exch_rate.visible) == ("USD", True)


def test_a_blank_fee_is_recorded_as_zero(stock_form):
    """The fee is optional: left empty, the trade is recorded with no fee."""
    form, submit, calls = stock_form
    form.fee.value = ""

    submit()

    assert _sent(calls, "fee") == (0.0,)


@pytest.mark.parametrize("tab, changes, message", [
    ("Stock", {"date": None}, "Date is missing"),
    ("Stock", {"date": date.today() + timedelta(days=1)}, "Cannot insert future dates"),
    ("Stock", {"date": date(1999, 12, 31)}, "The date cannot be earlier than 01-01-2000"),
    ("Stock", {"ticker": " "}, "Ticker is missing"),
    ("Stock", {"quantity": "5.5"}, "The quantity must be an integer greater than 0"),
    ("Stock", {"quantity": "0"}, "The quantity must be an integer greater than 0"),
    ("Stock", {"price": "0"}, "The price must be greater than 0"),
    ("Stock", {"fee": "1.2.3"}, "The fee must be a number greater than or equal to 0"),
    ("Stock", {"currency": "USD", "exch_rate": ""}, "The conversion rate must be a number greater than 0"),
    ("ETF", {"etf_subtype": "ETF-M", "tax_bracket": "150"}, "The tax bracket must be a number between 0 and 100"),
    ("ETF", {}, "Please select a fee management mode"),
    ("ETF", {"fee_mode": "loss"}, "Please select a fee management mode"),  # a buy, but no card tapped
], ids=["no-date", "future", "before-the-accounts-opening", "no-ticker", "fractional-quantity", "zero-quantity",
        "zero-price", "bad-fee", "usd-without-rate", "tax-bracket-over-100", "etf-without-fee-mode",
        "etf-buy-without-fee-card"])
def test_form_refuses_invalid_values(open_trade_form, page, tab, changes, message):
    """Each invalid value shows its own message, and nothing is recorded.

    A date can come before the account's last operation (02-09-2024), but not
    before 01-01-2000, the day every account opens on.
    """
    form, submit, calls = open_trade_form(tab)
    for field, value in changes.items():
        if field == "etf_subtype":
            form.etf_subtype.selected = [value]
        else:
            getattr(form, field).value = value

    submit()

    assert calls == []
    assert snack_texts(page) == [message]


def test_a_ticker_of_the_wrong_kind_is_refused(stock_form, page, monkeypatch):
    """Buying an ETF ticker from the Stock form shows an error and records nothing; the spinner goes away.

    Yahoo is asked what kind of security the ticker is before the trade is saved.
    """
    form, submit, calls = stock_form
    monkeypatch.setattr(views.operations_view, "search_tickers",
                        lambda *args, **kwargs: [{"symbol": "UUU", "quote_type": "etf"}])

    submit()

    assert calls == []
    assert snack_texts(page) == ["This Ticker is not comprised in this asset class"]
    assert form.loading.visible is False
