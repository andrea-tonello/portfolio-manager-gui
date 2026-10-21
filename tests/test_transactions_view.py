"""Tests for the Transactions screen: the order it lists operations in, on screen and in the CSV export,
and removing the last one when it is a transfer.

Newest first, and operations of the same day from the last entered to the
first, so running totals such as the cash held read in sequence.
"""

import io
from datetime import date

import pandas as pd
import pytest
from test_ledger_snapshots import _replay, deposit

from services import operations_service
from utils.columns import export_headers
from views.transactions_view import TransactionsView

# Three deposits on the same day, between two others.
SAME_DAY = [
    deposit(date(2024, 1, 2), 1000),
    deposit(date(2024, 1, 3), 100),
    deposit(date(2024, 1, 3), 200),
    deposit(date(2024, 1, 3), 300),
    deposit(date(2024, 1, 4), 50),
]
CASH_HELD_NEWEST_FIRST = [1650.0, 1600.0, 1300.0, 1100.0, 1000.0]


@pytest.fixture
def view(app, state, tmp_path):
    """The Transactions screen showing an account that holds only the deposits above."""
    state.commit(1, _replay(SAME_DAY, tmp_path / "same_day"))
    state.tx_selection = "1"
    view = TransactionsView(app)
    view.build()
    return view


def test_screen_lists_newest_first(view):
    """The table lists the latest operation first; same-day ones from the last entered."""
    assert view._tx_filtered_df["cash_held"].tolist() == CASH_HELD_NEWEST_FIRST


def test_export_uses_the_screen_order(view, state):
    """The CSV export lists the operations in the same order as the screen.

    It used to sort by date alone, which leaves operations of the same day in
    an arbitrary order: here 1650, 1100, 1300, 1600, 1000.
    """
    csv_bytes = view._prepare_export_csv(state.get_account(1).transactions)

    exported = pd.read_csv(io.BytesIO(csv_bytes))
    assert exported[export_headers(state.translator)["cash_held"]].tolist() == CASH_HELD_NEWEST_FIRST


def _transfer_to_second_broker(state, tmp_path):
    """Open "Second Broker" and send it 500 from Test Broker (account 1); return its index."""
    second = state.add_broker("Second Broker")
    state.commit(second, _replay([deposit(date(2024, 1, 2), 1_000)], tmp_path / "second").assign(account="Second Broker"))
    sent, received = operations_service.execute_transfer(state.get_account(1), state.get_account(second),
                                                         "10-01-2025", date(2025, 1, 10), 500)
    state.commit(1, sent)
    state.commit(second, received)
    return second


def test_a_transfer_shows_which_way_the_cash_went(view, state, tmp_path):
    """The export names the other account with its direction, "to: Second Broker" and "from: Test Broker",
    while the ledger keeps the bare name, which removing a transfer looks its other half up by."""
    second = _transfer_to_second_broker(state, tmp_path)
    asset_name = export_headers(state.translator)["asset_name"]

    sent = pd.read_csv(io.BytesIO(view._prepare_export_csv(state.get_account(1).transactions)))
    received = pd.read_csv(io.BytesIO(view._prepare_export_csv(state.get_account(second).transactions)))

    assert (sent[asset_name][0], received[asset_name][0]) == ("to: Second Broker", "from: Test Broker")
    assert state.get_account(1).df.iloc[-1]["asset_name"] == "Second Broker"


def test_removing_a_transfer_asks_first_then_removes_it_from_both_accounts(app, page, state, tmp_path):
    """The last row being a transfer, Remove asks first, naming both accounts: Cancel keeps them, Remove takes both halves."""
    second = _transfer_to_second_broker(state, tmp_path)
    rows = (len(state.get_account(1).df), len(state.get_account(second).df))
    state.tx_selection = "1"
    view = TransactionsView(app)
    view.build()

    view._on_remove_row(None, 1)
    dialog = page.dialogs[-1]
    assert dialog.content.value == "It will be removed from both Test Broker and Second Broker."
    dialog.actions[0].on_click(None)  # Cancel
    assert (len(state.get_account(1).df), len(state.get_account(second).df)) == rows

    view._on_remove_row(None, 1)
    page.dialogs[-1].actions[1].on_click(None)  # Remove

    assert (len(state.get_account(1).df), len(state.get_account(second).df)) == (rows[0] - 1, rows[1] - 1)
