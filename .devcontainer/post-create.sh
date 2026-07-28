#!/usr/bin/env bash
set -Eeuo pipefail

if [[ ! -x .venv/bin/python ]]; then
  /usr/bin/python3 -m venv --clear --system-site-packages .venv
fi
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -e '.[dev]'
.venv/bin/python -m compileall -q src
.venv/bin/ruff format --check .
.venv/bin/ruff check .
.venv/bin/mypy src
QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q
