"""Tests for the update check, run against canned GitHub answers (no network).

services/update_service.py asks GitHub for a newer release; components/update_check.py
tells the user, at launch or when they search for updates from the drawer.
"""

import io
import json
import urllib.error
import urllib.request

import flet as ft
import pytest
from conftest import find_controls, snack_texts

from components import update_check
from components.update_check import check_for_update
from services import update_service
from services.update_service import UpdateCheckFailed, newer_release


def fake_github(monkeypatch, tag):
    """Make urllib.request.urlopen answer as GitHub would if the latest release were tagged `tag`."""
    def urlopen(url, *args, **kwargs):
        """Stand-in for urlopen: return a release with the given tag."""
        return io.BytesIO(json.dumps({"tag_name": tag, "body": "notes"}).encode("utf-8"))

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)


@pytest.mark.parametrize("current, tag, offered", [
    ("0.4.0", "v0.4.1", True),
    ("0.9.0", "v0.10.0", True),   # compared as numbers: as text "0.10.0" < "0.9.0"
    ("0.4.1", "v0.4.1", False),
    ("0.5.0", "v0.4.1", False),
    ("0.4.1", "nightly", False),  # a tag that isn't a version is ignored
])
def test_only_a_newer_release_is_offered(monkeypatch, current, tag, offered):
    """The release is returned only when its tag is a higher version than the running app's."""
    fake_github(monkeypatch, tag)

    assert (newer_release(current) is not None) == offered


def test_a_copy_run_from_source_never_asks_github():
    """Version "dev" (the source code's) skips the check: the network guard fails the test if GitHub is asked."""
    assert newer_release("dev") is None


def test_no_connection_is_not_mistaken_for_no_update(monkeypatch):
    """Offline, the check raises UpdateCheckFailed rather than answering "nothing newer"."""
    def urlopen(url, *args, **kwargs):
        """Stand-in for urlopen: fail as it does without a connection."""
        raise urllib.error.URLError("no connection")

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)

    with pytest.raises(UpdateCheckFailed):
        newer_release("0.4.0")


def _offline():
    """Stand-in for newer_release when GitHub can't be reached."""
    raise UpdateCheckFailed


RELEASE = {"tag_name": "v9.9.9", "body": "notes", "html_url": "https://github.com/release", "assets": []}


@pytest.mark.parametrize("answer, shown", [
    (lambda: None, "You are on the latest version"),
    (_offline, "Couldn't check for updates. Try again later"),
    (lambda: RELEASE, None),
], ids=["up-to-date", "offline", "newer-release"])
def test_searching_from_the_drawer_answers_under_the_entry_until_it_closes(app, page, monkeypatch, answer, shown):
    """The drawer's entry says "Checking…" while greyed out, then its answer, until the drawer closes.

    A snack bar would be hidden under the open drawer. A newer release opens
    its dialog instead, leaving the entry plain. Offline, the search used to
    report the app up to date. GitHub answers at once here, so "Checking…"
    waits out the rest of its second before the answer replaces it. Closing
    the drawer during the search leaves "Checking…", as the search goes on.
    """
    app.show_tab(0)
    drawer = page.end_drawer
    [tile] = [tile for tile in find_controls(drawer, ft.ListTile) if tile.title.value == "Search for Updates"]
    monkeypatch.setattr(update_service, "newer_release", answer)
    searches, waits = [], []
    monkeypatch.setattr(page, "run_thread", lambda fn, *args: searches.append(fn))
    monkeypatch.setattr(update_check.time, "sleep", waits.append)

    tile.on_click(None)
    drawer.on_dismiss()
    assert (tile.subtitle.value, tile.disabled, isinstance(tile.trailing, ft.ProgressRing)) == ("Checking…", True, True)
    searches.pop()()

    assert waits == [pytest.approx(1, abs=0.1)]
    assert (tile.subtitle and tile.subtitle.value, tile.disabled, tile.trailing) == (shown, False, None)
    assert [dialog.title.value for dialog in page.dialogs] == ([] if shown else ["Version 9.9.9 available"])
    drawer.on_dismiss()
    assert tile.subtitle is None


@pytest.mark.parametrize("answer", [lambda: None, _offline], ids=["up-to-date", "offline"])
def test_the_check_at_launch_stays_silent(page, translator, monkeypatch, answer):
    """With nothing to offer, the automatic check at launch shows no message and no dialog."""
    monkeypatch.setattr(update_service, "newer_release", answer)
    monkeypatch.setattr(page, "run_thread", lambda fn, *args: fn(*args))

    check_for_update(page, translator)

    assert (snack_texts(page), page.dialogs) == ([], [])
