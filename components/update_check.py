"""Telling the user that a newer version is on GitHub, with a button to download it: at launch, or when asked."""

import logging
import time

import flet as ft

from components.dialogs import show_info_dialog
from services import update_service

logger = logging.getLogger(__name__)

# How long the drawer's update entry shows "Checking…" at least, so it doesn't just flash.
_CHECKING_SECONDS = 1

# The file each platform installs, as the release workflow names it, e.g.
# portfolio-manager-0.4.1.apk. Other platforms (e.g. iOS, which has no build)
# get the release page instead.
_DOWNLOADS = {
    ft.PagePlatform.ANDROID: "portfolio-manager-{version}.apk",
    ft.PagePlatform.LINUX: "portfolio-manager-{version}-linux.zip",
    ft.PagePlatform.WINDOWS: "portfolio-manager-{version}-windows.zip",
    ft.PagePlatform.MACOS: "portfolio-manager-{version}-macos.zip",
}


def check_for_update(page, translator, report=None):
    """Ask GitHub for a newer release in the background and, if there is one, show its notes.

    `report` is given for a check the user asked for (update_tile): it receives
    the text to show when no release is offered, i.e. the app is up to date or
    GitHub couldn't be reached, or None when the release dialog opens. Without
    it (the check at launch) nothing else is shown.
    Download opens this platform's file in the browser: on Android, opening
    the downloaded APK installs it over the app, keeping its data.
    """
    def worker():
        """Run the check off the screen's thread, so a slow connection never freezes it."""
        try:
            release = update_service.newer_release()
        except update_service.UpdateCheckFailed:
            logger.info("Update check failed", exc_info=True)
            if report:
                report(translator.get("update.check_failed"))
            return
        if release is None:
            if report:
                report(translator.get("update.no_updates"))
            return
        if report:
            report(None)
        version = release["tag_name"].removeprefix("v")
        urls = {asset["name"]: asset["browser_download_url"] for asset in release.get("assets", [])}
        file_name = _DOWNLOADS.get(page.platform, "").format(version=version)
        # BLANK opens the system browser rather than one inside the app, so the download
        # carries on, and can be opened from the notifications, after leaving the app.
        url = ft.Url(urls.get(file_name, release["html_url"]), target=ft.UrlTarget.BLANK)
        show_info_dialog(
            page,
            translator.get("update.title", version=version),
            release.get("body") or "",
            markdown=True,
            actions=[
                ft.TextButton(translator.get("update.later"), on_click=lambda _: page.pop_dialog()),
                ft.TextButton(translator.get("update.download"), url=url, on_click=lambda _: page.pop_dialog()),
            ],
        )

    page.run_thread(worker)


def update_tile(page, translator):
    """The drawer's "Search for Updates" entry, which says under its own title what the search found.

    Returns (entry, clear): `clear` removes the answer, for the drawer to call when it closes.
    """
    t = translator
    tile = ft.ListTile(
        leading=ft.Icon(ft.Icons.FILE_DOWNLOAD_OUTLINED),
        title=ft.Text(t.get("update.search_for_updates")),
        min_height=60,
        height=60,
        content_padding=ft.Padding.only(left=25, right=20),
    )
    started = 0.0  # when the latest search started, as time.monotonic()

    def show(message, busy=False):
        """Write `message` under the title (None: nothing), with a spinner and the entry greyed out while `busy`."""
        tile.subtitle = ft.Text(message, size=12) if message else None
        tile.trailing = ft.ProgressRing(width=16, height=16, stroke_width=2) if busy else None
        tile.disabled = busy
        page.update()

    def report(message):
        """Show the search's answer until the drawer closes (None: the release dialog opens, so nothing).

        It runs in the search's background thread, so waiting there for
        "Checking…" to have been up a second doesn't freeze the screen.
        """
        time.sleep(max(0.0, _CHECKING_SECONDS - (time.monotonic() - started)))
        show(message)

    def search(_):
        """Ask GitHub, showing that the search is under way."""
        nonlocal started
        started = time.monotonic()
        show(t.get("update.checking"), busy=True)
        check_for_update(page, t, report=report)

    def clear():
        """Remove the answer shown under the title. A search still under way keeps its "Checking…".

        Its answer then appears in the closed drawer, to be read when it is
        opened again; clearing "Checking…" would also make the entry tappable
        again, while the first search is still running.
        """
        if tile.subtitle is not None and not tile.disabled:
            show(None)

    tile.on_click = search
    return tile, clear
