import numpy as np

from newrow import newrow_cash, newrow_etf_stock, newrow_split
from services.market_data import fetch_ticker_name as fetch_name
from utils.constants import CURRENCIES
from domain.errors import ValidationError


def execute_cash_operation(df, broker, op_kind, date_str, ref_date,
                           amount, ticker=None, description=None, asset_name=None):
    if op_kind == "deposit_withdrawal":
        op_type = "Deposit" if amount > 0 else "Withdrawal"
        product, tk, name = "Cash", np.nan, np.nan

    elif op_kind == "dividend":
        if asset_name is None:
            asset_name = fetch_name(ticker)
        op_type, product, tk, name = "Dividend", "Dividend", ticker, asset_name

    elif op_kind == "charge":
        amount = -abs(amount)
        op_type = "Tax"
        product = description if description else "Tax"
        tk, name = np.nan, np.nan

    else:
        raise ValueError(f"Unknown op_kind: {op_kind}")

    return newrow_cash(df, date_str, ref_date, broker, amount,
                       op_type, product, tk, name)


def execute_etf_stock(df, broker, date_str, ref_date,
                      currency, conv_rate, ticker, quantity, price,
                      fee, ter, product_type, *, is_buy, asset_name=None, tax_rate=0.26, fee_mode="abp"):
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
