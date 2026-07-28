import re
from pathlib import Path

from neri_printer_manager import __version__


def test_package_version_matches_pyproject() -> None:
    project = Path(__file__).parents[1]
    text = (project / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'(?m)^version = "([^"]+)"$', text)
    assert match is not None
    assert match.group(1) == __version__


def test_gui_entry_point_uses_the_unified_application() -> None:
    project = Path(__file__).parents[1]
    text = (project / "pyproject.toml").read_text(encoding="utf-8")
    assert 'neri-printer-manager = "neri_printer_manager.app:main"' in text
