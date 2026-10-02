import pandas as pd
import numpy as np
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, ROUND_DOWN


def round_half_up(value, decimal="0.01"):
    """Round `value` to `decimal` places, halves away from zero (2.675 -> 2.68); NaN or None gives NaN.

    Raises ValueError for anything that isn't a finite number (text, infinity),
    so it can't end up in an account row.
    """
    if pd.isna(value):
        return np.nan
    try:
        return float(Decimal(str(value)).quantize(Decimal(decimal), rounding=ROUND_HALF_UP))
    except InvalidOperation as e:
        raise ValueError(f"cannot round {value!r}: not a finite number") from e


def round_down(value, decimal="0.01"):
    return float(Decimal(str(value)).quantize(Decimal(decimal), rounding=ROUND_DOWN))

