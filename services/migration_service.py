"""Moving the accounts recorded before the journal to it: each ledger turned into the journal that rebuilds it.

Each row of an account's ledger, after the opening row, becomes the
operation that recorded it, in the ledger's order, which was the order of
entry. The ledger is then rebuilt from the journal and compared with the one
it replaces: every value must match, except the valuations (assets_value,
nav), priced again with today's Yahoo data. Other differences come from what
a row didn't keep exactly; they are shown to the user, and the rebuilt
values kept. Values a row keeps only rounded (a price, a split's ratio) are
first recovered from the other columns where possible.

Nothing is saved here: AppState.commit_migration saves the result.
"""

import math
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from datetime import date, datetime
from fractions import Fraction

import pandas as pd

from domain.account import Account
from domain.errors import ValidationError
from domain.journal import Kind, Operation, OperationRefused, new_id, rebuild, trade_prices
from domain.ledger import ETF_PRODUCTS, Op, Product, holding_rows
from domain.tax import DEFAULT_CAPITAL_GAINS_TAX_RATE, buy_asset, sell_asset
from services.market_data import PriceBook
from utils.columns import COLUMNS, OP_ID
from utils.constants import DATE_FORMAT
from utils.other_utils import round_half_up

# Valued with each row's day's prices, which Yahoo may give differently today: not compared.
_VALUATIONS = {"assets_value", "nav"}

# Columns added after the first versions: rows written before them leave them empty, which
# meant these values (no purchase fees pending, the usual 26% tax). A rebuilt row fills them in.
_EMPTY_MEANT = {"pending_fees": 0.0, "tax_bracket": DEFAULT_CAPITAL_GAINS_TAX_RATE * 100}

# The fee modes an ETF trade can have, most likely first. On a sale "pending"
# works as "abp" (it only matters on a buy), and the form offers only these two.
_FEE_MODES = {Kind.BUY: ("abp", "loss", "pending"), Kind.SELL: ("abp", "loss")}


class MigrationError(ValidationError):
    """An account can't be moved to the journal: one of its operations can't be converted or rebuilt.

    Unlike being offline, this comes back at every start, so the message
    names the account and the operation, e.g. "The operation of 05-03-2025
    in Fineco can't be converted: ...". `reason` is a ValidationError
    (translated in turn) or the text of the problem.
    """

    def __init__(self, account: str, date: str, reason):
        """Point at the message naming `account`, the operation's `date` and the `reason`."""
        super().__init__("journal.migration.row_failed", account=account, date=date, reason=reason)


@dataclass(frozen=True)
class Difference:
    """A value that the ledger rebuilt from the journal stores differently from the ledger it replaces.

    Example: Difference("05-03-2025", "Buy", "ISP.MI", "effective_amount", -3901.25, -3901.26).
    """

    date: str        # of the row, as stored (DD-MM-YYYY)
    operation: str   # of the row, e.g. "Buy"
    ticker: str      # of the row; "" for one without, e.g. a deposit
    column: str
    before: object
    after: object


@dataclass
class Migration:
    """An account moved to the journal: its operations, the ledger rebuilt from them, and the values that changed.

    `source` is the ledger it was worked out from: the migration can only
    replace that one (see AppState.commit_migration).
    """

    journal: list[Operation]
    ledger: pd.DataFrame
    differences: list[Difference]
    source: pd.DataFrame


def migrate(accounts: dict[int, Account]) -> tuple[dict[int, Migration], list[MigrationError]]:
    """Return the migrations of the accounts in `accounts` without a journal, by account number, and the failures.

    Each account is migrated on its own: one that can't be (MigrationError,
    naming the account and the operation) doesn't hold back the others. The
    two halves of each transfer share a transfer_id, also with a half already
    in another account's journal, so an account migrated later joins them.
    One download of prices serves every account: if it fails (e.g.
    PricesUnavailable offline), it is raised and nothing is migrated.
    Nothing is saved.
    """
    legacy = {idx: account for idx, account in accounts.items() if account.journal is None}
    if not legacy:
        return {}, []
    journaled = [account for account in accounts.values() if account.journal is not None]
    transfer_ids = _pair_transfers({account.name: account.df for account in legacy.values()}, journaled)
    prices = _prices(list(legacy.values()))
    migrations, failures = {}, []
    for idx, account in legacy.items():
        try:
            migrations[idx] = _migrate_account(account, transfer_ids, prices)
        except MigrationError as ex:
            failures.append(ex)
    return migrations, failures


def _migrate_account(account: Account, transfer_ids: dict[tuple[str, int], str], prices: PriceBook) -> Migration:
    """Return the migration of `account`, or raise MigrationError naming the operation that prevents it.

    Rows recorded after later-dated ones are first moved to their own date
    where they can be (see _late_date). If rebuilding then refuses an
    operation, every such row keeps its place in the ledger instead, which
    gives the values the ledger was recorded with.
    """
    for keep_order in (False, True):
        journal = _journal(account, transfer_ids, prices, keep_order)
        try:
            ledger = rebuild(account.name, journal, prices=prices)
        except OperationRefused as ex:
            refused = ex
            continue
        return Migration(journal, ledger, _differences(account.df, ledger, journal), account.df)
    raise MigrationError(account.name, refused.operation.date.strftime(DATE_FORMAT), refused.reason) from refused


def _journal(account: Account, transfer_ids: dict[tuple[str, int], str], prices: PriceBook,
             keep_order: bool) -> list[Operation]:
    """Return the operations of `account`'s ledger, one per row, in the ledger's order.

    A row dated before the row above it gets the date _late_date gives it.
    Raises MigrationError naming the first row that can't be converted.
    """
    journal = []
    for position in range(1, len(account.df)):
        try:
            op = _operation(account.df, position, transfer_ids.get((account.name, position)))
            if journal and op.date < journal[-1].date:
                op = replace(op, date=_late_date(account.df, position, op, journal[-1].date, keep_order))
            journal.append(_with_fee_mode(account, position, op, prices))
        except (ValueError, TypeError, ValidationError) as ex:
            reason = ex if isinstance(ex, ValidationError) else str(ex)
            raise MigrationError(account.name, account.df.iloc[position]["date"], reason) from ex
    return journal


def _late_date(ledger: pd.DataFrame, position: int, op: Operation, previous_day: date, keep_order: bool) -> date:
    """Return the date of the operation `op`, at `position` of `ledger` but dated before the row above it.

    Only a split found on Yahoo is recorded so (Home recorded it after the
    last operation, with its own date). It keeps that date, so Home finds
    it recorded and doesn't offer it again, unless its ticker wasn't held
    yet then (a split of the day before the first buy): it goes to the day
    of the first buy instead, still within a day of Yahoo's. With
    `keep_order` (the first try was refused), or for any other operation, it
    takes `previous_day`, the date of the row above, keeping its place.

    Example: a 2:1 split of 15-08 recorded after a withdrawal of 02-09 keeps
    15-08; one of 02-01 recorded after the first buy, on 03-01, gets 03-01.
    """
    if keep_order or op.kind != Kind.SPLIT:
        return previous_day
    held = holding_rows(ledger.iloc[1:position], op.ticker)
    if held.empty:
        return previous_day
    first_held = min(datetime.strptime(day, DATE_FORMAT).date() for day in held["date"])
    return max(op.date, first_held)


def _pair_transfers(ledgers: dict[str, pd.DataFrame], journaled: list[Account]) -> dict[tuple[str, int], str]:
    """Return the transfer_id of every transfer row of `ledgers`, by (account name, row position).

    A transfer's two halves share it. They match as removing a transfer
    matched them before the journal: out of one account and into the
    other, on the same day, for the same amount, each naming the other
    account. Equal transfers on the same day pair in order. A half
    can also match one already in a `journaled` account whose own other
    half isn't there (e.g. that account was moved to the journal first): it
    takes that one's transfer_id. A half whose account was deleted gets an
    id of its own.
    """
    halves = defaultdict(lambda: ([], []))  # (sender, receiver, date, amount) -> (outgoing, incoming)
    for name, ledger in ledgers.items():
        for position in range(1, len(ledger)):
            row = ledger.iloc[position]
            amount = round(abs(float(row["effective_amount"])), 2)
            if row["operation"] == Op.TRANSFER_OUT:
                halves[(name, row["asset_name"], row["date"], amount)][0].append((name, position))
            elif row["operation"] == Op.TRANSFER_IN:
                halves[(row["asset_name"], name, row["date"], amount)][1].append((name, position))
    alone = Counter(op.transfer_id for account in journaled for op in account.journal if op.transfer_id)
    for account in journaled:
        for op in account.journal:
            if op.transfer_id and alone[op.transfer_id] == 1:
                day, amount = op.date.strftime(DATE_FORMAT), round(op.amount, 2)
                if op.kind == Kind.TRANSFER_OUT:
                    halves[(account.name, op.counterpart, day, amount)][0].append(op.transfer_id)
                else:
                    halves[(op.counterpart, account.name, day, amount)][1].append(op.transfer_id)
    transfer_ids = {}
    for sent, received in halves.values():
        for k in range(max(len(sent), len(received))):
            pair = [side[k] for side in (sent, received) if k < len(side)]
            transfer_id = next((half for half in pair if isinstance(half, str)), None) or new_id()
            for half in pair:
                if not isinstance(half, str):
                    transfer_ids[half] = transfer_id
    return transfer_ids


def _text(row: pd.Series, column: str) -> str | None:
    """Return the text in `column` of `row`, or None when the cell is empty."""
    value = row[column]
    return None if pd.isna(value) else str(value)


def _number(row: pd.Series, column: str, empty: float) -> float:
    """Return the number in `column` of `row`, or `empty` when the cell is empty (e.g. written before the column existed)."""
    value = row[column]
    return empty if pd.isna(value) else float(value)


def _operation(ledger: pd.DataFrame, position: int, transfer_id: str | None) -> Operation:
    """Return the operation that recorded the row at `position` of `ledger`, entered `position`-th.

    The reverse of journal.apply: the amounts lose their sign, a charge's
    description comes back from its product, a transfer's other account
    from its asset_name. An ETF trade's fee mode is "abp" for now (see
    _with_fee_mode). Raises ValueError for an operation the journal has no
    kind for, or values it can't hold.

    Example: a "Withdrawal" row of -500 -> Operation(kind="withdrawal", amount=500.0, ...).
    """
    row = ledger.iloc[position]
    common = {"id": new_id(), "seq": position, "date": datetime.strptime(row["date"], DATE_FORMAT).date()}
    operation, amount = row["operation"], abs(_number(row, "nominal_amount", 0.0))
    if operation in (Op.DEPOSIT, Op.WITHDRAWAL):
        return Operation(**common, kind=Kind.DEPOSIT if operation == Op.DEPOSIT else Kind.WITHDRAWAL, amount=amount)
    if operation in (Op.TRANSFER_OUT, Op.TRANSFER_IN):
        kind = Kind.TRANSFER_OUT if operation == Op.TRANSFER_OUT else Kind.TRANSFER_IN
        return Operation(**common, kind=kind, amount=amount, counterpart=_text(row, "asset_name"),
                         transfer_id=transfer_id)
    if operation == Op.DIVIDEND:
        return Operation(**common, kind=Kind.DIVIDEND, ticker=_text(row, "ticker"),
                         asset_name=_text(row, "asset_name"), amount=amount)
    if operation == Op.TAX:
        description = _text(row, "product")
        return Operation(**common, kind=Kind.CHARGE, amount=amount,
                         description=None if description == Product.TAX else description)
    if operation == Op.SPLIT:
        return Operation(**common, kind=Kind.SPLIT, ticker=_text(row, "ticker"), ratio=_split_ratio(ledger, position))
    if operation in (Op.BUY, Op.SELL):
        conv_rate = _number(row, "conv_rate", 1.0)
        return Operation(
            **common, kind=Kind.BUY if operation == Op.BUY else Kind.SELL,
            ticker=_text(row, "ticker"), asset_name=_text(row, "asset_name"), product=_text(row, "product"),
            currency=_text(row, "curr") or "EUR", conv_rate=conv_rate,
            quantity=abs(int(_number(row, "qt_exch", 0.0))), price=_price(row, conv_rate),
            fee=_number(row, "fee", 0.0), fee_mode="abp",
            tax_rate=_number(row, "tax_bracket", DEFAULT_CAPITAL_GAINS_TAX_RATE * 100) / 100,
            ter=_text(row, "ter"),
        )
    raise ValueError(f"unknown operation {operation!r}")


def _price(row: pd.Series, conv_rate: float) -> float:
    """Return the price a trade's row was recorded with, as exactly as the row allows.

    The row stores it rounded to 4 decimals, but its amounts were computed
    from it as typed: 1,000 shares at 100.12345 cost 100,123.45, at the
    stored 100.1235 100,123.50. When the stored price doesn't give the
    stored amount, the amount divided by the shares does (in USD, the
    amount before conversion, to the cent either way): that one is used.
    Example: the row above -> 100.12345.
    """
    stored, quantity = abs(_number(row, "price", 0.0)), abs(int(_number(row, "qt_exch", 0.0)))
    nominal = abs(_number(row, "nominal_amount", 0.0))

    def amount(price):
        """The amount in EUR that `quantity` units at `price` come to, rounded as newrow_etf_stock does."""
        return round_half_up(round_half_up(quantity * price) * conv_rate)

    if not quantity or amount(stored) == nominal:
        return stored
    in_currency = round(nominal / conv_rate, 2)
    for cents in (0, -0.01, 0.01):
        candidate = round((in_currency + cents) / quantity, 8)  # 100.12345, not the division's 100.12344999999999
        if amount(candidate) == nominal:
            return candidate
    return stored


def _split_ratio(ledger: pd.DataFrame, position: int) -> float:
    """Return the ratio the split at `position` of `ledger` was recorded with, as exactly as the ledger allows.

    The row stores it to 6 significant digits: a 1:3 reverse split's 1/3
    as "0.333333", which would turn 30 shares into 9.99999, and refuse a
    later sale of 10. Splits are fractions of small whole numbers, so the
    nearest such fraction is tried first, then the shares held after over
    those held before: the one giving the shares held as saved is kept.
    Example: "0.333333", 30 shares before and 10 after -> 1/3.
    """
    row = ledger.iloc[position]
    stored = _number(row, "qt_exch", 0.0)
    before = holding_rows(ledger.iloc[:position], row["ticker"])
    held_before = float(before["qt_held"].iloc[-1]) if not before.empty else 0.0
    if held_before <= 0 or not stored > 0:
        return stored
    held_after = _number(row, "qt_held", 0.0)
    candidates = [float(Fraction(str(stored)).limit_denominator(1000)), held_after / held_before, stored]
    return min(candidates, key=lambda ratio: abs(held_before * ratio - held_after))  # the first, on a tie


def _prices(accounts: list[Account]) -> PriceBook:
    """Download once the prices that valuing every row of `accounts` needs: all the assets they trade, over their history.

    The prices of their own trades are known prices (see PriceBook.close):
    an asset Yahoo no longer has (e.g. delisted) is valued at them rather
    than blocking the migration, as its valuations aren't compared.
    """
    assets, days, trades = set(), [], []
    for account in accounts:
        rows = account.df.iloc[1:]
        traded = rows[rows["operation"].isin([Op.BUY, Op.SELL])]
        assets |= set(zip(traded["ticker"], traded["curr"]))
        days += list(pd.to_datetime(rows["date"], format=DATE_FORMAT))
        trades += [(ticker, datetime.strptime(day, DATE_FORMAT).date(), abs(float(price)))
                   for ticker, day, price in zip(traded["ticker"], traded["date"], traded["price"])]
    if not days:  # no operation at all: no row to value
        return PriceBook(pd.DataFrame(), pd.DataFrame(), {})
    return PriceBook.download(list(assets), start=min(days), end=max(days), known=trade_prices(trades))


def _with_fee_mode(account: Account, position: int, op: Operation, prices: PriceBook) -> Operation:
    """Return `op` with the fee mode that rebuilds the row at `position` of `account`'s ledger as it was saved.

    The ledger doesn't store the fee mode, but it shows in the row: e.g. in
    "loss" mode the fee becomes a loss in the carryforward, in "abp" mode it
    raises the average buy price. Each mode an ETF trade can have is tried on
    the rows before it, as saved; the one matching the most of the columns
    it changes is kept, the likelier on a tie (with no fee, all match).
    Stocks always use "abp".
    """
    if op.kind not in _FEE_MODES or op.product not in ETF_PRODUCTS:
        return op
    saved = account.df.iloc[position]

    def matching(mode):
        """How many of the fee columns `op` in `mode` gives as saved."""
        columns = _fee_columns(account.df.iloc[:position], op, mode, prices)
        return sum(_same(value, saved[column]) for column, value in columns.items())

    return replace(op, fee_mode=max(_FEE_MODES[op.kind], key=matching))


def _fee_columns(before: pd.DataFrame, op: Operation, mode: str, prices: PriceBook) -> dict:
    """Return what the trade `op` in fee `mode` stores in the columns its fee mode changes, after the rows `before`.

    Worked out by buy_asset or sell_asset alone, without building the
    whole row, and rounded as newrow_etf_stock rounds them.
    """
    asset_rows = holding_rows(before, op.ticker)
    trade = (before, asset_rows, op.quantity, op.price, op.conv_rate, op.fee, op.date, op.product, op.ticker)
    if op.kind == Kind.BUY:
        results = buy_asset(*trade, fee_mode=mode, prices=prices)
    else:
        results = sell_asset(*trade, tax_rate=op.tax_rate, fee_mode=mode, prices=prices)
    return {"abp": round_half_up(results["abp"], decimal="0.0001"),
            **{column: round_half_up(results[column]) for column in ("generated_loss", "carryforward", "pending_fees")}}


def _same(before, after) -> bool:
    """Return True when two cells of a ledger hold the same value, however each was read or written.

    Numbers match to a millionth, so 10 read back from a file matches "+10"
    as written, and 1.0 matches "1.000000"; empty cells match each other.
    """
    if pd.isna(before) and pd.isna(after):
        return True
    try:
        return math.isclose(float(before), float(after), abs_tol=1e-6)
    except (TypeError, ValueError):
        return str(before) == str(after)


def _differences(before: pd.DataFrame, after: pd.DataFrame, journal: list[Operation]) -> list[Difference]:
    """Return the values of the rebuilt ledger `after` that differ from the ledger `before`, row by row.

    Each rebuilt row is compared with the row its operation came from (its
    seq is that row's position), wherever the rebuild placed it. The opening
    rows and the valuations aren't compared. An empty cell of a column added
    later counts as the value it meant (_EMPTY_MEANT): e.g. a buy saved
    before pending_fees existed matches its rebuilt row's 0.
    """
    position_of = {op.id: op.seq for op in journal}
    differences = []
    for new_position in range(1, len(after)):
        new = after.iloc[new_position]
        differences += row_differences(before.iloc[position_of[new[OP_ID]]], new)
    return differences


def row_differences(old: pd.Series, new: pd.Series) -> list[Difference]:
    """Return the values of the rebuilt ledger row `new` that differ from those of the row `old` it replaces.

    The valuations aren't compared: they depend on Yahoo's data of the day.
    An empty cell of a column added later counts as the value it meant
    (_EMPTY_MEANT). Example: a buy whose net amount went from -3901.25 to
    -3901.26 -> [Difference("05-03-2025", "Buy", "ISP.MI", "effective_amount", -3901.25, -3901.26)].
    """
    differences = []
    for column in COLUMNS:
        meant = column in _EMPTY_MEANT and pd.isna(old[column]) and _same(_EMPTY_MEANT[column], new[column])
        if column not in _VALUATIONS and not meant and not _same(old[column], new[column]):
            differences.append(Difference(old["date"], old["operation"], _text(old, "ticker") or "",
                                          column, old[column], new[column]))
    return differences
