import pandas as pd
import numpy as np
import warnings

from services.market_data import download_close
from decimal import Decimal

from utils.other_utils import round_down, D, to_money, ValidationError
from utils.date_utils import add_solar_years
from services.market_data import fetch_exchange_rate
from utils.constants import DATE_FORMAT, ETF_PRODUCTS
warnings.simplefilter(action='ignore', category=Warning)


def get_tickers(translator, data):
    total_tickers = []
    active_tickers = []
    for account in data:
        total_assets, active_assets = get_asset_value(translator, account[1], just_assets=True)

        total_ticker_list = total_assets[["ticker", "curr"]].dropna(subset=["ticker", "curr"]).drop_duplicates().apply(tuple, axis=1).tolist()
        active_ticker_list = active_assets[["ticker", "curr"]].dropna(subset=["ticker", "curr"]).drop_duplicates().apply(tuple, axis=1).tolist()

        total_tickers.extend(total_ticker_list)
        active_tickers.extend(active_ticker_list)

    return list(set(total_tickers)), list(set(active_tickers))


def _compute_total_liquidity(final_df):
    accounts = final_df['account'].unique()
    liq_cols = []
    liq_hist_cols = []
    for acc in accounts:
        col_name = f'liq_running_{acc}'
        col_name_hist = f'liq_hist_{acc}'

        final_df[col_name] = final_df.where(final_df["account"] == acc)["cash_held"]
        final_df[col_name] = final_df[col_name].ffill()
        final_df[col_name_hist] = final_df.where(final_df["account"] == acc)["committed_cash"]
        final_df[col_name_hist] = final_df[col_name_hist].ffill()

        liq_cols.append(col_name)
        liq_hist_cols.append(col_name_hist)

    final_df[liq_cols] = final_df[liq_cols].fillna(0)
    final_df['cash_total'] = final_df[liq_cols].sum(axis=1)
    final_df[liq_hist_cols] = final_df[liq_hist_cols].fillna(0)
    final_df['committed_total'] = final_df[liq_hist_cols].sum(axis=1)
    final_df = final_df.drop(columns=liq_cols+liq_hist_cols)
    return final_df


def _compute_total_quantities(final_df):
    pairs = final_df.dropna(subset=['ticker'])[['account', 'ticker']].drop_duplicates().values
    state_cols = []
    ticker_to_cols_map = {}

    for conto, ticker in pairs:
        col_name = f'state_qty_{conto}_{ticker}'
        state_cols.append(col_name)
        if ticker not in ticker_to_cols_map:
            ticker_to_cols_map[ticker] = []
        ticker_to_cols_map[ticker].append(col_name)
        mask = (final_df['account'] == conto) & (final_df['ticker'] == ticker)
        final_df[col_name] = final_df.where(mask)['qt_held']
        final_df[col_name] = final_df[col_name].ffill()

    final_df[state_cols] = final_df[state_cols].fillna(0)
    final_df['qt_total'] = np.nan

    for ticker, cols_to_sum in ticker_to_cols_map.items():
        ticker_rows_mask = (final_df['ticker'] == ticker) & (final_df['qt_held'].notna())
        final_df.loc[ticker_rows_mask, 'qt_total'] = final_df[cols_to_sum].sum(axis=1)
    final_df = final_df.drop(columns=state_cols)

    final_df = final_df.drop(columns=["account", "qt_held", "cash_held", "committed_cash"])
    return final_df


def _download_price_data(translator, only_tickers, start_ref_date, end_ref_date):
    prices_df = pd.DataFrame([])
    exch_df = pd.DataFrame([])
    fallback_index = pd.date_range(start=start_ref_date, end=end_ref_date)

    try:
        prices_df, _ = download_close(only_tickers, start=start_ref_date, end=end_ref_date)
        exch_series, _ = download_close("USDEUR=X", start=start_ref_date, end=end_ref_date)

        if isinstance(prices_df, pd.Series):
            prices_df = prices_df.to_frame(name=only_tickers[0] if len(only_tickers) == 1 else "Close")

        if isinstance(exch_series, pd.Series):
            exch_df = exch_series.to_frame(name="USDEUR=X")
        elif not exch_series.empty:
            exch_df = exch_series
        else:
            exch_df = pd.DataFrame()

        if not prices_df.empty and not exch_df.empty:
            common_dates = prices_df.index.intersection(exch_df.index)
            prices_df = prices_df.loc[common_dates]
            exch_df = exch_df.loc[common_dates]

            prices_df = prices_df.ffill().dropna()
            exch_df = exch_df.ffill().dropna()
            target_index = prices_df.index

            if target_index.empty:
                target_index = fallback_index
        elif not prices_df.empty:
            prices_df = prices_df.ffill().dropna()
            target_index = prices_df.index if not prices_df.empty else fallback_index
        else:
            target_index = fallback_index

    except Exception:
        target_index = fallback_index

    return prices_df, exch_df, target_index


def _build_portfolio_timeseries(translator, final_df, prices_df, exch_df, target_index, total_tickers, only_tickers):
    try:
        portfolio_data = final_df.copy()
        portfolio_data = portfolio_data.drop(columns=["curr"])
        portfolio_data = portfolio_data.sort_values(by='date', kind="mergesort")

        liquidity_sparse = portfolio_data.dropna(subset=['cash_total'])
        liquidity_sparse = liquidity_sparse.drop_duplicates(subset=['date'], keep='last')
        liquidity_sparse = liquidity_sparse.set_index('date')[['cash_total']]
        liquidity_sparse = liquidity_sparse.rename(columns={'cash_total': 'cash'})

        immessa_sparse = portfolio_data.dropna(subset=['committed_total'])
        immessa_sparse = immessa_sparse.drop_duplicates(subset=['date'], keep='last')
        immessa_sparse = immessa_sparse.set_index('date')[['committed_total']]
        immessa_sparse = immessa_sparse.rename(columns={'committed_total': 'committed_cash'})

        quantities_sparse = portfolio_data.dropna(subset=['ticker', 'qt_total'])
        quantities_sparse = quantities_sparse.drop_duplicates(subset=['date', 'ticker'], keep='last')
        quantities_wide_sparse = quantities_sparse.pivot(index='date', columns='ticker', values='qt_total')

        combined_sparse_data = pd.concat([quantities_wide_sparse, liquidity_sparse, immessa_sparse], axis=1)

        for ticker in only_tickers:
            if ticker not in combined_sparse_data.columns:
                combined_sparse_data[ticker] = np.nan
        if 'cash' not in combined_sparse_data.columns:
            combined_sparse_data['cash'] = np.nan
        if 'committed_cash' not in combined_sparse_data.columns:
            combined_sparse_data['committed_cash'] = np.nan

        final_columns = only_tickers + ['cash', 'committed_cash']
        combined_sparse_data = combined_sparse_data[final_columns]

        if not target_index.empty:
            combined_index = target_index.union(combined_sparse_data.index).sort_values()
            quantities_df_filled = combined_sparse_data.reindex(combined_index).ffill()
            portfolio_history_df = quantities_df_filled.loc[target_index]
            portfolio_history_df[only_tickers] = portfolio_history_df[only_tickers].fillna(0)

            if not prices_df.empty:
                if isinstance(prices_df, pd.Series):
                    prices_df_for_calc = prices_df.to_frame(name=only_tickers[0])
                    prices_df_for_calc = prices_df_for_calc.reindex(columns=only_tickers, fill_value=0.0)
                else:
                    prices_df_for_calc = prices_df.reindex(columns=only_tickers, fill_value=0.0)

                for ticker, currency in total_tickers:
                    if currency == "USD":
                        prices_df_for_calc[ticker] = prices_df_for_calc[ticker] * exch_df["USDEUR=X"]
                portfolio_history_df['assets_value'] = (prices_df_for_calc * portfolio_history_df[only_tickers]).sum(axis=1)
            else:
                portfolio_history_df['assets_value'] = 0.0
                portfolio_history_df.index.rename("Date", inplace=True)

            portfolio_history_df['nav'] = portfolio_history_df['assets_value'] + portfolio_history_df['cash']
            portfolio_history_df["cash_flow"] = portfolio_history_df["committed_cash"].diff()

            previous_nav = portfolio_history_df['nav'].shift(1)
            portfolio_history_df["daily_twrr"] = (
                portfolio_history_df['nav'] - previous_nav - portfolio_history_df['cash_flow']
            ) / previous_nav

            portfolio_history_df = portfolio_history_df.iloc[1:]
            portfolio_history_df["cumulative_twrr"] = (1 + portfolio_history_df["daily_twrr"]).cumprod() - 1
            portfolio_history_df = portfolio_history_df.reset_index()

        else:
            final_columns_complete = ["Date"] + total_tickers + ["cash", "committed_cash", "assets_value", "nav", "daily_twrr", "cumulative_twrr"]
            portfolio_history_df = pd.DataFrame(columns=final_columns_complete)
        return portfolio_history_df

    except Exception as e:
        raise RuntimeError(f"Error building portfolio timeseries: {e}")


def portfolio_history(translator, start_ref_date, end_ref_date, data):

    total_tickers, _ = get_tickers(translator, data)
    only_tickers = [t[0] for t in total_tickers]

    all_dfs = []
    for account in data:
        df_copy = account[1].copy()
        df_copy["date"] = pd.to_datetime(df_copy["date"], dayfirst=True, errors="coerce")
        df_copy = df_copy[["date", "account", "ticker", "curr", "qt_held", "cash_held", "committed_cash"]]
        all_dfs.append(df_copy)

    final_df = pd.concat(all_dfs, ignore_index=True)
    final_df = final_df.sort_values(by="date", ascending=True, kind="mergesort")
    final_df = final_df.iloc[len(data):]
    final_df = final_df.reset_index(drop=True)

    final_df = _compute_total_liquidity(final_df)
    final_df = _compute_total_quantities(final_df)

    prices_df, exch_df, target_index = _download_price_data(
        translator, only_tickers, start_ref_date, end_ref_date
    )

    return _build_portfolio_timeseries(
        translator, final_df, prices_df, exch_df, target_index, total_tickers, only_tickers
    )


def aggregate_positions(total_positions):
    aggr_positions_dict = {}
    for pos in total_positions:
        ticker = pos["ticker"]
        value = pos["value"]
        aggr_positions_dict[ticker] = aggr_positions_dict.get(ticker, 0) + value

    aggr_positions = []
    for ticker, value_sum in aggr_positions_dict.items():
        new_pos = {"ticker": ticker, "value": value_sum}
        aggr_positions.append(new_pos)

    return aggr_positions


def get_asset_value(translator, df, current_ticker=None, ref_date=None, just_assets=False):

    df_copy = df.copy()
    df_copy["date"] = pd.to_datetime(df_copy["date"], format=DATE_FORMAT)
    if ref_date:
        ref_date = pd.Timestamp(ref_date)
        df_copy = df_copy[df_copy["date"] <= ref_date]

    df_filtered = df_copy.dropna(subset=["ticker"])
    if current_ticker:
        df_filtered = df_filtered[df_filtered["ticker"] != current_ticker]

    df_filtered = df_filtered[df_filtered["operation"].isin(["Buy", "Sell", "Split"])]
    total_assets = df_filtered.groupby("ticker").last().reset_index()
    total_active_assets = total_assets.loc[total_assets["qt_held"] > 0, ["ticker", "qt_held", "curr", "abp"]]

    if just_assets:
        return total_assets, total_active_assets

    if total_active_assets.empty:
        return []

    positions = []
    tickers = []
    for _, row in total_active_assets.iterrows():
        positions.append({
            "ticker": row["ticker"],
            "quantity": row["qt_held"],
            "exchange_rate": 1.0 if row["curr"] == "EUR" else fetch_exchange_rate(ref_date.strftime("%Y-%m-%d")),
            "price": np.nan,
            "value": np.nan,
            "pmc": row["abp"]
        })
        tickers.append(row["ticker"])

    start_date = pd.to_datetime(ref_date) - pd.Timedelta(days=10)
    end_date = pd.to_datetime(ref_date) + pd.Timedelta(days=1)

    data, names = download_close(tickers, start=start_date, end=end_date)
    if isinstance(data, pd.Series):
        data = data.to_frame(name=tickers[0])
    data_valid = (
        data.loc[data.index <= pd.to_datetime(ref_date)]
            .dropna(how="any")
    )
    data_ref = data_valid.iloc[-1]

    # Adjusted close for prev_close only: keeps daily P&L continuous across a split day.
    # Do NOT use for current price — adjusted close also bakes in dividends, which are
    # recorded explicitly as Dividend rows and would double-count otherwise.
    data_adj, _ = download_close(tickers, start=start_date, end=end_date, adjusted=True)
    if isinstance(data_adj, pd.Series):
        data_adj = data_adj.to_frame(name=tickers[0])
    data_adj_valid = (
        data_adj.loc[data_adj.index <= pd.to_datetime(ref_date)]
            .dropna(how="any")
    ) if not data_adj.empty else data_valid
    data_prev = data_adj_valid.iloc[-2] if len(data_adj_valid) >= 2 else data_ref

    for item in positions:
        ticker = item["ticker"]
        price = data_ref[ticker] * item["exchange_rate"]
        item["price"] = price
        item["value"] = item["quantity"] * price
        item["prev_close"] = data_prev[ticker] * item["exchange_rate"]
        item["name"] = names.get(ticker, ticker)

    return positions


def buy_asset(translator, df, asset_rows, quantity, price, conv_rate, fee, ref_date, product, ticker, fee_mode="abp"):

    quantity_d = D(quantity)
    price_d = D(price)
    conv_rate_d = D(conv_rate)
    fee_d = D(fee)

    price_abs_d = abs(price_d) * conv_rate_d
    fee_in_cost_d = fee_d if fee_mode == "abp" else Decimal("0")

    if asset_rows.empty:
        current_qt_d = quantity_d
        pmpc_d = (price_abs_d * quantity_d + fee_in_cost_d) / quantity_d
    else:
        last_pmpc_d = D(asset_rows["abp"].iloc[-1])
        last_remaining_qt_d = D(asset_rows["qt_held"].iloc[-1])

        old_cost_d = last_pmpc_d * last_remaining_qt_d
        new_cost_d = price_abs_d * quantity_d + fee_in_cost_d
        current_qt_d = last_remaining_qt_d + quantity_d

        pmpc_d = (old_cost_d + new_cost_d) / current_qt_d

    importo_residuo_d = pmpc_d * current_qt_d

    fiscal_credit_iniziale = compute_backpack(df, ref_date, as_of_index=len(df))
    fiscal_credit_aggiornato_d = D(fiscal_credit_iniziale)

    minusvalenza_comm = np.nan
    end_date = np.nan

    if product in ETF_PRODUCTS and fee_mode == "buy_loss":
        minusvalenza_comm = to_money(fee_d)
        end_date = add_solar_years(ref_date)
        fiscal_credit_aggiornato_d += fee_d

    nominal_d = quantity_d * price_d * conv_rate_d
    current_liq_d = D(df["cash_held"].iloc[-1]) + nominal_d - fee_d
    positions = get_asset_value(translator, df, current_ticker=ticker, ref_date=ref_date)
    asset_value_d = sum((D(pos["value"]) for pos in positions), Decimal("0")) + (current_qt_d * price_abs_d)

    return {
        "operation": "Buy",
        "qt_held": float(current_qt_d),
        "abp": to_money(pmpc_d, "0.0001"),
        "residual_amount": to_money(importo_residuo_d),
        "released_amount": np.nan,
        "gross_gain": np.nan,
        "generated_loss": minusvalenza_comm,
        "expiry": end_date,
        "carryforward": to_money(fiscal_credit_aggiornato_d),
        "taxable_gain": np.nan,
        "tax": np.nan,
        "pl": np.nan,
        "cash_held": to_money(current_liq_d),
        "assets_value": to_money(asset_value_d),
        "nav": to_money(current_liq_d + asset_value_d)
    }


def compute_backpack(df, data_operazione, as_of_index=None):
    history = df.copy()
    history['date_dt'] = pd.to_datetime(history['date'], format=DATE_FORMAT)
    data_operazione = pd.Timestamp(data_operazione)
    history = history[history['date_dt'] <= data_operazione].copy()
    if as_of_index is not None:
        history = history.loc[history.index < as_of_index]

    history = history.sort_values(by=['date_dt']).assign(_orig_index=history.index)
    history = history.sort_values(by=['date_dt', '_orig_index'])

    active_minuses = []

    for _, r in history.iterrows():
        current_date = r['date_dt']
        active_minuses = [m for m in active_minuses if m['expiry'] >= current_date]

        if pd.notna(r.get('generated_loss')) and r['generated_loss'] > 0:
            scad = r.get('expiry', np.nan)
            if pd.isna(scad):
                expiry_dt = current_date
            else:
                expiry_dt = pd.to_datetime(scad, format=DATE_FORMAT, errors='coerce')
            active_minuses.append({'amount': D(r['generated_loss']), 'expiry': expiry_dt})

        if pd.notna(r.get('gross_gain')) and r['gross_gain'] > 0:
            to_consume_d = D(r['gross_gain'])
            i = 0
            while to_consume_d > 0 and i < len(active_minuses):
                avail_d = active_minuses[i]['amount']
                used_d = min(avail_d, to_consume_d)
                active_minuses[i]['amount'] = avail_d - used_d
                to_consume_d -= used_d
                # Quantize before zero-test: avoids the float-equality trap
                # where a sub-cent residual keeps the bucket "alive" forever.
                if active_minuses[i]['amount'].quantize(Decimal("0.01")) <= 0:
                    i += 1
            active_minuses = [m for m in active_minuses if m['amount'].quantize(Decimal("0.01")) > 0]

    active_minuses = [m for m in active_minuses if m['expiry'] >= data_operazione]
    total_d = sum((m['amount'] for m in active_minuses), Decimal("0"))
    return float(max(Decimal("0"), total_d.quantize(Decimal("0.01"))))


def sell_asset(translator, df, asset_rows, quantity, price, conv_rate, fee, ref_date, product, ticker, tax_rate=0.26, fee_mode="abp"):

    if asset_rows.empty:
        raise ValidationError(translator.get("operations.stock.sell_noitems"))

    quantity_d = D(quantity)
    price_d = D(price)
    conv_rate_d = D(conv_rate)
    fee_d = D(fee)
    tax_rate_d = D(tax_rate)

    last_pmpc_d = D(asset_rows["abp"].iloc[-1])
    last_remaining_qt_d = D(asset_rows["qt_held"].iloc[-1])

    if quantity_d > last_remaining_qt_d:
        raise ValidationError(translator.get("operations.stock.sell_noqt", quantity=quantity, last_remaining_qt=float(last_remaining_qt_d)))

    importo_effettivo_d = quantity_d * price_d * conv_rate_d - fee_d
    costo_rilasciato_d = quantity_d * last_pmpc_d

    plusvalenza_lorda_d = importo_effettivo_d - costo_rilasciato_d

    fiscal_credit_iniziale_d = D(compute_backpack(df, ref_date, as_of_index=len(df)))
    fiscal_credit_aggiornato_d = fiscal_credit_iniziale_d
    plusvalenza_imponibile_d = Decimal("0")
    minusvalenza_generata_d = Decimal("0")
    imposta_d = Decimal("0")
    end_date = np.nan

    if plusvalenza_lorda_d > 0:
        plusvalenza_da_compensare_d = plusvalenza_lorda_d
        if fiscal_credit_iniziale_d > 0 and product not in ETF_PRODUCTS:
            credito_utilizzato_d = min(plusvalenza_da_compensare_d, fiscal_credit_iniziale_d)
            plusvalenza_da_compensare_d -= credito_utilizzato_d
            fiscal_credit_aggiornato_d -= credito_utilizzato_d

        plusvalenza_imponibile_d = plusvalenza_da_compensare_d
        imposta_d = plusvalenza_imponibile_d * tax_rate_d
    else:
        # Preserve the original round_down behaviour for losses
        plusvalenza_lorda_d = D(round_down(float(plusvalenza_lorda_d)))

        minusvalenza_generata_d = abs(plusvalenza_lorda_d)
        fiscal_credit_aggiornato_d += minusvalenza_generata_d
        end_date = add_solar_years(ref_date)

    plusvalenza_netta_d = plusvalenza_lorda_d - imposta_d

    current_qt_d = last_remaining_qt_d - quantity_d
    importo_residuo_d = last_pmpc_d * current_qt_d
    pmpc_residuo_d = last_pmpc_d if current_qt_d > 0 else Decimal("0")

    if product in ETF_PRODUCTS and fee_mode == "sell_loss":
        minusvalenza_comm_d = fee_d if plusvalenza_lorda_d > 0 else Decimal("0")
        fiscal_credit_aggiornato_d += minusvalenza_comm_d
        end_date = add_solar_years(ref_date)
        minusvalenza_generata_d += minusvalenza_comm_d

    current_liq_d = D(df["cash_held"].iloc[-1]) + importo_effettivo_d - imposta_d
    positions = get_asset_value(translator, df, current_ticker=ticker, ref_date=ref_date)
    asset_value_d = sum((D(pos["value"]) for pos in positions), Decimal("0")) + (current_qt_d * price_d * conv_rate_d)

    return {
        "operation": "Sell",
        "qt_held": float(current_qt_d),
        "abp": to_money(pmpc_residuo_d, "0.0001"),
        "residual_amount": to_money(importo_residuo_d),
        "released_amount": to_money(costo_rilasciato_d),
        "gross_gain": to_money(plusvalenza_lorda_d) if plusvalenza_lorda_d > 0 else np.nan,
        "generated_loss": np.nan if minusvalenza_generata_d == 0 else to_money(minusvalenza_generata_d),
        "expiry": end_date,
        "carryforward": to_money(fiscal_credit_aggiornato_d),
        "taxable_gain": to_money(plusvalenza_imponibile_d) if plusvalenza_lorda_d > 0 else np.nan,
        "tax": to_money(imposta_d),
        "pl": to_money(plusvalenza_netta_d) if plusvalenza_lorda_d > 0 else to_money(plusvalenza_lorda_d),
        "cash_held": to_money(current_liq_d),
        "assets_value": to_money(asset_value_d),
        "nav": to_money(current_liq_d + asset_value_d)
    }
