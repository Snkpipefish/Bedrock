#!/usr/bin/env bash
# Keep-alive for GitHub Codespace — sender SSH-heartbeat hvert 20. min
# for å unngå at codespace idle-timer (default 30 min) stopper harvest.
#
# Brukes som cron-job på laptop:
#   crontab -e
#   */20 * * * * /home/pc/bedrock/scripts/codespace_keepalive.sh

set -uo pipefail

CSNAME="stunning-sniffle-pv459prj4wgh664p"
LOG="/home/pc/bedrock/data/_meta/codespace_keepalive.log"
mkdir -p "$(dirname "$LOG")"

# Ping codespace med en lett kommando som genererer aktivitet.
# Sjekker også om harvest fortsatt kjører — logger hvis ikke.
TIMESTAMP="$(date -Iseconds)"
RESULT="$(
    /home/pc/.local/bin/gh codespace ssh -c "$CSNAME" -- \
        'pgrep -af run_parallel_harvest > /dev/null && echo HARVEST_OK || echo HARVEST_DONE' 2>&1
)"

echo "$TIMESTAMP $RESULT" >> "$LOG"

# Hvis HARVEST_DONE: send notifikasjon (notify-send finnes på laptop)
if [[ "$RESULT" == *"HARVEST_DONE"* ]]; then
    /usr/bin/notify-send "Bedrock harvest" "Codespace harvest fullført — sjekk DB og hent resultater" 2>&1 || true
fi
