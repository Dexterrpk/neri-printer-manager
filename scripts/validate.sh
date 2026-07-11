#!/usr/bin/env bash
set -Eeuo pipefail

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV="${VENV:-.venv}"

if [[ ! -x "${VENV}/bin/python" ]]; then
  "${PYTHON_BIN}" -m venv "${VENV}"
fi

"${VENV}/bin/python" -m pip install --upgrade pip
"${VENV}/bin/pip" install -e '.[dev]'
"${VENV}/bin/ruff" check .
"${VENV}/bin/mypy" src/neri_printer_manager
"${VENV}/bin/pytest" -q
"${VENV}/bin/python" -m compileall -q src

echo "Validação concluída com sucesso."
