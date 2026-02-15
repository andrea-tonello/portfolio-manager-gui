import numpy as np

from newrow import newrow_cash, newrow_etf_stock
from utils.fetch_utils import fetch_name
from utils.other_utils import round_half_up
from utils.constants import CURRENCY_EUR, CURRENCY_USD, CURRENCY_CHOICES


def execute_cash_operation(translator, df, broker, op_kind, date_str, ref_date,
                           amount, ticker=None, description=None, asset_name=None):
    if op_kind == "deposit_withdrawal":
        op_type = "Deposito" if amount > 0 else "Prelievo"
        product, tk, name = "Contanti", np.nan, np.nan

    elif op_kind == "dividend":
        if asset_name is None:
            asset_name = fetch_name(ticker)
        op_type, product, tk, name = "Dividendo", "Dividendo", ticker, asset_name

    elif op_kind == "charge":
        amount = -abs(amount)
        op_type = "Imposta"
        product = description if description else "Imposta"
        tk, name = np.nan, np.nan

    else:
        raise ValueError(f"Unknown op_kind: {op_kind}")

    return newrow_cash(translator, df, date_str, ref_date, broker, amount,
                       op_type, product, tk, name)


def execute_etf_stock(translator, df, broker, date_str, ref_date,
                      currency_int, conv_rate, ticker, quantity, price,
                      fee, ter, product_type, asset_name=None):
    currency_code = CURRENCY_CHOICES[currency_int]
    buy = price < 0

    if asset_name is None:
        asset_name = fetch_name(ticker)

    return newrow_etf_stock(translator, df, date_str, ref_date, broker,
                            currency_code, product_type, ticker, quantity,
                            price, conv_rate, ter, fee, buy,
                            asset_name_override=asset_name)
