"""Tests for compute_allocation, the numbers behind the Allocation pie chart.

The pie splits the portfolio, on the date the user picks, between cash and the
kinds of asset held. Both must be taken on that same date.
"""

import pytest
from test_ledger_snapshots import STOCKS_EUR, _replay

from domain.account import Account
from domain.ledger import Product
from services.analysis_service import compute_allocation


@pytest.mark.parametrize("day, cash", [
    ("2024-02-15", 7896.00),  # between the second buy (01-02) and the first sell (01-03)
    ("2024-10-01", 8723.12),  # after the last operation: today's cash
    ("2023-12-01", 0.0),      # before the first deposit: nothing yet
], ids=["between-operations", "after-the-last", "before-the-first"])
def test_allocation_takes_the_cash_held_on_the_chosen_date(day, cash, tmp_path, fake_market):
    """The cash slice is the cash held on the chosen day, like the assets next to it.

    It used to be the cash held today whatever the date (REFACTORING.md,
    Appendix A item 4): on 15-02-2024 it showed 8723.12 instead of 7896.00.
    """
    account = Account(1, "Stocks", "", _replay(STOCKS_EUR, tmp_path))

    assert compute_allocation([account], day)[Product.CASH] == cash
