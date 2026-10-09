"""Telling the user at launch that a newer version is on GitHub, with a button to download it."""

import flet as ft

from components.dialogs import show_info_dialog
from services import update_service

# The file each platform installs, as the release workflow names it. Other
# platforms (e.g. iOS, which has no build) get the release page instead.
_DOWNLOADS = {
    ft.PagePlatform.ANDROID: "portfolio-manager.apk",
    ft.PagePlatform.LINUX: "portfolio-manager-linux.zip",
    ft.PagePlatform.WINDOWS: "portfolio-manager-windows.zip",
    ft.PagePlatform.MACOS: "portfolio-manager-macos.zip",
}


def check_for_update(page, translator):
    """Ask GitHub for a newer release in the background and, if there is one, show its notes.

    Nothing is shown when the app is up to date or GitHub can't be reached.
    Download opens this platform's file in the browser: on Android, opening
    the downloaded APK installs it over the app, keeping its data.
    """
    def worker():
        """Run the check off the screen's thread, so a slow connection never freezes it."""
        release = update_service.newer_release()
        if release is None:
            return
        urls = {asset["name"]: asset["browser_download_url"] for asset in release.get("assets", [])}
        # BLANK opens the system browser rather than one inside the app, so the download
        # carries on, and can be opened from the notifications, after leaving the app.
        url = ft.Url(urls.get(_DOWNLOADS.get(page.platform), release["html_url"]), target=ft.UrlTarget.BLANK)
        show_info_dialog(
            page,
            translator.get("update.title", version=release["tag_name"].removeprefix("v")),
            release.get("body") or "",
            markdown=True,
            actions=[
                ft.TextButton(translator.get("update.later"), on_click=lambda _: page.pop_dialog()),
                ft.TextButton(translator.get("update.download"), url=url, on_click=lambda _: page.pop_dialog()),
            ],
        )

    page.run_thread(worker)
