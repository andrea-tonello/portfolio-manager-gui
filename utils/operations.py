import pandas as pd
import numpy as np
from datetime import datetime
import json
import os
import yfinance as yf
import seaborn as sns
import matplotlib.pyplot as plt

from newrow import newrow_cash, newrow_etf_stock
from utils.asset_utils import get_asset_value
from utils.date_utils import get_date
from utils.fetch_utils import fetch_name
from utils.other_utils import round_half_up, wrong_input, create_defaults


# 1 - LIQUIDITÀ

def cashop(df, dt):
    cash = float(input("  - Ammontare operazione in EUR (negativo se prelievo) > "))
    if cash == 0:
        raise ValueError("Il contante inserito non può essere 0€.\nPositivo se depositato, negativo se prelevato.")
    op_type = "Deposito" if cash > 0 else "Prelievo"

    df = newrow_cash(df, dt, cash, op_type, "Contanti", np.nan, np.nan)
    print()
    print(df.tail(10))
    input("\nPremi Invio per continuare...")
    return df

def dividend(df, dt):
    cash = float(input("  - Dividendo in EUR al netto di tasse > "))
    if cash <= 0.0:
        raise ValueError("Il dividendo non può essere <= 0€")
    ticker = input("  - Ticker completo dell'emittente dividendo > ")
    name = fetch_name(ticker)

    df = newrow_cash(df, dt, cash, "Dividendo", "Dividendo", ticker, name)
    print()
    print(df.tail(10))
    input("\nPremi Invio per continuare...")
    return df

def charge(df, dt):
    cash = float(input("  - Ammontare imposta in EUR > "))
    if cash <= 0.0:
        raise ValueError("L'imposta è da intendersi > 0.")
    descr = str(input('  - Descrizione imposta (es. "Bollo Q2 2025") > '))

    df = newrow_cash(df, dt, -cash, "Imposta", descr, np.nan, np.nan)
    print()
    print(df.tail(10))
    input("\nPremi Invio per continuare...")
    return df





# 2,3 - ETF, STOCK

def etf_stock(df, choice="ETF"):
    
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

    df = newrow_etf_stock(df, dt, "EUR" if currency==1 else "USD", choice, ticker, quantity, price, conv_rate, ter, fee, buy)
    print()
    print(df.tail(10))
    input("\nPremi Invio per continuare...")
    return df



# 6.1 - RESOCONTO
def summary(df, brokers, data):

    dt = get_date(df, sequential_only=False)
    ref_date = datetime.strptime(dt, "%d-%m-%Y")

    total_current_liq = []
    total_asset_value = []
    total_nav = []
    total_historic_liq = []
    total_pl = []

    for account in data:
        print(f"\n\n\nConto {account[0]}: {brokers[account[0]]} " + "="*70)

        df_copy = account[1].copy()
        positions = get_asset_value(df_copy, ref_date=ref_date)

    ### CALCOLO LIQUIDITA PER DATA X: 
    # SE DATA X È PRESENTE NEL df USA QUELLA 
    # ALTRIMENTI PESCA LA PRIMA DATA PRECEDENTE DISPONIBILE
        df_copy["Data"] = pd.to_datetime(df_copy["Data"], dayfirst=True, errors="coerce")
        df_valid = df_copy[df_copy["Data"] <= ref_date]
        if df_valid.empty:
            raise ValueError(f"Nessuna data disponibile nel DataFrame precedente a {dt}")

        current_liq = round_half_up(float(df_valid.iloc[-1]["Liquidita Attuale"]))
        asset_value = round_half_up(sum(pos["value"] for pos in positions))
        nav = round_half_up(current_liq + asset_value)
        historic_liq = df_valid["Liq. Storica Immessa"].iloc[-1]
        pl = round_half_up(nav - historic_liq)

        print(f"\n    NAV (al {dt}): {nav}€")
        print(f"\t- Liquidità: {current_liq}€")
        print(f"\t- Valore Titoli: {asset_value}€")
        print(f"    Liquidità Storica Immessa: {historic_liq}€")
        print(f"    P&L Totale: {pl}€\n")

        total_current_liq.append(current_liq)
        total_asset_value.append(asset_value)
        total_nav.append(nav)
        total_historic_liq.append(historic_liq)
        total_pl.append(pl)

        print(f"    Titoli detenuti in data {dt}:\n")
        if len(positions) == 0:
            print("\t ---")
        else:
            for pos in positions:
                print(f"\t- {pos["ticker"]}    QT: {pos["quantity"]}    Prezzo attuale: {round_half_up(pos["price"], decimal="0.0001")}€    Controvalore: {round_half_up(pos["value"])}€")

    print("\n\n\n--- Totale Portafoglio ---")
    print(f"\n    NAV (al {dt}): {round_half_up(sum(total_nav))}€")
    print(f"\t- Liquidità: {round_half_up(sum(total_current_liq))}€")
    print(f"\t- Valore Titoli: {round_half_up(sum(total_asset_value))}€")
    print(f"    Liquidità Storica Immessa: {round_half_up(sum(total_historic_liq))}€")
    print(f"    P&L Totale: {round_half_up(sum(total_pl))}€\n")
    input("\nPremi Invio per continuare...")


# 6.2 - CORRELAZIONE
def correlation(df, data):

    print("  Data inizio analisi:")
    start_dt = get_date(df, sequential_only=False)
    start_ref_date = datetime.strptime(start_dt, "%d-%m-%Y")
    print("  Data fine analisi:")
    end_dt = get_date(df, sequential_only=False)
    end_ref_date = datetime.strptime(end_dt, "%d-%m-%Y")

    total_tickers = []

    for account in data:
        df_filtered = get_asset_value(account[1], just_active_assets=True)
        ticker_list = df_filtered["Ticker"].dropna().unique().tolist()
        total_tickers.extend(ticker_list)

    # Calcolo correlazione
    total_tickers = list(set(total_tickers))
    prices_df = yf.download(total_tickers, start=start_ref_date, end=end_ref_date, progress=False)
    returns_df = prices_df["Close"].pct_change().dropna()
    correlation_matrix = returns_df.corr()

    print(f"\n--- Correlazione semplice.   Dal: {start_dt}   Al: {end_dt} ---\n")
    print(correlation_matrix)

    print(f"\n--- Correlazione rolling tra due assets.   Dal: {start_dt}   Al: {end_dt} ---\n")
    asset1 = input("  - Inserire ticker asset 1 > ")
    asset2 = input("  - Inserire ticker asset 2 > ")
    print("  - Finestra temporale in giorni ")
    window = int(input("    Si consiglia 100-150 per storici superiori a 2 anni e 20-60 per storici inferiori > "))
    rolling_corr = returns_df[asset1].rolling(window=window).corr(returns_df[asset2])

    fig1 = plt.figure(figsize=(7, 6))
    ax1 = sns.heatmap(correlation_matrix, cmap="coolwarm", vmin=-1, vmax=1, center=0, annot=True, annot_kws={"fontsize": 12})
    ax1.set_xlabel('')  # remove x-axis label
    ax1.set_ylabel('')  # remove y-axis label
    fig1.canvas.manager.set_window_title(f"Correlazione semplice.   Dal: {start_dt}   Al: {end_dt}")

    fig2 = plt.figure(figsize=(8, 6))
    ax2 = rolling_corr.plot(title=f'Intervallo: {window}gg.   Assets: {asset1}, {asset2}', legend=False, color='blue')
    ax2.axhline(0, color='red', linestyle='--', linewidth=0.8, label='Correlazione Zero')
    ax2.set_xlabel('Data')
    ax2.set_ylabel('Coefficiente di correlazione')
    ax2.grid(True, alpha=0.5)
    fig2.canvas.manager.set_window_title(f"Correlazione rolling.   Dal: {start_dt}   Al: {end_dt}")
    plt.show()

    input("\nPremi Invio per continuare...")



# 7 - INIZIALIZZA BROKERS
def initialize_brokers(save_folder):
    path = os.path.join(save_folder, "brokers.json")
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