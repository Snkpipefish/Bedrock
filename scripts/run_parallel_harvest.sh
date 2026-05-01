#!/usr/bin/env bash
# Parallel harvest-wrapper — 4-way parallelism med per-instrument start-dato.
#
# Splitter 22 instrumenter i 4 grupper som kjører sekvensielt innen gruppen
# men parallelt mellom grupper. SQLite WAL-mode håndterer 4 samtidige writers
# (commit-tid <1ms vs 5-10s per ref_date compute → minimal lock-kontention).
#
# Per-instrument start-dato basert på data-coverage-analyse session 136:
# - Copper: 2022-02-08 (CFTC-cutoff — pre-2022 har ingen positioning-data)
# - BTC: 2018-04-10 (CME futures-start — pre-2018 har ingen COT)
# - Andre: 2010-03 (60d warmup etter prices_min)
#
# Kjør detached:
#   nohup nice -n 10 ionice -c 3 ./scripts/run_parallel_harvest.sh \
#     > data/_meta/harvest_parallel.log 2>&1 &
#
# Sjekk progress:
#   sqlite3 data/bedrock.db "SELECT instrument, COUNT(*) FROM driver_observations GROUP BY instrument"
#   tail -f data/_meta/harvest_g1.log  (eller g2/g3/g4)
#
# Stopp:
#   pkill -f run_parallel_harvest.sh ; pkill -f harvest_driver_observations

set -uo pipefail

cd "$(dirname "$0")/.." || exit 1

STEP_DAYS="${BEDROCK_HARVEST_STEP_DAYS:-14}"

# Optional --only-driver-flag (audit-runde 5 sub-fase 12.6 fix-spec Steg 4):
# brukes for målrettet backfill av en enkelt driver etter bug-fix.
# Eksempel: BEDROCK_HARVEST_ONLY_DRIVER=event_distance ./scripts/run_parallel_harvest.sh
ONLY_DRIVER="${BEDROCK_HARVEST_ONLY_DRIVER:-}"
ONLY_DRIVER_ARG=""
if [[ -n "$ONLY_DRIVER" ]]; then
    ONLY_DRIVER_ARG="--only-driver $ONLY_DRIVER"
    echo "[only-driver] målrettet backfill: $ONLY_DRIVER"
fi

# Auto-resume av paused fetch-timere ved exit (samme som single-tråd-wrapper).
if [[ "${BEDROCK_HARVEST_RESUME_TIMERS:-1}" == "1" ]]; then
    _resume_timers() {
        echo "=== trap EXIT: re-aktiverer pausede fetch-timere ==="
        for TIMER in bedrock-fetch-prices bedrock-fetch-fundamentals \
                     bedrock-fetch-weather bedrock-fetch-seismic \
                     bedrock-fetch-comex bedrock-fetch-eia_inventories \
                     bedrock-fetch-cot_disaggregated bedrock-fetch-cot_legacy \
                     bedrock-fetch-cot_ice bedrock-fetch-cot_euronext; do
            systemctl --user start "${TIMER}.timer" 2>&1 | sed "s/^/  /"
        done
    }
    trap _resume_timers EXIT
fi

# Per-instrument start-dato (data-coverage-trimming).
declare -A START_DATES=(
    [Brent]="2010-03-05"
    [CrudeOil]="2010-03-05"
    [NaturalGas]="2010-03-05"
    [Gold]="2010-03-05"
    [Silver]="2010-03-05"
    [Copper]="2022-02-08"   # CFTC-cutoff
    [Platinum]="2010-03-05"
    [Sugar]="2010-03-05"
    [Corn]="2010-03-05"
    [Soybean]="2010-03-05"
    [Coffee]="2010-03-05"
    [Wheat]="2010-03-05"
    [Cocoa]="2010-03-05"
    [Cotton]="2010-03-05"
    [SP500]="2010-03-05"
    [Nasdaq]="2010-03-05"
    [EURUSD]="2010-03-02"
    [USDJPY]="2010-03-02"
    [GBPUSD]="2010-03-02"
    [AUDUSD]="2010-03-02"
    [BTC]="2018-04-10"      # CME BTC futures-start
    [ETH]="2018-01-08"
)

# 4 grupper for parallell-kjøring. Splittet for å balansere wall-time.
# Brent + CrudeOil er allerede partial så de er i G1 først (kort restbeløp
# kompletteres tidlig, så fortsetter med tunge instrumenter).
GROUP1=(CrudeOil NaturalGas Gold Silver Copper Platinum)
GROUP2=(Sugar Corn Soybean Coffee Wheat Cocoa)
GROUP3=(Cotton SP500 Nasdaq EURUSD USDJPY)
GROUP4=(GBPUSD AUDUSD BTC ETH)

# Funksjon for å kjøre én gruppe sekvensielt
run_group() {
    local LABEL="$1"; shift
    echo "=== Gruppe ${LABEL} start: $(date -Iseconds) ==="
    echo "Instrumenter: $*"
    for INST in "$@"; do
        local START_DATE="${START_DATES[$INST]:-}"
        local START_ARG=""
        if [[ -n "$START_DATE" ]]; then
            START_ARG="--start-date $START_DATE"
        fi
        echo ""
        echo "--- [${LABEL}] ${INST} (start_date=${START_DATE:-full}) ($(date -Iseconds)) ---"
        PYTHONUNBUFFERED=1 PYTHONPATH=src .venv/bin/python \
            scripts/harvest_driver_observations.py \
            --instrument "${INST}" \
            --step-days "${STEP_DAYS}" \
            $START_ARG \
            $ONLY_DRIVER_ARG
        local RC=$?
        if [[ $RC -ne 0 ]]; then
            echo "!!! [${LABEL}] ${INST} feilet med exit-code ${RC}, fortsetter med neste"
        fi
    done
    echo ""
    echo "=== Gruppe ${LABEL} ferdig: $(date -Iseconds) ==="
}

START="$(date -Iseconds)"
echo "=== run_parallel_harvest.sh start: ${START} ==="
echo "Step days: ${STEP_DAYS}"
echo "G1 (${#GROUP1[@]}): ${GROUP1[*]}"
echo "G2 (${#GROUP2[@]}): ${GROUP2[*]}"
echo "G3 (${#GROUP3[@]}): ${GROUP3[*]}"
echo "G4 (${#GROUP4[@]}): ${GROUP4[*]}"
echo

mkdir -p data/_meta

# Launch 4 grupper parallelt med separate log-filer
run_group "G1" "${GROUP1[@]}" > data/_meta/harvest_g1.log 2>&1 &
PID1=$!
run_group "G2" "${GROUP2[@]}" > data/_meta/harvest_g2.log 2>&1 &
PID2=$!
run_group "G3" "${GROUP3[@]}" > data/_meta/harvest_g3.log 2>&1 &
PID3=$!
run_group "G4" "${GROUP4[@]}" > data/_meta/harvest_g4.log 2>&1 &
PID4=$!

echo "G1 PID=${PID1}, G2 PID=${PID2}, G3 PID=${PID3}, G4 PID=${PID4}"
echo "Følg progress: tail -f data/_meta/harvest_g{1..4}.log"

# Vent på alle 4
wait $PID1 $PID2 $PID3 $PID4

END="$(date -Iseconds)"
echo
echo "=== run_parallel_harvest.sh ferdig: ${END} ==="
echo "Total wall-time: start=${START} end=${END}"
echo
echo "DB-statistikk:"
sqlite3 data/bedrock.db "SELECT instrument, COUNT(*) AS rows, COUNT(DISTINCT ref_date) AS dates FROM driver_observations GROUP BY instrument ORDER BY instrument"
