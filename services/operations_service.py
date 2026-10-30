"""Checking what the user typed in the Operations forms, before the operation is recorded through the journal.

Each parse_* function turns a form's text into the values of an operation,
or raises ValidationError with the message of the first problem found. The
screens then record the operation with journal_service.record.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

import pandas as pd

from services.market_data import fetch_splits
from services.validation import parse_positive, validate_date
from utils.formatting import fmt_eur
from utils.other_utils import round_half_up
from domain.account import Account
from domain.errors import ValidationError
from domain.ledger import ETF_PRODUCTS, Product
from domain.positions import first_trade_date, unrecorded_splits
from domain.tax import DEFAULT_CAPITAL_GAINS_TAX_RATE


# The message for an amount that isn't a number above zero, by kind of cash operation.
_CASH_AMOUNT_ERRORS = {
    "deposit": "operations.cash.error_cash",
    "withdrawal": "operations.cash.error_cash",
    "dividend": "operations.cash.error_dividend",
    "charge": "operations.cash.error_charge",
}

# The split ratios accepted: from a 1:1000 reverse split to a 1000:1 split.
_SPLIT_RATIOS = (0.001, 1000)


def parse_cash_amount(kind: str, text: str | None) -> float:
    """Return the amount typed for a cash operation of `kind`, always positive: the kind gives it its sign.

    Raises ValidationError with the message for that kind when it isn't a
    number above 0. Example: parse_cash_amount("withdrawal", "100") -> 100.0,
    stored as -100 by the withdrawal's row.
    """
    return parse_positive(text, _CASH_AMOUNT_ERRORS[kind])


def parse_split_ratio(text: str | None) -> float:
    """Return the split ratio typed: how many new shares replace one, e.g. 2.0 for 2:1, 0.5 for a 1:2 reverse split.

    Raises ValidationError("operations.split.ratio_error") for anything but
    a number from 0.001 to 1000.
    """
    return check_split_ratio(parse_positive(text, "operations.split.ratio_error"))


def check_split_ratio(ratio: float) -> float:
    """Return `ratio` if it is a split ratio the app accepts, from 0.001 to 1000; else raise ValidationError.

    Also for the splits found on Yahoo: a bad event there (e.g. 1 for 5000)
    would otherwise cut the holding 5000-fold in every row after it.
    """
    if not _SPLIT_RATIOS[0] <= ratio <= _SPLIT_RATIOS[1]:
        raise ValidationError("operations.split.ratio_error")
    return ratio


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
    ter: str | None    # an ETF's yearly cost, e.g. "0.2%"; None when not given
    product: str       # the product code stored in the CSV, a Product value such as "ETF-M"
    tax_rate: float    # on capital gains, e.g. 0.26
    fee_mode: str      # how the fee is accounted for: "abp", "loss" or "pending" (see buy_asset)


def parse_trade(*, product: str, is_buy: bool, day: date | None, ticker: str | None, quantity: str | None,
                price: str | None, fee: str | None, currency: str, exch_rate: str | None, fee_currency: str,
                ter: str | None, tax_bracket: str | None, fee_mode: str | None,
                ledger_df: pd.DataFrame) -> TradeInput:
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
    ter_value = ter.strip().rstrip("%") + "%" if is_etf and ter else None

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


def parse_transfer(source_df: pd.DataFrame, recipient: Account | None, day: date, text: str | None) -> float:
    """Check a transfer of cash from the account whose ledger is `source_df` to `recipient`; return its amount.

    `day` must already be checked against the source's ledger, as for every
    operation. Raises ValidationError for the first problem: no recipient
    chosen; `day` earlier than the recipient's last operation (its rows must
    stay in date order too); an amount that isn't a number above 0; more than
    the cash the source holds, which is its last row's since `day` comes after it.

    Example: with 4,584.10 EUR held, "5000" raises
    ValidationError("operations.transfer.not_enough_cash", available="4,584.10€").
    """
    if recipient is None:
        raise ValidationError("operations.transfer.no_recipient")
    recipient_dates = pd.to_datetime(recipient.df["date"], dayfirst=True, errors="coerce").dropna()
    if not recipient_dates.empty and day < recipient_dates.max().date():
        raise ValidationError("operations.transfer.date_recipient", account=recipient.name)
    amount = parse_positive(text, "operations.cash.error_cash")
    available = float(source_df["cash_held"].iloc[-1])
    if amount > available:
        raise ValidationError("operations.transfer.not_enough_cash", available=fmt_eur(available))
    return amount


def detect_unrecorded_splits(df: pd.DataFrame | None, ticker: str) -> list[tuple[str, float]]:
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
