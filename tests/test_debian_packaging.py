from pathlib import Path

PROJECT = Path(__file__).parents[1]


def test_debian_install_does_not_run_pip_or_create_a_venv() -> None:
    script = (PROJECT / "scripts/build_deb.sh").read_text(encoding="utf-8")
    postinst = script.split('cat > "$PACKAGE_ROOT/DEBIAN/postinst"', 1)[1].split("EOF", 2)[1]

    assert "pip install" not in postinst
    assert "python3 -m venv" not in postinst
    assert "python3-venv" not in script


def test_debian_package_supports_mint_21_and_22_glib_names() -> None:
    script = (PROJECT / "scripts/build_deb.sh").read_text(encoding="utf-8")

    assert "libglib2.0-0t64 | libglib2.0-0" in script


def test_launchers_use_the_bundled_application() -> None:
    script = (PROJECT / "scripts/build_deb.sh").read_text(encoding="utf-8")
    helper = (PROJECT / "packaging/libexec/neri-printer-helper").read_text(encoding="utf-8")

    assert "/opt/neri-printer-manager/lib" in script
    assert "exec /usr/bin/python3 -m neri_printer_manager.app" in script
    assert "exec /usr/bin/python3 -m neri_printer_manager.cli" in script
    assert "exec /usr/bin/python3 -m neri_printer_manager.privileged" in helper


def test_debian_package_removes_pyside_development_files() -> None:
    script = (PROJECT / "scripts/build_deb.sh").read_text(encoding="utf-8")

    assert '"$PYTHON_LIB/bin"' in script
    assert '"$PYSIDE_ROOT/include"' in script
    assert "-name '*.pyi' -delete" in script
