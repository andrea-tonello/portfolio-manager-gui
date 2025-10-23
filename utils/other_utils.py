import pandas as pd
import numpy as np
import os
from decimal import Decimal, ROUND_HALF_UP, ROUND_DOWN

def load_account(brokers, save_folder, report_default, select_one=True):

    accounts_selected = []

    if select_one:
        print("\nSelezionare il conto su cui operare.\n")
        for key, value in brokers.items():
            print(f"    {key}. {value}")
        account = input(f"\n > ")
        try:
            account = int(account)
            if account not in list( range(1, len(brokers)+1) ):
                raise ValueError
        except ValueError:
            wrong_input()

        file = report_default + brokers[account] + ".csv"
        path = os.path.join(save_folder, file)
        try:
            df = pd.read_csv(path)
        except FileNotFoundError:
            print(f'\nFile "{file}" non trovato.\nAssicurati che sia già presente nella cartella reports e che segua il formato di Template.csv')
            exit()

        len_df_init = len(df)
        edited_flag = False
        accounts_selected.append({
            "acc_idx": account,
            "df": df,
            "file": file,
            "path": path,
            "len_df_init": len_df_init,
            "edited_flag": edited_flag
        })
        
    else:
        for account in list( range(1, len(brokers)+1) ):
            file = report_default + brokers[account] + ".csv"
            path = os.path.join(save_folder, file)
            try:
                df = pd.read_csv(path)
            except FileNotFoundError:
                print(f'\nFile "{file}" non trovato.\nAssicurati che sia già presente nella cartella reports e che segua il formato di Template.csv')
                exit()

            len_df_init = len(df)
            edited_flag = False
            accounts_selected.append({
                "acc_idx": account,
                "df": df,
                "file": file,
                "path": path,
                "len_df_init": len_df_init,
                "edited_flag": edited_flag
            })

    return accounts_selected


def format_accounts(df, acc_idx, all_accounts):
    # Remove active account (since we have real-time data from df. 
    # Otherwise we would be working with the previously saved report)
    non_active_accounts = [acc for acc in all_accounts if acc["acc_idx"] != acc_idx]

    # [(1, df1), (2, df2),...]
    data = [(acc["acc_idx"], acc["df"]) for acc in non_active_accounts]
    data.append((acc_idx, df))
    data = sorted(data, key=lambda x: x[0])
    return data


def round_half_up(valore, decimal="0.01"):
    # Handle NaN or None
    if pd.isna(valore):
        return np.nan
    
    try:
        return float(Decimal(str(valore)).quantize(Decimal(decimal), rounding=ROUND_HALF_UP))
    except Exception:
        print(f"Warning: unable to round value {valore}")
        return valore
    
def round_down(value, decimal="0.01"):
    return float(Decimal(str(value)).quantize(Decimal(decimal), rounding=ROUND_DOWN))


def wrong_input():
    print("I dati inseriti non sono corretti:")
    input("\nPremi Invio per tornare al Menu Principale...")
    raise KeyboardInterrupt

"""
def select_broker(brokers):
    print("  - Seleziona conto")
    list_all_brokers = "\n".join(f"\t{key}. {value}" for key, value in brokers.items())
    print(list_all_brokers)
    brk = input("    > ")
    try:
        brk = int(brk)
        if brk not in list( range( 1, len(brokers)+1 ) ):
            raise ValueError
    except ValueError:
        wrong_input()
    return brokers[brk]
"""


def create_defaults(save_folder, broker_name):

    path1 = os.path.join(save_folder, "Report " + broker_name + ".csv")
    path2 = os.path.join(save_folder, "Template.csv")
    check1 = os.path.isfile(path1)
    check2 = os.path.isfile(path2)

    df_template = pd.DataFrame({
        "Data": ["01-01-2000"],
        "Operazione": [np.nan],
        "Prodotto": [np.nan],
        "Ticker": [np.nan],
        "Nome Asset": [np.nan],
        "TER": [np.nan],
        "Valuta": [np.nan],
        "Tasso di Conv.": [np.nan],
        "QT. Scambio": [np.nan],
        "Prezzo": [np.nan],
        "Prezzo EUR": [np.nan],
        "Imp. Nominale Operaz.": [np.nan],
        "Commissioni": [np.nan],
        "QT. Attuale": [np.nan],
        "PMC": [np.nan],
        "Imp. Residuo Asset": [np.nan],
        "Imp. Effettivo Operaz.": [np.nan],
        "Costo Rilasciato": [np.nan],
        "Plusv. Lorda": [np.nan],
        "Minusv. Generata": [np.nan],
        "Scadenza": [np.nan],
        "Zainetto Fiscale": [0.0],
        "Plusv. Imponibile": [np.nan],
        "Imposta": [np.nan],
        "P&L": [np.nan],
        "Liquidita Attuale": [0],
        "Valore Titoli": [0],
        "NAV": [0.0],
        "Liq. Storica Immessa": [0.0]
    })

    # if the reports folder is missing entirely OR 
    # if the reports folder is there, but Report.csv and Report-template.csv are missing:
    if (not os.listdir(save_folder)) or (not (check1 and check2)):
        # Se c'è già un report "riempito" ma manca il template, inizializza solo il template (sennò sovrascrivi il report)
        if check1 == True and check2 == False:
            df_template.to_csv(path2, index=False)
        else:
            df_template.to_csv(path1, index=False)
            df_template.to_csv(path2, index=False)
            





def display_information():
    print("--- INFORMAZIONI / LEGENDA ---")
    print("\nQuesta pagina funge da glossario relativo alle colonne della tabella.\n")
    print("- Data\n    Data dell'esecuzione dell'operazione.\n")
    print("- Operazione\n    Tipo di operazione (Acquisto, Vendita, Deposito...)\n")
    print("- Prodotto\n    Tipo di prodotto (Azione, ETF, Contanti...)\n")
    print("- Ticker\n    Ticker della security nel caso fosse specificata. Segue lo standard di Yahoo Finance.\n")
    print("- Nome Asset\n    Nome esaustivo della security.\n")
    print("- TER\n    Per prodotti idonei, Total Expense Ratio annualizzato.\n")
    print("- Valuta\n    Valuta dell'operazione (attualmente supportate: EUR, USD).\n")
    print("- Tasso di Conv.\n    Tasso di conversione EUR-USD dell'operazione.\n")
    print("- QT. Scambio\n    Quantità della security scambiata nell'operazione corrente. Positiva se Acquisto, negativa se Vendita.\n")
    print("- Prezzo\n    Prezzo unitario in valuta originale. Negativo se Acquisto, positivo se Vendita.\n")
    print("- Prezzo EUR\n    Prezzo unitario in EUR. Negativo se Acquisto, positivo se Vendita.\n")
    print("- Imp. Nominale Operaz.\n    Controvalore diretto dell'operazione. Nel caso di securities, è uguale a QT. Scambio * Prezzo EUR.\n")
    print("- Commissioni\n    Commissioni applicate dall'intermediario per l'operazione.\n")
    print("- QT. Attuale\n    Quantità attuale della security dopo l'operazione corrente.\n")
    print("- PMC\n    Prezzo Medio di Carico ponderato della security. I prezzi tengono conto delle commissioni.\n    ( somma[i=1->n] QT[i] * Prezzo[i] )  /  ( somma[i=1->n] QT[i] )\n")
    print("- Imp. Residuo\n    Importo Residuo dell'asset. Calcolato come PMC * QT. Attuale.\n")
    print("- Imp. Effettivo Operaz.\n    Importo effettivo dell'operazione al netto di eventuali commissioni.\n")
    print("- Costo Rilasciato\n    Costo rilasciato dopo la vendita di un asset. Calcolato come PMC * QT. Scambio.\n")
    print("- Plusv. Lorda\n    Plusvalenza lorda generata dalla vendita. Calcolata come Imp. Effettivo - Costo Rilasciato.\n")
    print("- Minusv. Generata\n    Minusvalenza generata dall'operazione. Per alcuni prodotti (es. ETF) si possono generare anche all'acquisto (minusvalenza da commissione).\n")
    print("- Scadenza\n    Data di scadenza della minusvalenza, oltre la quale non potrà più essere compensata.\n")
    print("- Zainetto Fiscale\n    Tiene conto del totale delle minusvalenze ancora da compensare, e provvede a rimuoverle eventualmente a scadenza.\n")
    print("- Plusv. Imponibile\n    Plusvalenza sul quale si andrà effettivamente a pagare l'imposta. Si riduce in caso di minusvalenze da compensare.\n    Supponendo plus=20€, zainetto=5€, si andrà a pagare l'imposta solo su 20-5 = 15€, invece che 20€.\n")
    print("- Imposta\n    Imposta pagata, calcolata sulla plusvalenza imponibile.\n")
    print("- P&L\n    Profit & Loss della vendita. Calcolata come Plusv. Lorda - Imposta.\n")
    print("- Liquidità Attuale\n    Liquidità disponibile nel conto dopo l'operazione.\n")
    print("- Valore Titoli\n    Valore dei titoli detenuti nel conto dopo l'operazione.\n")
    print("- NAV\n    Net Asset Value dopo l'operazione. Calcolato come Liquidità Attuale + Valore Titoli.\n")
    print("- Liq. Storica Immessa\n    Liquidità totale immessa nel conto. Tiene conto esclusivamente di depositi e prelievi.\n")

    input("Premi Invio per tornare al Menu Principale...")

