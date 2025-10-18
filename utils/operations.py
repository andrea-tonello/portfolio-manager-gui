import pandas as pd
import numpy as np
from datetime import datetime
import json
import os

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

    fee = float(input("  - Commissione (in valuta originale) > "))
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



# 5 - RESOCONTO

def summary(df):

    dt = get_date(df, sequential_only=False)
    ref_date = datetime.strptime(dt, "%d-%m-%Y")
    positions = get_asset_value(df, ref_date=ref_date)

    print()
    print(df.tail(10))

  ### CALCOLO LIQUIDITA PER DATA X: 
    # SE DATA X È PRESENTE NEL df USA QUELLA 
    # ALTRIMENTI PESCA LA PRIMA DATA PRECEDENTE DISPONIBILE
    df_copy = df.copy()
    df_copy["Data"] = pd.to_datetime(df_copy["Data"], dayfirst=True, errors="coerce")

    df_valid = df_copy[df_copy["Data"] <= ref_date]

    if df_valid.empty:
        raise ValueError(f"Nessuna data disponibile nel DataFrame precedente a {dt}")

    current_liq = float(df_valid.iloc[-1]["Liquidita Attuale"])

    asset_value = sum(pos["value"] for pos in positions)
    nav = current_liq + asset_value

    historic_liq = df["Liq. Storica Immessa"].iloc[-1]
    pl = nav - historic_liq

    print("\n\n--- Statistiche ---")
    print(f"\n    NAV (al {dt}): {round_half_up(nav)}€")
    print(f"\t- Liquidità: {round_half_up(current_liq)}€")
    print(f"\t- Valore Titoli: {round_half_up(asset_value)}€")
    print(f"    Liquidità Storica Immessa: {historic_liq}€")
    print(f"    P&L Totale: {round_half_up(pl)}€\n")

    print(f"\nTitoli detenuti in data {dt}:\n")
    for pos in positions:
        print(f"    {pos["ticker"]}    QT: {pos["quantity"]}    Prezzo attuale: {round_half_up(pos["price"], decimal="0.0001")}€    Controvalore: {round_half_up(pos["value"])}€")

    input("\nPremi Invio per continuare...")







# 6 - INIZIALIZZA BROKERS

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