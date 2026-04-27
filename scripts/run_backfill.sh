#!/usr/bin/env bash
# Generisk detached backfill-runner. Kjører ett av flere backfill-
# jobs i bakgrunnen via nohup + disown så de overlever Claude Code-
# session-exit.
#
# Bruk:
#   scripts/run_backfill.sh <job> [start|status|stop|tail] [args]
#
# Tilgjengelige jobs:
#   nass-crop-progress    NASS Crop Progress historikk (2010-2021)
#   usgs-seismic          USGS earthquake historikk (2010+)
#   euronext              Euronext COT historikk (optimalisert)
#   cftc-name-drift       CFTC kontrakt-navn-drift (Brent, Copper)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
META_DIR="$REPO_ROOT/data/_meta"

job="${1:-help}"
cmd="${2:-status}"
shift 2 2>/dev/null || true

case "$job" in
  nass-crop-progress)
    LABEL="nass_crop_progress"
    COMMAND=(
      "$REPO_ROOT/.venv/bin/bedrock" backfill crop-progress
      --year 2010 --year 2011 --year 2012 --year 2013
      --year 2014 --year 2015 --year 2016 --year 2017
      --year 2018 --year 2019 --year 2020 --year 2021
    )
    ;;
  usgs-seismic)
    LABEL="usgs_seismic"
    COMMAND=(
      env PYTHONUNBUFFERED=1 PYTHONPATH=src
      "$REPO_ROOT/.venv/bin/python"
      "$REPO_ROOT/scripts/backfill_usgs_seismic_history.py"
    )
    ;;
  euronext)
    LABEL="euronext"
    COMMAND=(
      env PYTHONUNBUFFERED=1 PYTHONPATH=src
      "$REPO_ROOT/.venv/bin/python"
      "$REPO_ROOT/scripts/backfill_euronext_optimized.py"
    )
    ;;
  cftc-name-drift)
    LABEL="cftc_name_drift"
    COMMAND=(
      env PYTHONUNBUFFERED=1 PYTHONPATH=src
      "$REPO_ROOT/.venv/bin/python"
      "$REPO_ROOT/scripts/backfill_cftc_name_drift.py"
    )
    ;;
  harvest-drivers)
    LABEL="harvest_drivers"
    COMMAND=(
      bash "$REPO_ROOT/scripts/run_full_history_harvest.sh"
    )
    ;;
  analyze)
    LABEL="analyze"
    # Sekvensiell: driver_performance først, så cross_correlations.
    # bash -c brukes for å chain'e dem i samme detached process.
    COMMAND=(
      bash -c "cd '$REPO_ROOT' && \
        echo '=== analyze_driver_performance.py ===' && \
        PYTHONUNBUFFERED=1 PYTHONPATH=src .venv/bin/python scripts/analyze_driver_performance.py && \
        echo '=== analyze_cross_correlations.py ===' && \
        PYTHONUNBUFFERED=1 PYTHONPATH=src .venv/bin/python scripts/analyze_cross_correlations.py"
    )
    ;;
  help|*)
    echo "Bruk: $0 <job> {start|status|stop|tail}"
    echo ""
    echo "Jobs:"
    echo "  nass-crop-progress    NASS Crop Progress historikk (2010-2021)"
    echo "  usgs-seismic          USGS earthquake historikk (2010+)"
    echo "  euronext              Euronext COT optimalisert backfill"
    echo "  cftc-name-drift       CFTC kontrakt-navn-drift (Brent, Copper)"
    echo "  harvest-drivers       Full historisk driver-harvest (~24-35 timer)"
    echo "  analyze               Driver-performance + kryss-korrelasjon (etter harvest)"
    exit 0
    ;;
esac

LOG_FILE="$META_DIR/backfill_${LABEL}.log"
PID_FILE="$META_DIR/backfill_${LABEL}.pid"

case "$cmd" in
  start)
    if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
      echo "$LABEL kjører allerede (PID $(cat "$PID_FILE"))"
      exit 1
    fi
    mkdir -p "$META_DIR"
    cd "$REPO_ROOT"
    {
      echo "==============================="
      echo "$LABEL backfill startet $(date -Iseconds)"
      echo "Args: $*"
      echo "==============================="
    } >> "$LOG_FILE"
    nohup "${COMMAND[@]}" "$@" >> "$LOG_FILE" 2>&1 &
    pid=$!
    disown $pid 2>/dev/null || true
    echo "$pid" > "$PID_FILE"
    echo "$LABEL startet detached (PID $pid)"
    echo "Log: $LOG_FILE"
    ;;

  status)
    if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
      pid=$(cat "$PID_FILE")
      echo "✓ $LABEL kjører (PID $pid)"
      echo "  uptime: $(ps -o etime= -p "$pid" | tr -d ' ')"
      echo ""
      tail -n 10 "$LOG_FILE" 2>/dev/null || echo "(ingen log)"
    else
      echo "✗ $LABEL ikke kjørende"
      [[ -f "$LOG_FILE" ]] && { echo ""; tail -n 10 "$LOG_FILE"; }
    fi
    ;;

  stop)
    if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
      pid=$(cat "$PID_FILE")
      kill "$pid"
      sleep 2
      kill -0 "$pid" 2>/dev/null && kill -9 "$pid"
      rm -f "$PID_FILE"
      echo "$LABEL stoppet"
    else
      echo "Ingen kjørende $LABEL"
    fi
    ;;

  tail)
    [[ -f "$LOG_FILE" ]] || { echo "Ingen log: $LOG_FILE"; exit 1; }
    tail -f "$LOG_FILE"
    ;;
esac
