import pandas as pd
import numpy as np
import os
from decimal import Decimal, ROUND_HALF_UP, ROUND_DOWN

from utils.constants import REPORT_PREFIX


class ValidationError(Exception):
    """Raised when user input or business logic validation fails."""
    pass


def round_half_up(valore, decimal="0.01"):
    if pd.isna(valore):
        return np.nan
    try:
        return float(Decimal(str(valore)).quantize(Decimal(decimal), rounding=ROUND_HALF_UP))
    except Exception:
        return valore


def round_down(value, decimal="0.01"):
    return float(Decimal(str(value)).quantize(Decimal(decimal), rounding=ROUND_DOWN))


def create_defaults(save_folder, broker_name):
    from newrow import _base_row

    path_rep = os.path.join(save_folder, REPORT_PREFIX + broker_name + ".csv")
    check_rep = os.path.isfile(path_rep)

    row = _base_row()
    row.update({
        "Data": "01-01-2000",
        "Conto": broker_name,
        "Zainetto Fiscale": 0.0,
        "Liquidita Attuale": 0,
        "Valore Titoli": 0,
        "NAV": 0.0,
        "Liq. Impegnata": 0.0,
    })
    df_template = pd.DataFrame({k: [v] for k, v in row.items()})

    if (not os.listdir(save_folder)) or (not check_rep):
        df_template.to_csv(path_rep, index=False)


_GLOSSARY_KEYS = {
    1: [
        "glossary.page_1.title", "glossary.page_1.date", "glossary.page_1.account",
        "glossary.page_1.operation", "glossary.page_1.product", "glossary.page_1.ticker",
        "glossary.page_1.asset_name", "glossary.page_1.ter", "glossary.page_1.currency",
        "glossary.page_1.exch_rate", "glossary.page_1.qt_exch", "glossary.page_1.price",
        "glossary.page_1.eur_price", "glossary.page_1.nominal_value", "glossary.page_1.fees",
        "glossary.page_1.qt_held", "glossary.page_1.avg_price", "glossary.page_1.eff_value",
        "glossary.page_1.released_value", "glossary.page_1.gross_cap_gain",
        "glossary.page_1.cap_loss", "glossary.page_1.exp_date", "glossary.page_1.backpack",
        "glossary.page_1.cap_gain_tax", "glossary.page_1.tax_amount", "glossary.page_1.pl",
        "glossary.page_1.cash_held", "glossary.page_1.assets_value", "glossary.page_1.nav",
        "glossary.page_1.historic_cash",
    ],
    2: [
        "glossary.page_2.title", "glossary.page_2.return", "glossary.page_2.xirr",
        "glossary.page_2.twrr", "glossary.page_2.volatility", "glossary.page_2.sharpe_ratio",
        "glossary.page_2.corr", "glossary.page_2.corr_roll", "glossary.page_2.drawdown",
        "glossary.page_2.var",
    ],
}
