#!/bin/bash
# Wrapper for ~/.config/autostart/bedrock-widget.desktop.
#
# Venter på at signal_server kommer opp på port 5100, deretter starter
# Microsoft Edge i --app-modus med widget-siden. Kjøres ved login.
#
# Etter session 2026-05-26.

set -u

WIDGET_URL="http://localhost:5100/widget"
EDGE_BIN="/usr/bin/microsoft-edge"
PROFILE_DIR="$HOME/.config/bedrock-widget-edge"
LOG_FILE="$HOME/.cache/bedrock-widget.log"

mkdir -p "$(dirname "$LOG_FILE")"

{
  echo "[$(date -Iseconds)] bedrock-widget-launch start"

  # Vent inntil signal-server svarer (boot tar 5-20s typisk).
  for i in $(seq 1 60); do
    if curl -sf "$WIDGET_URL" >/dev/null 2>&1; then
      echo "[$(date -Iseconds)] signal-server oppe etter ${i}s"
      break
    fi
    sleep 2
  done

  if ! curl -sf "$WIDGET_URL" >/dev/null 2>&1; then
    echo "[$(date -Iseconds)] signal-server ikke tilgjengelig etter 120s — avbryter"
    exit 1
  fi

  # Start Edge i --app-modus (chromeless window). Egen profil-dir så
  # widget-sesjonen ikke kolliderer med vanlig Edge-bruk.
  exec "$EDGE_BIN" \
    --app="$WIDGET_URL" \
    --window-size=540,420 \
    --window-position=20,20 \
    --user-data-dir="$PROFILE_DIR" \
    --no-first-run \
    --no-default-browser-check
} >>"$LOG_FILE" 2>&1
