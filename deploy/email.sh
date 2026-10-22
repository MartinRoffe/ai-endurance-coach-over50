#!/bin/bash
# Daily readiness email. Same retry rules as the macOS launchd wrapper.
# Exit 0: sent. Exit 2: watch has not synced — retry every 30 minutes.
# Any other status stops immediately (no retry).
# Deadline is three hours after start (same as the Mac wrapper).
# The attempt that reaches the deadline sends with whatever has synced.
set -u
DATA="${ENDURANCE_COACH_HOME:-$HOME/.ai_endurance_coach_over50}"
export DOTENV_PATH="${DOTENV_PATH:-$DATA/.env}"
BIN="${ENDURANCE_COACH_BIN:-$DATA/venv/bin/endurance-coach}"
if [ ! -x "$BIN" ]; then
    BIN="$(command -v endurance-coach || true)"
fi
if [ -z "${BIN}" ]; then
    echo "endurance-coach not found" >&2
    exit 1
fi
PY="${BIN%/*}/python"
if [ ! -x "$PY" ]; then
    PY="$(command -v python3)"
fi
DEADLINE="$("$PY" -c "from datetime import datetime, timedelta; print(int((datetime.now()+timedelta(hours=3)).timestamp()))")" || exit 1
while true; do
    "$BIN" --withings-sync --email --fetch
    CODE=$?
    if [ "$CODE" -eq 0 ]; then
        exit 0
    fi
    if [ "$CODE" -ne 2 ]; then
        exit "$CODE"
    fi
    NOW=$(date +%s)
    if [ "$NOW" -ge "$DEADLINE" ]; then
        echo "Watch never synced by the deadline — sending with the data on hand"
        "$BIN" --withings-sync --email --fetch --email-incomplete
        exit $?
    fi
    echo "Watch not synced yet, retrying in 30 min…"
    sleep 1800
done
