"""Tests for domain/positions.py: which assets an account holds, and what they are worth.

holdings() reads the ledger only; priced_positions() also fetches prices
(faked here by the fake_market fixture); held_tickers() lists what is
currently held, for the Home split check and the Operations split form.
"""

import ast
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from domain.positions import held_tickers, holdings, priced_positions

ROOT = Path(__file__).resolve().parent.parent

# A small ledger: BBB.MI is bought and later sold out, AAA.MI and CCC.MI are still held.
LEDGER = pd.DataFrame({
    "date": ["01-01-2024", "02-01-2024", "03-01-2024", "04-01-2024", "05-01-2024", "08-01-2024"],
    "operation": ["Deposit", "Buy", "Buy", "Dividend", "Sell", "Buy"],
    "ticker": [np.nan, "BBB.MI", "AAA.MI", "AAA.MI", "BBB.MI", "EEE.MI"],
    "asset_name": [np.nan, "Beta SpA", "Alpha SpA", "Alpha SpA", "Beta SpA", "Equity World ETF"],
    "curr": ["EUR"] * 6,
    "qt_held": [np.nan, 10.0, 5.0, np.nan, 0.0, 3.0],
    "abp": [np.nan, 50.0, 100.0, np.nan, 0.0, 80.0],
})


def test_holdings_lists_every_asset_and_those_still_held():
    """All assets ever bought, and separately those with a quantity above zero, without fetching prices."""
    all_assets, active = holdings(LEDGER)

    assert sorted(all_assets["ticker"]) == ["AAA.MI", "BBB.MI", "EEE.MI"]
    assert dict(zip(active["ticker"], active["qt_held"])) == {"AAA.MI": 5.0, "EEE.MI": 3.0}


def test_holdings_on_a_past_date_and_without_one_ticker():
    """On 4 January BBB.MI was still held and EEE.MI not yet bought; exclude_ticker leaves an asset out."""
    _, active = holdings(LEDGER, ref_date=date(2024, 1, 4), exclude_ticker="AAA.MI")

    assert list(active["ticker"]) == ["BBB.MI"]


def test_priced_positions_values_each_held_asset(fake_market):
    """Each held asset is valued at its closing price on the date (fake prices: +0.1% per day from 2024-01-01).

    Example: AAA.MI closes at 100.3 on 4 January, so 5 units are worth 501.5 EUR.
    """
    positions = priced_positions(LEDGER, date(2024, 1, 4))

    values = {p["ticker"]: (p["quantity"], p["price"], p["value"]) for p in positions}
    assert values == {
        "AAA.MI": (5.0, pytest.approx(100.3), pytest.approx(501.5)),
        "BBB.MI": (10.0, pytest.approx(50.15), pytest.approx(501.5)),
    }


def test_priced_positions_of_an_account_holding_nothing():
    """An account with no assets gives an empty list, without fetching any price."""
    assert priced_positions(LEDGER.iloc[:1], date(2024, 1, 1)) == []


def test_held_tickers_names_the_assets_currently_held():
    """Assets sold out (BBB.MI) are left out; each held one comes with its name."""
    assert held_tickers(LEDGER) == {"AAA.MI": "Alpha SpA", "EEE.MI": "Equity World ETF"}


def test_domain_code_does_not_import_the_ui():
    """Nothing in domain/ imports Flet, the screens or the UI components, so it can run (and be tested) without a UI."""
    ui_modules = ("flet", "views", "components")
    offenders = []
    for path in sorted((ROOT / "domain").glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            offenders += [f"{path.name}: {n}" for n in names if n.split(".")[0] in ui_modules]

    assert offenders == []
