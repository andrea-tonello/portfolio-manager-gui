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
    try:
        cash = float(input("  - Ammontare operazione in EUR (negativo se prelievo)\n    > "))
        if cash == 0:
            raise ValueError()
    except ValueError:
        wrong_input("Il contante inserito deve essere un numero diverso da 0. Positivo se depositato, negativo se prelevato.")
    op_type = "Deposito" if cash > 0 else "Prelievo"

    df = newrow_cash(df, dt, ref_date, broker, cash, op_type, "Contanti", np.nan, np.nan)
    print()
    print(df.tail(10))
    input("\nPremi Invio per continuare...")
    return df

def dividend(df, dt, ref_date, broker):
    try:
        cash = float(input("  - Dividendo in EUR al netto di tasse\n    > "))
        if cash <= 0.0:
            raise ValueError
    except ValueError:
        wrong_input("Il dividendo inserito deve essere un numero maggiore di 0.")
    ticker = input("  - Ticker completo dell'emittente dividendo\n    > ")
    name = fetch_name(ticker)

    df = newrow_cash(df, dt, ref_date, broker, cash, "Dividendo", "Dividendo", ticker, name)
    print()
    print(df.tail(10))
    input("\nPremi Invio per continuare...")
    return df

def charge(df, dt, ref_date, broker):
    try:
        cash = float(input("  - Ammontare imposta in EUR\n    > "))
        if cash <= 0.0:
            raise ValueError
    except ValueError:
        wrong_input("L'imposta inserita deve essere un numero maggiore di 0.")
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
    try:
        currency = int(input("    > "))
        if currency not in [1, 2]:
            raise ValueError
    except ValueError:
        wrong_input("Valuta non riconosciuta. È necessario inserire il numero corrispondente alla valuta di interesse.")
    
    conv_rate = 1.0
    if currency == 2:
        conv_rate = float(input("  - Tasso di conversione EUR-USD\n    > "))        ## TYPE CHECK
    conv_rate = round_half_up(1.0 / conv_rate, decimal="0.000001")

    ticker = input("  - Ticker completo (standard Yahoo Finance)\n    > ")

    try:
        quantity = input("  - Quantità (intero positivo)\n    > ")
        if not (quantity.isdigit() and int(quantity) > 0):
            raise ValueError
        quantity = int(quantity)
    except ValueError or AttributeError:
        wrong_input("Quantità non valida. Deve essere un numero intero maggiore di 0.")
            
    try:
        price = float(input("  - Prezzo unitario (negativo se acquisto)\n    > "))
        if price == 0:
            raise ValueError
    except ValueError:
        wrong_input("Il prezzo non può essere 0. Negativo se acquisto, positivo se vendita.")

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
            wrong_input("Valuta non riconosciuta. È necessario inserire il numero corrispondente alla valuta di interesse.")

    try:
        fee = float(input("  - Commissione\n    > "))
        if fee < 0:
            raise ValueError
    except ValueError:
        wrong_input("La commissione deve essere un numero maggiore o uguale a 0.")

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




# 7 - IMPOSTAZIONI

def add_brokers(config_folder):
    path = os.path.join(config_folder, "brokers.json")
    with open(path, 'r', encoding='utf-8') as f:
        brokers = json.load(f)

    idx = len(brokers) + 1
    print('    Inserisci alias conto. Digitare "q" per terminare.')
    while True:
        new_broker = input("\n     > ")
        if new_broker == "q":
            if len(brokers) == 0:
                print("    Operazione negata. È necessario aggiungere almeno un conto.")
                continue
            else:
                print("\nSalvataggio completato. Conti salvati:\n")
                for key, value in brokers.items():
                    print(f"{key}. {value}") 
                break
        brokers[idx] = new_broker
        idx += 1
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(brokers, f, indent=4)
    
    input("\n    Premi Invio per continuare...")
    return brokers


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