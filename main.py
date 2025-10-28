import time

# these imports take ~0.20 seconds
import numpy as np
import pandas as pd
import os
import json

# these imports take 0.80-0.83 seconds
import utils.operations_menu as mop
import utils.operations_account as aop
from utils.date_utils import get_date
from utils.other_utils import wrong_input, create_defaults, display_information

pd.set_option('display.max_columns', None)
REP_DEF = "Report "
save_folder = os.path.join(os.getcwd(), "reports")
config_folder = os.path.join(os.getcwd(), "config")
os.makedirs(save_folder, exist_ok=True)
os.makedirs(config_folder, exist_ok=True)

def main_menu(file, account_name, len_df, len_df_init, edited_flag):
    print("\n=================== MENU PRINCIPALE ===================\n")
    print(f"Si sta operando sul conto: {account_name}\nFile caricato: {file}, con {len_df_init} righe.")

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
    print("    a. Cambia conto\n")
    print("    1. Liquidità")
    print("    2. ETF")
    print("    3. Azioni")
    print("    4. Obbligazioni")
    print("    5. Ultimi movimenti")
    print("    6. Analisi portafoglio")
    print("    7. Inizializza intermediari\n")
    print("    s. Esporta in CSV")
    print("    r. Rimuovi ultima riga")
    print("    i. Informazioni/Glossario")
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
        create_defaults(save_folder, broker_name)
    # Convert keys back to ints (json saves everything as str)
    brokers = {int(k): v for k, v in brokers.items()}

    account = aop.load_account(brokers, save_folder, REP_DEF)
    df = account[0]["df"] 
    len_df_init = account[0]["len_df_init"]
    edited_flag = account[0]["edited_flag"] 
    file = account[0]["file"]
    path = account[0]["path"]
    acc_idx = account[0]["acc_idx"]

    all_accounts = aop.load_account(brokers, save_folder, REP_DEF, active_only=False)
    os.system("cls" if os.name == "nt" else "clear")

    while True:

        try:
            if len(df) != len_df_init:
                edited_flag = True

            main_menu(file, brokers[acc_idx], len(df), len_df_init, edited_flag)
            print("\n" + "="*55)
            choice = input("\n> ")

            if choice in ('a', 'A'):
                account = aop.load_account(brokers, save_folder, REP_DEF)
                df = account[0]["df"] 
                len_df_init = account[0]["len_df_init"]
                edited_flag = account[0]["edited_flag"] 
                file = account[0]["file"]
                path = account[0]["path"]
                acc_idx = account[0]["acc_idx"]

                os.system("cls" if os.name == "nt" else "clear")
                continue

            elif choice == '1':
                os.system("cls" if os.name == "nt" else "clear")
                print("\n--- OPERAZIONI SU LIQUIDITA' ---\n")
                print("> Seleziona operazione. CTRL+C per tornare al Menu Principale.\n")
                print("    1. Depositi e Prelievi\n    2. Dividendi\n    3. Imposta di Bollo / Altre imposte")
                operation = input("\n> ")
                try:
                    operation = int(operation)
                    if operation not in [1, 2, 3]:
                        raise ValueError
                except:
                    wrong_input()
                print()            

                dt = get_date(df)

                if operation == 1:
                    df = mop.cashop(df, dt, brokers[acc_idx])
                elif operation == 2:
                    df = mop.dividend(df, dt, brokers[acc_idx])
                else:
                    df = mop.charge(df, dt, brokers[acc_idx])
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

                os.system("cls" if os.name == "nt" else "clear")
                print("\n--- ANALISI PORTAFOGLIO ---\n")
                print("> Seleziona operazione. CTRL+C per tornare al Menu Principale.\n")
                print("    1. Statistiche generali\n    2. Analisi correlazione\n    3. Drawdown\n    4. VaR")
                accounts_formatted = aop.format_accounts(df, acc_idx, all_accounts)
                operation = input("\n> ")
                try:
                    operation = int(operation)
                    if operation not in [1, 2, 3, 4]:
                        raise ValueError
                except:
                    wrong_input()
                print()            

                if operation == 1:
                    mop.summary(df, brokers, accounts_formatted)
                elif operation == 2:
                    mop.correlation(df, accounts_formatted)
                elif operation == 3:
                    mop.drawdown(df, accounts_formatted)
                else:
                    mop.var_mc(df, accounts_formatted)
                os.system("cls" if os.name == "nt" else "clear")

            elif choice == '7':
                os.system("cls" if os.name == "nt" else "clear")
                print("\n--- INIZIALIZZAZIONE INTERMEDIARI ---\n\nCTRL+C per annullare e tornare al Menu Principale.")
                brokers = mop.initialize_brokers(config_folder)
                os.system("cls" if os.name == "nt" else "clear")
            
            elif choice in ('i', 'I'):
                os.system("cls" if os.name == "nt" else "clear")
                print("--- INFORMAZIONI / GLOSSARIO ---")
                print("> Seleziona categoria. CTRL+C per tornare al Menu Principale.\n")
                print("    1. Descrizione colonne del report\n    2. Informazioni su metriche/statistiche")
                accounts_formatted = aop.format_accounts(df, acc_idx, all_accounts)
                operation = input("\n> ")
                try:
                    operation = int(operation)
                    if operation not in [1, 2]:
                        raise ValueError
                except:
                    wrong_input()
                print()            

                if operation == 1:
                    display_information(page=operation)
                else:
                    display_information(page=operation)
                os.system("cls" if os.name == "nt" else "clear")

            elif choice in ('s', 'S'):
                os.system("cls" if os.name == "nt" else "clear")
                df.to_csv(path, index=False)
                len_df_init = len(df)
                edited_flag = False
                print(f"\nEsportato {file} in {path}")
                input("\nPremi Invio per tornare al Menu Principale...")
                os.system("cls" if os.name == "nt" else "clear")

            elif choice in ('r', 'R'):
                os.system("cls" if os.name == "nt" else "clear")
                if len(df) > 1:
                    df = df.iloc[:-1]
                    print("\nUltima riga rimossa.")
                else:
                    print("\nLa riga template non può essere rimossa.")

            elif choice in ('q', 'Q'):
                os.system("cls" if os.name == "nt" else "clear")
                exit("\nEsco dal programma...\n")
            
            else:
                os.system("cls" if os.name == "nt" else "clear")
                input("\nScelta non valida. Premi Invio per riprovare.")

        except KeyboardInterrupt:
            os.system("cls" if os.name == "nt" else "clear")
            continue