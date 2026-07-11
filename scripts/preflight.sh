#!/usr/bin/env bash
set -Eeuo pipefail

failures=0
check_command() {
  if command -v "$1" >/dev/null 2>&1; then
    printf '[OK] %s\n' "$1"
  else
    printf '[ERRO] %s ausente\n' "$1"
    failures=$((failures + 1))
  fi
}

for command in python3 lpstat lpinfo lpadmin lp cupsctl systemctl pkexec journalctl; do
  check_command "$command"
done

if systemctl is-active --quiet cups.service; then
  echo '[OK] cups.service ativo'
else
  echo '[ERRO] cups.service inativo'
  failures=$((failures + 1))
fi

if [[ -x /usr/libexec/neri-printer-helper ]]; then
  echo '[OK] helper administrativo instalado'
else
  echo '[AVISO] helper administrativo ainda não instalado'
fi

if [[ -f /usr/share/polkit-1/actions/com.neriinfotech.printermanager.policy ]]; then
  echo '[OK] política Polkit instalada'
else
  echo '[AVISO] política Polkit ainda não instalada'
fi

if (( failures > 0 )); then
  printf 'Pré-validação concluída com %d falha(s).\n' "$failures" >&2
  exit 1
fi

echo 'Pré-validação concluída com sucesso.'
