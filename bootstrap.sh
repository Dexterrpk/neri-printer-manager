#!/usr/bin/env bash
set -Eeuo pipefail

REPO_URL="https://github.com/Dexterrpk/neri-printer-manager.git"
MODE="${1:---auto}"

case "$MODE" in
  --auto|--fast|--normal|--repair) ;;
  -h|--help)
    cat <<'EOF'
Uso:
  bash bootstrap.sh            # escolhe automaticamente instalação ou atualização
  bash bootstrap.sh --fast     # atualização rápida
  bash bootstrap.sh --normal   # instala somente dependências ausentes
  bash bootstrap.sh --repair   # reinstala dependências e recria o aplicativo
EOF
    exit 0
    ;;
  *) echo "Opção inválida: $MODE" >&2; exit 2 ;;
esac

# O script deve ser iniciado pelo usuário que utilizará o programa. Mesmo sem sudo,
# ele usa su automaticamente e volta ao usuário comum ao terminar.
if [[ ${EUID} -eq 0 ]]; then
  TARGET_USER="${NERI_TARGET_USER:-${SUDO_USER:-$(logname 2>/dev/null || true)}}"
  [[ -n "$TARGET_USER" && "$TARGET_USER" != "root" ]] || {
    echo "Execute este comando no terminal do usuário comum, não dentro de um shell root." >&2
    exit 1
  }
else
  TARGET_USER="$(id -un)"
fi
TARGET_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
[[ -n "$TARGET_HOME" ]] || { echo "Não foi possível localizar a pasta do usuário $TARGET_USER." >&2; exit 1; }
PROJECT_DIR="${NERI_PROJECT_DIR:-$TARGET_HOME/neri-printer-manager}"

quote_command() {
  local out="" arg
  for arg in "$@"; do printf -v out '%s %q' "$out" "$arg"; done
  printf '%s' "${out# }"
}

run_root() {
  if [[ ${EUID} -eq 0 ]]; then
    "$@"
    return
  fi

  # Usa sudo para usuários autorizados. Caso contrário, pede diretamente a senha root via su.
  if command -v sudo >/dev/null 2>&1 && id -nG "$TARGET_USER" | tr ' ' '\n' | grep -Eq '^(sudo|admin|wheel)$'; then
    sudo "$@"
  elif command -v su >/dev/null 2>&1; then
    local command
    command="$(quote_command "$@")"
    su -c "$command"
  else
    echo "Não foi encontrado sudo nem su para obter privilégios administrativos." >&2
    exit 1
  fi
}

ensure_download_tools() {
  if command -v git >/dev/null 2>&1; then return; fi
  echo "== Instalando ferramenta necessária para baixar o projeto =="
  run_root apt-get update
  run_root apt-get install -y git ca-certificates
}

ensure_download_tools

if [[ -d "$PROJECT_DIR/.git" ]]; then
  echo "== Atualizando projeto existente =="
  git -C "$PROJECT_DIR" remote set-url origin "$REPO_URL"
  git -C "$PROJECT_DIR" fetch --prune origin
  git -C "$PROJECT_DIR" reset --hard origin/main
else
  echo "== Baixando projeto =="
  rm -rf "$PROJECT_DIR"
  git clone "$REPO_URL" "$PROJECT_DIR"
fi

INSTALL_MODE="$MODE"
if [[ "$MODE" == "--auto" ]]; then
  if [[ -x /opt/neri-printer-manager/venv/bin/python ]]; then
    INSTALL_MODE="--fast"
  else
    INSTALL_MODE="--normal"
  fi
fi

if [[ "$INSTALL_MODE" == "--normal" ]]; then
  INSTALL_ARGS=()
else
  INSTALL_ARGS=("$INSTALL_MODE")
fi

echo "== Instalando para o usuário $TARGET_USER (modo ${INSTALL_MODE#--}) =="
run_root env NERI_TARGET_USER="$TARGET_USER" bash "$PROJECT_DIR/install.sh" "${INSTALL_ARGS[@]}"

hash -r
if ! command -v neri-printer-manager >/dev/null 2>&1; then
  echo "Instalação concluída, mas o comando neri-printer-manager não foi encontrado." >&2
  exit 1
fi

echo
echo "Instalação concluída para $TARGET_USER."
echo "Abra pelo menu ou execute: neri-printer-manager"

# Só abre automaticamente quando ainda estamos na sessão gráfica do usuário comum.
if [[ ${EUID} -ne 0 && -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]]; then
  nohup neri-printer-manager >/tmp/neri-printer-manager-start.log 2>&1 &
fi
