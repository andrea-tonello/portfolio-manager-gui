"""Tests for components/file_export.py: the file picker the screens share.

Flet's FilePicker is a page service: registered once on the page, then used
by any screen to show the system's save or open dialog. Saving through it is
tested with the real exports, in test_exports.py.
"""

import flet as ft

from components.file_export import get_file_picker


def test_the_file_picker_is_registered_once_and_reused(page):
    """The first call registers a FilePicker on the page; later calls return the same one."""
    first = get_file_picker(page)
    second = get_file_picker(page)

    assert first is second
    assert [s for s in page.services if isinstance(s, ft.FilePicker)] == [first]
