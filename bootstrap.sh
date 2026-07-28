#!/usr/bin/env bash
set -Eeuo pipefail

REPO_URL="https://github.com/Dexterrpk/neri-printer-manager.git"
MODE="${1:---auto}"
ROOT_METHOD=""
TEMP_SOURCE=""

case "$MODE" in
  --auto|--fast|--normal|--repair) ;;
  -h|--help)
    cat <<'EOF'
Uso:
  bash bootstrap.sh            # instala ou atualiza automaticamente
  bash bootstrap.sh --fast     # reutiliza um ambiente íntegro
  bash bootstrap.sh --normal   # instala somente o que estiver ausente
  bash bootstrap.sh --repair   # reinstala dependências e o aplicativo
EOF
    exit 0
    ;;
  *) echo "Opção inválida: $MODE" >&2; exit 2 ;;
esac

if [[ ${EUID} -eq 0 ]]; then
  TARGET_USER="${NERI_TARGET_USER:-${SUDO_USER:-$(logname 2>/dev/null || true)}}"
  [[ -n "$TARGET_USER" && "$TARGET_USER" != "root" ]] || {
    echo "Execute no terminal do usuário comum, fora de um shell root." >&2
    exit 1
  }
else
  TARGET_USER="$(id -un)"
fi

TARGET_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
[[ -n "$TARGET_HOME" && -d "$TARGET_HOME" ]] || {
  echo "Não foi possível localizar a pasta do usuário $TARGET_USER." >&2
  exit 1
}
TARGET_HOME="$(realpath -e "$TARGET_HOME")"
PROJECT_DIR="$(realpath -m "${NERI_PROJECT_DIR:-$TARGET_HOME/neri-printer-manager}")"
case "$PROJECT_DIR" in
  "$TARGET_HOME"/*) ;;
  *)
    echo "A pasta do projeto precisa ficar dentro de $TARGET_HOME." >&2
    exit 1
    ;;
esac
CACHE_DIR="$TARGET_HOME/.cache/neri-printer-manager"

quote_command() {
  local out="" arg
  for arg in "$@"; do
    printf -v out '%s %q' "$out" "$arg"
  done
  printf '%s' "${out# }"
}

user_is_admin_group() {
  id -nG "$TARGET_USER" 2>/dev/null | tr ' ' '\n' | grep -Eq '^(sudo|admin|wheel)$'
}

choose_root_method() {
  [[ -n "$ROOT_METHOD" ]] && return 0
  if [[ ${EUID} -eq 0 ]]; then
    ROOT_METHOD="root"
  elif command -v sudo >/dev/null 2>&1 && user_is_admin_group; then
    ROOT_METHOD="sudo"
    echo "== O sudo solicitará autorização administrativa =="
  elif command -v pkexec >/dev/null 2>&1 && [[ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]]; then
    ROOT_METHOD="pkexec"
    echo "== O PolicyKit abrirá uma janela de autorização =="
  elif command -v su >/dev/null 2>&1; then
    ROOT_METHOD="su"
    echo "== O su solicitará a senha da conta root =="
  else
    echo "Não foi encontrado um método de autorização administrativa." >&2
    exit 1
  fi
}

run_root() {
  choose_root_method
  case "$ROOT_METHOD" in
    root) "$@" ;;
    sudo) sudo "$@" ;;
    pkexec) pkexec "$@" ;;
    su)
      local command
      command="$(quote_command "$@")"
      su -c "$command"
      ;;
    *) echo "Método administrativo inválido." >&2; exit 1 ;;
  esac
}

run_user() {
  if [[ ${EUID} -eq 0 ]]; then
    /usr/sbin/runuser -u "$TARGET_USER" -- /usr/bin/env HOME="$TARGET_HOME" "$@"
  else
    "$@"
  fi
}

cleanup() {
  if [[ -n "$TEMP_SOURCE" ]]; then
    case "$TEMP_SOURCE" in
      "$CACHE_DIR"/bootstrap.*) run_user rm -rf -- "$TEMP_SOURCE" ;;
    esac
  fi
}
trap cleanup EXIT

ensure_download_tools() {
  if command -v git >/dev/null 2>&1; then
    return
  fi
  echo "== Instalando Git para baixar o projeto =="
  run_root /usr/bin/apt-get update
  run_root /usr/bin/apt-get install -y git ca-certificates
}

fresh_source() {
  run_user mkdir -p "$CACHE_DIR"
  TEMP_SOURCE="$(run_user mktemp -d "$CACHE_DIR/bootstrap.XXXXXX")"
  run_user git clone --depth 1 --branch main "$REPO_URL" "$TEMP_SOURCE"
  SOURCE_DIR="$TEMP_SOURCE"
}

ensure_download_tools
SOURCE_DIR="$PROJECT_DIR"
if [[ -d "$PROJECT_DIR/.git" ]]; then
  echo "== Verificando atualização do projeto =="
  UPDATE_READY=1
  if run_user git -C "$PROJECT_DIR" remote get-url origin >/dev/null 2>&1; then
    run_user git -C "$PROJECT_DIR" remote set-url origin "$REPO_URL" || UPDATE_READY=0
  else
    run_user git -C "$PROJECT_DIR" remote add origin "$REPO_URL" || UPDATE_READY=0
  fi
  if [[ "$UPDATE_READY" -eq 1 ]] &&
     run_user git -C "$PROJECT_DIR" fetch --prune origin main; then
    BRANCH="$(run_user git -C "$PROJECT_DIR" symbolic-ref --short -q HEAD || true)"
  else
    BRANCH=""
    UPDATE_READY=0
  fi
  if [[ "$UPDATE_READY" -eq 1 && "$BRANCH" == "main" ]] &&
     [[ -z "$(run_user git -C "$PROJECT_DIR" status --porcelain)" ]] &&
     run_user git -C "$PROJECT_DIR" merge-base --is-ancestor HEAD origin/main; then
    run_user git -C "$PROJECT_DIR" merge --ff-only origin/main
  else
    echo "A cópia existente não pode ser atualizada com segurança; ela será preservada."
    fresh_source
  fi
elif [[ -e "$PROJECT_DIR" ]]; then
  echo "A pasta $PROJECT_DIR já existe e não é um repositório; ela será preservada."
  fresh_source
else
  echo "== Baixando projeto =="
  run_user mkdir -p "$(dirname "$PROJECT_DIR")"
  run_user git clone --depth 1 --branch main "$REPO_URL" "$PROJECT_DIR"
fi

INSTALL_MODE="$MODE"
if [[ "$MODE" == "--auto" ]]; then
  if [[ -x /opt/neri-printer-manager/venv/bin/python ]]; then
    INSTALL_MODE="--fast"
  else
    INSTALL_MODE="--normal"
  fi
fi
INSTALL_ARGS=()
[[ "$INSTALL_MODE" == "--normal" ]] || INSTALL_ARGS=("$INSTALL_MODE")

echo "== Instalando para $TARGET_USER (modo ${INSTALL_MODE#--}) =="
if ! run_root /usr/bin/env NERI_TARGET_USER="$TARGET_USER" \
  /usr/bin/bash "$SOURCE_DIR/install.sh" "${INSTALL_ARGS[@]}"; then
  echo "A instalação falhou. Consulte /var/log/neri-printer-manager-install.log." >&2
  exit 1
fi

hash -r
command -v neri-printer-manager >/dev/null 2>&1 || {
  echo "O comando neri-printer-manager não foi encontrado após a instalação." >&2
  exit 1
}

echo
echo "Instalação concluída para $TARGET_USER."
echo "Abra pelo menu ou execute: neri-printer-manager"

if [[ ${EUID} -ne 0 && -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]]; then
  STATE_DIR="$TARGET_HOME/.local/state/neri-printer-manager"
  mkdir -p "$STATE_DIR"
  chmod 0700 "$STATE_DIR"
  touch "$STATE_DIR/startup.log"
  chmod 0600 "$STATE_DIR/startup.log"
  nohup neri-printer-manager >"$STATE_DIR/startup.log" 2>&1 &
fi
