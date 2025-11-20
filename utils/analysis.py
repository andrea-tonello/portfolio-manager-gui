import pandas as pd
import numpy as np
from datetime import datetime
import yfinance as yf
import matplotlib.pyplot as plt
from itertools import chain

from utils.date_utils import get_date, get_pf_date
from utils.account import portfolio_history, get_asset_value, get_tickers, aggregate_positions
from utils.other_utils import round_half_up, wrong_input
import utils.newton as newton


def xirr(cash_flows, flows_dates, annualization=365, x0=0.1, x1=0.2, max_iter=100):
    """
    **Given**:
    - *list* of float `cash_flows`: list of ordered cash flows (deposits (-), withdrawals (+)). The first transaction is the initial investment (-); 
    the final transaction corresponds to total liquidation (+)
    - *list* of dates `flows_dates`: list of ordered date objects relative to the cash flows. 
    - *int* `annualization = 365`: time period of interest; default is 365 since we often want annualized returns
    - *float* `guess = 0.1`: initial guess for the Newton method

    **Returns**:
    - *float* `xirr_rate`: XIRR value if convergence is reached, else NaN
    """
    days = [(data - flows_dates[0]).days for data in flows_dates]
    years = np.array(days) / annualization

    # The goal is to find the rate which brings this function (Net Present Value) to 0 using Newton method.
    def npv_formula(rate):
        return sum(
            cf / (1 + rate)**t
            for cf, t in zip(cash_flows, years)
        )
    try:
        xirr_rate = newton.secant(npv_formula, x0=x0, x1=x1, max_iter=max_iter)
        return xirr_rate
    except ZeroDivisionError:
        print("ERRORE: Denominator is zero. Secant method fails.")
    except RuntimeError:
        print(f"ERRORE: Non è stata raggiunta la convergenza nel calcolo dello XIRR dopo {max_iter} iterazioni.")
    return np.nan


# 6 - ANALISI PORTAFOGLIO
#    6.1 - Resoconto
def summary(translator, brokers, data, save_path):
    print(translator.get("analysis.summary.date"))
    dt, ref_date = get_date(translator=translator)

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

    for account in data:
        print("\n\n\n"+ translator.get("analysis.summary.account_literal") + f" {account[0]}: {brokers[account[0]]} " + "="*70)

        df_copy = account[1].copy()
        positions = get_asset_value(translator, df_copy, ref_date=ref_date)

        df_valid, first_date = get_pf_date(translator, df_copy, dt, ref_date)

        current_liq = round_half_up(float(df_valid.iloc[-1]["Liquidita Attuale"]))
        historic_liq = df_valid["Liq. Impegnata"].iloc[-1]
        asset_value = 0.0
        pl = df_valid["P&L"].sum()
        pl_unrealized = 0.0
        nav = current_liq

        # cash flows (they must have swapped values)
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
            flows = flows[:-1]  # remove "wrong" nav
            nav = nav + round_half_up(asset_value)
            flows.append(nav)   # add updated nav
            xirr_full = xirr(flows, flows_dates, annualization=(ref_date-flows_dates[0]).days)
            xirr_ann = xirr(flows, flows_dates)
            accounts_with_positions += 1
        else:
            print(translator.get("analysis.summary.no_active_pos"))
        total_flows.append(flows)
        total_flows_dates.append(flows_dates)

        print(translator.get("analysis.summary.nav", dt=dt, nav=nav))
        print(translator.get("analysis.summary.cash", current_liq=current_liq))
        print(translator.get("analysis.summary.assets_value", asset_value=asset_value))
        print(translator.get("analysis.summary.historic_cash", historic_liq=historic_liq))
        print(translator.get("analysis.summary.pl", pl=round_half_up(pl)))
        print(translator.get("analysis.summary.pl_unrealized", pl_unrealized=round_half_up(pl_unrealized)))
        print(translator.get("analysis.summary.return_account", xirr_full=xirr_full, xirr_ann=xirr_ann))

        total_current_liq.append(current_liq)
        total_asset_value.append(asset_value)
        total_nav.append(nav)
        total_historic_liq.append(historic_liq)
        total_pl.append(pl)
        total_pl_unrealized.append(pl_unrealized)
        if first_date is not None:
            first_dates.append(first_date)

        print(translator.get("analysis.summary.assets_recap.held_assets", dt=dt))
        if not positions:
            print("\t ---")
        else:
            for pos in positions:
                print(f"\t- {pos["ticker"]}" + translator.get("analysis.summary.assets_recap.avg_price") + f"{pos["pmc"]:.4f}€" + translator.get("analysis.summary.assets_recap.current_price") + f"{round_half_up(pos["price"], decimal="0.0001"):.4f}€    QT: {pos["quantity"]}" + translator.get("analysis.summary.assets_recap.value") + f"{round_half_up(pos["value"]):.2f}€")

    print("\n\n\n" + translator.get("analysis.summary.portfolio_literal") + "="*70)
    if first_dates:
        min_date = min(first_dates)
        pf_history = portfolio_history(translator, min_date, ref_date, data)
    else:
        pf_history = pd.DataFrame([])
    xirr_total_full = np.nan
    xirr_total_ann = np.nan
    twrr_total = np.nan
    twrr_ann = np.nan
    volatility = np.nan
    sharpe_ratio = np.nan

    if accounts_with_positions > 0: # if there is at least one active position across all accounts, proceed with statistics
    # XIRR ========================================================================
        combined_flows = list(
            chain.from_iterable(
                zip(dates, flows) for dates, flows in zip(total_flows_dates, total_flows)
            )
        )
        # Sort by date
        combined_flows.sort(key=lambda x: x[0])
        all_dates, all_flows = zip(*combined_flows)
        # Convert to lists (optional)
        all_dates = list(all_dates)
        all_flows = list(all_flows)
        days_xirr = (ref_date-all_dates[0]).days
        xirr_total_full = xirr(all_flows, all_dates, annualization=days_xirr)
        xirr_total_ann = xirr(all_flows, all_dates)

    # TWR ========================================================================
        trading_days = 252
        days_twrr = len(pf_history)
        twrr_total = pf_history["TWRR Cumulativo"].iloc[-1]
        twrr_ann = (1 + twrr_total)**(trading_days / days_twrr) - 1

    # Sharpe ratio (with TWRR) ====================================================
        risk_free_rate = 0.02
        risk_free_daily = (1 + risk_free_rate)**(1/trading_days) - 1          # Convert annual risk-free rate to daily
        excess_returns = pf_history["TWRR Giornaliero"] - risk_free_daily
        sharpe_ratio = np.sqrt(trading_days) * (excess_returns.mean() / excess_returns.std())

        # Note: this is the volatility of the returns. The denominator of the sharpe ratio is instead the volatility of excess return (i.e. returns - risk free rate)
        volatility = pf_history["TWRR Giornaliero"].std() * np.sqrt(trading_days)  
    else:
        print(translator.get("analysis.summary.no_active_pos"))  

# Display results ============================================================
    print(translator.get("analysis.summary.nav", dt=dt, nav=round_half_up(sum(total_nav))))
    print(translator.get("analysis.summary.cash", current_liq=round_half_up(sum(total_current_liq))))
    print(translator.get("analysis.summary.assets_value", asset_value=round_half_up(sum(total_asset_value))))
    print(translator.get("analysis.summary.historic_cash", historic_liq=round_half_up(sum(total_historic_liq))))
    print(translator.get("analysis.summary.pl", pl=round_half_up(sum(total_pl))))
    print(translator.get("analysis.summary.pl_unrealized", pl_unrealized=round_half_up(sum(total_pl_unrealized))))
    print(translator.get("analysis.summary.return_portfolio", xirr_full=xirr_total_full, xirr_ann=xirr_total_ann, twrr_full=twrr_total, twrr_ann=twrr_ann))
    print(translator.get("analysis.summary.volatility", volatility=volatility))
    print(translator.get("analysis.summary.sharpe_ratio", sharpe_ratio=sharpe_ratio))

    if not pf_history.empty:
        pf_history = pf_history.dropna()
        fig, ax = plt.subplots(figsize=(10, 8))
        ax.plot(pf_history["Date"], pf_history["NAV"], label="Valore portafoglio", color="blue", linestyle="-")
        ax.plot(pf_history["Date"], pf_history["Valore Titoli"], label='Valore titoli', color='red', linestyle='--')
        ax.plot(pf_history["Date"], pf_history["Liquidita"], label='Liquidità nel conto', color='darkgreen', linestyle='--')
        ax.plot(pf_history["Date"], pf_history["Liquidita Impegnata"], label='Liquidità impegnata', color='limegreen', linestyle=':')
        ax.set_xlabel(translator.get("analysis.summary.plot1.xlabel"))
        ax.set_ylabel(translator.get("analysis.summary.plot1.ylabel"))
        labels = ax.get_xticklabels() 
        ax.set_xticklabels(labels, rotation=45, ha='right')
        ax.legend()
        ax.grid(True, alpha=0.5)
        fig.tight_layout()
        fig.canvas.manager.set_window_title(translator.get("analysis.summary.plot1.window_title", min_date=min_date.strftime("%d-%m-%Y"), dt=dt))
        plt.show()

        rounding_dict = { "Liquidita":2, "Liquidita Impegnata":2, "Valore Titoli":2, "NAV":2, 
                         "Cash Flow":2, "TWRR Giornaliero":4, "TWRR Cumulativo":4 }
        pf_history = pf_history.round(rounding_dict)
        pf_history = pf_history.set_index("Date")
        pf_history.to_csv(save_path, date_format='%Y-%m-%d')
        print(translator.get("analysis.summary.exported", save_path=save_path))



#    6.2 - Correlazione
def correlation(translator, data):
    # parse empty accounts:
    # remove rows with dividends, since there may be the (very unlikely) case where there is a report
    # with has a ticker which happens to only have dividends associated to it (and no buy/sell operation whatsoever)
    for account in data:
        account[1] = account[1][account[1]["Operazione"].isin(["Acquisto", "Vendita"])]

    print(translator.get("analysis.corr.date"))
    print(translator.get("analysis.corr.start_dt"))
    start_dt, start_ref_date = get_date(translator=translator)
    print(translator.get("analysis.corr.end_dt"))
    end_dt, end_ref_date = get_date(translator=translator)

    print(translator.get("analysis.corr.simple"))

    _, active_tickers = get_tickers(translator, data)
    if active_tickers:     # if you where able to retrieve active tickers:
        active_tickers = [t[0] for t in active_tickers]

        # Simple correlation between owned assets.
        active_tickers = list(set(active_tickers))
        prices_df = yf.download(active_tickers, start=start_ref_date, end=end_ref_date, progress=False)
        returns_df = prices_df["Close"].pct_change().dropna()
        correlation_matrix = returns_df.corr()
        print()
        print(correlation_matrix)
        print("\n")
    else:                  # not enough data (empty account, no buy/sell operation)
        print(translator.get("analysis.corr.simple_error"))

    # Rolling correlation. Not restricted to just owned assets;
    # If at least one of the input assets is not owned, download appropriate data.
    # Else reuse what was previously downloaded  
    print(translator.get("analysis.corr.rolling"))
    asset1 = input(translator.get("analysis.corr.asset1"))
    asset2 = input(translator.get("analysis.corr.asset2"))
    try: 
        window = int(input(translator.get("analysis.corr.window")))
        if window <= 0:
            raise ValueError
    except ValueError:
        wrong_input(translator, translator.get("analysis.corr.window_error"))

    if not(asset1 or asset2) in active_tickers:
        prices_df = yf.download([asset1, asset2], start=start_ref_date, end=end_ref_date, progress=False)
        returns_df = prices_df["Close"].pct_change().dropna()
    rolling_corr = returns_df[asset1].rolling(window=window).corr(returns_df[asset2])

    if active_tickers:
        # heatmap is drawn with matplotlib to avoid requiring seaborn just for this purpose
        fig1, ax1 = plt.subplots(figsize=(7, 6))
        cax = ax1.matshow(correlation_matrix, cmap="coolwarm", vmin=-1, vmax=1)
        fig1.colorbar(cax, label=translator.get("analysis.corr.plot1.colorbar"))
        labels = correlation_matrix.columns
        ax1.set_xticks(np.arange(len(labels)))
        ax1.set_yticks(np.arange(len(labels)))
        ax1.set_xticklabels(labels)
        ax1.set_yticklabels(labels)
        # draw the numbers on the tiles:
        for i in range(len(labels)):
            for j in range(len(labels)):
                text = ax1.text(j, i, f"{correlation_matrix.iloc[i, j]:.3f}",
                            ha="center", va="center", color="black", fontsize=15)
        fig1.tight_layout()
        fig1.canvas.manager.set_window_title(translator.get("analysis.corr.plot1.window_title", start_dt=start_dt, end_dt=end_dt))

    fig2 = plt.figure(figsize=(8, 6))
    ax2 = rolling_corr.plot(title=translator.get("analysis.corr.plot2.title", window=window, asset1=asset1, asset2=asset2), legend=False, color="blue")
    ax2.axhline(0, color="red", linestyle="--", linewidth=0.8)
    ax2.set_xlabel(translator.get("analysis.corr.plot2.xlabel"))
    ax2.set_ylabel(translator.get("analysis.corr.plot2.ylabel"))
    ax2.grid(True, alpha=0.5)
    fig2.tight_layout()
    fig2.canvas.manager.set_window_title(translator.get("analysis.corr.plot2.window_title", start_dt=end_dt, end_dt=end_dt))
    plt.show()


#    6.3 - Drawdown
def drawdown(translator, data):
    data = [account for account in data if len(account[1]) > 1]

    print(translator.get("analysis.drawdown.date"))
    print(translator.get("analysis.drawdown.start_dt"))
    start_dt, start_ref_date = get_date(translator=translator)
    print(translator.get("analysis.drawdown.end_dt"))
    end_dt, end_ref_date = get_date(translator=translator)

    if data:
        pf_history = portfolio_history(translator, start_ref_date, end_ref_date, data)
        pf_history = pf_history.dropna()
        running_max = pf_history["NAV"].expanding().max()
        drawdown = (pf_history["NAV"] - running_max) / running_max
        mdd = drawdown.min()
        print(translator.get("analysis.drawdown.result", start_dt=start_dt, end_dt=end_dt, mdd=mdd*100))

        fig, ax = plt.subplots(figsize=(10, 8))
        ax.plot(pf_history["Date"], (drawdown * 100), color="black", linestyle="-")
        ax.axhline(mdd * 100, color="red", linestyle="--", linewidth=2, label=translator.get("analysis.drawdown.plot1.legend", mdd=mdd*100))
        ax.set_xlabel(translator.get("analysis.drawdown.plot1.xlabel"))
        ax.set_ylabel("Drawdown (%)")
        ax.set_ylim(bottom=mdd*100 -2.5, top=2.5)
        labels = ax.get_xticklabels() 
        ax.set_xticklabels(labels, rotation=45, ha="right")
        ax.legend()
        ax.grid(True, alpha=0.5)
        fig.tight_layout()
        fig.canvas.manager.set_window_title(translator.get("analysis.drawdown.plot1.window_title", start_dt=start_dt, end_dt=end_dt))
        plt.show()
    else:
        print(translator.get("analysis.drawdown.error"))  
        


def var_mc(translator, data):
    # SEE IF YOU CAN OPTIMIZE ACTIVE POSITION FETCHING LOGIC
    # there must be some positions currently opened
    data = [account for account in data if account[1]["Valore Titoli"].iloc[-1] > 0.0]

    if data:    
        start_ref_date = "2010-01-01"
        try:
            confidence_interval = float(input(translator.get("analysis.var.ci")))
            if confidence_interval <= 0.0 or confidence_interval >= 1.0:
                raise ValueError
        except ValueError:
            wrong_input(translator, translator.get("analysis.var.ci_error")) 
        
        try:
            projected_days = int(input(translator.get("analysis.var.days")))
            if projected_days <= 0:
                raise ValueError
        except ValueError:
            wrong_input(translator, translator.get("analysis.var.days_error"))
        end_dt = datetime.now()

        _, total_tickers = get_tickers(translator, data)
        usd_tickers = [t[0] for t in total_tickers if t[1] == "USD"]
        eur_tickers = [t[0] for t in total_tickers if t[1] == "EUR"]

        total_positions = []
        total_liquidity = []

        # get for date end_dt: total positions held across accounts, total liquidity 
        print(translator.get("yf.download_current"))
        for account in data:
            df_copy = account[1].copy()
            positions = get_asset_value(translator, df_copy, ref_date=end_dt, suppress_progress=True)
            total_positions.extend(positions)

            df_valid, _ = get_pf_date(translator, df_copy, end_dt, end_dt)
            current_liq = round_half_up(float(df_valid.iloc[-1]["Liquidita Attuale"]))
            total_liquidity.append(current_liq)

        # weights for active positions and cash
        aggr_positions = aggregate_positions(total_positions)  # only opened positions at current time
        assets_value = [pos["value"] for pos in aggr_positions]
        asset_tickers = [pos["ticker"] for pos in aggr_positions]

        cash = sum(total_liquidity)
        portfolio_value = sum(assets_value)
        weights = assets_value / portfolio_value
        portfolio_value = portfolio_value + cash
        
        print(translator.get("yf.download_historic_generic"))
        # 1. Costruisci un'unica lista di tutti i ticker necessari
        tickers_to_download = []
        if usd_tickers:
            tickers_to_download.extend(usd_tickers)
        if eur_tickers:
            tickers_to_download.extend(eur_tickers)

        # 2. Aggiungi il tasso di cambio se *qualsiasi* ticker è presente
        if tickers_to_download:
            tickers_to_download.append("USDEUR=X")
        else:
            print("    " + translator.get("yf.no_tickers"))
            prices_df = pd.DataFrame([])

        # 3. Esegui UNA SOLA chiamata di download (solo se necessario)
        if tickers_to_download:
            all_data = yf.download(
                tickers_to_download, 
                start=start_ref_date, 
                end=end_dt, 
                progress=False
            )
            # Gestione del caso in cui yf restituisce dati None/vuoti
            if all_data.empty:
                print(translator.get("yf.error_empty_df"))
                prices_df = pd.DataFrame([])
            else:
                # 4. Estrai i prezzi 'Close'
                if len(tickers_to_download) > 1:
                    close_prices = all_data["Close"]
                else:
                    # Uniforma l'output a DataFrame se c'è un solo ticker
                    close_prices = all_data["Close"].to_frame(name=tickers_to_download[0])

                # 5. Prepara i DataFrame e calcola le date comuni
                final_usd_df = pd.DataFrame([])
                final_eur_df = pd.DataFrame([])
                indices_to_intersect = []

                # Estrai exch_df per primo, dato che è necessario per tutti i casi
                exch_df = close_prices["USDEUR=X"].dropna()
                indices_to_intersect.append(exch_df.index)

                if eur_tickers:
                    # Estrai i prezzi EUR e rimuovi i giorni in cui *nessun* ticker EUR aveva dati
                    eur_prices_df = close_prices[eur_tickers].dropna(how='all')
                    indices_to_intersect.append(eur_prices_df.index)
                    final_eur_df = eur_prices_df

                if usd_tickers:
                    # Estrai i prezzi USD
                    usd_prices_df = close_prices[usd_tickers].dropna(how='all')
                    indices_to_intersect.append(usd_prices_df.index)
                    
                    # Converti i prezzi USD in EUR. .mul() allinea automaticamente gli indici
                    final_usd_df = usd_prices_df.mul(exch_df, axis=0)

                # 6. Calcola le date comuni
                if not indices_to_intersect:
                    common_dates = pd.DatetimeIndex([])
                else:
                    common_dates = indices_to_intersect[0]
                    for idx in indices_to_intersect[1:]:
                        common_dates = common_dates.intersection(idx)
                
                # 7. Costruisci la lista di DataFrame da concatenare *condizionalmente*
                dfs_to_concat = []
                if usd_tickers:
                    # Filtra solo se il DataFrame non è vuoto
                    dfs_to_concat.append(final_usd_df.loc[common_dates])
                if eur_tickers:
                    # Filtra solo se il DataFrame non è vuoto
                    dfs_to_concat.append(final_eur_df.loc[common_dates])

                # 8. Concatena i risultati
                if dfs_to_concat:
                    prices_df = pd.concat(dfs_to_concat, axis=1)
                else:
                    prices_df = pd.DataFrame([])

            prices_df = prices_df[asset_tickers]
            log_returns = np.log(prices_df/prices_df.shift(1))
            log_returns = log_returns.dropna()

            # strong assumption: expected returns are based on historical data
            def expected_return(tickers, log_returns, weights):
                means = []
                for ticker, weight in zip(tickers, weights):
                    ticker_df = log_returns[ticker].copy()
                    ticker_df = ticker_df.dropna()
                    ticker_mean = ticker_df.mean() * weight
                    means.append(ticker_mean)
                return np.sum(means)

            def standard_deviation (cov_matrix, weights):
                variance = weights.T @ cov_matrix @ weights
                return np.sqrt(variance)
            
            cov_matrix = log_returns.cov()
            portfolio_expected_return = expected_return(asset_tickers, log_returns, weights)
            portfolio_std_dev = standard_deviation (cov_matrix, weights)

            def random_z_score():
                return np.random.normal(0, 1)

            def scenario_gain_loss(portfolio_value, portfolio_expected_return, portfolio_std_dev, z_score, days):
                return portfolio_value * portfolio_expected_return * days + (portfolio_value * portfolio_std_dev * z_score * np.sqrt(days))
            
            num_simulations = 50000
            scenarioReturn = []

            for _ in range(num_simulations):
                z_score = random_z_score()
                scenarioReturn.append(scenario_gain_loss(portfolio_value, portfolio_expected_return, portfolio_std_dev, z_score, projected_days))

            VaR = -np.percentile(scenarioReturn, 100 * (1 - confidence_interval))
            print(translator.get("analysis.var.result", ci=confidence_interval, days=projected_days, var=VaR))

            fig, ax = plt.subplots(figsize=(8, 6))
            ax.hist(scenarioReturn, bins=100, density=True, color="lightgray")
            ax.set_xlabel(translator.get("analysis.var.plot1.xlabel"))
            ax.set_ylabel(translator.get("analysis.var.plot1.ylabel"))
            ax.axvline(-VaR, color="red", linestyle="dashed", linewidth=2, label=translator.get("analysis.var.plot1.legend", ci=confidence_interval, var=VaR))
            ax.legend()
            fig.tight_layout()
            fig.canvas.manager.set_window_title(translator.get("analysis.var.plot1.window_title", days=projected_days))
            plt.show()
    else:
        print(translator.get("analysis.var.error"))