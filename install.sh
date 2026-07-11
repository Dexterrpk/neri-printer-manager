#!/usr/bin/env bash
set -Eeuo pipefail

APP="neri-printer-manager"
PREFIX="/opt/${APP}"
HELPER="/usr/libexec/neri-printer-helper"
POLICY="/usr/share/polkit-1/actions/com.neriinfotech.printermanager.policy"
DESKTOP="/usr/share/applications/neri-printer-manager.desktop"

if [[ ${EUID} -ne 0 ]]; then
  echo "Execute com sudo: sudo ./install.sh" >&2
  exit 1
fi

if ! command -v apt-get >/dev/null 2>&1; then
  echo "Distribuição não suportada: apt-get não encontrado." >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y \
  python3 python3-venv python3-pip \
  cups cups-client cups-browsed cups-filters ghostscript \
  avahi-daemon avahi-utils policykit-1 smbclient

install -d -m 0755 "${PREFIX}"
python3 -m venv "${PREFIX}/venv"
"${PREFIX}/venv/bin/pip" install --upgrade pip
"${PREFIX}/venv/bin/pip" install .

install -D -m 0755 packaging/libexec/neri-printer-helper "${HELPER}"
install -D -m 0644 packaging/polkit/com.neriinfotech.printermanager.policy "${POLICY}"
install -D -m 0644 packaging/debian/neri-printer-manager.desktop "${DESKTOP}"

cat > /usr/local/bin/neri-printer-manager <<EOF
#!/usr/bin/env bash
exec "${PREFIX}/venv/bin/neri-printer-manager" "\$@"
EOF
cat > /usr/local/bin/neri-printer-cli <<EOF
#!/usr/bin/env bash
exec "${PREFIX}/venv/bin/neri-printer-cli" "\$@"
EOF
chmod 0755 /usr/local/bin/neri-printer-manager /usr/local/bin/neri-printer-cli

systemctl enable --now cups.service avahi-daemon.service
update-desktop-database >/dev/null 2>&1 || true

echo "Instalação concluída. Execute: neri-printer-manager"
