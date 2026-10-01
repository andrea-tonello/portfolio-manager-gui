"""Checks on the files in assets/ that the app and `flet build` rely on.

A wrong image path raises no error: Flet just draws an empty box, and
`flet build` quietly falls back to Flet's default app icon. A wrong entry in
pyproject.toml's exclude list is just as silent: the files get packaged anyway.
These tests catch those mistakes, e.g. after moving files around in assets/.
"""

import ast
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"


def _image_sources_in_code():
    """Return (file, line, src) for every image path written literally in the app's code.

    It reads the source files (without running them) and collects the `src` of
    each ft.Image(...) call, given by keyword or as the first argument. Flet
    resolves these paths inside assets/, e.g. src="imgs/github-logo.png" is
    assets/imgs/github-logo.png.
    """
    found = []
    for path in sorted(ROOT.rglob("*.py")):
        relative = path.relative_to(ROOT)
        if relative.parts[0] in ("tests", "build") or relative.parts[0].startswith("."):
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "Image"):
                continue
            values = [kw.value for kw in node.keywords if kw.arg == "src"] + node.args[:1]
            for value in values:
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    found.append((str(relative), node.lineno, value.value))
    return found


def test_every_image_in_the_code_exists_in_assets():
    """Each ft.Image(src=...) in the code points to a file that exists under assets/."""
    sources = _image_sources_in_code()
    assert sources, "the scan should find the app's images"

    missing = [f"{file}:{line} {src}" for file, line, src in sources if not (ASSETS / src).is_file()]

    assert missing == []


def _build_excludes():
    """Return the `[tool.flet.app] exclude` list from pyproject.toml."""
    with open(ROOT / "pyproject.toml", "rb") as f:
        return tomllib.load(f)["tool"]["flet"]["app"]["exclude"]


def test_build_excludes_are_exact_paths_for_every_platform():
    """Each exclude entry is an exact path; nested ones exist and are also listed for Windows.

    The packager (serious_python) compares every file's path with the entries
    as plain text, using the system's separator. So a wildcard such as "*.csv"
    never matches anything, and "assets/docs" only matches on Linux and macOS:
    Windows builds need 'assets\\docs' too. Wildcards belong in
    [tool.flet.cleanup] app_files instead.
    """
    excludes = _build_excludes()

    assert [e for e in excludes if any(c in e for c in "*?[")] == []
    for entry in (e for e in excludes if "/" in e):
        assert (ROOT / entry).exists(), f"{entry} doesn't exist: moved without updating pyproject.toml?"
        assert entry.replace("/", "\\") in excludes, f"{entry} has no Windows spelling"


@pytest.mark.parametrize("name", ["icon.png", "icon_android.png"])
def test_app_icons_stay_at_the_assets_root(name):
    """`flet build` looks for the app icon only directly in assets/: icon_<platform>.png first, then icon.png.

    There is no setting to look elsewhere. Moved into a subfolder (e.g.
    assets/imgs/), the icons would be ignored and the build would use Flet's
    default icon. icon.png also serves as the splash-screen image.
    """
    assert (ASSETS / name).is_file()
