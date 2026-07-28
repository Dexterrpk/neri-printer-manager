#!/usr/bin/env bash
set -Eeuo pipefail

APP="neri-printer-manager"
PREFIX="/opt/${APP}"
STAGING="/opt/${APP}.staging"
BACKUP="/opt/${APP}.backup"
ROLLBACK_DIR="/opt/${APP}.rollback"
HELPER="/usr/libexec/neri-printer-helper"
POLICY="/usr/share/polkit-1/actions/com.neriinfotech.printermanager.policy"
DESKTOP="/usr/share/applications/neri-printer-manager.desktop"
LOG="/var/log/${APP}-install.log"
MODE="normal"
TARGET_USER="${NERI_TARGET_USER:-${SUDO_USER:-}}"
DEPLOYED=0
SYSTEM_FILES=(
  "$HELPER"
  "$POLICY"
  "$DESKTOP"
  "/usr/local/bin/neri-printer-manager"
  "/usr/local/bin/neri-printer-cli"
)

usage() {
  cat <<'EOF'
Uso: bash ./install.sh [opção]

Opções:
  --fast      Reutiliza as dependências quando o ambiente atual está íntegro.
  --repair    Reinstala os pacotes do sistema e recria o ambiente Python.
  --help      Mostra esta ajuda.

Execute como root. Para instalação normal, prefira bootstrap.sh.
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

[[ ${EUID} -eq 0 ]] || {
  echo "Este instalador precisa ser executado como root." >&2
  exit 1
}
exec 9>"/run/lock/${APP}.install.lock"
if ! /usr/bin/flock -n 9; then
  echo "Outra instalação do Neri Printer Manager já está em andamento." >&2
  exit 1
fi
command -v apt-get >/dev/null 2>&1 || {
  echo "Distribuição não suportada: apt-get não encontrado." >&2
  exit 1
}
[[ -f pyproject.toml && -f packaging/libexec/neri-printer-helper ]] || {
  echo "Execute o instalador dentro da pasta do projeto." >&2
  exit 1
}
if dpkg-query -W -f='${Status}' "$APP" 2>/dev/null |
  grep -q '^install ok installed$'; then
  echo "O pacote Debian $APP já está instalado." >&2
  echo "Atualize-o com outro pacote .deb ou remova-o antes de usar este instalador." >&2
  exit 2
fi

if [[ -z "$TARGET_USER" || "$TARGET_USER" == "root" ]]; then
  TARGET_USER="$(logname 2>/dev/null || true)"
fi
[[ "$TARGET_USER" != "root" ]] || TARGET_USER=""

touch "$LOG"
chmod 0600 "$LOG"
exec > >(tee -a "$LOG") 2>&1
echo "== Neri Printer Manager: instalação (${MODE}) =="
date -Is
echo "Usuário solicitante: ${TARGET_USER:-não identificado}"

export DEBIAN_FRONTEND=noninteractive
if dpkg-query -W -f='${Status}' libglib2.0-0t64 2>/dev/null |
  grep -q '^install ok installed$'; then
  GLIB_PACKAGE="libglib2.0-0t64"
else
  GLIB_PACKAGE="libglib2.0-0"
fi
REQUIRED_PACKAGES=(
  python3 python3-venv python3-pip ca-certificates
  cups cups-client cups-bsd cups-filters ghostscript python3-cups
  avahi-daemon avahi-utils libnss-mdns policykit-1
  libxcb-cursor0 libxkbcommon-x11-0 libxcb-xinerama0 libxcb-icccm4
  libxcb-image0 libxcb-keysyms1 libxcb-render-util0 libegl1 libgl1
  libdbus-1-3 libfontconfig1 "$GLIB_PACKAGE"
)
FEATURE_PACKAGES=(
  samba smbclient samba-common-bin
  hplip printer-driver-hpcups printer-driver-gutenprint
  foomatic-db-compressed-ppds
)
ALL_PACKAGES=("${REQUIRED_PACKAGES[@]}" "${FEATURE_PACKAGES[@]}")

missing_packages() {
  local package
  for package in "$@"; do
    if ! dpkg-query -W -f='${Status}' "$package" 2>/dev/null |
      grep -q '^install ok installed$'; then
      printf '%s\n' "$package"
    fi
  done
}

mapfile -t MISSING < <(missing_packages "${ALL_PACKAGES[@]}")
if [[ "$MODE" == "fast" && ${#MISSING[@]} -gt 0 ]]; then
  echo "Modo rápido convertido em normal; faltam: ${MISSING[*]}"
  MODE="normal"
fi

if [[ "$MODE" == "repair" ]]; then
  echo "Reinstalando dependências do sistema."
  apt-get update
  apt-get install -y --reinstall --no-install-recommends "${ALL_PACKAGES[@]}"
elif [[ ${#MISSING[@]} -gt 0 ]]; then
  echo "Instalando dependências ausentes: ${MISSING[*]}"
  apt-get update
  apt-get install -y --no-install-recommends "${MISSING[@]}"
else
  echo "Dependências do sistema já estão instaladas."
fi

cleanup() {
  if [[ -d "$STAGING" ]]; then
    rm -rf -- "$STAGING"
  fi
  if [[ "$DEPLOYED" -eq 0 && -d "$ROLLBACK_DIR" ]]; then
    rm -rf -- "$ROLLBACK_DIR"
  fi
}
rollback() {
  set +e
  echo "Falha na atualização. Restaurando a versão anterior..." >&2
  if [[ -d "$PREFIX" ]]; then
    rm -rf -- "$PREFIX"
  fi
  if [[ -d "$BACKUP" ]]; then
    mv "$BACKUP" "$PREFIX"
  fi
  local index path
  for index in "${!SYSTEM_FILES[@]}"; do
    path="${SYSTEM_FILES[$index]}"
    rm -f -- "$path"
    if [[ -f "$ROLLBACK_DIR/present-$index" ]]; then
      cp -a -- "$ROLLBACK_DIR/file-$index" "$path"
    fi
  done
  DEPLOYED=0
  rm -rf -- "$ROLLBACK_DIR"
  set -e
}
on_exit() {
  local status=$?
  trap - EXIT
  if [[ "$status" -ne 0 && "$DEPLOYED" -eq 1 ]]; then
    rollback
  fi
  cleanup
  exit "$status"
}
trap on_exit EXIT

if [[ -d "$BACKUP" && ! -d "$PREFIX" ]]; then
  echo "Recuperando uma instalação anterior interrompida."
  mv "$BACKUP" "$PREFIX"
fi
rm -rf -- "$STAGING" "$BACKUP" "$ROLLBACK_DIR"

healthy_existing_environment() {
  [[ -x "$PREFIX/venv/bin/python" ]] || return 1
  "$PREFIX/venv/bin/python" -m pip check >/dev/null 2>&1 || return 1
  QT_QPA_PLATFORM=offscreen "$PREFIX/venv/bin/python" - <<'PY' >/dev/null 2>&1
import PySide6
import cups
import neri_printer_manager
import pytest
PY
}

if [[ "$MODE" == "fast" ]] && healthy_existing_environment; then
  echo "Reutilizando uma cópia verificada do ambiente atual."
  cp -a "$PREFIX" "$STAGING"
  "$STAGING/venv/bin/python" -m pip install \
    --disable-pip-version-check --no-deps --force-reinstall .
else
  [[ "$MODE" == "fast" ]] && echo "Ambiente atual inconsistente; recriando."
  /usr/bin/python3 -m venv --system-site-packages "$STAGING/venv"
  "$STAGING/venv/bin/python" -m pip install \
    --disable-pip-version-check --upgrade pip setuptools wheel
  "$STAGING/venv/bin/python" -m pip install \
    --disable-pip-version-check '.[test]'
fi

PYTHON="$STAGING/venv/bin/python"
"$PYTHON" -m pip check
echo "Executando testes automatizados..."
PYTHONDONTWRITEBYTECODE=1 QT_QPA_PLATFORM=offscreen PYTHONPATH=src \
  "$PYTHON" -m pytest -q -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 QT_QPA_PLATFORM=offscreen PYTHONPATH=src "$PYTHON" - <<'PY'
from PySide6.QtWidgets import QApplication
from neri_printer_manager.app import MainWindow

application = QApplication.instance() or QApplication([])
window = MainWindow(auto_refresh=False)
assert window.sidebar.count() == 7
assert window.pages.count() == 7
window.close()
print("Teste gráfico: OK")
PY
"$PYTHON" - <<'PY'
import compileall
from pathlib import Path
import neri_printer_manager

package = Path(neri_printer_manager.__file__).parent
raise SystemExit(0 if compileall.compile_dir(package, quiet=1) else 1)
PY

install -d -m 0700 "$ROLLBACK_DIR"
for index in "${!SYSTEM_FILES[@]}"; do
  path="${SYSTEM_FILES[$index]}"
  if [[ -e "$path" || -L "$path" ]]; then
    cp -a -- "$path" "$ROLLBACK_DIR/file-$index"
    touch "$ROLLBACK_DIR/present-$index"
  fi
done
[[ -d "$PREFIX" ]] && mv "$PREFIX" "$BACKUP"
DEPLOYED=1
mv "$STAGING" "$PREFIX"

install -D -m 0755 packaging/libexec/neri-printer-helper "$HELPER"
install -D -m 0644 packaging/polkit/com.neriinfotech.printermanager.policy "$POLICY"
install -D -m 0644 packaging/debian/neri-printer-manager.desktop "$DESKTOP"

cat > /usr/local/bin/neri-printer-manager <<EOF
#!/usr/bin/env bash
exec "$PREFIX/venv/bin/python" -m neri_printer_manager.app "\$@"
EOF
cat > /usr/local/bin/neri-printer-cli <<EOF
#!/usr/bin/env bash
exec "$PREFIX/venv/bin/python" -m neri_printer_manager.cli "\$@"
EOF
chmod 0755 /usr/local/bin/neri-printer-manager /usr/local/bin/neri-printer-cli
chmod -R a+rX "$PREFIX"

systemctl enable --now cups.service avahi-daemon.service
systemctl restart cups.service
update-desktop-database >/dev/null 2>&1 || true

"$PREFIX/venv/bin/python" -m pip check
/usr/local/bin/neri-printer-cli --version
QT_QPA_PLATFORM=offscreen "$PREFIX/venv/bin/python" -c \
  'from neri_printer_manager.app import MainWindow'

if systemctl is-active --quiet cups-browsed.service 2>/dev/null; then
  echo "Aviso: cups-browsed está ativo. Filas efêmeras serão separadas das filas instaladas."
fi

VERSION=$("$PREFIX/venv/bin/python" -c \
  'from neri_printer_manager import __version__; print(__version__)')
DEPLOYED=0
rm -rf -- "$BACKUP" "$ROLLBACK_DIR"
trap - EXIT
echo "Instalação concluída. Versão: $VERSION"
echo "Log: $LOG"
echo "Abra como usuário comum: neri-printer-manager"
