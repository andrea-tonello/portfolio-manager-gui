import pandas as pd
import numpy as np
from datetime import datetime, date
import json
import os
import yfinance as yf
import seaborn as sns
import matplotlib.pyplot as plt
from itertools import chain
#from scipy.stats import norm

from newrow import newrow_cash, newrow_etf_stock
from utils.operations_account import portfolio_history, get_asset_value, get_tickers, aggregate_positions
from utils.date_utils import get_date, get_pf_date
from utils.fetch_utils import fetch_name    
from utils.other_utils import round_half_up, wrong_input, xirr


# 1 - LIQUIDITÀ
def cashop(df, dt, broker):
    cash = float(input("  - Ammontare operazione in EUR (negativo se prelievo) > "))
    if cash == 0:
        raise ValueError("Il contante inserito non può essere 0€.\nPositivo se depositato, negativo se prelevato.")
    op_type = "Deposito" if cash > 0 else "Prelievo"

    df = newrow_cash(df, dt, broker, cash, op_type, "Contanti", np.nan, np.nan)
    print()
    print(df.tail(10))
    input("\nPremi Invio per continuare...")
    return df

def dividend(df, dt, broker):
    cash = float(input("  - Dividendo in EUR al netto di tasse > "))
    if cash <= 0.0:
        raise ValueError("Il dividendo non può essere <= 0€")
    ticker = input("  - Ticker completo dell'emittente dividendo > ")
    name = fetch_name(ticker)

    df = newrow_cash(df, dt, broker, cash, "Dividendo", "Dividendo", ticker, name)
    print()
    print(df.tail(10))
    input("\nPremi Invio per continuare...")
    return df

def charge(df, dt, broker):
    cash = float(input("  - Ammontare imposta in EUR > "))
    if cash <= 0.0:
        raise ValueError("L'imposta è da intendersi > 0.")
    descr = str(input('  - Descrizione imposta (es. "Bollo Q2 2025") > '))

    df = newrow_cash(df, dt, broker, -cash, "Imposta", descr, np.nan, np.nan)
    print()
    print(df.tail(10))
    input("\nPremi Invio per continuare...")
    return df



# 2,3 - ETF, STOCK
def etf_stock(df, broker, choice="ETF"):
    
    dt = get_date(df)

    print("  - Valuta\n\t1. EUR\n\t2. USD")
    currency = input("    > ")
    try:
        currency = int(currency)
        if currency not in [1, 2]:
            raise ValueError
    except ValueError:
        wrong_input()
    
    conv_rate = 1.0
    if currency == 2:
        conv_rate = float(input("  - Tasso di conversione EUR-USD > "))
    conv_rate = round_half_up(1.0 / conv_rate, decimal="0.000001")

    ticker = input("  - Ticker completo (standard Yahoo Finance) > ")

    qt = input("  - Quantità (intero positivo) > ")
    if not (qt.isdigit() and int(qt) > 0):
        raise ValueError("Quantità non valida. Deve essere un intero positivo.")
    else:
        quantity = int(qt)

    price = float(input("  - Prezzo unitario (negativo se acquisto) > "))
    if price == 0:
        raise ValueError("Il prezzo non può essere 0€.\nNegativo se acquisto, positivo se vendita.")

    print("  - Valuta commissione")
    print("    È necessario specificarla in quanto, ad esempio, Fineco (conto Trading) applica fees fisse in EUR anche su operazioni in USD.")
    print("\t1. EUR\n\t2. USD")
    currency_fee = input("    > ")
    try:
        currency_fee = int(currency_fee)
        if currency_fee not in [1, 2]:
            raise ValueError
    except ValueError:
        wrong_input()

    fee = float(input("  - Commissione > "))
    if currency_fee == 2:
        fee = round_half_up(fee / conv_rate, decimal="0.000001")

    buy = price < 0
    
    ter = np.nan
    if choice == "ETF":
        ter = input("  - Total Expense Ratio > ")
        ter += "%"

    df = newrow_etf_stock(df, dt, broker, "EUR" if currency==1 else "USD", choice, ticker, quantity, price, conv_rate, ter, fee, buy)
    print()
    print(df.tail(10))
    input("\nPremi Invio per continuare...")
    return df



# 6 - ANALISI PORTAFOGLIO
#    6.1 - Resoconto
def summary(df, brokers, data, save_folder):

    dt = get_date(df, sequential_only=False)
    ref_date= datetime.strptime(dt, "%d-%m-%Y")

    total_current_liq = []
    total_asset_value = []
    total_nav = []
    total_historic_liq = []
    total_pl = []
    total_pl_unrealized = []
    total_flussi = []
    total_date_flussi = []
    first_dates = []

    for account in data:
        print(f"\n\n\nConto {account[0]}: {brokers[account[0]]} " + "="*70)

        df_copy = account[1].copy()
        positions = get_asset_value(df_copy, ref_date=ref_date)

        df_valid, first_date = get_pf_date(df_copy, dt, ref_date)

        current_liq = round_half_up(float(df_valid.iloc[-1]["Liquidita Attuale"]))
        asset_value = round_half_up(sum(pos["value"] for pos in positions))
        nav = round_half_up(current_liq + asset_value)
        historic_liq = df_valid["Liq. Storica Immessa"].iloc[-1]
        pl = df_valid["P&L"].sum()
        pl_unrealized = pl + sum([pos["value"] - pos["pmc"] * pos["quantity"] for pos in positions])

        # flussi di cassa (devono avere valore swappato)
        cashflow_df = df_valid[df_valid["Operazione"].isin(["Deposito", "Prelievo"])]
        flussi = (cashflow_df["Imp. Effettivo Operaz."] * -1).tolist()
        flussi.append(nav)
        date_flussi = cashflow_df["Data"].tolist()
        date_flussi.append(ref_date)
        xirr_full = xirr(flussi, date_flussi, annualization=(ref_date-date_flussi[0]).days)
        xirr_ann = xirr(flussi, date_flussi)

        print(f"\n    NAV (al {dt}): {nav}€")
        print(f"\t- Liquidità: {current_liq}€")
        print(f"\t- Valore Titoli: {asset_value}€")
        print(f"    Liquidità Impegnata: {historic_liq}€")
        print(f"    P&L: {round_half_up(pl)}€")
        print(f"    P&L comprendente il non realizzato: {round_half_up(pl_unrealized)}€")
        print(f"    Rendimento totale (XIRR): {xirr_full:.2%}")
        print(f"    Rendimento annualizzato (XIRR): {xirr_ann:.2%}\n")

        total_current_liq.append(current_liq)
        total_asset_value.append(asset_value)
        total_nav.append(nav)
        total_historic_liq.append(historic_liq)
        total_pl.append(pl)
        total_pl_unrealized.append(pl_unrealized)
        total_flussi.append(flussi)
        total_date_flussi.append(date_flussi)
        first_dates.append(first_date)

        print(f"    Titoli detenuti in data {dt}:\n")
        if len(positions) == 0:
            print("\t ---")
        else:
            for pos in positions:
                print(f"\t- {pos["ticker"]}    PMC: {pos["pmc"]}€    Prezzo attuale: {round_half_up(pos["price"], decimal="0.0001")}€    QT: {pos["quantity"]}    Controvalore: {round_half_up(pos["value"])}€")

# XIRR ========================================================================
    combined_flussi = list(
        chain.from_iterable(
            zip(dates, flussi) for dates, flussi in zip(total_date_flussi, total_flussi)
        )
    )
    # Sort by date
    combined_flussi.sort(key=lambda x: x[0])
    all_dates, all_flussi = zip(*combined_flussi)
    # Convert to lists (optional)
    all_dates = list(all_dates)
    all_flussi = list(all_flussi)
    days_xirr = (ref_date-all_dates[0]).days
    xirr_total_full = xirr(all_flussi, all_dates, annualization=days_xirr)
    xirr_total_ann = xirr(all_flussi, all_dates)

# TWR ========================================================================
    print("\n\n\nTotale Portafoglio " + "="*70)
    min_date = min(first_dates)
    pf_history = portfolio_history(min_date, ref_date, data)
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

# Display results ============================================================
    pf_history = pf_history.dropna()
    print(f"\n    NAV (al {dt}): {round_half_up(sum(total_nav))}€")
    print(f"\t- Liquidità: {round_half_up(sum(total_current_liq))}€")
    print(f"\t- Valore Titoli: {round_half_up(sum(total_asset_value))}€")
    print(f"    Liquidità Impegnata: {round_half_up(sum(total_historic_liq))}€\n")
    print(f"    P&L: {round_half_up(sum(total_pl))}€")
    print(f"    P&L comprendente il non realizzato: {round_half_up(sum(total_pl_unrealized))}€\n")
    print(f"    Rendimento")
    print(f"\t- XIRR totale: {xirr_total_full:.2%}")
    print(f"\t- XIRR annualizzato: {xirr_total_ann:.2%}")
    print(f"\t- TWRR totale: {twrr_total:.2%}")
    print(f"\t- TWRR annualizzato: {twrr_ann:.2%}\n")
    print(f"    Volatilità annualizzata: {volatility:.2%}")
    print(f"    Sharpe Ratio: {sharpe_ratio:.2f}\n")

    filename = "Storico Portafoglio.csv"
    save_path = os.path.join(save_folder, filename)
    pf_history.to_csv(save_path)
    print(f"\nEsportato {filename} in {save_path}\n")

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
    input("\nPremi Invio per continuare...")

#    6.2 - Correlazione
def correlation(df, data):

    print("  Data inizio analisi:")
    start_dt = get_date(df, sequential_only=False)
    start_ref_date = datetime.strptime(start_dt, "%d-%m-%Y")
    print("  Data fine analisi:")
    end_dt = get_date(df, sequential_only=False)
    end_ref_date = datetime.strptime(end_dt, "%d-%m-%Y")

    _, active_tickers = get_tickers(data)
    active_tickers = [t[0] for t in active_tickers]

    # Simple correlation between owned assets.
    active_tickers = list(set(active_tickers))
    prices_df = yf.download(active_tickers, start=start_ref_date, end=end_ref_date, progress=False)
    returns_df = prices_df["Close"].pct_change().dropna()
    correlation_matrix = returns_df.corr()
    print(f"\n--- Correlazione semplice ---")
    print(correlation_matrix)

    # Rolling correlation. Not restricted to just owned assets;
    # If at least one of the input assets is not owned, download appropriate data.
    # Else reuse what was previously downloaded  
    print(f"\n--- Correlazione rolling tra due assets ---")
    print("È possibile confrontare anche assets non detenuti in portafoglio.\n")
    asset1 = input("  - Inserire ticker asset 1 > ")
    asset2 = input("  - Inserire ticker asset 2 > ")
    print("  - Finestra temporale in giorni ")
    window = int(input("    Si consiglia 100-150 per storici superiori a 2 anni e 20-60 per storici inferiori > "))
    
    if not(asset1 or asset2) in active_tickers:
        prices_df = yf.download([asset1, asset2], start=start_ref_date, end=end_ref_date, progress=False)
        returns_df = prices_df["Close"].pct_change().dropna()
    rolling_corr = returns_df[asset1].rolling(window=window).corr(returns_df[asset2])

    fig1 = plt.figure(figsize=(7, 6))
    ax1 = sns.heatmap(correlation_matrix, cmap="coolwarm", vmin=-1, vmax=1, center=0, annot=True, annot_kws={"fontsize": 12})
    ax1.set_xlabel('')  # remove x-axis label
    ax1.set_ylabel('')  # remove y-axis label
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
def drawdown(df, data):

    print("  Data inizio analisi:")
    start_dt = get_date(df, sequential_only=False)
    start_ref_date = datetime.strptime(start_dt, "%d-%m-%Y")
    print("  Data fine analisi:")
    end_dt = get_date(df, sequential_only=False)
    end_ref_date = datetime.strptime(end_dt, "%d-%m-%Y")

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
    input("\nPremi Invio per continuare...")


def var_mc(df, data):

    # SEE IF YOU CAN OPTIMIZE ACTIVE POSITION FETCHING LOGIC
    
    start_ref_date = "2010-01-01"
    confidence_interval = float(input("  - Intervallo di Confidenza (es. 0.99) > "))    # type check
    projected_days = int(input("  - Numero di giorni interessati > "))    # type check, maybe < n
    end_dt = datetime.now()

    _, total_tickers = get_tickers(data)
    usd_tickers = [t[0] for t in total_tickers if t[1] == "USD"]
    eur_tickers = [t[0] for t in total_tickers if t[1] == "EUR"]

    total_positions = []
    total_liquidity = []

    # get in date end_dt: total positions held across accounts, total liquidity 
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
    asset_value = [pos["value"] for pos in aggr_positions]
    asset_tickers = [pos["ticker"] for pos in aggr_positions]
    sum_active_values = sum(asset_value)
    weights = asset_value / sum_active_values
    cash = sum(total_liquidity)

    print("    Scaricamento dati storici da Yahoo Finance...")
    usd_prices_df = yf.download(usd_tickers, start=start_ref_date, end=end_dt, progress=False)
    eur_prices_df = yf.download(eur_tickers, start=start_ref_date, end=end_dt, progress=False)
    exch_df = yf.download("USDEUR=X",start=start_ref_date, end=end_dt, progress=False)
    usd_prices_df = usd_prices_df["Close"]
    eur_prices_df = eur_prices_df["Close"]
    exch_df = exch_df["Close"]

    common_dates = usd_prices_df.index.intersection(eur_prices_df.index)
    common_dates = common_dates.intersection(exch_df.index)

    usd_prices_df = usd_prices_df.loc[common_dates]
    eur_prices_df = eur_prices_df.loc[common_dates]
    exch_df = exch_df.loc[common_dates]
    usd_prices_df = usd_prices_df.mul(exch_df["USDEUR=X"], axis=0)

    prices_df = pd.concat([usd_prices_df, eur_prices_df], axis=1)
    prices_df = prices_df[asset_tickers]

    log_returns = np.log(prices_df/prices_df.shift(1))

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

    def scenario_gain_loss(current_liq, sum_active_values, portfolio_expected_return, portfolio_std_dev, z_score, days):
        return current_liq + (sum_active_values * portfolio_expected_return * days) + (sum_active_values * portfolio_std_dev * z_score * np.sqrt(days))
    
    num_simulations = 50000
    scenarioReturn = []

    for _ in range(num_simulations):
        z_score = random_z_score()
        scenarioReturn.append(scenario_gain_loss(current_liq, sum_active_values, portfolio_expected_return, portfolio_std_dev, z_score, projected_days))

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
    input("\nPremi Invio per continuare...")






# 7 - INIZIALIZZA BROKERS
def initialize_brokers(config_folder):
    path = os.path.join(config_folder, "brokers.json")
    brokers = {}
    idx = 1
    print('    Inserisci alias conto. Digitare "q" per terminare.')
    while True:
        new_broker = input("\n     > ")
        if new_broker == "q":
            if len(brokers) == 0:
                print("    Operazione negata. È necessario aggiungere almeno un conto.")
                continue
            else:
                print("\nSalvataggio completato. Conti aggiunti:\n")
                for key, value in brokers.items():
                    print(f"{key}. {value}") 
                break
        brokers[idx] = new_broker
        idx += 1

    with open(path, 'w', encoding='utf-8') as f:
        json.dump(brokers, f, indent=4)
    
    input("\n    Premi Invio per continuare...")
    return brokers