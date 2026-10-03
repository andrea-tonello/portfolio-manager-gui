import os
import pandas as pd

from domain.account import Account
from domain.ledger import opening_row
from utils.constants import REPORT_PREFIX


def report_filename(broker_name):
    """Return the file name of an account's CSV, e.g. "Report Fineco.csv" for the account "Fineco"."""
    return REPORT_PREFIX + broker_name + ".csv"


def report_path(folder, broker_name):
    """Return the path of an account's CSV inside `folder`, e.g. <folder>/Report Fineco.csv."""
    return os.path.join(folder, report_filename(broker_name))


def create_defaults(save_folder, broker_name):
    """Create the CSV of a new account `broker_name` in `save_folder`, holding only its opening row.

    Does nothing if the file already exists: it holds the user's transactions.
    """
    path_rep = report_path(save_folder, broker_name)
    df_template = pd.DataFrame({k: [v] for k, v in opening_row(broker_name).items()})

    if not os.path.isfile(path_rep):
        df_template.to_csv(path_rep, index=False)


def load_single_account(brokers: dict, save_folder: str, account_idx: int) -> Account:
    """Load the account `brokers[account_idx]` from its CSV in `save_folder`."""
    name = brokers[account_idx]
    path = report_path(save_folder, name)
    return Account(idx=account_idx, name=name, path=path, df=pd.read_csv(path))


def save_account(account: Account):
    """Write the account's ledger to its CSV."""
    account.df.to_csv(account.path, index=False)


def delete_account_files(broker_name: str, save_folder: str):
    """Delete CSV files for a given broker."""
    path = report_path(save_folder, broker_name)
    if os.path.exists(path):
        os.remove(path)
