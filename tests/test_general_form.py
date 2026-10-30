"""Tests for the General tab of the Operations screen: cash operations, transfers and splits,
plus the date picker shared by every Operations tab.

The form records the operation through the journal (journal_service.record):
amounts are typed, and passed on, as positive numbers, and the operation's
kind (deposit or withdrawal, for example) gives the row its sign.
"""

from datetime import date, datetime

import pytest
from conftest import set_operations, snack_texts
from test_ledger_snapshots import NAMES, deposit

import views.operations_view
from domain.journal import Kind
from services import journal_service
from views.operations_view import OperationsView


@pytest.fixture
def general_form(monkeypatch, app, page, state):
    """The General tab for the test account, dated after its last operation, with operations recorded instead of saved.

    Returns (form, submit, calls): the GeneralForm, a function that presses
    "Add transaction", and the (kind, day, fields) of each operation that
    reached journal_service.record. Background work runs straight away, and
    a dividend's asset name comes without asking Yahoo.
    """
    calls = []

    def record(accounts, account, kind, day, **fields):
        """Stand-in for journal_service.record: remember the operation and change no account."""
        calls.append((kind, day, fields))
        return {}

    monkeypatch.setattr(journal_service, "record", record)
    monkeypatch.setattr(views.operations_view, "fetch_ticker_name", lambda ticker: NAMES[ticker])
    monkeypatch.setattr(page, "run_thread", lambda fn, *args: fn(*args))

    state.ops_acc_idx = 1
    view = OperationsView(app)
    view.build()
    form = view.general
    form.date.value = date(2025, 1, 10)
    return form, lambda: form.submit(None), calls


def _choose(form, kind):
    """Pick the operation `kind` as the user does: its segment, in whichever button offers it."""
    buttons = next(buttons for buttons in (form.cash_kind, form.corporate_kind)
                   if any(segment.value == kind for segment in buttons.segments))
    buttons.selected = [kind]
    buttons.on_change(None)


@pytest.mark.parametrize("kind, typed, fields", [
    ("deposit", {}, {"amount": 100.0}),
    ("withdrawal", {}, {"amount": 100.0}),
    ("dividend", {"ticker": "AAA.MI"}, {"amount": 100.0, "ticker": "AAA.MI", "asset_name": "Alpha SpA"}),
    ("charge", {"description": "Stamp duty"}, {"amount": 100.0, "description": "Stamp duty"}),
    ("charge", {"description": ""}, {"amount": 100.0, "description": None}),
], ids=["deposit", "withdrawal", "dividend", "charge", "charge-without-description"])
def test_cash_operation_is_recorded_with_its_kind(general_form, kind, typed, fields):
    """100 typed in the form is recorded as an operation of the kind chosen, the amount always positive.

    A dividend also passes its ticker and the asset's name, a charge its description (None when left blank).
    """
    form, submit, calls = general_form
    _choose(form, kind)
    form.amount.value = "100"
    for name, value in typed.items():
        getattr(form, name).value = value

    submit()

    assert calls == [(Kind(kind), date(2025, 1, 10), fields)]


def test_split_is_recorded_with_the_ratio_typed(general_form):
    """A 2:1 split of BBB.MI is recorded with ticker "BBB.MI" and ratio 2.0."""
    form, submit, calls = general_form
    _choose(form, "split")
    form.split_ticker.value = "BBB.MI"
    form.split_ratio.value = "2"

    submit()

    assert calls == [(Kind.SPLIT, date(2025, 1, 10), {"ticker": "BBB.MI", "ratio": 2.0})]


@pytest.mark.parametrize("changes, message", [
    ({"date": None}, "Date is missing"),
    ({"date": date(2024, 9, 1)}, "The date cannot be earlier than the last one recorded"),
    ({"kind": "deposit", "amount": "0"}, "The cash amount must be a number greater than 0"),
    ({"kind": "dividend", "amount": "0"}, "The dividend must be a number greater than 0"),
    ({"kind": "charge", "amount": "0"}, "The tax amount must be a number greater than 0"),
    ({"kind": "split", "split_ratio": "2"}, "Ticker is missing"),
    ({"kind": "split", "split_ticker": "BBB.MI", "split_ratio": ""}, "The ratio must be a positive number"),
], ids=["no-date", "before-last-operation", "zero-deposit", "zero-dividend", "zero-charge",
        "split-without-ticker", "split-without-ratio"])
def test_general_form_refuses_invalid_values(general_form, page, changes, message):
    """Each invalid value shows its own message, and nothing is recorded.

    The account's last operation is on 02-09-2024.
    """
    form, submit, calls = general_form
    form.amount.value = "100"
    for name, value in changes.items():
        if name == "kind":
            _choose(form, value)
        else:
            getattr(form, name).value = value

    submit()

    assert calls == []
    assert snack_texts(page) == [message]


@pytest.mark.parametrize("tab", ["general", "etf", "stock"])
def test_the_date_picker_starts_at_the_accounts_last_operation(app, page, state, tab):
    """In every Operations tab, the picker offers no day before the selected account's last operation (02-09-2024).

    A new operation can't be dated earlier: the picker used to offer every day since 2000.
    """
    state.ops_acc_idx = 1
    view = OperationsView(app)
    view.build()

    getattr(view, tab).date.button.on_click(None)

    assert page.dialogs[-1].first_date == datetime(2024, 9, 2)


def test_a_transfer_needs_another_account(general_form, page):
    """With a single account, Transfer says there is nowhere to send cash and the form stays on the operation before."""
    form, _, _ = general_form
    _choose(form, "withdrawal")

    _choose(form, "transfer")

    assert snack_texts(page) == ["You first need another account to transfer cash to"]
    assert (form.kind, form.cash_kind.selected, form.recipient_row.visible) == ("withdrawal", ["withdrawal"], False)


def test_a_transfer_from_the_form_records_it_in_both_accounts(app, page, state, monkeypatch):
    """Transfer, a recipient and 500: the test account sends 500 to the second one, which receives it.

    The amount shows the cash available (8,723.12, the test account's) while Transfer is chosen.
    """
    second = state.add_broker("Second Broker")
    set_operations(state, second, [deposit(date(2024, 1, 2), 1_000)])
    monkeypatch.setattr(page, "run_thread", lambda fn, *args: fn(*args))
    state.ops_acc_idx = 1
    view = OperationsView(app)
    view.build()
    form = view.general
    form.date.value = date(2025, 1, 10)

    _choose(form, "transfer")
    assert form.amount.helper == "Available: 8,723.12€"
    form.recipient.value = str(second)
    form.amount.value = "500"
    form.submit(None)

    sent, received = state.get_account(1).df.iloc[-1], state.get_account(second).df.iloc[-1]
    assert (sent["operation"], sent["asset_name"], sent["cash_held"]) == ("Transfer Out", "Second Broker", 8_223.12)
    assert (received["operation"], received["asset_name"], received["cash_held"]) == ("Transfer In", "Test Broker", 1_500)
