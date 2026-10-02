"""Tests for create_defaults: creating a new, empty account CSV.

create_defaults(folder, broker) writes "Report <broker>.csv" containing only
the opening row (dated 01-01-2000, all totals at zero). It must never touch a
file that already exists, because that file holds the user's transactions.
"""

import os

import pandas as pd

from services import account_service
from services.account_service import create_defaults
from utils.constants import REPORT_PREFIX

BROKER = "Test Broker"


def report_path(folder):
    """Path of the account CSV that create_defaults manages for BROKER inside `folder`."""
    return folder / f"{REPORT_PREFIX}{BROKER}.csv"


def test_creates_opening_row_in_an_empty_folder(tmp_path):
    """In an empty folder it writes a CSV with just the opening row."""
    create_defaults(str(tmp_path), BROKER)

    df = pd.read_csv(report_path(tmp_path))
    assert len(df) == 1
    assert df.loc[0, "date"] == "01-01-2000"
    assert df.loc[0, "account"] == BROKER
    assert df.loc[0, "cash_held"] == 0


def test_creates_the_file_when_other_accounts_already_exist(tmp_path):
    """Other brokers' files in the same folder don't stop it from creating this one."""
    (tmp_path / f"{REPORT_PREFIX}Other Broker.csv").write_text("date\n01-01-2000\n")

    create_defaults(str(tmp_path), BROKER)

    assert report_path(tmp_path).is_file()


def test_never_overwrites_an_existing_account_file(tmp_path):
    """An existing CSV is left byte-for-byte unchanged: it holds the user's transactions."""
    existing = "date,account,operation\n01-01-2000,Test Broker,\n02-01-2024,Test Broker,Deposit\n"
    report_path(tmp_path).write_text(existing)

    create_defaults(str(tmp_path), BROKER)

    assert report_path(tmp_path).read_text() == existing


def test_account_files_are_named_after_the_account():
    """Each account's CSV is "Report <account name>.csv"; report_path puts it inside a folder."""
    assert account_service.report_filename("Fineco") == "Report Fineco.csv"
    assert account_service.report_path("resources", "Fineco") == os.path.join("resources", "Report Fineco.csv")
