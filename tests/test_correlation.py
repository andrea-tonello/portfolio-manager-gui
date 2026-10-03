"""Tests for compute_correlation in services/analysis_service.py (the Correlation tab).

It receives the app's own Account objects, so it must read them without
changing them.
"""

import pytest
from conftest import fake_download_close
from test_ledger_snapshots import BROKER, STOCKS_EUR, _replay

from domain.account import Account
from services import analysis_service
from services.analysis_service import compute_correlation


@pytest.fixture
def accounts(tmp_path, fake_market, monkeypatch):
    """One account with the STOCKS_EUR history: AAA.MI fully sold, 20 BBB.MI still held, plus cash rows.

    analysis_service imports download_close by name, so the fake prices are
    installed there too.
    """
    monkeypatch.setattr(analysis_service, "download_close", fake_download_close)
    return [Account(1, BROKER, "", _replay(STOCKS_EUR, tmp_path))]


def test_correlation_leaves_the_accounts_unchanged(accounts):
    """Each account keeps the same ledger object, with all its rows, after the calculation.

    It used to be replaced by its buy/sell/split rows only, so any later use
    of the account would have seen it without deposits or cash.
    """
    ledger = accounts[0].df
    rows_before = len(ledger)

    compute_correlation(accounts, "2024-01-01", "2024-12-31")

    assert accounts[0].df is ledger
    assert len(accounts[0].df) == rows_before


def test_correlation_lists_only_the_assets_still_held(accounts):
    """Assets sold out (AAA.MI) are left out; the matrix covers the ones still held."""
    result = compute_correlation(accounts, "2024-01-01", "2024-12-31")

    assert result["active_tickers"] == ["BBB.MI"]
    assert list(result["correlation_matrix"].columns) == ["BBB.MI"]
