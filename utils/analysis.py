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
def summary(brokers, data, save_path):
    print('\n  - Data di interesse GG-MM-AAAA ("t" per data odierna)')
    dt, ref_date = get_date()

    total_current_liq = []
    total_asset_value = []
    total_nav = []
    total_historic_liq = []
    total_pl = []
    total_pl_unrealized = []
    total_flows = []
    total_flows_dates = []
    first_dates = []
    positions_check = []

    for account in data:
        print(f"\n\n\nConto {account[0]}: {brokers[account[0]]} " + "="*70)

        df_copy = account[1].copy()
        positions = get_asset_value(df_copy, ref_date=ref_date)

        df_valid, first_date = get_pf_date(df_copy, dt, ref_date)

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
            positions_check.append("pass")
        else:
            print("\n    Non è stato possibile reperire alcuna posizione attiva.\n    Statistiche non calcolabili.")
        total_flows.append(flows)
        total_flows_dates.append(flows_dates)

        print(f"\n    NAV (al {dt}): {nav:.2f}€")
        print(f"\t- Liquidità: {current_liq:.2f}€")
        print(f"\t- Valore Titoli: {asset_value:.2f}€")
        print(f"    Liquidità Impegnata: {historic_liq:.2f}€")
        print(f"    P&L: {round_half_up(pl):.2f}€")
        print(f"    P&L comprendente il non realizzato: {round_half_up(pl_unrealized):.2f}€")
        print(f"    Rendimento totale (XIRR): {xirr_full:.2%}")
        print(f"    Rendimento annualizzato (XIRR): {xirr_ann:.2%}\n")

        total_current_liq.append(current_liq)
        total_asset_value.append(asset_value)
        total_nav.append(nav)
        total_historic_liq.append(historic_liq)
        total_pl.append(pl)
        total_pl_unrealized.append(pl_unrealized)
        if first_date is not None:
            first_dates.append(first_date)

        print(f"    Titoli detenuti in data {dt}:\n")
        if not positions:
            print("\t ---")
        else:
            for pos in positions:
                print(f"\t- {pos["ticker"]}    PMC: {pos["pmc"]:.4f}€    Prezzo attuale: {round_half_up(pos["price"], decimal="0.0001"):.4f}€    QT: {pos["quantity"]}    Controvalore: {round_half_up(pos["value"]):.2f}€")


    print("\n\n\nTotale Portafoglio " + "="*70)
    if first_dates:
        min_date = min(first_dates)
        pf_history = portfolio_history(min_date, ref_date, data)
    else:
        pf_history = pd.DataFrame([])
    xirr_total_full = np.nan
    xirr_total_ann = np.nan
    twrr_total = np.nan
    twrr_ann = np.nan
    volatility = np.nan
    sharpe_ratio = np.nan

    if positions_check: # if there is at least one active position across all accounts, proceed with statistics
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
        print("\n    Non è stato possibile reperire alcuna posizione attiva tra tutti i conti.\n    Statistiche non calcolabili.")  

# Display results ============================================================
    print(f"\n    NAV (al {dt}): {round_half_up(sum(total_nav)):.2f}€")
    print(f"\t- Liquidità: {round_half_up(sum(total_current_liq)):.2f}€")
    print(f"\t- Valore Titoli: {round_half_up(sum(total_asset_value)):.2f}€")
    print(f"    Liquidità Impegnata: {round_half_up(sum(total_historic_liq)):.2f}€\n")
    print(f"    P&L: {round_half_up(sum(total_pl)):.2f}€")
    print(f"    P&L comprendente il non realizzato: {round_half_up(sum(total_pl_unrealized)):.2f}€\n")
    print(f"    Rendimento")
    print(f"\t- XIRR totale: {xirr_total_full:.2%}")
    print(f"\t- XIRR annualizzato: {xirr_total_ann:.2%}")
    print(f"\t- TWRR totale: {twrr_total:.2%}")
    print(f"\t- TWRR annualizzato: {twrr_ann:.2%}\n")
    print(f"    Volatilità annualizzata: {volatility:.2%}")
    print(f"    Sharpe Ratio: {sharpe_ratio:.2f}\n")

    if not pf_history.empty:
        pf_history = pf_history.dropna()
        fig, ax = plt.subplots(figsize=(10, 8))
        ax.plot(pf_history["Date"], pf_history["NAV"], label="Valore portafoglio", color="blue", linestyle="-")
        ax.plot(pf_history["Date"], pf_history["Valore Titoli"], label='Valore titoli', color='red', linestyle='--')
        ax.plot(pf_history["Date"], pf_history["Liquidita"], label='Liquidità nel conto', color='darkgreen', linestyle='--')
        ax.plot(pf_history["Date"], pf_history["Liquidita Impegnata"], label='Liquidità impegnata', color='limegreen', linestyle=':')
        ax.set_xlabel("Data")
        ax.set_ylabel("Valore (€)")
        labels = ax.get_xticklabels() 
        ax.set_xticklabels(labels, rotation=45, ha='right')
        ax.legend()
        ax.grid(True, alpha=0.5)
        fig.tight_layout()
        fig.canvas.manager.set_window_title(f"Valore Portafoglio | Dal: {min_date.strftime("%d-%m-%Y")} | Al: {dt}")
        plt.show()

        rounding_dict = { "Liquidita":2, "Liquidita Impegnata":2, "Valore Titoli":2, "NAV":2, 
                         "Cash Flow":2, "TWRR Giornaliero":4, "TWRR Cumulativo":4 }
        pf_history = pf_history.round(rounding_dict)
        pf_history = pf_history.set_index("Date")
        pf_history.to_csv(save_path, date_format='%Y-%m-%d')
        print(f"\nEsportato storico del portafoglio in {save_path}\n")

    input("\nPremi Invio per continuare...")




#    6.2 - Correlazione
def correlation(data):
    # parse empty accounts:
    # remove rows with dividends, since there may be the (very unlikely) case where there is a report
    # with has a ticker which happens to only have dividends associated to it (and no buy/sell operation whatsoever)
    for account in data:
        account[1] = account[1][account[1]["Operazione"].isin(["Acquisto", "Vendita"])]

    print('  Definire il periodo di analisi interessato. Ad esempio, da inizio portafoglio ad oggi.\n  Formato: GG-MM-AAAA, "t" per data odierna.')
    print("  - Data inizio analisi:")
    start_dt, start_ref_date = get_date()
    print("  - Data fine analisi:")
    end_dt, end_ref_date = get_date()

    print(f"\n--- Correlazione semplice ---")

    _, active_tickers = get_tickers(data)
    if active_tickers:     # if you where able to retrieve active tickers:
        active_tickers = [t[0] for t in active_tickers]

        # Simple correlation between owned assets.
        active_tickers = list(set(active_tickers))
        prices_df = yf.download(active_tickers, start=start_ref_date, end=end_ref_date, progress=False)
        returns_df = prices_df["Close"].pct_change().dropna()
        correlation_matrix = returns_df.corr()
        print(correlation_matrix)
    else:                  # not enough data (empty account, no buy/sell operation)
        print("    Matrice di correlazione non calcolabile: non sono presenti asset in portafoglio.\n\n")

    # Rolling correlation. Not restricted to just owned assets;
    # If at least one of the input assets is not owned, download appropriate data.
    # Else reuse what was previously downloaded  
    print(f"\n--- Correlazione rolling tra due assets ---")
    print("Inserire ticker degli asset interessati. Non è necessario che essi siano detenuti nel portafoglio.\n")
    asset1 = input("  - Ticker asset 1\n    > ")
    asset2 = input("  - Ticker asset 2\n    > ")
    window = int(input("  - Finestra temporale in giorni. Si consiglia 100-150 per storici superiori a 2 anni, 20-60 altrimenti.\n    > "))
    
    if not(asset1 or asset2) in active_tickers:
        prices_df = yf.download([asset1, asset2], start=start_ref_date, end=end_ref_date, progress=False)
        returns_df = prices_df["Close"].pct_change().dropna()
    rolling_corr = returns_df[asset1].rolling(window=window).corr(returns_df[asset2])

    if active_tickers:
        # heatmap is drawn with matplotlib to avoid requiring seaborn just for this purpose
        fig1, ax1 = plt.subplots(figsize=(7, 6))
        cax = ax1.matshow(correlation_matrix, cmap='coolwarm', vmin=-1, vmax=1)
        fig1.colorbar(cax, label='Correlation')
        labels = correlation_matrix.columns
        ax1.set_xticks(np.arange(len(labels)))
        ax1.set_yticks(np.arange(len(labels)))
        ax1.set_xticklabels(labels)
        ax1.set_yticklabels(labels)
        # draw the numbers on the tiles:
        for i in range(len(labels)):
            for j in range(len(labels)):
                text = ax1.text(j, i, f'{correlation_matrix.iloc[i, j]:.3f}',
                            ha='center', va='center', color='black', fontsize=15)
        fig1.tight_layout()
        fig1.canvas.manager.set_window_title(f"Correlazione semplice | Dal: {start_dt} | Al: {end_dt}")

    fig2 = plt.figure(figsize=(8, 6))
    ax2 = rolling_corr.plot(title=f'Intervallo: {window}gg    Assets: {asset1}, {asset2}', legend=False, color='blue')
    ax2.axhline(0, color='red', linestyle='--', linewidth=0.8, label='Correlazione Zero')
    ax2.set_xlabel('Data')
    ax2.set_ylabel('Coefficiente di correlazione')
    ax2.grid(True, alpha=0.5)
    fig2.tight_layout()
    fig2.canvas.manager.set_window_title(f"Correlazione rolling | Dal: {start_dt} | Al: {end_dt}")
    plt.show()

    input("\nPremi Invio per continuare...")

#    6.3 - Drawdown
def drawdown(data):

    data = [account for account in data if len(account[1]) > 1]

    print('  Definire il periodo di analisi interessato. Ad esempio, da inizio portafoglio ad oggi.\n  Formato: GG-MM-AAAA, "t" per data odierna.')
    print("  - Data inizio analisi:")
    start_dt, start_ref_date = get_date()
    print("  - Data fine analisi:")
    end_dt, end_ref_date = get_date()

    if data:
        pf_history = portfolio_history(start_ref_date, end_ref_date, data)
        pf_history = pf_history.dropna()
        running_max = pf_history["NAV"].expanding().max()
        drawdown = (pf_history["NAV"] - running_max) / running_max
        mdd = drawdown.min()
        print(f"\n    Maximum Drawdown del portafoglio tra il {start_dt} ed il {end_dt}: {mdd * 100:.2f}%")

        fig, ax = plt.subplots(figsize=(10, 8))
        ax.plot(pf_history["Date"], (drawdown * 100), color="red", linestyle="-")
        ax.axhline(mdd * 100, color='blue', linestyle='--', linewidth=2, label=f'Maximum Drawdown: {mdd * 100:.2f}%')
        ax.set_xlabel("Data")
        ax.set_ylabel("Drawdown (%)")
        ax.set_ylim(bottom=mdd*100 -2.5, top=2.5)
        labels = ax.get_xticklabels() 
        ax.set_xticklabels(labels, rotation=45, ha='right')
        ax.legend()
        ax.grid(True, alpha=0.5)
        fig.tight_layout()
        fig.canvas.manager.set_window_title(f"Drawdown Portafoglio | Dal: {start_dt} | Al: {end_dt}")
        plt.show()
    else:
        print("\n    Nessun dato presente nello storico delle transazioni, tra tutti i conti.\n    Drawdown non calcolabile.")  
    input("\nPremi Invio per continuare...")


def var_mc(data):

    # SEE IF YOU CAN OPTIMIZE ACTIVE POSITION FETCHING LOGIC
    # there must be some positions currently opened
    data = [account for account in data if account[1]["Valore Titoli"].iloc[-1] > 0.0]

    if data:    
        start_ref_date = "2010-01-01"
        try:
            confidence_interval = float(input("  - Intervallo di Confidenza (es. 0.99)\n    > "))
            if confidence_interval <= 0.0 or confidence_interval >= 1.0:
                raise ValueError
        except ValueError:
            wrong_input("L'Intervallo di Confidenza è definito tra 0 ed 1, estremi esclusi.") 
        
        try:
            projected_days = int(input("  - Numero di giorni interessati. Più questo numero è alto, meno attendibili saranno i risultati.\n    > "))
            if projected_days <= 0:
                raise ValueError
        except ValueError:
            wrong_input("Il numero di giorni per la previsione deve essere un numero intero maggiore di 0")
        end_dt = datetime.now()

        _, total_tickers = get_tickers(data)
        usd_tickers = [t[0] for t in total_tickers if t[1] == "USD"]
        eur_tickers = [t[0] for t in total_tickers if t[1] == "EUR"]

        total_positions = []
        total_liquidity = []

        # get for date end_dt: total positions held across accounts, total liquidity 
        print("\n    Aggiornamento dei titoli in possesso da Yahoo Finance...")
        for account in data:
            df_copy = account[1].copy()
            positions = get_asset_value(df_copy, ref_date=end_dt, suppress_progress=True)
            total_positions.extend(positions)

            df_valid, _ = get_pf_date(df_copy, end_dt, end_dt)
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
        

        print("    Scaricamento dei dati storici da Yahoo Finance...")

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
            print("    Nessun ticker da scaricare.")
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
                print("    Nessun dato scaricato da Yahoo Finance.")
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

            prices_df.to_csv("/home/atonello/Downloads/prices_df1.csv")



            prices_df = prices_df[asset_tickers]
            prices_df.to_csv("/home/atonello/Downloads/prices_df2.csv")

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
            
            """def expected_return(weights, log_returns):
                return np.sum(log_returns.mean()*weights)"""

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
            print(f"\n    Value at Risk del portafoglio al {confidence_interval:.0%} IdC su {projected_days} giorni:    {VaR:.2f}€")

            fig, ax = plt.subplots(figsize=(8, 6))
            ax.hist(scenarioReturn, bins=100, density=True, color="lightgray")
            ax.set_xlabel("Gain/Loss (€)")
            ax.set_ylabel("Densità")
            ax.axvline(-VaR, color='r', linestyle='dashed', linewidth=2, label=f'VaR al {confidence_interval:.0%} IdC: {VaR:.2f}€')
            ax.legend()
            fig.tight_layout()
            fig.canvas.manager.set_window_title(f"Distribuzione del Portfolio Gain/Loss su {projected_days} giorni")
            plt.show()
    else:
        print("    Non è stata trovata alcuna posizione aperta tra tutti i conti.\n    Value at Risk nullo.")

    input("\nPremi Invio per continuare...")