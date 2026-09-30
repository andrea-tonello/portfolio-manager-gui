"""Characterisation test for compute_summary, the numbers behind the Statistics tab.

It runs compute_summary on the two test accounts from test_ledger_snapshots.py
(one still holding shares at the end, one fully sold) with the fake prices, and
compares the results with tests/snapshots/summary.json. Like the CSV snapshots,
it records what the code does today; regenerate with --update-snapshots only
after an intended change.
"""

import json
from datetime import date

from services.analysis_service import compute_summary
from test_ledger_snapshots import ETFS_AND_USD, STOCKS_EUR, _replay

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
    held position's ticker and value; leaves out the price-history table,
    which is too large to be useful in a snapshot. Numbers are rounded to 10
    significant digits (see round_floats).
    """
    accounts = [
        {**{field: acc[field] for field in ACCOUNT_FIELDS},
         "positions": [[pos["ticker"], pos["value"]] for pos in acc["positions"]]}
        for acc in result["accounts"]
    ]
    summary = {"accounts": accounts, "portfolio": result["portfolio"], "min_date": str(result["min_date"])}
    return json.dumps(round_floats(summary), indent=2, sort_keys=True)


def test_summary_matches_snapshot(tmp_path, translator, fake_market, snapshot):
    """Statistics for both accounts on 31-12-2024 are identical to tests/snapshots/summary.json."""
    data = [
        [1, _replay(STOCKS_EUR, translator, tmp_path / "stocks")],
        [2, _replay(ETFS_AND_USD, translator, tmp_path / "etfs")],
    ]

    result = compute_summary(translator, {1: "Stocks", 2: "ETFs"}, data, date(2024, 12, 31), "31-12-2024")

    snapshot("summary.json", summary_as_json(result))
