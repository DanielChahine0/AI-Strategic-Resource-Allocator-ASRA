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

# Pick a Python 3.11+ interpreter for creating venvs.
PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "✗ no '$PYTHON_BIN' on PATH — install Python 3.11+ (or set PYTHON_BIN)" >&2
  exit 1
fi

# Bootstrap one backend's environment if it isn't ready yet. Idempotent:
# each step is skipped when its output already exists, so re-runs are cheap.
# $1 = label, $2 = directory.
bootstrap_backend() {
  local label="$1" dir="$2"
  local py="$ROOT/$dir/.venv/bin/python"

  # 1. Create the virtualenv if it's missing.
  if [[ ! -x "$py" ]]; then
    echo "→ $label: creating virtualenv ($PYTHON_BIN)"
    "$PYTHON_BIN" -m venv "$ROOT/$dir/.venv"
  fi

  # 2. Install the package (editable, with dev extras) if it isn't importable.
  if ! ( cd "$ROOT/$dir" && "$py" -c "import asra_matcher" ) >/dev/null 2>&1; then
    echo "→ $label: installing dependencies (pip install -e '.[dev]')"
    "$py" -m pip install --quiet --upgrade pip
    ( cd "$ROOT/$dir" && "$py" -m pip install -e ".[dev]" )
  fi

  # 3. Seed .env from the example so the engine has its config file.
  if [[ ! -f "$ROOT/$dir/.env" && -f "$ROOT/$dir/.env.example" ]]; then
    echo "→ $label: creating .env from .env.example (add GEMINI_API_KEY to enable LLM)"
    cp "$ROOT/$dir/.env.example" "$ROOT/$dir/.env"
  fi
}

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
  # Expose the PID so wait_for can tell "still booting" from "already dead".
  BACKEND_PID=$!
  PIDS+=("$BACKEND_PID")
}

# Refuse to start if a port is already taken, and name the squatter — so a
# stale server (even one from another project) produces a clear message up
# front instead of a backend that dies on bind and a silent 60-second wait.
preflight_port() {
  local label="$1" port="$2" pids
  command -v lsof >/dev/null 2>&1 || return 0
  pids="$(lsof -nP -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | tr '\n' ' ' || true)"
  pids="${pids% }"
  if [[ -n "$pids" ]]; then
    echo "✗ $label: port $port is already in use by PID(s): $pids" >&2
    echo "  What's holding it:" >&2
    ps -o pid,etime,command -p $pids 2>/dev/null | sed 's/^/    /' >&2 || true
    echo "  Free it:  kill $pids   (then re-run ./run.sh)" >&2
    exit 1
  fi
}

# Poll a port's /health until it answers. Bails immediately if the
# backend process dies (e.g. a bind failure) instead of polling a corpse, and
# otherwise times out after ~60s. $3 = the backend's PID from start_backend.
wait_for() {
  local label="$1" port="$2" pid="$3" tries=0
  printf "→ waiting for %s" "$label"
  until curl -sf "http://localhost:$port/health" >/dev/null 2>&1; do
    # Dead process? Don't wait the full minute — surface its log and bail now.
    if ! kill -0 "$pid" 2>/dev/null; then
      echo " — $label exited before it was ready. Last log lines:" >&2
      tail -n 20 "$LOG_DIR/$label.log" >&2 || true
      exit 1
    fi
    tries=$((tries + 1))
    if (( tries > 60 )); then
      echo " — timed out after ${tries}s. Last log lines:" >&2
      tail -n 20 "$LOG_DIR/$label.log" >&2 || true
      exit 1
    fi
    printf "."
    sleep 1
  done
  echo " ✓"
}

# Ensure both backends are installed and configured before launching.
bootstrap_backend "ai-model"  "AI Model"
bootstrap_backend "rag-model" "RAG Model"

# The RAG engine needs its local vector store. Build it once if absent.
# This embeds the whole kb/ over the Gemini API and prints nothing until done,
# so we tee output to a log and warn that it's network-bound, not frozen.
if [[ ! -d "$ROOT/RAG Model/chroma_db" ]]; then
  echo "→ rag-model: building vector store — embedding kb/ via the Gemini API."
  echo "  This is network-bound and can take 1–3 min with no output. Not frozen."
  echo "  (needs GEMINI_API_KEY in 'RAG Model/.env' + internet; log → $LOG_DIR/ingest.log)"
  if ! ( cd "$ROOT/RAG Model" && "$ROOT/RAG Model/.venv/bin/python" -m asra_matcher ingest --rebuild ) \
        2>&1 | tee "$LOG_DIR/ingest.log"; then
    echo "✗ rag-model: vector-store build failed — see $LOG_DIR/ingest.log" >&2
    echo "  Common causes: missing/invalid GEMINI_API_KEY, or no network access." >&2
    exit 1
  fi
fi

# Make sure both ports are free before we start anything, so a conflict is a
# clear up-front error rather than a backend that dies on bind.
preflight_port "ai-model"  "$AI_PORT"
preflight_port "rag-model" "$RAG_PORT"

start_backend "ai-model"  "AI Model"  "$AI_PORT";  ai_pid=$BACKEND_PID
start_backend "rag-model" "RAG Model" "$RAG_PORT"; rag_pid=$BACKEND_PID

wait_for "ai-model"  "$AI_PORT"  "$ai_pid"
wait_for "rag-model" "$RAG_PORT" "$rag_pid"

echo "→ both engines up. Starting frontend…"
echo "  Open http://localhost:5173/compare"
echo ""

cd "$ROOT/Frontend"
[[ -d node_modules ]] || npm install
npm run dev
