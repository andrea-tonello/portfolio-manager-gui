import pandas as pd
import numpy as np

import utils.account as aop
from utils.columns import COLUMNS
from utils.other_utils import round_half_up


def _base_row():
    return {col: np.nan for col in COLUMNS}


def _append_row(df, row):
    new_row = pd.DataFrame({k: [v] for k, v in row.items()})
    return pd.concat([df, new_row], ignore_index=True)


def newrow_cash(translator, df, date, ref_date, broker, cash, op_type, product, ticker, name):

    current_liq = float(df["cash_held"].iloc[-1]) + cash

    if op_type in ["Deposit", "Withdrawal"]:
        historic_liq = float(df["committed_cash"].iloc[-1]) + cash
    else:
        historic_liq = float(df["committed_cash"].iloc[-1])

    positions = aop.get_asset_value(translator, df, ref_date=ref_date)
    asset_value = sum(pos["value"] for pos in positions)

    row = _base_row()
    row.update({
        "date": date,
        "account": broker,
        "operation": op_type,
        "product": product,
        "ticker": ticker,
        "asset_name": name,
        "curr": "EUR",
        "nominal_amount": cash,
        "effective_amount": cash,
        "carryforward": float(df["carryforward"].iloc[-1]),
        "pl": cash if op_type in ["Dividend", "Tax"] else np.nan,
        "cash_held": round_half_up(current_liq),
        "assets_value": round_half_up(asset_value),
        "nav": round_half_up(asset_value + current_liq),
        "committed_cash": round_half_up(historic_liq),
    })

    return _append_row(df, row)


def newrow_etf_stock(translator, df, date, ref_date, broker, currency, product, ticker, quantity, price, conv_rate, ter, fee, buy, asset_name_override=None):

    # BUY:  price -, buy=True
    # SELL: price +, buy=False

    if not asset_name_override:
        raise ValueError(f"asset_name_override is required for ticker '{ticker}'")
    name = asset_name_override
    asset_rows = df[df["ticker"] == ticker]
    asset_rows = asset_rows[asset_rows["operation"].isin(["Buy", "Sell"])]

    if buy:
        results = aop.buy_asset(translator, df, asset_rows, quantity, price, conv_rate, fee, ref_date, product, ticker)
    else:
        results = aop.sell_asset(translator, df, asset_rows, quantity, price, conv_rate, fee, ref_date, product, ticker)

    price_eur = price * conv_rate

    row = _base_row()
    row.update({
        "date": date,
        "account": broker,
        "operation": results["operation"],
        "product": product,
        "ticker": ticker,
        "asset_name": name,
        "ter": ter,
        "curr": currency,
        "conv_rate": f"{conv_rate:.6f}",
        "qt_exch": f"+{quantity}" if buy else f"-{quantity}",
        "price": round_half_up(price, decimal="0.0001"),
        "price_eur": round_half_up(price_eur, decimal="0.0001"),
        "nominal_amount": round_half_up(round_half_up(quantity * price) * conv_rate),
        "fee": round_half_up(fee),
        "qt_held": results["qt_held"],
        "abp": round_half_up(results["abp"], decimal="0.0001"),
        "residual_amount": round_half_up(results["residual_amount"]),
        "effective_amount": round_half_up(round_half_up(quantity * price) * conv_rate) - round_half_up(fee),
        "released_amount": round_half_up(results["released_amount"]),
        "gross_gain": round_half_up(results["gross_gain"]),
        "generated_loss": round_half_up(results["generated_loss"]),
        "expiry": results["expiry"],
        "carryforward": round_half_up(results["carryforward"]),
        "taxable_gain": round_half_up(results["taxable_gain"]),
        "tax": round_half_up(results["tax"]),
        "pl": round_half_up(results["pl"]),
        "cash_held": round_half_up(results["cash_held"]),
        "assets_value": round_half_up(results["assets_value"]),
        "nav": round_half_up(results["nav"]),
        "committed_cash": round_half_up(float(df["committed_cash"].iloc[-1])),
    })

    return _append_row(df, row)
