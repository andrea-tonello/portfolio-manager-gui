"""Tests for compute_drawdown in services/analysis_service.py (the Drawdown tab).

The drawdown is how far the portfolio's growth has fallen below its highest
point so far. Deposits and withdrawals are not growth: they are taken out, as
in the time-weighted return (TWRR). The fake prices rise 0.1% per day, so in
these accounts any fall comes from the cash flows, or from a fall made on purpose.
"""

from datetime import date

import numpy as np
import pandas as pd
import pytest
from conftest import fake_download_close
from test_ledger_snapshots import _replay, buy, deposit, sell, withdrawal

from domain.account import Account
from services import market_data
from services.analysis_service import compute_drawdown

INVESTED = [deposit(date(2024, 1, 2), 10_000), buy(date(2024, 1, 3), "BBB.MI", 100, price=50.0, fee=0.0)]


@pytest.mark.parametrize("asked, shown", [
    ("2023-06-01", date(2024, 1, 2)),
    ("2024-03-01", date(2024, 3, 1)),
], ids=["before-the-first-operation", "within-the-history"])
def test_the_period_starts_no_earlier_than_the_first_operation(tmp_path, fake_market, asked, shown):
    """Asked to start before the first operation (02-01-2024), the drawdown says it starts there; a later start is kept."""
    account = Account(1, "Test Broker", "", _replay(INVESTED, tmp_path))

    assert compute_drawdown([account], asked, "2024-06-28")["start"] == shown


def max_drawdown(steps, tmp_path):
    """The maximum drawdown, from 02-01-2024 to 28-06-2024, of an account made of `steps`."""
    account = Account(1, "Test Broker", "", _replay(steps, tmp_path))
    return compute_drawdown([account], "2024-01-02", "2024-06-28")["mdd"]


def test_a_withdrawal_is_not_a_drawdown(tmp_path, fake_market):
    """Taking 4,000 out while the stock only rises leaves the drawdown at 0%.

    Measured on the NAV, as it used to be, the withdrawal was a 38.81% fall.
    """
    assert max_drawdown([*INVESTED, withdrawal(date(2024, 3, 1), 4_000)], tmp_path) == 0


def test_a_deposit_does_not_hide_a_fall(tmp_path, fake_market, monkeypatch):
    """BBB.MI falls 20% during March, and 6,000 are deposited halfway through: the drawdown is 7.43%.

    Without the deposit it would be 9.20%: the second half of the fall hits a
    portfolio with more cash in it. Measured on the NAV, as it used to be, the
    deposit made it look like 4.21%.
    """
    def falling(tickers, **kwargs):
        """The fake prices, with BBB.MI sliding from 100% to 80% of its value between 1 and 29 March 2024."""
        prices, names = fake_download_close(tickers, **kwargs)
        if "BBB.MI" in prices.columns:
            share = np.clip((prices.index - pd.Timestamp("2024-03-01")).days / 28, 0, 1)
            prices["BBB.MI"] = prices["BBB.MI"] * (1 - 0.2 * share)
        return prices, names

    monkeypatch.setattr(market_data, "download_close", falling)

    assert max_drawdown([*INVESTED, deposit(date(2024, 3, 15), 6_000)], tmp_path) == pytest.approx(-0.0743, abs=1e-4)