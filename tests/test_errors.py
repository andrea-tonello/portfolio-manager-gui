"""Tests for how error messages reach the user (REFACTORING.md, D1).

Domain and service code never translates anything. When something is wrong it
raises a ValidationError that carries a locale key (a path into
assets/i18n/<language>.json, e.g. "operations.split.ratio_error") and the values to
fill into that message. The screens turn it into text in the user's current
language with components.snack.error_message.
"""

import ast
import asyncio
import io
import json
import zipfile
from datetime import date
from pathlib import Path

import flet as ft
import pandas as pd
import pytest
from test_ledger_snapshots import NAMES, _replay, buy, deposit, sell, split

from components.snack import error_message
from domain.errors import TickerNotFound, ValidationError
from services import analysis_service, config_service, market_data
from utils.constants import I18N_DIR
from domain.account import Account
from domain.ledger import get_pf_date
from utils.translator import Translator
from views.settings_view import SettingsView

ROOT = Path(__file__).resolve().parent.parent
LANGUAGES = ["en", "it"]


def _translator(language):
    """A real Translator for `language` ("en" or "it"), loaded from the project's assets/i18n/ folder."""
    return Translator(language_code=language, locales_dir=I18N_DIR)


# ── Every key written in the code exists in every language ──────────

def _locale_keys_used_in_code():
    """Return (file, line, key) for every locale key written literally in the app's code.

    It reads the source files (without running them) and collects the first
    argument of translator lookups such as t.get("home.overview") or
    state.translator.get("..."), and of ValidationError("...").
    Keys built at run time (e.g. t.get(locale_key)) can't be checked this way.
    """
    found = []
    for path in sorted(ROOT.rglob("*.py")):
        relative = path.relative_to(ROOT)
        if relative.parts[0] in ("tests", "build") or relative.parts[0].startswith("."):
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not (isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)):
                continue
            func = node.func
            is_translation = (
                isinstance(func, ast.Attribute) and func.attr == "get"
                and ((isinstance(func.value, ast.Name) and func.value.id in ("t", "translator"))
                     or (isinstance(func.value, ast.Attribute) and func.value.attr == "translator"))
            )
            is_error = isinstance(func, ast.Name) and func.id == "ValidationError"
            if is_translation or is_error:
                found.append((str(relative), node.lineno, node.args[0].value))
    return found


def _has_message(strings, key):
    """True if `key` (dotted path, e.g. "misc_errors.nodates") leads to a message in `strings`."""
    value = strings
    for part in key.split("."):
        if not isinstance(value, dict) or part not in value:
            return False
        value = value[part]
    return isinstance(value, str)


@pytest.mark.parametrize("language", LANGUAGES)
def test_every_locale_key_written_in_the_code_exists(language):
    """A key missing from a locale file shows up in the app as "<the.key>" instead of a message.

    Before D1, get_pf_date used "dates.error_nodates", which exists in neither
    file (the message lives at "misc_errors.nodates").
    """
    strings = json.loads((Path(I18N_DIR) / f"{language}.json").read_text(encoding="utf-8"))
    keys = _locale_keys_used_in_code()
    assert keys, "the scan should find the app's locale keys"

    missing = [f"{file}:{line} {key}" for file, line, key in keys if not _has_message(strings, key)]

    assert missing == []


# ── Turning an error into text ────────────────────────────────────────

def test_error_message_uses_the_language_active_when_it_is_shown():
    """The same error object reads in English or Italian, depending on the translator used to show it."""
    ex = ValidationError("operations.stock.sell_noqt", quantity=5, last_remaining_qt=3)

    assert error_message(_translator("en"), ex) == "Quantity sold (5) exceeds available quantity (3)"
    assert error_message(_translator("it"), ex) == "Quantità venduta (5) superiore a quella disponibile (3)"


def test_error_message_shows_other_errors_as_they_are(translator):
    """Errors without a locale key (network failures, bugs) are shown with their own text."""
    assert error_message(translator, RuntimeError("No exchange rate data available")) == \
        "No exchange rate data available"


def test_ticker_not_found_is_a_validation_error_naming_the_ticker(translator):
    """TickerNotFound is a ValidationError, so screens catch and translate it like any other."""
    ex = TickerNotFound("XYZ.MI")

    assert isinstance(ex, ValidationError)
    assert error_message(translator, ex) == 'Ticker not recognized: "XYZ.MI"'


# ── Domain code raises keys, not translated text ──────────────────────

DAY = date(2024, 3, 1)


@pytest.mark.parametrize("steps, key, params", [
    pytest.param([deposit(DAY, 1000), sell(DAY, "AAA.MI", 5, 100.0, 0.0)],
                 "operations.stock.sell_noitems", {}, id="sell-nothing-held"),
    pytest.param([deposit(DAY, 5000), buy(DAY, "AAA.MI", 10, 100.0, 0.0), sell(DAY, "AAA.MI", 20, 100.0, 0.0)],
                 "operations.stock.sell_noqt", {"quantity": 20, "last_remaining_qt": 10}, id="sell-more-than-held"),
    pytest.param([deposit(DAY, 1000), split(DAY, "AAA.MI", 2.0)],
                 "operations.split.ticker_notheld", {"ticker": "AAA.MI"}, id="split-never-held"),
    pytest.param([deposit(DAY, 5000), buy(DAY, "AAA.MI", 10, 100.0, 0.0), sell(DAY, "AAA.MI", 10, 100.0, 0.0),
                  split(DAY, "AAA.MI", 2.0)],
                 "operations.split.ticker_notheld", {"ticker": "AAA.MI"}, id="split-after-selling-all"),
])
def test_rejected_operations_raise_a_key_and_its_values(steps, key, params, tmp_path, fake_market):
    """Operations the ledger can't accept raise a ValidationError with the message key and the values to show."""
    with pytest.raises(ValidationError) as info:
        _replay(steps, tmp_path)

    assert (info.value.key, info.value.params) == (key, params)


def test_valuing_before_the_first_row_raises_a_key():
    """Asking for the portfolio on a date before the account's first row is reported with a locale key."""
    account = Account(1, "Main", "", pd.DataFrame({"date": ["01-01-2000"], "cash_held": [0.0]}))

    with pytest.raises(ValidationError) as info:
        get_pf_date(account, "31-12-1999", date(1999, 12, 31))

    assert (info.value.key, info.value.params) == ("misc_errors.nodates", {"dt": "31-12-1999"})


@pytest.fixture
def yahoo_names(monkeypatch):
    """Make Yahoo's chart endpoint know only the tickers in NAMES (test_ledger_snapshots), returning their names.

    For any other ticker it fails the way Yahoo does for an unknown symbol.
    """
    def fake_fetch_chart(ticker, **kwargs):
        """Return chart metadata with the long name, or fail like Yahoo for unknown tickers."""
        if ticker not in NAMES:
            raise RuntimeError("There is no data for this ticker")
        return {"meta": {"longName": NAMES[ticker]}}

    monkeypatch.setattr(market_data, "_fetch_chart", fake_fetch_chart)


def test_fetch_ticker_name_returns_the_name_of_a_known_ticker(yahoo_names):
    """A ticker Yahoo knows gives back its long name."""
    assert market_data.fetch_ticker_name("AAA.MI") == "Alpha SpA"


def test_fetch_ticker_name_raises_ticker_not_found(yahoo_names):
    """A ticker Yahoo doesn't know raises TickerNotFound, which carries the ticker for the message."""
    with pytest.raises(TickerNotFound) as info:
        market_data.fetch_ticker_name("NOPE.MI")

    assert info.value.params == {"ticker": "NOPE.MI"}


@pytest.mark.parametrize("missing_ticker, key", [
    ("AAA.MI", "operations.stock.ticker_nodata"),     # known ticker, no prices in the period
    ("NOPE.MI", "operations.stock.ticker_notfound"),  # Yahoo doesn't know the ticker
])
def test_rolling_correlation_explains_why_a_ticker_has_no_prices(missing_ticker, key, yahoo_names, monkeypatch):
    """When one of the two tickers has no prices, the error says whether it is unknown or just has no data."""
    other = "BBB.MI"
    prices = pd.DataFrame({other: [10.0, 10.5, 11.0]}, index=pd.bdate_range("2024-01-01", periods=3))
    monkeypatch.setattr(analysis_service, "download_close", lambda tickers, **kwargs: (prices, {}))

    with pytest.raises(ValidationError) as info:
        analysis_service.compute_correlation([], "2024-01-01", "2024-01-31", missing_ticker, other, 2)

    assert (info.value.key, info.value.params) == (key, {"ticker": missing_ticker})


# ── Backup validation ────────────────────────────────────────────────

HEADER = "date,account,operation,product,ticker\n"


def _zip(files):
    """Build a ZIP archive in memory from {path inside the archive: text or bytes} and return its bytes."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buffer.getvalue()


# A valid backup: config.ini lists the users, each with a config.ini and a CSV per account.
MULTI_USER = {
    "config.ini": "[Users]\n1 = Tester\n",
    "users/Tester/config.ini": "[Brokers]\n1 = Main\n",
    "users/Tester/resources/Report Main.csv": HEADER,
}


def _without(files, name):
    """Return a copy of `files` with the archive entry `name` removed."""
    return {k: v for k, v in files.items() if k != name}


def test_valid_backup_passes():
    """A backup in the current format is accepted without raising."""
    config_service.validate_backup(_zip(MULTI_USER))


USER_CONFIG = "users/Tester/config.ini"
USER_CSV = "users/Tester/resources/Report Main.csv"

BROKEN_BACKUPS = {
    "not-a-zip": (b"not a zip", "settings.account.import_error", {}),
    "no-config": (_zip({"notes.txt": "hello"}), "settings.backup.missing_config", {}),
    "config-not-ini": (_zip({**MULTI_USER, "config.ini": "no sections here"}),
                       "settings.backup.invalid_config", {}),
    "no-users": (_zip({**MULTI_USER, "config.ini": "[Theme]\nmode = dark\n"}),
                 "settings.backup.no_users", {}),
    # The single-user format from before users existed is no longer supported.
    "old-single-user-format": (_zip({"config.ini": "[Brokers]\n1 = Main\n", "resources/Report Main.csv": HEADER}),
                               "settings.backup.no_users", {}),
    "user-config-missing": (_zip(_without(MULTI_USER, USER_CONFIG)),
                            "settings.backup.missing_user_config", {"username": "Tester"}),
    "user-config-not-ini": (_zip({**MULTI_USER, USER_CONFIG: "no sections here"}),
                            "settings.backup.invalid_user_config", {"username": "Tester"}),
    "user-without-accounts": (_zip({**MULTI_USER, USER_CONFIG: "[Brokers]\n"}),
                              "settings.backup.user_no_accounts", {"username": "Tester"}),
    "user-csv-missing": (_zip(_without(MULTI_USER, USER_CSV)),
                         "settings.backup.missing_user_csv", {"account": "Main", "username": "Tester"}),
    "csv-header-unreadable": (_zip({**MULTI_USER, USER_CSV: b"\xff\xfe\x00"}),
                              "settings.backup.unreadable_header", {"file": USER_CSV}),
    "csv-columns-missing": (_zip({**MULTI_USER, USER_CSV: "date,account\n"}),
                            "settings.backup.missing_columns", {"file": USER_CSV, "columns": "operation, product"}),
}


@pytest.mark.parametrize("case", BROKEN_BACKUPS)
def test_broken_backups_raise_a_translatable_error(case):
    """Each problem in a backup raises a ValidationError whose message exists in every language.

    Before D1 only "not a zip" was translated; every other message was
    English-only text (REFACTORING.md, Appendix A item 5).
    """
    zip_bytes, key, params = BROKEN_BACKUPS[case]

    with pytest.raises(ValidationError) as info:
        config_service.validate_backup(zip_bytes)

    assert (info.value.key, info.value.params) == (key, params)
    for language in LANGUAGES:
        text = error_message(_translator(language), info.value)
        assert not text.startswith("<"), f"{language}: message missing or a placeholder is wrong: {text}"


@pytest.mark.parametrize("files", [{"notes.txt": "hello"}, MULTI_USER], ids=["invalid", "valid"])
def test_the_backup_archive_is_closed_after_checking(monkeypatch, files):
    """validate_backup closes the archive it opened, whether the backup is rejected or accepted.

    It used to stay open whenever a problem was found.
    """
    zip_bytes = _zip(files)
    opened = []

    class TrackedZipFile(zipfile.ZipFile):
        """A ZipFile that remembers each archive opened, to check later that it was closed."""

        def __init__(self, *args, **kwargs):
            """Open the archive as usual and remember it."""
            super().__init__(*args, **kwargs)
            opened.append(self)

    monkeypatch.setattr(config_service.zipfile, "ZipFile", TrackedZipFile)

    try:
        config_service.validate_backup(zip_bytes)
    except ValidationError:
        pass

    assert len(opened) == 1
    assert opened[0].fp is None, "the archive is still open"


class FakeImportPicker:
    """Stand-in for ft.FilePicker whose pick_files "chooses" a file holding `data`."""

    def __init__(self, data):
        """Remember the bytes the chosen file will contain."""
        self.data = data

    async def pick_files(self, **kwargs):
        """Return one picked file with its contents, as Flet does with with_data=True."""
        return [ft.FilePickerFile(id=0, name="backup.zip", size=len(self.data), bytes=self.data)]


def test_backup_import_error_is_shown_in_the_users_language(page, state):
    """Importing a broken backup shows the problem in the app's current language (here Italian)."""
    state.translator.load_language("it")
    view = SettingsView(page, state)
    view.build()
    view.file_picker = FakeImportPicker(_zip({"notes.txt": "hello"}))

    asyncio.run(view._on_import_backup(None))

    snacks = [c for c in page.overlay if isinstance(c, ft.SnackBar)]
    assert [s.content.value for s in snacks] == ["File config.ini mancante nel backup."]
    assert page.dialogs == [], "no import confirmation should be offered for a broken backup"
