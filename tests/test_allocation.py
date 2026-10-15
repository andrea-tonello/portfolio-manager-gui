"""Tests for compute_allocation and compute_sector_allocation, the numbers behind the Allocation tab.

The pie splits the portfolio between cash and the kinds of asset held, both
taken on the same date. The sector split shares each stock and equity ETF
between its sectors, and leaves the rest of the portfolio out.
"""

from datetime import date

import pytest
from test_ledger_snapshots import STOCKS_EUR, _replay, buy, deposit

from domain.account import Account
from domain.ledger import Product
from services import analysis_service
from services.analysis_service import UNCLASSIFIED, compute_allocation, compute_sector_allocation


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


# An equity ETF, a stock (in USD) and a money-market ETF, all held on DAY.
MIXED = [
    deposit(date(2024, 1, 2), 20_000),
    buy(date(2024, 1, 3), "EEE.MI", 10, price=80.0, fee=5.0, product="ETF-S", ter="0.2%", fee_mode="loss"),
    buy(date(2024, 1, 4), "UUU", 5, price=200.0, fee=1.0, currency="USD", conv_rate=0.9),
    buy(date(2024, 1, 5), "MMM.MI", 100, price=10.0, fee=0.0, product="ETF-M", ter="0.1%", fee_mode="abp"),
]
DAY = "2024-02-15"


def test_sector_allocation_splits_each_stock_and_equity_etf_by_its_sectors(tmp_path, fake_market, monkeypatch):
    """The equity ETF's value is shared between its sectors; the stock Yahoo has no sectors for is unclassified.

    EEE.MI is 25% technology and 75% financial services. The money-market
    ETF and the cash have no sector: they only count in the portfolio's value.
    """
    monkeypatch.setattr(analysis_service, "fetch_sector_weights",
                        lambda tickers: {"EEE.MI": {"technology": 0.25, "financial_services": 0.75}})
    account = Account(1, "Mixed", "", _replay(MIXED, tmp_path))
    by_class = compute_allocation([account], DAY)
    etf, stock = by_class[Product.ETF_STOCK], by_class[Product.STOCK]
    assert by_class[Product.ETF_MM] > 0 and by_class[Product.CASH] > 0

    allocation, portfolio_value = compute_sector_allocation([account], DAY)

    assert allocation == pytest.approx({"technology": 0.25 * etf, "financial_services": 0.75 * etf,
                                        UNCLASSIFIED: stock})
    assert portfolio_value == pytest.approx(sum(by_class.values()))
