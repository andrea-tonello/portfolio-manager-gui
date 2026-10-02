"""Tests for compute_correlation in services/analysis_service.py (the Correlation tab).

`data` is the list of [account index, ledger DataFrame] pairs the Analysis
screen builds; the correlation must read it without changing it.
"""

import pytest
from conftest import fake_download_close
from test_ledger_snapshots import STOCKS_EUR, _replay

from services import analysis_service
from services.analysis_service import compute_correlation


@pytest.fixture
def data(tmp_path, fake_market, monkeypatch):
    """One account with the STOCKS_EUR history: AAA.MI fully sold, 20 BBB.MI still held, plus cash rows.

    analysis_service imports download_close by name, so the fake prices are
    installed there too.
    """
    monkeypatch.setattr(analysis_service, "download_close", fake_download_close)
    return [[1, _replay(STOCKS_EUR, tmp_path)]]


def test_correlation_leaves_the_callers_data_unchanged(data):
    """The account's ledger in `data` is the same object, with all its rows, after the calculation.

    It used to be replaced by its buy/sell/split rows only, so any later use
    of `data` would have seen an account without deposits or cash.
    """
    ledger = data[0][1]
    rows_before = len(ledger)

    compute_correlation(data, "2024-01-01", "2024-12-31")

    assert data[0][1] is ledger
    assert len(data[0][1]) == rows_before


def test_correlation_lists_only_the_assets_still_held(data):
    """Assets sold out (AAA.MI) are left out; the matrix covers the ones still held."""
    result = compute_correlation(data, "2024-01-01", "2024-12-31")

    assert result["active_tickers"] == ["BBB.MI"]
    assert list(result["correlation_matrix"].columns) == ["BBB.MI"]
