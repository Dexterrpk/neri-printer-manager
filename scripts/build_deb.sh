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
OUTPUT="$PROJECT_ROOT/build/neri-printer-manager_${VERSION}_${ARCH}.deb"
rm -rf -- "$BUILD_ROOT"
install -d "$PACKAGE_ROOT/DEBIAN"
install -d "$PACKAGE_ROOT/opt/neri-printer-manager/wheels"
install -d "$PACKAGE_ROOT/usr/bin"
install -d "$PACKAGE_ROOT/usr/libexec"
install -d "$PACKAGE_ROOT/usr/share/applications"
install -d "$PACKAGE_ROOT/usr/share/doc/neri-printer-manager/docs/screenshots"
install -d "$PACKAGE_ROOT/usr/share/polkit-1/actions"

cat > "$PACKAGE_ROOT/DEBIAN/control" <<EOF
Package: neri-printer-manager
Version: $VERSION
Section: admin
Priority: optional
Architecture: $ARCH
Maintainer: Neri InfoTech <Dexterrpk@users.noreply.github.com>
Depends: python3 (>= 3.10), python3-venv, python3-cups, cups, cups-client, cups-filters, ghostscript, avahi-daemon, avahi-utils, libnss-mdns, policykit-1, libxcb-cursor0, libxkbcommon-x11-0, libxcb-xinerama0, libxcb-icccm4, libxcb-image0, libxcb-keysyms1, libxcb-render-util0, libegl1, libgl1, libdbus-1-3, libfontconfig1, libglib2.0-0
Recommends: samba, smbclient, samba-common-bin, hplip, printer-driver-hpcups, printer-driver-gutenprint, foomatic-db-compressed-ppds
Suggests: cups-browsed
Homepage: https://github.com/Dexterrpk/neri-printer-manager
Description: Gerenciador seguro de impressoras para Linux Mint
 Descobre, instala, compartilha e diagnostica impressoras USB, IPP,
 JetDirect, LPD e SMB com interface PySide6 e autorização PolicyKit.
EOF

cat > "$PACKAGE_ROOT/DEBIAN/postinst" <<'EOF'
#!/usr/bin/env bash
set -e
if [[ ! -x /opt/neri-printer-manager/venv/bin/python ]] ||
   ! /opt/neri-printer-manager/venv/bin/python -c 'import cups' >/dev/null 2>&1 ||
   ! /opt/neri-printer-manager/venv/bin/python -m pip --version >/dev/null 2>&1; then
  rm -rf -- /opt/neri-printer-manager/venv
  /usr/bin/python3 -m venv --system-site-packages /opt/neri-printer-manager/venv
fi
/opt/neri-printer-manager/venv/bin/python -m pip install \
  --disable-pip-version-check --no-index --upgrade --force-reinstall \
  --find-links /opt/neri-printer-manager/wheels neri-printer-manager
/opt/neri-printer-manager/venv/bin/python -m pip check
systemctl enable --now cups.service avahi-daemon.service || true
systemctl try-restart cups.service || true
update-desktop-database >/dev/null 2>&1 || true
EOF
chmod 0755 "$PACKAGE_ROOT/DEBIAN/postinst"

cat > "$PACKAGE_ROOT/DEBIAN/postrm" <<'EOF'
#!/usr/bin/env bash
set -e
case "${1:-}" in
  remove|purge)
    rm -rf -- /opt/neri-printer-manager
    ;;
esac
update-desktop-database >/dev/null 2>&1 || true
EOF
chmod 0755 "$PACKAGE_ROOT/DEBIAN/postrm"

PIP_CACHE_DIR="${PIP_CACHE_DIR:-$PROJECT_ROOT/build/pip-cache}" \
  python3 -m pip wheel . --wheel-dir "$PACKAGE_ROOT/opt/neri-printer-manager/wheels"
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
#!/usr/bin/env bash
exec /opt/neri-printer-manager/venv/bin/python -m neri_printer_manager.app "$@"
EOF
cat > "$PACKAGE_ROOT/usr/bin/neri-printer-cli" <<'EOF'
#!/usr/bin/env bash
exec /opt/neri-printer-manager/venv/bin/python -m neri_printer_manager.cli "$@"
EOF
chmod 0755 \
  "$PACKAGE_ROOT/usr/bin/neri-printer-manager" \
  "$PACKAGE_ROOT/usr/bin/neri-printer-cli"

dpkg-deb --root-owner-group --build "$PACKAGE_ROOT" "$OUTPUT"
echo "Pacote criado em $OUTPUT"
