"""What the accounts are worth right now: cash, positions at the latest prices, and profit or loss.

Home shows these numbers. compute_snapshot() fetches the prices (through
domain.positions.priced_positions); Snapshot and Position only do arithmetic
on what it found, so they can be checked without any network.
"""

from dataclasses import dataclass

from domain.account import Account
from domain.positions import priced_positions
from utils.date_utils import DateLike
from utils.other_utils import round_half_up


def _pct(amount, base):
    """Return `amount` as a percentage of `base`, or None when `base` is zero (nothing to compare with).

    Example: _pct(25.0, 200.0) -> 12.5.
    """
    return amount / base * 100 if base else None


@dataclass(frozen=True)
class Position:
    """One asset held, possibly in several accounts, valued at its latest price. Amounts are in EUR.

    `pmc` is the average buy price (fees included), `prev_close` the price one
    trading day earlier. Example: 20 shares bought at 50.05, now at 63.70,
    yesterday at 63.65 -> value 1274.0, unrealized_pnl +273.0, daily_pnl +1.0.
    """

    ticker: str
    name: str
    quantity: float
    pmc: float
    price: float
    prev_close: float

    @property
    def value(self) -> float:
        """What the position is worth at the latest price."""
        return self.quantity * self.price

    @property
    def cost(self) -> float:
        """What the position cost to buy."""
        return self.quantity * self.pmc

    @property
    def unrealized_pnl(self) -> float:
        """Gain or loss if it were sold at the latest price (before taxes)."""
        return self.quantity * (self.price - self.pmc)

    @property
    def unrealized_pct(self) -> float | None:
        """The price change since buying, in percent."""
        return _pct(self.price - self.pmc, self.pmc)

    @property
    def daily_pnl(self) -> float:
        """Gain or loss since the previous close."""
        return self.quantity * (self.price - self.prev_close)

    @property
    def daily_pct(self) -> float | None:
        """The price change since the previous close, in percent."""
        return _pct(self.price - self.prev_close, self.prev_close)


@dataclass(frozen=True)
class Snapshot:
    """The totals of one or more accounts at one moment, as Home shows them. Amounts are in EUR.

    `committed` is the money deposited minus the money withdrawn: the total P&L
    is measured against it. Example: 10,000 deposited, 9,000 cash left and
    positions worth 1,300 -> nav 10,300 and total_pnl +300 (+3%).
    """

    cash: float
    assets: float
    committed: float
    positions: list[Position]

    @property
    def nav(self) -> float:
        """Net asset value: cash plus positions."""
        return self.cash + self.assets

    @property
    def unrealized_pnl(self) -> float:
        """Gain or loss on what is still held, if it were all sold now."""
        return sum(p.unrealized_pnl for p in self.positions)

    @property
    def unrealized_pct(self) -> float | None:
        """unrealized_pnl as a percentage of what the positions cost."""
        return _pct(self.unrealized_pnl, sum(p.cost for p in self.positions))

    @property
    def daily_pnl(self) -> float:
        """Gain or loss of the positions since the previous close."""
        return sum(p.daily_pnl for p in self.positions)

    @property
    def daily_pct(self) -> float | None:
        """daily_pnl as a percentage of what the positions were worth at the previous close."""
        return _pct(self.daily_pnl, sum(p.quantity * p.prev_close for p in self.positions))

    @property
    def total_pnl(self) -> float:
        """Everything gained or lost so far, sold or not: nav minus the money put in."""
        return self.nav - self.committed

    @property
    def total_pct(self) -> float | None:
        """total_pnl as a percentage of the money put in."""
        return _pct(self.total_pnl, self.committed)


def _merge(positions: list[Position]) -> Position:
    """Combine the positions of one ticker held in several accounts into one, at their average buy price.

    Example: 20 shares bought at 50.05 and 10 at 55.10 -> 30 shares at 51.733.
    Price, previous close and name come from the first account.
    """
    first = positions[0]
    if len(positions) == 1:
        return first
    quantity = sum(p.quantity for p in positions)
    return Position(first.ticker, first.name, quantity, sum(p.cost for p in positions) / quantity,
                    first.price, first.prev_close)


def compute_snapshot(accounts: list[Account], ref_date: DateLike) -> Snapshot:
    """Value `accounts` together at `ref_date`, fetching the prices of what they hold.

    Positions in the same ticker are merged across accounts, in the order they
    are first met. Each account's positions are rounded to the cent before the
    totals are added up, as each account's own NAV is.
    """
    cash = assets = committed = 0.0
    by_ticker: dict[str, list[Position]] = {}
    for account in accounts:
        if account.df is None or account.df.empty:
            continue
        cash += account.last("cash_held")
        committed += account.last("committed_cash")
        priced = priced_positions(account.df, ref_date)
        if priced:
            assets += round_half_up(sum(p["value"] for p in priced))
        for p in priced:
            position = Position(p["ticker"], p["name"], p["quantity"], p["pmc"], p["price"], p["prev_close"])
            by_ticker.setdefault(p["ticker"], []).append(position)
    return Snapshot(cash, assets, committed, [_merge(group) for group in by_ticker.values()])
