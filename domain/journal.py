"""The operations journal: what the user did in an account, from which its ledger is rebuilt.

The ledger (domain/ledger.py) keeps the result of each operation: running
totals computed from the rows before it. The journal keeps the operations
themselves, with the values the user entered, so the ledger can be built
again at any time, e.g. after an operation is added before others. Each
operation builds one row with the same newrow_* builder the Operations
screen uses (domain/newrow.py), and the row records the operation's id and
fingerprint (op_id and op_hash columns): which operation built it, and as
it was then.

Operations are applied in order of date and, on the same day, of entry
(`seq`). Example: a deposit dated 10-01-2024, entered (seq 3) after a buy
on 05-01-2024 (seq 1) and a sale on 20-01-2024 (seq 2), gets the second row
of the rebuilt ledger, and the sale's row counts its cash.
"""

import hashlib
import json
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
from utils.columns import OP_HASH, OP_ID
from utils.constants import CURRENCIES, DATE_FORMAT
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

# The types a field's value can have when set: numbers for these, text for the others.
# Not bool, nor numpy's integers, which the journal file couldn't store.
_NUMBER_TYPES = {"quantity": (int,), **{name: (int, float)
                                         for name in ("amount", "conv_rate", "price", "fee", "tax_rate", "ratio")}}


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

        Refused: an unknown kind, a value of the wrong type (e.g. a seq of
        "3", which couldn't be ordered), a field of its kind missing or
        another kind's present, and values the row builders can't take (a
        split ratio of 0 would divide by zero, a currency other than EUR or
        USD has no exchange rate). Also stores `kind` as a Kind,
        so "deposit" and Kind.DEPOSIT give the same operation.
        """
        object.__setattr__(self, "kind", Kind(self.kind))  # raises ValueError for an unknown kind
        if not isinstance(self.id, str) or not self.id:
            self._refuse(f"its id must be a text, got {self.id!r}")
        if type(self.seq) is not int:
            self._refuse(f"seq must be a whole number, got {self.seq!r}")
        if type(self.date) is not date:
            self._refuse(f"date must be a day, got {self.date!r}")
        own = KIND_FIELDS[self.kind]
        for field in fields(self)[4:]:  # past id, seq, date and kind
            value = getattr(self, field.name)
            if field.name in own and value is None and field.name not in _OPTIONAL_FIELDS:
                self._refuse(f"no {field.name}")
            if field.name not in own and value is not None:
                self._refuse(f"it can't have a {field.name}")
            if value is not None and (isinstance(value, bool)
                                      or not isinstance(value, _NUMBER_TYPES.get(field.name, (str,)))):
                self._refuse(f"{field.name} has the wrong type: {value!r}")
            if field.name in _POSITIVE_FIELDS and value is not None and not value > 0:  # `not >` refuses NaN too
                self._refuse(f"{field.name} must be above 0, got {value}")
        if self.fee is not None and not self.fee >= 0:
            self._refuse(f"fee can't be negative, got {self.fee}")
        if self.tax_rate is not None and not 0 <= self.tax_rate <= 1:
            self._refuse(f"tax_rate must be between 0 and 1, got {self.tax_rate}")
        if self.fee_mode is not None and self.fee_mode not in _FEE_MODES:
            self._refuse(f"fee_mode must be one of {_FEE_MODES}, got {self.fee_mode!r}")
        if self.currency is not None and self.currency not in CURRENCIES:
            self._refuse(f"currency must be one of {CURRENCIES}, got {self.currency!r}")

    def _refuse(self, problem: str):
        """Raise the ValueError of __post_init__, naming the operation and its `problem`."""
        raise ValueError(f"{self.kind} operation {self.id}: {problem}")


def new_id() -> str:
    """Return a new operation id, unique in every journal: 32 hex characters, e.g. "3f2a9c...e1"."""
    return uuid.uuid4().hex


def sort_key(op: Operation) -> tuple[date, int]:
    """Return what orders `op` in its journal: its date, then its order of entry on that date."""
    return op.date, op.seq


def fingerprint(op: Operation) -> str:
    """Return a short code of everything `op` holds, which changes when any of its values does, e.g. "9c41d0e2a7b3f815".

    Each ledger row keeps the fingerprint of the operation that built it
    (op_hash column): a row built before the operation was edited no longer
    matches it, though its id still does.
    """
    text = json.dumps(operation_to_dict(op), sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def rows_up_to_date(ledger: pd.DataFrame, operations: list[Operation]) -> int:
    """Return how many rows of `ledger`, after its opening row, are still the ones `operations` build, in order.

    Each row names the operation that built it, as it was then (op_id and
    op_hash). The count stops at the first row whose operation has since
    been added before it, deleted or edited: from there on the rows must be
    built again. Example: rows built by A, B, C, and the journal A, X, B, C
    (X dated before B) -> 1; the journal A, B', C (B edited) -> 1 too.
    """
    if OP_HASH not in ledger:
        return 0
    built = zip(ledger[OP_ID].iloc[1:], ledger[OP_HASH].iloc[1:])
    count = 0
    for row, op in zip(built, sorted(operations, key=sort_key)):
        if row != (op.id, fingerprint(op)):
            break
        count += 1
    return count


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

    The same values the Operations screen passed to newrow_cash before the
    journal, so rebuilt rows match those recorded then.
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
    """Return the ledger `df` of the account `broker` with the row of `op` added, naming `op` (op_id and op_hash).

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

    # Text, with NaN on rows built before the journal. Each column is made text once, on the first
    # row it tags (created if missing); after that each row only sets its own cell.
    for column, value in ((OP_ID, op.id), (OP_HASH, fingerprint(op))):
        if column not in new or new[column].dtype != "str":
            new[column] = (new[column] if column in new else pd.Series(np.nan, index=new.index)).astype("str")
        new.loc[new.index[-1], column] = value
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


def trade_prices(trades: list[tuple[str, date, float]]) -> dict[str, pd.Series]:
    """Return the prices of `trades`, (ticker, day, price) each, by ticker and day: the `known` prices of a PriceBook.

    A rebuild values an asset at them when Yahoo has no price for it (see
    PriceBook.close). The last trade of a day gives its price.
    Example: [("AAA.MI", date(2024, 3, 1), 12.4)] -> {"AAA.MI": a Series holding 12.4 on 2024-03-01}.
    """
    by_ticker = {}
    for ticker, day, price in trades:
        by_ticker.setdefault(ticker, {})[pd.Timestamp(day)] = price
    return {ticker: pd.Series(prices, dtype=float).sort_index() for ticker, prices in by_ticker.items()}


def rebuild(broker: str, operations: list[Operation], ledger: pd.DataFrame | None = None,
            from_index: int = 0, prices: PriceBook | None = None) -> pd.DataFrame:
    """Return the ledger of the account `broker`, built from its journal `operations` in order of (date, seq).

    Without `ledger`, it starts from a new account's opening row. With the
    account's current `ledger`, its opening row and the rows of the first
    `from_index` operations are kept as they are and only the rest are built
    again: an operation added in the past changes nothing before its position.

    The rows built are valued with `prices`. Without it, the closes of the
    assets they can hold are downloaded once, from the first row built to
    the last, instead of once for each row; an asset Yahoo has no price for
    is valued at the latest price known, possibly that of its own trades.

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
        known = trade_prices([(op.ticker, op.date, op.price) for op in operations if op.kind in (Kind.BUY, Kind.SELL)])
        prices = PriceBook.download(_assets_to_value(df, to_build), start=to_build[0].date, end=to_build[-1].date,
                                    known=known)
    for op in to_build:
        try:
            df = apply(df, op, broker, prices)
        except ValidationError as ex:
            raise OperationRefused(op, ex) from ex
    return df
