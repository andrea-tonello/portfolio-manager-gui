"""Builders of new ledger rows: each takes an account's ledger and returns it with one more row.

operations_service calls them when the user records a cash operation, a
trade or a split.
"""

from datetime import date

import pandas as pd
import numpy as np

from domain.errors import ValidationError
from domain.ledger import Op, TextCell, base_row, holding_rows
from domain.positions import priced_positions
from domain.tax import DEFAULT_CAPITAL_GAINS_TAX_RATE, buy_asset, sell_asset
from utils.date_utils import DateLike
from utils.other_utils import round_half_up


def _append_row(df, row):
    new_row = pd.DataFrame({k: [v] for k, v in row.items()})
    return pd.concat([df, new_row], ignore_index=True)


def newrow_cash(df: pd.DataFrame, date_str: str, ref_date: DateLike, broker: str, cash: float, op_type: Op,
                product: str, ticker: TextCell, name: TextCell) -> pd.DataFrame:

    current_liq = float(df["cash_held"].iloc[-1]) + cash

    if op_type in (Op.DEPOSIT, Op.WITHDRAWAL):
        historic_liq = float(df["committed_cash"].iloc[-1]) + cash
    else:
        historic_liq = float(df["committed_cash"].iloc[-1])

    positions = priced_positions(df, ref_date)
    asset_value = sum(pos["value"] for pos in positions)

    row = base_row()
    row.update({
        "date": date_str,
        "account": broker,
        "operation": op_type,
        "product": product,
        "ticker": ticker,
        "asset_name": name,
        "curr": "EUR",
        "nominal_amount": cash,
        "effective_amount": cash,
        "carryforward": float(df["carryforward"].iloc[-1]),
        "pl": cash if op_type in (Op.DIVIDEND, Op.TAX) else np.nan,
        "cash_held": round_half_up(current_liq),
        "assets_value": round_half_up(asset_value),
        "nav": round_half_up(asset_value + current_liq),
        "committed_cash": round_half_up(historic_liq),
    })

    return _append_row(df, row)


def newrow_etf_stock(df: pd.DataFrame, date_str: str, ref_date: date, broker: str, currency: str, product: str,
                     ticker: str, quantity: int, price: float, conv_rate: float, ter: TextCell, fee: float, *,
                     is_buy: bool, asset_name: str, tax_rate: float = DEFAULT_CAPITAL_GAINS_TAX_RATE,
                     fee_mode: str = "abp") -> pd.DataFrame:
    """Record a buy or a sell of `quantity` units of `ticker` and return the account with the new row.

    `price` is the price of one unit in `currency`, always positive; `is_buy`
    says which side the trade is on. The row follows the CSV's sign convention,
    applied only here: money leaving the account is negative, so a buy stores a
    negative price and negative amounts, a sell positive ones.

    Example: buying 10 units at 100 EUR with a 2 EUR fee stores price -100,
    nominal_amount -1000 and effective_amount -1002; selling the 10 units at
    120 EUR with the same fee stores 120, 1200 and 1198.
    """
    if price <= 0:
        raise ValueError(f"price must be positive (got {price}); use is_buy to tell a buy from a sell")
    if not asset_name:
        raise ValueError(f"asset_name is required for ticker '{ticker}'")
    asset_rows = holding_rows(df, ticker)

    if is_buy:
        results = buy_asset(df, asset_rows, quantity, price, conv_rate, fee, ref_date, product, ticker, fee_mode=fee_mode)
    else:
        results = sell_asset(df, asset_rows, quantity, price, conv_rate, fee, ref_date, product, ticker, tax_rate=tax_rate, fee_mode=fee_mode)

    # The CSV stores money leaving the account as negative: a buy's price and amounts.
    signed_price = -price if is_buy else price
    price_eur = signed_price * conv_rate

    row = base_row()
    row.update({
        "date": date_str,
        "account": broker,
        "operation": results["operation"],
        "product": product,
        "ticker": ticker,
        "asset_name": asset_name,
        "ter": ter,
        "curr": currency,
        "conv_rate": f"{conv_rate:.6f}",
        "qt_exch": f"+{quantity}" if is_buy else f"-{quantity}",
        "price": round_half_up(signed_price, decimal="0.0001"),
        "price_eur": round_half_up(price_eur, decimal="0.0001"),
        "nominal_amount": round_half_up(round_half_up(quantity * signed_price) * conv_rate),
        "fee": round_half_up(fee),
        "qt_held": results["qt_held"],
        "abp": round_half_up(results["abp"], decimal="0.0001"),
        "residual_amount": round_half_up(results["residual_amount"]),
        "effective_amount": round_half_up( round_half_up(round_half_up(quantity * signed_price) * conv_rate) - round_half_up(fee) ),
        "released_amount": round_half_up(results["released_amount"]),
        "gross_gain": round_half_up(results["gross_gain"]),
        "generated_loss": round_half_up(results["generated_loss"]),
        "expiry": results["expiry"],
        "carryforward": round_half_up(results["carryforward"]),
        "taxable_gain": round_half_up(results["taxable_gain"]),
        "tax_bracket": tax_rate * 100,
        "tax": round_half_up(results["tax"]),
        "pl": round_half_up(results["pl"]),
        "cash_held": round_half_up(results["cash_held"]),
        "assets_value": round_half_up(results["assets_value"]),
        "nav": round_half_up(results["nav"]),
        "committed_cash": round_half_up(float(df["committed_cash"].iloc[-1])),
    })

    return _append_row(df, row)


def newrow_split(df: pd.DataFrame, date_str: str, ref_date: DateLike, broker: str, ticker: str,
                 ratio: float) -> pd.DataFrame:
    """Record a stock split as a unit-conversion row.

    A split is not a cash event: qt_held and abp are rescaled by the ratio, but
    total invested value (qt × abp) is preserved. No fees, no P&L, no tax.
    """
    asset_rows = holding_rows(df, ticker)

    if asset_rows.empty:
        raise ValidationError("operations.split.ticker_notheld", ticker=ticker)

    last_row = asset_rows.iloc[-1]
    prev_qt = float(last_row["qt_held"])
    prev_abp = float(last_row["abp"])

    if prev_qt <= 0:
        raise ValidationError("operations.split.ticker_notheld", ticker=ticker)

    new_qt = prev_qt * ratio
    new_abp = prev_abp / ratio
    residual = new_qt * new_abp

    # Keep the prior row's product category + asset_name + currency so downstream
    # code (categorization, display, exchange-rate lookup) treats the ticker
    # identically before and after the split.
    product = last_row.get("product")
    asset_name = last_row.get("asset_name")
    curr = last_row.get("curr", "EUR")

    current_liq = float(df["cash_held"].iloc[-1])
    positions = priced_positions(df, ref_date, exclude_ticker=ticker)
    asset_value = sum(pos["value"] for pos in positions) + (new_qt * new_abp)

    row = base_row()
    row.update({
        "date": date_str,
        "account": broker,
        "operation": Op.SPLIT,
        "product": product,
        "ticker": ticker,
        "asset_name": asset_name,
        "curr": curr,
        "qt_exch": f"{ratio:g}",
        "qt_held": new_qt,
        "abp": round_half_up(new_abp, decimal="0.0001"),
        "residual_amount": round_half_up(residual),
        "carryforward": round_half_up(float(df["carryforward"].iloc[-1])),
        "cash_held": round_half_up(current_liq),
        "assets_value": round_half_up(asset_value),
        "nav": round_half_up(asset_value + current_liq),
        "committed_cash": round_half_up(float(df["committed_cash"].iloc[-1])),
    })

    return _append_row(df, row)
