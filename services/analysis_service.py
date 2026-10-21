import pandas as pd
import numpy as np
from datetime import date, datetime
from itertools import chain

from domain.account import Account
from domain.errors import ValidationError
from domain.history import portfolio_history
from domain.ledger import CASH_FLOWS, Product, get_pf_date, holding_rows
from domain.positions import aggregate_positions, get_tickers, priced_positions
from domain.returns import xirr
from services.market_data import download_close, download_prices_eur, fetch_sector_weights, fetch_ticker_name
from utils.date_utils import DateLike
from utils.other_utils import round_half_up

# Days a stock exchange is open in a year; turns daily returns and volatility into yearly ones.
TRADING_DAYS_PER_YEAR = 252
# Yearly return of a riskless investment, which the Sharpe ratio subtracts from the portfolio's.
RISK_FREE_RATE = 0.02
# Monte Carlo VaR: how many future outcomes to simulate, and the first day of
# price history whose days the outcomes are built from.
VAR_SIMULATIONS = 50_000
VAR_HISTORY_START = "2010-01-01"
# What the sector allocation splits: shares of companies, held directly or
# through an ETF. Bond and money-market ETFs and cash have no sector.
EQUITY_PRODUCTS = {Product.STOCK, Product.ETF_STOCK}
# The sector of the shares Yahoo has no sectors for.
UNCLASSIFIED = "unclassified"


def summary_history(accounts: list[Account], ref_date: date, dt_str: str) -> pd.DataFrame | None:
    """The portfolio's value day by day, from the first operation of `accounts` to `ref_date`.

    This is the chart of the Statistics tab, and what its TWRR, volatility and
    Sharpe ratio are computed from (compute_summary). Returns None when no
    account has an operation on or before `ref_date`. `dt_str` is `ref_date`
    as the user wrote it, for the error raised when an account has no row up to it.
    """
    ref_date = pd.Timestamp(ref_date)
    first_dates = [first for account in accounts if (first := get_pf_date(account, dt_str, ref_date)[1]) is not None]
    return portfolio_history(min(first_dates), ref_date, accounts) if first_dates else None


def compute_summary(accounts: list[Account], ref_date: date, dt_str: str,
                    pf_history: pd.DataFrame | None = None) -> dict:
    """Statistics of each Account in `accounts` and of all of them together, on `ref_date`.

    `pf_history` is what summary_history returned for the same accounts and
    day, when it is already known (the chart was drawn first): passing it
    saves downloading the whole price history again.

    Returns dict:
    {
        "accounts": [{ acc_idx, broker_name, nav, current_liq, asset_value,
                       historic_liq, pl, pl_unrealized, xirr_full, xirr_ann, positions }],
        "portfolio": { nav, current_liq, asset_value, historic_liq, pl, pl_unrealized,
                       xirr_full, xirr_ann, twrr_full, twrr_ann, volatility, sharpe_ratio,
                       has_positions, positions },
        "pf_history": DataFrame or None,
        "min_date": datetime or None,
    }
    The portfolio's `positions` are the accounts' merged by ticker
    (positions.aggregate_positions): a ticker held in two accounts is listed once.
    """
    ref_date = pd.Timestamp(ref_date)
    total_current_liq = []
    total_asset_value = []
    total_nav = []
    total_historic_liq = []
    total_pl = []
    total_pl_unrealized = []
    total_flows = []
    total_flows_dates = []
    first_dates = []
    accounts_with_positions = 0
    account_results = []

    for account in accounts:
        positions = priced_positions(account.df, ref_date)

        df_valid, first_date = get_pf_date(account, dt_str, ref_date)

        current_liq = round_half_up(float(df_valid.iloc[-1]["cash_held"]))
        historic_liq = df_valid["committed_cash"].iloc[-1]
        pl = df_valid["pl"].sum()
        asset_value = 0.0
        pl_unrealized = 0.0
        if positions:
            asset_value = round_half_up(sum(pos["value"] for pos in positions))
            pl_unrealized = pl + sum([pos["value"] - pos["pmc"] * pos["quantity"] for pos in positions])
        nav = current_liq + asset_value

        # XIRR cash flows: deposits and transfers in (money in, negative), withdrawals and transfers out
        # (money out, positive), and finally the account's value today, as if cashed out now.
        cashflow_df = df_valid[df_valid["operation"].isin(CASH_FLOWS)]
        flows = (cashflow_df["effective_amount"] * -1).tolist() + [nav]
        flows_dates = cashflow_df["date"].tolist() + [ref_date]

        xirr_full = np.nan
        xirr_ann = np.nan

        if positions:
            xirr_full = xirr(flows, flows_dates, annualization=(ref_date - flows_dates[0]).days)
            xirr_ann = xirr(flows, flows_dates)
            accounts_with_positions += 1

        total_flows.append(flows)
        total_flows_dates.append(flows_dates)

        total_current_liq.append(current_liq)
        total_asset_value.append(asset_value)
        total_nav.append(nav)
        total_historic_liq.append(historic_liq)
        total_pl.append(pl)
        total_pl_unrealized.append(pl_unrealized)
        if first_date is not None:
            first_dates.append(first_date)

        account_results.append({
            "acc_idx": account.idx,
            "broker_name": account.name,
            "nav": nav,
            "current_liq": current_liq,
            "asset_value": asset_value,
            "historic_liq": historic_liq,
            "pl": round_half_up(pl),
            "pl_unrealized": round_half_up(pl_unrealized),
            "xirr_full": xirr_full,
            "xirr_ann": xirr_ann,
            "positions": positions or [],
        })

    # Portfolio-level
    pf_history_df = None
    min_date = None
    xirr_total_full = np.nan
    xirr_total_ann = np.nan
    twrr_total = np.nan
    twrr_ann = np.nan
    volatility = np.nan
    sharpe_ratio = np.nan

    if first_dates:
        min_date = min(first_dates)
        pf_history_df = pf_history if pf_history is not None else portfolio_history(min_date, ref_date, accounts)

    if accounts_with_positions > 0:
        # XIRR
        combined_flows = list(
            chain.from_iterable(
                zip(dates, flows) for dates, flows in zip(total_flows_dates, total_flows)
            )
        )
        combined_flows.sort(key=lambda x: x[0])
        all_dates, all_flows = zip(*combined_flows)
        all_dates = list(all_dates)
        all_flows = list(all_flows)
        days_xirr = (ref_date - all_dates[0]).days
        xirr_total_full = xirr(all_flows, all_dates, annualization=days_xirr)
        xirr_total_ann = xirr(all_flows, all_dates)

        # TWRR
        if pf_history_df is not None and not pf_history_df.empty:
            days_twrr = len(pf_history_df)
            twrr_total = pf_history_df["cumulative_twrr"].iloc[-1]
            twrr_ann = (1 + twrr_total) ** (TRADING_DAYS_PER_YEAR / days_twrr) - 1

            # Sharpe
            risk_free_daily = (1 + RISK_FREE_RATE) ** (1 / TRADING_DAYS_PER_YEAR) - 1
            excess_returns = pf_history_df["daily_twrr"] - risk_free_daily
            sharpe_ratio = np.sqrt(TRADING_DAYS_PER_YEAR) * (excess_returns.mean() / excess_returns.std())

            volatility = pf_history_df["daily_twrr"].std() * np.sqrt(TRADING_DAYS_PER_YEAR)

    return {
        "accounts": account_results,
        "portfolio": {
            "nav": round_half_up(sum(total_nav)),
            "current_liq": round_half_up(sum(total_current_liq)),
            "asset_value": round_half_up(sum(total_asset_value)),
            "historic_liq": round_half_up(sum(total_historic_liq)),
            "pl": round_half_up(sum(total_pl)),
            "pl_unrealized": round_half_up(sum(total_pl_unrealized)),
            "xirr_full": xirr_total_full,
            "xirr_ann": xirr_total_ann,
            "twrr_full": twrr_total,
            "twrr_ann": twrr_ann,
            "volatility": volatility,
            "sharpe_ratio": sharpe_ratio,
            "has_positions": accounts_with_positions > 0,
            "positions": aggregate_positions([pos for acc in account_results for pos in acc["positions"]]),
        },
        "pf_history": pf_history_df,
        "min_date": min_date,
    }


def compute_correlation(accounts: list[Account], start_ref_date: DateLike, end_ref_date: DateLike,
                        asset1: str | None = None, asset2: str | None = None, window: int | None = None) -> dict:
    """Correlation between the assets held in `accounts` (a list of Account), or between two given tickers.

    Returns dict:
    {
        "correlation_matrix": DataFrame or None,
        "rolling_corr": Series or None,
        "active_tickers": list,
    }
    When asset1/asset2/window are None, only simple correlation is computed.
    When they are provided, only rolling correlation is computed.
    """
    _, active_tickers = get_tickers(accounts)
    correlation_matrix = None
    rolling_corr = None

    if asset1 and asset2 and window:
        # Rolling correlation only
        close_df, _ = download_close([asset1, asset2], start=start_ref_date, end=end_ref_date)

        missing = [t for t in [asset1, asset2] if t not in close_df.columns]
        if missing:
            ticker = missing[0]
            # Pick the error message: fetch_ticker_name raises TickerNotFound if Yahoo
            # doesn't know the ticker; if it returns, the ticker exists but has no
            # prices in the chosen period.
            fetch_ticker_name(ticker)
            raise ValidationError("operations.stock.ticker_nodata", ticker=ticker)

        close_df = close_df.ffill()
        returns_df = close_df.pct_change().dropna()
        rolling_corr = returns_df[asset1].rolling(window=window).corr(returns_df[asset2])
    else:
        # Simple correlation only
        if active_tickers:
            active_ticker_names = list(set([t[0] for t in active_tickers]))
            close_df, _ = download_close(active_ticker_names, start=start_ref_date, end=end_ref_date)
            close_df = close_df.ffill()
            returns_df = close_df.pct_change().dropna()
            correlation_matrix = returns_df.corr()

    return {
        "correlation_matrix": correlation_matrix,
        "rolling_corr": rolling_corr,
        "active_tickers": [t[0] for t in active_tickers] if active_tickers else [],
    }


def compute_drawdown(accounts: list[Account], start_ref_date: DateLike, end_ref_date: DateLike) -> dict:
    """Drawdown of the portfolio made of `accounts` (a list of Account) between the two dates.

    The drawdown on a day is how far the portfolio's growth has fallen below its highest point 
    so far, with deposits and withdrawals taken out (the TWRR, as for the volatility and the Sharpe ratio).

    Returns dict:
    {
        "pf_history": DataFrame,
        "drawdown": Series,
        "mdd": float,
        "has_data": bool,
    }
    """
    accounts = [account for account in accounts if account.has_transactions]

    if not accounts:
        return {"pf_history": None, "drawdown": None, "mdd": None, "has_data": False}

    pf_history_df = portfolio_history(start_ref_date, end_ref_date, accounts)
    pf_history_df = pf_history_df.dropna()
    # Growth from 1.0 on the start date; a peak of at least 1.0 counts a loss on the very first day too.
    growth = 1 + pf_history_df["cumulative_twrr"]
    drawdown = growth / growth.cummax().clip(lower=1.0) - 1
    mdd = drawdown.min()

    return {
        "pf_history": pf_history_df,
        "drawdown": drawdown,
        "mdd": mdd,
        "has_data": True,
    }


def _simulate_outcomes(value, daily_returns, days, num_simulations, rng=None):
    """Simulate `num_simulations` possible future gains/losses scenarios of 
    the portfolio  over `days` days, using data from the past.

    Inputs:
    - `value`: the invested value in EUR (no cash)
    - `daily_returns`: a np.array of the portfolio's past daily returns since VAR_HISTORY_STARTS
    - `days`: how many days ahead each outcome looks, e.g. 10
    - `num_simulations`: how many outcomes to simulate, e.g. 50,000
    - `rng`: a NumPy random generator

    Output: a np.array of `num_simulations` gains or losses in EUR, one per simulated future. 
    The VaR is read off its worst ones, and the chart draws its histogram.

    Example: value 10,000 and the days picked -2%, +1%, +0.5% give
    10,000€ * (0.98 * 1.01 * 1.005 - 1) = -52.51€.
    """
    rng = rng or np.random.default_rng()

    # What random days do we pick from daily_returns? 
    # --> 50000x10 vector filled with random day choices: 0, 1, 2, ..., len(daily_returns)
    picks = rng.integers(0, len(daily_returns), size=(num_simulations, days))

    # daily_returns[picks],     50000x10: each value holds the return on day `picks`
    # np.prod(1 + ..., axis=1), 50000x1 : compounds the 10 returns for each row, giving one final return per simulated future 
    # value * (... - 1),        50000x1 : turns each final return into a gain or loss in EUR (50000x1)
    return value * (np.prod(1 + daily_returns[picks], axis=1) - 1)


def compute_var_mc(accounts: list[Account], confidence_interval: float, projected_days: int) -> dict:
    """Value at Risk by historical Monte Carlo simulation: the scenarios replay real past days, from VAR_HISTORY_START to today.
    Only the invested value can be lost: the past returns apply to it, and the cash, which doesn't move, adds no risk.

    Returns dict:
    {
        "var": float,
        "scenario_return": list,
        "portfolio_value": float,
        "has_positions": bool,
    }
    """
    accounts = [account for account in accounts if account.last("assets_value") > 0.0]

    if not accounts:
        return {"var": 0.0, "scenario_return": [], "portfolio_value": 0.0, "has_positions": False}

    start_ref_date = VAR_HISTORY_START
    end_dt = datetime.now()

    _, total_tickers = get_tickers(accounts)

    total_positions = []
    total_liquidity = []

    for account in accounts:
        positions = priced_positions(account.df, end_dt)
        total_positions.extend(positions)

        df_valid, _ = get_pf_date(account, end_dt, end_dt)
        current_liq = round_half_up(float(df_valid.iloc[-1]["cash_held"]))
        total_liquidity.append(current_liq)

    aggr_positions = aggregate_positions(total_positions)
    assets_value = [pos["value"] for pos in aggr_positions]
    asset_tickers = [pos["ticker"] for pos in aggr_positions]

    invested = sum(assets_value)
    weights = np.array(assets_value) / invested
    portfolio_value = invested + sum(total_liquidity)

    prices_df = download_prices_eur(total_tickers, start_ref_date, end_dt)
    if prices_df.empty:
        return {"var": 0.0, "scenario_return": [], "portfolio_value": portfolio_value, "has_positions": False}

    prices_df = prices_df[asset_tickers]

    # Each past day's return of the portfolio as it is now: every asset's return that day, weighted by its
    # share of the invested value. (Simple returns, not log returns: they add up across assets.)
    daily_returns = (prices_df.pct_change().dropna() @ weights).to_numpy()

    scenario_return = _simulate_outcomes(
        invested, daily_returns, projected_days, num_simulations=VAR_SIMULATIONS,
    ).tolist()

    var_value = -np.percentile(scenario_return, 100 * (1 - confidence_interval))

    return {
        "var": var_value,
        "scenario_return": scenario_return,
        "portfolio_value": portfolio_value,
        "has_positions": True,
    }


def _holdings_on(accounts: list[Account], ref_date: DateLike) -> tuple[float, list[tuple[str, str, float]]]:
    """Return what `accounts` hold on `ref_date`: (cash, positions), in EUR at that day's prices.

    `positions` has one (ticker, product, value) per asset held in each
    account, e.g. [("ISP.MI", "Stock", 1500.0), ("SWDA.MI", "ETF-S", 3200.0)].
    """
    ref_date = pd.Timestamp(ref_date)
    cash = 0.0
    positions = []
    for account in accounts:
        # Cash held on ref_date: the last row on or before it (the opening row, at zero, before any operation)
        rows, _ = get_pf_date(account, ref_date, ref_date)
        cash += round_half_up(float(rows.iloc[-1]["cash_held"]))

        product_by_ticker = holding_rows(account.df).groupby("ticker")["product"].last().to_dict()
        for pos in priced_positions(account.df, ref_date):
            positions.append((pos["ticker"], product_by_ticker.get(pos["ticker"], Product.STOCK), pos["value"]))
    return cash, positions


def compute_allocation(accounts: list[Account], ref_date: DateLike) -> dict[str, float]:
    """Compute asset allocation by product type across `accounts` (a list of Account), on `ref_date`.

    Returns dict mapping product type → market value in EUR, all as of
    `ref_date`: the cash held that day and the positions at that day's prices.
    Categories: Stock, Stock ETF, MM ETF, Bond ETF, Cash.
    """
    cash, positions = _holdings_on(accounts, ref_date)
    allocation: dict[str, float] = {Product.CASH: cash}
    for _, product, value in positions:
        allocation[product] = allocation.get(product, 0) + value
    return allocation


def compute_sector_allocation(accounts: list[Account], ref_date: DateLike) -> tuple[dict[str, float], float]:
    """Split the stocks and equity ETFs that `accounts` hold on `ref_date` between sectors.

    Returns (allocation, portfolio_value). `allocation` maps a sector (one of
    market_data.SECTORS, or UNCLASSIFIED for shares Yahoo has no sectors for)
    to its value in EUR. `portfolio_value` is everything held, cash and the
    other ETFs included, to say how much of the portfolio the split covers.
    The sectors are today's, whatever `ref_date`.

    Example: 1000€ of ISP.MI (a bank) and 2000€ of an ETF 30% in technology and
    70% in financial services, plus 500€ of cash ->
    ({"financial_services": 2400.0, "technology": 600.0}, 3500.0).
    """
    cash, positions = _holdings_on(accounts, ref_date)
    equity = [(ticker, value) for ticker, product, value in positions if product in EQUITY_PRODUCTS]
    weights = fetch_sector_weights(sorted({ticker for ticker, _ in equity}))

    allocation: dict[str, float] = {}
    for ticker, value in equity:
        for sector, weight in weights.get(ticker, {UNCLASSIFIED: 1.0}).items():
            allocation[sector] = allocation.get(sector, 0) + value * weight
    return allocation, cash + sum(value for _, _, value in positions)
