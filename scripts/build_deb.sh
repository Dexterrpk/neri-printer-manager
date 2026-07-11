#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="${VERSION:-1.0.0}"
ARCH="${ARCH:-all}"
ROOT="build/deb/neri-printer-manager_${VERSION}_${ARCH}"

rm -rf build/deb
install -d "${ROOT}/DEBIAN"
install -d "${ROOT}/opt/neri-printer-manager"
install -d "${ROOT}/usr/local/bin"
install -d "${ROOT}/usr/libexec"
install -d "${ROOT}/usr/share/applications"
install -d "${ROOT}/usr/share/polkit-1/actions"

cat > "${ROOT}/DEBIAN/control" <<EOF
Package: neri-printer-manager
Version: ${VERSION}
Section: admin
Priority: optional
Architecture: ${ARCH}
Maintainer: Neri InfoTech
Depends: python3 (>= 3.10), python3-venv, cups, cups-client, cups-browsed, cups-filters, ghostscript, avahi-daemon, avahi-utils, policykit-1
Recommends: samba, smbclient, printer-driver-gutenprint, foomatic-db-compressed-ppds
Description: Gerenciador e diagnóstico profissional de impressoras para Linux Mint
EOF

cat > "${ROOT}/DEBIAN/postinst" <<'EOF'
#!/usr/bin/env bash
set -e
python3 -m venv /opt/neri-printer-manager/venv
/opt/neri-printer-manager/venv/bin/pip install --no-index --find-links /opt/neri-printer-manager/wheels neri-printer-manager
systemctl enable --now cups.service avahi-daemon.service || true
update-desktop-database >/dev/null 2>&1 || true
EOF
chmod 0755 "${ROOT}/DEBIAN/postinst"

cat > "${ROOT}/DEBIAN/prerm" <<'EOF'
#!/usr/bin/env bash
set -e
rm -f /usr/local/bin/neri-printer-manager /usr/local/bin/neri-printer-cli
EOF
chmod 0755 "${ROOT}/DEBIAN/prerm"

python3 -m pip wheel . --wheel-dir "${ROOT}/opt/neri-printer-manager/wheels"
install -m 0755 packaging/libexec/neri-printer-helper "${ROOT}/usr/libexec/neri-printer-helper"
install -m 0644 packaging/debian/neri-printer-manager.desktop "${ROOT}/usr/share/applications/neri-printer-manager.desktop"
install -m 0644 packaging/polkit/com.neriinfotech.printermanager.policy "${ROOT}/usr/share/polkit-1/actions/com.neriinfotech.printermanager.policy"

cat > "${ROOT}/usr/local/bin/neri-printer-manager" <<'EOF'
#!/usr/bin/env bash
exec /opt/neri-printer-manager/venv/bin/neri-printer-manager "$@"
EOF
cat > "${ROOT}/usr/local/bin/neri-printer-cli" <<'EOF'
#!/usr/bin/env bash
exec /opt/neri-printer-manager/venv/bin/neri-printer-cli "$@"
EOF
chmod 0755 "${ROOT}/usr/local/bin/neri-printer-manager" "${ROOT}/usr/local/bin/neri-printer-cli"

dpkg-deb --build "${ROOT}" "build/neri-printer-manager_${VERSION}_${ARCH}.deb"
echo "Pacote criado em build/neri-printer-manager_${VERSION}_${ARCH}.deb"
