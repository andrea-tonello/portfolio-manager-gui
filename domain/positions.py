"""Which assets an account holds, and what they are worth.

holdings() and held_tickers() only read the ledger, as do the split-check
helpers first_trade_date() and unrecorded_splits(). priced_positions() also
fetches closing prices (and the USD->EUR rate) from Yahoo Finance through
services.market_data.
"""

import warnings

import numpy as np
import pandas as pd

from domain.ledger import Op, holding_rows
from services import market_data
from utils.constants import DATE_FORMAT

# Silences every warning in the whole app; scope or remove it (REFACTORING.md, D6).
warnings.simplefilter(action='ignore', category=Warning)


def holdings(df, ref_date=None, exclude_ticker=None):
    """Return (all_assets, active_assets) from the ledger `df`, without fetching prices.

    all_assets has one row per asset ever bought: the latest values of its
    buy/sell/split rows. active_assets keeps those still held (qt_held > 0),
    with columns ticker, qt_held, curr and abp. With `ref_date`, rows after
    that date are ignored; `exclude_ticker` leaves one asset out (a new row
    for it is being built).
    """
    df_copy = df.copy()
    df_copy["date"] = pd.to_datetime(df_copy["date"], format=DATE_FORMAT)
    if ref_date:
        df_copy = df_copy[df_copy["date"] <= pd.Timestamp(ref_date)]

    df_filtered = df_copy.dropna(subset=["ticker"])
    if exclude_ticker:
        df_filtered = df_filtered[df_filtered["ticker"] != exclude_ticker]

    df_filtered = holding_rows(df_filtered)
    total_assets = df_filtered.groupby("ticker").last().reset_index()
    total_active_assets = total_assets.loc[total_assets["qt_held"] > 0, ["ticker", "qt_held", "curr", "abp"]]
    return total_assets, total_active_assets


def priced_positions(df, ref_date, exclude_ticker=None):
    """Return one dict per asset held on `ref_date`, valued at that day's closing price in EUR.

    Keys: ticker, name, quantity, pmc (average buy price), exchange_rate
    (USD->EUR, 1.0 for EUR assets), price, value (quantity x price) and
    prev_close (the previous day's price). Fetches prices from Yahoo Finance.
    Returns [] when nothing is held.

    Example: 5 units of a stock closing at 100.3 EUR -> price 100.3, value 501.5.
    """
    _, total_active_assets = holdings(df, ref_date, exclude_ticker)
    if total_active_assets.empty:
        return []
    ref_date = pd.Timestamp(ref_date)

    positions = []
    tickers = []
    for _, row in total_active_assets.iterrows():
        positions.append({
            "ticker": row["ticker"],
            "quantity": row["qt_held"],
            "exchange_rate": 1.0 if row["curr"] == "EUR" else market_data.fetch_exchange_rate(ref_date.strftime("%Y-%m-%d")),
            "price": np.nan,
            "value": np.nan,
            "pmc": row["abp"]
        })
        tickers.append(row["ticker"])

    start_date = pd.to_datetime(ref_date) - pd.Timedelta(days=10)
    end_date = pd.to_datetime(ref_date) + pd.Timedelta(days=1)

    data, names = market_data.download_close(tickers, start=start_date, end=end_date)
    data_valid = (
        data.loc[data.index <= pd.to_datetime(ref_date)]
            .dropna(how="any")
    )
    data_ref = data_valid.iloc[-1]

    # Adjusted close for prev_close only: keeps daily P&L continuous across a split day.
    # Do NOT use for current price — adjusted close also bakes in dividends, which are
    # recorded explicitly as Dividend rows and would double-count otherwise.
    data_adj, _ = market_data.download_close(tickers, start=start_date, end=end_date, adjusted=True)
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


def held_tickers(df):
    """Return {ticker: asset_name} for every asset currently held (quantity above zero).

    Assets are ordered by their latest buy, sell or split. Used to look for
    unrecorded splits (Home) and to fill the Split form's ticker list (Operations).
    """
    last_rows = holding_rows(df).groupby("ticker", sort=False).tail(1)
    held = last_rows[last_rows["qt_held"].astype(float) > 0]
    return dict(zip(held["ticker"], held["asset_name"]))


def first_trade_date(df, ticker):
    """Return the date (a datetime) of the first buy, sell or split of `ticker` in `df`, or None if there is none."""
    dates = pd.to_datetime(holding_rows(df, ticker)["date"], dayfirst=True, errors="coerce").dropna()
    return dates.min().to_pydatetime() if not dates.empty else None


def unrecorded_splits(df, ticker, splits):
    """Return the splits of `ticker` not yet recorded in `df`, as (ISO date, ratio), in the order given.

    `splits` is a list of (date, ratio) pairs, as market_data.fetch_splits
    returns them. A split counts as recorded when a Split row of the ticker is
    dated within a day of it, since the user may date it a day apart from Yahoo.

    Example: with a Split row on 01-07-2024, [(2024-06-30, 2.0), (2024-07-03, 3.0)]
    -> [("2024-07-03", 3.0)].
    """
    asset_rows = holding_rows(df, ticker)
    split_rows = asset_rows[asset_rows["operation"] == Op.SPLIT]
    recorded_dates = set()
    for d in pd.to_datetime(split_rows["date"], dayfirst=True, errors="coerce").dropna():
        for delta in (-1, 0, 1):
            recorded_dates.add((d + pd.Timedelta(days=delta)).date())

    return [(day.strftime("%Y-%m-%d"), ratio) for day, ratio in splits if day not in recorded_dates]


def get_tickers(data):
    """Return (all, active): the (ticker, currency) pairs ever held and still held, across all accounts in `data`.

    `data` is a list of [account index, ledger DataFrame] pairs.
    """
    total_tickers = []
    active_tickers = []
    for account in data:
        total_assets, active_assets = holdings(account[1])

        total_ticker_list = total_assets[["ticker", "curr"]].dropna(subset=["ticker", "curr"]).drop_duplicates().apply(tuple, axis=1).tolist()
        active_ticker_list = active_assets[["ticker", "curr"]].dropna(subset=["ticker", "curr"]).drop_duplicates().apply(tuple, axis=1).tolist()

        total_tickers.extend(total_ticker_list)
        active_tickers.extend(active_ticker_list)

    return list(set(total_tickers)), list(set(active_tickers))


def aggregate_positions(total_positions):
    """Merge positions of the same ticker held in several accounts into one {ticker, value} each."""
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
