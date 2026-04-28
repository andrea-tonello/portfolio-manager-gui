from decimal import Decimal

import pandas as pd
import numpy as np

import utils.account as aop
from utils.columns import COLUMNS
from utils.other_utils import round_half_up, D, to_money, ValidationError


def _base_row():
    return {col: np.nan for col in COLUMNS}


def _append_row(df, row):
    new_row = pd.DataFrame({k: [v] for k, v in row.items()})
    return pd.concat([df, new_row], ignore_index=True)


def newrow_cash(translator, df, date, ref_date, broker, cash, op_type, product, ticker, name):

    cash_d = D(cash)
    prev_cash_held_d = D(df["cash_held"].iloc[-1])
    prev_committed_d = D(df["committed_cash"].iloc[-1])
    prev_carryforward_d = D(df["carryforward"].iloc[-1])

    current_liq_d = prev_cash_held_d + cash_d
    if op_type in ["Deposit", "Withdrawal"]:
        historic_liq_d = prev_committed_d + cash_d
    else:
        historic_liq_d = prev_committed_d

    positions = aop.get_asset_value(translator, df, ref_date=ref_date)
    asset_value_d = sum((D(pos["value"]) for pos in positions), Decimal("0"))

    row = _base_row()
    row.update({
        "date": date,
        "account": broker,
        "operation": op_type,
        "product": product,
        "ticker": ticker,
        "asset_name": name,
        "curr": "EUR",
        "nominal_amount": to_money(cash_d),
        "effective_amount": to_money(cash_d),
        "carryforward": to_money(prev_carryforward_d),
        "pl": to_money(cash_d) if op_type in ["Dividend", "Tax"] else np.nan,
        "cash_held": to_money(current_liq_d),
        "assets_value": to_money(asset_value_d),
        "nav": to_money(asset_value_d + current_liq_d),
        "committed_cash": to_money(historic_liq_d),
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

    quantity_d = D(quantity)
    price_d = D(price)
    conv_rate_d = D(conv_rate)
    fee_d = D(fee)
    price_eur_d = price_d * conv_rate_d
    nominal_d = quantity_d * price_d * conv_rate_d
    effective_d = nominal_d - fee_d

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
        "price": to_money(price_d, "0.0001"),
        "price_eur": to_money(price_eur_d, "0.0001"),
        "nominal_amount": to_money(nominal_d),
        "fee": to_money(fee_d),
        "qt_held": results["qt_held"],
        "abp": to_money(results["abp"], "0.0001"),
        "residual_amount": to_money(results["residual_amount"]),
        "effective_amount": to_money(effective_d),
        "released_amount": to_money(results["released_amount"]),
        "gross_gain": to_money(results["gross_gain"]),
        "generated_loss": to_money(results["generated_loss"]),
        "expiry": results["expiry"],
        "carryforward": to_money(results["carryforward"]),
        "taxable_gain": to_money(results["taxable_gain"]),
        "tax_bracket": tax_rate * 100,
        "tax": to_money(results["tax"]),
        "pl": to_money(results["pl"]),
        "cash_held": to_money(results["cash_held"]),
        "assets_value": to_money(results["assets_value"]),
        "nav": to_money(results["nav"]),
        "committed_cash": to_money(df["committed_cash"].iloc[-1]),
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
    prev_qt_d = D(last_row["qt_held"])
    prev_abp_d = D(last_row["abp"])
    ratio_d = D(ratio)

    if prev_qt_d <= 0:
        raise ValidationError(translator.get("operations.split.ticker_notheld", ticker=ticker))

    new_qt_d = prev_qt_d * ratio_d
    new_abp_d = prev_abp_d / ratio_d
    residual_d = new_qt_d * new_abp_d

    # Keep the prior row's product category + asset_name + currency so downstream
    # code (categorization, display, exchange-rate lookup) treats the ticker
    # identically before and after the split.
    product = last_row.get("product")
    asset_name = last_row.get("asset_name")
    curr = last_row.get("curr", "EUR")

    current_liq_d = D(df["cash_held"].iloc[-1])
    positions = aop.get_asset_value(translator, df, current_ticker=ticker, ref_date=ref_date)
    asset_value_d = sum((D(pos["value"]) for pos in positions), Decimal("0")) + residual_d

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
        "qt_held": float(new_qt_d),
        "abp": to_money(new_abp_d, "0.0001"),
        "residual_amount": to_money(residual_d),
        "carryforward": to_money(df["carryforward"].iloc[-1]),
        "cash_held": to_money(current_liq_d),
        "assets_value": to_money(asset_value_d),
        "nav": to_money(asset_value_d + current_liq_d),
        "committed_cash": to_money(df["committed_cash"].iloc[-1]),
    })

    return _append_row(df, row)
