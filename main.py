import sys
import numpy as np
import pandas as pd
import os
import json
import configparser

import utils.menu_operations as mop
import utils.account as aop
from utils.other_utils import create_defaults
from utils.translator import Translator

pd.set_option("display.max_columns", None)
LANG = {1: ("en", "English"), 2: ("it", "Italiano")}
REP_DEF = "Report "
user_folder = os.path.join(os.getcwd(), "reports")
config_folder = os.path.join(os.getcwd(), "config")
config_res_folder = os.path.join(config_folder, "resources")
os.makedirs(user_folder, exist_ok=True)
os.makedirs(config_res_folder, exist_ok=True)

def main_menu(translator, file, account_name, len_df, len_df_init, edited_flag):
    header = translator.get("main_menu.title")
    header_length = len(header)
    print("\n" + header + "\n")
    print(translator.get("main_menu.operating_on", account_name=account_name, file=file, rows=len_df_init-1))

    if edited_flag:
        diff = len_df - len_df_init
        print(translator.get("main_menu.unsaved_changes"))
        if diff == 0:
            print(translator.get("main_menu.rows_changed", diff=diff) + translator.get("main_menu.rows_changed_zero"))
        else:
            print(translator.get("main_menu.rows_changed", diff=diff))
    else:
        print(translator.get("main_menu.no_changes"))
    
    print(translator.get("main_menu.select_operation"))
    print(translator.get("main_menu.operations"))
    return header_length


if __name__ == "__main__":

    config_path = os.path.join(config_folder, "config.ini")
    config = configparser.ConfigParser()


    default_lang = LANG[1][0]    # default - en
    translator = Translator(language_code=default_lang)
    lang_code = None
    if os.path.exists(config_path):
        config.read(config_path)
        if 'Language' in config and 'Code' in config['Language']:
            lang_code = config['Language']['Code']
    if lang_code is None:
        lang_code = mop.select_language(translator, config_folder, LANG)
    translator.load_language(lang_code)


    brokers = {}
    # Try to load brokers from config
    if os.path.exists(config_path) and 'Brokers' in config:
        try:
            # Convert keys to int (configparser reads keys as strings)
            brokers = {int(k): v for k, v in config.items('Brokers')}
        except ValueError:
            pass
    # If no brokers found (first boot or empty section), initialize
    if not brokers:
        print(translator.get("main_menu.first_boot"))
        brokers = mop.initialize_brokers(translator, config_folder)
        os.system("cls" if os.name == "nt" else "clear")    
    for broker_name in list(brokers.values()):
        create_defaults(config_res_folder, broker_name)


    loaded = False
    while not loaded:
        account, is_loaded = aop.load_account(translator, brokers, config_res_folder, REP_DEF)
        loaded = is_loaded
        os.system("cls" if os.name == "nt" else "clear")

    df = account[0]["df"] 
    len_df_init = account[0]["len_df_init"]
    edited_flag = account[0]["edited_flag"] 
    file = account[0]["file"]
    path = account[0]["path"]
    acc_idx = account[0]["acc_idx"]

    all_accounts, _ = aop.load_account(translator, brokers, config_res_folder, REP_DEF, active_only=False)
    os.system("cls" if os.name == "nt" else "clear")

    while True:

        try:
            if len(df) != len_df_init:
                edited_flag = True

            header_length = main_menu(translator, file, brokers[acc_idx], len(df), len_df_init, edited_flag)
            print("\n" + "="*header_length)
            choice = input("\n> ")

            if choice in ("a", "A"):
                loaded = False
                while not loaded:
                    account, is_loaded = aop.load_account(translator, brokers, config_res_folder, REP_DEF)
                    loaded = is_loaded
                    os.system("cls" if os.name == "nt" else "clear")
                df = account[0]["df"] 
                len_df_init = account[0]["len_df_init"]
                edited_flag = account[0]["edited_flag"] 
                file = account[0]["file"]
                path = account[0]["path"]
                acc_idx = account[0]["acc_idx"]

                os.system("cls" if os.name == "nt" else "clear")
                continue

            elif choice == "1":
                cash_loop = True
                while cash_loop:
                    os.system("cls" if os.name == "nt" else "clear")
                    print(translator.get("cash.title") + translator.get("redirect.cancel_home") + "\n")
                    print(translator.get("cash.operations"))
                    operation = input("\n> ")

                    if operation == "1":
                        df = mop.cashop(translator, df, brokers[acc_idx])                  
                        cash_loop = False
                    elif operation == "2":
                        df = mop.dividend(translator, df, brokers[acc_idx])
                        cash_loop = False
                    elif operation == "3":
                        df = mop.charge(translator, df, brokers[acc_idx])
                        cash_loop = False
                    else:
                        input("\n" + translator.get("redirect.invalid_choice"))
                        continue
                    input("\n" + translator.get("redirect.continue_home"))
                os.system("cls" if os.name == "nt" else "clear")

            elif choice == "2":
                os.system("cls" if os.name == "nt" else "clear")
                print(translator.get("stock.title_etf") + translator.get("redirect.cancel_home") + "\n")
                df = mop.etf_stock(translator, df, brokers[acc_idx], choice="ETF")
                os.system("cls" if os.name == "nt" else "clear")
            
            elif choice == "3":
                os.system("cls" if os.name == "nt" else "clear")
                print(translator.get("stock.title_stock") + translator.get("redirect.cancel_home") + "\n")
                df = mop.etf_stock(translator, df, brokers[acc_idx], choice="Azioni")
                os.system("cls" if os.name == "nt" else "clear")

            elif choice == "4":
                os.system("cls" if os.name == "nt" else "clear")
                print(translator.get("bond.title") + translator.get("redirect.cancel_home") + "\n")
                input(translator.get("bond.not_implemented"))
                os.system("cls" if os.name == "nt" else "clear")

            elif choice == "5":
                os.system("cls" if os.name == "nt" else "clear")
                print(translator.get("review.title"))
                print(df.tail(10))
                input("\n" + translator.get("redirect.continue_home"))
                os.system("cls" if os.name == "nt" else "clear")

            elif choice == "6":
                analysis_loop = True
                while analysis_loop:
                    os.system("cls" if os.name == "nt" else "clear")
                    print(translator.get("analysis.title") + translator.get("redirect.cancel_home") + "\n")
                    print(translator.get("analysis.operations"))
                    operation = input("\n> ")
                    accounts_formatted = aop.format_accounts(df, acc_idx, all_accounts)

                    if operation == "1":
                        from utils.analysis import summary
                        hist_save_path = os.path.join(user_folder, "Storico Portafoglio.csv")
                        summary(translator, brokers, accounts_formatted, hist_save_path)                  
                        analysis_loop = False
                    elif operation == "2":
                        from utils.analysis import correlation
                        correlation(translator, accounts_formatted)
                        analysis_loop = False
                    elif operation == "3":
                        from utils.analysis import drawdown
                        drawdown(translator, accounts_formatted)
                        analysis_loop = False
                    elif operation == "4":
                        from utils.analysis import var_mc
                        var_mc(translator, accounts_formatted)
                        analysis_loop = False
                    else:
                        input("\n" + translator.get("redirect.invalid_choice"))
                    input(translator.get("redirect.continue"))
                os.system("cls" if os.name == "nt" else "clear")

            elif choice in ("s", "S"):
                while True:
                    os.system("cls" if os.name == "nt" else "clear")
                    print(translator.get("settings.title") + translator.get("redirect.cancel_home") + "\n")
                    print(translator.get("settings.operations"))
                    operation = input("\n> ")

                    if operation == "1":
                        lang_code = mop.select_language(translator, config_folder, LANG)
                        translator.load_language(lang_code)
                        break
                    if operation == "2":
                        brokers = mop.add_brokers(translator, config_folder)
                        sys.exit(translator.get("settings.account.accounts_added") + translator.get("redirect.exit"))                     
                        break
                    elif operation == "3":
                        brokers = mop.initialize_brokers(translator, config_folder)
                        sys.exit(translator.get("settings.account.accounts_initialized") + translator.get("redirect.exit"))
                        break
                    elif operation == "4":
                        os.system("cls" if os.name == "nt" else "clear")
                        print(translator.get("settings.account.reset_warning"))
                        confirmation = input(translator.get("settings.account.reset_confirm"))
                        if confirmation == "RESET":
                            import shutil
                            try:
                                if os.path.exists(config_folder):
                                    shutil.rmtree(config_folder)
                                if os.path.exists(user_folder):
                                    shutil.rmtree(user_folder)
                            except OSError as e:
                                print(translator.get("settings.account.deletion_error"))
                            os.system("cls" if os.name == "nt" else "clear")
                            sys.exit(translator.get("settings.account.reset_completed") + translator.get("redirect.exit"))
                        else:
                            break
                    else:
                        input("\n" + translator.get("redirect.invalid_choice"))
                os.system("cls" if os.name == "nt" else "clear")

            elif choice in ("e", "E"):
                os.system("cls" if os.name == "nt" else "clear")
                path_user = os.path.join(user_folder, file)
                df_user = df.copy()
                df_user = df_user[1:]
                df.to_csv(path, index=False)                        # for internal use
                df_user.to_csv(path_user, index=False)              # for the user to see 
                len_df_init = len(df)   
                edited_flag = False
                print(translator.get("export.exported", file=file, user_folder=user_folder))
                input(translator.get("redirect.continue_home"))
                os.system("cls" if os.name == "nt" else "clear")

            elif choice in ("r", "R"):
                os.system("cls" if os.name == "nt" else "clear")
                if len(df) > 1:
                    df = df.iloc[:-1]
                    print(translator.get("remove_row.row_removed"))
                else:
                    print(translator.get("remove_row.no_rows"))

            elif choice in ("i", "I"):
                from utils.other_utils import display_information
                info_loop = True
                while info_loop:
                    os.system("cls" if os.name == "nt" else "clear")
                    print(translator.get("glossary.title") + translator.get("redirect.cancel_home") + "\n")
                    print(translator.get("glossary.operations"))
                    operation = input("\n> ")
                    if operation in ("1", "2"):
                        display_information(translator, page=int(operation))                 
                        info_loop = False
                    else:
                        input("\n" + translator.get("redirect.invalid_choice"))
                os.system("cls" if os.name == "nt" else "clear")

            elif choice in ("q", "Q"):
                os.system("cls" if os.name == "nt" else "clear")
                sys.exit("\n" + translator.get("redirect.exit"))
            
            else:
                os.system("cls" if os.name == "nt" else "clear")
                input("\n" + translator.get("redirect.invalid_choice"))

        except KeyboardInterrupt:
            os.system("cls" if os.name == "nt" else "clear")
            continue