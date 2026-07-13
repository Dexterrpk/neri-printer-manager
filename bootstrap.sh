#!/usr/bin/env bash
set -Eeuo pipefail

REPO_URL="https://github.com/Dexterrpk/neri-printer-manager.git"
PROJECT_DIR="${NERI_PROJECT_DIR:-${HOME}/neri-printer-manager}"
MODE="${1:---fast}"

case "$MODE" in
  --fast|--normal|--repair) ;;
  -h|--help)
    cat <<'EOF'
Uso:
  bash bootstrap.sh            # atualização rápida (padrão)
  bash bootstrap.sh --normal   # verifica e instala somente pacotes ausentes
  bash bootstrap.sh --repair   # reinstala dependências e recria o aplicativo
EOF
    exit 0
    ;;
  *)
    echo "Opção inválida: $MODE" >&2
    echo "Use --fast, --normal ou --repair." >&2
    exit 2
    ;;
esac

if ! command -v sudo >/dev/null 2>&1; then
  echo "sudo não está instalado." >&2
  exit 1
fi

# Garante apenas as ferramentas necessárias para obter o projeto.
if ! command -v git >/dev/null 2>&1; then
  sudo apt-get update
  sudo apt-get install -y git ca-certificates
fi

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

cd "$PROJECT_DIR"
chmod +x install.sh

if [[ "$MODE" == "--normal" ]]; then
  sudo bash ./install.sh
else
  sudo bash ./install.sh "$MODE"
fi

hash -r

if command -v neri-printer-manager >/dev/null 2>&1; then
  echo
  echo "Instalação concluída. Iniciando o Neri Printer Manager..."
  exec neri-printer-manager
fi

echo "Instalação concluída, mas o atalho neri-printer-manager não foi encontrado." >&2
exit 1
