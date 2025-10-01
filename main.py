import numpy as np
import pandas as pd
import os

from newrow import newrow_cash, newrow_etf_stock, fancy_df
from utils import broker_fee, get_date, round_half_up

pd.set_option('display.max_columns', None)

def choice_etf_stock(df, choice="ETF"):
    
    date = get_date(df)
    brk = int(input("Seleziona intermediario (SIM) (1. Fineco, 2. BG Saxo): "))
    currency = int(input("Seleziona valuta (1. EUR, 2. USD): "))
    
    conv_rate = 1.0
    if currency == 2:
        conv_rate = float(input("Inserisci tasso di conversione: "))

    ticker = input("Inserisci Ticker completo: ")

    qt = input("Inserisci quantità (intero positivo): ")
    if not (qt.isdigit() and int(qt) > 0):
        raise ValueError("Quantità non valida. Deve essere un intero positivo.")
    else:
        quantity = int(qt)

    price = float(input("Inserisci prezzo unitario (negativo se acquisto): "))
    if price == 0:
        raise ValueError("Il prezzo non può essere 0€.\nNegativo se acquisto, positivo se vendita.")
    price_og = price

    broker, fee = broker_fee(brk, choice, conv_rate, trade_value=quantity * abs(price_og*conv_rate))

    price = price * conv_rate

    if price < 0:   # buy
        buy = True
        difference = df["Liquidita Attuale"].iloc[-1] + (quantity * price - fee)
        #if difference < 0:
        #    raise ValueError(f"Liquidità insufficiente: {df["Liquidita Attuale"].iloc[-1]}€ {quantity * price - fee}€ = {difference}€")
    
    else:           # sell
        buy = False
    
    ter = np.nan
    if choice == "ETF":
        ter = input("Inserisci TER: ")

    return newrow_etf_stock(df, date, "EUR" if currency==1 else "USD", choice, ticker, quantity, price_og, price, ter, broker, fee, buy)

def main_menu(file, len_df, len_df_init, edited_flag):
    print("\n\n===== MENU PRINCIPALE =====")
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
    
    print("\n1. Liquidità")
    print("2. ETF")
    print("3. Azioni")
    print("4. Obbligazioni")
    print("5. Visualizza resoconto...")
    print("6. Esporta in CSV")
    print("r. Rimuovi ultima riga")
    print("0. Esci dal programma")


if __name__ == "__main__":

    save_folder = os.path.join(os.getcwd(), "reports")
    os.makedirs(save_folder, exist_ok=True)
    file = "report.csv"
    path = os.path.join(save_folder, file)

    rep = input(f"Importato {file} di default. Cambiare report? (y/n): ")

    if rep == "y":
        print("Assurati che il tuo file segua il formato di report-template.csv\n e che sia all'interno della cartella reports.")
        file = input('Inserisci nome del file (es. "report-template.csv"): ')
        path = os.path.join(save_folder, file)

    df = pd.read_csv(path)
    len_df_init = len(df)
    edited_flag = False

    while True:

        if len(df) != len_df_init:
            edited_flag = True

        main_menu(file, len(df), len_df_init, edited_flag)
        choice = input("\nSeleziona operazione (1 2 3 4 5 6 r 0): ")
        print("\n" + "="*28)

        # CASH
        if choice == '1':
            os.system("cls" if os.name == "nt" else "clear")
            print("\n--- 1. LIQUIDITA ---")

            date = get_date(df)

            brk = int(input("Seleziona intermediario (SIM) (1. Fineco, 2. BG Saxo): "))
            brokers = {
                1: "Fineco",
                2: "BG Saxo",
            }
            broker = brokers.get(brk, "SIM non riconosciuto")
            
            cash = float(input("Inserisci contante da depositare o prelevare: "))
            if cash == 0.0:
                raise ValueError("Il contante inserito non può essere 0€.\nPositivo se depositato, negativo se prelevato.")
            
            
            df = newrow_cash(df, date, cash, broker)
            print(fancy_df(df.tail(10)))
        
        # ETF
        elif choice == '2':
            os.system("cls" if os.name == "nt" else "clear")
            print("\n--- 2. ETF ---")
            df = choice_etf_stock(df, choice="ETF")
            print(fancy_df(df.tail(10)))
        
        elif choice == '3':
            os.system("cls" if os.name == "nt" else "clear")
            print("\n--- 3. AZIONI ---")
            df = choice_etf_stock(df, choice="Stock")
            print(fancy_df(df.tail(10)))


        # DIVIDENDI:
        #   div_EUR = div_USD * conv_rate
        #  First apply the US tax, then the Italian tax
        #   div_EUR *= (1-0.15)     US TAX
        #   div_EUR *= (1-0.26)     IT TAX
        #   div_EUR = round(div_EUR)



        elif choice == '4':
            os.system("cls" if os.name == "nt" else "clear")
            print("\n--- 4. OBBLIGAZIONI ---")
            print("Obbligazioni non ancora implementate.")

        elif choice == '5':
            os.system("cls" if os.name == "nt" else "clear")
            print("\n--- 5. RESOCONTO ---\n")
            
            print(fancy_df(df.tail(10)))
            
            pl = df["Netto"].sum()
            print("\n\n--- Statistiche ---")
            print(f"\n\tP&L Totale: {round_half_up(pl)}€")
            print(f"\tNAV Aggiornato al [IMPLEMENTA]")
            
        elif choice == '6':
            os.system("cls" if os.name == "nt" else "clear")

            df.to_csv(path, index=False)

            df_fancy = fancy_df(df)
            file_fancy = file.replace(".csv", "-fancy.csv")
            path_fancy = os.path.join(save_folder, file_fancy)

            df_fancy.to_csv(path_fancy, index=False)

            print(f"\nEsportati {file} e {file_fancy} in {path}")


        elif choice == 'r':
            os.system("cls" if os.name == "nt" else "clear")
            if len(df) > 1:
                df = df.iloc[:-1]
                print("\nUltima riga rimossa.")
            else:
                print("\nLa riga template non può essere rimossa.")

        elif choice == '0':
            os.system("cls" if os.name == "nt" else "clear")
            exit("\nEsco dal programma...\n")
        
        else:
            os.system("cls" if os.name == "nt" else "clear")
            print("\nScelta non valida. Riprova.")