"""Tests for each account's files (services/account_service.py): saving them together and loading them back.

An account has its ledger, report-<account>.csv, and its journal,
journal-<account>.json. A save writes all its files or none, and one
interrupted is finished at the next load. Loading rebuilds a ledger that
doesn't match its journal, and the files are first brought up to date
(prepare_files), e.g. renaming a ledger saved before the journal.
"""

import json
import os
from datetime import date

import pandas as pd
import pytest
from test_journal import journal_of
from test_ledger_snapshots import STOCKS_EUR, _replay, deposit

from domain.journal import Kind, Operation, rebuild
from services import account_service, journal_service
from services.account_service import journal_path, ledger_path, load_single_account, prepare_files, save_accounts

BROKER = "Test Broker"
BROKERS = {1: BROKER}


@pytest.fixture
def saved(tmp_path, fake_market):
    """Save the STOCKS_EUR account's journal and ledger in `tmp_path` as the app does; return (folder, journal, ledger)."""
    journal = journal_of(STOCKS_EUR)
    ledger = rebuild(BROKER, journal)
    save_accounts(str(tmp_path), {BROKER: (journal, ledger)})
    return str(tmp_path), journal, ledger


def contents(folder):
    """Return {file name: text} of every file in `folder`, to tell whether any changed."""
    files = {}
    for name in os.listdir(folder):
        with open(os.path.join(folder, name), encoding="utf-8") as f:
            files[name] = f.read()
    return files


def no_rebuild(monkeypatch):
    """Make any rebuild while loading fail the test: the ledger on file must be used as it is."""
    monkeypatch.setattr(account_service, "rebuild", lambda *args, **kwargs: pytest.fail("rebuilt a matching ledger"))


def test_an_account_saved_with_its_journal_loads_back_as_it_was(saved, monkeypatch):
    """The journal and ledger saved together load back as they were, without rebuilding the ledger.

    No temporary file is left behind, and each row still names the operation that built it.
    """
    folder, journal, ledger = saved
    no_rebuild(monkeypatch)

    account = load_single_account(BROKERS, folder, 1)

    assert sorted(os.listdir(folder)) == ["journal-Test Broker.json", "report-Test Broker.csv"]
    assert account.journal == journal
    assert list(account.df["op_id"].iloc[1:]) == [op.id for op in journal]
    assert account.df["cash_held"].tolist() == ledger["cash_held"].tolist()


def _remove_ledger(folder, journal, ledger):
    """Delete the account's ledger file, as if it had been lost."""
    os.remove(ledger_path(folder, BROKER))


def _lose_last_row(folder, journal, ledger):
    """Save the ledger without its last row: the journal holds an operation the ledger doesn't."""
    ledger.iloc[:-1].to_csv(ledger_path(folder, BROKER), index=False)


def _edit_journal(folder, journal, ledger):
    """Replace the journal by one whose last withdrawal is 400 instead of 500.

    Every row still names an operation of the journal: only their
    fingerprints tell that the last one changed after its row was built.
    """
    edited = [*journal[:-1], Operation(**{**vars(journal[-1]), "amount": 400.0})]
    with open(journal_path(folder, BROKER), "w", encoding="utf-8") as f:
        f.write(journal_service.journal_to_json(edited))


@pytest.mark.parametrize("damage", [_remove_ledger, _lose_last_row, _edit_journal],
                         ids=["missing", "other-operations", "older-journal"])
def test_a_ledger_that_doesnt_match_its_journal_is_rebuilt_and_saved_at_load(saved, damage, monkeypatch):
    """A ledger missing, or not built from the journal's operations as they are, is rebuilt from the journal.

    The rebuilt ledger is used and saved over the old one, so the next load
    uses it as it is.
    """
    folder, journal, ledger = saved
    damage(folder, journal, ledger)
    expected = rebuild(BROKER, journal_service.read_journal(journal_path(folder, BROKER)))

    account = load_single_account(BROKERS, folder, 1)
    no_rebuild(monkeypatch)
    reloaded = load_single_account(BROKERS, folder, 1)

    assert account.df["cash_held"].tolist() == expected["cash_held"].tolist()
    assert reloaded.df["cash_held"].tolist() == expected["cash_held"].tolist()


@pytest.fixture
def two_accounts(tmp_path, fake_market):
    """Fineco (1,000 EUR deposited) and Directa (100), each with its journal, saved in `tmp_path`; return them by number."""
    folder = str(tmp_path)
    accounts = {}
    for idx, (name, amount) in enumerate([("Fineco", 1000), ("Directa", 100)], start=1):
        journal = journal_of([deposit(date(2024, 1, 2), amount)])
        save_accounts(folder, {name: (journal, rebuild(name, journal))})
        accounts[idx] = load_single_account({idx: name}, folder, idx)
    return folder, accounts


def _transfer(accounts):
    """Return the changes of Fineco sending 300 to Directa on 10-01-2024, by account name, as save_accounts takes them."""
    changes = journal_service.record(accounts, accounts[1], Kind.TRANSFER_OUT, date(2024, 1, 10),
                                     amount=300.0, counterpart="Directa")
    return {accounts[idx].name: change for idx, change in changes.items()}


def test_a_save_stopped_after_writing_its_files_is_finished_at_the_next_load(two_accounts, monkeypatch):
    """A transfer whose files were all written, but not yet renamed when the app stopped, is in both accounts after.

    Renaming the files one by one, a stop in between would leave the
    transfer in one account only: the save is finished instead.
    """
    folder, accounts = two_accounts
    monkeypatch.setattr(account_service, "_finish_save", lambda folder: None)  # the app stops here
    save_accounts(folder, _transfer(accounts))
    monkeypatch.undo()

    prepare_files(folder, ["Fineco", "Directa"])
    loaded = [load_single_account({1: "Fineco", 2: "Directa"}, folder, idx) for idx in (1, 2)]

    assert [account.last("cash_held") for account in loaded] == [700, 400]
    assert sorted(os.listdir(folder)) == ["journal-Directa.json", "journal-Fineco.json",
                                          "report-Directa.csv", "report-Fineco.csv"]


def test_a_save_that_fails_while_writing_changes_nothing(two_accounts, monkeypatch):
    """When a file can't be written (e.g. the disk is full), no file changes and no temporary file is left.

    Here the third of the transfer's four files fails, half written.
    """
    folder, accounts = two_accounts
    before = contents(folder)
    write_fully, written = account_service._write_fully, []

    def full_disk(path, text):
        """Write the first two files; fail on the third after writing half of it."""
        written.append(path)
        write_fully(path, text if len(written) < 3 else text[:len(text) // 2])
        if len(written) == 3:
            raise OSError("No space left on device")

    monkeypatch.setattr(account_service, "_write_fully", full_disk)

    with pytest.raises(OSError):
        save_accounts(folder, _transfer(accounts))

    assert contents(folder) == before


def test_a_file_that_cant_replace_its_old_one_yet_is_replaced_before_the_next_save(two_accounts, monkeypatch):
    """A ledger held open by another program (Windows) can't be replaced: the save is kept and finished later.

    The save counts as done, so the accounts in memory take it. Its stuck
    file replaces the old one as soon as it can, before anything else is saved.
    """
    folder, accounts = two_accounts
    replace = os.replace

    def locked(source, target):
        """Refuse to replace Fineco's ledger, as Windows does for a file open in Excel."""
        if target.endswith("report-Fineco.csv"):
            raise PermissionError("The file is being used by another process")
        replace(source, target)

    monkeypatch.setattr(account_service.os, "replace", locked)
    save_accounts(folder, _transfer(accounts))
    monkeypatch.undo()

    assert json.loads(contents(folder)["pending-save.json"]) == ["report-Fineco.csv"]
    save_accounts(folder, {})
    assert "pending-save.json" not in os.listdir(folder)
    assert pd.read_csv(ledger_path(folder, "Fineco"))["cash_held"].tolist() == [0, 1000, 700]


def test_a_ledger_under_its_old_name_is_renamed_before_an_empty_one_is_created(tmp_path, fake_market):
    """Before loading, an account's "Report <account>.csv" from before the journal becomes its report-<account>.csv.

    Missing ledgers are created at the same time: the old file must be
    found first, not hidden by an empty ledger created next to it.
    """
    folder = tmp_path / "resources"
    folder.mkdir()
    old = _replay(STOCKS_EUR, tmp_path / "old")
    old.to_csv(folder / "Report Test Broker.csv", index=False)

    prepare_files(str(folder), [BROKER])
    account = load_single_account(BROKERS, str(folder), 1)

    assert os.listdir(folder) == ["report-Test Broker.csv"]
    assert account.df["cash_held"].tolist() == old["cash_held"].tolist()
    assert account.journal is None


def test_an_account_whose_journal_cant_be_read_is_left_out_untouched(state):
    """A journal this version can't read (e.g. from a newer one) leaves its account out, with its files as they were.

    Loaded from its ledger alone, the account could be changed without its
    journal, and those changes lost once the journal is read again.
    """
    folder = state.config_res_folder
    with open(journal_path(folder, BROKER), "w", encoding="utf-8") as f:
        f.write('{"version": 2, "operations": []}')
    before = contents(folder)

    state.load_all_accounts()

    assert 1 not in state.accounts
    assert contents(folder) == before
