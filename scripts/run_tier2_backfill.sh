#!/usr/bin/env bash
# Detached Tier 2 backfill-runner.
#
# Kjører Tier 2 historisk backfill i bakgrunnen via nohup + disown
# slik at jobben overlever session-exit. Output skrives til
# data/_meta/tier2_backfill.log med tidsstempel.
#
# Bruk:
#   scripts/run_tier2_backfill.sh start [args]   # start backfill detached
#   scripts/run_tier2_backfill.sh status         # vis pid + siste log-linjer
#   scripts/run_tier2_backfill.sh stop           # stopp pågående backfill
#   scripts/run_tier2_backfill.sh tail           # følg log-en (Ctrl-C for å gå ut)
#
# Args (videreført til backfill_tier2_history.py):
#   --skip-cot-ice / --skip-euronext / --skip-conab / --skip-unica
#   --cot-ice-from N / --cot-ice-to N / --euronext-n N
#
# Eksempel — kun Euronext med 200 onsdager:
#   scripts/run_tier2_backfill.sh start --skip-cot-ice --skip-conab --skip-unica --euronext-n 200

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_FILE="$REPO_ROOT/data/_meta/tier2_backfill.log"
PID_FILE="$REPO_ROOT/data/_meta/tier2_backfill.pid"
SCRIPT="$REPO_ROOT/scripts/backfill_tier2_history.py"

cmd="${1:-status}"
shift || true

case "$cmd" in
  start)
    if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
      echo "Tier 2 backfill kjører allerede (PID $(cat "$PID_FILE"))"
      echo "Bruk 'tail' for å følge eller 'stop' for å avbryte."
      exit 1
    fi
    mkdir -p "$(dirname "$LOG_FILE")"
    cd "$REPO_ROOT"
    {
      echo "==============================="
      echo "Tier 2 backfill startet $(date -Iseconds)"
      echo "Args: $*"
      echo "==============================="
    } >> "$LOG_FILE"
    # nohup + disown gir true detached process som overlever shell-exit
    nohup env PYTHONUNBUFFERED=1 PYTHONPATH=src \
      "$REPO_ROOT/.venv/bin/python" "$SCRIPT" "$@" \
      >> "$LOG_FILE" 2>&1 &
    pid=$!
    disown $pid 2>/dev/null || true
    echo "$pid" > "$PID_FILE"
    echo "Tier 2 backfill startet detached (PID $pid)"
    echo "Log: $LOG_FILE"
    echo "Følg med: scripts/run_tier2_backfill.sh tail"
    ;;

  status)
    if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
      pid=$(cat "$PID_FILE")
      echo "✓ kjører (PID $pid)"
      echo "  uptime: $(ps -o etime= -p "$pid" | tr -d ' ')"
      echo "  log:    $LOG_FILE"
      echo ""
      echo "Siste 10 linjer:"
      tail -n 10 "$LOG_FILE" 2>/dev/null || echo "  (ingen log enda)"
    else
      echo "✗ ikke kjørende"
      if [[ -f "$LOG_FILE" ]]; then
        echo ""
        echo "Siste log-linjer fra forrige kjøring:"
        tail -n 10 "$LOG_FILE"
      fi
    fi
    ;;

  stop)
    if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
      pid=$(cat "$PID_FILE")
      kill "$pid"
      sleep 2
      if kill -0 "$pid" 2>/dev/null; then
        kill -9 "$pid"
      fi
      rm -f "$PID_FILE"
      echo "Tier 2 backfill stoppet (PID $pid)"
    else
      echo "Ingen kjørende backfill"
    fi
    ;;

  tail)
    if [[ ! -f "$LOG_FILE" ]]; then
      echo "Ingen log-fil enda: $LOG_FILE"
      exit 1
    fi
    tail -f "$LOG_FILE"
    ;;

  *)
    echo "Bruk: $0 {start|status|stop|tail} [args]"
    exit 1
    ;;
esac
