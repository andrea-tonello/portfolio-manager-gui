import numpy as np
import json
import os
#from scipy.stats import norm

from newrow import newrow_cash, newrow_etf_stock
from utils.date_utils import get_date
from utils.fetch_utils import fetch_name    
from utils.other_utils import round_half_up, wrong_input


# 1 - LIQUIDITÀ
def cashop(df, dt, ref_date, broker):
    cash = float(input("  - Ammontare operazione in EUR (negativo se prelievo)\n    > "))
    if cash == 0:
        raise ValueError("Il contante inserito non può essere 0€.\nPositivo se depositato, negativo se prelevato.")
    op_type = "Deposito" if cash > 0 else "Prelievo"

    df = newrow_cash(df, dt, ref_date, broker, cash, op_type, "Contanti", np.nan, np.nan)
    print()
    print(df.tail(10))
    input("\nPremi Invio per continuare...")
    return df

def dividend(df, dt, ref_date, broker):
    cash = float(input("  - Dividendo in EUR al netto di tasse\n    > "))
    if cash <= 0.0:
        raise ValueError("Il dividendo non può essere <= 0€")
    ticker = input("  - Ticker completo dell'emittente dividendo\n    > ")
    name = fetch_name(ticker)

    df = newrow_cash(df, dt, ref_date, broker, cash, "Dividendo", "Dividendo", ticker, name)
    print()
    print(df.tail(10))
    input("\nPremi Invio per continuare...")
    return df

def charge(df, dt, ref_date, broker):
    cash = float(input("  - Ammontare imposta in EUR\n    > "))
    if cash <= 0.0:
        raise ValueError("L'imposta è da intendersi > 0€.")
    descr = str(input('  - Descrizione imposta (es. "Bollo Q2 2025")\n    > '))

    df = newrow_cash(df, dt, ref_date, broker, -cash, "Imposta", descr, np.nan, np.nan)
    print()
    print(df.tail(10))
    input("\nPremi Invio per continuare...")
    return df



# 2,3 - ETF, STOCK
def etf_stock(df, broker, choice="ETF"):
    
    print('\n  - Data operazione GG-MM-AAAA ("t" per data odierna)')
    dt, ref_date = get_date(df)

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
        conv_rate = float(input("  - Tasso di conversione EUR-USD\n    > "))
    conv_rate = round_half_up(1.0 / conv_rate, decimal="0.000001")

    ticker = input("  - Ticker completo (standard Yahoo Finance)\n    > ")

    qt = input("  - Quantità (intero positivo)\n    > ")
    if not (qt.isdigit() and int(qt) > 0):
        raise ValueError("Quantità non valida. Deve essere un intero positivo.")
    else:
        quantity = int(qt)

    price = float(input("  - Prezzo unitario (negativo se acquisto)\n    > "))
    if price == 0:
        raise ValueError("Il prezzo non può essere 0€.\nNegativo se acquisto, positivo se vendita.")

    currency_fee = 1
    if currency == 2:
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

    fee = float(input("  - Commissione\n    > "))
    if currency_fee == 2:
        fee = round_half_up(fee / conv_rate, decimal="0.000001")

    buy = price < 0
    
    ter = np.nan
    if choice == "ETF":
        ter = input("  - Total Expense Ratio\n    > ")
        ter += "%"

    df = newrow_etf_stock(df, dt, ref_date, broker, "EUR" if currency==1 else "USD", choice, ticker, quantity, price, conv_rate, ter, fee, buy)
    print()
    print(df.tail(10))
    input("\nPremi Invio per continuare...")
    return df










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