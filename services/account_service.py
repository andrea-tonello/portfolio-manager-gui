import os
import pandas as pd

from utils.constants import REPORT_PREFIX


def load_single_account(brokers: dict, save_folder: str, account_idx: int) -> dict:
    filename = REPORT_PREFIX + brokers[account_idx] + ".csv"
    path = os.path.join(save_folder, filename)
    df = pd.read_csv(path)
    return {
        "acc_idx": account_idx,
        "df": df,
        "file": filename,
        "path": path,
        "len_df_init": len(df),
        "edited_flag": False,
    }


def load_all_accounts(brokers: dict, save_folder: str) -> list[dict]:
    accounts = []
    for idx in sorted(brokers.keys()):
        accounts.append(load_single_account(brokers, save_folder, idx))
    return accounts


def save_account(df: pd.DataFrame, path: str):
    """Save account DataFrame to its internal config path."""
    df.to_csv(path, index=False)


def delete_account_files(broker_name: str, save_folder: str, user_folder: str):
    """Delete CSV files for a given broker."""
    filename = REPORT_PREFIX + broker_name + ".csv"
    for folder in (save_folder, user_folder):
        path = os.path.join(folder, filename)
        if os.path.exists(path):
            os.remove(path)
