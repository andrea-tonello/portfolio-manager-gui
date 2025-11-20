import pandas as pd
import numpy as np
import os
from decimal import Decimal, ROUND_HALF_UP, ROUND_DOWN


def round_half_up(valore, decimal="0.01"):
    if pd.isna(valore):
        return np.nan
    try:
        return float(Decimal(str(valore)).quantize(Decimal(decimal), rounding=ROUND_HALF_UP))
    except Exception:
        print(f"Warning: unable to round value {valore}")
        return valore
    

def round_down(value, decimal="0.01"):
    return float(Decimal(str(value)).quantize(Decimal(decimal), rounding=ROUND_DOWN))


def wrong_input(translator, error="error not specified", suppress_error=False):
    if suppress_error:
        print("\n" + error)
    else:
        print(translator.get("misc.wrong_input"))
        print(translator.get("misc.which_error") + error)
    input(translator.get("redirect.continue_home"))
    raise KeyboardInterrupt


def create_defaults(save_folder, broker_name):
    path_rep = os.path.join(save_folder, "Report " + broker_name + ".csv")
    check_rep = os.path.isfile(path_rep)

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
    # if the reports folder is there, but Report.csv is missing:
    if (not os.listdir(save_folder)) or (not check_rep):
        df_template.to_csv(path_rep, index=False)
            

def display_information(translator, page):
    os.system("cls" if os.name == "nt" else "clear")
    if page == 1:
        print(translator.get("glossary.page_1.title"))
        print(translator.get("glossary.page_1.date"))
        print(translator.get("glossary.page_1.account"))
        print(translator.get("glossary.page_1.operation"))
        print(translator.get("glossary.page_1.product"))
        print(translator.get("glossary.page_1.ticker"))
        print(translator.get("glossary.page_1.asset_name"))
        print(translator.get("glossary.page_1.ter"))
        print(translator.get("glossary.page_1.currency"))
        print(translator.get("glossary.page_1.exch_rate"))
        print(translator.get("glossary.page_1.qt_exch"))
        print(translator.get("glossary.page_1.price"))
        print(translator.get("glossary.page_1.eur_price"))
        print(translator.get("glossary.page_1.nominal_value"))
        print(translator.get("glossary.page_1.fees"))
        print(translator.get("glossary.page_1.qt_held"))
        print(translator.get("glossary.page_1.avg_price"))
        print(translator.get("glossary.page_1.eff_value"))
        print(translator.get("glossary.page_1.released_value"))
        print(translator.get("glossary.page_1.gross_cap_gain"))
        print(translator.get("glossary.page_1.cap_loss"))
        print(translator.get("glossary.page_1.exp_date"))
        print(translator.get("glossary.page_1.backpack"))
        print(translator.get("glossary.page_1.cap_gain_tax"))
        print(translator.get("glossary.page_1.tax_amount"))
        print(translator.get("glossary.page_1.pl"))
        print(translator.get("glossary.page_1.cash_held"))
        print(translator.get("glossary.page_1.assets_value"))
        print(translator.get("glossary.page_1.nav"))
        print(translator.get("glossary.page_1.historic_cash"))
    else:
        print(translator.get("glossary.page_2.title"))
        print(translator.get("glossary.page_2.return"))
        print(translator.get("glossary.page_2.xirr"))
        print(translator.get("glossary.page_2.twrr"))
        print(translator.get("glossary.page_2.volatility"))
        print(translator.get("glossary.page_2.sharpe_ratio"))
        print(translator.get("glossary.page_2.corr"))
        print(translator.get("glossary.page_2.corr_roll"))
        print(translator.get("glossary.page_2.drawdown"))
        print(translator.get("glossary.page_2.var"))

    input(translator.get("redirect.continue_home"))

