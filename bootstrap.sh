#!/usr/bin/env bash
set -Eeuo pipefail

REPO_URL="https://github.com/Dexterrpk/neri-printer-manager.git"
MODE="${1:---auto}"
ROOT_METHOD=""

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
[[ -n "$TARGET_HOME" ]] || {
  echo "Não foi possível localizar a pasta do usuário $TARGET_USER." >&2
  exit 1
}
PROJECT_DIR="${NERI_PROJECT_DIR:-$TARGET_HOME/neri-printer-manager}"

quote_command() {
  local out="" arg
  for arg in "$@"; do printf -v out '%s %q' "$out" "$arg"; done
  printf '%s' "${out# }"
}

user_is_admin_group() {
  id -nG "$TARGET_USER" 2>/dev/null | tr ' ' '\n' | grep -Eq '^(sudo|admin|wheel)$'
}

choose_root_method() {
  [[ -n "$ROOT_METHOD" ]] && return 0

  if [[ ${EUID} -eq 0 ]]; then
    ROOT_METHOD="root"
    return 0
  fi

  if command -v sudo >/dev/null 2>&1 && user_is_admin_group; then
    ROOT_METHOD="sudo"
    echo "== A autenticação administrativa será solicitada pelo sudo =="
    return 0
  fi

  # Não executa um teste separado com pkexec. A primeira ação administrativa real
  # abre a janela do PolicyKit, evitando a impressão de que a senha foi ignorada.
  if command -v pkexec >/dev/null 2>&1 && [[ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]]; then
    ROOT_METHOD="pkexec"
    echo "== Uma janela do PolicyKit solicitará uma conta administrativa =="
    return 0
  fi

  if command -v su >/dev/null 2>&1; then
    ROOT_METHOD="su"
    echo "== Será solicitada a senha da conta root pelo su =="
    echo "Atenção: não é necessariamente a senha do usuário $TARGET_USER."
    return 0
  fi

  cat >&2 <<EOF
Não foi encontrado um método de autenticação administrativa.
Peça a um administrador para instalar sudo/PolicyKit ou executar o instalador para o usuário $TARGET_USER.
EOF
  exit 1
}

run_root() {
  choose_root_method
  case "$ROOT_METHOD" in
    root) "$@" ;;
    sudo)
      if ! sudo "$@"; then
        echo "O sudo recusou a autenticação ou a operação administrativa falhou." >&2
        exit 1
      fi
      ;;
    pkexec)
      if ! pkexec "$@"; then
        echo "A autenticação do PolicyKit foi cancelada, recusada ou não há agente gráfico ativo." >&2
        echo "Entre com uma conta administrativa na janela exibida ou peça ajuda ao administrador." >&2
        exit 1
      fi
      ;;
    su)
      local command
      command="$(quote_command "$@")"
      if ! su -c "$command"; then
        echo "A senha root foi recusada ou a conta root está desabilitada." >&2
        echo "Use uma conta administrativa pelo PolicyKit ou sudo." >&2
        exit 1
      fi
      ;;
    *) echo "Método administrativo inválido." >&2; exit 1 ;;
  esac
}

ensure_download_tools() {
  if command -v git >/dev/null 2>&1; then return; fi
  echo "== Instalando ferramenta necessária para baixar o projeto =="
  run_root /usr/bin/apt-get update
  run_root /usr/bin/apt-get install -y git ca-certificates
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
run_root /usr/bin/env NERI_TARGET_USER="$TARGET_USER" /usr/bin/bash "$PROJECT_DIR/install.sh" "${INSTALL_ARGS[@]}"

hash -r
if ! command -v neri-printer-manager >/dev/null 2>&1; then
  echo "Instalação concluída, mas o comando neri-printer-manager não foi encontrado." >&2
  exit 1
fi

echo
echo "Instalação concluída para $TARGET_USER."
echo "Abra pelo menu ou execute: neri-printer-manager"

if [[ ${EUID} -ne 0 && -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]]; then
  nohup neri-printer-manager >/tmp/neri-printer-manager-start.log 2>&1 &
fi
