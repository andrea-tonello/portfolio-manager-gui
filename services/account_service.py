import os
import pandas as pd

from domain.ledger import opening_row
from utils.columns import rename_from_legacy
from utils.constants import REPORT_PREFIX


def create_defaults(save_folder, broker_name):
    """Create the CSV of a new account `broker_name` in `save_folder`, holding only its opening row.

    Does nothing if the file already exists: it holds the user's transactions.
    """
    path_rep = os.path.join(save_folder, REPORT_PREFIX + broker_name + ".csv")
    df_template = pd.DataFrame({k: [v] for k, v in opening_row(broker_name).items()})

    if not os.path.isfile(path_rep):
        df_template.to_csv(path_rep, index=False)


def load_single_account(brokers: dict, save_folder: str, account_idx: int) -> dict:
    filename = REPORT_PREFIX + brokers[account_idx] + ".csv"
    path = os.path.join(save_folder, filename)
    df = pd.read_csv(path)

    # Auto-migrate legacy Italian column names to English
    if rename_from_legacy(df):
        df.to_csv(path, index=False)

    return {
        "df": df,
        "file": filename,
        "path": path,
    }


def save_account(df: pd.DataFrame, path: str):
    """Save account DataFrame to its internal config path."""
    df.to_csv(path, index=False)


def delete_account_files(broker_name: str, save_folder: str):
    """Delete CSV files for a given broker."""
    filename = REPORT_PREFIX + broker_name + ".csv"
    path = os.path.join(save_folder, filename)
    if os.path.exists(path):
        os.remove(path)
