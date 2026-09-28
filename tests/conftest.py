"""Shared test fixtures: fake market data, a real Translator, snapshot comparison."""

from pathlib import Path

import pandas as pd
import pytest

import utils.account
from utils.translator import Translator

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT_DIR = Path(__file__).resolve().parent / "snapshots"


# ── Fake market data ─────────────────────────────────────────────────
# Deterministic prices so tests never depend on Yahoo Finance.
# Each price drifts up 0.1% per calendar day from 2024-01-01, and raw
# closes are divided by the split ratio from the split date onwards,
# like real (unadjusted) Yahoo closes.

FAKE_BASE_PRICES = {
    "AAA.MI": 100.0,
    "BBB.MI": 50.0,
    "EEE.MI": 80.0,
    "MMM.MI": 10.0,
    "UUU": 200.0,
}
FAKE_SPLITS = {"AAA.MI": (pd.Timestamp("2024-07-01"), 2.0)}
FAKE_USDEUR = 0.91
_PRICE_EPOCH = pd.Timestamp("2024-01-01")


def fake_close(ticker: str, day: pd.Timestamp) -> float:
    """Return the made-up closing price of `ticker` on `day`, in the ticker's own currency.

    Example: AAA.MI closes at 100.0 on 2024-01-01, 101.0 on 2024-01-11, and
    at half its drifted price from its 2:1 split on 2024-07-01.
    """
    price = FAKE_BASE_PRICES[ticker] * (1 + 0.001 * (day - _PRICE_EPOCH).days)
    split = FAKE_SPLITS.get(ticker)
    if split and day >= split[0]:
        price /= split[1]
    return round(price, 4)


def fake_download_close(tickers, start=None, end=None, period=None, adjusted=False):
    """Offline stand-in for services.market_data.download_close.

    Returns the same shapes as the real function: `(prices, names)`, where
    `prices` has one row per weekday between `start` and `end` and is a Series
    when a single ticker is requested, a DataFrame otherwise. Unknown tickers
    are left out, as Yahoo would. `adjusted` is accepted but ignored.
    """
    if period is not None:
        raise NotImplementedError("fake_download_close only supports start/end")
    if isinstance(tickers, str):
        tickers = [tickers]
    index = pd.bdate_range(pd.Timestamp(start).normalize(), pd.Timestamp(end).normalize(), name="Date")
    known = [tk for tk in tickers if tk in FAKE_BASE_PRICES]
    df = pd.DataFrame({tk: [fake_close(tk, day) for day in index] for tk in known}, index=index)
    names = {tk: f"{tk} Name" for tk in known}
    if df.empty:
        return pd.DataFrame(), names
    if len(tickers) == 1 and tickers[0] in df.columns:
        return df[tickers[0]], names
    return df, names


def fake_fetch_exchange_rate(ref_date=None) -> float:
    """Offline stand-in for services.market_data.fetch_exchange_rate: always FAKE_USDEUR."""
    return FAKE_USDEUR


@pytest.fixture
def fake_market(monkeypatch):
    """Make utils.account use the fake prices and exchange rate above for the duration of a test.

    Request this fixture in any test that builds account rows or values
    positions. The originals are restored automatically when the test ends.
    """
    monkeypatch.setattr(utils.account, "download_close", fake_download_close)
    monkeypatch.setattr(utils.account, "fetch_exchange_rate", fake_fetch_exchange_rate)


# ── Translator ───────────────────────────────────────────────────────

@pytest.fixture
def translator():
    """The app's real English Translator, loaded from the project's locales/ folder."""
    return Translator(language_code="en", locales_dir=str(ROOT / "locales"))


# ── Snapshots ────────────────────────────────────────────────────────

def pytest_addoption(parser):
    """Add the `--update-snapshots` command-line flag to pytest."""
    parser.addoption(
        "--update-snapshots", action="store_true",
        help="Rewrite tests/snapshots/* with the current output instead of comparing.",
    )


@pytest.fixture
def snapshot(request):
    """Provide a `check(name, text)` function that compares `text` with tests/snapshots/<name>.

    Usage in a test: `snapshot("stocks_eur.csv", df.to_csv(index=False))`.
    When pytest runs with --update-snapshots, the file is overwritten with
    `text` instead of being compared.
    """
    update = request.config.getoption("--update-snapshots")

    def check(name: str, text: str):
        """Fail if `text` differs from the stored snapshot `name` (or write it in update mode)."""
        path = SNAPSHOT_DIR / name
        if update:
            SNAPSHOT_DIR.mkdir(exist_ok=True)
            path.write_text(text, encoding="utf-8")
            return
        if not path.exists():
            pytest.fail(f"Snapshot {name} missing: run `uv run pytest --update-snapshots` and review it.")
        assert text.splitlines() == path.read_text(encoding="utf-8").splitlines()

    return check
