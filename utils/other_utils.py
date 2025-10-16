import pandas as pd
import numpy as np
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