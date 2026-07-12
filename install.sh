#!/usr/bin/env bash
set -Eeuo pipefail
APP="neri-printer-manager"
PREFIX="/opt/${APP}"
HELPER="/usr/libexec/neri-printer-helper"
POLICY="/usr/share/polkit-1/actions/com.neriinfotech.printermanager.policy"
DESKTOP="/usr/share/applications/neri-printer-manager.desktop"
[[ ${EUID} -eq 0 ]] || { echo "Execute com sudo: sudo bash ./install.sh" >&2; exit 1; }
command -v apt-get >/dev/null 2>&1 || { echo "Distribuição não suportada: apt-get não encontrado." >&2; exit 1; }
export DEBIAN_FRONTEND=noninteractive
PACKAGES=(
 python3 python3-venv python3-pip python3-pytest git ca-certificates
 cups cups-client cups-bsd cups-browsed cups-filters ghostscript
 avahi-daemon avahi-utils libnss-mdns policykit-1
 samba smbclient samba-common-bin
 hplip printer-driver-hpcups printer-driver-gutenprint foomatic-db-compressed-ppds
 libxcb-cursor0 libxkbcommon-x11-0 libxcb-xinerama0 libxcb-icccm4 libxcb-image0
 libxcb-keysyms1 libxcb-render-util0 libegl1 libgl1
)
MISSING=()
for package in "${PACKAGES[@]}"; do
 dpkg-query -W -f='${Status}' "$package" 2>/dev/null | grep -q '^install ok installed$' || MISSING+=("$package")
done
if ((${#MISSING[@]}>0)); then
 echo "Instalando dependências ausentes: ${MISSING[*]}"
 apt-get update
 apt-get install -y --no-install-recommends "${MISSING[@]}"
else
 echo "Todas as dependências do sistema já estão instaladas."
fi
install -d -m 0755 "$PREFIX"
if [[ ! -x "$PREFIX/venv/bin/python" ]]; then python3 -m venv "$PREFIX/venv"; fi
"$PREFIX/venv/bin/python" -m pip install --upgrade pip setuptools wheel
"$PREFIX/venv/bin/pip" install --force-reinstall .
# Teste rápido antes de substituir os atalhos. pytest é garantido pelo apt.
PYTHONPATH=src python3 -m pytest -q || { echo "Os testes falharam; instalação interrompida." >&2; exit 1; }
install -D -m 0755 packaging/libexec/neri-printer-helper "$HELPER"
install -D -m 0644 packaging/polkit/com.neriinfotech.printermanager.policy "$POLICY"
install -D -m 0644 packaging/debian/neri-printer-manager.desktop "$DESKTOP"
printf '#!/usr/bin/env bash\nexec "%s/venv/bin/neri-printer-manager" "$@"\n' "$PREFIX" > /usr/local/bin/neri-printer-manager
printf '#!/usr/bin/env bash\nexec "%s/venv/bin/neri-printer-cli" "$@"\n' "$PREFIX" > /usr/local/bin/neri-printer-cli
chmod 0755 /usr/local/bin/neri-printer-manager /usr/local/bin/neri-printer-cli
systemctl enable --now cups.service avahi-daemon.service
systemctl enable --now smbd.service 2>/dev/null || true
update-desktop-database >/dev/null 2>&1 || true
echo "Instalação concluída. Versão: $($PREFIX/venv/bin/pip show neri-printer-manager | awk '/^Version:/{print $2}')"
echo "Execute: neri-printer-manager"
