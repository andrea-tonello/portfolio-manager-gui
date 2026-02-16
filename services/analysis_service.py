import pandas as pd
import numpy as np
from datetime import datetime
from itertools import chain

from services.market_data import download_close
from utils.date_utils import get_pf_date
from utils.account import portfolio_history, get_asset_value, get_tickers, aggregate_positions
from utils.other_utils import round_half_up
from utils.constants import DATE_FORMAT
import utils.newton as newton


def xirr(cash_flows, flows_dates, annualization=365, x0=0.1, x1=0.2, max_iter=100):
    days = [(data - flows_dates[0]).days for data in flows_dates]
    years = np.array(days) / annualization

    def npv_formula(rate):
        return sum(
            cf / (1 + rate) ** t
            for cf, t in zip(cash_flows, years)
        )

    try:
        xirr_rate = newton.secant(npv_formula, x0=x0, x1=x1, max_iter=max_iter)
        return xirr_rate
    except (ZeroDivisionError, RuntimeError):
        return np.nan


def compute_summary(translator, brokers, data, ref_date, dt_str, save_path=None):
    """
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

    for account in data:
        df_copy = account[1].copy()
        positions = get_asset_value(translator, df_copy, ref_date=ref_date)

        df_valid, first_date = get_pf_date(translator, df_copy, dt_str, ref_date)

        current_liq = round_half_up(float(df_valid.iloc[-1]["Liquidita Attuale"]))
        historic_liq = df_valid["Liq. Impegnata"].iloc[-1]
        asset_value = 0.0
        pl = df_valid["P&L"].sum()
        pl_unrealized = 0.0
        nav = current_liq

        cashflow_df = df_valid[df_valid["Operazione"].isin(["Deposito", "Prelievo"])]
        flows = (cashflow_df["Imp. Effettivo Operaz."] * -1).tolist()
        flows.append(nav)
        flows_dates = cashflow_df["Data"].tolist()
        flows_dates.append(ref_date)

        xirr_full = np.nan
        xirr_ann = np.nan

        if positions:
            asset_value = round_half_up(sum(pos["value"] for pos in positions))
            pl_unrealized = pl + sum([pos["value"] - pos["pmc"] * pos["quantity"] for pos in positions])
            flows = flows[:-1]
            nav = nav + round_half_up(asset_value)
            flows.append(nav)
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
            "acc_idx": account[0],
            "broker_name": brokers[account[0]],
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
        pf_history_df = portfolio_history(translator, min_date, ref_date, data)

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
            trading_days = 252
            days_twrr = len(pf_history_df)
            twrr_total = pf_history_df["TWRR Cumulativo"].iloc[-1]
            twrr_ann = (1 + twrr_total) ** (trading_days / days_twrr) - 1

            # Sharpe
            risk_free_rate = 0.02
            risk_free_daily = (1 + risk_free_rate) ** (1 / trading_days) - 1
            excess_returns = pf_history_df["TWRR Giornaliero"] - risk_free_daily
            sharpe_ratio = np.sqrt(trading_days) * (excess_returns.mean() / excess_returns.std())

            volatility = pf_history_df["TWRR Giornaliero"].std() * np.sqrt(trading_days)

    # Export CSV if save_path given
    if save_path and pf_history_df is not None and not pf_history_df.empty:
        pf_export = pf_history_df.dropna()
        rounding_dict = {
            "Liquidita": 2, "Liquidita Impegnata": 2, "Valore Titoli": 2, "NAV": 2,
            "Cash Flow": 2, "TWRR Giornaliero": 4, "TWRR Cumulativo": 4,
        }
        pf_export = pf_export.round(rounding_dict)
        pf_export = pf_export.set_index("Date")
        pf_export.to_csv(save_path, date_format="%Y-%m-%d")

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


def compute_correlation(translator, data, start_ref_date, end_ref_date, asset1, asset2, window):
    """
    Returns dict:
    {
        "correlation_matrix": DataFrame or None,
        "rolling_corr": Series,
        "active_tickers": list,
    }
    """
    for account in data:
        account[1] = account[1][account[1]["Operazione"].isin(["Acquisto", "Vendita"])]

    _, active_tickers = get_tickers(translator, data)
    correlation_matrix = None

    if active_tickers:
        active_ticker_names = list(set([t[0] for t in active_tickers]))
        close_df = download_close(active_ticker_names, start=start_ref_date, end=end_ref_date)
        if isinstance(close_df, pd.Series):
            close_df = close_df.to_frame(name=active_ticker_names[0])
        close_df = close_df.ffill()
        returns_df = close_df.pct_change().dropna()
        correlation_matrix = returns_df.corr()
    else:
        returns_df = pd.DataFrame()

    # Rolling correlation
    if not (asset1 in (active_tickers if not active_tickers else [t[0] for t in active_tickers])):
        close_df = download_close([asset1, asset2], start=start_ref_date, end=end_ref_date)
        if isinstance(close_df, pd.Series):
            close_df = close_df.to_frame(name=asset1)
        close_df = close_df.ffill()
        returns_df = close_df.pct_change().dropna()

    rolling_corr = returns_df[asset1].rolling(window=window).corr(returns_df[asset2])

    return {
        "correlation_matrix": correlation_matrix,
        "rolling_corr": rolling_corr,
        "active_tickers": [t[0] for t in active_tickers] if active_tickers else [],
    }


def compute_drawdown(translator, data, start_ref_date, end_ref_date):
    """
    Returns dict:
    {
        "pf_history": DataFrame,
        "drawdown": Series,
        "mdd": float,
        "has_data": bool,
    }
    """
    data = [account for account in data if len(account[1]) > 1]

    if not data:
        return {"pf_history": None, "drawdown": None, "mdd": None, "has_data": False}

    pf_history_df = portfolio_history(translator, start_ref_date, end_ref_date, data)
    pf_history_df = pf_history_df.dropna()
    running_max = pf_history_df["NAV"].expanding().max()
    drawdown = (pf_history_df["NAV"] - running_max) / running_max
    mdd = drawdown.min()

    return {
        "pf_history": pf_history_df,
        "drawdown": drawdown,
        "mdd": mdd,
        "has_data": True,
    }


def compute_var_mc(translator, data, confidence_interval, projected_days):
    """
    Returns dict:
    {
        "var": float,
        "scenario_return": list,
        "portfolio_value": float,
        "has_positions": bool,
    }
    """
    data = [account for account in data if account[1]["Valore Titoli"].iloc[-1] > 0.0]

    if not data:
        return {"var": 0.0, "scenario_return": [], "portfolio_value": 0.0, "has_positions": False}

    start_ref_date = "2010-01-01"
    end_dt = datetime.now()

    _, total_tickers = get_tickers(translator, data)
    usd_tickers = [t[0] for t in total_tickers if t[1] == "USD"]
    eur_tickers = [t[0] for t in total_tickers if t[1] == "EUR"]

    total_positions = []
    total_liquidity = []

    for account in data:
        df_copy = account[1].copy()
        positions = get_asset_value(translator, df_copy, ref_date=end_dt, suppress_progress=True)
        total_positions.extend(positions)

        df_valid, _ = get_pf_date(translator, df_copy, end_dt, end_dt)
        current_liq = round_half_up(float(df_valid.iloc[-1]["Liquidita Attuale"]))
        total_liquidity.append(current_liq)

    aggr_positions = aggregate_positions(total_positions)
    assets_value = [pos["value"] for pos in aggr_positions]
    asset_tickers = [pos["ticker"] for pos in aggr_positions]

    cash = sum(total_liquidity)
    portfolio_value = sum(assets_value)
    weights = np.array(assets_value) / portfolio_value
    portfolio_value = portfolio_value + cash

    tickers_to_download = []
    if usd_tickers:
        tickers_to_download.extend(usd_tickers)
    if eur_tickers:
        tickers_to_download.extend(eur_tickers)

    if tickers_to_download:
        tickers_to_download.append("USDEUR=X")
    else:
        return {"var": 0.0, "scenario_return": [], "portfolio_value": portfolio_value, "has_positions": False}

    close_prices = download_close(tickers_to_download, start=start_ref_date, end=end_dt)

    if isinstance(close_prices, pd.Series):
        close_prices = close_prices.to_frame(name=tickers_to_download[0])

    if close_prices.empty:
        return {"var": 0.0, "scenario_return": [], "portfolio_value": portfolio_value, "has_positions": False}

    close_prices = close_prices.ffill()

    final_usd_df = pd.DataFrame([])
    final_eur_df = pd.DataFrame([])
    indices_to_intersect = []

    exch_df = close_prices["USDEUR=X"].dropna()
    indices_to_intersect.append(exch_df.index)

    if eur_tickers:
        eur_prices_df = close_prices[eur_tickers].dropna(how="all")
        indices_to_intersect.append(eur_prices_df.index)
        final_eur_df = eur_prices_df

    if usd_tickers:
        usd_prices_df = close_prices[usd_tickers].dropna(how="all")
        indices_to_intersect.append(usd_prices_df.index)
        final_usd_df = usd_prices_df.mul(exch_df, axis=0)

    if not indices_to_intersect:
        common_dates = pd.DatetimeIndex([])
    else:
        common_dates = indices_to_intersect[0]
        for idx in indices_to_intersect[1:]:
            common_dates = common_dates.intersection(idx)

    dfs_to_concat = []
    if usd_tickers:
        dfs_to_concat.append(final_usd_df.loc[common_dates])
    if eur_tickers:
        dfs_to_concat.append(final_eur_df.loc[common_dates])

    if dfs_to_concat:
        prices_df = pd.concat(dfs_to_concat, axis=1)
    else:
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

    num_simulations = 50000
    scenario_return = []

    for _ in range(num_simulations):
        z_score = np.random.normal(0, 1)
        gain_loss = (portfolio_value * portfolio_expected_return * projected_days +
                     portfolio_value * portfolio_std_dev * z_score * np.sqrt(projected_days))
        scenario_return.append(gain_loss)

    var_value = -np.percentile(scenario_return, 100 * (1 - confidence_interval))

    return {
        "var": var_value,
        "scenario_return": scenario_return,
        "portfolio_value": portfolio_value,
        "has_positions": True,
    }
