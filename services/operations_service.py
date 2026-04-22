import numpy as np

from newrow import newrow_cash, newrow_etf_stock, newrow_split
from services.market_data import fetch_ticker_name as fetch_name
from utils.constants import CURRENCY_CHOICES
from utils.other_utils import ValidationError


def execute_cash_operation(translator, df, broker, op_kind, date_str, ref_date,
                           amount, ticker=None, description=None, asset_name=None):
    if op_kind == "deposit_withdrawal":
        op_type = "Deposit" if amount > 0 else "Withdrawal"
        product, tk, name = "Cash", np.nan, np.nan

    elif op_kind == "dividend":
        if asset_name is None:
            asset_name = fetch_name(ticker, err=translator.get("operations.stock.ticker_notfound", ticker=ticker))
        op_type, product, tk, name = "Dividend", "Dividend", ticker, asset_name

    elif op_kind == "charge":
        amount = -abs(amount)
        op_type = "Tax"
        product = description if description else "Tax"
        tk, name = np.nan, np.nan

    else:
        raise ValueError(f"Unknown op_kind: {op_kind}")

    return newrow_cash(translator, df, date_str, ref_date, broker, amount,
                       op_type, product, tk, name)


def execute_etf_stock(translator, df, broker, date_str, ref_date,
                      currency_int, conv_rate, ticker, quantity, price,
                      fee, ter, product_type, asset_name=None, tax_rate=0.26, fee_mode="abp"):
    currency_code = CURRENCY_CHOICES[currency_int]
    buy = price < 0

    if asset_name is None:
        asset_name = fetch_name(ticker, err=translator.get("operations.stock.ticker_notfound", ticker=ticker))

    return newrow_etf_stock(translator, df, date_str, ref_date, broker,
                            currency_code, product_type, ticker, quantity,
                            price, conv_rate, ter, fee, buy,
                            asset_name_override=asset_name, tax_rate=tax_rate, fee_mode=fee_mode)


def execute_split(translator, df, broker, date_str, ref_date, ticker, ratio):
    if not isinstance(ratio, (int, float)) or ratio <= 0 or ratio > 1000 or ratio < 0.001:
        raise ValidationError(translator.get("operations.split.ratio_error"))
    return newrow_split(translator, df, date_str, ref_date, broker, ticker, float(ratio))
