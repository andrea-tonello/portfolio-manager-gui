"""Tests for the Value at Risk (VaR) simulation in services/analysis_service.py.

VaR answers: "over the next N days, how much could the portfolio lose, in all
but the worst 1% of cases?" The app simulates many possible outcomes and reads
the loss at the worst-1% mark. Each outcome replays blocks of real consecutive
past days of the portfolio, starting at random, rather than draws from a bell curve.
"""

import json
from datetime import date, datetime

import numpy as np
from conftest import FX_TICKER, fake_download_close
from test_ledger_snapshots import _replay, buy, deposit
from test_summary import round_floats

from domain.account import Account
from services import analysis_service, market_data
from services.analysis_service import _simulate_outcomes


def test_outcomes_chain_blocks_of_real_consecutive_days(monkeypatch):
    """Every outcome chains blocks of consecutive past days, cut to the horizon.

    The past is -10%, -10%, +10%; with blocks of 2 days, the only blocks are
    (-10%, -10%) and (-10%, +10%). 3 days are a block, then the first day of
    another, which is always -10%. On 10,000: -2,710 (0.9 × 0.9 × 0.9) or
    -1,090 (0.9 × 1.1 × 0.9). Days picked one by one could also give +3,310
    (three +10% days), but two +10% days in a row never happened.
    """
    monkeypatch.setattr(analysis_service, "VAR_BLOCK_DAYS", 2)

    outcomes = _simulate_outcomes(10_000, np.array([-0.10, -0.10, 0.10]), 3, 1_000, rng=np.random.default_rng(0))

    assert sorted({round(outcome, 2) for outcome in outcomes}) == [-2_710, -1_090]


# ── compute_var_mc: what the simulation is fed ───────────────────────

class _FixedNow(datetime):
    """A datetime whose now() is always 31 December 2024, so the VaR is computed on a fixed day."""

    @classmethod
    def now(cls, tz=None):
        """Return 31 December 2024 instead of the current time."""
        return cls(2024, 12, 31)


def _varying_fx_download_close(tickers, **kwargs):
    """fake_download_close, but with a USD->EUR rate that changes every day (between 0.90 and 0.96).

    With the fake market's constant rate, converting USD prices to EUR would
    not change their daily returns, so a mistake in the conversion would go
    unnoticed by the VaR.
    """
    prices, names = fake_download_close(tickers, **kwargs)
    if FX_TICKER in prices.columns:
        prices[FX_TICKER] = [0.90 + 0.01 * (day.day % 7) for day in prices.index]
    return prices, names


# A EUR stock (AAA.MI) and a USD stock (UUU), bought in January 2024.
INVESTMENTS = [
    buy(date(2024, 1, 3), "AAA.MI", 10, 100.0, 2.0),
    buy(date(2024, 1, 4), "UUU", 5, 200.0, 1.0, currency="USD", conv_rate=0.9),
]


def _simulation_inputs(steps, folder, monkeypatch):
    """What compute_var_mc feeds the simulation for an account made of `steps`, on 31-12-2024.

    A year of fake prices is used (from 2024-01-01). The simulation is random,
    so it is replaced by a stand-in that records its inputs: the value it is
    applied to, the portfolio's past daily returns (as a list) and the days.
    """
    monkeypatch.setattr(analysis_service, "datetime", _FixedNow)
    monkeypatch.setattr(analysis_service, "VAR_HISTORY_START", "2024-01-01")
    monkeypatch.setattr(market_data, "download_close", _varying_fx_download_close)
    # analysis_service imports download_close by name (its correlation tool uses it).
    monkeypatch.setattr(analysis_service, "download_close", _varying_fx_download_close)
    received = {}

    def record_inputs(value, daily_returns, days, num_simulations, rng=None):
        """Stand-in for _simulate_outcomes: remember the inputs and return flat outcomes."""
        received.update(value=value, daily_returns=list(daily_returns), days=days)
        return np.zeros(num_simulations)

    monkeypatch.setattr(analysis_service, "_simulate_outcomes", record_inputs)
    df = _replay(steps, folder)

    analysis_service.compute_var_mc([Account(1, "Test Broker", "", df)], 0.99, 10)
    return received


def test_var_inputs_match_snapshot(tmp_path, fake_market, monkeypatch, snapshot):
    """What compute_var_mc feeds the simulation is identical to tests/snapshots/var_inputs.json.

    The past daily returns are summed up (how many, their average, spread,
    worst and best), which is enough to notice any change in them.
    """
    received = _simulation_inputs([deposit(date(2024, 1, 2), 10_000), *INVESTMENTS], tmp_path, monkeypatch)
    returns = np.array(received.pop("daily_returns"))
    received.update(returns_count=len(returns), returns_mean=returns.mean(), returns_std=returns.std(),
                    worst_return=returns.min(), best_return=returns.max())

    snapshot("var_inputs.json", json.dumps(round_floats(received), indent=2, sort_keys=True))


def test_cash_adds_no_risk(tmp_path, fake_market, monkeypatch):
    """The same investments give the same VaR however much cash sits next to them: cash doesn't move."""
    little_cash = _simulation_inputs([deposit(date(2024, 1, 2), 2_000), *INVESTMENTS], tmp_path / "little", monkeypatch)
    lots_of_cash = _simulation_inputs([deposit(date(2024, 1, 2), 42_000), *INVESTMENTS], tmp_path / "lots", monkeypatch)

    assert little_cash == lots_of_cash
