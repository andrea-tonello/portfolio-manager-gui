import os
import pandas as pd
import numpy as np
import warnings

from services.market_data import download_close
from utils.other_utils import round_half_up, round_down, ValidationError
from utils.date_utils import add_solar_years
from utils.fetch_utils import fetch_exchange_rate
from utils.constants import DATE_FORMAT
warnings.simplefilter(action='ignore', category=Warning)


def format_accounts(df, acc_idx, all_accounts, non_active_only=False):
    non_active_accounts = [acc for acc in all_accounts if acc["acc_idx"] != acc_idx]
    data = [(acc["acc_idx"], acc["df"]) for acc in non_active_accounts]

    if non_active_only:
        data = sorted(data, key=lambda x: x[0])
    else:
        data.append((acc_idx, df))
        data = sorted(data, key=lambda x: x[0])
    data = [list(t) for t in data]
    return data


def get_tickers(translator, data):
    total_tickers = []
    active_tickers = []
    for account in data:
        total_assets, active_assets = get_asset_value(translator, account[1], just_assets=True)

        total_ticker_list = total_assets[["Ticker", "Valuta"]].dropna(subset=["Ticker", "Valuta"]).drop_duplicates().apply(tuple, axis=1).tolist()
        active_ticker_list = active_assets[["Ticker", "Valuta"]].dropna(subset=["Ticker", "Valuta"]).drop_duplicates().apply(tuple, axis=1).tolist()

        total_tickers.extend(total_ticker_list)
        active_tickers.extend(active_ticker_list)

    return list(set(total_tickers)), list(set(active_tickers))


def _compute_total_liquidity(final_df):
    accounts = final_df['Conto'].unique()
    liq_cols = []
    liq_hist_cols = []
    for acc in accounts:
        col_name = f'liq_running_{acc}'
        col_name_hist = f'liq_hist_{acc}'

        final_df[col_name] = final_df.where(final_df["Conto"] == acc)["Liquidita Attuale"]
        final_df[col_name] = final_df[col_name].ffill()
        final_df[col_name_hist] = final_df.where(final_df["Conto"] == acc)["Liq. Impegnata"]
        final_df[col_name_hist] = final_df[col_name_hist].ffill()

        liq_cols.append(col_name)
        liq_hist_cols.append(col_name_hist)

    final_df[liq_cols] = final_df[liq_cols].fillna(0)
    final_df['Liquidita Totale'] = final_df[liq_cols].sum(axis=1)
    final_df[liq_hist_cols] = final_df[liq_hist_cols].fillna(0)
    final_df['Liq. Impegnata Totale'] = final_df[liq_hist_cols].sum(axis=1)
    final_df = final_df.drop(columns=liq_cols+liq_hist_cols)
    return final_df


def _compute_total_quantities(final_df):
    pairs = final_df.dropna(subset=['Ticker'])[['Conto', 'Ticker']].drop_duplicates().values
    state_cols = []
    ticker_to_cols_map = {}

    for conto, ticker in pairs:
        col_name = f'state_qty_{conto}_{ticker}'
        state_cols.append(col_name)
        if ticker not in ticker_to_cols_map:
            ticker_to_cols_map[ticker] = []
        ticker_to_cols_map[ticker].append(col_name)
        mask = (final_df['Conto'] == conto) & (final_df['Ticker'] == ticker)
        final_df[col_name] = final_df.where(mask)['QT. Attuale']
        final_df[col_name] = final_df[col_name].ffill()

    final_df[state_cols] = final_df[state_cols].fillna(0)
    final_df['QT. Totale'] = np.nan

    for ticker, cols_to_sum in ticker_to_cols_map.items():
        ticker_rows_mask = (final_df['Ticker'] == ticker) & (final_df['QT. Attuale'].notna())
        final_df.loc[ticker_rows_mask, 'QT. Totale'] = final_df[cols_to_sum].sum(axis=1)
    final_df = final_df.drop(columns=state_cols)

    final_df = final_df.drop(columns=["Conto", "QT. Attuale", "Liquidita Attuale", "Liq. Impegnata"])
    return final_df


def _download_price_data(translator, only_tickers, start_ref_date, end_ref_date):
    prices_df = pd.DataFrame([])
    exch_df = pd.DataFrame([])
    fallback_index = pd.date_range(start=start_ref_date, end=end_ref_date)

    try:
        prices_df = download_close(only_tickers, start=start_ref_date, end=end_ref_date)
        exch_series = download_close("USDEUR=X", start=start_ref_date, end=end_ref_date)

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
        portfolio_data.drop(columns=["Valuta"])
        portfolio_data = portfolio_data.sort_values(by='Data', kind="mergesort")

        liquidity_sparse = portfolio_data.dropna(subset=['Liquidita Totale'])
        liquidity_sparse = liquidity_sparse.drop_duplicates(subset=['Data'], keep='last')
        liquidity_sparse = liquidity_sparse.set_index('Data')[['Liquidita Totale']]
        liquidity_sparse = liquidity_sparse.rename(columns={'Liquidita Totale': 'Liquidita'})

        immessa_sparse = portfolio_data.dropna(subset=['Liq. Impegnata Totale'])
        immessa_sparse = immessa_sparse.drop_duplicates(subset=['Data'], keep='last')
        immessa_sparse = immessa_sparse.set_index('Data')[['Liq. Impegnata Totale']]
        immessa_sparse = immessa_sparse.rename(columns={'Liq. Impegnata Totale': 'Liquidita Impegnata'})

        quantities_sparse = portfolio_data.dropna(subset=['Ticker', 'QT. Totale'])
        quantities_sparse = quantities_sparse.drop_duplicates(subset=['Data', 'Ticker'], keep='last')
        quantities_wide_sparse = quantities_sparse.pivot(index='Data', columns='Ticker', values='QT. Totale')

        combined_sparse_data = pd.concat([quantities_wide_sparse, liquidity_sparse, immessa_sparse], axis=1)

        for ticker in only_tickers:
            if ticker not in combined_sparse_data.columns:
                combined_sparse_data[ticker] = np.nan
        if 'Liquidita' not in combined_sparse_data.columns:
            combined_sparse_data['Liquidita'] = np.nan
        if 'Liquidita Impegnata' not in combined_sparse_data.columns:
            combined_sparse_data['Liquidita Impegnata'] = np.nan

        final_columns = only_tickers + ['Liquidita', 'Liquidita Impegnata']
        combined_sparse_data = combined_sparse_data[final_columns]

        if not target_index.empty:
            combined_index = target_index.union(combined_sparse_data.index).sort_values()
            quantities_df_filled = combined_sparse_data.reindex(combined_index).ffill()
            portfolio_history_df = quantities_df_filled.loc[target_index]
            portfolio_history_df[only_tickers] = portfolio_history_df[only_tickers].fillna(0)

            if not prices_df.empty:
                if isinstance(prices_df, pd.Series):
                    prices_df_for_calc = prices_df.to_frame(name=only_tickers[0])
                else:
                    prices_df_for_calc = prices_df[only_tickers]

                for ticker, currency in total_tickers:
                    if currency == "USD":
                        prices_df_for_calc[ticker] = prices_df_for_calc[ticker] * exch_df["USDEUR=X"]
                portfolio_history_df['Valore Titoli'] = (prices_df_for_calc * portfolio_history_df[only_tickers]).sum(axis=1)
            else:
                portfolio_history_df['Valore Titoli'] = 0.0
                portfolio_history_df.index.rename("Date", inplace=True)

            portfolio_history_df['NAV'] = portfolio_history_df['Valore Titoli'] + portfolio_history_df['Liquidita']
            portfolio_history_df["Cash Flow"] = portfolio_history_df["Liquidita Impegnata"].diff()

            previous_nav = portfolio_history_df['NAV'].shift(1)
            portfolio_history_df["TWRR Giornaliero"] = (
                portfolio_history_df['NAV'] - previous_nav - portfolio_history_df['Cash Flow']
            ) / previous_nav

            portfolio_history_df = portfolio_history_df.iloc[1:]
            portfolio_history_df["TWRR Cumulativo"] = (1 + portfolio_history_df["TWRR Giornaliero"]).cumprod() - 1
            portfolio_history_df = portfolio_history_df.reset_index()

        else:
            final_columns_complete = ["Date"] + total_tickers + ["Liquidita", "Liquidita Impegnata", "Valore Titoli", "NAV", "TWRR Giornaliero", "TWRR Cumulativo"]
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
        df_copy["Data"] = pd.to_datetime(df_copy["Data"], dayfirst=True, errors="coerce")
        df_copy = df_copy[["Data", "Conto", "Ticker", "Valuta", "QT. Attuale", "Liquidita Attuale", "Liq. Impegnata"]]
        all_dfs.append(df_copy)

    final_df = pd.concat(all_dfs, ignore_index=True)
    final_df = final_df.sort_values(by="Data", ascending=True, kind="mergesort")
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


def get_asset_value(translator, df, current_ticker=None, ref_date=None, just_assets=False, suppress_progress=False):

    df_copy = df.copy()
    df_copy["Data"] = pd.to_datetime(df_copy["Data"], format=DATE_FORMAT)
    if ref_date:
        ref_date = pd.Timestamp(ref_date)
        df_copy = df_copy[df_copy["Data"] <= ref_date]

    df_filtered = df_copy.dropna(subset=["Ticker"])
    if current_ticker:
        df_filtered = df_filtered[df_filtered["Ticker"] != current_ticker]

    df_filtered = df_filtered[df_filtered["Operazione"].isin(["Acquisto", "Vendita"])]
    total_assets = df_filtered.groupby("Ticker").last().reset_index()
    total_active_assets = total_assets.loc[total_assets["QT. Attuale"] > 0, ["Ticker", "QT. Attuale", "Valuta", "PMC"]]

    if just_assets:
        return total_assets, total_active_assets

    if total_active_assets.empty:
        return []

    positions = []
    tickers = []
    for _, row in total_active_assets.iterrows():
        positions.append({
            "ticker": row["Ticker"],
            "quantity": row["QT. Attuale"],
            "exchange_rate": 1.0 if row["Valuta"] == "EUR" else fetch_exchange_rate(ref_date.strftime("%Y-%m-%d")),
            "price": np.nan,
            "value": np.nan,
            "pmc": row["PMC"]
        })
        tickers.append(row["Ticker"])

    start_date = pd.to_datetime(ref_date) - pd.Timedelta(days=10)
    end_date = pd.to_datetime(ref_date) + pd.Timedelta(days=1)

    data = download_close(tickers, start=start_date, end=end_date)
    if isinstance(data, pd.Series):
        data = data.to_frame(name=tickers[0])
    data_ref = (
        data.loc[data.index <= pd.to_datetime(ref_date)]
            .dropna(how="any")
            .iloc[-1]
    )

    for item in positions:
        ticker = item["ticker"]
        price = data_ref[ticker] * item["exchange_rate"]
        item["price"] = price
        item["value"] = item["quantity"] * price

    return positions


def buy_asset(translator, df, asset_rows, quantity, price, conv_rate, fee, ref_date, product, ticker):

    price_abs = abs(price) / conv_rate
    fee = round_half_up(fee)
    pmpc = 0
    current_qt = quantity

    if asset_rows.empty:
        pmpc = (price_abs * quantity + fee) / quantity
    else:
        last_pmpc = asset_rows["PMC"].iloc[-1]
        last_remaining_qt = asset_rows["QT. Attuale"].iloc[-1]

        old_cost = last_pmpc * last_remaining_qt
        new_cost = price_abs * quantity + fee
        current_qt = last_remaining_qt + quantity

        pmpc = ((old_cost + new_cost) / current_qt)

    importo_residuo = pmpc * current_qt

    fiscal_credit_iniziale = compute_backpack(df, ref_date, as_of_index=len(df))
    fiscal_credit_aggiornato = fiscal_credit_iniziale

    minusvalenza_comm = np.nan
    end_date = np.nan

    if product == "ETF":
        minusvalenza_comm = fee
        end_date = add_solar_years(ref_date)
        fiscal_credit_aggiornato += minusvalenza_comm

    current_liq = float(df["Liquidita Attuale"].iloc[-1]) + round_half_up(round_half_up(quantity * price) / conv_rate) - fee
    positions = get_asset_value(translator, df, current_ticker=ticker, ref_date=ref_date)
    asset_value = sum(pos["value"] for pos in positions) + (current_qt * price_abs)

    return {
        "Operazione": "Acquisto",
        "QT. Attuale": current_qt,
        "PMC": pmpc,
        "Imp. Residuo Asset": importo_residuo,
        "Costo Rilasciato": np.nan,
        "Plusv. Lorda": np.nan,
        "Minusv. Generata": minusvalenza_comm,
        "Scadenza": end_date,
        "Zainetto Fiscale": fiscal_credit_aggiornato,
        "Plusv. Imponibile": np.nan,
        "Imposta": np.nan,
        "P&L": np.nan,
        "Liquidita Attuale": current_liq,
        "Valore Titoli": asset_value,
        "NAV": current_liq + asset_value
    }


def compute_backpack(df, data_operazione, as_of_index=None):
    history = df.copy()
    history['Data_dt'] = pd.to_datetime(history['Data'], format=DATE_FORMAT)
    data_operazione = pd.Timestamp(data_operazione)
    history = history[history['Data_dt'] <= data_operazione].copy()
    if as_of_index is not None:
        history = history.loc[history.index < as_of_index]

    history = history.sort_values(by=['Data_dt']).assign(_orig_index=history.index)
    history = history.sort_values(by=['Data_dt', '_orig_index'])

    active_minuses = []

    for _, r in history.iterrows():
        current_date = r['Data_dt']
        active_minuses = [m for m in active_minuses if m['expiry'] >= current_date]

        if pd.notna(r.get('Minusv. Generata')) and r['Minusv. Generata'] > 0:
            scad = r.get('Scadenza', np.nan)
            if pd.isna(scad):
                expiry_dt = current_date
            else:
                expiry_dt = pd.to_datetime(scad, format=DATE_FORMAT, errors='coerce')
            active_minuses.append({'amount': float(r['Minusv. Generata']), 'expiry': expiry_dt})

        if pd.notna(r.get('Plusv. Lorda')) and r['Plusv. Lorda'] > 0:
            to_consume = float(r['Plusv. Lorda'])
            i = 0
            while to_consume > 0 and i < len(active_minuses):
                avail = active_minuses[i]['amount']
                used = min(avail, to_consume)
                active_minuses[i]['amount'] -= used
                to_consume -= used
                if active_minuses[i]['amount'] == 0:
                    i += 1
            active_minuses = [m for m in active_minuses if m['amount'] > 0]

    active_minuses = [m for m in active_minuses if m['expiry'] >= data_operazione]
    total = sum(m['amount'] for m in active_minuses)
    return max(0.0, total)


def sell_asset(translator, df, asset_rows, quantity, price, conv_rate, fee, ref_date, product, ticker, tax_rate=0.26):

    if asset_rows.empty:
        raise ValidationError(translator.get("stock.sell_noitems"))

    fee = round_half_up(fee)
    last_pmpc = asset_rows["PMC"].iloc[-1]
    last_remaining_qt = asset_rows["QT. Attuale"].iloc[-1]

    if quantity > last_remaining_qt:
        raise ValidationError(translator.get("stock.sell_noqt", quantity=quantity, last_remaining_qt=last_remaining_qt))

    importo_effettivo = round_half_up((round_half_up(quantity * price)) / conv_rate) - fee
    costo_rilasciato = quantity * last_pmpc

    plusvalenza_lorda = importo_effettivo - costo_rilasciato

    fiscal_credit_iniziale = compute_backpack(df, ref_date, as_of_index=len(df))
    fiscal_credit_aggiornato = fiscal_credit_iniziale
    plusvalenza_imponibile = 0
    minusvalenza_generata = 0
    minusvalenza_comm = np.nan
    imposta = 0
    end_date = np.nan

    if plusvalenza_lorda > 0:
        plusvalenza_da_compensare = plusvalenza_lorda
        if fiscal_credit_iniziale > 0 and product != "ETF":
            credito_utilizzato = min(plusvalenza_da_compensare, fiscal_credit_iniziale)
            plusvalenza_da_compensare -= credito_utilizzato
            fiscal_credit_aggiornato -= credito_utilizzato

        plusvalenza_imponibile = plusvalenza_da_compensare
        imposta = plusvalenza_imponibile * tax_rate
    else:
        plusvalenza_lorda = round_down(plusvalenza_lorda)

        minusvalenza_generata = abs(plusvalenza_lorda)
        fiscal_credit_aggiornato += minusvalenza_generata
        end_date = add_solar_years(ref_date)

    plusvalenza_netta = plusvalenza_lorda - imposta

    current_qt = last_remaining_qt - quantity
    importo_residuo = last_pmpc * current_qt
    pmpc_residuo = last_pmpc if current_qt > 0 else 0.0

    if product == "ETF":
        minusvalenza_comm = fee
        fiscal_credit_aggiornato += minusvalenza_comm
        end_date = add_solar_years(ref_date)
        minusvalenza_generata += minusvalenza_comm

    current_liq = float(df["Liquidita Attuale"].iloc[-1]) + importo_effettivo - round_half_up(imposta)
    positions = get_asset_value(translator, df, current_ticker=ticker, ref_date=ref_date)
    asset_value = sum(pos["value"] for pos in positions) + (current_qt * price)

    return {
        "Operazione": "Vendita",
        "QT. Attuale": current_qt,
        "PMC": pmpc_residuo,
        "Imp. Residuo Asset": importo_residuo,
        "Costo Rilasciato": costo_rilasciato,
        "Plusv. Lorda": plusvalenza_lorda if plusvalenza_lorda > 0 else np.nan,
        "Minusv. Generata": np.nan if minusvalenza_generata == 0 else minusvalenza_generata,
        "Scadenza": end_date,
        "Zainetto Fiscale": fiscal_credit_aggiornato,
        "Plusv. Imponibile": plusvalenza_imponibile if plusvalenza_lorda > 0 else np.nan,
        "Imposta": imposta,
        "P&L": plusvalenza_netta if plusvalenza_lorda > 0 else plusvalenza_lorda,
        "Liquidita Attuale": current_liq,
        "Valore Titoli": asset_value,
        "NAV": current_liq + asset_value
    }
