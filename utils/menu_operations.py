import numpy as np
import json
import os
#from scipy.stats import norm

from newrow import newrow_cash, newrow_etf_stock
from utils.date_utils import get_date
from utils.fetch_utils import fetch_name    
from utils.other_utils import round_half_up, wrong_input


# 1 - LIQUIDITÀ
def cashop(translator, df, broker):
    print(translator.get("cash.date"))            
    dt, ref_date = get_date(translator, df)
    try:
        cash = float(input(translator.get("cash.cash_amount")))
        if cash == 0:
            raise ValueError()
    except ValueError:
        wrong_input(translator.get("cash.cash_error"))
    op_type = "Deposito" if cash > 0 else "Prelievo"

    df = newrow_cash(translator, df, dt, ref_date, broker, cash, op_type, "Contanti", np.nan, np.nan)
    print()
    print(df.tail(10))
    return df

def dividend(translator, df, broker):
    print(translator.get("cash.date"))            
    dt, ref_date = get_date(translator, df)
    try:
        cash = float(input(translator.get("cash.dividend_amount")))
        if cash <= 0.0:
            raise ValueError
    except ValueError:
        wrong_input(translator.get("cash.dividend_error"))
    ticker = input(translator.get("cash.dividend_ticker"))
    name = fetch_name(ticker)

    df = newrow_cash(translator, df, dt, ref_date, broker, cash, "Dividendo", "Dividendo", ticker, name)
    print()
    print(df.tail(10))
    return df

def charge(translator, df, broker):
    print(translator.get("cash.date"))            
    dt, ref_date = get_date(translator, df)
    try:
        cash = float(input(translator.get("cash.charge_amount")))
        if cash <= 0.0:
            raise ValueError
    except ValueError:
        wrong_input(translator.get("cash.charge_error"))
    descr = str(input(translator.get("cash.charge_descr")))

    df = newrow_cash(translator, df, dt, ref_date, broker, -cash, "Imposta", descr, np.nan, np.nan)
    print()
    print(df.tail(10))
    return df



# 2,3 - ETF, STOCK
def etf_stock(translator, df, broker, choice="ETF"):
    
    print(translator.get("stock.date"))
    dt, ref_date = get_date(translator, df)

    print(translator.get("stock.currency"))
    try:
        currency = int(input("    > "))
        if currency not in [1, 2]:
            raise ValueError
    except ValueError:
        wrong_input(translator.get("stock.currency_error"))
    
    conv_rate = 1.0
    if currency == 2:
        try:
            conv_rate = float(input(translator.get("stock.exch_rate")))
            if conv_rate <= 0:
                raise ValueError
        except ValueError:
            wrong_input(translator.get("stock.exch_rate_error"))
    conv_rate = round_half_up(1.0 / conv_rate, decimal="0.000001")

    ticker = input(translator.get("stock.ticker"))

    try:
        quantity = input(translator.get("stock.qt"))
        if not (quantity.isdigit() and int(quantity) > 0):
            raise ValueError
        quantity = int(quantity)
    except ValueError or AttributeError:
        wrong_input(translator.get("stock.qt_error"))
            
    try:
        price = float(input(translator.get("stock.price")))
        if price == 0:
            raise ValueError
    except ValueError:
        wrong_input(translator.get("stock.price_error"))

    currency_fee = 1
    if currency == 2:
        print(translator.get("stock.currency_fee"))
        currency_fee = input("    > ")
        try:
            currency_fee = int(currency_fee)
            if currency_fee not in [1, 2]:
                raise ValueError
        except ValueError:
            wrong_input(translator.get("stock.currency_error"))

    try:
        fee = float(input(translator.get("stock.fee")))
        if fee < 0:
            raise ValueError
    except ValueError:
        wrong_input(translator.get("stock.fee_error"))

    if currency_fee == 2:
            fee = round_half_up(fee / conv_rate, decimal="0.000001")

    buy = price < 0
    
    ter = np.nan
    if choice == "ETF":
        ter = input(translator.get("stock.ter"))
        ter += "%"

    df = newrow_etf_stock(translator, df, dt, ref_date, broker, "EUR" if currency==1 else "USD", choice, ticker, quantity, price, conv_rate, ter, fee, buy)
    print()
    print(df.tail(10))
    input("\n" + translator.get("redirect.continue_home"))
    return df




# 7 - IMPOSTAZIONI

def add_brokers(translator, config_folder):
    path = os.path.join(config_folder, "brokers.json")
    with open(path, 'r', encoding='utf-8') as f:
        brokers = json.load(f)

    idx = len(brokers) + 1
    print(translator.get("settings.add_account"))
    while True:
        new_broker = input("\n     > ")
        if new_broker == "q":
            if len(brokers) == 0:
                print(translator.get("settings.op_denied"))
                continue
            else:
                print(translator.get("settings.saved"))
                for key, value in brokers.items():
                    print(f"{key}. {value}") 
                break
        brokers[idx] = new_broker
        idx += 1
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(brokers, f, indent=4)
    
    input(translator.get("redirect.continue"))
    return brokers


def initialize_brokers(translator, config_folder):
    path = os.path.join(config_folder, "brokers.json")
    brokers = {}
    idx = 1
    print(translator.get("settings.add_account"))
    while True:
        new_broker = input("\n     > ")
        if new_broker == "q":
            if len(brokers) == 0:
                print(translator.get("settings.op_denied"))
                continue
            else:
                print(translator.get("settings.saved"))
                for key, value in brokers.items():
                    print(f"{key}. {value}") 
                break
        brokers[idx] = new_broker
        idx += 1

    with open(path, 'w', encoding='utf-8') as f:
        json.dump(brokers, f, indent=4)
    
    input(translator.get("redirect.continue"))
    return brokers