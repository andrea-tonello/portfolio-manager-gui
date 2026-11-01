"""An account: its name, where its CSV is stored, its ledger and its journal.

The ledger (`df`) has one row per operation and always starts with a synthetic
opening row, dated LEDGER_START_DATE with every running total at zero, so
that each real operation can read the "previous" totals from the row before
it. `transactions` gives the real operations only. The journal holds the
operations as entered, from which the ledger is rebuilt (domain/journal.py).
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:  # domain.journal builds rows with code that imports this module
    from domain.journal import Operation


@dataclass
class Account:
    """One broker account, as loaded from report-<name>.csv and journal-<name>.json.

    `path` is the ledger's CSV. `journal` is None for an account recorded
    before the journal existed, until it is migrated: its ledger is then the
    only record of its operations.

    Code that only reads accounts (analysis, history) must never assign to
    `df`: these are the objects the app keeps in memory, so a filtered ledger
    would replace the real one and be saved with the next operation. Filter
    into a local variable instead.
    """

    idx: int
    name: str
    path: str
    df: pd.DataFrame
    journal: "list[Operation] | None" = None

    @property
    def transactions(self) -> pd.DataFrame:
        """The real operations: every row except the opening row."""
        return self.df.iloc[1:]

    @property
    def has_transactions(self) -> bool:
        """True once at least one operation has been recorded."""
        return len(self.df) > 1

    def last(self, column: str) -> float:
        """The latest value of a running total such as "nav" or "cash_held"; 0.0 if there is none.

        Example: after deposits of 1000 and 500 EUR, last("cash_held") is 1500.0.
        """
        if self.df.empty:
            return 0.0
        return float(self.df.iloc[-1].get(column, 0) or 0)
