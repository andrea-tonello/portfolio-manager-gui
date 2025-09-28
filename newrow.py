import pandas as pd
import numpy as np
import openfigi as figi
from utils import buy_asset, sell_asset

def newrow_cash(df, date, cash, broker):
    op_type = "deposit" if cash > 0 else "withdrawal"
    net_final = cash

    new_row = pd.DataFrame({
        "Data": [date],
        "Operazione": [op_type],
        "SIM": [broker],
        "Prodotto": [np.nan],
        "ISIN": [np.nan],
        "Asset Name": [np.nan],
        "TER": [np.nan],
        "Valuta": ["EUR"],
        "QT. Scambio": [np.nan],
        "Prezzo": [np.nan],
        "Imp. Nominale Operaz.": [cash],
        "Commissioni": [np.nan],
        "QT. Attuale Asset": [np.nan],
        "Imp. Residuo Asset": [np.nan],
        "PMPC Asset": [np.nan],
        "Imp. Effettivo Operaz.": [cash],
        "Costo Rilasciato": [np.nan],
        "Plusv. Lorda": [np.nan],
        "Minusv. Generata": [np.nan],
        "Scadenza": [np.nan],
        "Zainetto Fiscale": [float(df["Zainetto Fiscale"].iloc[-1])],
        "Plusv. Imponibile": [np.nan],
        "Imposta": [np.nan],
        "Netto": [net_final],
        "Liquidita Attuale": [ float(df["Liquidita Attuale"].iloc[-1]) + net_final ],
        "Valore Titoli": [float(df["Valore Titoli"].iloc[-1])],
        "NAV": [ float(df["NAV"].iloc[-1]) + net_final ],
        "Liq. Storica Immessa": [ float(df["Liq. Storica Immessa"].iloc[-1]) + net_final ]
    })

    df = pd.concat([df, new_row], ignore_index=True)

    return df



def newrow_etf(df, date, isin, quantity, price, ter, broker, fee, buy):

    # BUY:  price -, coeff -1, buy=True
    # SELL: price +, coeff 1,  buy=False

    response = figi.lookup_by_isin(isin)
    name = figi.parse_response(response)["name"]
    asset_rows = df[df["ISIN"] == isin]

    if buy:
        results = buy_asset(df, asset_rows, quantity, price, fee)
    else:
        results = sell_asset(df, asset_rows, quantity, price, fee, date)


    #current_qt, total_imp_eff = search_asset(asset_rows)
    #pv_mv, net_final = plus_minus(total_imp_eff, (quantity * price - fee))
    #credit = calculate_credit()

    new_row = pd.DataFrame({
        "Data": [date],
        "Operazione": [results["Operazione"]],
        "SIM": [broker],
        "Prodotto": ["ETF"],
        "ISIN": [isin],
        "Asset Name": [name],
        "TER": [ter],
        "Valuta": ["EUR"],
        "QT. Scambio": [quantity],
        "Prezzo": [price],
        "Imp. Nominale Operaz.": [(quantity * price)],
        "Commissioni": [fee],
        "QT. Attuale Asset": [results["QT. Attuale Asset"]],
        "Imp. Residuo Asset": [results["Imp. Residuo Asset"]],
        "PMPC Asset": [results["PMPC Asset"]], #else asset_rows["PMPC Asset"].iloc[-1
        "Imp. Effettivo Operaz.": [(quantity * price - fee)],
        "Costo Rilasciato": [results["Costo Rilasciato"]],
        "Plusv. Lorda": [results["Plusv. Lorda"]],
        "Minusv. Generata": [results["Minusv. Generata"]],
        "Scadenza": [results["Scadenza"]],
        "Zainetto Fiscale": [results["Zainetto Fiscale"]],
        "Plusv. Imponibile": [results["Plusv. Imponibile"]],
        "Imposta": [results["Imposta"]],
        "Netto": [results["Netto"]],
        "Liquidita Attuale": [results["Liquidita Attuale"]], #else abs(total_imp_eff) + net_final)
        "Valore Titoli": [results["Valore Titoli"]],
        "NAV": [results["NAV"]], # else df["NAV"].iloc[-1] + fee + net_final
        "Liq. Storica Immessa": [ float(df["Liq. Storica Immessa"].iloc[-1])],
    })

    df = pd.concat([df, new_row], ignore_index=True)

    return df


# Esempio su plusvalenza e feei:
#   Acquisto 100 azioni a 10 € = 1.000 €
#   feee acquisto = 5 €
#   -> Costo totale di carico = 1.005 €
#   Rivendo a 12 € = 1.200 €
#   feee vendita = 5 €
#   Incasso netto = 1.195 €

# Plusvalenza imponibile = 1.195 – 1.005 = 190 €
# L’imposta sostitutiva del 26% si applica quindi su 190 €, non sui 200 € “lordi”.

# Calcolo della Minusvalenza
#   Acquisto 100 azioni a 10 € = 1.000 €
#   feee acquisto = 5 €
#   -> Costo totale di carico = 1.005 €
#   Rivendo a 8 € = 800 €
#   feee vendita = 5 €
#   Incasso netto = 795 €

# Minusvalenza = Incasso netto - Costo totale di carico
# Minusvalenza = 795 € - 1.005 € = -210 €

"""
La normativa italiana prevede che il prezzo medio ponderato di carico (PMPC) 
si calcoli comprensivo delle feei di acquisto e che anche il ricavo di vendita 
si consideri al netto delle feei di vendita.




def PMPC(df, quantity, price):
    asset_rows = df.copy()

    # Ensure numeric types
    asset_rows["QT. Attuale Asset"] = pd.to_numeric(asset_rows["QT. Attuale Asset"], errors="coerce")
    asset_rows["Importo Nominale"] = pd.to_numeric(asset_rows.get("Importo Nominale"), errors="coerce")
    asset_rows["QT. Scambio"] = pd.to_numeric(asset_rows.get("QT. Scambio"), errors="coerce")

    # Find last row where a sell brought asset quantity to zero
    sell_zero_mask = (asset_rows["Operazione"] == "sell") & (asset_rows["QT. Attuale Asset"] == 0)
    sell_zero_indices = asset_rows.index[sell_zero_mask]

    # First ever data point for that ISIN
    if asset_rows.empty:                   
        return price

    # ISIN already logged, but no 0-sell event yet
    if sell_zero_indices.empty:         
        last_pmpc = asset_rows["PMPC Asset"].iloc[-1]
        last_remaining_qt = asset_rows["QT. Attuale Asset"].iloc[-1]
        numerator = last_pmpc * last_remaining_qt + price * quantity
        return (numerator / (last_remaining_qt + quantity))

    else:        
        last_sell_index = sell_zero_indices[-1]
        rows_to_weight = asset_rows.loc[asset_rows.index > last_sell_index]

    # Weighted average calculation
    weighted_sum = abs(rows_to_weight["Importo Nominale"].sum()) + (quantity * abs(price))
    qt_total = abs(rows_to_weight["QT. Scambio"].sum()) + quantity

    return weighted_sum / qt_total if qt_total != 0 else abs(price)






def PMPC(df, quantity, price):

    asset_rows = df.copy()
    asset_rows["QT. Attuale Asset"] = pd.to_numeric(asset_rows["QT. Attuale Asset"], errors="coerce")
    
    # Find the last row where sell operation resulted in zero quantity
    sell_zero_mask = (asset_rows["Operazione"] == "sell") & (asset_rows["QT. Attuale Asset"] == 0)
    sell_zero_indices = asset_rows[sell_zero_mask].index
    
    if sell_zero_indices.empty and asset_rows.shape[0] == 0:   # First ever data point for that ISIN
        return abs(price)  
    
    if sell_zero_indices.empty:                             # ISIN already logged, but no 0-sell event yet
        rows_to_weight = asset_rows
        rows_to_weight["Importo Nominale"] = pd.to_numeric(rows_to_weight["Importo Nominale"], errors="coerce")
        rows_to_weight["QT. Scambio"] = pd.to_numeric(rows_to_weight["QT. Scambio"], errors="coerce")

        weighted_sum = abs(rows_to_weight["Importo Nominale"].sum()) + (quantity * abs(price))
        qt_total = abs(float(rows_to_weight["QT. Scambio"].sum())) + quantity

        return weighted_sum / qt_total

    last_sell_index = sell_zero_indices[-1]
    
    # Return rows after the last sell-to-zero
    rows_to_weight = asset_rows[asset_rows.index > last_sell_index]
    rows_to_weight["Importo Nominale"] = pd.to_numeric(rows_to_weight["Importo Nominale"], errors="coerce")
    rows_to_weight["QT. Scambio"] = pd.to_numeric(rows_to_weight["QT. Scambio"], errors="coerce")


    weighted_sum = abs(rows_to_weight["Importo Nominale"].sum()) + (quantity * abs(price))
    qt_total = abs(float(rows_to_weight["QT. Scambio"].sum())) + quantity

    pmpc = weighted_sum / qt_total

    return pmpc

"""