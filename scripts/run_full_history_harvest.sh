#!/usr/bin/env bash
# Wrapper for full historisk driver-harvest.
#
# Looper alle 22 instrumenter sekvensielt og kaller
# harvest_driver_observations.py per instrument. Resumable: stopp med
# pkill, restart hopper over allerede-skrevne (instrument, ref_date)-
# kombinasjoner.
#
# Kjør detached:
#   nohup ./scripts/run_full_history_harvest.sh > /tmp/harvest.log 2>&1 &
#   tail -f /tmp/harvest.log
#
# Sjekk progress:
#   sqlite3 data/bedrock.db "SELECT instrument, COUNT(*) AS rows, COUNT(DISTINCT ref_date) AS dates FROM driver_observations GROUP BY instrument ORDER BY instrument"
#
# Stopp:
#   pkill -f harvest_driver_observations.py

set -uo pipefail

cd "$(dirname "$0")/.." || exit 1
REPO_ROOT="$(pwd)"

STEP_DAYS="${BEDROCK_HARVEST_STEP_DAYS:-14}"

# Auto-resume av paused fetch-timere ved exit (session 136 mitigation
# mot OOM/timer-kollisjon — operator pauser timere før harvest-start,
# trap sørger for at de re-aktiveres når harvest avslutter, uavhengig
# av suksess/feil/SIGTERM). BEDROCK_HARVEST_RESUME_TIMERS=0 skrur av
# auto-resume hvis ønsket (f.eks. for testing).
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

# Alle 22 instrumenter. Whitelist-distinksjonen er IKKE tatt med —
# fordi (a) listen endrer seg over tid og (b) vi vil teste alt på
# tvers. Instrumenter uten analog_outcomes (BTC/ETH/NaturalGas/Copper/
# Platinum per session 116) får syntetisert forward_return fra prices.
# Rekkefølge: mest-touchede av Phase A-C først så vi ser tidlige
# resultater på de mest relevante.
INSTRUMENTS=(
    Brent       # cot_ice + eia
    CrudeOil    # eia
    NaturalGas  # cot_ice + eia (ingen analog_outcomes — synthesize)
    Gold        # comex + mining
    Silver      # comex + mining
    Copper      # comex + mining (ingen analog_outcomes — synthesize)
    Platinum    # mining (ingen analog_outcomes — synthesize)
    Sugar       # unica
    Corn        # cot_euronext + conab + shipping
    Soybean     # conab + shipping
    Coffee      # conab
    Wheat       # cot_euronext + shipping
    Cocoa       # shipping
    Cotton      # shipping
    SP500
    Nasdaq
    EURUSD
    USDJPY
    GBPUSD
    AUDUSD
    BTC         # ingen analog_outcomes — synthesize
    ETH         # ingen analog_outcomes — synthesize
)

START="$(date -Iseconds)"
echo "=== run_full_history_harvest.sh start: ${START} ==="
echo "Step days: ${STEP_DAYS}"
echo "Instruments: ${#INSTRUMENTS[@]}"
echo

for INST in "${INSTRUMENTS[@]}"; do
    echo "--- Starter ${INST} ($(date -Iseconds)) ---"
    PYTHONUNBUFFERED=1 PYTHONPATH=src .venv/bin/python \
        scripts/harvest_driver_observations.py \
        --instrument "${INST}" \
        --step-days "${STEP_DAYS}"
    RC=$?
    if [[ $RC -ne 0 ]]; then
        echo "!!! ${INST} feilet med exit-code ${RC}, fortsetter med neste"
    fi
done

END="$(date -Iseconds)"
echo
echo "=== run_full_history_harvest.sh ferdig: ${END} ==="
echo "Total wall-time: start=${START} end=${END}"
echo
echo "DB-statistikk:"
sqlite3 data/bedrock.db "SELECT instrument, COUNT(*) AS rows, COUNT(DISTINCT ref_date) AS dates FROM driver_observations GROUP BY instrument ORDER BY instrument"
