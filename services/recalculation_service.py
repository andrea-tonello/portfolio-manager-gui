"""Recalculating the history: every account's ledger rebuilt from its first operation, with the app's current rules.

A ledger is only rebuilt from where its journal changes, so rows computed
by an older version of the rules (domain/rules.py) keep their values until
the history is recalculated: from Settings, or when the app offers it after
an update that changed the rules (components/recalculation.py). Nothing is
saved here: AppState.commit_recalculation saves.
"""

from domain.account import Account
from domain.errors import ValidationError
from domain.journal import Kind, OperationRefused, prices_for, rebuild
from services.journal_service import Changes
from services.market_data import PriceBook
from services.migration_service import Difference, row_differences
from utils.columns import OP_ID


class RecalculationError(ValidationError):
    """An account's history can't be recalculated: under the current rules, one of its operations can't be applied.

    E.g. a sale that a changed rule leaves without enough shares. The
    message names the account and the operation.
    """

    def __init__(self, account: str, reason: OperationRefused):
        """Point at the message naming `account` and the `reason` (the operation refused, and why)."""
        super().__init__("journal.recalculate.refused", account=account, reason=reason)


def recalculate(accounts: dict[int, Account]) -> Changes:
    """Return every account with a journal, its ledger rebuilt from its first operation: {account number: (journal, ledger)}.

    The journals don't change. One download of prices serves every account,
    over their whole history; an asset Yahoo no longer has is valued at
    the latest price known, as in any rebuild. Raises PricesUnavailable
    when Yahoo can't be reached (e.g. offline), and RecalculationError when
    an operation can't be applied any more. Accounts not moved to the
    journal yet are left out: the migration rebuilds them anyway.
    """
    journaled = {idx: account for idx, account in accounts.items() if account.journal is not None}
    prices = _prices(list(journaled.values()))
    changes = {}
    for idx, account in journaled.items():
        try:
            changes[idx] = (account.journal, rebuild(account.name, account.journal, prices=prices))
        except OperationRefused as ex:
            raise RecalculationError(account.name, ex) from ex
    return changes


def differences(accounts: dict[int, Account], changes: Changes) -> dict[int, list[Difference]]:
    """Return, by account number, the values each recalculated ledger in `changes` stores differently from the current one.

    Rows are matched by the operation that built them (op_id). The
    valuations aren't compared (see migration_service.row_differences):
    they are re-priced with today's data anyway. Only accounts with a
    difference are listed. Example: {1: [Difference("05-03-2025", "Sell",
    "ISP.MI", "tax", 12.4, 11.9)]} when a rule change lowered that tax.
    """
    found = {}
    for idx, (_, ledger) in changes.items():
        before = accounts[idx].df.set_index(OP_ID)
        account_differences = []
        for _, new in ledger.iloc[1:].iterrows():
            if new[OP_ID] in before.index:
                account_differences += row_differences(before.loc[new[OP_ID]], new)
        if account_differences:
            found[idx] = account_differences
    return found


def _prices(accounts: list[Account]) -> PriceBook | None:
    """Download once the prices that valuing every row of `accounts` needs: the assets they trade, over their history.

    None when they hold no operation: there is no row to value.
    """
    operations = [op for account in accounts for op in account.journal]
    if not operations:
        return None
    assets = sorted({(op.ticker, op.currency) for op in operations if op.kind in (Kind.BUY, Kind.SELL)})
    days = [op.date for op in operations]
    return prices_for(operations, assets, start=min(days), end=max(days))
