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
ACTIVE_ROOT=""

usage() {
  cat <<'EOF'
Uso: sudo bash ./install.sh [opção]

Opções:
  --fast      Reutiliza o ambiente Python íntegro e atualiza somente o aplicativo.
  --repair    Reinstala todas as dependências APT e recria o aplicativo.
  --help      Mostra esta ajuda.

Sem opção, o instalador verifica e instala somente os pacotes ausentes e cria
um ambiente novo antes de ativar a atualização.
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
echo "== Neri Printer Manager: instalação (${MODE}) =="
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
  echo "Modo rápido: pacotes APT não serão consultados nem reinstalados."
  for command in python3 git; do
    command -v "$command" >/dev/null 2>&1 || {
      echo "Comando obrigatório ausente: $command" >&2
      echo "Execute: sudo bash ./install.sh" >&2
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
  echo "Falha na atualização. Restaurando versão anterior..." >&2
  rm -rf "$PREFIX"
  [[ -d "$BACKUP" ]] && mv "$BACKUP" "$PREFIX"
}
trap cleanup EXIT
rm -rf "$STAGING" "$BACKUP"

healthy_existing_environment() {
  [[ -x "$PREFIX/venv/bin/python" ]] || return 1
  "$PREFIX/venv/bin/python" -m pip check >/dev/null 2>&1 || return 1
  "$PREFIX/venv/bin/python" - <<'PY' >/dev/null 2>&1
import PySide6
import pytest
import neri_printer_manager
PY
}

if [[ "$MODE" == "fast" ]] && healthy_existing_environment; then
  echo "Ambiente Python existente íntegro; reutilizando dependências e cache."
  cp -a "$PREFIX" "$BACKUP"
  ACTIVE_ROOT="$PREFIX"
  "$PREFIX/venv/bin/python" -m pip install --disable-pip-version-check --no-deps --force-reinstall .
else
  if [[ "$MODE" == "fast" ]]; then
    echo "Ambiente existente ausente ou inconsistente; criando ambiente novo com segurança."
  fi
  python3 -m venv "$STAGING/venv"
  "$STAGING/venv/bin/python" -m pip install --disable-pip-version-check --upgrade pip setuptools wheel
  "$STAGING/venv/bin/python" -m pip install --disable-pip-version-check '.[dev]'
  ACTIVE_ROOT="$STAGING"
fi

"$ACTIVE_ROOT/venv/bin/python" -m pip check
"$ACTIVE_ROOT/venv/bin/python" -m compileall -q src/neri_printer_manager

echo "Executando testes automatizados..."
QT_QPA_PLATFORM=offscreen PYTHONPATH=src \
  "$ACTIVE_ROOT/venv/bin/python" -m pytest -q || {
    if [[ "$ACTIVE_ROOT" == "$PREFIX" ]]; then rollback; fi
    echo "Os testes falharam. A versão anterior foi preservada." >&2
    exit 1
  }

QT_QPA_PLATFORM=offscreen "$ACTIVE_ROOT/venv/bin/python" - <<'PY'
from PySide6.QtWidgets import QApplication
from neri_printer_manager.safe_app import SafeEnhancedWindow
app = QApplication.instance() or QApplication([])
window = SafeEnhancedWindow(auto_refresh=False)
assert window.pages.count() >= 7
window.close()
print("Teste gráfico e importações: OK")
PY

if [[ "$ACTIVE_ROOT" == "$STAGING" ]]; then
  if [[ -d "$PREFIX" ]]; then mv "$PREFIX" "$BACKUP"; fi
  if ! mv "$STAGING" "$PREFIX"; then rollback; exit 1; fi
fi
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
echo "Execute como usuário comum: neri-printer-manager"
