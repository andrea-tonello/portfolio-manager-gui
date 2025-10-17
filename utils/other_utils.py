import pandas as pd
import numpy as np
import os
from decimal import Decimal, ROUND_HALF_UP, ROUND_DOWN

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


def select_broker(brokers):
    print("  - Seleziona intermediario/SIM")
    list_all_brokers = "\n".join(f"\t{key}. {value}" for key, value in brokers.items())
    print(list_all_brokers)
    brk = input("    > ")
    try:
        brk = int(brk)
        if brk not in list( range( 1, int(list(brokers.keys())[-1]) +1 ) ):
            raise ValueError
    except ValueError:
        wrong_input()
    return brokers[brk]


def create_defaults(save_folder):

    path1 = os.path.join(save_folder, "report.csv")
    path2 = os.path.join(save_folder, "report-template.csv")

    df_template = pd.DataFrame({
        "Data": ["01-01-2000"],
        "SIM": [np.nan],
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

    df_template.to_csv(path1, index=False)
    df_template.to_csv(path2, index=False)


def display_information():
    print("--- INFORMAZIONI / LEGENDA ---")
    print("\nQuesta pagina funge da glossario relativo alle colonne della tabella.\n")
    print("- Data\n    Data dell'esecuzione dell'operazione.\n")
    print("- SIM\n    Intermediario finanziario / SIM presso il quale è avvenuta l'operazione.\n")
    print("- Operazione\n    Tipo di operazione (Acquisto, Vendita, Deposito...)\n")
    print("- Prodotto\n    Tipo di prodotto (Azione, ETF, Contanti...)\n")
    print("- Ticker\n    Ticker della security nel caso fosse specificata. Segue lo standard di Yahoo Finance.\n")
    print("- Nome Asset\n    Nome esaustivo della security.\n")
    print("- TER\n    Per prodotti idonei, Total Expense Ratio annualizzato.\n")
    print("- Valuta\n    Valuta dell'operazione (attualmente supportate: EUR, USD).\n")
    print("- Tasso di Conv.\n    Tasso di conversione EUR-USD dell'operazione.\n")
    print("- QT. Scambio\n    Quantità della security scambiata nell'operazione corrente. Positiva se Acquisto, negativa se Vendita.\n")
    print("- Prezzo\n    Prezzo unitario in valuta originale. Negativo se Acquisto, positivo se Vendita.\n")
    print("- Prezzo EUR\n    Prezzo unitario EUR. Negativo se Acquisto, positivo se Vendita.\n")
    print("- Imp. Nominale Operaz.\n    Controvalore diretto dell'operazione. Nel caso di securities, è uguale a QT. Scambio * Prezzo EUR.\n")
    print("- Commissioni\n    Commissioni applicate dall'intermediario per l'operazione.\n")
    print("- QT. Attuale\n    Quantità attuale della security dopo l'operazione corrente.\n")


    input("Premi Invio per tornare al Menu Principale...")

