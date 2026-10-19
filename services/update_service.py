"""Asking GitHub whether a newer version of the app has been released."""

import http.client
import json
import urllib.request

from utils.constants import APP_VERSION

# GitHub's description of the newest release, drafts and pre-releases excluded.
_LATEST_RELEASE_URL = "https://api.github.com/repos/andrea-tonello/portfolio-manager-gui/releases/latest"


class UpdateCheckFailed(Exception):
    """GitHub couldn't be asked about releases, or gave no usable answer (e.g. offline). The cause is chained."""


def parse_version(text: str) -> tuple[int, ...] | None:
    """Turn a version or release tag into numbers that compare correctly, or None if it isn't one.

    Comparing the text would put "0.10.0" before "0.9.0"; the numbers don't.

    Example: parse_version("v0.4.1") -> (0, 4, 1); parse_version("dev") -> None.
    """
    parts = text.removeprefix("v").split(".")
    if not all(part.isdigit() for part in parts):
        return None
    return tuple(int(part) for part in parts)


def newer_release(current: str = APP_VERSION) -> dict | None:
    """Return GitHub's newest release if it is newer than `current`, else None.

    The release is GitHub's JSON as a dict: tag_name (e.g. "v0.4.1"), body
    (the release notes), html_url (the release page) and assets (the files,
    each with name and browser_download_url). None as well when `current` is
    not a release number (a copy run from the source code, versioned "dev"),
    without asking GitHub. Raises UpdateCheckFailed when GitHub gives no usable
    answer, e.g. offline, so a check the user asked for can say so instead of
    reporting the app up to date.
    """
    current_version = parse_version(current)
    if current_version is None:
        return None
    try:
        with urllib.request.urlopen(_LATEST_RELEASE_URL, timeout=10) as resp:
            release = json.load(resp)
        latest_version = parse_version(release["tag_name"])
    except (OSError, http.client.HTTPException, ValueError, KeyError, TypeError, AttributeError) as ex:
        raise UpdateCheckFailed from ex
    if latest_version is None or latest_version <= current_version:
        return None
    return release
