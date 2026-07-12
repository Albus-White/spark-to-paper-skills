#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SESSION="${DRAWAI_WORKBENCH_TMUX_SESSION:-drawai-workbench}"
HOST="${DRAWAI_WORKBENCH_HOST:-127.0.0.1}"
CONNECT_HOST="${DRAWAI_WORKBENCH_CONNECT_HOST:-}"
if [[ -z "$CONNECT_HOST" ]]; then
  case "$HOST" in
    0.0.0.0|::|\[::\])
      CONNECT_HOST="127.0.0.1"
      ;;
    *)
      CONNECT_HOST="$HOST"
      ;;
  esac
fi
API_PORT="${DRAWAI_WORKBENCH_API_PORT:-8890}"
FRONTEND_PORT="${DRAWAI_WORKBENCH_FRONTEND_PORT:-5174}"
SAM_PORT="${DRAWAI_SAM3_PORT:-18080}"
OCR_PORT="${DRAWAI_OCR_PORT:-18080}"
RUNTIME_ROOT="${DRAWAI_LOCAL_RUNTIME_ROOT:-.local/drawai_runtime}"
case "$RUNTIME_ROOT" in
  /*)
    RUNTIME_ROOT_ABS="$RUNTIME_ROOT"
    ;;
  *)
    RUNTIME_ROOT_ABS="$ROOT_DIR/$RUNTIME_ROOT"
    ;;
esac
RUNTIME_BIN="$RUNTIME_ROOT_ABS/.venv/bin"
WORKSPACE="${DRAWAI_WORKBENCH_WORKSPACE:-.local/workbench}"
CONFIG="${DRAWAI_WORKBENCH_DEFAULT_CONFIG:-configs/drawai/config.yaml}"
DEVICE="${DRAWAI_DEVICE:-cpu}"
SAM3_DEVICE="${DRAWAI_SAM3_DEVICE:-}"
RMBG_DEVICE="${DRAWAI_RMBG_DEVICE:-}"
PADDLE_DEVICE="${DRAWAI_PADDLE_DEVICE:-}"
OCR_DET_LIMIT_SIDE_LEN="${DRAWAI_OCR_DET_LIMIT_SIDE_LEN:-1280}"
OCR_TIMEOUT_SECONDS="${DRAWAI_WORKBENCH_OCR_TIMEOUT_SECONDS:-600}"
RAW_MODEL_API="${DRAWAI_MODEL_API:-}"
MODEL_API="${RAW_MODEL_API:-http://$CONNECT_HOST:$SAM_PORT}"
START_LOCAL_MODEL="${DRAWAI_WORKBENCH_START_MODEL:-}"
RUNTIME_LOG=".local/drawai-local-services.log"
API_LOG=".local/workbench-api.log"
FRONTEND_LOG=".local/workbench-frontend.log"
RUNTIME_PID=".local/drawai-local-services.pid"
API_PID=".local/workbench-api.pid"
FRONTEND_PID=".local/workbench-frontend.pid"

if command -v tmux >/dev/null 2>&1; then
  LAUNCHER="tmux"
else
  LAUNCHER="nohup"
fi

is_loopback_model_api() {
  case "$1" in
    ""|http://127.0.0.1:*|http://localhost:*|http://0.0.0.0:*|http://\[::1\]:*)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

if [[ -z "$START_LOCAL_MODEL" ]]; then
  if is_loopback_model_api "$RAW_MODEL_API"; then
    START_LOCAL_MODEL=1
  else
    START_LOCAL_MODEL=0
  fi
fi

wait_for_http() {
  local name="$1"
  local url="$2"
  local log_path="$3"
  for _ in {1..60}; do
    if curl -fsS --max-time 2 "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  echo "[drawai-workbench] $name did not become ready: $url" >&2
  if [[ -f "$log_path" ]]; then
    echo "[drawai-workbench] last lines from $log_path:" >&2
    tail -n 80 "$log_path" >&2
  fi
  return 1
}

stop_pid_file() {
  local pid_path="$1"
  local pid=""
  if [[ ! -f "$pid_path" ]]; then
    return 0
  fi
  pid="$(cat "$pid_path" 2>/dev/null || true)"
  if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
    for _ in {1..20}; do
      if ! kill -0 "$pid" 2>/dev/null; then
        break
      fi
      sleep 0.1
    done
    if kill -0 "$pid" 2>/dev/null; then
      kill -9 "$pid" 2>/dev/null || true
    fi
  fi
  rm -f "$pid_path"
}

start_nohup_process() {
  local name="$1"
  local command="$2"
  local log_path="$3"
  local pid_path="$4"
  stop_pid_file "$pid_path"
  : >"$log_path"
  echo "[drawai-workbench] starting $name with nohup; log: $log_path"
  nohup bash -lc "$command" >"$log_path" 2>&1 &
  echo "$!" >"$pid_path"
}

if [[ "$START_LOCAL_MODEL" == "1" ]]; then
  if ! is_loopback_model_api "$MODEL_API"; then
    echo "[drawai-workbench] refusing to auto-start local model runtime for non-loopback DRAWAI_MODEL_API=$MODEL_API" >&2
    echo "[drawai-workbench] unset DRAWAI_MODEL_API, or set DRAWAI_WORKBENCH_START_MODEL=0 for an external model runtime." >&2
    exit 2
  fi
fi

cd "$ROOT_DIR"
mkdir -p .local

RUNTIME_PYTHONPATH="$ROOT_DIR/src"
for runtime_path in "$RUNTIME_ROOT/python_site_packages" "$RUNTIME_ROOT/source/sam3"; do
  if [[ -d "$runtime_path" ]]; then
    RUNTIME_PYTHONPATH="$RUNTIME_PYTHONPATH:$runtime_path"
  fi
done
if [[ -n "${DRAWAI_LOCAL_RUNTIME_EXTRA_PYTHONPATH:-}" ]]; then
  RUNTIME_PYTHONPATH="$RUNTIME_PYTHONPATH:$DRAWAI_LOCAL_RUNTIME_EXTRA_PYTHONPATH"
fi
if [[ -n "${PYTHONPATH:-}" ]]; then
  RUNTIME_PYTHONPATH="$RUNTIME_PYTHONPATH:$PYTHONPATH"
fi

RUNTIME_COMMAND="env PYTHONPATH='$RUNTIME_PYTHONPATH' uv run drawai server model --host '$HOST' --runtime-root '$RUNTIME_ROOT' --device '$DEVICE' --sam3-device '$SAM3_DEVICE' --rmbg-device '$RMBG_DEVICE' --paddle-device '$PADDLE_DEVICE' --ocr-det-limit-side-len '$OCR_DET_LIMIT_SIDE_LEN' --sam-port '$SAM_PORT' --ocr-port '$OCR_PORT'"
API_COMMAND="env PATH='$RUNTIME_BIN:$PATH' DRAWAI_LOCAL_RUNTIME_ROOT='$RUNTIME_ROOT_ABS' DRAWAI_WORKBENCH_WORKSPACE='$WORKSPACE' DRAWAI_WORKBENCH_DEFAULT_CONFIG='$CONFIG' DRAWAI_WORKBENCH_OCR_TIMEOUT_SECONDS='$OCR_TIMEOUT_SECONDS' DRAWAI_MODEL_API='$MODEL_API' uv run drawai server api --no-start-model --host '$HOST' --port '$API_PORT' --workspace '$WORKSPACE' --config '$CONFIG' --model-api '$MODEL_API' --ocr-timeout-seconds '$OCR_TIMEOUT_SECONDS'"
FRONTEND_COMMAND="env DRAWAI_WORKBENCH_API_URL='http://$CONNECT_HOST:$API_PORT' DRAWAI_WORKBENCH_HOST='$HOST' DRAWAI_WORKBENCH_FRONTEND_PORT='$FRONTEND_PORT' '$ROOT_DIR/scripts/run_drawai_workbench_frontend.sh'"

if [[ "$LAUNCHER" == "tmux" ]]; then
  if tmux has-session -t "$SESSION" 2>/dev/null; then
    tmux kill-session -t "$SESSION"
  fi

  if [[ "$START_LOCAL_MODEL" == "1" ]]; then
    tmux new-session -d -s "$SESSION" -n runtime -c "$ROOT_DIR" \
      "$RUNTIME_COMMAND 2>&1 | tee '$RUNTIME_LOG'"
    wait_for_http "model runtime" "$MODEL_API/health" "$RUNTIME_LOG"
    tmux new-window -t "$SESSION" -n api -c "$ROOT_DIR" \
      "$API_COMMAND 2>&1 | tee '$API_LOG'"
  else
    tmux new-session -d -s "$SESSION" -n api -c "$ROOT_DIR" \
      "$API_COMMAND 2>&1 | tee '$API_LOG'"
  fi

  tmux new-window -t "$SESSION" -n frontend -c "$ROOT_DIR" \
    "$FRONTEND_COMMAND 2>&1 | tee '$FRONTEND_LOG'"
else
  echo "[drawai-workbench] tmux is not available; falling back to nohup."
  stop_pid_file "$RUNTIME_PID"
  stop_pid_file ".local/workbench-api.pid"
  stop_pid_file ".local/workbench-frontend.pid"
  if [[ "$START_LOCAL_MODEL" == "1" ]]; then
    start_nohup_process "model runtime" "$RUNTIME_COMMAND" "$RUNTIME_LOG" "$RUNTIME_PID"
    wait_for_http "model runtime" "$MODEL_API/health" "$RUNTIME_LOG"
  fi
  start_nohup_process "workbench api" "$API_COMMAND" "$API_LOG" "$API_PID"
  start_nohup_process "workbench frontend" "$FRONTEND_COMMAND" "$FRONTEND_LOG" "$FRONTEND_PID"
fi

wait_for_http "workbench frontend" "http://$CONNECT_HOST:$FRONTEND_PORT/" "$FRONTEND_LOG"

echo "DrawAI Workbench launcher: $LAUNCHER"
echo "Frontend: http://$HOST:$FRONTEND_PORT/"
echo "API: http://$HOST:$API_PORT/api/health"
echo "Runtime health: http://$HOST:$SAM_PORT/health and http://$HOST:$OCR_PORT/health"
echo "Model API: $MODEL_API"
echo "Internal connect host: $CONNECT_HOST"
echo
echo "Logs:"
echo "  $RUNTIME_LOG"
echo "  $API_LOG"
echo "  $FRONTEND_LOG"
echo
if [[ "$LAUNCHER" == "tmux" ]]; then
  echo "DrawAI Workbench session: $SESSION"
  echo "Attach: tmux attach -t $SESSION"
else
  echo "PID files:"
  echo "  $RUNTIME_PID"
  echo "  $API_PID"
  echo "  $FRONTEND_PID"
fi
