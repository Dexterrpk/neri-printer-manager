#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORTABLE="$ROOT/portable/neri-printer-manager-portable.sh"
export NERI_PM_LIBRARY=1
source "$PORTABLE"

fail(){ echo "FAIL: $*" >&2; exit 1; }
pass(){ echo "PASS: $*"; }

validate_queue 'HP-P1102w_2' || fail queue-valid
! validate_queue 'HP P1102w' || fail queue-space
pass queue-validation

safe_uri 'hp:/usb/HP_LaserJet?serial=123' || fail hp-uri
safe_uri 'ipp://192.168.1.10/ipp/print' || fail ipp-uri
! safe_uri 'file:///etc/passwd' || fail unsafe-uri
pass uri-whitelist

mock=$(mktemp -d)
trap 'rm -rf "$mock"' EXIT
cat > "$mock/lpstat" <<'M'
#!/usr/bin/env bash
if [[ "$1" == "-p" ]]; then
cat <<'OUT'
printer HL-1200-series is idle. enabled since Fri
printer HP-LaserJet-Professional-P1102w is idle. enabled since Sat
    cfFilterChain: pdftopdf (PID 5287) exited with no errors.
printer HP-LaserJet-Professional-P1102w-2 is idle. enabled since Sat
OUT
fi
M
chmod +x "$mock/lpstat"
oldpath=$PATH
PATH="$mock:$PATH"
mapfile -t qs < <(queue_names)
PATH=$oldpath
[[ ${#qs[@]} -eq 3 ]] || fail "expected 3 queues, got ${#qs[@]}: ${qs[*]}"
[[ " ${qs[*]} " != *' or '* ]] || fail fake-or
[[ " ${qs[*]} " != *' pdftopdf '* ]] || fail fake-pdftopdf
pass localized-parser-avoids-fake-queues

reset_findings
job_log(){ cat <<'LOG';
E [19/Sep/2026:07:40:47 -0300] [Job 4557] PrintSpy: A URI do dispositivo é inválida.
W [19/Sep/2026:07:40:49 -0300] [Job 4557] Backend hp returned status 1 (failed)
LOG
}
append_job_findings 'HP-LaserJet-Professional-P1102w' 'HP-LaserJet-Professional-P1102w-4557'
printf '%s\n' "${FINDING_CODES[@]}" | grep -qx HP_BACKEND_FAILED || fail hp-backend-diagnosis
printf '%s\n' "${FINDING_CODES[@]}" | grep -qx PRINTSPY_URI_INVALID || fail printspy-diagnosis
pass job-evidence-classification

for pat in \
  'sudo iptables' 'sudo nft ' 'sudo ufw ' 'sudo firewall-cmd' \
  'sudo ip route' 'sudo route ' 'sudo nmcli' 'sudo dhclient' \
  'systemctl restart NetworkManager' 'systemctl restart networking'; do
  if grep -Fq "$pat" "$PORTABLE"; then
    fail "blocked command present: $pat"
  fi
done
pass no-network-admin-commands

echo 'ALL TESTS PASSED'
