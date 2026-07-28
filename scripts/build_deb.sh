#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

PROJECT_VERSION=$(python3 -c \
  'import pathlib, re; text=pathlib.Path("pyproject.toml").read_text(); match=re.search(r"(?m)^version = \"([^\"]+)\"$", text); print(match.group(1) if match else "")')
[[ -n "$PROJECT_VERSION" ]] || {
  echo "Não foi possível ler a versão em pyproject.toml." >&2
  exit 2
}
VERSION="${VERSION:-$PROJECT_VERSION}"
ARCH="${ARCH:-$(dpkg --print-architecture)}"
[[ "$VERSION" =~ ^[0-9][0-9A-Za-z.+:~-]*$ ]] || {
  echo "Versão Debian inválida: $VERSION" >&2
  exit 2
}
[[ "$ARCH" =~ ^[a-z0-9][a-z0-9-]*$ ]] || {
  echo "Arquitetura Debian inválida: $ARCH" >&2
  exit 2
}

BUILD_ROOT="$PROJECT_ROOT/build/deb"
PACKAGE_ROOT="$BUILD_ROOT/neri-printer-manager_${VERSION}_${ARCH}"
OUTPUT="$PROJECT_ROOT/build/neri-printer.deb"
LEGACY_OUTPUT="$PROJECT_ROOT/build/neri-printer-manager_${VERSION}_${ARCH}.deb"
WHEEL_DIR="$BUILD_ROOT/wheels"
PYTHON_LIB="$PACKAGE_ROOT/opt/neri-printer-manager/lib"
rm -rf -- "$BUILD_ROOT"
rm -f -- "$OUTPUT" "$LEGACY_OUTPUT"
install -d "$PACKAGE_ROOT/DEBIAN"
install -d "$PYTHON_LIB"
install -d "$PACKAGE_ROOT/usr/bin"
install -d "$PACKAGE_ROOT/usr/libexec"
install -d "$PACKAGE_ROOT/usr/share/applications"
install -d "$PACKAGE_ROOT/usr/share/doc/neri-printer-manager/docs/screenshots"
install -d "$PACKAGE_ROOT/usr/share/polkit-1/actions"
install -d "$WHEEL_DIR"

cat > "$PACKAGE_ROOT/DEBIAN/control" <<EOF
Package: neri-printer-manager
Version: $VERSION
Section: admin
Priority: optional
Architecture: $ARCH
Maintainer: Neri InfoTech <Dexterrpk@users.noreply.github.com>
Depends: python3 (>= 3.10), python3-cups, cups, cups-client, cups-filters, ghostscript, avahi-daemon, avahi-utils, libnss-mdns, policykit-1, libxcb-cursor0, libxkbcommon-x11-0, libxcb-xinerama0, libxcb-icccm4, libxcb-image0, libxcb-keysyms1, libxcb-render-util0, libegl1, libgl1, libdbus-1-3, libfontconfig1, libglib2.0-0t64 | libglib2.0-0
Recommends: samba, smbclient, samba-common-bin, hplip, printer-driver-hpcups, printer-driver-gutenprint, foomatic-db-compressed-ppds
Suggests: cups-browsed
Homepage: https://github.com/Dexterrpk/neri-printer-manager
Description: Gerenciador seguro de impressoras para Linux Mint
 Descobre, instala, compartilha e diagnostica impressoras USB, IPP,
 JetDirect, LPD e SMB com interface PySide6 e autorização PolicyKit.
EOF

cat > "$PACKAGE_ROOT/DEBIAN/preinst" <<'EOF'
#!/bin/sh
set -e
case "${1:-}" in
  install|upgrade)
    # Remove o ambiente criado por versões anteriores. A aplicação atual já
    # chega instalada no pacote e não executa pip na máquina do usuário.
    rm -rf -- /opt/neri-printer-manager/venv
    ;;
esac
EOF
chmod 0755 "$PACKAGE_ROOT/DEBIAN/preinst"

cat > "$PACKAGE_ROOT/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
systemctl enable --now cups.service avahi-daemon.service || true
systemctl try-restart cups.service || true
update-desktop-database >/dev/null 2>&1 || true
EOF
chmod 0755 "$PACKAGE_ROOT/DEBIAN/postinst"

cat > "$PACKAGE_ROOT/DEBIAN/postrm" <<'EOF'
#!/bin/sh
set -e
case "${1:-}" in
  remove|purge)
    rm -rf -- /opt/neri-printer-manager/venv
    ;;
esac
update-desktop-database >/dev/null 2>&1 || true
EOF
chmod 0755 "$PACKAGE_ROOT/DEBIAN/postrm"

PIP_CACHE_DIR="${PIP_CACHE_DIR:-$PROJECT_ROOT/build/pip-cache}" \
  python3 -m pip wheel . --wheel-dir "$WHEEL_DIR"
python3 -m pip install \
  --disable-pip-version-check --no-index --no-deps --no-compile \
  --target "$PYTHON_LIB" "$WHEEL_DIR"/*.whl

# O wheel do PySide6 também traz ferramentas de desenvolvimento, cabeçalhos e
# arquivos de tipagem. Eles não participam da execução desta aplicação Qt
# Widgets e aumentariam desnecessariamente o instalador.
PYSIDE_ROOT="$PYTHON_LIB/PySide6"
rm -rf -- \
  "$PYTHON_LIB/bin" \
  "$PYSIDE_ROOT/doc" \
  "$PYSIDE_ROOT/glue" \
  "$PYSIDE_ROOT/include" \
  "$PYSIDE_ROOT/scripts" \
  "$PYSIDE_ROOT/support" \
  "$PYSIDE_ROOT/typesystems"
find "$PYSIDE_ROOT" -maxdepth 1 -type f -name '*.pyi' -delete
rm -f -- \
  "$PYSIDE_ROOT/assistant" \
  "$PYSIDE_ROOT/designer" \
  "$PYSIDE_ROOT/linguist" \
  "$PYSIDE_ROOT/lrelease" \
  "$PYSIDE_ROOT/lupdate" \
  "$PYSIDE_ROOT/qmlformat" \
  "$PYSIDE_ROOT/qmllint" \
  "$PYSIDE_ROOT/qmlls" \
  "$PYSIDE_ROOT/svgtoqml"

install -m 0755 packaging/libexec/neri-printer-helper \
  "$PACKAGE_ROOT/usr/libexec/neri-printer-helper"
install -m 0644 packaging/debian/neri-printer-manager.desktop \
  "$PACKAGE_ROOT/usr/share/applications/neri-printer-manager.desktop"
install -m 0644 packaging/polkit/com.neriinfotech.printermanager.policy \
  "$PACKAGE_ROOT/usr/share/polkit-1/actions/com.neriinfotech.printermanager.policy"
install -m 0644 README.md LICENSE SECURITY.md \
  "$PACKAGE_ROOT/usr/share/doc/neri-printer-manager/"
install -m 0644 LICENSE \
  "$PACKAGE_ROOT/usr/share/doc/neri-printer-manager/copyright"
install -m 0644 docs/ARCHITECTURE.md docs/HOMOLOGATION.md \
  docs/TROUBLESHOOTING.md docs/USER_GUIDE.md \
  "$PACKAGE_ROOT/usr/share/doc/neri-printer-manager/docs/"
install -m 0644 docs/screenshots/*.png \
  "$PACKAGE_ROOT/usr/share/doc/neri-printer-manager/docs/screenshots/"
gzip -9n -c CHANGELOG.md > \
  "$PACKAGE_ROOT/usr/share/doc/neri-printer-manager/changelog.gz"

cat > "$PACKAGE_ROOT/usr/bin/neri-printer-manager" <<'EOF'
#!/bin/sh
export PYTHONPATH="/opt/neri-printer-manager/lib${PYTHONPATH:+:$PYTHONPATH}"
exec /usr/bin/python3 -m neri_printer_manager.app "$@"
EOF
cat > "$PACKAGE_ROOT/usr/bin/neri-printer-cli" <<'EOF'
#!/bin/sh
export PYTHONPATH="/opt/neri-printer-manager/lib${PYTHONPATH:+:$PYTHONPATH}"
exec /usr/bin/python3 -m neri_printer_manager.cli "$@"
EOF
chmod 0755 \
  "$PACKAGE_ROOT/usr/bin/neri-printer-manager" \
  "$PACKAGE_ROOT/usr/bin/neri-printer-cli"

dpkg-deb --root-owner-group --build "$PACKAGE_ROOT" "$OUTPUT"
echo "Pacote criado em $OUTPUT"
