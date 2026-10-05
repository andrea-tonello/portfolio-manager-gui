from dataclasses import dataclass
from datetime import date, datetime, timedelta

import numpy as np

from domain.newrow import newrow_cash, newrow_etf_stock, newrow_split
from services.market_data import fetch_splits
from services.market_data import fetch_ticker_name as fetch_name
from services.validation import parse_positive, validate_date
from utils.constants import CURRENCIES
from utils.other_utils import round_half_up
from domain.errors import ValidationError
from domain.ledger import ETF_PRODUCTS, Op, Product
from domain.positions import first_trade_date, unrecorded_splits
from domain.tax import DEFAULT_CAPITAL_GAINS_TAX_RATE


# The message for an amount that isn't a number above zero, by kind of cash operation.
_CASH_AMOUNT_ERRORS = {
    "deposit": "operations.cash.error_cash",
    "withdrawal": "operations.cash.error_cash",
    "dividend": "operations.cash.error_dividend",
    "charge": "operations.cash.error_charge",
}


def parse_cash_amount(kind, text):
    """Return the amount typed for a cash operation of `kind`: negative for a withdrawal, positive otherwise.

    The user always types a positive number. Raises ValidationError with the
    message for that kind when it isn't one.
    Example: parse_cash_amount("withdrawal", "100") -> -100.0.
    """
    amount = parse_positive(text, _CASH_AMOUNT_ERRORS[kind])
    return -amount if kind == "withdrawal" else amount


@dataclass(frozen=True)
class TradeInput:
    """A buy or sell typed in the ETF or Stock form, checked and ready to record."""

    is_buy: bool
    date: date
    ticker: str
    quantity: int
    price: float       # in `currency`, always positive
    currency: str      # "EUR" or "USD"
    conv_rate: float   # USD -> EUR rate; 1.0 for EUR
    fee: float         # in EUR, even when paid in USD
    ter: str | float   # an ETF's yearly cost, e.g. "0.2%"; NaN when not given
    product: Product   # the product code stored in the CSV
    tax_rate: float    # on capital gains, e.g. 0.26
    fee_mode: str      # how the fee is accounted for: "abp", "buy_loss" or "sell_loss"


def parse_trade(*, product, is_buy, day, ticker, quantity, price, fee, currency, exch_rate,
                fee_currency, ter, tax_bracket, fee_mode, ledger_df) -> TradeInput:
    """Check the values of an ETF or Stock form, in the order of its fields, and return them ready to record.

    The text arguments are what the user typed. `product` is Product.STOCK or
    the ETF type picked. `ter`, `tax_bracket` (a percentage, money-market ETFs
    only) and `fee_mode` are read only for the ETF types that use them; stocks
    always use the "abp" fee mode (the fee raises the average buy price).
    Raises ValidationError with the message of the first problem found.

    Example: quantity "5", price "200", currency "USD", exch_rate "0.9" and a
    fee of "2" USD -> quantity 5, price 200.0, conv_rate 0.9 and fee 1.8 (EUR).
    """
    if product == Product.ETF_BOND:
        raise ValidationError("operations.stock.not_implemented")
    day = validate_date(day, ledger_df=ledger_df)
    ticker = (ticker or "").strip()
    if not ticker:
        raise ValidationError("operations.stock.ticker_error")
    quantity = parse_positive(quantity, "operations.stock.qt_error", integer=True)
    price = parse_positive(price, "operations.stock.price_error")
    fee = parse_positive(fee, "operations.stock.fee_error", allow_zero=True, empty=0.0)

    conv_rate = 1.0
    if currency == "USD":
        conv_rate = parse_positive(exch_rate, "operations.stock.exch_rate_error")
        if fee_currency == "USD":
            fee = round_half_up(fee * conv_rate, decimal="0.000001")

    is_etf = product in ETF_PRODUCTS
    ter_value = ter.strip().rstrip("%") + "%" if is_etf and ter else np.nan

    tax_rate = DEFAULT_CAPITAL_GAINS_TAX_RATE
    if product == Product.ETF_MM:
        bracket = parse_positive(tax_bracket, "operations.stock.tax_bracket_error", allow_zero=True)
        if bracket > 100:
            raise ValidationError("operations.stock.tax_bracket_error")
        tax_rate = bracket / 100

    if not is_etf:
        fee_mode = "abp"
    elif not fee_mode:
        raise ValidationError("operations.stock.fee_mode_error")

    return TradeInput(is_buy, day, ticker, quantity, price, currency, conv_rate, fee,
                      ter_value, product, tax_rate, fee_mode)


def execute_cash_operation(df, broker, op_kind, date_str, ref_date,
                           amount, ticker=None, description=None, asset_name=None):
    if op_kind == "deposit_withdrawal":
        op_type = Op.DEPOSIT if amount > 0 else Op.WITHDRAWAL
        product, tk, name = Product.CASH, np.nan, np.nan

    elif op_kind == "dividend":
        if asset_name is None:
            asset_name = fetch_name(ticker)
        op_type, product, tk, name = Op.DIVIDEND, Product.DIVIDEND, ticker, asset_name

    elif op_kind == "charge":
        amount = -abs(amount)
        op_type = Op.TAX
        product = description if description else Product.TAX
        tk, name = np.nan, np.nan

    else:
        raise ValueError(f"Unknown op_kind: {op_kind}")

    return newrow_cash(df, date_str, ref_date, broker, amount,
                       op_type, product, tk, name)


def execute_etf_stock(df, broker, date_str, ref_date,
                      currency, conv_rate, ticker, quantity, price,
                      fee, ter, product_type, *, is_buy, asset_name=None,
                      tax_rate=DEFAULT_CAPITAL_GAINS_TAX_RATE, fee_mode="abp"):
    """Record a buy (`is_buy=True`) or a sell of a stock or ETF; `price` is always positive.

    `currency` is the trade's currency code, "EUR" or "USD"; `conv_rate` converts
    it to EUR (1.0 for EUR). Looks up the ticker's name on Yahoo Finance unless
    `asset_name` is given.
    """
    if currency not in CURRENCIES:
        raise ValueError(f"currency must be one of {CURRENCIES}, got {currency!r}")

    if asset_name is None:
        asset_name = fetch_name(ticker)

    return newrow_etf_stock(df, date_str, ref_date, broker,
                            currency, product_type, ticker, quantity,
                            price, conv_rate, ter, fee, is_buy=is_buy,
                            asset_name=asset_name, tax_rate=tax_rate, fee_mode=fee_mode)


def execute_split(df, broker, date_str, ref_date, ticker, ratio):
    if not isinstance(ratio, (int, float)) or not (0.001 <= ratio <= 1000):
        raise ValidationError("operations.split.ratio_error")
    return newrow_split(df, date_str, ref_date, broker, ticker, float(ratio))


def detect_unrecorded_splits(df, ticker):
    """Return the splits of `ticker` that Yahoo reports but the ledger `df` doesn't record yet.

    Each is (ISO date, ratio), oldest first, e.g. [("2024-10-15", 0.1)] for a
    1:10 reverse split. Only splits since the ticker was first traded (minus a
    day) are asked for. Used by Home to offer recording them.
    """
    if df is None or df.empty:
        return []
    first = first_trade_date(df, ticker)
    if first is None:
        return []
    splits = fetch_splits(ticker, start=first - timedelta(days=1), end=datetime.now() + timedelta(days=1))
    return unrecorded_splits(df, ticker, splits)
