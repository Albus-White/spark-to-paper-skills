#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_ROOT="${DRAWAI_LOCAL_RUNTIME_ROOT:-}"
if [[ -z "$RUNTIME_ROOT" ]]; then
  RUNTIME_ROOT="$ROOT/.local/drawai_runtime"
fi
PYTHON_VERSION="${DRAWAI_LOCAL_RUNTIME_PYTHON:-3.12}"
TORCH_SPEC="${DRAWAI_TORCH_SPEC:-torch>=2.4,<2.12}"
TORCHVISION_SPEC="${DRAWAI_TORCHVISION_SPEC:-torchvision>=0.19,<0.27}"
TORCH_BACKEND="${DRAWAI_TORCH_BACKEND:-cpu}"
TORCH_INDEX_URL="${DRAWAI_TORCH_INDEX_URL:-}"
SKIP_TORCH_INSTALL="${DRAWAI_SKIP_TORCH_INSTALL:-0}"

torch_index_url_for_backend() {
  case "$1" in
    default)
      printf ''
      ;;
    cpu)
      printf 'https://download.pytorch.org/whl/cpu'
      ;;
    cu121|cu124|cu126|cu128|cu130)
      printf 'https://download.pytorch.org/whl/%s' "$1"
      ;;
    *)
      echo "Unsupported DRAWAI_TORCH_BACKEND=$1" >&2
      exit 2
      ;;
  esac
}

torch_backend_from_cuda_version() {
  local version="$1"
  local major="${version%%.*}"
  local minor="${version#*.}"
  if [[ "$minor" == "$version" ]]; then
    minor=0
  fi
  if ! [[ "$major" =~ ^[0-9]+$ && "$minor" =~ ^[0-9]+$ ]]; then
    printf 'cpu'
  elif (( major > 13 || (major == 13 && minor >= 0) )); then
    printf 'cu130'
  elif (( major > 12 || (major == 12 && minor >= 8) )); then
    printf 'cu128'
  elif (( major == 12 && minor >= 6 )); then
    printf 'cu126'
  elif (( major == 12 && minor >= 4 )); then
    printf 'cu124'
  elif (( major == 12 && minor >= 1 )); then
    printf 'cu121'
  else
    printf 'cpu'
  fi
}

detect_torch_backend() {
  if [[ "$(uname -s)" != "Linux" ]]; then
    printf 'default'
    return
  fi
  if command -v nvidia-smi >/dev/null 2>&1; then
    local cuda_version
    cuda_version="$(nvidia-smi 2>/dev/null | sed -nE 's/.*CUDA Version: ([0-9]+(\.[0-9]+)?).*/\1/p' | head -n 1)"
    if [[ -n "$cuda_version" ]]; then
      torch_backend_from_cuda_version "$cuda_version"
      return
    fi
  fi
  printf 'cpu'
}

RESOLVED_TORCH_BACKEND="$TORCH_BACKEND"
if [[ "$RESOLVED_TORCH_BACKEND" == "auto" ]]; then
  RESOLVED_TORCH_BACKEND="$(detect_torch_backend)"
fi
if [[ -z "$TORCH_INDEX_URL" ]]; then
  TORCH_INDEX_URL="$(torch_index_url_for_backend "$RESOLVED_TORCH_BACKEND")"
fi

default_if_exists() {
  local candidate="$1"
  if [[ -e "$candidate" ]]; then
    printf '%s' "$candidate"
  fi
}

SAM3_SOURCE="${DRAWAI_SAM3_SOURCE:-$(default_if_exists "$RUNTIME_ROOT/source/sam3")}"
SAM3_CHECKPOINT_SOURCE="${DRAWAI_SAM3_CHECKPOINT_SOURCE:-$(default_if_exists "$RUNTIME_ROOT/models/sam3/sam3.pt")}"
SAM3_BPE_SOURCE="${DRAWAI_SAM3_BPE_SOURCE:-$(default_if_exists "$RUNTIME_ROOT/models/sam3/bpe_simple_vocab_16e6.txt.gz")}"
RMBG_SOURCE="${DRAWAI_RMBG_SOURCE:-$(default_if_exists "$RUNTIME_ROOT/models/rmbg2")}"
PADDLE_MODELS_SOURCE="${DRAWAI_PADDLE_MODELS_SOURCE:-$(default_if_exists "$RUNTIME_ROOT/models/paddlex/official_models")}"
GATEWAY_SOURCE="${DRAWAI_LOCAL_CODEX_GATEWAY_SOURCE:-}"

PYTHON="$RUNTIME_ROOT/.venv/bin/python"

copy_file() {
  local source="$1"
  local target="$2"
  mkdir -p "$(dirname "$target")"
  if [[ "$source" != *:* && -e "$source" && -e "$target" ]]; then
    local source_real
    local target_real
    source_real="$(cd "$(dirname "$source")" && pwd -P)/$(basename "$source")"
    target_real="$(cd "$(dirname "$target")" && pwd -P)/$(basename "$target")"
    if [[ "$source_real" == "$target_real" ]]; then
      return
    fi
  fi
  if [[ "$source" == *:* ]]; then
    rsync -a "$source" "$target"
  else
    cp "$source" "$target"
  fi
}

sync_dir() {
  local source="$1"
  local target="$2"
  mkdir -p "$target"
  if [[ "$source" != *:* && -d "$source" ]]; then
    local source_real
    local target_real
    source_real="$(cd "$source" && pwd -P)"
    target_real="$(cd "$target" && pwd -P)"
    if [[ "$source_real" == "$target_real" ]]; then
      return
    fi
  fi
  rsync -a --delete --exclude='.msc' --exclude='.mv' --exclude='._____temp' "$source" "$target"
}

require_source() {
  local env_name="$1"
  local value="$2"
  local description="$3"
  if [[ -z "$value" ]]; then
    echo "Missing $env_name for $description." >&2
    echo "Set $env_name to a local path/rsync source, or run scripts/download_drawai_local_models.sh first." >&2
    exit 1
  fi
}

echo "[drawai-local] runtime root: $RUNTIME_ROOT"
mkdir -p "$RUNTIME_ROOT/models/sam3" "$RUNTIME_ROOT/models/paddlex/official_models" "$RUNTIME_ROOT/models/rmbg2" "$RUNTIME_ROOT/tools"

echo "[drawai-local] creating Python runtime"
uv venv "$RUNTIME_ROOT/.venv" --python "$PYTHON_VERSION"

echo "[drawai-local] installing Paddle CPU runtime"
uv pip install --python "$PYTHON" paddlepaddle==3.2.0 --index-url https://www.paddlepaddle.org.cn/packages/stable/cpu/

if [[ "$SKIP_TORCH_INSTALL" == "1" ]]; then
  echo "[drawai-local] skipping PyTorch install because DRAWAI_SKIP_TORCH_INSTALL=1"
  "$PYTHON" -c "import torch, torchvision"
else
  echo "[drawai-local] installing PyTorch runtime: $TORCH_SPEC $TORCHVISION_SPEC"
  echo "[drawai-local] PyTorch backend: $RESOLVED_TORCH_BACKEND"
  TORCH_INSTALL_COMMAND=(uv pip install --python "$PYTHON")
  if [[ -n "$TORCH_INDEX_URL" ]]; then
    echo "[drawai-local] PyTorch index: $TORCH_INDEX_URL"
    TORCH_INSTALL_COMMAND+=(--index-url "$TORCH_INDEX_URL" --reinstall-package torch --reinstall-package torchvision)
  fi
  TORCH_INSTALL_COMMAND+=("$TORCH_SPEC" "$TORCHVISION_SPEC")
  "${TORCH_INSTALL_COMMAND[@]}"
fi

echo "[drawai-local] installing DrawAI runtime dependencies"
uv pip install --python "$PYTHON" \
  --prerelease=allow \
  -e "$ROOT" \
  paddleocr==3.5.0 \
  paddlex==3.5.2 \
  transformers==4.57.6 \
  timm==1.0.27 \
  opencv-python-headless==4.11.0.86 \
  numpy==1.26.4 \
  einops \
  kornia==0.8.2 \
  kornia-rs==0.1.11 \
  pycocotools \
  scikit-image

require_source "DRAWAI_SAM3_SOURCE" "$SAM3_SOURCE" "the facebookresearch/sam3 source checkout"
if [[ ! -d "$SAM3_SOURCE" ]]; then
  echo "SAM3 source checkout not found: $SAM3_SOURCE" >&2
  echo "Set DRAWAI_SAM3_SOURCE to the facebookresearch/sam3 checkout." >&2
  exit 1
fi

echo "[drawai-local] installing SAM3 source: $SAM3_SOURCE"
uv pip install --python "$PYTHON" -e "$SAM3_SOURCE"

require_source "DRAWAI_SAM3_CHECKPOINT_SOURCE" "$SAM3_CHECKPOINT_SOURCE" "the SAM3 checkpoint file"
require_source "DRAWAI_SAM3_BPE_SOURCE" "$SAM3_BPE_SOURCE" "the SAM3 BPE vocabulary file"
echo "[drawai-local] syncing SAM3 checkpoint and BPE"
copy_file "$SAM3_CHECKPOINT_SOURCE" "$RUNTIME_ROOT/models/sam3/sam3.pt"
copy_file "$SAM3_BPE_SOURCE" "$RUNTIME_ROOT/models/sam3/bpe_simple_vocab_16e6.txt.gz"

require_source "DRAWAI_PADDLE_MODELS_SOURCE" "$PADDLE_MODELS_SOURCE" "the PaddleOCR official model directory"
echo "[drawai-local] syncing PaddleOCR PP-OCRv5 server models"
sync_dir "$PADDLE_MODELS_SOURCE/PP-OCRv5_server_det" "$RUNTIME_ROOT/models/paddlex/official_models/"
sync_dir "$PADDLE_MODELS_SOURCE/PP-OCRv5_server_rec" "$RUNTIME_ROOT/models/paddlex/official_models/"

require_source "DRAWAI_RMBG_SOURCE" "$RMBG_SOURCE" "the RMBG-2.0 model directory"
echo "[drawai-local] syncing RMBG-2.0"
sync_dir "$RMBG_SOURCE" "$RUNTIME_ROOT/models/rmbg2/"

if [[ -n "$GATEWAY_SOURCE" ]]; then
  echo "[drawai-local] syncing optional local Codex OpenAI gateway"
  sync_dir "$GATEWAY_SOURCE" "$RUNTIME_ROOT/tools/local-codex-openai-gateway/"
else
  echo "[drawai-local] skipping optional local Codex OpenAI gateway; Codex Python SDK is the default SVG backend"
fi

echo "[drawai-local] verifying key files"
test -f "$RUNTIME_ROOT/models/sam3/sam3.pt"
test -f "$RUNTIME_ROOT/models/sam3/bpe_simple_vocab_16e6.txt.gz"
test -f "$RUNTIME_ROOT/models/paddlex/official_models/PP-OCRv5_server_det/inference.pdiparams"
test -f "$RUNTIME_ROOT/models/paddlex/official_models/PP-OCRv5_server_rec/inference.pdiparams"
test -f "$RUNTIME_ROOT/models/rmbg2/model.safetensors"
if [[ -n "$GATEWAY_SOURCE" ]]; then
  test -f "$RUNTIME_ROOT/tools/local-codex-openai-gateway/package.json"
fi
"$PYTHON" -c "import openai_codex"

echo "[drawai-local] ready"
echo "Run with: uv run drawai run <image> --local --run-name local_single_svg_ppt"
