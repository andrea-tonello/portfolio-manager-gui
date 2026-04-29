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
        "date": "01-01-2000",
        "account": broker_name,
        "carryforward": 0.0,
        "cash_held": 0,
        "assets_value": 0,
        "nav": 0.0,
        "committed_cash": 0.0,
    })
    df_template = pd.DataFrame({k: [v] for k, v in row.items()})

    if (not os.listdir(save_folder)) or (not check_rep):
        df_template.to_csv(path_rep, index=False)

