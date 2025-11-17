import sys
import numpy as np
import pandas as pd
import os
import json

import utils.menu_operations as mop
import utils.account as aop
from utils.date_utils import get_date
from utils.other_utils import create_defaults

pd.set_option('display.max_columns', None)
REP_DEF = "Report "
user_folder = os.path.join(os.getcwd(), "reports")
config_folder = os.path.join(os.getcwd(), "config")
config_res_folder = os.path.join(config_folder, "resources")
os.makedirs(user_folder, exist_ok=True)
os.makedirs(config_res_folder, exist_ok=True)

def main_menu(file, account_name, len_df, len_df_init, edited_flag):
    print("\n=================== MENU PRINCIPALE ===================\n")
    print(f"Si sta operando sul conto: {account_name}\nFile caricato: {file}, con {len_df_init-1} righe.")

    if edited_flag:
        diff = len_df - len_df_init
        print("Sono presenti modifiche non salvate.")
        if diff == 0:
            print(f"Righe totali aggiunte o rimosse: {diff} (il numero di righe è invariato, ma il contenuto potrebbe essere stato modificato).")
        else:
            print(f"Righe totali aggiunte o rimosse: {diff}")
    else:
        print("Nessuna modifica eseguita.")
    
    print("\n> Seleziona operazione.\n")
    print("    c. Cambia conto\n")
    print("    1. Liquidità")
    print("    2. ETF")
    print("    3. Azioni")
    print("    4. Obbligazioni")
    print("    5. Ultimi movimenti")
    print("    6. Analisi portafoglio\n")
    print("    s. Impostazioni applicazione")
    print("    e. Esporta in CSV")
    print("    r. Rimuovi ultima riga")
    print("    i. Informazioni/Glossario\n")
    print("    q. Esci dal programma")


if __name__ == "__main__":

    try:
        with open(os.path.join(config_folder, "brokers.json"), 'r', encoding='utf-8') as f:
            brokers = json.load(f)  
    except FileNotFoundError:
        print("\nSembra che sia la prima volta che si utilizzi questo programma.")
        print("Si prega di aggiungere un alias rappresentativo per ciascuno dei propri conti.")
        print('Ad esempio, "Fineco" o "Conto Intesa 1".\n')
        brokers = mop.initialize_brokers(config_folder)
        os.system("cls" if os.name == "nt" else "clear")    

    for broker_name in list(brokers.values()):
        create_defaults(config_res_folder, broker_name)
    # Convert keys back to ints (json saves everything as str)
    brokers = {int(k): v for k, v in brokers.items()}

    loaded = False
    while not loaded:
        account, is_loaded = aop.load_account(brokers, config_res_folder, REP_DEF)
        loaded = is_loaded
        os.system("cls" if os.name == "nt" else "clear")

    df = account[0]["df"] 
    len_df_init = account[0]["len_df_init"]
    edited_flag = account[0]["edited_flag"] 
    file = account[0]["file"]
    path = account[0]["path"]
    acc_idx = account[0]["acc_idx"]

    all_accounts, _ = aop.load_account(brokers, config_res_folder, REP_DEF, active_only=False)
    os.system("cls" if os.name == "nt" else "clear")

    while True:

        try:
            if len(df) != len_df_init:
                edited_flag = True

            main_menu(file, brokers[acc_idx], len(df), len_df_init, edited_flag)
            print("\n" + "="*55)
            choice = input("\n> ")

            if choice in ('c', 'C'):
                loaded = False
                while not loaded:
                    account, is_loaded = aop.load_account(brokers, config_res_folder, REP_DEF)
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

            elif choice == '1':
                cash_loop = True
                while cash_loop:
                    os.system("cls" if os.name == "nt" else "clear")
                    print("\n--- OPERAZIONI SU LIQUIDITA' ---\n\nCTRL+C per annullare e tornare al Menu Principale.\n")
                    print("    1. Depositi e Prelievi\n    2. Dividendi\n    3. Imposta di Bollo / Altre imposte")
                    operation = input("\n> ")
                    print('\n  - Data operazione GG-MM-AAAA ("t" per data odierna)')            
                    dt, ref_date = get_date(df)

                    if operation == "1":
                        df = mop.cashop(df, dt, ref_date, brokers[acc_idx])                  
                        cash_loop = False
                    elif operation == "2":
                        df = mop.dividend(df, dt, ref_date, brokers[acc_idx])
                        cash_loop = False
                    elif operation == "3":
                        df = mop.charge(df, dt, ref_date, brokers[acc_idx])
                        cash_loop = False
                    else:
                        input("\nScelta non valida. Premi Invio per riprovare.")
                os.system("cls" if os.name == "nt" else "clear")

            elif choice == '2':
                os.system("cls" if os.name == "nt" else "clear")
                print("\n--- ETF ---\n\nCTRL+C per annullare e tornare al Menu Principale.\n")
                df = mop.etf_stock(df, brokers[acc_idx], choice="ETF")
                os.system("cls" if os.name == "nt" else "clear")
            
            elif choice == '3':
                os.system("cls" if os.name == "nt" else "clear")
                print("\n--- AZIONI ---\n\nCTRL+C per annullare e tornare al Menu Principale.\n")
                df = mop.etf_stock(df, brokers[acc_idx], choice="Azioni")
                os.system("cls" if os.name == "nt" else "clear")

            elif choice == '4':
                os.system("cls" if os.name == "nt" else "clear")
                print("\n--- OBBLIGAZIONI ---\n\nCTRL+C per annullare e tornare al Menu Principale.\n")
                input("Obbligazioni non ancora implementate. Premi Invio per continuare...")
                os.system("cls" if os.name == "nt" else "clear")

            elif choice == '5':
                os.system("cls" if os.name == "nt" else "clear")
                print("\n--- ULTIMI MOVIMENTI (MAX 10) ---\n\n")
                print(df.tail(10))
                input("\nPremi Invio per tornare al Menu Principale...")
                os.system("cls" if os.name == "nt" else "clear")

            elif choice == '6':
                analysis_loop = True
                while analysis_loop:
                    os.system("cls" if os.name == "nt" else "clear")
                    print("\n--- ANALISI PORTAFOGLIO ---\n\nCTRL+C per annullare e tornare al Menu Principale.\n")
                    print("    1. Statistiche generali\n    2. Analisi correlazione\n    3. Drawdown\n    4. VaR")
                    operation = input("\n> ")
                    accounts_formatted = aop.format_accounts(df, acc_idx, all_accounts)

                    if operation == "1":
                        from utils.analysis import summary
                        hist_save_path = os.path.join(user_folder, "Storico Portafoglio.csv")
                        summary(brokers, accounts_formatted, hist_save_path)                  
                        analysis_loop = False
                    elif operation == "2":
                        from utils.analysis import correlation
                        correlation(accounts_formatted)
                        analysis_loop = False
                    elif operation == "3":
                        from utils.analysis import drawdown
                        drawdown(accounts_formatted)
                        analysis_loop = False
                    elif operation == "4":
                        from utils.analysis import var_mc
                        var_mc(accounts_formatted)
                        analysis_loop = False
                    else:
                        input("\nScelta non valida. Premi Invio per riprovare.")
                os.system("cls" if os.name == "nt" else "clear")

            elif choice in ("s", "S"):
                settings_loop = True
                while settings_loop:
                    os.system("cls" if os.name == "nt" else "clear")
                    print("\n--- IMPOSTAZIONI APPLICAZIONE ---\n\nCTRL+C per annullare e tornare al Menu Principale.\n")
                    print("    1. Aggiungi conti\n    2. Inizializza conti\n    3. Inizializza applicazione (richiede conferma)")
                    operation = input("\n> ")

                    if operation == "1":
                        brokers = mop.add_brokers(config_folder)
                        sys.exit("\nConti aggiunti. Esco dall'applicazione...\n")                     
                        settings_loop = False
                    elif operation == "2":
                        brokers = mop.initialize_brokers(config_folder)
                        sys.exit("\nConti inizializzati. Esco dall'applicazione...\n")
                        settings_loop = False
                    elif operation == "3":
                        os.system("cls" if os.name == "nt" else "clear")
                        print("\nQuesta operazione non è reversibile. L'applicazione verrà reimpostata, eliminando tutti i dati salvati.")
                        confirmation = input("Digitare 'CONFERMA' per procedere. Altri input saranno ignorati.\n\n    > ")
                        if confirmation == "CONFERMA":
                            import shutil
                            try:
                                if os.path.exists(config_folder):
                                    shutil.rmtree(config_folder)
                                if os.path.exists(user_folder):
                                    shutil.rmtree(user_folder)
                            except OSError as e:
                                print(f"Error deleting directory: {e}")
                            os.system("cls" if os.name == "nt" else "clear")
                            sys.exit("\nReset completato. Esco dall'applicazione...\n")
                        else:
                            settings_loop = False
                    else:
                        input("\nScelta non valida. Premi Invio per riprovare.")
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
                print(f'\nEsportato "{file}" in {user_folder}')
                input("\nPremi Invio per tornare al Menu Principale...")
                os.system("cls" if os.name == "nt" else "clear")

            elif choice in ('r', 'R'):
                os.system("cls" if os.name == "nt" else "clear")
                if len(df) > 1:
                    df = df.iloc[:-1]
                    print("\nUltima riga rimossa.")
                else:
                    print("\nNessuna riga da rimuovere.")

            elif choice in ('i', 'I'):
                from utils.other_utils import display_information
                info_loop = True
                while info_loop:
                    os.system("cls" if os.name == "nt" else "clear")
                    print("\n--- INFORMAZIONI / GLOSSARIO ---\n\nCTRL+C per annullare e tornare al Menu Principale.\n")
                    print("    1. Descrizione colonne del report\n    2. Informazioni su metriche/statistiche")
                    operation = input("\n> ")
                    if operation in ("1", "2"):
                        display_information(page=int(operation))                 
                        info_loop = False
                    else:
                        input("\nScelta non valida. Premi Invio per riprovare.")
                os.system("cls" if os.name == "nt" else "clear")

            elif choice in ('q', 'Q'):
                os.system("cls" if os.name == "nt" else "clear")
                sys.exit("\nEsco dal programma...\n")
            
            else:
                os.system("cls" if os.name == "nt" else "clear")
                input("\nScelta non valida. Premi Invio per riprovare.")

        except KeyboardInterrupt:
            os.system("cls" if os.name == "nt" else "clear")
            continue