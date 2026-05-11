#!/usr/bin/env bash
# Debounced wrapper rundt `bedrock signals-all --bot-only --output data/signals_bot.json`.
#
# Brukes som ExecStartPost på 26 bedrock-fetch-*-services. Når mange fetch-services
# fyrer parallelt (typisk på boot med Persistent=true etter helg, der 20+ missed
# timer-runs fyrer samtidig), unngår vi å spawn 25 parallelle `signals-all`-prosesser
# som hver bruker ~6% CPU. Total CPU-storm på boot: ~100% i flere minutter.
#
# Pattern: dirty-bit + non-blocking flock + while-loop.
#   1. Touch dirty-bit (signaliserer at det er ny data å reflektere).
#   2. Forsøk non-blocking flock. Hvis en annen invocation holder låsen, exit 0
#      (den holderen vil dekke oss — dirty-bit garanterer at den re-kjører).
#   3. Hvis lås acquired: while dirty exists, fjern dirty, sleep 5s (coalesce),
#      kjør signals-all. Repeter hvis dirty kom tilbake under kjøringen.
#
# Boot-storm-effekt: 26 fetch-ExecStartPost → 2 signals-all-runs (ikke 26).
# Normal drift: én fetcher fyrer → 1 signals-all etter 5s debounce.
set -euo pipefail

LOCK="/tmp/bedrock-signals-bot-regen.lock"
DIRTY="/tmp/bedrock-signals-bot-regen.dirty"
COALESCE_SECONDS=5

REPO="/home/pc/bedrock"
BEDROCK_BIN="$REPO/.venv/bin/bedrock"
OUTPUT="data/signals_bot.json"

touch "$DIRTY"

exec 9>"$LOCK"
if ! flock -n 9; then
    exit 0
fi

cd "$REPO"
while [[ -f "$DIRTY" ]]; do
    rm -f "$DIRTY"
    sleep "$COALESCE_SECONDS"
    "$BEDROCK_BIN" signals-all --bot-only --output "$OUTPUT"
done
