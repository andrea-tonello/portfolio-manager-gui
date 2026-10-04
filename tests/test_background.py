"""Tests for components/background.py: running a screen's slow work without freezing it.

The Add and Calculate buttons start work that can take a while (fetching
prices, computing statistics). run_in_background shows a spinner, runs the
work in a separate thread, shows any error in a red snack bar in the user's
language, and hides the spinner whatever happens.
"""

import logging

import flet as ft
import pytest
from conftest import snack_texts

from components.background import run_in_background
from domain.errors import ValidationError


@pytest.fixture
def run_now(page, monkeypatch):
    """Make the fake page run background work straight away, so its effects can be checked."""
    monkeypatch.setattr(page, "run_thread", lambda fn, *args: fn(*args))


@pytest.fixture
def spinner():
    """A hidden progress ring, like the ones next to the screens' buttons."""
    return ft.ProgressRing(visible=False)


def test_the_spinner_shows_while_the_work_runs_and_hides_after(page, translator, spinner, run_now):
    """The spinner is visible during the work and hidden once it has finished."""
    seen = []

    run_in_background(page, translator, lambda: seen.append(spinner.visible), loading=spinner)

    assert seen == [True]
    assert spinner.visible is False
    assert snack_texts(page) == []


def test_an_error_is_shown_in_the_users_language(page, translator, spinner, run_now):
    """A ValidationError from the work appears as its translated message, and the spinner is hidden."""
    def work():
        """Fail like a sale of more shares than are held."""
        raise ValidationError("operations.stock.sell_noqt", quantity=5, last_remaining_qt=3)

    run_in_background(page, translator, work, loading=spinner)

    assert snack_texts(page) == ["Quantity sold (5) exceeds available quantity (3)"]
    assert spinner.visible is False


def test_an_unexpected_error_is_shown_and_logged(page, translator, run_now, caplog):
    """Any other error (e.g. a bug) shows its own text, and its traceback goes to the log for debugging."""
    def work():
        """Fail with an error the app doesn't expect."""
        raise KeyError("nav")

    with caplog.at_level(logging.ERROR):
        run_in_background(page, translator, work)

    assert snack_texts(page) == ["'nav'"]
    assert "KeyError" in caplog.text


def test_the_work_runs_in_a_separate_thread(page, translator, monkeypatch):
    """The work is handed to page.run_thread, so the screen stays responsive meanwhile."""
    started = []
    monkeypatch.setattr(page, "run_thread", lambda fn, *args: started.append(fn))

    run_in_background(page, translator, lambda: None)

    assert len(started) == 1
