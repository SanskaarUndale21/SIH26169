#!/usr/bin/env bash
# Starts the whole FSOC coarse-alignment tracker stack: the web dashboard/
# live-control server in the background, then the desktop GUI in the
# foreground. Closing the desktop GUI (or Ctrl+C) also stops the web
# server -- no orphaned background process left behind.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

PORT=8420
WEB_LOG="logs/web_dashboard.log"
mkdir -p logs

if command -v python >/dev/null 2>&1; then
    PYTHON=python
elif command -v python3 >/dev/null 2>&1; then
    PYTHON=python3
else
    echo "python not found on PATH -- install Python 3.10+ first." >&2
    exit 1
fi

already_running() {
    curl -s -o /dev/null -m 1 "http://127.0.0.1:${PORT}/"
}

WEB_PID=""
if already_running; then
    echo "Web console already running at http://127.0.0.1:${PORT}/ -- leaving it as is."
else
    echo "Starting web dashboard + live control server on port ${PORT}..."
    "$PYTHON" web/dashboard_server.py >"$WEB_LOG" 2>&1 &
    WEB_PID=$!

    for _ in $(seq 1 20); do
        if already_running; then
            break
        fi
        sleep 0.5
    done

    if already_running; then
        echo "Web console up: http://127.0.0.1:${PORT}/"
    else
        echo "Web dashboard did not come up in time -- check ${WEB_LOG}" >&2
    fi
fi

cleanup() {
    if [ -n "$WEB_PID" ] && kill -0 "$WEB_PID" 2>/dev/null; then
        echo "Stopping web dashboard server (pid $WEB_PID)..."
        kill "$WEB_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT INT TERM

echo "Launching desktop GUI..."
"$PYTHON" main.py

echo "Desktop GUI closed."
