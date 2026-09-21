#!/usr/bin/env bash
set -euo pipefail
umask 077

# Neri Printer Manager - lançador portátil oficial
# Criado por Cleiton Neri — Neri Infotech
# Esta versão baixa e executa uma revisão fixa e auditada do modo portátil.

PORTABLE_COMMIT="4dabceec7e43c8e9f20e690fa8266f1e9b4c22d6"
PORTABLE_URL="https://raw.githubusercontent.com/Dexterrpk/neri-printer-manager/${PORTABLE_COMMIT}/portable/neri-printer-manager-portable.sh"
TMP_FILE="$(mktemp /tmp/neri-printer-manager-launcher.XXXXXX.sh)"

cleanup() {
  rm -f -- "$TMP_FILE" 2>/dev/null || true
}
trap cleanup EXIT HUP INT TERM

if command -v curl >/dev/null 2>&1; then
  curl -fsSL --retry 2 --connect-timeout 10 "$PORTABLE_URL" -o "$TMP_FILE"
elif command -v wget >/dev/null 2>&1; then
  wget -qO "$TMP_FILE" "$PORTABLE_URL"
else
  echo "ERRO: curl ou wget é necessário para executar o modo portátil." >&2
  exit 1
fi

chmod 700 "$TMP_FILE"
bash "$TMP_FILE" "$@"
