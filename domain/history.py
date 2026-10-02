"""The portfolio's day-by-day value over a period, across all accounts.

portfolio_history combines the ledgers with daily closing prices from Yahoo
Finance (through services.market_data) into one row per trading day: cash,
assets value, NAV and the time-weighted return (TWRR). The Summary,
Statistics and Drawdown analyses are built on it.
"""

import numpy as np
import pandas as pd

from domain.positions import get_tickers
from services import market_data


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

    for account, ticker in pairs:
        col_name = f'state_qty_{account}_{ticker}'
        state_cols.append(col_name)
        if ticker not in ticker_to_cols_map:
            ticker_to_cols_map[ticker] = []
        ticker_to_cols_map[ticker].append(col_name)
        mask = (final_df['account'] == account) & (final_df['ticker'] == ticker)
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


def _download_price_data(total_tickers, start_ref_date, end_ref_date):
    """Return (prices in EUR, the days the history covers) for the (ticker, currency) pairs in `total_tickers`.

    The days are the trading days that have prices. Without any price (an
    account holding only cash, or nothing downloaded) they are every calendar
    day from start to end.
    """
    prices_df = market_data.download_prices_eur(total_tickers, start_ref_date, end_ref_date)
    if prices_df.empty:
        return prices_df, pd.date_range(start=start_ref_date, end=end_ref_date)
    return prices_df, prices_df.index


def _build_portfolio_timeseries(final_df, prices_df, target_index, total_tickers, only_tickers):
    try:
        portfolio_data = final_df.copy()
        portfolio_data = portfolio_data.drop(columns=["curr"])
        portfolio_data = portfolio_data.sort_values(by='date', kind="mergesort")

        liquidity_sparse = portfolio_data.dropna(subset=['cash_total'])
        liquidity_sparse = liquidity_sparse.drop_duplicates(subset=['date'], keep='last')
        liquidity_sparse = liquidity_sparse.set_index('date')[['cash_total']]
        liquidity_sparse = liquidity_sparse.rename(columns={'cash_total': 'cash'})

        committed_sparse = portfolio_data.dropna(subset=['committed_total'])
        committed_sparse = committed_sparse.drop_duplicates(subset=['date'], keep='last')
        committed_sparse = committed_sparse.set_index('date')[['committed_total']]
        committed_sparse = committed_sparse.rename(columns={'committed_total': 'committed_cash'})

        quantities_sparse = portfolio_data.dropna(subset=['ticker', 'qt_total'])
        quantities_sparse = quantities_sparse.drop_duplicates(subset=['date', 'ticker'], keep='last')
        quantities_wide_sparse = quantities_sparse.pivot(index='date', columns='ticker', values='qt_total')

        combined_sparse_data = pd.concat([quantities_wide_sparse, liquidity_sparse, committed_sparse], axis=1, sort=True)

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
                prices_df_for_calc = prices_df.reindex(columns=only_tickers, fill_value=0.0)
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
        raise RuntimeError(f"Error building portfolio timeseries: {e}") from e


def portfolio_history(start_ref_date, end_ref_date, data):

    total_tickers, _ = get_tickers(data)
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

    prices_df, target_index = _download_price_data(total_tickers, start_ref_date, end_ref_date)

    return _build_portfolio_timeseries(
        final_df, prices_df, target_index, total_tickers, only_tickers
    )
