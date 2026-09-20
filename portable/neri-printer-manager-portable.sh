#!/usr/bin/env bash
# Neri Printer Manager Portable - modo local, seguro e efêmero.
# Não altera firewall, DNS, DHCP, rotas, interfaces, Zentyal ou hosts remotos.

set -u
set -o pipefail
umask 077
export LC_ALL=C LANG=C LANGUAGE=C

APP_NAME="Neri Printer Manager Portable"
APP_VERSION="3.0.0-portable"
TMP_ROOT="$(mktemp -d /tmp/neri-printer-manager.XXXXXX)"
REPORT="$TMP_ROOT/report.txt"
BACKUP_DONE=0
SELECTED_QUEUE=""
TEST_JOB_ID=""

declare -a FINDING_CODES=()
declare -a FINDING_TITLES=()
declare -a FINDING_DETAILS=()
declare -a FINDING_REPAIRS=()

cleanup() {
  rm -rf -- "$TMP_ROOT" 2>/dev/null || true
}
trap cleanup EXIT HUP INT TERM

say() { printf '%s\n' "$*"; }
hr() { printf '%*s\n' 72 '' | tr ' ' '='; }
pause() { read -r -p "Pressione ENTER para continuar..." _ || true; }

need_cmd() {
  command -v "$1" >/dev/null 2>&1
}

validate_queue() {
  [[ "$1" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]{0,126}$ ]]
}

validate_job() {
  [[ "$1" =~ ^[A-Za-z0-9_.-]+-[0-9]+$ ]]
}

safe_uri() {
  case "$1" in
    usb:*|hp:*|ipp://*|ipps://*|socket://*|lpd://*|smb://*) return 0 ;;
    *) return 1 ;;
  esac
}

require_base() {
  local missing=()
  local c
  for c in lpstat lp lpadmin cupsenable cupsaccept cupsd systemctl; do
    need_cmd "$c" || missing+=("$c")
  done
  if ((${#missing[@]})); then
    say "ERRO: faltam comandos essenciais: ${missing[*]}"
    say "Este modo portátil não instala o próprio aplicativo nem dependências automaticamente."
    exit 1
  fi
}

add_finding() {
  FINDING_CODES+=("$1")
  FINDING_TITLES+=("$2")
  FINDING_DETAILS+=("$3")
  FINDING_REPAIRS+=("$4")
}

reset_findings() {
  FINDING_CODES=()
  FINDING_TITLES=()
  FINDING_DETAILS=()
  FINDING_REPAIRS=()
}

queue_names() {
  lpstat -p 2>/dev/null | awk '$1=="printer" {print $2}' | awk '!seen[$0]++'
}

choose_queue() {
  local queues=() i ans
  mapfile -t queues < <(queue_names)
  if ((${#queues[@]} == 0)); then
    say "Nenhuma fila local encontrada no CUPS."
    return 1
  fi
  say
  say "Impressoras configuradas:"
  for i in "${!queues[@]}"; do
    printf '  %d) %s\n' "$((i+1))" "${queues[$i]}"
  done
  read -r -p "Escolha: " ans
  [[ "$ans" =~ ^[0-9]+$ ]] || return 1
  ((ans >= 1 && ans <= ${#queues[@]})) || return 1
  SELECTED_QUEUE="${queues[$((ans-1))]}"
  validate_queue "$SELECTED_QUEUE" || { say "Nome de fila inválido."; return 1; }
}

queue_uri() {
  local q="$1"
  lpstat -v "$q" 2>/dev/null | sed -n "s/^device for ${q}: //p" | head -n1
}

queue_enabled() {
  ! lpstat -p "$1" 2>/dev/null | grep -qi 'disabled'
}

queue_accepting() {
  lpstat -a "$1" 2>/dev/null | grep -q '^.* accepting requests'
}

backup_cups() {
  ((BACKUP_DONE == 1)) && return 0
  local b="$TMP_ROOT/backup"
  mkdir -p "$b"
  say "Criando backup temporário de segurança..."
  sudo cp -a /etc/cups/cupsd.conf "$b/cupsd.conf" 2>/dev/null || true
  sudo cp -a /etc/cups/printers.conf "$b/printers.conf" 2>/dev/null || true
  if [[ -n "$SELECTED_QUEUE" && -f "/etc/cups/ppd/$SELECTED_QUEUE.ppd" ]]; then
    sudo cp -a "/etc/cups/ppd/$SELECTED_QUEUE.ppd" "$b/$SELECTED_QUEUE.ppd" 2>/dev/null || true
  fi
  BACKUP_DONE=1
}

restore_cups_files() {
  local b="$TMP_ROOT/backup"
  [[ -d "$b" ]] || return 1
  say "Restaurando configuração anterior..."
  [[ -f "$b/cupsd.conf" ]] && sudo cp -a "$b/cupsd.conf" /etc/cups/cupsd.conf
  [[ -f "$b/printers.conf" ]] && sudo cp -a "$b/printers.conf" /etc/cups/printers.conf
  if [[ -n "$SELECTED_QUEUE" && -f "$b/$SELECTED_QUEUE.ppd" ]]; then
    sudo cp -a "$b/$SELECTED_QUEUE.ppd" "/etc/cups/ppd/$SELECTED_QUEUE.ppd"
  fi
  if sudo cupsd -t >/dev/null 2>&1; then
    sudo systemctl restart cups
  else
    say "ATENÇÃO: o backup restaurado também não passou na validação do CUPS."
    return 1
  fi
}

cups_config_error() {
  sudo cupsd -t 2>&1 || true
}

recent_queue_log() {
  local q="$1"
  [[ -r /var/log/cups/error_log ]] || { sudo tail -n 400 /var/log/cups/error_log 2>/dev/null || true; return; }
  tail -n 400 /var/log/cups/error_log 2>/dev/null || true
}

job_log() {
  local jobnum="$1"
  local pattern="\\[Job ${jobnum}\\]"
  if [[ -r /var/log/cups/error_log ]]; then
    grep -E "$pattern" /var/log/cups/error_log 2>/dev/null | tail -n 80 || true
  else
    sudo grep -E "$pattern" /var/log/cups/error_log 2>/dev/null | tail -n 80 || true
  fi
}

extract_job_number() {
  local id="$1"
  printf '%s' "${id##*-}"
}

probe_target_port() {
  local uri="$1" host="" port=""
  case "$uri" in
    socket://*) port=9100 ;;
    ipp://*|ipps://*) port=631 ;;
    lpd://*) port=515 ;;
    smb://*) port=445 ;;
    *) return 0 ;;
  esac
  local rest="${uri#*://}"
  rest="${rest#*@}"
  host="${rest%%/*}"
  host="${host%%:*}"
  [[ -n "$host" ]] || return 0
  if need_cmd nc; then
    if ! nc -z -w 2 "$host" "$port" >/dev/null 2>&1; then
      add_finding "NETWORK_TARGET_UNREACHABLE" "Impressora de rede não respondeu" "O alvo específico $host não respondeu na porta $port. Nenhuma varredura de rede foi feita." "none"
    fi
  fi
}

diagnose_passive() {
  local q="$1" uri state cfg backend serial log
  reset_findings
  hr
  say "Diagnóstico: $q"
  hr

  if ! systemctl is-active --quiet cups; then
    add_finding "CUPS_DOWN" "CUPS está parado" "O serviço cups.service não está ativo." "restart_cups"
  fi

  cfg="$(cups_config_error)"
  if ! sudo cupsd -t >/dev/null 2>&1; then
    add_finding "CUPS_CONFIG_INVALID" "Configuração do CUPS inválida" "${cfg//$'\n'/ }" "repair_cups_config"
  fi

  if ! queue_enabled "$q"; then
    add_finding "QUEUE_DISABLED" "Fila pausada/desabilitada" "A fila $q está desabilitada." "enable_queue"
  fi
  if ! queue_accepting "$q"; then
    add_finding "QUEUE_REJECTING" "Fila recusando trabalhos" "A fila $q não está aceitando novos trabalhos." "accept_queue"
  fi

  uri="$(queue_uri "$q")"
  if [[ -z "$uri" ]]; then
    add_finding "URI_MISSING" "URI ausente" "O CUPS não informou um dispositivo para a fila." "none"
  elif ! safe_uri "$uri"; then
    add_finding "URI_UNSUPPORTED" "URI não reconhecida" "A URI usa um esquema fora do catálogo seguro do modo portátil." "none"
  else
    say "URI: $uri"
    backend="${uri%%:*}"
    [[ "$backend" == "ipps" ]] && backend="ipp"
    if [[ "$backend" =~ ^(hp|usb|ipp|socket|lpd|smb)$ ]] && [[ ! -x "/usr/lib/cups/backend/$backend" ]]; then
      add_finding "BACKEND_MISSING" "Backend do CUPS ausente" "Não encontrei executável /usr/lib/cups/backend/$backend." "repair_backend"
    fi
    if [[ "$uri" == hp:/usb/* || "$uri" == usb:* ]]; then
      serial="${uri##*serial=}"
      [[ "$serial" == "$uri" ]] && serial=""
      if need_cmd lpinfo; then
        if [[ -n "$serial" ]]; then
          lpinfo -v 2>/dev/null | grep -Fq "$serial" || add_finding "USB_NOT_VISIBLE" "USB não localizado" "A fila aponta para o serial $serial, mas ele não apareceu no lpinfo -v." "none"
        else
          lpinfo -v 2>/dev/null | grep -Eiq '(^|[[:space:]])(direct[[:space:]]+)?(usb:|hp:/usb/)' || add_finding "USB_NOT_VISIBLE" "Nenhuma impressora USB visível" "O CUPS não listou dispositivo USB/HP disponível." "none"
        fi
      fi
    fi
    probe_target_port "$uri"
  fi

  if [[ ! -f "/etc/cups/ppd/$q.ppd" ]]; then
    # Filas driverless podem não depender de PPD legado.
    if [[ "$uri" != ipp://* && "$uri" != ipps://* ]]; then
      add_finding "PPD_MISSING" "Driver/PPD não encontrado" "Não existe /etc/cups/ppd/$q.ppd para esta fila não-driverless." "none"
    fi
  fi

  if lpstat -o "$q" 2>/dev/null | grep -q .; then
    add_finding "JOBS_PENDING" "Há trabalhos pendentes" "Existem trabalhos ainda não concluídos nesta fila." "jobs"
  fi

  log="$(recent_queue_log "$q")"
  if grep -Fq "client-error-not-authorized" <<<"$log" && grep -Fq "$q" <<<"$log"; then
    add_finding "AUTH_DENIED" "Permissão da fila bloqueando operação" "O log recente contém client-error-not-authorized para $q." "fix_queue_permissions"
  fi
  if grep -Eqi 'Missing integer value for MaxJobs' <<<"$log"; then
    add_finding "MAXJOBS_INVALID" "Diretiva MaxJobs inválida" "O CUPS registrou MaxJobs sem valor inteiro." "fix_maxjobs"
  fi

  show_findings
}

show_findings() {
  local i
  say
  if ((${#FINDING_CODES[@]} == 0)); then
    say "Nenhum problema passivo confirmado."
    return 0
  fi
  say "Problemas/evidências encontradas:"
  for i in "${!FINDING_CODES[@]}"; do
    printf '\n[%d] %s\n    Código: %s\n    Evidência: %s\n' "$((i+1))" "${FINDING_TITLES[$i]}" "${FINDING_CODES[$i]}" "${FINDING_DETAILS[$i]}"
  done
}

append_job_findings() {
  local q="$1" jobid="$2" jobnum log
  jobnum="$(extract_job_number "$jobid")"
  [[ "$jobnum" =~ ^[0-9]+$ ]] || return 0
  log="$(job_log "$jobnum")"
  [[ -n "$log" ]] || return 0

  if grep -Eqi 'Backend hp returned status [1-9]|backend hp.*failed' <<<"$log"; then
    add_finding "HP_BACKEND_FAILED" "Falha confirmada no backend HPLIP" "O trabalho $jobid chegou ao CUPS, mas o backend hp retornou falha." "repair_hplip"
  fi
  if grep -Eqi 'PrintSpy:.*URI.*inválida|PrintSpy:.*URI.*invalid' <<<"$log"; then
    add_finding "PRINTSPY_URI_INVALID" "PrintSpy rejeitou a URI" "O PrintSpy informou URI inválida no trabalho $jobid." "none"
  fi
  if grep -Eqi 'filter failed|stopped with status [1-9]|Filter failed' <<<"$log"; then
    if grep -Eqi 'ghostscript|gs:' <<<"$log"; then
      add_finding "GHOSTSCRIPT_FAILED" "Falha no Ghostscript" "O trabalho $jobid apresentou erro ligado ao Ghostscript." "repair_ghostscript"
    else
      add_finding "FILTER_FAILED" "Falha em filtro do CUPS" "O trabalho $jobid apresentou falha em filtro." "repair_cups_filters"
    fi
  fi
  if grep -Eqi 'permission denied' <<<"$log"; then
    add_finding "FILTER_PERMISSION" "Permissão negada em filtro/backend" "O trabalho $jobid contém Permission denied." "repair_package_permissions"
  fi
  if grep -Eqi 'Unable to open PPD|PPD.*(missing|not found|bad value)' <<<"$log"; then
    add_finding "PPD_BAD" "PPD ausente ou inválido" "O log do trabalho $jobid aponta problema no PPD." "none"
  fi
  if grep -Eqi 'Unable to connect|Connection refused|Broken pipe' <<<"$log"; then
    add_finding "COMMUNICATION_FAILED" "Falha de comunicação" "O backend não conseguiu manter comunicação com o destino." "none"
  fi
}

run_test_job() {
  local q="$1" out rc jobid
  say
  read -r -p "Enviar uma página de teste para diagnóstico completo? [S/n] " out
  [[ "$out" =~ ^[Nn]$ ]] && return 0

  if [[ ! -r /usr/share/cups/data/testprint ]]; then
    say "Página padrão do CUPS não encontrada. Teste ignorado."
    return 0
  fi

  say "Enviando página de teste para $q..."
  if out="$(lp -d "$q" /usr/share/cups/data/testprint 2>&1)"; then
    rc=0
  else
    rc=$?
  fi
  say "$out"
  if ((rc != 0)); then
    if grep -Eqi 'not authorized|permission|permiss' <<<"$out"; then
      add_finding "AUTH_DENIED" "Permissão para imprimir negada" "$out" "fix_queue_permissions"
    else
      add_finding "TEST_SUBMIT_FAILED" "Falha ao criar trabalho de teste" "$out" "none"
    fi
    return 0
  fi
  jobid="$(sed -n 's/.*request id is \([^ ]*\).*/\1/p' <<<"$out")"
  [[ -z "$jobid" ]] && jobid="$(sed -n 's/.*id de requisição é \([^ ]*\).*/\1/p' <<<"$out")"
  [[ -z "$jobid" ]] && jobid="$(grep -oE '[A-Za-z0-9_.-]+-[0-9]+' <<<"$out" | head -n1 || true)"
  TEST_JOB_ID="$jobid"
  sleep 8
  if [[ -n "$jobid" ]]; then
    append_job_findings "$q" "$jobid"
    if lpstat -W not-completed -o "$q" 2>/dev/null | grep -Fq "$jobid"; then
      add_finding "TEST_STILL_PENDING" "Teste ainda não concluiu" "O trabalho $jobid continua pendente após a espera inicial." "jobs"
    fi
  fi
  show_findings
}

confirm() {
  local prompt="$1" ans
  read -r -p "$prompt [s/N] " ans
  [[ "$ans" =~ ^[SsYy]$ ]]
}

validate_and_restart_cups() {
  if ! sudo cupsd -t; then
    say "Validação do CUPS falhou. A alteração não será ativada."
    restore_cups_files || true
    return 1
  fi
  sudo systemctl restart cups
  sleep 2
  systemctl is-active --quiet cups
}

fix_maxjobs() {
  local err line n tmp
  err="$(cups_config_error)"
  line="$(grep -Eo 'line [0-9]+' <<<"$err" | head -n1 | awk '{print $2}')"
  [[ "$line" =~ ^[0-9]+$ ]] || { say "Não consegui localizar a linha inválida."; return 1; }
  n="$(sudo sed -n "${line}p" /etc/cups/cupsd.conf | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
  [[ "$n" =~ ^MaxJobs([[:space:]]*)$ ]] || { say "A linha não é exatamente um MaxJobs sem valor; não vou alterá-la automaticamente."; return 1; }
  backup_cups
  tmp="$TMP_ROOT/cupsd.conf.new"
  sudo cat /etc/cups/cupsd.conf > "$tmp"
  sed -i "${line}s/^/# NeriPM disabled invalid directive: /" "$tmp"
  sudo cp "$tmp" /etc/cups/cupsd.conf
  validate_and_restart_cups
}

repair_hplip() {
  say "Esta correção reinstala apenas componentes locais HP/HPLIP."
  confirm "Reparar HPLIP/HPCUPS?" || return 0
  backup_cups
  sudo apt-get update || return 1
  sudo apt-get install --reinstall -y hplip hplip-data printer-driver-hpcups || return 1
  if need_cmd hp-plugin; then
    say "Se o modelo exigir plugin proprietário, o instalador HP será aberto agora."
    confirm "Executar hp-plugin em modo interativo?" && sudo hp-plugin -i || true
  fi
  validate_and_restart_cups
}

repair_filters() {
  confirm "Reinstalar cups-filters e validar o CUPS?" || return 0
  backup_cups
  sudo apt-get update || return 1
  sudo apt-get install --reinstall -y cups-filters || return 1
  validate_and_restart_cups
}

repair_ghostscript() {
  confirm "Reinstalar Ghostscript?" || return 0
  sudo apt-get update || return 1
  sudo apt-get install --reinstall -y ghostscript || return 1
  validate_and_restart_cups
}

repair_backend() {
  local q="$1" uri scheme pkg=""
  uri="$(queue_uri "$q")"
  scheme="${uri%%:*}"
  case "$scheme" in
    hp) pkg="hplip" ;;
    usb|ipp|ipps|socket|lpd) pkg="cups" ;;
    smb) pkg="smbclient" ;;
    *) say "Backend desconhecido; nenhuma alteração automática."; return 0 ;;
  esac
  confirm "Reinstalar o pacote $pkg associado ao backend $scheme?" || return 0
  backup_cups
  sudo apt-get update || return 1
  sudo apt-get install --reinstall -y "$pkg" || return 1
  validate_and_restart_cups
}

fix_permissions() {
  local q="$1"
  confirm "Liberar impressão para usuários nesta fila específica ($q)?" || return 0
  backup_cups
  sudo lpadmin -p "$q" -u allow:all || { restore_cups_files || true; return 1; }
  validate_and_restart_cups
}

apply_repairs() {
  local q="$1" i action code
  ((${#FINDING_CODES[@]})) || { say "Nenhuma correção automática necessária."; return 0; }
  say
  say "As correções abaixo são locais. Rede, firewall, DNS, DHCP, rotas e Zentyal não serão alterados."
  confirm "Deseja avaliar as correções disponíveis uma a uma?" || return 0

  for i in "${!FINDING_CODES[@]}"; do
    action="${FINDING_REPAIRS[$i]}"
    code="${FINDING_CODES[$i]}"
    case "$action" in
      restart_cups)
        if sudo cupsd -t >/dev/null 2>&1 && confirm "[$code] Reiniciar somente o serviço CUPS?"; then sudo systemctl restart cups; fi
        ;;
      repair_cups_config)
        if [[ "$code" == "CUPS_CONFIG_INVALID" ]] && cups_config_error | grep -q 'Missing integer value for MaxJobs'; then
          confirm "[$code] Corrigir apenas a diretiva MaxJobs inválida?" && fix_maxjobs || true
        else
          say "[$code] Configuração inválida não reconhecida com segurança; correção automática bloqueada."
        fi
        ;;
      fix_maxjobs) confirm "[$code] Corrigir MaxJobs inválido?" && fix_maxjobs || true ;;
      enable_queue) confirm "[$code] Habilitar somente $q?" && sudo cupsenable "$q" || true ;;
      accept_queue) confirm "[$code] Fazer somente $q aceitar trabalhos?" && sudo cupsaccept "$q" || true ;;
      fix_queue_permissions) fix_permissions "$q" || true ;;
      repair_hplip) repair_hplip || true ;;
      repair_cups_filters) repair_filters || true ;;
      repair_ghostscript) repair_ghostscript || true ;;
      repair_backend) repair_backend "$q" || true ;;
      jobs) say "[$code] Use o menu Fila; trabalhos nunca são cancelados em massa automaticamente." ;;
      repair_package_permissions) say "[$code] Permissão de arquivo precisa ser vinculada ao pacote dono; nenhuma chmod em massa será executada." ;;
      none) say "[$code] Sem correção automática segura; somente diagnóstico." ;;
    esac
  done

  say
  say "Revalidando..."
  diagnose_passive "$q"
}

manage_jobs() {
  local jobs=() i ans id
  mapfile -t jobs < <(lpstat -o 2>/dev/null)
  if ((${#jobs[@]} == 0)); then say "Nenhum trabalho pendente."; return 0; fi
  say "Trabalhos pendentes:"
  for i in "${!jobs[@]}"; do printf '  %d) %s\n' "$((i+1))" "${jobs[$i]}"; done
  read -r -p "Escolha um trabalho para cancelar (0 = voltar): " ans
  [[ "$ans" =~ ^[0-9]+$ ]] || return 0
  ((ans == 0)) && return 0
  ((ans >= 1 && ans <= ${#jobs[@]})) || return 0
  id="$(awk '{print $1}' <<<"${jobs[$((ans-1))]}")"
  validate_job "$id" || { say "ID inválido; cancelamento bloqueado."; return 1; }
  confirm "Cancelar somente $id?" && cancel "$id"
}

install_detected() {
  need_cmd lpinfo || { say "lpinfo não está disponível."; return 1; }
  local devices=() i ans uri name model models=() msel
  mapfile -t devices < <(lpinfo -v 2>/dev/null | awk 'NF>=2 {print $2}' | grep -E '^(usb:|hp:|ipp://|ipps://|socket://|lpd://|smb://)' | awk '!seen[$0]++')
  ((${#devices[@]})) || { say "Nenhum dispositivo compatível foi detectado."; return 0; }
  say "Dispositivos detectados:"
  for i in "${!devices[@]}"; do printf '  %d) %s\n' "$((i+1))" "${devices[$i]}"; done
  read -r -p "Escolha (0 = voltar): " ans
  [[ "$ans" =~ ^[0-9]+$ ]] || return 0
  ((ans == 0)) && return 0
  ((ans >= 1 && ans <= ${#devices[@]})) || return 0
  uri="${devices[$((ans-1))]}"
  safe_uri "$uri" || { say "URI bloqueada."; return 1; }
  read -r -p "Nome local da fila (letras/números/ponto/hífen/_): " name
  validate_queue "$name" || { say "Nome inválido."; return 1; }

  if [[ "$uri" == ipp://* || "$uri" == ipps://* ]]; then
    model="everywhere"
  else
    say "Para USB/HP/Socket/LPD/SMB, escolha explicitamente um driver instalado."
    mapfile -t models < <(lpinfo -m 2>/dev/null | head -n 40)
    if ((${#models[@]} == 0)); then say "Nenhum driver listado."; return 1; fi
    for i in "${!models[@]}"; do printf '  %d) %s\n' "$((i+1))" "${models[$i]}"; done
    read -r -p "Driver (0 = cancelar): " msel
    [[ "$msel" =~ ^[0-9]+$ ]] || return 0
    ((msel == 0)) && return 0
    ((msel >= 1 && msel <= ${#models[@]})) || return 0
    model="$(awk '{print $1}' <<<"${models[$((msel-1))]}")"
    [[ "$model" =~ ^[A-Za-z0-9][A-Za-z0-9_./:+-]{0,511}$ ]] || { say "Driver inválido."; return 1; }
  fi

  say "Será criada somente a fila $name -> $uri. Nenhuma configuração de rede será alterada."
  confirm "Criar fila?" || return 0
  backup_cups
  sudo lpadmin -p "$name" -E -v "$uri" -m "$model" || { restore_cups_files || true; return 1; }
  sudo cupsenable "$name" || true
  sudo cupsaccept "$name" || true
  if ! sudo cupsd -t >/dev/null 2>&1; then restore_cups_files || true; return 1; fi
  say "Fila criada."
}

security_summary() {
  hr
  say "$APP_NAME $APP_VERSION"
  say "MODO SEGURO: somente host local e impressora explicitamente selecionada."
  say "PROIBIDO pelo desenho: firewall, DNS, DHCP, gateway, rotas, VLAN, interfaces, Zentyal, execução remota e scan de sub-rede."
  say "Arquivos temporários: $TMP_ROOT (apagados ao sair)."
  hr
}

main_menu() {
  local ans
  while true; do
    say
    say "1) Diagnosticar e corrigir uma impressora"
    say "2) Instalar impressora detectada"
    say "3) Fila de impressão"
    say "4) Ver estado do CUPS"
    say "0) Sair"
    read -r -p "Opção: " ans
    case "$ans" in
      1)
        if choose_queue; then
          diagnose_passive "$SELECTED_QUEUE"
          run_test_job "$SELECTED_QUEUE"
          apply_repairs "$SELECTED_QUEUE"
          pause
        fi
        ;;
      2) install_detected; pause ;;
      3) manage_jobs; pause ;;
      4)
        systemctl status cups --no-pager -l || true
        say
        sudo cupsd -t || true
        pause
        ;;
      0) say "Encerrando. Os arquivos temporários serão removidos."; break ;;
      *) say "Opção inválida." ;;
    esac
  done
}

if [[ "${NERI_PM_LIBRARY:-0}" != "1" ]]; then
  require_base
  security_summary
  main_menu
fi
