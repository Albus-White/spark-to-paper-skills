#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKBENCH_DIR="$ROOT_DIR/apps/workbench"
HOST="${DRAWAI_WORKBENCH_HOST:-127.0.0.1}"
FRONTEND_PORT="${DRAWAI_WORKBENCH_FRONTEND_PORT:-5174}"
API_URL="${DRAWAI_WORKBENCH_API_URL:-http://127.0.0.1:8890}"
NODE_REQUIREMENT="^20.19.0 || >=22.12.0"

node_version_satisfies_vite() {
  local version="${1#v}"
  local major minor patch
  IFS=. read -r major minor patch <<< "$version"
  major="${major//[!0-9]/}"
  minor="${minor//[!0-9]/}"
  patch="${patch//[!0-9]/}"
  major="${major:-0}"
  minor="${minor:-0}"
  patch="${patch:-0}"

  if (( major == 20 )); then
    (( minor > 19 || (minor == 19 && patch >= 0) ))
    return
  fi
  if (( major == 22 )); then
    (( minor > 12 || (minor == 12 && patch >= 0) ))
    return
  fi
  (( major > 22 ))
}

load_nvm_default_if_available() {
  local nvm_script=""
  if [[ -n "${NVM_DIR:-}" && -s "$NVM_DIR/nvm.sh" ]]; then
    nvm_script="$NVM_DIR/nvm.sh"
  elif [[ -s "$HOME/.nvm/nvm.sh" ]]; then
    export NVM_DIR="$HOME/.nvm"
    nvm_script="$NVM_DIR/nvm.sh"
  fi
  if [[ -z "$nvm_script" ]]; then
    return
  fi

  # shellcheck source=/dev/null
  . "$nvm_script"
  if command -v nvm >/dev/null 2>&1; then
    nvm use --silent default >/dev/null 2>&1 \
      || nvm use --silent node >/dev/null 2>&1 \
      || nvm use --silent stable >/dev/null 2>&1 \
      || true
  fi
}

ensure_workbench_node() {
  if command -v node >/dev/null 2>&1 && node_version_satisfies_vite "$(node -v)"; then
    return
  fi

  load_nvm_default_if_available

  if command -v node >/dev/null 2>&1 && node_version_satisfies_vite "$(node -v)"; then
    return
  fi

  local node_detail="not found"
  if command -v node >/dev/null 2>&1; then
    node_detail="$(node -v) at $(command -v node)"
  fi
  echo "[drawai-workbench] Node.js $NODE_REQUIREMENT is required for the Workbench frontend; found $node_detail." >&2
  echo "[drawai-workbench] Install a compatible Node.js, put it on PATH, or configure an nvm default version." >&2
  exit 2
}

ensure_workbench_node
if ! command -v npm >/dev/null 2>&1; then
  echo "[drawai-workbench] npm is required to start the Workbench frontend. Install Node.js/npm first." >&2
  exit 2
fi

echo "[drawai-workbench] frontend Node: $(node -v) ($(command -v node))"
if [[ ! -x "$WORKBENCH_DIR/node_modules/.bin/vite" ]]; then
  echo "[drawai-workbench] installing frontend dependencies in $WORKBENCH_DIR"
  if [[ -f "$WORKBENCH_DIR/package-lock.json" ]]; then
    (cd "$WORKBENCH_DIR" && npm ci)
  else
    (cd "$WORKBENCH_DIR" && npm install)
  fi
fi

cd "$WORKBENCH_DIR"
exec env DRAWAI_WORKBENCH_API_URL="$API_URL" npm run dev -- --host "$HOST" --port "$FRONTEND_PORT"
