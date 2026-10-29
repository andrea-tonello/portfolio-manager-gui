"""The operations journal: what the user did in an account, from which its ledger is rebuilt.

The ledger (domain/ledger.py) keeps the result of each operation: running
totals computed from the rows before it. The journal keeps the operations
themselves, with the values the user entered, so the ledger can be built
again at any time, e.g. after an operation is added before others. Each
operation builds one row with the same newrow_* builder the Operations
screen uses (domain/newrow.py), and the row records the operation's id in
its op_id column.

Operations are applied in order of date and, on the same day, of entry
(`seq`). Example: a deposit dated 10-01-2024, entered (seq 3) after a buy
on 05-01-2024 (seq 1) and a sale on 20-01-2024 (seq 2), gets the second row
of the rebuilt ledger, and the sale's row counts its cash.
"""

import uuid
from dataclasses import dataclass, fields
from datetime import date
from enum import StrEnum

import numpy as np
import pandas as pd

from domain.errors import ValidationError
from domain.ledger import Op, Product, opening_ledger
from domain.newrow import newrow_cash, newrow_etf_stock, newrow_split
from domain.positions import holdings
from services.market_data import PriceBook
from utils.columns import OP_ID
from utils.constants import DATE_FORMAT
from utils.formatting import fmt_eur


class Kind(StrEnum):
    """What an operation of the journal does, as stored in the journal file."""

    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    TRANSFER_OUT = "transfer_out"  # cash sent to another of the user's accounts
    TRANSFER_IN = "transfer_in"    # cash received from another of the user's accounts
    DIVIDEND = "dividend"
    CHARGE = "charge"              # a tax or fee paid from cash, e.g. stamp duty
    BUY = "buy"
    SELL = "sell"
    SPLIT = "split"


_TRADE_FIELDS = ("ticker", "asset_name", "product", "currency", "conv_rate", "quantity", "price", "fee",
                 "fee_mode", "tax_rate", "ter")

# The fields of each kind of operation besides id, seq, date and kind, in the order the journal file lists them.
KIND_FIELDS = {
    Kind.DEPOSIT: ("amount",),
    Kind.WITHDRAWAL: ("amount",),
    Kind.TRANSFER_OUT: ("amount", "counterpart", "transfer_id"),
    Kind.TRANSFER_IN: ("amount", "counterpart", "transfer_id"),
    Kind.DIVIDEND: ("ticker", "asset_name", "amount"),
    Kind.CHARGE: ("amount", "description"),
    Kind.BUY: _TRADE_FIELDS,
    Kind.SELL: _TRADE_FIELDS,
    Kind.SPLIT: ("ticker", "ratio"),
}

# Fields that can be None even in the kinds that have them: a charge with no
# description of its own, an ETF whose TER wasn't given (and every stock).
_OPTIONAL_FIELDS = {"description", "ter"}

# Fields that must be above 0 when set; the kind gives the row its sign.
_POSITIVE_FIELDS = {"amount", "quantity", "price", "conv_rate", "ratio"}

# How a trade's fee counts for taxes (see buy_asset).
_FEE_MODES = ("abp", "loss", "pending")


@dataclass(frozen=True)
class Operation:
    """One operation of an account's journal, with the values the user entered.

    - id: fixed for life (see new_id); it identifies the operation for
      deleting or editing it, and its row in the ledger (op_id column).
    - seq: the order of entry within the account; it orders operations on the same date.
    - kind: what the operation does. The fields of its kind are listed in
      KIND_FIELDS; the others stay None.

    The kinds' fields, as the Operations forms produce them:
    - amount: in EUR, always positive; the kind gives the row its sign
      (a withdrawal of 100 has amount 100 and stores -100).
    - counterpart, transfer_id: a transfer's other account, and the id shared
      by its two halves (one in each account's journal).
    - description: a charge's own description, e.g. "Stamp duty"; None stores "Tax".
    - Trades: price in `currency` and unrounded; conv_rate the USD->EUR rate
      (1.0 for EUR); fee in EUR; fee_mode "abp", "loss" or "pending" (see
      buy_asset); tax_rate e.g. 0.26; ter the text stored in the ledger, e.g. "0.2%".
    - ratio: a split's, e.g. 2.0 for 2:1.

    Example: Operation(id=new_id(), seq=1, date=date(2024, 1, 2), kind=Kind.DEPOSIT, amount=10000.0).
    """

    id: str
    seq: int
    date: date
    kind: Kind
    amount: float | None = None
    counterpart: str | None = None
    transfer_id: str | None = None
    ticker: str | None = None
    asset_name: str | None = None
    description: str | None = None
    product: str | None = None
    currency: str | None = None
    conv_rate: float | None = None
    quantity: int | None = None
    price: float | None = None
    fee: float | None = None
    fee_mode: str | None = None
    tax_rate: float | None = None
    ter: str | None = None
    ratio: float | None = None

    def __post_init__(self):
        """Raise ValueError for an operation that couldn't build its row, e.g. read from a damaged journal file.

        Refused: an unknown kind, a field of its kind missing or another
        kind's present, and values the row builders can't take (a split
        ratio of 0 would divide by zero). Also stores `kind` as a Kind, so
        "deposit" and Kind.DEPOSIT give the same operation.
        """
        object.__setattr__(self, "kind", Kind(self.kind))  # raises ValueError for an unknown kind
        own = KIND_FIELDS[self.kind]
        for field in fields(self)[4:]:  # past id, seq, date and kind
            value = getattr(self, field.name)
            if field.name in own and value is None and field.name not in _OPTIONAL_FIELDS:
                self._refuse(f"no {field.name}")
            if field.name not in own and value is not None:
                self._refuse(f"it can't have a {field.name}")
            if field.name in _POSITIVE_FIELDS and value is not None and not value > 0:  # `not >` refuses NaN too
                self._refuse(f"{field.name} must be above 0, got {value}")
        if self.fee is not None and not self.fee >= 0:
            self._refuse(f"fee can't be negative, got {self.fee}")
        if self.tax_rate is not None and not 0 <= self.tax_rate <= 1:
            self._refuse(f"tax_rate must be between 0 and 1, got {self.tax_rate}")
        if self.fee_mode is not None and self.fee_mode not in _FEE_MODES:
            self._refuse(f"fee_mode must be one of {_FEE_MODES}, got {self.fee_mode!r}")

    def _refuse(self, problem: str):
        """Raise the ValueError of __post_init__, naming the operation and its `problem`."""
        raise ValueError(f"{self.kind} operation {self.id}: {problem}")


def new_id() -> str:
    """Return a new operation id, unique in every journal: 32 hex characters, e.g. "3f2a9c...e1"."""
    return uuid.uuid4().hex


def sort_key(op: Operation) -> tuple[date, int]:
    """Return what orders `op` in its journal: its date, then its order of entry on that date."""
    return op.date, op.seq


def operation_to_dict(op: Operation) -> dict:
    """Return `op` as the journal file stores it: id, seq, ISO date, kind, then its kind's fields.

    Example: {"id": "3f2a...", "seq": 1, "date": "2024-01-02", "kind": "deposit", "amount": 10000.0}.
    """
    stored = {"id": op.id, "seq": op.seq, "date": op.date.isoformat(), "kind": str(op.kind)}
    stored.update({name: getattr(op, name) for name in KIND_FIELDS[op.kind]})
    return stored


def operation_from_dict(stored: dict) -> Operation:
    """Return the operation the journal file stores as `stored` (the reverse of operation_to_dict).

    Raises ValueError when it isn't a valid operation (e.g. a date that isn't
    ISO), TypeError when a field is missing (id, seq, date or kind) or no kind has it.
    """
    if "date" in stored:
        stored = {**stored, "date": date.fromisoformat(stored["date"])}
    return Operation(**stored)


class OperationRefused(ValidationError):
    """An operation of the journal can't be applied to the account as it stands at its date.

    Raised by rebuild when something added, deleted or changed before the
    operation makes it impossible. `operation` is the operation refused and
    `reason` the error it raised. Only sales, splits and transfers out can be
    refused (see apply), each with its own message, journal.refused.<kind>:
    "The sale of AAA.MI on 03-06-2024 would no longer be possible: Quantity
    sold (5) exceeds available quantity (0)".
    """

    def __init__(self, operation: Operation, reason: ValidationError):
        """Point at the message for `operation`'s kind, naming it and translating `reason` inside it."""
        super().__init__(f"journal.refused.{operation.kind}", ticker=operation.ticker,
                         account=operation.counterpart, date=operation.date.strftime(DATE_FORMAT), reason=reason)
        self.operation = operation
        self.reason = reason


def _cash_row(op: Operation) -> tuple[int, Op, str, str | float, str | float]:
    """Return what a cash operation's row stores: (sign of the amount, operation, product, ticker, asset_name).

    The same values services/operations_service.py passes to newrow_cash.
    Example: a transfer of 500 to "Directa" -> (-1, "Transfer Out", "Cash", NaN, "Directa").
    """
    return {
        Kind.DEPOSIT: (1, Op.DEPOSIT, Product.CASH, np.nan, np.nan),
        Kind.WITHDRAWAL: (-1, Op.WITHDRAWAL, Product.CASH, np.nan, np.nan),
        Kind.TRANSFER_OUT: (-1, Op.TRANSFER_OUT, Product.CASH, np.nan, op.counterpart),
        Kind.TRANSFER_IN: (1, Op.TRANSFER_IN, Product.CASH, np.nan, op.counterpart),
        Kind.DIVIDEND: (1, Op.DIVIDEND, Product.DIVIDEND, op.ticker, op.asset_name),
        Kind.CHARGE: (-1, Op.TAX, op.description or Product.TAX, np.nan, np.nan),
    }[op.kind]


def apply(df: pd.DataFrame, op: Operation, broker: str, prices: PriceBook | None = None) -> pd.DataFrame:
    """Return the ledger `df` of the account `broker` with the row of `op` added, holding op.id in its op_id column.

    The row is built from the totals of the last row of `df`, as when the
    user records the operation today, and values the assets held with
    `prices` (from Yahoo when not given). Raises ValidationError when the account
    can't take it: selling more than is held, splitting a ticker not held,
    or sending more cash than is held (a check the Operations form makes
    when the transfer is entered, and that must hold after a rebuild too).
    """
    day, date_str = op.date, op.date.strftime(DATE_FORMAT)
    if op.kind in (Kind.BUY, Kind.SELL):
        ter = np.nan if op.ter is None else op.ter
        new = newrow_etf_stock(df, date_str, day, broker, op.currency, op.product, op.ticker, op.quantity, op.price,
                               op.conv_rate, ter, op.fee, is_buy=op.kind == Kind.BUY, asset_name=op.asset_name,
                               tax_rate=op.tax_rate, fee_mode=op.fee_mode, prices=prices)
    elif op.kind == Kind.SPLIT:
        new = newrow_split(df, date_str, day, broker, op.ticker, op.ratio, prices=prices)
    else:
        available = float(df["cash_held"].iloc[-1])
        if op.kind == Kind.TRANSFER_OUT and op.amount > available:
            raise ValidationError("operations.transfer.not_enough_cash", available=fmt_eur(available))
        sign, operation, product, ticker, name = _cash_row(op)
        new = newrow_cash(df, date_str, day, broker, sign * op.amount, operation, product, ticker, name, prices=prices)

    # Text with NaN on rows built before the journal; the column is created on the first row it tags.
    ids = new[OP_ID] if OP_ID in new else pd.Series(np.nan, index=new.index)
    new[OP_ID] = ids.astype("str")
    new.loc[new.index[-1], OP_ID] = op.id
    return new


def _assets_to_value(ledger: pd.DataFrame, operations: list[Operation]) -> list[tuple[str, str]]:
    """Return (ticker, currency) of every asset the rows of `operations`, built after `ledger`, can hold.

    Those held at the end of `ledger`, in the currency of their last row,
    and those `operations` buy or sell: a row in another currency than EUR
    is valued with the USD->EUR rate, even a sale in USD of an asset bought
    in EUR. Assets sold out before are left out: their prices aren't needed.

    Example: a ledger holding UUU (bought in USD) and operations buying AAA.MI
    -> [("AAA.MI", "EUR"), ("UUU", "USD")], in no particular order.
    """
    _, held = holdings(ledger)
    assets = set(zip(held["ticker"], held["curr"]))
    assets |= {(op.ticker, op.currency) for op in operations if op.kind in (Kind.BUY, Kind.SELL)}
    return list(assets)


def rebuild(broker: str, operations: list[Operation], ledger: pd.DataFrame | None = None,
            from_index: int = 0, prices: PriceBook | None = None) -> pd.DataFrame:
    """Return the ledger of the account `broker`, built from its journal `operations` in order of (date, seq).

    Without `ledger`, it starts from a new account's opening row. With the
    account's current `ledger`, its opening row and the rows of the first
    `from_index` operations are kept as they are and only the rest are built
    again: an operation added in the past changes nothing before its position.

    The rows built are valued with `prices`. Without it, the closes of the
    assets they can hold are downloaded once, from the first row built to
    the last, instead of once for each row.

    Raises OperationRefused for the first operation that can't be applied.
    The caller decides whether that is the operation being recorded or a
    later one it would make impossible.

    Example: a journal holding a deposit on 02-01 and a buy on 05-01, and
    now a withdrawal on 03-01, is rebuilt with from_index=1 from the ledger
    of the first two: the deposit's row is kept, the withdrawal's and the
    buy's are built again.
    """
    if ledger is None and from_index:
        raise ValueError("rebuilding from an operation past the first needs the ledger holding the ones before it")
    df = opening_ledger(broker) if ledger is None else ledger.iloc[:from_index + 1]
    to_build = sorted(operations, key=sort_key)[from_index:]
    if prices is None and to_build:
        prices = PriceBook.download(_assets_to_value(df, to_build), start=to_build[0].date, end=to_build[-1].date)
    for op in to_build:
        try:
            df = apply(df, op, broker, prices)
        except ValidationError as ex:
            raise OperationRefused(op, ex) from ex
    return df
