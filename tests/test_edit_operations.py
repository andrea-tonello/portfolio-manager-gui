"""Tests for editing an operation picked in Transactions: Operations shows its form filled in, and saves through journal_service.edit.

The operation keeps its id and order of entry. The operations after it are
recalculated, once the user agrees; an edit that would make a later one
impossible is refused, naming it. Prices are the fake market's.
"""

from datetime import date

import pytest
from conftest import set_operations, snack_texts
from test_ledger_snapshots import ETFS_AND_USD, NAMES, STOCKS_EUR, buy, deposit, sell
from test_transactions_view import tap_row

import views.operations_view
from domain.journal import Kind
from services import config_service, journal_service
from views import shell
from views.operations_view import OperationsView
from views.transactions_view import TransactionsView

# An ETF buy whose fee waits for the sale to enter the carryforward ("pending"), then a sale.
PENDING_FEE = [
    deposit(date(2024, 1, 2), 5_000),
    buy(date(2024, 2, 1), "EEE.MI", 10, price=50.0, fee=3.0, product="ETF-S", ter="0.2%", fee_mode="pending"),
    sell(date(2024, 5, 2), "EEE.MI", 5, price=60.0, fee=1.0, product="ETF-S", ter="0.2%", fee_mode="loss"),
]


@pytest.fixture
def open_edit(app, monkeypatch, immediately):
    """Return a function that opens Operations on the edit of `op` in account `idx`, as Edit in Transactions does.

    It returns the form shown. Background work runs straight away, and Yahoo
    (the tickers' kind and names) is answered without it.
    """
    monkeypatch.setattr(views.operations_view, "search_tickers", lambda *args, **kwargs: [])
    monkeypatch.setattr(views.operations_view, "fetch_ticker_name", lambda ticker: NAMES[ticker])

    def open_form(idx, op):
        """Edit `op` of account `idx`; return the form filled in with it."""
        app.edit_operation(idx, op.id)
        view = OperationsView(app)
        view.build()
        return next(form for form in (view.general, view.etf, view.stock) if form.editing is not None)

    return open_form


def _agree(page):
    """Answer the question about recalculating other operations, if one was asked: save."""
    if page.dialogs and page.dialogs[-1].open:
        page.dialogs[-1].actions[1].on_click(None)


@pytest.mark.parametrize("steps", [STOCKS_EUR, ETFS_AND_USD, PENDING_FEE], ids=["stocks", "etfs-and-usd", "pending-fee"])
def test_an_edit_saved_unchanged_leaves_every_operation_as_it_was(open_edit, page, state, steps):
    """Every operation, opened for editing and saved as shown, stays the very same operation.

    So each form shows every value as recorded: e.g. an ETF buy's fee left
    pending, a money-market ETF's tax bracket, a trade's exchange rate, the
    sale of shares no longer held, a split.
    """
    set_operations(state, 1, steps)
    journal = list(state.get_account(1).journal)

    for op in journal:
        open_edit(1, op).submit(None)
        _agree(page)

        assert snack_texts(page) == ["Changes saved"], op
        assert state.get_account(1).journal == journal, op


def test_an_edited_sales_fee_panel_describes_the_sale_as_it_will_be_saved(open_edit, state):
    """Editing the sale of EEE.MI, the panel counts the 3 EUR of purchase fees pending before it, which saving adds again.

    After the sale they are used up: read from its own row, the panel would
    say only the sale's fee is added.
    """
    set_operations(state, 1, PENDING_FEE)

    form = open_edit(1, state.get_account(1).journal[-1])

    assert form._sale_fee_text.value == "1.00€ + 3.00€ will be added to the Tax Carryforward"


def test_an_edit_that_cant_be_shown_any_more_is_given_up(app, state, open_edit):
    """A transfer being edited whose recipient is then deleted (in Settings) leaves Operations as without an edit.

    Its form can't show a recipient that no longer exists. Building it used to fail.
    """
    second = state.add_broker("Second Broker")
    set_operations(state, second, [deposit(date(2024, 1, 2), 1_000)])
    state.commit_changes(journal_service.record(state.accounts, state.get_account(1), Kind.TRANSFER_OUT,
                                                date(2025, 1, 10), amount=500.0, counterpart="Second Broker"))
    state.editing = (1, state.get_account(1).journal[-1].id)
    state.remove_broker(second)

    view = OperationsView(app)
    view.build()

    assert (view.editing, state.editing) == (None, None)


def test_leaving_an_edit_puts_back_what_the_user_had(app, page, state, open_edit, monkeypatch):
    """The account picked in Operations stays picked, and leaving for Home while the edit saves keeps Home shown.

    Saved meanwhile, the edit used to bring Transactions back over the tab
    the user went to, and Operations then showed the edited account.
    """
    state.ops_acc_idx = None
    state.split_checked_session = True  # Home's check for splits isn't what this is about
    form = open_edit(1, state.get_account(1).journal[-1])
    form.amount.value = "400"
    background = []
    monkeypatch.setattr(page, "run_thread", lambda fn, *args: background.append((fn, args)))

    form.submit(None)  # the save is under way...
    app.show_tab(shell.HOME_TAB)  # ...when the user goes to Home
    for fn, args in background:
        fn(*args)

    assert snack_texts(page) == ["Changes saved"]
    assert (state.last_nav_index, state.ops_acc_idx) == (shell.HOME_TAB, None)


def test_an_edited_dividend_changes_the_rows_after_it(app, page, state, open_edit):
    """The dividend of 15-04-2024 (12.5) picked in Transactions and edited to 20 adds 7.5 to the cash of the 6 operations after it.

    It keeps its id and order of entry, the question names the operations
    recalculated, and once saved Transactions is shown again.
    """
    config_service.save_tx_filter(state.user_config_folder, "count", 50)
    state.tx_selection = "1"
    transactions = TransactionsView(app)
    transactions.build()
    dividend = next(op for op in state.get_account(1).journal if op.kind == Kind.DIVIDEND)
    cash = state.get_account(1).last("cash_held")

    tap_row(transactions, "15-04-2024", "Dividend")
    page.dialogs[-1].actions[1].on_click(None)  # Edit
    assert (state.editing, state.last_nav_index) == ((1, dividend.id), shell.OPERATIONS_TAB)
    form = open_edit(1, dividend)
    assert (form.date.value, form.amount.value, form.ticker.value) == (date(2024, 4, 15), "12.5", "AAA.MI")
    form.amount.value = "20"
    form.submit(None)
    assert page.dialogs[-1].content.value.startswith("The change recalculates 6 other operations")
    page.dialogs[-1].actions[1].on_click(None)  # Save changes

    edited = next(op for op in state.get_account(1).journal if op.id == dividend.id)
    assert (edited.seq, edited.amount) == (dividend.seq, 20.0)
    assert state.get_account(1).last("cash_held") == pytest.approx(cash + 7.5)
    assert (state.editing, state.last_nav_index) == (None, shell.TRANSACTIONS_TAB)


def test_an_edit_that_leaves_a_later_sale_short_is_refused(open_edit, page, state):
    """The buy of 10 AAA.MI on 01-02-2024 edited to 4 leaves 4 for the sale of 5 on 03-06-2024: refused, naming it.

    No question comes first, nothing is saved, and the edit stays open to be changed.
    """
    journal = list(state.get_account(1).journal)
    buy_op = journal[2]
    form = open_edit(1, buy_op)
    form.quantity.value = "4"

    form.submit(None)

    [message] = snack_texts(page)
    assert message.startswith("The sale of AAA.MI on 03-06-2024 would no longer be possible")
    assert not page.dialogs or not page.dialogs[-1].open
    assert state.get_account(1).journal == journal
    assert state.editing == (1, buy_op.id)


def test_an_edited_transfer_changes_both_accounts_and_can_send_the_cash_it_sent(app, page, state, open_edit):
    """A transfer of 8,000 of the 8,723.12 held, edited to 8,500, is allowed: the cash it sent counts as available again.

    Picked from the account receiving it, it is edited from the one sending
    it, its recipient fixed. Both halves get the new amount.
    """
    second = state.add_broker("Second Broker")
    set_operations(state, second, [deposit(date(2024, 1, 2), 1_000)])
    state.commit_changes(journal_service.record(state.accounts, state.get_account(1), Kind.TRANSFER_OUT,
                                                date(2025, 1, 10), amount=8_000.0, counterpart="Second Broker"))
    sent, received = state.get_account(1).journal[-1], state.get_account(second).journal[-1]
    state.tx_selection = str(second)
    transactions = TransactionsView(app)
    transactions.build()

    tap_row(transactions, "10-01-2025", "Transfer in")
    page.dialogs[-1].actions[1].on_click(None)  # Edit
    assert state.editing == (1, sent.id)
    form = open_edit(1, sent)
    assert (form.kind, form.recipient.value, form.recipient.disabled) == ("transfer", str(second), True)
    assert form.amount.helper == "Available: 8,723.12€"
    form.amount.value = "8500"
    form.submit(None)

    amounts = [op.amount for acc in (1, second) for op in state.get_account(acc).journal if op.id in (sent.id, received.id)]
    assert amounts == [8_500.0, 8_500.0]
    assert (state.get_account(1).last("cash_held"), state.get_account(second).last("cash_held")) == \
        pytest.approx((223.12, 9_500))
