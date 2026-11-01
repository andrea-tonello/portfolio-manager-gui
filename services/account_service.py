"""Each account's files in the user's resources folder: creating, loading, saving and deleting them.

An account has two files:
- report-<account>.csv, its ledger (domain/ledger.py);
- journal-<account>.json, its operations as entered (domain/journal.py and
  services/journal_service.py), from which the ledger is rebuilt. An
  account recorded before the journal existed has none until it is
  migrated: its ledger is then the only record.
A migrated account also keeps its ledger from before, as
before-journal-<account>.csv (see keep_before_journal).

Ledgers used to be saved as "Report <account>.csv", the name now kept for
the CSVs the user exports from Transactions (export_filename). prepare_files
renames them before the accounts are loaded.
"""

import json
import logging
import os
import shutil
import threading

import pandas as pd

from domain.account import Account
from domain.errors import ValidationError
from domain.journal import Operation, rebuild, rows_up_to_date
from domain.ledger import opening_ledger
from services.journal_service import journal_to_json, read_journal
from utils.columns import COLUMNS, INTERNAL_COLUMNS
from utils.constants import (
    BEFORE_JOURNAL_PREFIX, BEFORE_RECALCULATION_PREFIX, JOURNAL_PREFIX, LEDGER_PREFIX, REPORT_PREFIX,
)

logger = logging.getLogger(__name__)

# Written in the folder once a save has written all its files under temporary names, and
# deleted once they replace the old ones: it lists them, so a save interrupted in between is
# finished at the next load (see save_accounts).
_PENDING_SAVE = "pending-save.json"
_TEMPORARY = ".tmp"  # added to a file's name while it is being written

# Held by every save, and by finishing or cleaning up one, so a save made from a background
# thread (e.g. the migration) and one made from the screen never touch each other's files.
_save_lock = threading.RLock()


def ledger_filename(broker_name: str) -> str:
    """Return the file name of an account's ledger, e.g. "report-Fineco.csv" for the account "Fineco"."""
    return f"{LEDGER_PREFIX}{broker_name}.csv"


def ledger_path(folder: str, broker_name: str) -> str:
    """Return the path of an account's ledger inside `folder`, e.g. <folder>/report-Fineco.csv."""
    return os.path.join(folder, ledger_filename(broker_name))


def journal_filename(broker_name: str) -> str:
    """Return the file name of an account's journal, e.g. "journal-Fineco.json" for the account "Fineco"."""
    return f"{JOURNAL_PREFIX}{broker_name}.json"


def journal_path(folder: str, broker_name: str) -> str:
    """Return the path of an account's journal inside `folder`, e.g. <folder>/journal-Fineco.json."""
    return os.path.join(folder, journal_filename(broker_name))


def before_journal_path(folder: str, broker_name: str) -> str:
    """Return where an account's ledger from before the journal is kept, e.g. <folder>/before-journal-Fineco.csv.

    A copy kept for safety when the account moves to the journal (see
    keep_before_journal). Its name can't be any account's ledger, which
    always starts with "report-".
    """
    return os.path.join(folder, f"{BEFORE_JOURNAL_PREFIX}{broker_name}.csv")


def keep_before_journal(folder: str, broker_name: str) -> None:
    """Copy the account's ledger, as it is now, to its before-journal file (see before_journal_path).

    Called right before the ledger is replaced by the one rebuilt from the
    journal, which happens once: an earlier copy, from an attempt that
    saved nothing, may miss operations recorded since, so it is replaced.
    The copy is written under a temporary name first, so a stop halfway
    leaves no partial copy (finish_interrupted_save deletes the temporary file).
    """
    copy = before_journal_path(folder, broker_name)
    with _save_lock:
        shutil.copyfile(ledger_path(folder, broker_name), copy + _TEMPORARY)
        os.replace(copy + _TEMPORARY, copy)


def before_recalculation_path(folder: str, broker_name: str) -> str:
    """Return where an account's ledger from before its last recalculation is kept, e.g. <folder>/before-recalculation-Fineco.csv.

    A copy kept for safety, as the before-journal one: the values a
    recalculation of the history replaced (see keep_before_recalculation).
    """
    return os.path.join(folder, f"{BEFORE_RECALCULATION_PREFIX}{broker_name}.csv")


def keep_before_recalculation(folder: str, broker_name: str, ledger: pd.DataFrame) -> None:
    """Write `ledger`, the account's ledger a recalculation replaced, as its before-recalculation file.

    The ledger in memory, not the file: that may be older (e.g. a ledger
    rebuilt at load that couldn't be saved). It replaces the copy of an
    earlier recalculation, through a temporary file, so a stop halfway
    leaves no partial copy.
    """
    copy = before_recalculation_path(folder, broker_name)
    with _save_lock:
        _write_fully(copy + _TEMPORARY, ledger.to_csv(index=False))
        os.replace(copy + _TEMPORARY, copy)


def export_filename(broker_name: str) -> str:
    """Return the name offered for transactions exported as CSV, e.g. "Report Fineco.csv" or "Report All Accounts.csv".

    Ledgers were saved under this name before the journal (see prepare_files).
    """
    return f"{REPORT_PREFIX}{broker_name}.csv"


def prepare_files(folder: str, broker_names: list[str]) -> None:
    """Bring the files of a user's accounts up to date, before they are loaded.

    Finishes a save the app stopped in the middle of (see
    finish_interrupted_save; if a file still can't be replaced, it is
    logged and tried again later). Renames each ledger still saved as
    "Report <account>.csv", from before the journal, to report-<account>.csv,
    unless that exists. Then creates the ledger of an account that has none
    (create_defaults): after the renaming, or it would hide the user's
    operations. An account whose files can't be prepared is logged, and the
    others are still prepared.
    """
    try:
        finish_interrupted_save(folder)
    except OSError:
        logger.warning("Could not finish an interrupted save yet", exc_info=True)
    for name in broker_names:
        try:
            old, new = os.path.join(folder, export_filename(name)), ledger_path(folder, name)
            if os.path.isfile(old) and not os.path.exists(new):
                os.replace(old, new)
            create_defaults(folder, name)
        except OSError:
            logger.warning("Could not prepare the files of %s", name, exc_info=True)


def create_defaults(save_folder: str, broker_name: str) -> None:
    """Create the files of a new account `broker_name` in `save_folder`: a ledger of its opening row, an empty journal.

    Does nothing if the account already has a ledger: it holds the user's
    transactions (without a journal, the account is migrated at the next
    start). With a journal but no ledger, only the ledger is created, and
    loading the account rebuilds it from the journal: an empty journal
    there would lose every operation.

    Each file is written in full, then put in place, without finishing any
    earlier save first (as save_accounts does): a file of another account
    that can't be replaced yet mustn't stop a new account. A stop between
    the two files is harmless: next time the missing one is created.
    """
    files = {ledger_path(save_folder, broker_name): opening_ledger(broker_name).to_csv(index=False)}
    if os.path.isfile(next(iter(files))):
        return
    if not os.path.isfile(journal_path(save_folder, broker_name)):
        files[journal_path(save_folder, broker_name)] = journal_to_json([])
    with _save_lock:
        for path, text in files.items():
            _write_fully(path + _TEMPORARY, text)
            os.replace(path + _TEMPORARY, path)


def _read_ledger(path: str) -> pd.DataFrame:
    """Read the ledger CSV at `path`, with every column of COLUMNS and the internal ones, in that order.

    A file written before a column was added (e.g. pending_fees, or op_id
    before the journal) gets it, empty, in its place.
    """
    ledger = pd.read_csv(path, dtype={col: "str" for col in INTERNAL_COLUMNS})
    return ledger.reindex(columns=[*COLUMNS, *INTERNAL_COLUMNS])


def _matches(ledger: pd.DataFrame | None, journal: list[Operation]) -> bool:
    """Return True when `ledger` holds one row per operation of `journal`, each built by it as it is now.

    Not so when the ledger is missing, or was saved from an older journal
    (e.g. its file was replaced while the app was closed).
    """
    return ledger is not None and len(ledger) - 1 == len(journal) == rows_up_to_date(ledger, journal)


def load_single_account(brokers: dict, save_folder: str, account_idx: int) -> Account:
    """Load the account `brokers[account_idx]` from its files in `save_folder` (see prepare_files, called first).

    An account whose ledger doesn't match its journal gets it rebuilt and
    saved. If rebuilding fails (e.g. no prices offline), the ledger on file
    is used: the next operation recorded rebuilds every row that doesn't
    match, and the next load tries again. If only saving fails, the rebuilt
    ledger is used. Raises FileNotFoundError when there is no ledger to use,
    and ValueError when the journal can't be read (e.g. written by a newer
    version): the account can't be shown, and mustn't be changed without it.
    """
    name = brokers[account_idx]
    path, journal_file = ledger_path(save_folder, name), journal_path(save_folder, name)
    ledger = _read_ledger(path) if os.path.isfile(path) else None
    journal = read_journal(journal_file) if os.path.isfile(journal_file) else None
    if journal is not None and not _matches(ledger, journal):
        try:
            ledger = rebuild(name, journal)
        except (LookupError, ValidationError):
            logger.warning("Could not rebuild the ledger of %s from its journal", name, exc_info=True)
        else:
            try:
                save_accounts(save_folder, {name: (None, ledger)})
            except OSError:
                logger.warning("Could not save the rebuilt ledger of %s", name, exc_info=True)
    if ledger is None:
        raise FileNotFoundError(path)
    return Account(idx=account_idx, name=name, path=path, df=ledger, journal=journal)


def _write_fully(path: str, text: str) -> None:
    """Write `text` to `path`, forced to disk before returning: renaming the file afterwards can't leave it half written."""
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())


def save_accounts(folder: str, changes: dict[str, tuple[list[Operation] | None, pd.DataFrame]]) -> None:
    """Save the journal and ledger of each account named in `changes`, inside `folder`: all of them, or none.

    1. Every file is written in full under a temporary name (<file>.tmp).
       If one can't be, the temporary files are deleted and the error
       raised: nothing has changed.
    2. A marker file listing them is written. From then on the save is
       decided: even if the app stops, they replace the old files at the
       next load (finish_interrupted_save). So a transfer is never saved in
       one account and not in the other.
    3. Each replaces its old file. One that can't (e.g. on Windows, a ledger
       open in another program) is left listed in the marker, logged, and
       tried again before the next save or load.

    A journal of None (an account not migrated yet) leaves the account's
    journal file alone. Raises before writing anything if an earlier save
    still can't be finished.

    Example: save_accounts(folder, {"Fineco": (journal, ledger)}) replaces
    journal-Fineco.json and report-Fineco.csv.
    """
    files = {}  # final path -> text, all made before any file is written
    for name, (journal, ledger) in changes.items():
        if journal is not None:
            files[journal_path(folder, name)] = journal_to_json(journal)
        files[ledger_path(folder, name)] = ledger.to_csv(index=False)
    marker = os.path.join(folder, _PENDING_SAVE)
    with _save_lock:
        finish_interrupted_save(folder)
        try:
            for path, text in files.items():
                _write_fully(path + _TEMPORARY, text)
            _write_fully(marker + _TEMPORARY, json.dumps([os.path.basename(path) for path in files]))
            os.replace(marker + _TEMPORARY, marker)
        except BaseException:
            for path in [*files, marker]:
                if os.path.exists(path + _TEMPORARY):
                    os.remove(path + _TEMPORARY)
            raise
        try:
            _finish_save(folder)
        except OSError:
            logger.warning("A saved file couldn't replace the old one yet; it will be tried again", exc_info=True)


def _finish_save(folder: str) -> None:
    """Replace each file listed in the marker by its temporary version, then delete the marker.

    Files that can't be replaced stay listed in the marker, and OSError is
    raised naming them. A file already replaced (no temporary version left)
    is skipped, so finishing twice is harmless.
    """
    marker = os.path.join(folder, _PENDING_SAVE)
    with open(marker, encoding="utf-8") as f:
        names = json.load(f)
    stuck = []
    for name in names:
        path = os.path.join(folder, name)
        if os.path.exists(path + _TEMPORARY):
            try:
                os.replace(path + _TEMPORARY, path)
            except OSError:
                stuck.append(name)
    if stuck:
        _write_fully(marker + _TEMPORARY, json.dumps(stuck))
        os.replace(marker + _TEMPORARY, marker)
        raise OSError(f"could not replace {', '.join(stuck)}")
    os.remove(marker)


def finish_interrupted_save(folder: str) -> None:
    """Finish a save the app stopped in the middle of, and delete the leftovers of one stopped before.

    A save listed in the marker file was decided: its files replace the old
    ones now. Any other temporary file belongs to a save stopped before
    that point, which changed nothing: it is deleted. Raises OSError when a
    file still can't be replaced.
    """
    with _save_lock:  # no save is writing its temporary files meanwhile
        if os.path.exists(os.path.join(folder, _PENDING_SAVE)):
            _finish_save(folder)
        for name in os.listdir(folder):
            if name.endswith(_TEMPORARY):
                os.remove(os.path.join(folder, name))


def delete_account_files(broker_name: str, save_folder: str):
    """Delete the files of the account `broker_name`: its ledger, its journal, and the copies of its earlier ledgers.

    Those are the ledger from before the journal and the one from before its last recalculation.
    """
    with _save_lock:
        for path in (ledger_path(save_folder, broker_name), journal_path(save_folder, broker_name),
                     before_journal_path(save_folder, broker_name), before_recalculation_path(save_folder, broker_name)):
            if os.path.exists(path):
                os.remove(path)
