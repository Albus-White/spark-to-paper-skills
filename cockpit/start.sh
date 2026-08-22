#!/usr/bin/env bash
# Spark Cockpit - start the local app.
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

PY=""
for c in python3 python; do
    if command -v "$c" >/dev/null 2>&1; then PY="$c"; break; fi
done
if [ -z "$PY" ]; then
    echo "Python 3.10+ is required but was not found on your PATH. Install it and run this file again." >&2
    exit 1
fi

LOG="${TMPDIR:-/tmp}/spark-cockpit.log"

# nohup + & : the server survives this terminal, so closing it never kills a run.
cd "$ROOT"
nohup "$PY" -m cockpit "$@" >"$LOG" 2>&1 &
PID=$!

echo "Spark Cockpit is starting - your browser opens in a moment."
echo "If it does not, go to  http://127.0.0.1:8765"
echo
echo "It keeps running after you close this terminal."
echo "  log:   $LOG"
echo "  stop:  kill $PID"
