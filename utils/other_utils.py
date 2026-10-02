import pandas as pd
import numpy as np
from decimal import Decimal, ROUND_HALF_UP, ROUND_DOWN


def round_half_up(value, decimal="0.01"):
    if pd.isna(value):
        return np.nan
    try:
        return float(Decimal(str(value)).quantize(Decimal(decimal), rounding=ROUND_HALF_UP))
    except Exception:
        return value


def round_down(value, decimal="0.01"):
    return float(Decimal(str(value)).quantize(Decimal(decimal), rounding=ROUND_DOWN))

