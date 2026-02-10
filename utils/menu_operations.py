import numpy as np
import configparser
import os

from newrow import newrow_cash, newrow_etf_stock
from utils.date_utils import get_date
from utils.fetch_utils import fetch_name
from utils.other_utils import round_half_up, wrong_input, validated_float, validated_int
from utils.constants import clear_screen, CURRENCY_EUR, CURRENCY_USD, CURRENCY_CHOICES

# 1. CASH OPERATIONS
def cash_operation(translator, df, broker, op_kind):
    print(translator.get("cash.date"))
    dt, ref_date = get_date(translator, df)

    if op_kind == "deposit_withdrawal":
        cash = validated_float(translator, translator.get("cash.cash_amount"),
                               "cash.cash_error", condition=lambda x: x != 0)
        op_type = "Deposito" if cash > 0 else "Prelievo"
        product, ticker, name = "Contanti", np.nan, np.nan

    elif op_kind == "dividend":
        cash = validated_float(translator, translator.get("cash.dividend_amount"),
                               "cash.dividend_error", condition=lambda x: x > 0)
        ticker = input(translator.get("cash.dividend_ticker"))
        name = fetch_name(ticker)
        op_type, product = "Dividendo", "Dividendo"

    elif op_kind == "charge":
        cash_input = validated_float(translator, translator.get("cash.charge_amount"),
                                     "cash.charge_error", condition=lambda x: x > 0)
        cash = -cash_input
        descr = str(input(translator.get("cash.charge_descr")))
        op_type, product, ticker, name = "Imposta", descr, np.nan, np.nan

    df = newrow_cash(translator, df, dt, ref_date, broker, cash, op_type, product, ticker, name)
    print()
    print(df.tail(10))
    return df



# 2/3. ETF/STOCK
def etf_stock(translator, df, broker, choice="ETF"):
    
    print(translator.get("stock.date"))
    dt, ref_date = get_date(translator, df)

    print(translator.get("stock.currency"))
    currency = validated_int(translator, "    > ", "stock.currency_error",
                             condition=lambda x: x in [CURRENCY_EUR, CURRENCY_USD])

    conv_rate = 1.0
    if currency == CURRENCY_USD:
        conv_rate = validated_float(translator, translator.get("stock.exch_rate"),
                                    "stock.exch_rate_error", condition=lambda x: x > 0)
    conv_rate = round_half_up(1.0 / conv_rate, decimal="0.000001")

    ticker = input(translator.get("stock.ticker"))
    quantity = validated_int(translator, translator.get("stock.qt"), "stock.qt_error",
                             condition=lambda x: x > 0)
    price = validated_float(translator, translator.get("stock.price"), "stock.price_error",
                            condition=lambda x: x != 0)

    currency_fee = CURRENCY_EUR
    if currency == CURRENCY_USD:
        print(translator.get("stock.currency_fee"))
        currency_fee = validated_int(translator, "    > ", "stock.currency_error",
                                     condition=lambda x: x in [CURRENCY_EUR, CURRENCY_USD])

    fee = validated_float(translator, translator.get("stock.fee"), "stock.fee_error",
                          condition=lambda x: x >= 0)

    if currency_fee == CURRENCY_USD:
            fee = round_half_up(fee / conv_rate, decimal="0.000001")

    buy = price < 0
    
    ter = np.nan
    if choice == "ETF":
        ter = input(translator.get("stock.ter"))
        ter += "%"

    df = newrow_etf_stock(translator, df, dt, ref_date, broker, CURRENCY_CHOICES[currency], choice, ticker, quantity, price, conv_rate, ter, fee, buy)
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
            clear_screen()
            continue
        
        lang_code = lang_dict[selected_lang][0]
        config.set("Language", "code", lang_code)
        break

    with open(path, 'w', encoding='utf-8') as f:
        config.write(f)
    
    translator.load_language(lang_code)
    input(translator.get("settings.language.changed") + " " + translator.get("redirect.continue"))
    return lang_code


def manage_brokers(translator, config_folder, reset=False):
    path = os.path.join(config_folder, "config.ini")
    config = configparser.ConfigParser()
    config.read(path)

    if reset:
        if config.has_section('Brokers'):
            config.remove_section('Brokers')
        config.add_section('Brokers')
        brokers = {}
        idx = 1
    else:
        if not config.has_section('Brokers'):
            config.add_section('Brokers')
        existing_indices = []
        if 'Brokers' in config:
            try:
                existing_indices = [int(k) for k in config['Brokers']]
            except ValueError:
                pass
        idx = max(existing_indices) + 1 if existing_indices else 1
        brokers = {int(k): v for k, v in config.items('Brokers')} if 'Brokers' in config else {}

    print(translator.get("settings.account.add_account"))
    while True:
        new_broker = input("\n     > ")
        if new_broker == "q":
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

    input("\n" + translator.get("redirect.continue"))
    return brokers