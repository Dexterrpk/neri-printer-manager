#!/usr/bin/env bash
set -Eeuo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Execute com sudo: sudo ./uninstall.sh" >&2
  exit 1
fi

if dpkg-query -W -f='${Status}' neri-printer-manager 2>/dev/null |
  grep -q '^install ok installed$'; then
  echo "A instalação foi feita por pacote Debian. Use:" >&2
  echo "  sudo apt remove neri-printer-manager" >&2
  exit 2
fi

rm -f /usr/local/bin/neri-printer-manager /usr/local/bin/neri-printer-cli
rm -f /usr/libexec/neri-printer-helper
rm -f /usr/share/polkit-1/actions/com.neriinfotech.printermanager.policy
rm -f /usr/share/applications/neri-printer-manager.desktop
rm -rf -- \
  /opt/neri-printer-manager \
  /opt/neri-printer-manager.staging \
  /opt/neri-printer-manager.backup \
  /opt/neri-printer-manager.rollback
update-desktop-database >/dev/null 2>&1 || true

echo "Neri Printer Manager removido. Configurações do CUPS e impressoras foram preservadas."
