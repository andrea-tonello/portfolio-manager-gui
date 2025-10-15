import numpy as np
import pandas as pd
import os
from datetime import date, datetime

import operations as op
from newrow import newrow_cash, newrow_etf_stock
from utils import broker_fee, get_date, round_half_up, get_asset_value
from fetch_data import fetch_name
import json

pd.set_option('display.max_columns', None)
BROKERS_PATH = "reports/brokers.json"
file = "report.csv"
save_folder = os.path.join(os.getcwd(), "reports")
os.makedirs(save_folder, exist_ok=True)


def main_menu(file, len_df, len_df_init, edited_flag):
    print("\n\n============ MENU PRINCIPALE ============\n")
    print(f"File selezionato: {file} con {len_df_init} righe.")

    if edited_flag:
        diff = len_df - len_df_init
        print("Sono presenti modifiche non salvate.")
        if diff == 0:
            print(f"Righe totali aggiunte o rimosse: {diff} (il numero di righe è invariato, ma il contenuto è stato modificato).")
        else:
            print(f"Righe totali aggiunte o rimosse: {diff}")
    else:
        print("Nessuna modifica eseguita.")
    
    print("\n> Seleziona operazione.")
    print("\n    1. Liquidità")
    print("    2. ETF")
    print("    3. Azioni")
    print("    4. Obbligazioni")
    print("    5. Visualizza resoconto...")
    print("    6. Inizializza intermediari\n")
    print("    s. Esporta in CSV")
    print("    r. Rimuovi ultima riga")
    print("    q. Esci dal programma")


if __name__ == "__main__":

    try:
        with open(BROKERS_PATH, 'r', encoding='utf-8') as f:
            brokers = json.load(f)
    except FileNotFoundError:
        print("\nSembra che sia la prima volta che si utilizzi questo programma.")
        print("Si prega di aggiungere un alias rappresentativo per ciascuno dei propri account.")
        print('Ad esempio, "Fineco" o "Conto Intesa 1".\n')
        brokers = op.initialize_brokers(BROKERS_PATH)
        os.system("cls" if os.name == "nt" else "clear")


    path = os.path.join(save_folder, file)
    rep = input(f"\nImportato {file} di default. Cambiare report? (y/N): ")
    if rep == "y":
        print("Assurati che il tuo file segua il formato di report-template.csv\n e che sia all'interno della cartella reports.")
        file = input('Inserisci nome del file (es. "report-template.csv"): ')
        path = os.path.join(save_folder, file)

    df = pd.read_csv(path)
    len_df_init = len(df)
    edited_flag = False

    while True:

        try:
            if len(df) != len_df_init:
                edited_flag = True

            main_menu(file, len(df), len_df_init, edited_flag)
            print("\n" + "="*41)
            choice = input("\n> ")

            if choice == '1':
                os.system("cls" if os.name == "nt" else "clear")
                print("\n--- OPERAZIONI SU LIQUIDITA' ---\n")
                print("> Seleziona operazione. CTRL+C per tornare al Menu Principale.\n")
                print("    1. Depositi e Prelievi\n    2. Dividendi\n    3. Imposta di Bollo / Altre imposte")
                operation = int(input("\n> "))
                print()
                if operation not in [1, 2, 3]:
                    raise KeyError("Seleziona tra 1, 2, 3.")

                dt = get_date(df)

                brk = int(input("    Intermediario/SIM (1. Fineco, 2. BG Saxo) > "))
                brokers = {1: "Fineco", 2: "BG Saxo"}
                broker = brokers.get(brk, "SIM non riconosciuto")

                if operation == 1:
                    df = op.cashop(df, dt, broker)
                elif operation == 2:
                    df = op.dividend(df, dt, broker)
                else:
                    df = op.charge(df, dt, broker)
                os.system("cls" if os.name == "nt" else "clear")

            elif choice == '2':
                os.system("cls" if os.name == "nt" else "clear")
                print("\n--- ETF ---\n\nCTRL+C per tornare al Menu Principale.\n")
                df = op.etf_stock(df, choice="ETF")
                os.system("cls" if os.name == "nt" else "clear")
            
            elif choice == '3':
                os.system("cls" if os.name == "nt" else "clear")
                print("\n--- AZIONI ---\n\nCTRL+C per tornare al Menu Principale.\n")
                df = op.etf_stock(df, choice="Azioni")
                os.system("cls" if os.name == "nt" else "clear")

            elif choice == '4':
                os.system("cls" if os.name == "nt" else "clear")
                print("\n--- OBBLIGAZIONI ---\n\nCTRL+C per tornare al Menu Principale.\n")
                input("Obbligazioni non ancora implementate. Premi Invio per continuare...")
                os.system("cls" if os.name == "nt" else "clear")

            elif choice == '5':
                os.system("cls" if os.name == "nt" else "clear")
                print("\n--- RESOCONTO ---\n")
                op.summary(df)
                os.system("cls" if os.name == "nt" else "clear")

            elif choice == '6':
                os.system("cls" if os.name == "nt" else "clear")
                print("\n--- INIZIALIZZAZIONE INTERMEDIARI ---\n\nCTRL+C per annullare e tornare al Menu Principale.")
                brokers = op.initialize_brokers(BROKERS_PATH)
                os.system("cls" if os.name == "nt" else "clear")
                
            elif choice == 's':
                os.system("cls" if os.name == "nt" else "clear")
                df.to_csv(path, index=False)
                print(f"\nEsportato {file} in {path}")
                input("\nPremi Invio per continuare...")
                os.system("cls" if os.name == "nt" else "clear")


            elif choice == 'r':
                os.system("cls" if os.name == "nt" else "clear")
                if len(df) > 1:
                    df = df.iloc[:-1]
                    print("\nUltima riga rimossa.")
                else:
                    print("\nLa riga template non può essere rimossa.")


            elif choice == 'q':
                os.system("cls" if os.name == "nt" else "clear")
                exit("\nEsco dal programma...\n")
            
            else:
                os.system("cls" if os.name == "nt" else "clear")
                input("\nScelta non valida. Premi Invio per riprovare.")

        except KeyboardInterrupt:
            os.system("cls" if os.name == "nt" else "clear")
            continue