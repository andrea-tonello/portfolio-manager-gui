"""Tests for the update check, run against canned GitHub answers (no network).

services/update_service.py asks GitHub for a newer release; components/update_check.py
tells the user, at launch or when they search for updates from the drawer.
"""

import io
import json
import urllib.error
import urllib.request

import pytest
from conftest import snack_texts

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


@pytest.mark.parametrize("answer, manual, shown", [
    (lambda: None, True, ["You are on the latest version"]),
    (_offline, True, ["Couldn't check for updates. Try again later"]),
    (lambda: None, False, []),
    (_offline, False, []),
], ids=["manual-up-to-date", "manual-offline", "launch-up-to-date", "launch-offline"])
def test_only_a_check_the_user_asked_for_says_why_nothing_is_offered(page, translator, monkeypatch,
                                                                   answer, manual, shown):
    """Searching for updates from the drawer says the app is up to date, or that GitHub couldn't be reached.

    The automatic check at launch stays silent in both cases. Offline, a
    manual check used to report the app up to date.
    """
    monkeypatch.setattr(update_service, "newer_release", answer)
    monkeypatch.setattr(page, "run_thread", lambda fn, *args: fn(*args))

    check_for_update(page, translator, manual=manual)

    assert snack_texts(page) == shown
