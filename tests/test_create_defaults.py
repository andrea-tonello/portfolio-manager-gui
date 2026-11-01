"""Tests for create_defaults: creating the files of a new account.

create_defaults(folder, broker) writes "report-<broker>.csv" containing only
the opening row (dated 01-01-2000, all totals at zero), and an empty journal,
"journal-<broker>.json". It must never touch a file that already exists,
because that file holds the user's transactions.
"""

import os

import pandas as pd

from services.account_service import create_defaults, journal_filename, ledger_filename
from services.journal_service import read_journal

BROKER = "Test Broker"
JOURNAL = '{"version": 1, "operations": [{"id": "a", "seq": 1, "date": "2024-01-02", "kind": "deposit", "amount": 1.0}]}'


def report_path(folder):
    """Path of the account CSV that create_defaults manages for BROKER inside `folder`."""
    return folder / ledger_filename(BROKER)


def journal_path(folder):
    """Path of the account journal that create_defaults manages for BROKER inside `folder`."""
    return folder / journal_filename(BROKER)


def test_creates_opening_row_and_an_empty_journal_in_an_empty_folder(tmp_path):
    """In an empty folder it writes a CSV with just the opening row, and a journal with no operations."""
    create_defaults(str(tmp_path), BROKER)

    df = pd.read_csv(report_path(tmp_path))
    assert len(df) == 1
    assert df.loc[0, "date"] == "01-01-2000"
    assert df.loc[0, "account"] == BROKER
    assert df.loc[0, "cash_held"] == 0
    assert read_journal(journal_path(tmp_path)) == []


def test_never_overwrites_an_existing_account_file(tmp_path):
    """An existing CSV is left byte-for-byte unchanged: it holds the user's transactions.

    Without a journal, it is an account from before the journal, and gets no
    empty one: loading would then rebuild the CSV from it, losing every
    operation. The migration gives it its journal instead.
    """
    existing = "date,account,operation\n01-01-2000,Test Broker,\n02-01-2024,Test Broker,Deposit\n"
    report_path(tmp_path).write_text(existing)

    create_defaults(str(tmp_path), BROKER)

    assert report_path(tmp_path).read_text() == existing
    assert not os.path.exists(journal_path(tmp_path))


def test_a_new_account_is_created_though_another_accounts_save_is_stuck(tmp_path):
    """Another account's file that can't be replaced yet (e.g. open in Excel on Windows) doesn't stop a new account.

    That save is left for later, as it is: the new account's files are written on their own.
    """
    (tmp_path / "pending-save.json").write_text('["report-Other.csv"]')
    (tmp_path / "report-Other.csv.tmp").write_text("the other account's ledger, not yet in place")

    create_defaults(str(tmp_path), BROKER)

    assert len(pd.read_csv(report_path(tmp_path))) == 1 and read_journal(journal_path(tmp_path)) == []
    assert (tmp_path / "report-Other.csv.tmp").exists() and (tmp_path / "pending-save.json").exists()


def test_a_journal_without_its_ledger_is_kept(tmp_path):
    """With a journal but no CSV (e.g. the CSV was lost), only the CSV is created: loading rebuilds it from the journal."""
    journal_path(tmp_path).write_text(JOURNAL)

    create_defaults(str(tmp_path), BROKER)

    assert journal_path(tmp_path).read_text() == JOURNAL
    assert len(pd.read_csv(report_path(tmp_path))) == 1
