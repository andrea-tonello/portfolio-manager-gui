"""Characterisation tests for the account CSV builders in domain/newrow.py.

Each test replays a fixed sequence of operations through newrow_cash,
newrow_etf_stock and newrow_split, starting from the opening row written by
create_defaults, and compares the resulting CSV with tests/snapshots/.

The snapshots record what the code does *today*, not what it should do. A diff
means the numbers written to users' CSV files changed. If that is intended,
regenerate with `uv run pytest --update-snapshots` and review the diff in git.
"""

import io
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd
import pytest

from domain.journal import Operation
from domain.newrow import newrow_cash, newrow_etf_stock, newrow_split
from services.account_service import create_defaults, ledger_path
from utils.constants import DATE_FORMAT

BROKER = "Test Broker"
NAMES = {
    "AAA.MI": "Alpha SpA",
    "BBB.MI": "Beta SpA",
    "EEE.MI": "Equity World ETF",
    "MMM.MI": "Money Market ETF",
    "UUU": "Uniform Corp",
}


# ── Operations ───────────────────────────────────────────────────────
# Each helper returns a Step: called as `step(df) -> df`, it calls the
# builders with the same arguments the Operations screen passed before the
# journal, which journal.apply passes now.

@dataclass(frozen=True)
class Step:
    """One operation of a scenario, in the two forms the tests need.

    Calling it records the operation the way the app does today: one newrow_*
    call, returning the ledger with one more row. `fields` is the same
    operation as the journal stores it (domain/journal.py), without the id and
    order of entry that each journal gives it, e.g.
    {"kind": "withdrawal", "date": date(2024, 9, 2), "amount": 500}.
    """

    record: Callable[[pd.DataFrame], pd.DataFrame]
    fields: dict

    def __call__(self, df: pd.DataFrame) -> pd.DataFrame:
        """Return the ledger `df` with this operation's row added."""
        return self.record(df)


def deposit(day, amount):
    """Step that deposits `amount` EUR of cash into the account."""
    return Step(lambda df: newrow_cash(df, _fmt(day), day, BROKER, amount,
                                       "Deposit", "Cash", np.nan, np.nan),
                {"kind": "deposit", "date": day, "amount": amount})


def withdrawal(day, amount):
    """Step that withdraws `amount` EUR of cash. Pass a positive amount; it is stored as negative."""
    return Step(lambda df: newrow_cash(df, _fmt(day), day, BROKER, -amount,
                                       "Withdrawal", "Cash", np.nan, np.nan),
                {"kind": "withdrawal", "date": day, "amount": amount})


def dividend(day, ticker, amount):
    """Step that records a dividend of `amount` EUR received from `ticker`."""
    return Step(lambda df: newrow_cash(df, _fmt(day), day, BROKER, amount,
                                       "Dividend", "Dividend", ticker, NAMES[ticker]),
                {"kind": "dividend", "date": day, "ticker": ticker, "asset_name": NAMES[ticker], "amount": amount})


def charge(day, amount, description):
    """Step that records a tax or fee paid in cash (e.g. stamp duty).

    Pass a positive amount; it is stored as negative. `description` becomes
    the row's product, as in the app.
    """
    return Step(lambda df: newrow_cash(df, _fmt(day), day, BROKER, -abs(amount),
                                       "Tax", description, np.nan, np.nan),
                {"kind": "charge", "date": day, "amount": abs(amount), "description": description})


def buy(day, ticker, qty, price, fee, *, product="Stock", currency="EUR",
        conv_rate=1.0, ter=np.nan, fee_mode="abp"):
    """Step that buys `qty` shares of `ticker` at `price` (in `currency`) plus `fee` EUR.

    `conv_rate` is the USD→EUR rate; `ter` and `fee_mode` only matter for ETFs.
    """
    return Step(lambda df: newrow_etf_stock(
        df, _fmt(day), day, BROKER, currency, product, ticker, qty, price,
        conv_rate, ter, fee, is_buy=True, asset_name=NAMES[ticker], fee_mode=fee_mode),
        _trade_fields("buy", day, ticker, qty, price, fee, product, currency, conv_rate, ter, fee_mode, 0.26))


def sell(day, ticker, qty, price, fee, *, product="Stock", currency="EUR",
         conv_rate=1.0, ter=np.nan, fee_mode="abp", tax_rate=0.26):
    """Step that sells `qty` shares of `ticker` at `price` (in `currency`) minus `fee` EUR.

    `tax_rate` is applied to the taxable gain: 0.26 by default; in the app the
    user can enter a different rate only for money-market ETFs.
    """
    return Step(lambda df: newrow_etf_stock(
        df, _fmt(day), day, BROKER, currency, product, ticker, qty, price,
        conv_rate, ter, fee, is_buy=False, asset_name=NAMES[ticker],
        tax_rate=tax_rate, fee_mode=fee_mode),
        _trade_fields("sell", day, ticker, qty, price, fee, product, currency, conv_rate, ter, fee_mode, tax_rate))


def split(day, ticker, ratio):
    """Step that records a stock split of `ticker` (ratio 2.0 = 2:1, 0.5 = 1:2)."""
    return Step(lambda df: newrow_split(df, _fmt(day), day, BROKER, ticker, ratio),
                {"kind": "split", "date": day, "ticker": ticker, "ratio": ratio})


def _trade_fields(kind, day, ticker, qty, price, fee, product, currency, conv_rate, ter, fee_mode, tax_rate):
    """Return the journal fields of a buy or sell step; a TER left NaN (not given) is None in the journal."""
    return {"kind": kind, "date": day, "ticker": ticker, "asset_name": NAMES[ticker], "product": product,
            "currency": currency, "conv_rate": conv_rate, "quantity": qty, "price": price, "fee": fee,
            "fee_mode": fee_mode, "tax_rate": tax_rate, "ter": None if pd.isna(ter) else ter}


def journal_of(steps):
    """Return the journal of a scenario: one operation per step, entered in the scenario's order (seq 1, 2, ...)."""
    return [Operation(id=f"op{seq}", seq=seq, **step.fields) for seq, step in enumerate(steps, start=1)]


def _fmt(day):
    """Format a date the way the app stores it in the CSV (DD-MM-YYYY)."""
    return day.strftime(DATE_FORMAT)


# ── Scenarios ────────────────────────────────────────────────────────

# Stocks in EUR: average price, gain, loss into the carryforward, cash
# operations, a later gain offset by the carryforward, a 2:1 split, full exit.
STOCKS_EUR = [
    deposit(date(2024, 1, 2), 10_000),
    buy(date(2024, 1, 3), "AAA.MI", 10, price=100.0, fee=2.0),
    buy(date(2024, 2, 1), "AAA.MI", 10, price=110.0, fee=2.0),
    sell(date(2024, 3, 1), "AAA.MI", 5, price=130.0, fee=2.0),
    sell(date(2024, 4, 2), "AAA.MI", 5, price=90.0, fee=2.0),
    dividend(date(2024, 4, 15), "AAA.MI", 12.5),
    charge(date(2024, 4, 16), 1.5, "Stamp duty"),
    buy(date(2024, 5, 2), "BBB.MI", 20, price=50.0, fee=1.0),
    sell(date(2024, 6, 3), "AAA.MI", 5, price=120.0, fee=2.0),
    split(date(2024, 7, 1), "AAA.MI", 2.0),
    sell(date(2024, 8, 1), "AAA.MI", 10, price=70.0, fee=2.0),
    withdrawal(date(2024, 9, 2), 500),
]

# ETFs and USD: fees recorded as losses on the buy and on the sale, ETF gains
# that must not be offset by the carryforward (nor consume it), a money-market
# ETF at 12.5% tax, and a USD stock whose gain is offset by the 10 EUR
# carryforward built up from the ETF fees.
ETFS_AND_USD = [
    deposit(date(2024, 1, 2), 20_000),
    buy(date(2024, 1, 3), "EEE.MI", 10, price=80.0, fee=5.0,
        product="ETF-S", ter="0.2%", fee_mode="loss"),
    buy(date(2024, 1, 4), "UUU", 5, price=200.0, fee=1.0,
        currency="USD", conv_rate=0.9),
    sell(date(2024, 3, 1), "EEE.MI", 10, price=90.0, fee=5.0,
         product="ETF-S", ter="0.2%", fee_mode="loss"),
    buy(date(2024, 3, 4), "MMM.MI", 100, price=10.0, fee=0.0,
        product="ETF-M", ter="0.1%", fee_mode="abp"),
    sell(date(2024, 6, 3), "MMM.MI", 100, price=10.5, fee=0.0,
         product="ETF-M", ter="0.1%", fee_mode="abp", tax_rate=0.125),
    sell(date(2024, 7, 1), "UUU", 5, price=220.0, fee=1.0,
         currency="USD", conv_rate=0.92),
]


# ── Tests ────────────────────────────────────────────────────────────

# Tells pytest: "run the decorated test once for each entry in this list, 
#                filling the parameters name and steps from that entry." 
# The list has 2 entries, so each decorated function runs twice
SCENARIOS = pytest.mark.parametrize("name, steps", [
    ("stocks_eur", STOCKS_EUR),
    ("etfs_and_usd", ETFS_AND_USD),
])


def _replay(steps, folder, *, reload_each_step=False) -> pd.DataFrame:
    """Build an account CSV in `folder` by applying `steps` in order, and return the final DataFrame.

    'folder' is tmp_path, a pytest temporary directory created elsewhere. 
    That's where the output CSV will be stored.

    It starts from the opening row that create_defaults writes when an account
    is created, read back from disk exactly as the app does on first launch.
    With reload_each_step, the CSV is saved and read back after each operation,
    as happens when the user adds transactions across several app sessions.
    """
    folder.mkdir(parents=True, exist_ok=True)
    create_defaults(str(folder), BROKER)
    path = ledger_path(str(folder), BROKER)
    df = pd.read_csv(path)
    for step in steps:
        df = step(df)
        if reload_each_step:
            df.to_csv(path, index=False)
            df = pd.read_csv(path)
    return df


@SCENARIOS
def test_ledger_matches_snapshot(name, steps, tmp_path, fake_market, snapshot):
    """The CSV produced by the scenario is identical to tests/snapshots/<name>.csv.

    Fails if any value written to the account CSV changes, e.g. after a
    refactor alters a calculation, rounding or the column layout.
    """
    df = _replay(steps, tmp_path)           # run the scenario with today's code
    snapshot(f"{name}.csv", df.to_csv(index=False))     # hand the resulting CSV text to check()



@SCENARIOS
def test_ledger_numbers_survive_reload_between_operations(name, steps, tmp_path, fake_market):
    """Saving and reloading the CSV between operations does not change any value.

    In the app, each new operation may be computed from a CSV reloaded at
    launch rather than from the table still in memory. Both paths must give
    the same numbers.
    """
    in_memory = _replay(steps, tmp_path / "a")
    reloaded = _replay(steps, tmp_path / "b", reload_each_step=True)

    # Compare parsed values, not text: once reloaded, re-saved rows format some
    # columns differently (qt_exch "+10" -> "10.0", conv_rate "1.000000" -> "1.0").
    in_memory = pd.read_csv(io.StringIO(in_memory.to_csv(index=False)))
    pd.testing.assert_frame_equal(reloaded, in_memory, check_dtype=False)


def test_a_split_row_values_the_split_asset_at_that_days_price(tmp_path, fake_market):
    """A split row's asset value prices every asset at that day's close, the split one included.

    The 2:1 split of AAA.MI on 01-07-2024 leaves 10 units with an average buy
    price of 52.60, closing at 59.10 that day: 591 EUR, next to 1,182 of
    BBB.MI. Valued at the average buy price, as it used to be, AAA.MI counted
    526 and the row stored 1,708 instead of 1,773.
    """
    split_row = _replay(STOCKS_EUR[:10], tmp_path).iloc[-1]

    assert (split_row["operation"], split_row["ticker"]) == ("Split", "AAA.MI")
    assert (split_row["assets_value"], split_row["nav"]) == (1773.0, 10341.28)
