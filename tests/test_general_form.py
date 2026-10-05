"""Tests for the General tab of the Operations screen: cash operations and splits.

The form hands the operation to operations_service with a sign convention:
amounts are typed as positive numbers, and a withdrawal is passed on as a
negative one. The service decides from it whether the row is a deposit or a
withdrawal.
"""

from datetime import date

import pytest
from conftest import snack_texts

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
    form.kind.value = kind
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
    form.kind.value = "split"
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
        getattr(form, name).value = value

    submit()

    assert calls == []
    assert snack_texts(page) == [message]
