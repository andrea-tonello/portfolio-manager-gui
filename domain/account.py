"""An account: its name, where its CSV is stored, and its ledger.

The ledger (`df`) has one row per operation and always starts with a synthetic
opening row, dated LEDGER_START_DATE with every running total at zero, so
that each real operation can read the "previous" totals from the row before
it. `transactions` gives the real operations only.
"""

from dataclasses import dataclass

import pandas as pd


@dataclass
class Account:
    """One broker account, as loaded from `Report <name>.csv`.

    Code that only reads accounts (analysis, history) must never assign to
    `df`: these are the objects the app keeps in memory, so a filtered ledger
    would replace the real one and be saved with the next operation. Filter
    into a local variable instead.
    """

    idx: int
    name: str
    path: str
    df: pd.DataFrame

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
