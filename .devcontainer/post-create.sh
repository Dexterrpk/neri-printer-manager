#!/usr/bin/env bash
set -Eeuo pipefail

python -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -e '.[dev]'
.venv/bin/python -m compileall -q src
.venv/bin/ruff check .
.venv/bin/pytest -q
