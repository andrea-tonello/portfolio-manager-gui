"""Tests for the Transactions screen: the order it lists operations in, on screen and in the CSV export,
and removing an operation: the last one, or that of a row tapped.

Newest first, and operations of the same day from the last entered to the
first, so running totals such as the cash held read in sequence.
"""

import asyncio
import io
from datetime import date

import flet as ft
import pandas as pd
import pytest
from conftest import find_controls, set_operations, snack_texts
from test_exports import FakeFilePicker
from test_ledger_snapshots import deposit

from domain.journal import Kind
from services import config_service, journal_service
from utils.columns import OP_ID, export_headers
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
def view(app, state):
    """The Transactions screen showing an account that holds only the deposits above."""
    set_operations(state, 1, SAME_DAY)
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


def test_an_accounts_export_is_named_report_and_leaves_out_the_operation_ids(app, state):
    """Exporting an account offers "Report <account>.csv", with only the ledger's own columns.

    The ledger itself is now report-<account>.csv, and carries the internal
    op_id column (the journal operation of each row), which isn't for the user.
    """
    state.load_all_accounts()  # read back from its file, op_id column included
    view = TransactionsView(app)
    view.build()
    view.file_picker = FakeFilePicker("/home/me/Report Test Broker.csv")

    asyncio.run(view._on_export(None, 1))

    saved = view.file_picker.calls[0]
    assert saved["file_name"] == "Report Test Broker.csv"
    header = saved["src_bytes"].decode("utf-8").splitlines()[0].split(",")
    assert header == list(export_headers(state.translator).values())


def test_remove_last_undoes_the_operation_entered_last_whatever_its_date(app, page, state, immediately):
    """A split found on Yahoo goes on its own past date; "remove last" then removes it, not the latest-dated operation.

    The test account's last operation is a withdrawal on 02-09-2024; the
    split of 15-08-2024 is entered after it, so removing it asks first: the
    withdrawal is recalculated.
    """
    state.commit_changes(journal_service.record(state.accounts, state.get_account(1), Kind.SPLIT, date(2024, 8, 15),
                                                ticker="BBB.MI", ratio=2.0))
    view = TransactionsView(app)
    view.build()

    view._on_remove_row(None, 1)
    assert page.dialogs[-1].content.value.startswith("Removing it recalculates 1 other operation")
    page.dialogs[-1].actions[1].on_click(None)  # Remove

    ledger = state.get_account(1).df
    assert [op.kind for op in state.get_account(1).journal][-2:] == ["sell", "withdrawal"]
    assert ledger[(ledger["operation"] == "Split") & (ledger["ticker"] == "BBB.MI")].empty


@pytest.fixture
def every_row(app, state, immediately):
    """The Transactions screen listing all of the test account's operations (50 at most), its work run straight away."""
    config_service.save_tx_filter(state.user_config_folder, "count", 50)
    state.tx_selection = "1"
    view = TransactionsView(app)
    view.build()
    return view


def tap_row(view, *texts):
    """Tap the row of the table showing each of `texts` (e.g. its date and operation), as the user does."""
    [table] = find_controls(view.tx_table_container, ft.DataTable)
    row = next(row for row in table.rows if all(text in [cell.content.value for cell in row.cells] for text in texts))
    row.on_select_change(None)


def test_a_row_tapped_can_be_removed_and_the_rows_after_it_are_rebuilt(every_row, page, state):
    """Tapping the dividend of 15-04-2024 offers to edit or remove it; removed, the 6 operations after it lose its 12.5.

    The question naming them comes before anything is saved.
    """
    view = every_row
    journal = state.get_account(1).journal
    dividend = next(op for op in journal if op.kind == Kind.DIVIDEND)
    later = [op.id for op in journal if op.date > dividend.date]
    before = state.get_account(1).df.set_index(OP_ID)["cash_held"]

    tap_row(view, "15-04-2024", "Dividend")
    menu = page.dialogs[-1]
    assert (menu.title.value, menu.content.value) == ("Dividend AAA.MI", "15-04-2024 · Test Broker")
    assert [action.content for action in menu.actions] == ["Cancel", "Edit", "Remove"]
    menu.actions[2].on_click(None)  # Remove
    assert page.dialogs[-1].content.value.startswith("Removing it recalculates 6 other operations")
    page.dialogs[-1].actions[1].on_click(None)  # Remove

    after = state.get_account(1).df.set_index(OP_ID)["cash_held"]
    assert dividend not in state.get_account(1).journal
    assert (before[later] - after[later]).tolist() == pytest.approx([12.5] * 6)


def test_removing_a_buy_a_later_sale_needs_is_refused(every_row, page, state):
    """Removing the buy of 10 AAA.MI on 01-02-2024 leaves none for the sale of 03-06-2024: refused, naming it.

    No question comes first, and the account stays as it was.
    """
    journal, ledger = list(state.get_account(1).journal), state.get_account(1).df.copy()

    tap_row(every_row, "01-02-2024", "Buy")
    page.dialogs[-1].actions[2].on_click(None)  # Remove

    [message] = snack_texts(page)
    assert message.startswith("The sale of AAA.MI on 03-06-2024 would no longer be possible")
    assert not page.dialogs[-1].open  # the row's dialog, closed: no question followed it
    assert state.get_account(1).journal == journal and state.get_account(1).df.equals(ledger)


def test_a_row_whose_operation_is_gone_says_so(every_row, page, state):
    """Tapping a row of an operation removed since the list was shown says so, and shows the list again.

    E.g. tapped just after its removal was saved, before the list came
    back. The tap used to fail without a word.
    """
    withdrawal = journal_service.last_entered(state.get_account(1))
    state.commit_changes(journal_service.delete(state.accounts, state.get_account(1), withdrawal.id))

    tap_row(every_row, "02-09-2024", "Withdrawal")

    assert snack_texts(page) == ["This transaction is no longer among the account's operations."]
    assert not page.dialogs


def test_no_other_change_starts_while_one_waits_for_its_answer(every_row, page, state):
    """While the question about removing the dividend is open, "remove last" is refused, saying why; once cancelled, it works.

    One change at a time, from the tap until it is saved or cancelled:
    worked out meanwhile, the second would be refused when saved anyway.
    """
    operations = len(state.get_account(1).journal)
    tap_row(every_row, "15-04-2024", "Dividend")
    page.dialogs[-1].actions[2].on_click(None)  # Remove: the question opens

    every_row._on_remove_row(None, 1)
    assert snack_texts(page) == ["Another change is being saved: try again in a moment."]
    assert len(state.get_account(1).journal) == operations

    page.dialogs[-1].actions[0].on_click(None)  # Cancel
    every_row._on_remove_row(None, 1)
    assert len(state.get_account(1).journal) == operations - 1


def _transfer_to_second_broker(state):
    """Open "Second Broker" and send it 500 from Test Broker (account 1); return its index."""
    second = state.add_broker("Second Broker")
    set_operations(state, second, [deposit(date(2024, 1, 2), 1_000)])
    state.commit_changes(journal_service.record(state.accounts, state.get_account(1), Kind.TRANSFER_OUT,
                                                date(2025, 1, 10), amount=500.0, counterpart="Second Broker"))
    return second


def test_a_transfer_shows_which_way_the_cash_went(view, state):
    """The export names the other account with its direction, "to: Second Broker" and "from: Test Broker",
    while the ledger keeps the bare name, which doesn't depend on the language."""
    second = _transfer_to_second_broker(state)
    asset_name = export_headers(state.translator)["asset_name"]

    sent = pd.read_csv(io.BytesIO(view._prepare_export_csv(state.get_account(1).transactions)))
    received = pd.read_csv(io.BytesIO(view._prepare_export_csv(state.get_account(second).transactions)))

    assert (sent[asset_name][0], received[asset_name][0]) == ("to: Second Broker", "from: Test Broker")
    assert state.get_account(1).df.iloc[-1]["asset_name"] == "Second Broker"


def test_removing_a_transfer_asks_first_then_removes_it_from_both_accounts(app, page, state, immediately):
    """The last row being a transfer, Remove asks first, naming both accounts: Cancel keeps them, Remove takes both halves."""
    second = _transfer_to_second_broker(state)
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
