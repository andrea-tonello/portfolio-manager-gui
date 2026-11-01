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
from domain.errors import ValidationError
from domain.journal import (
    Kind, Operation, OperationRefused, new_id, operation_from_dict, operation_to_dict, rebuild, rows_up_to_date,
    sort_key,
)
from utils.columns import OP_ID
from utils.formatting import fmt_eur

# The version written in every journal file; a file with another one can't be read.
JOURNAL_VERSION = 1

# What record, delete and edit return: {account number: (its new journal, its rebuilt ledger)}.
Changes = dict[int, tuple[list[Operation], pd.DataFrame]]

# Fields an edit can't change: what identifies the operation, and which accounts a transfer joins.
_FIXED_FIELDS = {"id", "seq", "kind", "counterpart", "transfer_id"}

# How far below zero a row's cash may be and still count as zero (float noise on cash rounded to the cent).
_CASH_TOLERANCE = 1e-6

# The kinds of operation that bring cash into their account: an edit lowering one must not leave even its own row
# short of cash (edit).
_CASH_IN = {Kind.DEPOSIT, Kind.DIVIDEND, Kind.SELL, Kind.TRANSFER_IN}


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
    other = _other_account_recorded(accounts, account, kind, fields)
    if other is not None:
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
    becomes impossible, e.g. a sale of shares whose buy is deleted, and
    ValidationError("journal.short_of_cash") when one is left short of
    cash, e.g. a buy paid with the deposit deleted.
    """
    deleted = find_operation(account, op_id)
    journals = {account.idx: [op for op in _journal_of(account) if op.id != op_id]}
    half = _other_half(accounts, account, deleted)
    if half is not None:
        other, other_op = half
        journals[other.idx] = [op for op in _journal_of(other) if op.id != other_op.id]
    return _rebuilt(accounts, journals, keep_cash=True)


def edit(accounts: dict[int, Account], account: Account, op_id: str, **new_fields) -> Changes:
    """Return the changes made by giving the operation `op_id` of `account` the values `new_fields`.

    The operation keeps its id and order of entry. A transfer's other half
    gets the same new date and amount. Each changed ledger is rebuilt from
    the earlier of the operation's old and new positions. Raises ValueError
    for a field that can't change (id, seq, kind, counterpart, transfer_id:
    delete the operation and record another instead), and ValidationError or
    OperationRefused as record does. Unlike record, it also refuses leaving
    an operation short of cash, as delete does. The edited operation's own
    row may go below zero when it spends cash (a buy, a withdrawal, a
    charge), as when recording it; one bringing cash in (a deposit, a
    dividend, a sale, a transfer in) is checked like the others.

    Example: edit(accounts, fineco, deposit_id, amount=1500.0) raises the
    cash of every row from the deposit on by the 500 EUR added.
    """
    if _FIXED_FIELDS & new_fields.keys():
        raise ValueError(f"an edit can't change {sorted(_FIXED_FIELDS & new_fields.keys())}")
    old = find_operation(account, op_id)
    edited = {account.idx: replace(old, **new_fields)}
    half = _other_half(accounts, account, old)
    if half is not None:
        other, other_op = half
        edited[other.idx] = replace(other_op, **{k: v for k, v in new_fields.items() if k in ("date", "amount")})
    journals = {idx: [op if op.id != after.id else after for op in _journal_of(accounts[idx])]
                for idx, after in edited.items()}
    return _rebuilt(accounts, journals, changed={after.id for after in edited.values()}, keep_cash=True,
                    own_rows={after.id for after in edited.values() if after.kind not in _CASH_IN})


def _rebuilt(accounts: dict[int, Account], journals: dict[int, list[Operation]],
             changed: set[str] | None = None, keep_cash: bool = False, own_rows: set[str] = frozenset()) -> Changes:
    """Return the changes for the accounts in `journals` (account number -> its new journal), each ledger rebuilt.

    Each ledger keeps the rows of its current one that the new journal
    still builds the same way (see rows_up_to_date): those before an
    operation added, deleted or edited, and none of a ledger left out of
    step with its journal. When rebuilding refuses one of the operations in
    `changed` (those being recorded or edited), its own error is raised, not
    OperationRefused: "Quantity sold (5) exceeds...", not "The sale of ...
    would no longer be possible". With `keep_cash` (a removal or an edit),
    no operation but those in `own_rows` may be left short of cash (see
    _refuse_short_of_cash).
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
        if keep_cash:
            _refuse_short_of_cash(account, ledger, besides=own_rows)
        changes[idx] = (journal, ledger)
    return changes


def _refuse_short_of_cash(account: Account, ledger: pd.DataFrame, besides: set[str]) -> None:
    """Raise ValidationError("journal.short_of_cash") when `ledger`, rebuilt after a removal or an edit, leaves an operation short of cash.

    That is a row, other than those of the operations `besides`, whose cash
    is now below zero but wasn't in `account`'s current ledger. A row
    already below zero doesn't count, however the change moves it: buys
    and withdrawals aren't checked when recorded, so a history can be short
    somewhere already, and undoing a deposit just recorded must still put
    it back as it was. The error names the first such row.

    Example: removing the deposit of 10,000 that a buy of 1,002 on
    03-01-2024 spent -> "This would leave Test Broker short of cash: -1,002.00€ on 03-01-2024".
    """
    cash = ledger["cash_held"].astype(float)
    before = ledger[OP_ID].map(account.df.set_index(OP_ID)["cash_held"]).astype(float)
    # A row the current ledger lacks has no cash before (NaN, which compares False): it counts as not short before.
    short = (cash < -_CASH_TOLERANCE) & ~(before < -_CASH_TOLERANCE) & ~ledger[OP_ID].isin(besides)
    if short.any():
        row = ledger[short].iloc[0]
        raise ValidationError("journal.short_of_cash", account=account.name, cash=fmt_eur(float(row["cash_held"])),
                              date=row["date"])


def _journal_of(account: Account) -> list[Operation]:
    """Return `account`'s journal.

    Raises ValidationError("journal.not_migrated") for an account recorded
    before the journal whose migration hasn't succeeded yet (e.g. the app
    started offline): it can't change until then.
    """
    if account.journal is None:
        raise ValidationError("journal.not_migrated", account=account.name)
    return account.journal


def last_entered(account: Account) -> Operation:
    """Return the operation recorded last in `account`, whatever its date: what "remove last" undoes.

    E.g. a split found on Yahoo and recorded today on its date of last
    month, before newer operations. Raises ValidationError for an account not
    migrated yet (see _journal_of); the account must have an operation.
    """
    return max(_journal_of(account), key=lambda op: op.seq)


def later_operations(accounts: dict[int, Account], account: Account, kind: Kind, day: date, **fields) -> int:
    """Return how many operations recording one of `kind` on `day` in `account` recalculates: those dated after it.

    Takes the same arguments as record, and counts in every account it
    changes: for a transfer out, the counterpart's too. Those of `day`
    itself don't count, since a new operation goes after them. Example:
    with operations on 02-01, 03-01 and 05-01, a deposit on 03-01
    recalculates 1. Raises ValidationError for an account not migrated yet
    (see _journal_of).

    A ledger out of step with its journal (its rebuild failed offline at
    load) also has its rows rebuilt from where they differ. Those aren't
    counted: they are only brought back to what the journal says.
    """
    changed = [account, _other_account_recorded(accounts, account, kind, fields)]
    return sum(_count_after(_journal_of(each), (day, _next_seq(each))) for each in changed if each is not None)


def later_operations_deleting(accounts: dict[int, Account], account: Account, op_id: str) -> int:
    """Return how many operations deleting `op_id` from `account` recalculates: those after it.

    For a transfer, in both accounts. Example: deleting the second of three
    deposits on 02-01, 03-01 and 05-01 recalculates 1. Raises
    ValidationError as delete does, before deleting anything.
    """
    return sum(_count_after(_journal_of(each), sort_key(op), besides=op.id)
               for each, op in _with_other_half(accounts, account, find_operation(account, op_id)))


def later_operations_editing(accounts: dict[int, Account], account: Account, op_id: str, **new_fields) -> int:
    """Return how many other operations giving `op_id` of `account` the values `new_fields` recalculates.

    Those after the earlier of its place before and after the edit: a new
    date moves it among the others. For a transfer, in both accounts.
    Example: with deposits on 02-01, 03-01 and 05-01, moving the last to
    01-01 recalculates the other 2. Raises ValidationError as edit does.
    """
    day = new_fields.get("date")
    return sum(_count_after(_journal_of(each), min(sort_key(op), (day or op.date, op.seq)), besides=op.id)
               for each, op in _with_other_half(accounts, account, find_operation(account, op_id)))


def _count_after(journal: list[Operation], place: tuple[date, int], besides: str | None = None) -> int:
    """Return how many operations of `journal`, other than `besides`, come after `place`, a (date, order of entry)."""
    return sum(sort_key(op) > place and op.id != besides for op in journal)


def transfer_half(accounts: dict[int, Account], account: Account, op_id: str) -> tuple[Account, Operation] | None:
    """Return (the other account, its half) of the transfer `op_id` of `account`, or None.

    None when the operation isn't a transfer, or its other account was
    deleted. Lets a screen say which accounts deleting a transfer changes,
    before deleting it, and edit a transfer in from the account sending it.
    Raises ValidationError("journal.partner_unavailable") when the other
    account is there but not migrated yet (see _other_half).

    Example: for Directa's transfer in of 300 from Fineco ->
    (fineco, Operation(kind="transfer_out", amount=300.0, counterpart="Directa", ...));
    for a deposit -> None.
    """
    return _other_half(accounts, account, find_operation(account, op_id))


def _next_seq(account: Account) -> int:
    """Return the order of entry of the next operation recorded in `account`: 1 for the first."""
    return max((op.seq for op in _journal_of(account)), default=0) + 1


def find_operation(account: Account, op_id: str) -> Operation:
    """Return the operation `op_id` of `account`'s journal (the op_id of its ledger row); ValueError when it has none.

    Raises ValidationError for an account not migrated yet (see _journal_of).
    """
    found = next((op for op in _journal_of(account) if op.id == op_id), None)
    if found is None:
        raise ValueError(f"account {account.name} has no operation {op_id}")
    return found


def _with_other_half(accounts: dict[int, Account], account: Account, op: Operation) -> list[tuple[Account, Operation]]:
    """Return the operations a change of `op` touches, each with its account: [(account, op)], and its other half.

    The other half only for a transfer whose other account is still there.
    Example: Fineco's transfer out of 300 to Directa ->
    [(fineco, the transfer out), (directa, its transfer in)]; a deposit -> [(fineco, the deposit)].
    """
    half = _other_half(accounts, account, op)
    return [(account, op)] if half is None else [(account, op), half]


def _other_account_recorded(accounts: dict[int, Account], account: Account, kind: Kind, fields: dict) -> Account | None:
    """Return the other account that recording an operation of `kind` and `fields` in `account` changes, or None.

    Only a transfer out has one: the account named `counterpart`, which receives the cash.
    """
    return _account_named(accounts, fields["counterpart"], besides=account) if kind == Kind.TRANSFER_OUT else None


def _account_named(accounts: dict[int, Account], name: str, besides: Account) -> Account:
    """Return the account called `name`, other than `besides`: the other side of a transfer."""
    found = next((acc for acc in accounts.values() if acc.name == name and acc.idx != besides.idx), None)
    if found is None:
        raise ValueError(f"no account named {name}")
    return found


def _other_half(accounts: dict[int, Account], account: Account, op: Operation) -> tuple[Account, Operation] | None:
    """Return (the other account, its half) of the transfer `op` of `account`, or None.

    None when `op` isn't a transfer, or the other account was deleted.
    The half is found by the transfer_id both share. Raises
    ValidationError("journal.partner_unavailable") when the other account is
    there but not migrated yet: changing one half alone would leave the
    other for good.
    """
    if op.transfer_id is None:
        return None
    for other in accounts.values():
        if other.idx != account.idx and other.name == op.counterpart and other.journal is None:
            raise ValidationError("journal.partner_unavailable", account=other.name)
    for other in accounts.values():
        if other.idx != account.idx and other.journal is not None:
            half = next((o for o in other.journal if o.transfer_id == op.transfer_id), None)
            if half is not None:
                return other, half
    return None
