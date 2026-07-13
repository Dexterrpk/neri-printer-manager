#!/usr/bin/env bash
set -Eeuo pipefail

APP="neri-printer-manager"
PREFIX="/opt/${APP}"
STAGING="/opt/${APP}.staging"
BACKUP="/opt/${APP}.backup"
HELPER="/usr/libexec/neri-printer-helper"
POLICY="/usr/share/polkit-1/actions/com.neriinfotech.printermanager.policy"
DESKTOP="/usr/share/applications/neri-printer-manager.desktop"
LOG="/var/log/${APP}-install.log"
MODE="normal"

usage() {
  cat <<'EOF'
Uso: sudo bash ./install.sh [opção]

Opções:
  --fast      Não consulta nem instala pacotes APT; atualiza somente o aplicativo.
  --repair    Reinstala todas as dependências APT e recria o aplicativo.
  --help      Mostra esta ajuda.

Sem opção, o instalador verifica e instala somente os pacotes ausentes.
EOF
}

while (($# > 0)); do
  case "$1" in
    --fast) MODE="fast" ;;
    --repair) MODE="repair" ;;
    --help|-h) usage; exit 0 ;;
    *)
      echo "Opção inválida: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

[[ ${EUID} -eq 0 ]] || { echo "Execute com sudo: sudo bash ./install.sh" >&2; exit 1; }
command -v apt-get >/dev/null 2>&1 || { echo "Distribuição não suportada: apt-get não encontrado." >&2; exit 1; }
[[ -f pyproject.toml ]] || { echo "Execute o instalador dentro da pasta do projeto." >&2; exit 1; }

exec > >(tee -a "$LOG") 2>&1
echo "== Neri Printer Manager: instalação transacional (${MODE}) =="
date -Is

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

if [[ "$MODE" == "fast" ]]; then
  echo "Modo rápido: verificação e instalação de pacotes APT ignoradas."
  for command in python3 git; do
    command -v "$command" >/dev/null 2>&1 || {
      echo "Comando obrigatório ausente no modo rápido: $command" >&2
      echo "Execute a instalação normal: sudo bash ./install.sh" >&2
      exit 1
    }
  done
elif [[ "$MODE" == "repair" ]]; then
  echo "Modo reparo: reinstalando dependências do sistema."
  apt-get update
  apt-get install -y --reinstall --no-install-recommends "${PACKAGES[@]}"
else
  MISSING=()
  for package in "${PACKAGES[@]}"; do
    dpkg-query -W -f='${Status}' "$package" 2>/dev/null | grep -q '^install ok installed$' || MISSING+=("$package")
  done
  if ((${#MISSING[@]} > 0)); then
    echo "Instalando dependências ausentes: ${MISSING[*]}"
    apt-get update
    apt-get install -y --no-install-recommends "${MISSING[@]}"
  else
    echo "Todas as dependências do sistema já estão instaladas; APT não será executado."
  fi
fi

cleanup() { rm -rf "$STAGING"; }
rollback() {
  echo "Falha durante a ativação. Restaurando versão anterior..." >&2
  rm -rf "$PREFIX"
  [[ -d "$BACKUP" ]] && mv "$BACKUP" "$PREFIX"
}
trap cleanup EXIT
rm -rf "$STAGING" "$BACKUP"
python3 -m venv "$STAGING/venv"
"$STAGING/venv/bin/python" -m pip install --upgrade pip setuptools wheel
"$STAGING/venv/bin/python" -m pip install '.[dev]'

"$STAGING/venv/bin/python" -m pip check
"$STAGING/venv/bin/python" -m compileall -q "$STAGING/venv/lib" src

echo "Executando testes automatizados no ambiente de instalação..."
QT_QPA_PLATFORM=offscreen PYTHONPATH=src \
 "$STAGING/venv/bin/python" -m pytest -q || {
   echo "Os testes falharam. A versão atualmente instalada foi preservada." >&2
   exit 1
 }

QT_QPA_PLATFORM=offscreen "$STAGING/venv/bin/python" - <<'PY'
from PySide6.QtWidgets import QApplication
from neri_printer_manager.core import CupsService, DiagnosticService, JobService
from neri_printer_manager.device_discovery import RichDiscoveryService
from neri_printer_manager.host_locator import HostPrinterLocator
from neri_printer_manager.safe_app import SafeEnhancedWindow
from neri_printer_manager.usb import UsbPrinterService
app = QApplication.instance() or QApplication([])
window = SafeEnhancedWindow(auto_refresh=False)
assert window.pages.count() >= 7
window.close()
print("Teste gráfico e importações: OK")
PY

if [[ -d "$PREFIX" ]]; then mv "$PREFIX" "$BACKUP"; fi
if ! mv "$STAGING" "$PREFIX"; then rollback; exit 1; fi
trap - EXIT

if ! install -D -m 0755 packaging/libexec/neri-printer-helper "$HELPER" || \
   ! install -D -m 0644 packaging/polkit/com.neriinfotech.printermanager.policy "$POLICY" || \
   ! install -D -m 0644 packaging/debian/neri-printer-manager.desktop "$DESKTOP"; then
  rollback
  exit 1
fi

printf '#!/usr/bin/env bash\nexec "%s/venv/bin/neri-printer-manager" "$@"\n' "$PREFIX" > /usr/local/bin/neri-printer-manager
printf '#!/usr/bin/env bash\nexec "%s/venv/bin/neri-printer-cli" "$@"\n' "$PREFIX" > /usr/local/bin/neri-printer-cli
chmod 0755 /usr/local/bin/neri-printer-manager /usr/local/bin/neri-printer-cli

systemctl enable --now cups.service avahi-daemon.service
systemctl enable --now smbd.service 2>/dev/null || true
update-desktop-database >/dev/null 2>&1 || true

"$PREFIX/venv/bin/python" -m pip check
/usr/local/bin/neri-printer-cli --help >/dev/null
rm -rf "$BACKUP"

VERSION=$("$PREFIX/venv/bin/python" -m pip show neri-printer-manager | awk '/^Version:/{print $2}')
echo "Instalação concluída. Versão: ${VERSION:-desconhecida}"
echo "Modo utilizado: $MODE"
echo "Log: $LOG"
echo "Execute: neri-printer-manager"
