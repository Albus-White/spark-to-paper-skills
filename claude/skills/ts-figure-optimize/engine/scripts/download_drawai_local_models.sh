#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_ROOT="${DRAWAI_LOCAL_RUNTIME_ROOT:-$ROOT/.local/drawai_runtime}"
MODEL_SOURCE="${DRAWAI_MODEL_SOURCE:-modelscope}"

SAM3_MODELSCOPE_REPO="facebook/sam3"
SAM3_HF_REPO="facebook/sam3"
SAM3_SOURCE_REPO="${DRAWAI_SAM3_SOURCE_REPO:-https://github.com/facebookresearch/sam3.git}"
SAM3_BPE_URL="https://raw.githubusercontent.com/facebookresearch/sam3/main/sam3/assets/bpe_simple_vocab_16e6.txt.gz"
PADDLE_DET_MODELSCOPE_REPO="PaddlePaddle/PP-OCRv5_server_det"
PADDLE_DET_HF_REPO="PaddlePaddle/PP-OCRv5_server_det"
PADDLE_REC_MODELSCOPE_REPO="PaddlePaddle/PP-OCRv5_server_rec"
PADDLE_REC_HF_REPO="PaddlePaddle/PP-OCRv5_server_rec"
RMBG_MODELSCOPE_REPO="AI-ModelScope/RMBG-2.0"
RMBG_HF_REPO="briaai/RMBG-2.0"

DOWNLOAD_PADDLE=1
DOWNLOAD_SAM3=0
DOWNLOAD_RMBG=0
COMPONENT_SELECTED=0
ACCEPT_SAM3_LICENSE="${DRAWAI_ACCEPT_SAM3_LICENSE:-0}"
ACCEPT_RMBG_LICENSE="${DRAWAI_ACCEPT_RMBG_LICENSE:-0}"
DRY_RUN=0
HF_ACCESS_HINT_PRINTED=0

usage() {
  cat <<'EOF'
Usage:
  scripts/download_drawai_local_models.sh [options]

Downloads official local-runtime model artifacts into .local/drawai_runtime.

Default:
  Downloads only Apache-2.0 PaddleOCR PP-OCRv5 server models.

Options:
  --all                         Download PaddleOCR, SAM3, and RMBG artifacts.
  --paddle                      Download PaddleOCR PP-OCRv5 server det/rec.
  --sam3                        Download SAM3 source, checkpoint, and BPE vocab.
  --rmbg                        Download RMBG-2.0 local model files.
  --source modelscope|huggingface
                                Model artifact source. Default: modelscope.
  --runtime-root PATH           Override .local/drawai_runtime.
  --sam3-source-repo URL        Override the facebookresearch/sam3 source git URL.
  --accept-sam3-license         Confirm Meta SAM License/Hugging Face gated access terms.
  --accept-rmbg-license         Confirm you accepted the BRIA RMBG-2.0 license/access terms.
  --dry-run                     Print planned actions without downloading.
  -h, --help                    Show this help.

Environment:
  DRAWAI_LOCAL_RUNTIME_ROOT      Runtime root. Default: .local/drawai_runtime.
  DRAWAI_MODEL_SOURCE            modelscope or huggingface. Default: modelscope.
  DRAWAI_SAM3_SOURCE_REPO        Override the facebookresearch/sam3 source git URL.
  DRAWAI_ACCEPT_SAM3_LICENSE=1  Same as --accept-sam3-license.
  DRAWAI_ACCEPT_RMBG_LICENSE=1  Same as --accept-rmbg-license.
  HF_TOKEN                      Recommended when --source huggingface uses gated repositories.

Notes:
  ModelScope is the default artifact source and does not require Hugging Face
  gated access. SAM3 still uses Meta's SAM License. RMBG-2.0 weights are for
  non-commercial use unless you have a commercial agreement with BRIA.
EOF
}

select_component() {
  if [[ "$COMPONENT_SELECTED" -eq 0 ]]; then
    DOWNLOAD_PADDLE=0
    DOWNLOAD_SAM3=0
    DOWNLOAD_RMBG=0
    COMPONENT_SELECTED=1
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --all)
      select_component
      DOWNLOAD_PADDLE=1
      DOWNLOAD_SAM3=1
      DOWNLOAD_RMBG=1
      ;;
    --paddle)
      select_component
      DOWNLOAD_PADDLE=1
      ;;
    --sam3)
      select_component
      DOWNLOAD_SAM3=1
      ;;
    --rmbg)
      select_component
      DOWNLOAD_RMBG=1
      ;;
    --source)
      if [[ $# -lt 2 ]]; then
        echo "--source requires modelscope or huggingface." >&2
        exit 2
      fi
      MODEL_SOURCE="$2"
      shift
      ;;
    --runtime-root)
      if [[ $# -lt 2 ]]; then
        echo "--runtime-root requires a path." >&2
        exit 2
      fi
      RUNTIME_ROOT="$2"
      shift
      ;;
    --sam3-source-repo)
      if [[ $# -lt 2 ]]; then
        echo "--sam3-source-repo requires a URL or local git path." >&2
        exit 2
      fi
      SAM3_SOURCE_REPO="$2"
      shift
      ;;
    --accept-sam3-license)
      ACCEPT_SAM3_LICENSE=1
      ;;
    --accept-rmbg-license)
      ACCEPT_RMBG_LICENSE=1
      ;;
    --dry-run)
      DRY_RUN=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

normalize_model_source() {
  case "$MODEL_SOURCE" in
    modelscope|ms)
      MODEL_SOURCE="modelscope"
      ;;
    huggingface|hf)
      MODEL_SOURCE="huggingface"
      ;;
    *)
      echo "Unsupported model source: $MODEL_SOURCE" >&2
      echo "Use --source modelscope or --source huggingface." >&2
      exit 2
      ;;
  esac
}

require_command() {
  local name="$1"
  if ! command -v "$name" >/dev/null 2>&1; then
    echo "Missing required command: $name" >&2
    exit 1
  fi
}

plan() {
  echo "[drawai-models] $*"
}

ensure_hf_access_hint() {
  if [[ "$HF_ACCESS_HINT_PRINTED" -eq 1 ]]; then
    return
  fi
  if [[ -z "${HF_TOKEN:-}" && -z "${HUGGING_FACE_HUB_TOKEN:-}" && -z "${HUGGINGFACE_HUB_TOKEN:-}" ]]; then
    plan "HF_TOKEN is not set; gated downloads will rely on any existing Hugging Face CLI login."
  fi
  HF_ACCESS_HINT_PRINTED=1
}

require_license_acceptance() {
  local accepted="$1"
  local name="$2"
  local flag="$3"
  local url="$4"
  if [[ "$accepted" != "1" ]]; then
    echo "$name requires explicit license/access acceptance before downloading." >&2
    echo "Review: $url" >&2
    echo "Then rerun with $flag or set the matching DRAWAI_ACCEPT_* env var." >&2
    exit 1
  fi
}

download_modelscope_snapshot() {
  local repo_id="$1"
  local target_dir="$2"
  shift 2
  local patterns=("$@")
  plan "downloading ModelScope snapshot: $repo_id -> $target_dir"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    return
  fi
  mkdir -p "$target_dir"
  uv run --with modelscope --with pysocks python - "$repo_id" "$target_dir" "${patterns[@]}" <<'PY'
from __future__ import annotations

import sys

from modelscope import snapshot_download

repo_id = sys.argv[1]
target_dir = sys.argv[2]
allow_patterns = sys.argv[3:] or None

snapshot_download(
    repo_id,
    local_dir=target_dir,
    allow_file_pattern=allow_patterns,
)
PY
}

download_hf_snapshot() {
  local repo_id="$1"
  local target_dir="$2"
  shift 2
  local patterns=("$@")
  plan "downloading Hugging Face snapshot: $repo_id -> $target_dir"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    return
  fi
  mkdir -p "$target_dir"
  uv run --with huggingface-hub --with socksio python - "$repo_id" "$target_dir" "${patterns[@]}" <<'PY'
from __future__ import annotations

import os
import sys

from huggingface_hub.errors import GatedRepoError
from huggingface_hub import snapshot_download

repo_id = sys.argv[1]
target_dir = sys.argv[2]
allow_patterns = sys.argv[3:] or None
token = (
    os.environ.get("HF_TOKEN")
    or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    or os.environ.get("HUGGINGFACE_HUB_TOKEN")
)

try:
    snapshot_download(
        repo_id=repo_id,
        local_dir=target_dir,
        allow_patterns=allow_patterns,
        token=token,
    )
except GatedRepoError as exc:
    message_lines = [line for line in str(exc).splitlines() if line.strip()]
    print(f"Cannot access gated Hugging Face repo: {repo_id}", file=sys.stderr)
    print(message_lines[-1] if message_lines else type(exc).__name__, file=sys.stderr)
    if repo_id == "facebook/sam3":
        print(
            "SAM3 access is controlled by the upstream repo authors. "
            "Ask for access on https://huggingface.co/facebook/sam3, "
            "rerun with --source modelscope if that mirror is acceptable, "
            "or provide manual SAM3 files with: uv run drawai setup local "
            "--sam3-source /path/to/facebookresearch-sam3 "
            "--sam3-checkpoint /path/to/sam3.pt "
            "--sam3-bpe /path/to/bpe_simple_vocab_16e6.txt.gz",
            file=sys.stderr,
        )
    sys.exit(17)
PY
}

download_model_snapshot() {
  local modelscope_repo_id="$1"
  local hf_repo_id="$2"
  local target_dir="$3"
  shift 3
  if [[ "$MODEL_SOURCE" == "modelscope" ]]; then
    download_modelscope_snapshot "$modelscope_repo_id" "$target_dir" "$@"
  else
    ensure_hf_access_hint
    download_hf_snapshot "$hf_repo_id" "$target_dir" "$@"
  fi
}

model_snapshot_url() {
  local modelscope_repo_id="$1"
  local hf_repo_id="$2"
  if [[ "$MODEL_SOURCE" == "modelscope" ]]; then
    echo "https://modelscope.cn/models/$modelscope_repo_id"
  else
    echo "https://huggingface.co/$hf_repo_id"
  fi
}

download_url() {
  local url="$1"
  local target="$2"
  plan "downloading URL: $url -> $target"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    return
  fi
  mkdir -p "$(dirname "$target")"
  uv run --with httpx --with socksio python - "$url" "$target" <<'PY'
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import httpx

url = sys.argv[1]
target = Path(sys.argv[2])
target.parent.mkdir(parents=True, exist_ok=True)
with httpx.stream("GET", url, follow_redirects=True, timeout=600) as response:
    response.raise_for_status()
    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as handle:
        for chunk in response.iter_bytes():
            handle.write(chunk)
        temp_path = Path(handle.name)
temp_path.replace(target)
PY
}

download_sam3_source() {
  local source_dir="$RUNTIME_ROOT/source/sam3"
  plan "syncing SAM3 source: $SAM3_SOURCE_REPO -> $source_dir"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    return
  fi
  require_command git
  mkdir -p "$(dirname "$source_dir")"
  if [[ -d "$source_dir/.git" ]]; then
    git -C "$source_dir" fetch --depth 1 origin main
    git -C "$source_dir" checkout --quiet FETCH_HEAD
  elif [[ -e "$source_dir" ]]; then
    echo "SAM3 source target exists but is not a git checkout: $source_dir" >&2
    exit 1
  else
    git clone --depth 1 "$SAM3_SOURCE_REPO" "$source_dir"
  fi
}

download_sam3_bpe() {
  local source_bpe="$RUNTIME_ROOT/source/sam3/sam3/assets/bpe_simple_vocab_16e6.txt.gz"
  local target_bpe="$RUNTIME_ROOT/models/sam3/bpe_simple_vocab_16e6.txt.gz"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    plan "syncing SAM3 BPE vocab: $source_bpe -> $target_bpe"
    return
  fi
  if [[ -f "$source_bpe" ]]; then
    plan "syncing SAM3 BPE vocab: $source_bpe -> $target_bpe"
    mkdir -p "$(dirname "$target_bpe")"
    cp "$source_bpe" "$target_bpe"
  else
    download_url "$SAM3_BPE_URL" "$target_bpe"
  fi
}

download_paddle_models() {
  local root="$RUNTIME_ROOT/models/paddlex/official_models"
  download_model_snapshot "$PADDLE_DET_MODELSCOPE_REPO" "$PADDLE_DET_HF_REPO" "$root/PP-OCRv5_server_det" \
    "README.md" "config.json" "inference.json" "inference.pdiparams" "inference.yml"
  download_model_snapshot "$PADDLE_REC_MODELSCOPE_REPO" "$PADDLE_REC_HF_REPO" "$root/PP-OCRv5_server_rec" \
    "README.md" "config.json" "inference.json" "inference.pdiparams" "inference.yml"
}

download_sam3_models() {
  if [[ "$MODEL_SOURCE" == "huggingface" ]]; then
    require_license_acceptance \
      "$ACCEPT_SAM3_LICENSE" \
      "SAM3 Hugging Face download" \
      "--accept-sam3-license" \
      "https://huggingface.co/facebook/sam3"
  else
    plan "SAM3 artifacts are subject to upstream terms; review https://modelscope.cn/models/$SAM3_MODELSCOPE_REPO"
  fi
  download_sam3_source
  download_model_snapshot "$SAM3_MODELSCOPE_REPO" "$SAM3_HF_REPO" "$RUNTIME_ROOT/models/sam3" \
    "LICENSE" "README.md" "sam3.pt"
  download_sam3_bpe
}

download_rmbg_models() {
  require_license_acceptance \
    "$ACCEPT_RMBG_LICENSE" \
    "RMBG-2.0" \
    "--accept-rmbg-license" \
    "$(model_snapshot_url "$RMBG_MODELSCOPE_REPO" "$RMBG_HF_REPO")"
  download_model_snapshot "$RMBG_MODELSCOPE_REPO" "$RMBG_HF_REPO" "$RUNTIME_ROOT/models/rmbg2" \
    "README.md" \
    "config.json" \
    "preprocessor_config.json" \
    "BiRefNet_config.py" \
    "birefnet.py" \
    "model.safetensors"
}

verify_file() {
  local path="$1"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    return
  fi
  if [[ ! -f "$path" ]]; then
    echo "Expected downloaded file is missing: $path" >&2
    exit 1
  fi
}

write_model_sources_notice() {
  local notice="$RUNTIME_ROOT/MODEL_SOURCES.md"
  local paddle_det_url
  local paddle_rec_url
  local sam3_url
  local rmbg_url
  paddle_det_url="$(model_snapshot_url "$PADDLE_DET_MODELSCOPE_REPO" "$PADDLE_DET_HF_REPO")"
  paddle_rec_url="$(model_snapshot_url "$PADDLE_REC_MODELSCOPE_REPO" "$PADDLE_REC_HF_REPO")"
  sam3_url="$(model_snapshot_url "$SAM3_MODELSCOPE_REPO" "$SAM3_HF_REPO")"
  rmbg_url="$(model_snapshot_url "$RMBG_MODELSCOPE_REPO" "$RMBG_HF_REPO")"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    return
  fi
  cat > "$notice" <<EOF
# DrawAI Local Runtime Model Sources

This directory contains locally downloaded model artifacts for DrawAI. Do not
commit these files to git.

- Download source: $MODEL_SOURCE
- PaddleOCR detection: $paddle_det_url (Apache-2.0)
- PaddleOCR recognition: $paddle_rec_url (Apache-2.0)
- SAM3: $sam3_url and $SAM3_SOURCE_REPO (Meta SAM License)
- SAM3 BPE vocab: $SAM3_SOURCE_REPO source checkout; fallback URL $SAM3_BPE_URL
- RMBG-2.0: $rmbg_url (BRIA RMBG-2.0 / CC BY-NC 4.0 terms on the model card)

Review the upstream licenses and access terms before using these artifacts in a
redistributed, hosted, or commercial environment.
EOF
}

normalize_model_source
require_command uv

plan "runtime root: $RUNTIME_ROOT"
plan "model source: $MODEL_SOURCE"
mkdir -p "$RUNTIME_ROOT/models"

if [[ "$DOWNLOAD_PADDLE" -eq 1 ]]; then
  download_paddle_models
  verify_file "$RUNTIME_ROOT/models/paddlex/official_models/PP-OCRv5_server_det/inference.pdiparams"
  verify_file "$RUNTIME_ROOT/models/paddlex/official_models/PP-OCRv5_server_rec/inference.pdiparams"
fi

if [[ "$DOWNLOAD_SAM3" -eq 1 ]]; then
  download_sam3_models
  verify_file "$RUNTIME_ROOT/models/sam3/sam3.pt"
  verify_file "$RUNTIME_ROOT/models/sam3/bpe_simple_vocab_16e6.txt.gz"
fi

if [[ "$DOWNLOAD_RMBG" -eq 1 ]]; then
  download_rmbg_models
  verify_file "$RUNTIME_ROOT/models/rmbg2/model.safetensors"
  verify_file "$RUNTIME_ROOT/models/rmbg2/config.json"
  verify_file "$RUNTIME_ROOT/models/rmbg2/birefnet.py"
fi

write_model_sources_notice
plan "ready"
plan "next: scripts/bootstrap_drawai_local_runtime.sh"
