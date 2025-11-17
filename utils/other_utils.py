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



def wrong_input(error="error not specified", suppress_error=False):
    if suppress_error:
        print("\n" + error)
    else:
        print("\nI dati inseriti non sono corretti:")
        print("ERRORE: " + error)
    input("\nPremi Invio per tornare al Menu Principale...")
    raise KeyboardInterrupt


def create_defaults(save_folder, broker_name):

    path_rep = os.path.join(save_folder, "Report " + broker_name + ".csv")
    path_temp = os.path.join(save_folder, "Template.csv")
    check_rep = os.path.isfile(path_rep)
    check_temp = os.path.isfile(path_temp)

    df_template = pd.DataFrame({
        "Data": ["01-01-2000"],
        "Conto": broker_name,
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
        "Liq. Impegnata": [0.0]
    })

    # if the reports folder is missing entirely OR 
    # if the reports folder is there, but Report.csv and Report-template.csv are missing:
    if (not os.listdir(save_folder)) or (not (check_rep and check_temp)):
        # If somehow there's a filled report but no template, initialize JUST the template (otherwise the report will be overwritten)
        if check_rep == True and check_temp == False:
            df_template.to_csv(path_temp, index=False)
        else:
            df_template.to_csv(path_rep, index=False)
            df_template.to_csv(path_temp, index=False)
            

def display_information(page):
    os.system("cls" if os.name == "nt" else "clear")
    if page == 1:
        print("\nPagina 1.\nQuesta pagina funge da glossario relativo alle colonne della tabella.\n")
        print("- Data\n    Data dell'esecuzione dell'operazione.\n")
        print("- Conto\n    Conto sul quale è stata svolta l'operazione.\n")
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
        print("- Liq. Impegnata\n    Liquidità totale immessa nel conto. Tiene conto esclusivamente di depositi e prelievi.\n\n")

    else:
        print("\nPagina 2.\nQuesta pagina fornisce informazioni sugli strumenti statistici usati nell'analisi di portafoglio.\n")

        print("- Tipologie di rendimento")
        print("    XIRR (Extended Internal Rate of Return).")
        print("\tL'IRR è un metodo numerico per calcolare il Tasso Interno di Rendimento di una serie di flussi di cassa (entrate e uscite); lo XIRR è una variante")
        print("\tutilizzata quando i flussi si verificano a intervalli di tempo non regolari. Si calcola come il tasso che azzera il Valore Attuale Netto (NPV) di tutti i flussi.")
        print("\tUtile a misurare il proprio rendimento personale, tenendo conto delle scelte di investimento e disinvestimento.")
        
        print("    TWRR (Time-Weighted Rate of Return).")
        print("\tSi concentra sul rendimento degli asset e non sul rendimento effettivo dell'investitore (in pratica, escludendo i flussi di cassa).")
        print("\tIl calcolo si basa sulla media geometrica dei rendimenti di tutti i sottoperiodi in cui è suddiviso l'investimento (es. giornaliero, mensile).")
        print("\tUtile nel confronto di performance con benchmark/indici o nella misurazione di statistiche, quali lo Sharpe Ratio.\n")
        
        print("- Volatilità\n    Deviazione standard dei rendimenti su un determinato periodo di tempo.\n")
        print("- Sharpe Ratio\n    Misura la performance di un investimento confrontato con un asset 'risk-free' (ad esempio un tasso d'interesse di prestiti statali AAA a breve scadenza).")
        print("    Si calcola come la differenza tra i ritorni dell'investimento ed i ritorni risk-free, chiamata excess returns, diviso la deviazione standard degli excess returns.\n")

        print("- Correlazione semplice\n    Misura, tramite un coefficiente compreso tra -1 ed 1, quanto due asset siano correlati tra loro in un dato momento.")
        print("    +1: i due asset sono positivamente correlati: all'aumentare del primo, aumenta il secondo (e viceversa).")
        print("     0: i due asset sono perfettamente decorrelati: il cambiamento del primo non influisce in alcun modo sul secondo (e viceversa).")
        print("    -1: i due asset sono negativamente correlati: all'aumentare del primo, diminuisce il secondo (e viceversa).\n")
        print("- Correlazione scorrevole (rolling)\n    È calcolata in maniera analoga alla precedente, ma lungo un intervallo di tempo prestabilito (es. 5 anni); inoltre, viene applicata")
        print("    una media mobile con intervallo specificato (in giorni). Offre una misura di cambiamento della correlazione tra due asset nel tempo.\n")
        print("- Drawdown\n    Misura il declino percentuale del valore del portafoglio (o di un asset) dal suo picco storico al susseguente minimo.\n    Il Maximum Drawdown, in particolare, riporta la differenza maggiore.\n")
        print("- Value at Risk (VaR)\n    Massima perdita attesa su un orizzonte di tempo specificato in giorni, dato un intervallo di confidenza.")
        print("    L'implementazione qui utilizzata si basa su metodo Monte Carlo, utilizzando dati storici per le stime dei ritorni.\n\n")

    input("Premi Invio per tornare al Menu Principale...")

