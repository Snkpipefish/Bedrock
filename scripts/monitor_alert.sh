#!/usr/bin/env bash
# Sub-fase 12.6 — desktop-varsel hvis dagens pipeline-monitor er rød.
#
# Leser data/_meta/monitor_<dato>.json (skrevet av bedrock-monitor.service
# 06:30) og kaller notify-send hvis overall_ok=false eller fila mangler.
# Triggres av bedrock-monitor-alert.timer (user) ~10 min etter monitor.
#
# Exit-koder:
#   0  alt OK eller varsel sendt (vi vil ikke at user-timeren skal trigge
#      OnFailure som spam — vi sender selv).
#   ingen non-zero exit; alt logges via stdout/stderr → journal.

set -u
cd "$(dirname "$0")/.."

today=$(date +%F)
report="data/_meta/monitor_${today}.json"

notify() {
  /usr/bin/notify-send --urgency=critical --app-name=bedrock --icon=dialog-error \
    "Bedrock monitor: $1" "$2"
}

if [ ! -f "$report" ]; then
  echo "[monitor_alert] mangler $report — varsler"
  notify "rapport mangler" "Filen $report ble ikke skrevet i dag. Kjørte bedrock-monitor.service?"
  exit 0
fi

# Bruker python for robust JSON-parse, ikke jq (kan mangle).
.venv/bin/python - "$report" <<'PY'
import json
import sys
from pathlib import Path

report_path = Path(sys.argv[1])
data = json.loads(report_path.read_text())
if data.get("overall_ok") is True:
    print(f"[monitor_alert] {report_path.name}: overall_ok=true — ingen varsel")
    sys.exit(0)

# Bygg kort sammendrag av sjekker som feiler.
failed = [c for c in data.get("checks", []) if not c.get("ok", True)]
lines = []
for c in failed:
    detail = c.get("detail", "")
    # Trim hvis altfor lang.
    if len(detail) > 200:
        detail = detail[:197] + "..."
    lines.append(f"• {c['name']}: {detail}")
summary = "\n".join(lines) if lines else "overall_ok=false (ingen detaljer)"
print(f"[monitor_alert] varsler om: {summary}")

# Skriv summary til en temp-fil så bash kan plukke den opp.
out = Path("/tmp/bedrock_monitor_alert_msg.txt")
out.write_text(summary)
sys.exit(2)  # signal til bash at vi skal varsle
PY

py_rc=$?
if [ $py_rc -eq 2 ]; then
  msg=$(cat /tmp/bedrock_monitor_alert_msg.txt 2>/dev/null || echo "(ingen detaljer)")
  rm -f /tmp/bedrock_monitor_alert_msg.txt
  notify "pipeline-helse FEILET" "$msg"
fi

exit 0
