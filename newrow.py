import pandas as pd
import numpy as np

import utils.account as aop
from utils.columns import COLUMNS
from utils.other_utils import round_half_up, ValidationError


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


def newrow_etf_stock(translator, df, date, ref_date, broker, currency, product, ticker, quantity, price, conv_rate, ter, fee, buy, asset_name_override=None, tax_rate=0.26, fee_mode="abp"):

    # BUY:  price -, buy=True
    # SELL: price +, buy=False

    if not asset_name_override:
        raise ValueError(f"asset_name_override is required for ticker '{ticker}'")
    name = asset_name_override
    asset_rows = df[df["ticker"] == ticker]
    asset_rows = asset_rows[asset_rows["operation"].isin(["Buy", "Sell", "Split"])]

    if buy:
        results = aop.buy_asset(translator, df, asset_rows, quantity, price, conv_rate, fee, ref_date, product, ticker, fee_mode=fee_mode)
    else:
        results = aop.sell_asset(translator, df, asset_rows, quantity, price, conv_rate, fee, ref_date, product, ticker, tax_rate=tax_rate, fee_mode=fee_mode)

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
        "tax_bracket": tax_rate * 100,
        "tax": round_half_up(results["tax"]),
        "pl": round_half_up(results["pl"]),
        "cash_held": round_half_up(results["cash_held"]),
        "assets_value": round_half_up(results["assets_value"]),
        "nav": round_half_up(results["nav"]),
        "committed_cash": round_half_up(float(df["committed_cash"].iloc[-1])),
    })

    return _append_row(df, row)


def newrow_split(translator, df, date, ref_date, broker, ticker, ratio):
    """Record a stock split as a unit-conversion row.

    A split is not a cash event: qt_held and abp are rescaled by the ratio, but
    total invested value (qt × abp) is preserved. No fees, no P&L, no tax.
    """
    asset_rows = df[df["ticker"] == ticker]
    asset_rows = asset_rows[asset_rows["operation"].isin(["Buy", "Sell", "Split"])]

    if asset_rows.empty:
        raise ValidationError(translator.get("operations.split.ticker_notheld", ticker=ticker))

    last_row = asset_rows.iloc[-1]
    prev_qt = float(last_row["qt_held"])
    prev_abp = float(last_row["abp"])

    if prev_qt <= 0:
        raise ValidationError(translator.get("operations.split.ticker_notheld", ticker=ticker))

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
    positions = aop.get_asset_value(translator, df, current_ticker=ticker, ref_date=ref_date)
    asset_value = sum(pos["value"] for pos in positions) + (new_qt * new_abp)

    row = _base_row()
    row.update({
        "date": date,
        "account": broker,
        "operation": "Split",
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
