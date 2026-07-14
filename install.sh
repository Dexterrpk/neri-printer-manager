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
TARGET_USER="${NERI_TARGET_USER:-${SUDO_USER:-}}"

usage() {
  cat <<'EOF'
Uso: bash ./install.sh [opção]

Opções:
  --fast      Reutiliza o ambiente Python íntegro e atualiza somente o aplicativo.
  --repair    Reinstala todas as dependências APT e recria o aplicativo.
  --help      Mostra esta ajuda.

Execute como root. Prefira bootstrap.sh, que escolhe sudo ou su automaticamente,
identifica o usuário real e abre o programa como usuário comum.
EOF
}

while (($# > 0)); do
  case "$1" in
    --fast) MODE="fast" ;;
    --repair) MODE="repair" ;;
    --help|-h) usage; exit 0 ;;
    *) echo "Opção inválida: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

[[ ${EUID} -eq 0 ]] || { echo "Este instalador precisa ser executado como root." >&2; exit 1; }
command -v apt-get >/dev/null 2>&1 || { echo "Distribuição não suportada: apt-get não encontrado." >&2; exit 1; }
[[ -f pyproject.toml ]] || { echo "Execute o instalador dentro da pasta do projeto." >&2; exit 1; }

if [[ -z "$TARGET_USER" || "$TARGET_USER" == "root" ]]; then
  TARGET_USER="$(logname 2>/dev/null || true)"
fi
if [[ -n "$TARGET_USER" && "$TARGET_USER" != "root" ]]; then
  TARGET_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
else
  TARGET_USER=""
  TARGET_HOME=""
fi

exec > >(tee -a "$LOG") 2>&1
echo "== Neri Printer Manager: instalação (${MODE}) =="
date -Is
echo "Usuário de destino: ${TARGET_USER:-não identificado}"

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
  command -v python3 >/dev/null 2>&1 || { echo "Python 3 ausente. Execute a instalação normal." >&2; exit 1; }
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
    echo "Instalando somente dependências ausentes: ${MISSING[*]}"
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
  [[ "$MODE" == "fast" ]] && echo "Ambiente ausente ou inconsistente; recriando com segurança."
  python3 -m venv "$STAGING/venv"
  "$STAGING/venv/bin/python" -m pip install --disable-pip-version-check --upgrade pip setuptools wheel
  "$STAGING/venv/bin/python" -m pip install --disable-pip-version-check '.[dev]'
  ACTIVE_ROOT="$STAGING"
fi

"$ACTIVE_ROOT/venv/bin/python" -m pip check
"$ACTIVE_ROOT/venv/bin/python" -m compileall -q src/neri_printer_manager

echo "Executando testes automatizados..."
QT_QPA_PLATFORM=offscreen PYTHONPATH=src "$ACTIVE_ROOT/venv/bin/python" -m pytest -q || {
  [[ "$ACTIVE_ROOT" == "$PREFIX" ]] && rollback
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
  [[ -d "$PREFIX" ]] && mv "$PREFIX" "$BACKUP"
  if ! mv "$STAGING" "$PREFIX"; then rollback; exit 1; fi
fi
trap - EXIT

if ! install -D -m 0755 packaging/libexec/neri-printer-helper "$HELPER" || \
   ! install -D -m 0644 packaging/polkit/com.neriinfotech.printermanager.policy "$POLICY" || \
   ! install -D -m 0644 packaging/debian/neri-printer-manager.desktop "$DESKTOP"; then
  rollback
  exit 1
fi

cat > /usr/local/bin/neri-printer-manager <<EOF
#!/usr/bin/env bash
exec "$PREFIX/venv/bin/python" -m neri_printer_manager.safe_app "\$@"
EOF
cat > /usr/local/bin/neri-printer-cli <<EOF
#!/usr/bin/env bash
exec "$PREFIX/venv/bin/python" -m neri_printer_manager.cli "\$@"
EOF
chmod 0755 /usr/local/bin/neri-printer-manager /usr/local/bin/neri-printer-cli
chmod -R a+rX "$PREFIX"

systemctl enable --now cups.service avahi-daemon.service
systemctl enable --now smbd.service 2>/dev/null || true
systemctl restart cups.service
update-desktop-database >/dev/null 2>&1 || true

# Libera o usuário detectado para administrar filas locais sem executar a interface como root.
if [[ -n "$TARGET_USER" ]]; then
  for group in lp lpadmin sambashare; do
    getent group "$group" >/dev/null 2>&1 && usermod -aG "$group" "$TARGET_USER" || true
  done
  if [[ -n "$TARGET_HOME" && -d "$TARGET_HOME" ]]; then
    install -d -o "$TARGET_USER" -g "$(id -gn "$TARGET_USER")" "$TARGET_HOME/.local/share/applications"
    install -m 0644 -o "$TARGET_USER" -g "$(id -gn "$TARGET_USER")" "$DESKTOP" "$TARGET_HOME/.local/share/applications/neri-printer-manager.desktop"
  fi
fi

"$PREFIX/venv/bin/python" -m pip check
/usr/local/bin/neri-printer-cli --help >/dev/null
QT_QPA_PLATFORM=offscreen "$PREFIX/venv/bin/python" -c 'import neri_printer_manager.safe_app'
rm -rf "$BACKUP"

VERSION=$("$PREFIX/venv/bin/python" -m pip show neri-printer-manager | awk '/^Version:/{print $2}')
echo "Instalação concluída. Versão: ${VERSION:-desconhecida}"
echo "Modo utilizado: $MODE"
echo "Log: $LOG"
if [[ -n "$TARGET_USER" ]]; then
  echo "Usuário preparado: $TARGET_USER"
  echo "Abra como usuário comum: neri-printer-manager"
  echo "Se o usuário acabou de entrar no grupo lpadmin, encerre e abra a sessão uma vez."
fi
