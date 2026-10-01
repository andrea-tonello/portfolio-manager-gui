"""Shared test fixtures: network guard, fake market data, a real Translator, app state and
page stand-ins for building screens, snapshot comparison."""

import os
import urllib.request
from pathlib import Path

import flet as ft
import pandas as pd
import pytest

import utils.account
from app_state import AppState
from services import config_service
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
FX_TICKER = "USDEUR=X"
_PRICE_EPOCH = pd.Timestamp("2024-01-01")


def fake_close(ticker: str, day: pd.Timestamp) -> float:
    """Return the made-up closing price of `ticker` on `day`, in the ticker's own currency.
    + 0.1% per day.

    Example: AAA.MI closes at 100.0 on 2024-01-01, and at 101.0 after 10 days on 2024-01-11.
    At 2024-07-01 it would be at 118.2 -> but 2:1 split -> 59.1.

    The USD->EUR exchange rate, which Yahoo serves as the ticker "USDEUR=X",
    is constant at FAKE_USDEUR (the portfolio history needs it for USD assets).
    """
    if ticker == FX_TICKER:
        return FAKE_USDEUR
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
    known = [tk for tk in tickers if tk in FAKE_BASE_PRICES or tk == FX_TICKER]
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


# ── App state and page (for building screens) ────────────────────────

class FakePage:
    """Stand-in for ft.Page with the attributes the app's screens use.

    Background work (run_thread / run_task) is recorded but never run, so no
    live prices are fetched; dialogs are collected in `dialogs` instead of shown.
    """

    def __init__(self):
        """Start as an empty page with one root view, like a freshly opened app."""
        self.width = 400
        self.data = {}
        self.views = [ft.View(route="/")]
        self.controls = []
        self.overlay = []
        self.services = []
        self.dialogs = []
        self.appbar = self.navigation_bar = self.end_drawer = None
        self.on_view_pop = self.on_media_change = None
        self.web = False
        self.platform = ft.PagePlatform.LINUX

    def update(self):
        """Do nothing: there is no screen to redraw."""

    def run_thread(self, fn, *args):
        """Ignore background work (it would fetch live prices)."""

    def run_task(self, fn, *args):
        """Ignore async background work."""

    def show_dialog(self, dialog):
        """Record the dialog instead of displaying it."""
        self.dialogs.append(dialog)

    def pop_dialog(self):
        """Close the most recent dialog, if any."""
        if self.dialogs:
            self.dialogs.pop()


@pytest.fixture
def page():
    """A fresh FakePage (desktop platform by default; set `page.platform` to simulate others)."""
    return FakePage()


@pytest.fixture
def state(tmp_path, translator, fake_market):
    """An AppState for user "Tester" with one account holding the STOCKS_EUR history.

    Built the same way the app stores data: config.ini files for language,
    users and brokers, and the account CSV in the user's resources folder.
    """
    from test_ledger_snapshots import STOCKS_EUR, _replay  # the account history used by the snapshots

    config = str(tmp_path / "config")
    os.makedirs(config)
    config_service.save_language(config, "en")
    config_service.save_users(config, {1: "Tester"})
    config_service.save_active_user(config, 1)
    user_folder = config_service.get_user_folder(config, "Tester")
    resources = config_service.get_user_res_folder(config, "Tester")
    os.makedirs(resources)
    config_service.save_brokers(user_folder, {1: "Test Broker"}, reset=True)
    df = _replay(STOCKS_EUR, translator, Path(resources))
    df.to_csv(os.path.join(resources, "Report Test Broker.csv"), index=False)

    app_state = AppState(base_path=str(tmp_path))
    app_state.load_config()
    app_state.load_all_accounts()
    assert app_state.accounts, "the test account should have loaded"
    return app_state


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


# ── Network guard ────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def block_network(monkeypatch):
    """Stop every test from reaching the internet, and fail any test that tries.

    `autouse=True` means it runs for every test automatically; no test has to ask for it.

    The app only goes online through urllib.request.urlopen (in
    services/market_data.py), so that is replaced with a function that records
    the URL and raises an error. Raising alone is not enough: the app often
    catches the error and carries on with "no data" (e.g. download_close
    returns an empty table). So after the test finishes, any recorded attempt
    fails the test and lists the URLs.

    A test that builds account rows but forgets `fake_market`
    ends with "Test tried to access the network: https://query1.finance.yahoo.com/...".
    """
    attempts = []

    def refuse(request, *args, **kwargs):
        """Stand-in for urlopen: remember which URL was requested, then refuse to open it."""
        url = getattr(request, "full_url", request)  # urlopen accepts a Request or a plain URL
        attempts.append(url)
        raise ConnectionRefusedError(f"Tests must not access the network: {url}")

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    yield
    if attempts:
        pytest.fail("Test tried to access the network:\n  " + "\n  ".join(attempts), pytrace=False)