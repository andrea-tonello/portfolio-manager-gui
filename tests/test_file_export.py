"""Tests for components/file_export.py: the file picker the screens share, and saving bytes through it.

Flet's FilePicker is a page service: registered once on the page, then used
by any screen to show the system's save or open dialog.
"""

import asyncio

import flet as ft
from conftest import snack_texts
from test_exports import FakeFilePicker

from components.file_export import get_file_picker, save_bytes


def test_the_file_picker_is_registered_once_and_reused(page):
    """The first call registers a FilePicker on the page; later calls return the same one."""
    first = get_file_picker(page)
    second = get_file_picker(page)

    assert first is second
    assert [s for s in page.services if isinstance(s, ft.FilePicker)] == [first]


def test_save_bytes_hands_the_bytes_to_flet_and_confirms(page):
    """The bytes, name and extension go to the save dialog; once saved, the success message appears."""
    picker = FakeFilePicker("/home/me/report.csv")

    saved = asyncio.run(save_bytes(page, picker, "Report.csv", b"date,nav\n", "csv", "Exported"))

    assert saved is True
    assert picker.calls == [{"file_name": "Report.csv", "allowed_extensions": ["csv"], "src_bytes": b"date,nav\n"}]
    assert snack_texts(page) == ["Exported"]


def test_a_cancelled_save_shows_nothing(page):
    """If the user closes the save dialog, nothing is confirmed."""
    saved = asyncio.run(save_bytes(page, FakeFilePicker(None), "Report.csv", b"x", "csv", "Exported"))

    assert saved is False
    assert snack_texts(page) == []
