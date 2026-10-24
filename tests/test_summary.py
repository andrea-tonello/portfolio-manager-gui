"""Tests for compute_summary, the numbers behind the Statistics tab.

The characterisation test runs compute_summary on the two test accounts from
test_ledger_snapshots.py (one still holding shares at the end, one fully sold)
with the fake prices, and compares the results with tests/snapshots/summary.json.
Like the CSV snapshots, it records what the code does today; regenerate with
--update-snapshots only after an intended change. The others check the
figures of a period with a start date.
"""

import json
from datetime import date

import numpy as np
import pandas as pd
import pytest
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


# ── A period with a start date ───────────────────────────────────────
# 10,000 deposited on 02-01-2024, half spent on 100 BBB.MI at 50 (no fee). The
# fake price rises 0.1% a day from 50 on 01-01-2024: 53.00 on 01-03-2024 and
# 58.95 on 28-06-2024. So the account is worth 5,000 + 5,300 = 10,300 on
# 01-03-2024 and 5,000 + 5,895 = 10,895 on 28-06-2024: 595 gained in between.
INVESTED = [deposit(date(2024, 1, 2), 10_000), buy(date(2024, 1, 3), "BBB.MI", 100, price=50.0, fee=0.0)]


def _figures(steps, folder, start):
    """The portfolio figures of an account made of `steps`, on 28-06-2024, for the period from `start`."""
    account = Account(1, "Test Broker", "", _replay(steps, folder))
    return compute_summary([account], date(2024, 6, 28), "28-06-2024", start=start)["portfolio"]


def test_a_period_measures_its_returns_from_the_value_on_its_first_day(tmp_path, fake_market):
    """From 01-03-2024: 595 gained, and both returns are 10,895 / 10,300 - 1 = +5.78%.

    The 10,300 the account was worth on the start day counts as the money put
    in (XIRR), and the value a day earlier as the base (TWRR). The values
    themselves are those on the end date, as without a start.
    """
    figures = _figures(INVESTED, tmp_path, start=date(2024, 3, 1))

    assert figures["period_gain"] == pytest.approx(595.0)
    assert figures["xirr_full"] == pytest.approx(10_895 / 10_300 - 1, rel=1e-6)
    assert figures["twrr_full"] == pytest.approx(10_895 / 10_300 - 1, rel=1e-6)
    assert figures["nav"] == pytest.approx(10_895.0)


def test_money_deposited_during_the_period_is_not_a_gain(tmp_path, fake_market):
    """1,000 deposited on 02-04-2024: the account ends at 11,895, but the gain is still 595."""
    figures = _figures([*INVESTED, deposit(date(2024, 4, 2), 1_000)], tmp_path, start=date(2024, 3, 1))

    assert figures["nav"] == pytest.approx(11_895.0)
    assert figures["period_gain"] == pytest.approx(595.0)


@pytest.mark.parametrize("start", [date(2024, 1, 2), date(2023, 6, 1)], ids=["first-operation", "before-it"])
def test_a_start_on_or_before_the_first_operation_changes_nothing(tmp_path, fake_market, start):
    """MAX, or any earlier start, gives the figures of no start at all, and no gain line."""
    figures = _figures(INVESTED, tmp_path / "start", start=start)
    no_start = _figures(INVESTED, tmp_path / "none", start=None)

    assert figures["period_gain"] is None
    for name in ("xirr_full", "xirr_ann", "twrr_full", "twrr_ann", "volatility", "sharpe_ratio"):
        assert figures[name] == pytest.approx(no_start[name]), name
