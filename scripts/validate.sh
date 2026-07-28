#!/usr/bin/env bash
set -Eeuo pipefail

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV="${VENV:-.venv}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"
VENV_PATH="$(realpath -m "$VENV")"
case "$VENV_PATH" in
  "$PROJECT_ROOT"/*) ;;
  *) echo "O ambiente virtual precisa ficar dentro do projeto." >&2; exit 2 ;;
esac

if [[ ! -x "${VENV_PATH}/bin/python" ]]; then
  "${PYTHON_BIN}" -m venv --clear --system-site-packages "${VENV_PATH}"
fi

"${VENV_PATH}/bin/python" -m pip install --upgrade pip
"${VENV_PATH}/bin/pip" install -e '.[dev]'
"${VENV_PATH}/bin/ruff" format --check .
"${VENV_PATH}/bin/ruff" check .
"${VENV_PATH}/bin/mypy" src
QT_QPA_PLATFORM=offscreen "${VENV_PATH}/bin/pytest" -q
"${VENV_PATH}/bin/python" -m compileall -q src
bash -n bootstrap.sh install.sh uninstall.sh scripts/*.sh

echo "Validação concluída com sucesso."
