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

from domain.positions import aggregate_positions, held_tickers, holdings, priced_positions
from services import market_data

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


@pytest.mark.parametrize("eee_closes, eee_price, eee_prev", [
    ([80.0, np.nan, 82.0], 82.0, 80.0),   # EEE.MI has no close on 9 January
    ([80.0, 81.0, np.nan], 81.0, 80.0),   # EEE.MI has no close yet on 10 January
], ids=["gap-yesterday", "gap-today"])
def test_a_missing_close_of_one_ticker_does_not_move_the_others(monkeypatch, eee_closes, eee_price, eee_prev):
    """Each asset takes its own latest close and the one before, whatever gaps another asset has.

    Yahoo sometimes has no daily close for a ticker (e.g. some ETFs on Borsa
    Italiana). A day missing for one ticker used to be dropped for all: AAA.MI
    was then priced, or compared with, a day older than it should.
    """
    days = pd.to_datetime(["2024-01-08", "2024-01-09", "2024-01-10"])
    closes = pd.DataFrame({"AAA.MI": [100.0, 101.0, 102.0], "EEE.MI": eee_closes}, index=days)
    monkeypatch.setattr(market_data, "download_close", lambda *args, **kwargs: (closes, {}))

    positions = priced_positions(LEDGER, date(2024, 1, 10))

    prices = {p["ticker"]: (p["price"], p["prev_close"]) for p in positions}
    assert prices == {"AAA.MI": (102.0, 101.0), "EEE.MI": (eee_price, eee_prev)}


def test_priced_positions_of_an_account_holding_nothing():
    """An account with no assets gives an empty list, without fetching any price."""
    assert priced_positions(LEDGER.iloc[:1], date(2024, 1, 1)) == []


def test_held_tickers_names_the_assets_currently_held():
    """Assets sold out (BBB.MI) are left out; each held one comes with its name."""
    assert held_tickers(LEDGER) == {"AAA.MI": "Alpha SpA", "EEE.MI": "Equity World ETF"}


def test_a_ticker_held_in_two_accounts_is_merged_at_its_average_buy_price():
    """20 BBB.MI bought at 50.05 in one account and 10 at 55.10 in another make 30 at 51.7333, worth 1800.

    Other tickers keep their place in the list, and the accounts' own positions are left unchanged.
    """
    first = [{"ticker": "BBB.MI", "quantity": 20.0, "pmc": 50.05, "price": 60.0, "value": 1200.0},
             {"ticker": "AAA.MI", "quantity": 5.0, "pmc": 100.0, "price": 102.0, "value": 510.0}]
    second = [{"ticker": "BBB.MI", "quantity": 10.0, "pmc": 55.10, "price": 60.0, "value": 600.0}]

    merged = aggregate_positions(first + second)

    assert [pos["ticker"] for pos in merged] == ["BBB.MI", "AAA.MI"]
    assert merged[0] == pytest.approx({"ticker": "BBB.MI", "quantity": 30.0, "pmc": 51.7333, "price": 60.0,
                                       "value": 1800.0}, abs=1e-4)
    assert first[0]["quantity"] == 20.0 and first[0]["pmc"] == 50.05


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
