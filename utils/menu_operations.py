import numpy as np
import configparser
import os

from newrow import newrow_cash, newrow_etf_stock
from utils.date_utils import get_date
from utils.fetch_utils import fetch_name    
from utils.other_utils import round_half_up, wrong_input

# 1. CASH OPERATIONS
def cashop(translator, df, broker):
    print(translator.get("cash.date"))            
    dt, ref_date = get_date(translator, df)
    try:
        cash = float(input(translator.get("cash.cash_amount")))
        if cash == 0:
            raise ValueError()
    except ValueError:
        wrong_input(translator, translator.get("cash.cash_error"))
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
        wrong_input(translator, translator.get("cash.dividend_error"))
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
        wrong_input(translator, translator.get("cash.charge_error"))
    descr = str(input(translator.get("cash.charge_descr")))

    df = newrow_cash(translator, df, dt, ref_date, broker, -cash, "Imposta", descr, np.nan, np.nan)
    print()
    print(df.tail(10))
    return df



# 2/3. ETF/STOCK
def etf_stock(translator, df, broker, choice="ETF"):
    
    print(translator.get("stock.date"))
    dt, ref_date = get_date(translator, df)

    print(translator.get("stock.currency"))
    try:
        currency = int(input("    > "))
        if currency not in [1, 2]:
            raise ValueError
    except ValueError:
        wrong_input(translator, translator.get("stock.currency_error"))
    
    conv_rate = 1.0
    if currency == 2:
        try:
            conv_rate = float(input(translator.get("stock.exch_rate")))
            if conv_rate <= 0:
                raise ValueError
        except ValueError:
            wrong_input(translator, translator.get("stock.exch_rate_error"))
    conv_rate = round_half_up(1.0 / conv_rate, decimal="0.000001")

    ticker = input(translator.get("stock.ticker"))

    try:
        quantity = input(translator.get("stock.qt"))
        if not (quantity.isdigit() and int(quantity) > 0):
            raise ValueError
        quantity = int(quantity)
    except ValueError or AttributeError:
        wrong_input(translator, translator.get("stock.qt_error"))
            
    try:
        price = float(input(translator.get("stock.price")))
        if price == 0:
            raise ValueError
    except ValueError:
        wrong_input(translator, translator.get("stock.price_error"))

    currency_fee = 1
    if currency == 2:
        print(translator.get("stock.currency_fee"))
        currency_fee = input("    > ")
        try:
            currency_fee = int(currency_fee)
            if currency_fee not in [1, 2]:
                raise ValueError
        except ValueError:
            wrong_input(translator, translator.get("stock.currency_error"))

    try:
        fee = float(input(translator.get("stock.fee")))
        if fee < 0:
            raise ValueError
    except ValueError:
        wrong_input(translator, translator.get("stock.fee_error"))

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




# s. SETTINGS
def select_language(translator, config_folder, lang_dict):

    path = os.path.join(config_folder, "config.ini")
    config = configparser.ConfigParser()
    if os.path.exists(path):
        config.read(path)
    
    if not config.has_section("Language"):
        config.add_section("Language")

    while True:
        print("\n" + translator.get("settings.language.select_language") + "\n")
        for key, value in lang_dict.items():
            print(f"    {key}. {value[1]}")
        try:
            selected_lang = int(input(f"\n > "))
            if selected_lang not in lang_dict.keys():
                raise ValueError
        except ValueError:
            print(translator.get("settings.language.selection_error"))
            input(translator.get("redirect.invalid_choice") + "\n")
            os.system("cls" if os.name == "nt" else "clear")
            continue
        
        lang_code = lang_dict[selected_lang][0]
        config.set("Language", "code", lang_code)
        break

    with open(path, 'w', encoding='utf-8') as f:
        config.write(f)
    
    translator.load_language(lang_code)
    input(translator.get("settings.language.changed") + " " + translator.get("redirect.continue"))
    return lang_code


def add_brokers(translator, config_folder):
    path = os.path.join(config_folder, "config.ini")
    config = configparser.ConfigParser()
    config.read(path)

    if not config.has_section('Brokers'):
        config.add_section('Brokers')

    existing_indices = []
    if 'Brokers' in config:
        try:
            existing_indices = [int(k) for k in config['Brokers']]
        except ValueError:
            pass

    idx = max(existing_indices) + 1 if existing_indices else 1

    print(translator.get("settings.account.add_account"))
    brokers = {} 
    # Reload full brokers dict for return value
    if 'Brokers' in config:
        brokers = {int(k): v for k, v in config.items('Brokers')}

    while True:
        new_broker = input("\n     > ")
        if new_broker == "q":
            # Since we load from file, we check the current state of brokers in the file/dict
            if not brokers:
                print(translator.get("settings.account.op_denied"))
                continue
            else:
                print(translator.get("settings.account.saved"))
                for key, value in sorted(brokers.items()):
                    print(f"{key}. {value}") 
                break
        
        config.set('Brokers', str(idx), new_broker)
        brokers[idx] = new_broker
        idx += 1
    
    with open(path, 'w', encoding='utf-8') as f:
        config.write(f)
    
    input(translator.get("redirect.continue"))
    return brokers


def initialize_brokers(translator, config_folder):
    path = os.path.join(config_folder, "config.ini")
    config = configparser.ConfigParser()
    config.read(path)
    
    # Reset brokers section
    if config.has_section('Brokers'):
        config.remove_section('Brokers')
    config.add_section('Brokers')

    brokers = {}
    idx = 1
    print(translator.get("settings.account.add_account"))
    while True:
        new_broker = input("\n     > ")
        if new_broker == "q":
            if not brokers:
                print(translator.get("settings.account.op_denied"))
                continue
            else:
                print(translator.get("settings.account.saved"))
                for key, value in brokers.items():
                    print(f"{key}. {value}") 
                break
        
        config.set('Brokers', str(idx), new_broker)
        brokers[idx] = new_broker
        idx += 1

    with open(path, 'w', encoding='utf-8') as f:
        config.write(f)
    
    input("\n" + translator.get("redirect.continue"))
    return brokers