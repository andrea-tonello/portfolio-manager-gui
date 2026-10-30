"""Tests for recording, from the Operations screen, an operation dated before others of its account.

It takes its place by date, and the operations after it are recalculated
(journal_service.record), once the user agrees: a question names how many.
When it would make a later operation impossible, it is refused, naming that
operation, before any question, and nothing is saved.

The test account holds STOCKS_EUR, whose last operation is a withdrawal on
02-09-2024. Prices are the fake market's.
"""

from datetime import date
from pathlib import Path

import pytest
from conftest import set_operations, snack_texts
from test_ledger_snapshots import NAMES, buy, deposit, sell

import views.operations_view
from services.account_service import journal_path, ledger_path
from utils.columns import OP_ID
from views.operations_view import OperationsView


@pytest.fixture
def open_operations(app, state, monkeypatch, immediately):
    """Return a function that opens the Operations screen on the test account, whose operations are really recorded.

    Background work runs straight away, and the checks against Yahoo (the
    ticker's kind and name) are answered without it.
    """
    monkeypatch.setattr(views.operations_view, "search_tickers", lambda *args, **kwargs: [])
    monkeypatch.setattr(views.operations_view, "fetch_ticker_name", lambda ticker: NAMES[ticker])
    state.ops_acc_idx = 1

    def open_view():
        """Build the screen as it is shown, from the accounts as they are now."""
        view = OperationsView(app)
        view.build()
        return view

    return open_view


def _choose(form, kind):
    """Pick the operation `kind` in the General form, as tapping its segment does."""
    buttons = next(buttons for buttons in (form.cash_kind, form.corporate_kind)
                   if any(segment.value == kind for segment in buttons.segments))
    buttons.selected = [kind]
    buttons.on_change(None)


def test_a_deposit_dated_before_others_is_recorded_once_confirmed(open_operations, page, state):
    """1,000 deposited on 15-03-2024 raises by 1,000 the cash of the 8 operations after it, once the user agrees.

    The question names them; Cancel records nothing.
    """
    form = open_operations().general
    before = state.get_account(1).df.set_index(OP_ID)["cash_held"]
    later = [op.id for op in state.get_account(1).journal if op.date > date(2024, 3, 15)]
    form.date.value = date(2024, 3, 15)
    form.amount.value = "1000"

    form.submit(None)
    assert page.dialogs[-1].content.value == ("This operation comes before 8 later operations, which will be "
                                              "recalculated (taxes, Tax Carryforward and market values included).")
    page.dialogs[-1].actions[0].on_click(None)  # Cancel
    assert state.get_account(1).df.set_index(OP_ID)["cash_held"].equals(before)

    form.submit(None)
    page.dialogs[-1].actions[1].on_click(None)  # Record

    after = state.get_account(1).df.set_index(OP_ID)["cash_held"]
    assert (after[later] - before[later]).tolist() == pytest.approx([1_000] * 8)
    assert state.get_account(1).df["date"].tolist()[4:6] == ["01-03-2024", "15-03-2024"]


def test_a_sale_that_leaves_a_later_one_short_is_refused_without_asking(open_operations, page, state):
    """Selling 15 of 20 BBB.MI on 03-06-2024 leaves 5 for the sale of 10 on 01-08-2024: refused, naming that sale.

    The changes are worked out before asking, so an operation that can't be
    recorded gets no question about recalculating the later ones. The
    account's files, journal and ledger stay as they were.
    """
    set_operations(state, 1, [deposit(date(2024, 1, 2), 5_000), buy(date(2024, 5, 2), "BBB.MI", 20, price=50.0, fee=1.0),
                              sell(date(2024, 8, 1), "BBB.MI", 10, price=55.0, fee=1.0)])
    files = [Path(ledger_path(state.config_res_folder, "Test Broker")),
             Path(journal_path(state.config_res_folder, "Test Broker"))]
    saved = [path.read_bytes() for path in files]
    journal, ledger = list(state.get_account(1).journal), state.get_account(1).df.copy()
    form = open_operations().stock
    form.side_switch.value = True
    form.side_switch.on_change(None)  # Sell
    form.sell_ticker.value = "BBB.MI"
    form.date.value = date(2024, 6, 3)
    form.quantity.value, form.price.value, form.fee.value = "15", "60", "1"

    form.submit(None)

    [message] = snack_texts(page)
    assert message.startswith("The sale of BBB.MI on 01-08-2024 would no longer be possible: Quantity sold (10) exceeds")
    assert page.dialogs == []
    assert state.get_account(1).journal == journal and state.get_account(1).df.equals(ledger)
    assert [path.read_bytes() for path in files] == saved


def test_the_fee_panel_of_a_past_sale_uses_the_asset_as_it_was_on_that_day(open_operations, state):
    """A sale's fee panel reads the pending fees and the average buy price of the sale's date, not after later buys.

    EEE.MI is bought at 50 on 01-02-2024, its 3 EUR fee left pending, then
    at 100 on 02-05-2024, 2 more pending: by the end it averages 75, with 5
    pending. A sale at 60 on 01-03-2024 is at a gain on its own date
    (average 50), when 3 are pending: those are added to the carryforward.
    """
    set_operations(state, 1, [
        deposit(date(2024, 1, 2), 5_000),
        buy(date(2024, 2, 1), "EEE.MI", 10, price=50.0, fee=3.0, product="ETF-S", fee_mode="pending"),
        buy(date(2024, 5, 2), "EEE.MI", 10, price=100.0, fee=2.0, product="ETF-S", fee_mode="pending"),
    ])
    form = open_operations().etf
    form.side_switch.value = True
    form.side_switch.on_change(None)  # Sell
    form.sell_ticker.value = "EEE.MI"
    form.sell_ticker.on_select(None)
    form.fee_mode.value = "loss"
    form.fee_mode.on_change(None)  # Tax Carryforward: the panel shows
    form.price.value, form.fee.value = "60", "1"

    form.date.value = date(2024, 3, 1)
    form.date.on_change()  # as picking the date does

    assert form._sale_fee_text.value == "1.00€ + 3.00€ will be added to the Tax Carryforward"


def test_a_transfer_dated_in_the_past_rebuilds_both_accounts(open_operations, page, state):
    """500 sent on 10-06-2024 to an account with a deposit after that day goes before it in both accounts.

    The question counts the later operations of both (3 in the test account,
    1 in the other), and the amount's helper shows the cash held on the
    transfer's day, not after the last operation. Before the journal, a date
    before the recipient's last operation was refused.
    """
    second = state.add_broker("Second Broker")
    set_operations(state, second, [deposit(date(2024, 1, 2), 1_000), deposit(date(2024, 12, 2), 200)])
    form = open_operations().general
    _choose(form, "transfer")
    form.date.value = date(2024, 6, 10)
    form.date.on_change()  # as picking the date does
    assert form.amount.helper == "Available: 8,568.28€"
    form.recipient.value = str(second)
    form.amount.value = "500"

    form.submit(None)
    assert "comes before 4 later operations" in page.dialogs[-1].content.value
    page.dialogs[-1].actions[1].on_click(None)  # Record

    sent, received = state.get_account(1).df, state.get_account(second).df
    assert sent["operation"].tolist()[-4:] == ["Transfer Out", "Split", "Sell", "Withdrawal"]
    assert received["operation"].tolist()[-2:] == ["Transfer In", "Deposit"]
    assert (sent["cash_held"].iloc[-1], received["cash_held"].iloc[-1]) == pytest.approx((8_223.12, 1_700))
