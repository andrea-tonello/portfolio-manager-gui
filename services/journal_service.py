"""The operations journal's file format, and recording, deleting or editing an operation through it.

Each account's journal (domain/journal.py) is saved as journal-<account>.json:
{"version": 1, "operations": [...]}, each operation as operation_to_dict
gives it. record, delete and edit return the new journal and the rebuilt
ledger of every account they change, without saving anything: the caller
passes them to AppState.commit_changes, which saves both files.
"""

import json
from dataclasses import replace
from datetime import date

import pandas as pd

from domain.account import Account
from domain.journal import (
    Kind, Operation, OperationRefused, new_id, operation_from_dict, operation_to_dict, rebuild, rows_up_to_date,
)

# The version written in every journal file; a file with another one can't be read.
JOURNAL_VERSION = 1

# What record, delete and edit return: {account number: (its new journal, its rebuilt ledger)}.
Changes = dict[int, tuple[list[Operation], pd.DataFrame]]

# Fields an edit can't change: what identifies the operation, and which accounts a transfer joins.
_FIXED_FIELDS = {"id", "seq", "kind", "counterpart", "transfer_id"}


def journal_to_json(operations: list[Operation]) -> str:
    """Return the text of a journal file holding `operations`, in order of entry.

    Example: '{"version": 1, "operations": [{"id": "3f2a...", "seq": 1, "date": "2024-01-02", ...}]}', indented.
    """
    ordered = sorted(operations, key=lambda op: op.seq)
    return json.dumps({"version": JOURNAL_VERSION, "operations": [operation_to_dict(op) for op in ordered]},
                      indent=2, ensure_ascii=False)


def journal_from_json(text: str) -> list[Operation]:
    """Return the operations of a journal file's `text`.

    Raises ValueError when it isn't a journal this version can read: not
    JSON, another version, an invalid operation, or two with the same id
    (each row of the ledger names its operation by id).
    """
    try:
        stored = json.loads(text)
        if stored.get("version") != JOURNAL_VERSION:
            raise ValueError(f"unsupported journal version {stored.get('version')!r}")
        operations = [operation_from_dict(op) for op in stored["operations"]]
    except (TypeError, KeyError, AttributeError) as ex:
        raise ValueError(f"not a journal: {ex!r}") from ex
    if len({op.id for op in operations}) != len(operations):
        raise ValueError("two operations of the journal have the same id")
    return operations


def read_journal(path: str) -> list[Operation]:
    """Return the operations of the journal file at `path`. Raises ValueError when it can't be read (see journal_from_json)."""
    with open(path, encoding="utf-8") as f:
        return journal_from_json(f.read())


def record(accounts: dict[int, Account], account: Account, kind: Kind, day: date, **fields) -> Changes:
    """Return the changes made by recording a new operation of `kind` on `day` in `account`, with its `fields`.

    The operation gets a new id and the next order of entry, so on a day
    that already has operations it goes after them. A transfer out (fields
    amount and counterpart) also records its other half, a transfer in, in
    the account named `counterpart`, both sharing a new transfer_id. Each
    changed ledger is rebuilt from the new operation's position on.
    `accounts` are all the loaded accounts, by number.

    Raises ValidationError when the operation can't be recorded (e.g. selling
    more than is held), or OperationRefused when it would make a later one
    impossible, naming that one. `account`'s ledger is rebuilt first: for a
    transfer, the sender is the one that can be short of cash.

    Example: record(accounts, fineco, Kind.TRANSFER_OUT, date(2024, 6, 4), amount=500.0, counterpart="Directa")
    -> {fineco.idx: (journal, ledger), directa.idx: (journal, ledger)}.
    """
    if kind == Kind.TRANSFER_IN:
        raise ValueError("a transfer is recorded from the account sending it, as a transfer out")
    if kind == Kind.TRANSFER_OUT:
        fields["transfer_id"] = new_id()
    added = {account.idx: Operation(id=new_id(), seq=_next_seq(account), date=day, kind=kind, **fields)}
    if kind == Kind.TRANSFER_OUT:
        other = _account_named(accounts, fields["counterpart"], besides=account)
        added[other.idx] = Operation(id=new_id(), seq=_next_seq(other), date=day, kind=Kind.TRANSFER_IN,
                                     amount=fields["amount"], counterpart=account.name,
                                     transfer_id=fields["transfer_id"])
    journals = {idx: [*_journal_of(accounts[idx]), op] for idx, op in added.items()}
    return _rebuilt(accounts, journals, changed={op.id for op in added.values()})


def delete(accounts: dict[int, Account], account: Account, op_id: str) -> Changes:
    """Return the changes made by deleting the operation `op_id` from `account`.

    A transfer is deleted from both accounts: its other half is the
    operation with the same transfer_id in another account, if that account
    still exists. Each changed ledger is rebuilt from the deleted
    operation's position on. Raises OperationRefused when a later operation
    becomes impossible, e.g. a sale of shares whose buy is deleted.
    """
    deleted = _find(account, op_id)
    journals = {account.idx: [op for op in _journal_of(account) if op.id != op_id]}
    half = _other_half(accounts, account, deleted)
    if half is not None:
        other, other_op = half
        journals[other.idx] = [op for op in _journal_of(other) if op.id != other_op.id]
    return _rebuilt(accounts, journals)


def edit(accounts: dict[int, Account], account: Account, op_id: str, **new_fields) -> Changes:
    """Return the changes made by giving the operation `op_id` of `account` the values `new_fields`.

    The operation keeps its id and order of entry. A transfer's other half
    gets the same new date and amount. Each changed ledger is rebuilt from
    the earlier of the operation's old and new positions. Raises ValueError
    for a field that can't change (id, seq, kind, counterpart, transfer_id:
    delete the operation and record another instead), and ValidationError or
    OperationRefused as record does.

    Example: edit(accounts, fineco, deposit_id, amount=1500.0) raises the
    cash of every row from the deposit on by the 500 EUR added.
    """
    if _FIXED_FIELDS & new_fields.keys():
        raise ValueError(f"an edit can't change {sorted(_FIXED_FIELDS & new_fields.keys())}")
    old = _find(account, op_id)
    edited = {account.idx: replace(old, **new_fields)}
    half = _other_half(accounts, account, old)
    if half is not None:
        other, other_op = half
        edited[other.idx] = replace(other_op, **{k: v for k, v in new_fields.items() if k in ("date", "amount")})
    journals = {idx: [op if op.id != after.id else after for op in _journal_of(accounts[idx])]
                for idx, after in edited.items()}
    return _rebuilt(accounts, journals, changed={after.id for after in edited.values()})


def _rebuilt(accounts: dict[int, Account], journals: dict[int, list[Operation]],
             changed: set[str] | None = None) -> Changes:
    """Return the changes for the accounts in `journals` (account number -> its new journal), each ledger rebuilt.

    Each ledger keeps the rows of its current one that the new journal
    still builds the same way (see rows_up_to_date): those before an
    operation added, deleted or edited, and none of a ledger left out of
    step with its journal. When rebuilding refuses one of the operations in
    `changed` (those being recorded or edited), its own error is raised, not
    OperationRefused: "Quantity sold (5) exceeds...", not "The sale of ...
    would no longer be possible".
    """
    changes = {}
    for idx, journal in journals.items():
        account = accounts[idx]
        from_index = rows_up_to_date(account.df, journal)
        try:
            ledger = rebuild(account.name, journal, ledger=account.df, from_index=from_index)
        except OperationRefused as ex:
            if changed and ex.operation.id in changed:
                raise ex.reason from ex
            raise
        changes[idx] = (journal, ledger)
    return changes


def _journal_of(account: Account) -> list[Operation]:
    """Return `account`'s journal; ValueError for an account recorded before the journal and not migrated yet."""
    if account.journal is None:
        raise ValueError(f"account {account.name} has no journal yet")
    return account.journal


def _next_seq(account: Account) -> int:
    """Return the order of entry of the next operation recorded in `account`: 1 for the first."""
    return max((op.seq for op in _journal_of(account)), default=0) + 1


def _find(account: Account, op_id: str) -> Operation:
    """Return the operation `op_id` of `account`'s journal; ValueError when it has none."""
    found = next((op for op in _journal_of(account) if op.id == op_id), None)
    if found is None:
        raise ValueError(f"account {account.name} has no operation {op_id}")
    return found


def _account_named(accounts: dict[int, Account], name: str, besides: Account) -> Account:
    """Return the account called `name`, other than `besides`: the other side of a transfer."""
    found = next((acc for acc in accounts.values() if acc.name == name and acc.idx != besides.idx), None)
    if found is None:
        raise ValueError(f"no account named {name}")
    return found


def _other_half(accounts: dict[int, Account], account: Account, op: Operation) -> tuple[Account, Operation] | None:
    """Return (the other account, its half) of the transfer `op` of `account`, or None.

    None when `op` isn't a transfer, or the other account was deleted.
    The half is found by the transfer_id both share.
    """
    if op.transfer_id is None:
        return None
    for other in accounts.values():
        if other.idx != account.idx and other.journal is not None:
            half = next((o for o in other.journal if o.transfer_id == op.transfer_id), None)
            if half is not None:
                return other, half
    return None
