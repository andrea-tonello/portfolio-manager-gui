"""Italian capital gains tax rules, applied when an asset is bought or sold.

buy_asset and sell_asset work out a trade's effect on the asset (quantity,
average buy price), on taxes and on the carryforward ("zainetto fiscale": past
losses that can offset future gains until 31 December of the fourth year
after the loss), and on cash. compute_carryforward rebuilds the carryforward
from the ledger.
"""

from datetime import datetime

import numpy as np
import pandas as pd
from dateutil.relativedelta import relativedelta

from domain.errors import ValidationError
from domain.ledger import ETF_PRODUCTS, Op
from domain.positions import priced_positions
from utils.constants import DATE_FORMAT
from utils.other_utils import round_down, round_half_up

# Rate applied to a sale's taxable gain (gain minus any carryforward used).
# Money-market ETFs can be taxed at a different rate, typed by the user in the
# Operations form (e.g. 12.5% for those holding mainly government bonds).
DEFAULT_CAPITAL_GAINS_TAX_RATE = 0.26


def add_solar_years(loss_date):
    four_years_later = loss_date + relativedelta(years=4)
    expiry = datetime(four_years_later.year, 12, 31)
    return expiry.strftime(DATE_FORMAT)


def buy_asset(df, asset_rows, quantity, price, conv_rate, fee, ref_date, product, ticker, fee_mode="abp"):

    price_eur = price * conv_rate
    fee = round_half_up(fee)
    abp = 0
    current_qt = quantity

    fee_in_cost = fee if fee_mode == "abp" else 0

    if asset_rows.empty:
        abp = (price_eur * quantity + fee_in_cost) / quantity
    else:
        last_abp = asset_rows["abp"].iloc[-1]
        last_remaining_qt = asset_rows["qt_held"].iloc[-1]

        old_cost = last_abp * last_remaining_qt
        new_cost = price_eur * quantity + fee_in_cost
        current_qt = last_remaining_qt + quantity

        abp = ((old_cost + new_cost) / current_qt)

    residual_amount = abp * current_qt

    carryforward = compute_carryforward(df, ref_date, as_of_index=len(df))

    fee_loss = np.nan
    expiry = np.nan

    if product in ETF_PRODUCTS and fee_mode == "buy_loss":
        fee_loss = fee
        expiry = add_solar_years(ref_date)
        carryforward += fee_loss

    current_liq = float(df["cash_held"].iloc[-1]) - round_half_up(round_half_up(quantity * price) * conv_rate) - fee
    positions = priced_positions(df, ref_date, exclude_ticker=ticker)
    asset_value = sum(pos["value"] for pos in positions) + (current_qt * price_eur)

    return {
        "operation": Op.BUY,
        "qt_held": current_qt,
        "abp": abp,
        "residual_amount": residual_amount,
        "released_amount": np.nan,
        "gross_gain": np.nan,
        "generated_loss": fee_loss,
        "expiry": expiry,
        "carryforward": carryforward,
        "taxable_gain": np.nan,
        "tax": np.nan,
        "pl": np.nan,
        "cash_held": current_liq,
        "assets_value": asset_value,
        "nav": current_liq + asset_value
    }


def compute_carryforward(df, ref_date, as_of_index=None):
    history = df.copy()
    history['date_dt'] = pd.to_datetime(history['date'], format=DATE_FORMAT)
    ref_date = pd.Timestamp(ref_date)
    history = history[history['date_dt'] <= ref_date].copy()
    if as_of_index is not None:
        history = history.loc[history.index < as_of_index]

    # Stable sort: operations on the same day keep the order they were entered in,
    # which matters when a loss and a gain fall on the same day.
    history = history.sort_values(by='date_dt', kind='stable')

    active_losses = []

    for _, r in history.iterrows():
        current_date = r['date_dt']
        active_losses = [loss for loss in active_losses if loss['expiry'] >= current_date]

        if pd.notna(r.get('generated_loss')) and r['generated_loss'] > 0:
            expiry_value = r.get('expiry', np.nan)
            if pd.isna(expiry_value):
                expiry_dt = current_date
            else:
                expiry_dt = pd.to_datetime(expiry_value, format=DATE_FORMAT, errors='coerce')
            active_losses.append({'amount': float(r['generated_loss']), 'expiry': expiry_dt})

        # ETF gains are taxed in full and never offset past losses, same rule as sell_asset.
        is_etf_gain = r.get('product') in ETF_PRODUCTS
        if pd.notna(r.get('gross_gain')) and r['gross_gain'] > 0 and not is_etf_gain:
            to_consume = float(r['gross_gain'])
            i = 0
            while to_consume > 0 and i < len(active_losses):
                avail = active_losses[i]['amount']
                used = min(avail, to_consume)
                active_losses[i]['amount'] -= used
                to_consume -= used
                if active_losses[i]['amount'] == 0:
                    i += 1
            active_losses = [loss for loss in active_losses if loss['amount'] > 0]

    active_losses = [loss for loss in active_losses if loss['expiry'] >= ref_date]
    total = sum(loss['amount'] for loss in active_losses)
    return max(0.0, total)


def sell_asset(df, asset_rows, quantity, price, conv_rate, fee, ref_date, product, ticker, tax_rate=DEFAULT_CAPITAL_GAINS_TAX_RATE, fee_mode="abp"):

    if asset_rows.empty:
        raise ValidationError("operations.stock.sell_noitems")

    fee = round_half_up(fee)
    last_abp = asset_rows["abp"].iloc[-1]
    last_remaining_qt = asset_rows["qt_held"].iloc[-1]

    if quantity > last_remaining_qt:
        raise ValidationError("operations.stock.sell_noqt", quantity=quantity, last_remaining_qt=last_remaining_qt)

    effective_amount = round_half_up((round_half_up(quantity * price)) * conv_rate) - fee
    released_amount = quantity * last_abp

    gross_gain = effective_amount - released_amount  # negative = loss

    carryforward_before = compute_carryforward(df, ref_date, as_of_index=len(df))
    carryforward = carryforward_before
    taxable_gain = 0
    generated_loss = 0
    fee_loss = np.nan
    tax = 0
    expiry = np.nan

    if gross_gain > 0:
        gain_to_offset = gross_gain
        if carryforward_before > 0 and product not in ETF_PRODUCTS:
            carryforward_used = min(gain_to_offset, carryforward_before)
            gain_to_offset -= carryforward_used
            carryforward -= carryforward_used

        taxable_gain = gain_to_offset
        tax = taxable_gain * tax_rate
    else:
        gross_gain = round_down(gross_gain)

        generated_loss = abs(gross_gain)
        carryforward += generated_loss
        expiry = add_solar_years(ref_date)

    net_gain = gross_gain - tax

    current_qt = last_remaining_qt - quantity
    residual_amount = last_abp * current_qt
    abp = last_abp if current_qt > 0 else 0.0

    if product in ETF_PRODUCTS and fee_mode == "sell_loss":
        fee_loss = fee if gross_gain > 0 else 0
        carryforward += fee_loss
        expiry = add_solar_years(ref_date)
        generated_loss += fee_loss

    current_liq = float(df["cash_held"].iloc[-1]) + effective_amount - round_half_up(tax)
    positions = priced_positions(df, ref_date, exclude_ticker=ticker)
    asset_value = sum(pos["value"] for pos in positions) + (current_qt * price * conv_rate)

    return {
        "operation": Op.SELL,
        "qt_held": current_qt,
        "abp": abp,
        "residual_amount": residual_amount,
        "released_amount": released_amount,
        "gross_gain": gross_gain if gross_gain > 0 else np.nan,
        "generated_loss": np.nan if generated_loss == 0 else generated_loss,
        "expiry": expiry,
        "carryforward": carryforward,
        "taxable_gain": taxable_gain if gross_gain > 0 else np.nan,
        "tax": tax,
        "pl": net_gain if gross_gain > 0 else gross_gain,
        "cash_held": current_liq,
        "assets_value": asset_value,
        "nav": current_liq + asset_value
    }
