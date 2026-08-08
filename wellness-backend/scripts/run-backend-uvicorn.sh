#!/bin/sh
set -e

# Script to create a venv, install requirements, and start uvicorn in background.
# Run from the repo or directly: ./backend/scripts/run-backend-uvicorn.sh

BASE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$BASE_DIR"

VENV_DIR=".venv"
LOG="/tmp/dws-uvicorn.log"
PIDFILE="/tmp/dws-uvicorn.pid"

if [ ! -x "$(command -v python3)" ]; then
  echo "python3 not found on PATH. Install Python 3.8+"
  exit 2
fi

if [ ! -d "$VENV_DIR" ]; then
  echo "Creating virtualenv in $VENV_DIR"
  python3 -m venv "$VENV_DIR"
fi

echo "Installing dependencies into $VENV_DIR"
# Ensure venv python has pip; use ensurepip if necessary
if [ ! -x "$VENV_DIR/bin/pip" ]; then
  echo "Bootstrapping pip into the virtualenv"
  "$VENV_DIR/bin/python" -m ensurepip --upgrade || python3 -m ensurepip --upgrade
fi

"$VENV_DIR/bin/python" -m pip install --upgrade pip setuptools wheel
"$VENV_DIR/bin/python" -m pip install -r requirements.txt

if [ -f "$PIDFILE" ]; then
  PID=$(cat "$PIDFILE")
  if kill -0 "$PID" 2>/dev/null; then
    echo "uvicorn already running with pid $PID"
    exit 0
  else
    echo "Removing stale pidfile"
    rm -f "$PIDFILE"
  fi
fi

echo "Starting uvicorn... (logs -> $LOG)"
nohup "$VENV_DIR/bin/python" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 >"$LOG" 2>&1 &
echo $! >"$PIDFILE"

echo "Started uvicorn (pid $(cat $PIDFILE)). Tail logs with: tail -f $LOG"
