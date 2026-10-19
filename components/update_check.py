"""Telling the user that a newer version is on GitHub, with a button to download it: at launch, or when asked."""

import logging

import flet as ft

from components.dialogs import show_info_dialog
from components.snack import show_snack
from services import update_service

logger = logging.getLogger(__name__)

# The file each platform installs, as the release workflow names it, e.g.
# portfolio-manager-0.4.1.apk. Other platforms (e.g. iOS, which has no build)
# get the release page instead.
_DOWNLOADS = {
    ft.PagePlatform.ANDROID: "portfolio-manager-{version}.apk",
    ft.PagePlatform.LINUX: "portfolio-manager-{version}-linux.zip",
    ft.PagePlatform.WINDOWS: "portfolio-manager-{version}-windows.zip",
    ft.PagePlatform.MACOS: "portfolio-manager-{version}-macos.zip",
}


def check_for_update(page, translator, manual=False):
    """Ask GitHub for a newer release in the background and, if there is one, show its notes.

    The automatic check at launch shows nothing else. A manual one (manual=True,
    the drawer's "Search for Updates") also says when the app is up to date, or
    when GitHub couldn't be reached.
    Download opens this platform's file in the browser: on Android, opening
    the downloaded APK installs it over the app, keeping its data.
    """
    def worker():
        """Run the check off the screen's thread, so a slow connection never freezes it."""
        try:
            release = update_service.newer_release()
        except update_service.UpdateCheckFailed:
            logger.info("Update check failed", exc_info=True)
            if manual:
                show_snack(page, translator.get("update.check_failed"), error=True)
            return
        if release is None:
            if manual:
                show_snack(page, translator.get("update.no_updates"))
            return
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
