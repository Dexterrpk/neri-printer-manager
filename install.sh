#!/usr/bin/env bash
set -Eeuo pipefail

APP="neri-printer-manager"
PREFIX="/opt/${APP}"
STAGING="/opt/${APP}.staging"
BACKUP="/opt/${APP}.backup"
HELPER="/usr/libexec/neri-printer-helper"
POLICY="/usr/share/polkit-1/actions/com.neriinfotech.printermanager.policy"
DESKTOP="/usr/share/applications/neri-printer-manager.desktop"

[[ ${EUID} -eq 0 ]] || { echo "Execute com sudo: sudo bash ./install.sh" >&2; exit 1; }
command -v apt-get >/dev/null 2>&1 || { echo "Distribuição não suportada: apt-get não encontrado." >&2; exit 1; }
[[ -f pyproject.toml ]] || { echo "Execute o instalador dentro da pasta do projeto." >&2; exit 1; }

export DEBIAN_FRONTEND=noninteractive
PACKAGES=(
 python3 python3-venv python3-pip git ca-certificates
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

cleanup() {
 rm -rf "$STAGING"
}
trap cleanup EXIT
rm -rf "$STAGING"
python3 -m venv "$STAGING/venv"
"$STAGING/venv/bin/python" -m pip install --upgrade pip setuptools wheel
"$STAGING/venv/bin/python" -m pip install '.[dev]'

# Os testes usam exatamente o Python e o PySide6 que serão instalados.
echo "Executando testes no ambiente de instalação..."
QT_QPA_PLATFORM=offscreen PYTHONPATH=src \
 "$STAGING/venv/bin/python" -m pytest -q || {
   echo "Os testes falharam. A versão atualmente instalada foi preservada." >&2
   exit 1
 }

# Teste de importação e criação da janela sem iniciar o loop gráfico.
QT_QPA_PLATFORM=offscreen "$STAGING/venv/bin/python" - <<'PY'
from PySide6.QtWidgets import QApplication
from neri_printer_manager.safe_app import SafeEnhancedWindow
app = QApplication.instance() or QApplication([])
window = SafeEnhancedWindow(auto_refresh=False)
window.close()
print("Teste gráfico: OK")
PY

rm -rf "$BACKUP"
if [[ -d "$PREFIX" ]]; then mv "$PREFIX" "$BACKUP"; fi
if ! mv "$STAGING" "$PREFIX"; then
 [[ -d "$BACKUP" ]] && mv "$BACKUP" "$PREFIX"
 echo "Não foi possível ativar a nova versão; a versão anterior foi restaurada." >&2
 exit 1
fi
trap - EXIT

if ! install -D -m 0755 packaging/libexec/neri-printer-helper "$HELPER" || \
   ! install -D -m 0644 packaging/polkit/com.neriinfotech.printermanager.policy "$POLICY" || \
   ! install -D -m 0644 packaging/debian/neri-printer-manager.desktop "$DESKTOP"; then
 rm -rf "$PREFIX"
 [[ -d "$BACKUP" ]] && mv "$BACKUP" "$PREFIX"
 echo "Falha ao instalar arquivos do sistema; versão anterior restaurada." >&2
 exit 1
fi

printf '#!/usr/bin/env bash\nexec "%s/venv/bin/neri-printer-manager" "$@"\n' "$PREFIX" > /usr/local/bin/neri-printer-manager
printf '#!/usr/bin/env bash\nexec "%s/venv/bin/neri-printer-cli" "$@"\n' "$PREFIX" > /usr/local/bin/neri-printer-cli
chmod 0755 /usr/local/bin/neri-printer-manager /usr/local/bin/neri-printer-cli

systemctl enable --now cups.service avahi-daemon.service
systemctl enable --now smbd.service 2>/dev/null || true
update-desktop-database >/dev/null 2>&1 || true
rm -rf "$BACKUP"

VERSION=$("$PREFIX/venv/bin/python" -m pip show neri-printer-manager | awk '/^Version:/{print $2}')
echo "Instalação concluída. Versão: ${VERSION:-desconhecida}"
echo "Execute: neri-printer-manager"
