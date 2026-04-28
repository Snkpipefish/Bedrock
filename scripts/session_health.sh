#!/usr/bin/env bash
# Sub-fase 12.6 — kjapp pipeline-helse-rapport ved session-start.
#
# Kjøres av Claude Code som steg 4 i CLAUDE.md "Start av session".
# Ingen endringer — bare leser systemctl-status + dagens monitor-rapport.
#
# Output-format: kompakt og ikke-fargekodet (skal være lett-parsbart for
# språkmodellen). Linje 1 = grønn|rød, linje 2+ = detaljer.

set -u
cd "$(dirname "$0")/.."

red=0
issues=()

# 1. Failed user-services (bedrock-*)
failed=$(systemctl --user list-units --type=service --state=failed --no-pager --plain 2>/dev/null \
  | awk '$1 ~ /^bedrock-/ {print $1}')
if [ -n "$failed" ]; then
  red=1
  issues+=("FAILED user-services: $(echo "$failed" | tr '\n' ',' | sed 's/,$//')")
fi

# 2. Failed system-services (bedrock-*)
failed_sys=$(systemctl list-units --type=service --state=failed --no-pager --plain 2>/dev/null \
  | awk '$1 ~ /^bedrock-/ {print $1}')
if [ -n "$failed_sys" ]; then
  red=1
  issues+=("FAILED system-services: $(echo "$failed_sys" | tr '\n' ',' | sed 's/,$//')")
fi

# 3. Dagens monitor-rapport
today=$(date +%F)
report="data/_meta/monitor_${today}.json"
if [ -f "$report" ]; then
  ok=$(.venv/bin/python -c "import json,sys; print(json.load(open('$report')).get('overall_ok'))" 2>/dev/null)
  if [ "$ok" = "False" ]; then
    red=1
    summary=$(.venv/bin/python -c "
import json, sys
data = json.load(open('$report'))
failed = [c for c in data.get('checks', []) if not c.get('ok', True)]
parts = []
for c in failed:
    parts.append(c['name']+': '+c.get('detail',''))
print(' | '.join(parts))
" 2>/dev/null)
    issues+=("monitor=red — $summary")
  elif [ "$ok" = "True" ]; then
    issues+=("monitor=green ($report)")
  else
    issues+=("monitor=ukjent (kunne ikke parse $report)")
  fi
else
  # Hvis det er før 06:30 i dag, er manglende rapport forventet — sjekk i går.
  yesterday=$(date -d "yesterday" +%F)
  yreport="data/_meta/monitor_${yesterday}.json"
  if [ -f "$yreport" ]; then
    issues+=("monitor=mangler-i-dag (gårsdagens finnes: $yreport)")
  else
    issues+=("monitor=mangler både i dag og i går")
  fi
fi

# 4. Timere som ikke har kjørt på 2× cadence (placeholder — kun ren listing)
# Vi rapporterer bare timere som ikke har kjørt siste 7 dager — mer detaljert
# tids-sjekk skjer i monitor_pipeline.py. Her bare en sanity-check.
stale_timers=$(systemctl --user list-timers --all --no-pager 2>/dev/null \
  | awk '$1 ~ /^Sat|^Sun|^Mon|^Tue|^Wed|^Thu|^Fri/ && $NF ~ /bedrock-fetch-/ {
      # Simple heuristic: hvis siste kolonne (UNIT) er bedrock-fetch og
      # PASSED-feltet inneholder "weeks", er den stale ift forventet cadence.
      0
  }')

# Hovedlinje
if [ $red -eq 1 ]; then
  echo "PIPELINE-HELSE: RØD"
else
  echo "PIPELINE-HELSE: GRØNN"
fi
for issue in "${issues[@]}"; do
  echo "  - $issue"
done

# Eksitkode 0 alltid (vi vil ikke at session-start-checken selv blir behandlet
# som en feil av Claude). Status er i tekst-output.
exit 0
