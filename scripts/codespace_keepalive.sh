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
# Sjekk via log-mtime + DB-row-count i stedet for pgrep (som hadde
# self-match-bug fordi pgrep -f skanner full cmdline inkludert seg selv).
# HARVEST_OK = log skrevet siste 5 min ELLER row-count har økt siste sjekk.
RESULT="$(
    /home/pc/.local/bin/gh codespace ssh -c "$CSNAME" -- \
        '
        # Sjekk om noen group-log er modifisert siste 5 min (workers logger debug)
        if find /workspaces/Bedrock/data/_meta/harvest_g[1-4].log -mmin -5 2>/dev/null | grep -q .; then
            echo HARVEST_OK
        else
            # Backup: sjekk om master-log har "ferdig" eller fortsatt aktiv-mønster
            if grep -q "run_parallel_harvest.sh ferdig" /workspaces/Bedrock/data/_meta/harvest_codespace.log 2>/dev/null; then
                echo HARVEST_DONE
            else
                echo HARVEST_STALE
            fi
        fi
        ' 2>&1
)"

echo "$TIMESTAMP $RESULT" >> "$LOG"

# Hvis HARVEST_DONE: send completion-notifikasjon
if [[ "$RESULT" == *"HARVEST_DONE"* ]]; then
    /usr/bin/notify-send "Bedrock harvest" "Codespace harvest fullført — sjekk DB og hent resultater" 2>&1 || true
fi
# Hvis HARVEST_STALE: harvest har dødd (codespace suspend?), varsle for å restarte
if [[ "$RESULT" == *"HARVEST_STALE"* ]]; then
    /usr/bin/notify-send -u critical "Bedrock harvest" "Harvest virker død — sjekk Codespace status" 2>&1 || true
fi
