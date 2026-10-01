"""Tests for the three "save to file" exports: backup (Settings), chart CSVs (Analysis), transactions CSV.

Since Flet 1.0, FilePicker.save_file(src_bytes=...) writes the bytes itself on
every platform: the file_picker plugin saves them on desktop, and the operating
system does on Android, iOS and the web. The path it returns is only a report,
and on Android it is not even a real file path (e.g. "/document/753"), so the
app must hand over the bytes and never open that path itself.
"""

import asyncio

import flet as ft
import pytest

from views.analysis_view import AnalysisView
from views.settings_view import SettingsView
from views.transactions_view import TransactionsView

ANDROID_SAVE_PATH = "/document/753"   # what Flet 1.0.3 returned on a real Android phone


class FakeFilePicker:
    """Stand-in for ft.FilePicker: records what the app asks to save and returns `returned_path`."""

    def __init__(self, returned_path):
        """Return `returned_path` from every save_file call, like the platform's save dialog would."""
        self.returned_path = returned_path
        self.calls = []

    async def save_file(self, **kwargs):
        """Record the call (file name, bytes, ...) instead of opening a real save dialog."""
        self.calls.append(kwargs)
        return self.returned_path


EXPORTS = {
    "backup (Settings)": (SettingsView, lambda view: view._on_export_backup(None)),
    "chart CSV (Analysis)": (AnalysisView, lambda view: view._save_csv("Drawdown.csv", b"date,nav\n")),
    "transactions CSV": (TransactionsView, lambda view: view._save_via_picker("Report.csv", b"date,nav\n")),
}


@pytest.mark.parametrize("platform", [ft.PagePlatform.ANDROID, ft.PagePlatform.LINUX], ids=["android", "desktop"])
@pytest.mark.parametrize("export", EXPORTS)
def test_export_hands_bytes_to_flet_and_never_opens_the_returned_path(export, platform, page, state):
    """Each export passes its bytes to save_file and shows the success message, without writing a file itself.

    The picker returns Android's "/document/753"; opening it as a file (the old
    backup-export behaviour) fails with FileNotFoundError.
    """
    page.platform = platform
    view_cls, run_export = EXPORTS[export]
    view = view_cls(page, state)
    view.build()
    view.file_picker = FakeFilePicker(ANDROID_SAVE_PATH)

    asyncio.run(run_export(view))

    assert len(view.file_picker.calls) == 1
    assert view.file_picker.calls[0]["src_bytes"], "the bytes must be handed to Flet"
    assert any(isinstance(c, ft.SnackBar) for c in page.overlay), "a success message should be shown"


@pytest.mark.parametrize("export", EXPORTS)
def test_cancelled_export_shows_no_message(export, page, state):
    """If the user cancels the save dialog (save_file returns None), no success message appears."""
    view_cls, run_export = EXPORTS[export]
    view = view_cls(page, state)
    view.build()
    view.file_picker = FakeFilePicker(None)

    asyncio.run(run_export(view))

    assert not any(isinstance(c, ft.SnackBar) for c in page.overlay)
