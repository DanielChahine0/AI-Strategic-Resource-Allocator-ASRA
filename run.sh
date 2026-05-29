#!/usr/bin/env bash
#
# run.sh — launch the whole ASRA model-comparison stack with one command.
#
#   ./run.sh
#
# Starts both FastAPI engines in the background, waits until each answers,
# then runs the Vite dev server in the foreground. Quitting (Ctrl-C) or any
# backend dying tears the whole stack down — no orphaned uvicorn processes.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

AI_PORT=8000
RAG_PORT=8001
LOG_DIR="$ROOT/.run-logs"
mkdir -p "$LOG_DIR"

PIDS=()

cleanup() {
  echo ""
  echo "→ shutting down backends…"
  for pid in "${PIDS[@]:-}"; do
    if [[ -n "${pid:-}" ]] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
  done
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# Start one backend. $1 = label, $2 = directory, $3 = port.
start_backend() {
  local label="$1" dir="$2" port="$3"
  local py="$ROOT/$dir/.venv/bin/python"
  if [[ ! -x "$py" ]]; then
    echo "✗ $label: no venv python at $py" >&2
    exit 1
  fi
  echo "→ starting $label on :$port (logs → $LOG_DIR/$label.log)"
  # Bind to localhost only — these engines have no auth by default and handle
  # applicant PII; do not expose them on all interfaces.
  ( cd "$dir" && exec "$py" -m uvicorn asra_matcher.api:app --host 127.0.0.1 --port "$port" ) \
    >"$LOG_DIR/$label.log" 2>&1 &
  PIDS+=("$!")
}

# Poll a port's /eval/datasets until it answers (or time out).
wait_for() {
  local label="$1" port="$2" tries=0
  printf "→ waiting for %s" "$label"
  until curl -sf "http://localhost:$port/eval/datasets" >/dev/null 2>&1; do
    tries=$((tries + 1))
    if (( tries > 60 )); then
      echo " — timed out. Last log lines:" >&2
      tail -n 20 "$LOG_DIR/$label.log" >&2 || true
      exit 1
    fi
    printf "."
    sleep 1
  done
  echo " ✓"
}

start_backend "ai-model"  "AI Model"  "$AI_PORT"
start_backend "rag-model" "RAG Model" "$RAG_PORT"

wait_for "ai-model"  "$AI_PORT"
wait_for "rag-model" "$RAG_PORT"

echo "→ both engines up. Starting frontend…"
echo "  Open http://localhost:5173/compare"
echo ""

cd "$ROOT/Frontend"
[[ -d node_modules ]] || npm install
npm run dev
