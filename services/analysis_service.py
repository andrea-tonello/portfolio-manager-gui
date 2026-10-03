import pandas as pd
import numpy as np
from datetime import datetime
from itertools import chain

from domain.errors import ValidationError
from domain.history import portfolio_history
from domain.ledger import Op, Product, get_pf_date, holding_rows
from domain.positions import aggregate_positions, get_tickers, priced_positions
from domain.returns import xirr
from services.market_data import download_close, download_prices_eur, fetch_ticker_name
from utils.other_utils import round_half_up

# Days a stock exchange is open in a year; turns daily returns and volatility into yearly ones.
TRADING_DAYS_PER_YEAR = 252
# Yearly return of a riskless investment, which the Sharpe ratio subtracts from the portfolio's.
RISK_FREE_RATE = 0.02
# Monte Carlo VaR: how many future outcomes to simulate, and the first day of
# price history used to estimate the assets' returns and how they move together.
VAR_SIMULATIONS = 50_000
VAR_HISTORY_START = "2010-01-01"


def compute_summary(accounts, ref_date, dt_str):
    """Statistics of each Account in `accounts` and of all of them together, on `ref_date`.

    Returns dict:
    {
        "accounts": [{ acc_idx, broker_name, nav, current_liq, asset_value,
                       historic_liq, pl, pl_unrealized, xirr_full, xirr_ann, positions }],
        "portfolio": { nav, current_liq, asset_value, historic_liq, pl, pl_unrealized,
                       xirr_full, xirr_ann, twrr_full, twrr_ann, volatility, sharpe_ratio },
        "pf_history": DataFrame or None,
        "min_date": datetime or None,
    }
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

        # XIRR cash flows: deposits (money in, negative), withdrawals (money out,
        # positive), and finally the account's value today, as if cashed out now.
        cashflow_df = df_valid[df_valid["operation"].isin((Op.DEPOSIT, Op.WITHDRAWAL))]
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
        pf_history_df = portfolio_history(min_date, ref_date, accounts)

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
        },
        "pf_history": pf_history_df,
        "min_date": min_date,
    }


def compute_correlation(accounts, start_ref_date, end_ref_date, asset1=None, asset2=None, window=None):
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


def compute_drawdown(accounts, start_ref_date, end_ref_date):
    """Drawdown of the portfolio made of `accounts` (a list of Account) between the two dates.

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
    running_max = pf_history_df["nav"].expanding().max()
    drawdown = (pf_history_df["nav"] - running_max) / running_max
    mdd = drawdown.min()

    return {
        "pf_history": pf_history_df,
        "drawdown": drawdown,
        "mdd": mdd,
        "has_data": True,
    }


def _simulate_outcomes(value, daily_return, daily_std, days, num_simulations, rng=None):
    """Simulate many possible gains/losses (EUR) of the portfolio over `days` days, all at once.

    Each outcome is value × daily_return × days + value × daily_std × z × √days,
    where z is a random number from the standard bell curve (mostly between -2
    and +2). The VaR is then read off the worst outcomes, and the chart draws
    their histogram. NumPy generates all the random numbers in one call, which
    is much faster than a Python loop (≈65× in testing).

    `rng` is a NumPy random generator; pass one with a fixed seed to get
    repeatable outcomes (tests), or leave it None for fresh random numbers.
    """
    rng = rng or np.random.default_rng()
    z = rng.standard_normal(num_simulations)
    return value * daily_return * days + value * daily_std * z * np.sqrt(days)


def compute_var_mc(accounts, confidence_interval, projected_days):
    """Monte Carlo Value at Risk of the portfolio made of `accounts` (a list of Account).

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

    cash = sum(total_liquidity)
    portfolio_value = sum(assets_value)
    weights = np.array(assets_value) / portfolio_value
    portfolio_value = portfolio_value + cash

    prices_df = download_prices_eur(total_tickers, start_ref_date, end_dt)
    if prices_df.empty:
        return {"var": 0.0, "scenario_return": [], "portfolio_value": portfolio_value, "has_positions": False}

    prices_df = prices_df[asset_tickers]
    log_returns = np.log(prices_df / prices_df.shift(1)).dropna()

    def expected_return(tickers, log_returns, weights):
        means = []
        for ticker, weight in zip(tickers, weights):
            ticker_df = log_returns[ticker].copy().dropna()
            ticker_mean = ticker_df.mean() * weight
            means.append(ticker_mean)
        return np.sum(means)

    def standard_deviation(cov_matrix, weights):
        variance = weights.T @ cov_matrix @ weights
        return np.sqrt(variance)

    cov_matrix = log_returns.cov()
    portfolio_expected_return = expected_return(asset_tickers, log_returns, weights)
    portfolio_std_dev = standard_deviation(cov_matrix, weights)

    scenario_return = _simulate_outcomes(
        portfolio_value, portfolio_expected_return, portfolio_std_dev, projected_days,
        num_simulations=VAR_SIMULATIONS,
    ).tolist()

    var_value = -np.percentile(scenario_return, 100 * (1 - confidence_interval))

    return {
        "var": var_value,
        "scenario_return": scenario_return,
        "portfolio_value": portfolio_value,
        "has_positions": True,
    }


def compute_allocation(accounts, ref_date):
    """Compute asset allocation by product type across `accounts` (a list of Account).

    Returns dict mapping product type → market value in EUR.
    Categories: Stock, Stock ETF, MM ETF, Bond ETF, Cash.
    """
    ref_date = pd.Timestamp(ref_date)
    allocation = {}

    for account in accounts:
        # Cash from latest row
        cash = round_half_up(account.last("cash_held"))
        allocation[Product.CASH] = allocation.get(Product.CASH, 0) + cash

        # Active positions with product type
        positions = priced_positions(account.df, ref_date)
        product_by_ticker = holding_rows(account.df).groupby("ticker")["product"].last().to_dict()

        for pos in positions:
            product = product_by_ticker.get(pos["ticker"], Product.STOCK)
            allocation[product] = allocation.get(product, 0) + pos["value"]

    return allocation
