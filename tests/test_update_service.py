"""Tests for services/update_service.py, run against canned GitHub answers (no network)."""

import io
import json
import urllib.error
import urllib.request

import pytest

from services.update_service import newer_release


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


def test_no_connection_means_no_update(monkeypatch):
    """Offline, the check gives up quietly instead of raising."""
    def urlopen(url, *args, **kwargs):
        """Stand-in for urlopen: fail as it does without a connection."""
        raise urllib.error.URLError("no connection")

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)

    assert newer_release("0.4.0") is None
