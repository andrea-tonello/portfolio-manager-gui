import sys
import numpy as np
import pandas as pd
import os
import configparser

import utils.menu_operations as mop
import utils.account as aop
from utils.other_utils import create_defaults, run_submenu, display_information
from utils.translator import Translator
from utils.constants import clear_screen, LANG, REPORT_PREFIX

pd.set_option("display.max_columns", None)
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


def unpack_account(account):
    a = account[0]
    return a["df"], a["len_df_init"], a["edited_flag"], a["file"], a["path"], a["acc_idx"]


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
    if os.path.exists(config_path) and 'Brokers' in config:
        try:
            brokers = {int(k): v for k, v in config.items('Brokers')}
        except ValueError:
            pass
    if not brokers:
        print(translator.get("main_menu.first_boot"))
        brokers = mop.manage_brokers(translator, config_folder, reset=True)
        clear_screen()
    for broker_name in list(brokers.values()):
        create_defaults(config_res_folder, broker_name)

    loaded = False
    while not loaded:
        account, is_loaded = aop.load_account(translator, brokers, config_res_folder, REPORT_PREFIX)
        loaded = is_loaded
        clear_screen()

    df, len_df_init, edited_flag, file, path, acc_idx = unpack_account(account)

    all_accounts, _ = aop.load_account(translator, brokers, config_res_folder, REPORT_PREFIX, active_only=False)
    clear_screen()

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
                    account, is_loaded = aop.load_account(translator, brokers, config_res_folder, REPORT_PREFIX)
                    loaded = is_loaded
                    clear_screen()
                df, len_df_init, edited_flag, file, path, acc_idx = unpack_account(account)
                clear_screen()
                continue

            elif choice == "1":
                broker = brokers[acc_idx]
                df = run_submenu(translator, "cash.title", "cash.operations", {
                    "1": lambda: mop.cash_operation(translator, df, broker, "deposit_withdrawal"),
                    "2": lambda: mop.cash_operation(translator, df, broker, "dividend"),
                    "3": lambda: mop.cash_operation(translator, df, broker, "charge"),
                })
                input("\n" + translator.get("redirect.continue_home"))
                clear_screen()

            elif choice == "2":
                clear_screen()
                print(translator.get("stock.title_etf") + translator.get("redirect.cancel_home") + "\n")
                df = mop.etf_stock(translator, df, brokers[acc_idx], choice="ETF")
                clear_screen()

            elif choice == "3":
                clear_screen()
                print(translator.get("stock.title_stock") + translator.get("redirect.cancel_home") + "\n")
                df = mop.etf_stock(translator, df, brokers[acc_idx], choice="Azioni")
                clear_screen()

            elif choice == "4":
                clear_screen()
                print(translator.get("bond.title") + translator.get("redirect.cancel_home") + "\n")
                input(translator.get("bond.not_implemented"))
                clear_screen()

            elif choice == "5":
                clear_screen()
                print(translator.get("review.title"))
                print(df.tail(10))
                input("\n" + translator.get("redirect.continue_home"))
                clear_screen()

            elif choice == "6":
                from utils.analysis import summary, correlation, drawdown, var_mc
                accounts_formatted = aop.format_accounts(df, acc_idx, all_accounts)
                hist_save_path = os.path.join(user_folder, "Storico Portafoglio.csv")

                run_submenu(translator, "analysis.title", "analysis.operations", {
                    "1": lambda: summary(translator, brokers, accounts_formatted, hist_save_path),
                    "2": lambda: correlation(translator, accounts_formatted),
                    "3": lambda: drawdown(translator, accounts_formatted),
                    "4": lambda: var_mc(translator, accounts_formatted),
                })
                input("\n" + translator.get("redirect.continue"))
                clear_screen()

            elif choice in ("s", "S"):
                while True:
                    clear_screen()
                    print(translator.get("settings.title") + translator.get("redirect.cancel_home") + "\n")
                    print(translator.get("settings.operations"))
                    operation = input("\n> ")

                    if operation == "1":
                        lang_code = mop.select_language(translator, config_folder, LANG)
                        translator.load_language(lang_code)
                        break
                    elif operation == "2":
                        brokers = mop.manage_brokers(translator, config_folder, reset=False)
                        sys.exit(translator.get("settings.account.accounts_added") + translator.get("redirect.exit"))
                    elif operation == "3":
                        brokers = mop.manage_brokers(translator, config_folder, reset=True)
                        sys.exit(translator.get("settings.account.accounts_initialized") + translator.get("redirect.exit"))
                    elif operation == "4":
                        clear_screen()
                        print(translator.get("settings.account.reset_warning"))
                        confirmation = input(translator.get("settings.account.reset_confirm"))
                        if confirmation == "RESET":
                            import shutil
                            try:
                                if os.path.exists(config_folder):
                                    shutil.rmtree(config_folder)
                                if os.path.exists(user_folder):
                                    shutil.rmtree(user_folder)
                            except OSError:
                                print(translator.get("settings.account.deletion_error"))
                            clear_screen()
                            sys.exit(translator.get("settings.account.reset_completed") + translator.get("redirect.exit"))
                        else:
                            break
                    else:
                        input("\n" + translator.get("redirect.invalid_choice"))
                clear_screen()

            elif choice in ("e", "E"):
                clear_screen()
                path_user = os.path.join(user_folder, file)
                df_user = df.copy()
                df_user = df_user[1:]
                df.to_csv(path, index=False)                        # for internal use
                df_user.to_csv(path_user, index=False)              # for the user to see
                len_df_init = len(df)
                edited_flag = False
                print(translator.get("export.exported", file=file, user_folder=user_folder))
                input(translator.get("redirect.continue_home"))
                clear_screen()

            elif choice in ("r", "R"):
                clear_screen()
                if len(df) > 1:
                    df = df.iloc[:-1]
                    print(translator.get("remove_row.row_removed"))
                else:
                    print(translator.get("remove_row.no_rows"))

            elif choice in ("i", "I"):
                run_submenu(translator, "glossary.title", "glossary.operations", {
                    "1": lambda: display_information(translator, page=1),
                    "2": lambda: display_information(translator, page=2),
                })
                clear_screen()

            elif choice in ("q", "Q"):
                clear_screen()
                sys.exit("\n" + translator.get("redirect.exit"))

            else:
                clear_screen()
                input("\n" + translator.get("redirect.invalid_choice"))

        except KeyboardInterrupt:
            clear_screen()
            continue