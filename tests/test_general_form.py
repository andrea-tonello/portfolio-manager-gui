"""Tests for the General tab of the Operations screen: cash operations, transfers and splits,
plus the date picker shared by every Operations tab.

The form hands the operation to operations_service with a sign convention:
amounts are typed as positive numbers, and a withdrawal is passed on as a
negative one. The service decides from it whether the row is a deposit or a
withdrawal.
"""

from datetime import date, datetime

import pytest
from conftest import snack_texts
from test_ledger_snapshots import _replay, deposit

from services import operations_service
from views.operations_view import OperationsView


@pytest.fixture
def general_form(monkeypatch, app, page, state):
    """The General tab for the test account, dated after its last operation, with operations recorded instead of saved.

    Returns (form, submit, calls): the GeneralForm, a function that presses
    "Add transaction", and the (kind, args, kwargs) of each operation that
    reached operations_service. Background work runs straight away.
    """
    calls = []

    def recorder(kind):
        """Return a stand-in for one operations_service function that remembers its arguments."""
        def record(*args, **kwargs):
            """Remember the call and leave the account unchanged."""
            calls.append((kind, args, kwargs))
            return args[0]
        return record

    monkeypatch.setattr(operations_service, "execute_cash_operation", recorder("cash"))
    monkeypatch.setattr(operations_service, "execute_split", recorder("split"))
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


@pytest.mark.parametrize("kind, service_kind, amount, extra", [
    ("deposit", "deposit_withdrawal", 100.0, {}),
    ("withdrawal", "deposit_withdrawal", -100.0, {}),
    ("dividend", "dividend", 100.0, {"ticker": "AAA.MI"}),
    ("charge", "charge", 100.0, {"description": "Stamp duty"}),
])
def test_cash_operation_reaches_the_service(general_form, kind, service_kind, amount, extra):
    """100 typed in the form reaches the service as the right kind, negative only for a withdrawal.

    A dividend also passes its ticker, a charge its description.
    """
    form, submit, calls = general_form
    _choose(form, kind)
    form.amount.value = "100"
    for name, value in extra.items():
        getattr(form, name).value = value

    submit()

    [(called, args, kwargs)] = calls
    assert (called, args[2], args[5]) == ("cash", service_kind, amount)
    assert kwargs == {"ticker": extra.get("ticker"), "description": extra.get("description")}


def test_split_reaches_the_service_with_the_ratio_typed(general_form):
    """A 2:1 split of BBB.MI is passed on as ticker "BBB.MI" and ratio 2.0."""
    form, submit, calls = general_form
    _choose(form, "split")
    form.split_ticker.value = "BBB.MI"
    form.split_ratio.value = "2"

    submit()

    [(called, args, _)] = calls
    assert (called, args[4], args[5]) == ("split", "BBB.MI", 2.0)


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
    """Each invalid value shows its own message, and nothing reaches the service.

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


def test_a_transfer_from_the_form_records_it_in_both_accounts(app, page, state, tmp_path, monkeypatch):
    """Transfer, a recipient and 500: the test account sends 500 to the second one, which receives it.

    The amount shows the cash available (8,723.12, the test account's) while Transfer is chosen.
    """
    second = state.add_broker("Second Broker")
    state.commit(second, _replay([deposit(date(2024, 1, 2), 1_000)], tmp_path / "second").assign(account="Second Broker"))
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
