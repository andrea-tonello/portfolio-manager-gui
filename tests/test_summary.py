"""Characterisation test for compute_summary, the numbers behind the Statistics tab.

It runs compute_summary on the two test accounts from test_ledger_snapshots.py
(one still holding shares at the end, one fully sold) with the fake prices, and
compares the results with tests/snapshots/summary.json. Like the CSV snapshots,
it records what the code does today; regenerate with --update-snapshots only
after an intended change.
"""

import json
from datetime import date

import numpy as np
import pandas as pd
from conftest import fake_download_close

from domain.account import Account
from services import market_data
from services.analysis_service import compute_summary, summary_history
from test_ledger_snapshots import ETFS_AND_USD, STOCKS_EUR, _replay, buy, deposit

ACCOUNT_FIELDS = ("broker_name", "nav", "current_liq", "asset_value", "historic_liq",
                  "pl", "pl_unrealized", "xirr_full", "xirr_ann")


def round_floats(value, digits=10):
    """Round every float inside `value` (nested dicts/lists too) to `digits` significant digits.

    Statistics such as volatility or the Sharpe ratio can differ in their very
    last digit from run to run (e.g. 0.15226542788387992 vs 0.1522654278838802),
    depending on how memory happens to be laid out. Ten significant digits keep
    any real change visible while ignoring that noise.
    """
    if isinstance(value, float):
        return float(f"{value:.{digits}g}")
    if isinstance(value, dict):
        return {key: round_floats(item, digits) for key, item in value.items()}
    if isinstance(value, list):
        return [round_floats(item, digits) for item in value]
    return value


def summary_as_json(result) -> str:
    """Turn compute_summary's result into stable, readable JSON for the snapshot.

    Keeps every number per account and for the whole portfolio, plus each
    held position's ticker and value (the portfolio's merged across accounts);
    leaves out the price-history table,
    which is too large to be useful in a snapshot. Numbers are rounded to 10
    significant digits (see round_floats).
    """
    accounts = [
        {**{field: acc[field] for field in ACCOUNT_FIELDS},
         "positions": [[pos["ticker"], pos["value"]] for pos in acc["positions"]]}
        for acc in result["accounts"]
    ]
    portfolio = {**result["portfolio"],
                 "positions": [[pos["ticker"], pos["value"]] for pos in result["portfolio"]["positions"]]}
    summary = {"accounts": accounts, "portfolio": portfolio, "min_date": str(result["min_date"])}
    return json.dumps(round_floats(summary), indent=2, sort_keys=True)


def test_summary_matches_snapshot(tmp_path, fake_market, snapshot):
    """Statistics for both accounts on 31-12-2024 are identical to tests/snapshots/summary.json."""
    accounts = [
        Account(1, "Stocks", "", _replay(STOCKS_EUR, tmp_path / "stocks")),
        Account(2, "ETFs", "", _replay(ETFS_AND_USD, tmp_path / "etfs")),
    ]

    result = compute_summary(accounts, date(2024, 12, 31), "31-12-2024")

    snapshot("summary.json", summary_as_json(result))


def test_an_asset_listed_recently_does_not_cut_the_history(tmp_path, fake_market, monkeypatch):
    """The history starts with the account even if an asset bought later only has prices from a recent day.

    EEE.MI has prices only from 1 May 2024, as if it had been listed then, and
    is bought on 15 May. The history used to start on 1 May, the first day
    every asset ever held had a price, so January to April vanished from the
    Statistics chart.
    """
    def listed_in_may(tickers, **kwargs):
        """The fake prices, with none for EEE.MI before 1 May 2024."""
        prices, names = fake_download_close(tickers, **kwargs)
        if "EEE.MI" in prices.columns:
            prices.loc[prices.index < "2024-05-01", "EEE.MI"] = np.nan
        return prices, names

    monkeypatch.setattr(market_data, "download_close", listed_in_may)
    df = _replay([deposit(date(2024, 1, 2), 10_000), buy(date(2024, 1, 3), "BBB.MI", 100, price=50.0, fee=0.0),
                  buy(date(2024, 5, 15), "EEE.MI", 10, price=100.0, fee=0.0)], tmp_path)

    history = summary_history([Account(1, "Test Broker", "", df)], date(2024, 6, 28), "28-06-2024")

    assert history["Date"].iloc[0] == pd.Timestamp("2024-01-03")
