from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import urllib.request
from pathlib import Path
from typing import Iterable, Mapping, Sequence


SAM3_MODELSCOPE_REPO = "facebook/sam3"
SAM3_HF_REPO = "facebook/sam3"
SAM3_SOURCE_REPO = "https://github.com/facebookresearch/sam3.git"
SAM3_BPE_URL = "https://raw.githubusercontent.com/facebookresearch/sam3/main/sam3/assets/bpe_simple_vocab_16e6.txt.gz"
PADDLE_DET_MODELSCOPE_REPO = "PaddlePaddle/PP-OCRv5_server_det"
PADDLE_DET_HF_REPO = "PaddlePaddle/PP-OCRv5_server_det"
PADDLE_REC_MODELSCOPE_REPO = "PaddlePaddle/PP-OCRv5_server_rec"
PADDLE_REC_HF_REPO = "PaddlePaddle/PP-OCRv5_server_rec"
RMBG_MODELSCOPE_REPO = "AI-ModelScope/RMBG-2.0"
RMBG_HF_REPO = "briaai/RMBG-2.0"

DEFAULT_RUNTIME_PYTHON = "3.12"
SETUP_HEARTBEAT_SECONDS = 10.0
DIRECT_DOWNLOAD_HEARTBEAT_SECONDS = 3.0


def runtime_venv_python(runtime_root: Path) -> Path:
    if os.name == "nt":
        return runtime_root / ".venv" / "Scripts" / "python.exe"
    return runtime_root / ".venv" / "bin" / "python"


def runtime_venv_bin(runtime_root: Path) -> Path:
    if os.name == "nt":
        return runtime_root / ".venv" / "Scripts"
    return runtime_root / ".venv" / "bin"


def download_local_models(
    *,
    repo_root: Path,
    runtime_root: Path,
    model_source: str,
    include_sam3: bool,
    include_paddle: bool,
    include_rmbg: bool,
    accept_sam3_license: bool,
    accept_rmbg_license: bool,
    dry_run: bool,
    env: Mapping[str, str],
) -> None:
    components = [
        name
        for name, enabled in (
            ("paddle", include_paddle),
            ("sam3", include_sam3),
            ("rmbg", include_rmbg),
        )
        if enabled
    ]
    print(
        "[drawai-setup] download models: "
        f"source={model_source} components={','.join(components) or 'none'} runtime_root={runtime_root}"
    )
    if dry_run:
        if include_rmbg:
            print("[drawai-setup] would accept RMBG license: yes" if accept_rmbg_license else "[drawai-setup] would accept RMBG license: no")
        if include_paddle or include_sam3 or include_rmbg:
            print("[drawai-setup] would create/use model download helper venv")
        if include_sam3:
            print("[drawai-setup] would download SAM3 source/checkpoint/BPE")
        if include_paddle:
            print("[drawai-setup] would download PaddleOCR detection/recognition models")
        if include_rmbg:
            print("[drawai-setup] would download RMBG-2.0 model")
        return

    runtime_root.mkdir(parents=True, exist_ok=True)
    (runtime_root / "models").mkdir(parents=True, exist_ok=True)
    helper_python = _ensure_download_helper(repo_root=repo_root, runtime_root=runtime_root, env=env)
    print(f"[drawai-setup] model download helper ready: {helper_python}", flush=True)

    if include_paddle:
        print("[drawai-setup] component start: paddle", flush=True)
        _download_paddle_models(
            repo_root=repo_root,
            runtime_root=runtime_root,
            model_source=model_source,
            env=env,
            helper_python=helper_python,
        )
    if include_sam3:
        print("[drawai-setup] component start: sam3", flush=True)
        _download_sam3_models(
            repo_root=repo_root,
            runtime_root=runtime_root,
            model_source=model_source,
            accept_sam3_license=accept_sam3_license,
            env=env,
            helper_python=helper_python,
        )
    if include_rmbg:
        if not accept_rmbg_license:
            raise ValueError("RMBG-2.0 requires explicit license/access acceptance before downloading.")
        print("[drawai-setup] component start: rmbg", flush=True)
        _download_rmbg_models(
            repo_root=repo_root,
            runtime_root=runtime_root,
            model_source=model_source,
            env=env,
            helper_python=helper_python,
        )

    _write_model_sources_notice(runtime_root=runtime_root, model_source=model_source)
    print("[drawai-setup] model download phase complete")


def bootstrap_local_runtime(
    *,
    repo_root: Path,
    runtime_root: Path,
    env: Mapping[str, str],
    dry_run: bool,
) -> None:
    runtime_python = runtime_venv_python(runtime_root)
    python_version = env.get("DRAWAI_LOCAL_RUNTIME_PYTHON") or DEFAULT_RUNTIME_PYTHON
    torch_spec = env.get("DRAWAI_TORCH_SPEC") or "torch>=2.4,<2.12"
    torchvision_spec = env.get("DRAWAI_TORCHVISION_SPEC") or "torchvision>=0.19,<0.27"
    torch_backend = env.get("DRAWAI_TORCH_BACKEND") or "cpu"
    torch_index_url = env.get("DRAWAI_TORCH_INDEX_URL") or ""
    skip_torch = env.get("DRAWAI_SKIP_TORCH_INSTALL") == "1"

    print(f"[drawai-setup] bootstrap runtime venv: {runtime_root / '.venv'} python={python_version}")
    if dry_run:
        _print_would_run(["uv", "venv", str(runtime_root / ".venv"), "--python", python_version, "--clear"])
        _print_seed_pip(runtime_python)
        _print_would_run(
            _pip_install_command(
                runtime_python,
                [
                    "paddlepaddle==3.2.0",
                    "--index-url",
                    "https://www.paddlepaddle.org.cn/packages/stable/cpu/",
                ],
            )
        )
        if skip_torch:
            _print_would_run([str(runtime_python), "-c", "import torch, torchvision"])
        else:
            torch_args = []
            if torch_index_url:
                torch_args.extend(["--index-url", torch_index_url])
            torch_args.extend([torch_spec, torchvision_spec])
            _print_would_run(_pip_install_command(runtime_python, torch_args, reinstall=bool(torch_index_url)))
            print(f"[drawai-setup] would install PyTorch backend: {torch_backend}")
        _print_would_run(_pip_install_command(runtime_python, ["-e", str(repo_root), "...runtime deps..."]))
        _print_would_run(_pip_install_command(runtime_python, ["openai-codex", "pydantic<2.14"], prerelease=True))
        print("[drawai-setup] would install SAM3 source and sync model artifacts")
        return

    runtime_root.mkdir(parents=True, exist_ok=True)
    (runtime_root / "models" / "sam3").mkdir(parents=True, exist_ok=True)
    (runtime_root / "models" / "paddlex" / "official_models").mkdir(parents=True, exist_ok=True)
    (runtime_root / "models" / "rmbg2").mkdir(parents=True, exist_ok=True)
    (runtime_root / "tools").mkdir(parents=True, exist_ok=True)

    setup_env = dict(env)
    _run_setup_command(
        ["uv", "venv", str(runtime_root / ".venv"), "--python", python_version, "--clear"],
        label="create runtime venv",
        cwd=repo_root,
        env=setup_env,
        monitor_paths=[runtime_root],
    )
    _seed_pip_if_needed(runtime_python, label="seed runtime pip", cwd=repo_root, env=setup_env, monitor_paths=[runtime_root])
    _run_setup_command(
        _pip_install_command(
            runtime_python,
            [
                "paddlepaddle==3.2.0",
                "--index-url",
                "https://www.paddlepaddle.org.cn/packages/stable/cpu/",
            ],
        ),
        label="install Paddle CPU runtime",
        cwd=repo_root,
        env=setup_env,
        monitor_paths=[runtime_root],
    )

    if skip_torch:
        print("[drawai-setup] skipping PyTorch install because DRAWAI_SKIP_TORCH_INSTALL=1")
        _run_setup_command(
            [str(runtime_python), "-c", "import torch, torchvision"],
            label="verify existing PyTorch runtime",
            cwd=repo_root,
            env=setup_env,
            monitor_paths=[runtime_root],
        )
    else:
        torch_args = []
        if torch_index_url:
            torch_args.extend(["--index-url", torch_index_url])
        torch_args.extend([torch_spec, torchvision_spec])
        print(f"[drawai-setup] PyTorch backend: {torch_backend}")
        if torch_index_url:
            print(f"[drawai-setup] PyTorch index: {torch_index_url}")
        _run_setup_command(
            _pip_install_command(runtime_python, torch_args, reinstall=bool(torch_index_url)),
            label="install PyTorch runtime",
            cwd=repo_root,
            env=setup_env,
            monitor_paths=[runtime_root],
        )

    _run_setup_command(
        _pip_install_command(
            runtime_python,
            [
                "-e",
                str(repo_root),
                "paddleocr==3.5.0",
                "paddlex==3.5.2",
                "transformers==4.57.6",
                "timm==1.0.27",
                "opencv-python-headless==4.11.0.86",
                "numpy==1.26.4",
                "einops",
                "kornia==0.8.2",
                "kornia-rs==0.1.11",
                "pycocotools",
                "scikit-image",
            ],
        ),
        label="install DrawAI runtime dependencies",
        cwd=repo_root,
        env=setup_env,
        monitor_paths=[runtime_root],
    )
    _run_setup_command(
        _pip_install_command(runtime_python, ["openai-codex", "pydantic<2.14"], prerelease=True),
        label="install Codex Python SDK",
        cwd=repo_root,
        env=setup_env,
        monitor_paths=[runtime_root],
    )

    _materialize_runtime_artifacts(runtime_root=runtime_root, env=setup_env)
    _run_setup_command(
        [str(runtime_python), "-c", "import openai_codex"],
        label="verify Codex Python SDK import",
        cwd=repo_root,
        env=setup_env,
        monitor_paths=[runtime_root],
    )
    _verify_runtime_files(runtime_root)
    print("[drawai-setup] runtime bootstrap complete")


def _ensure_download_helper(*, repo_root: Path, runtime_root: Path, env: Mapping[str, str]) -> Path:
    helper_venv = runtime_root / "tools" / "download_venv"
    helper_python = _venv_python(helper_venv)
    if helper_python.is_file() and _download_helper_imports_ok(helper_python):
        print(f"[drawai-setup] using model download helper: {helper_python}")
        return helper_python
    helper_venv.parent.mkdir(parents=True, exist_ok=True)
    _run_setup_command(
        ["uv", "venv", str(helper_venv), "--python", sys.executable, "--clear"],
        label="create model download helper venv",
        cwd=repo_root,
        env=dict(env),
        monitor_paths=[helper_venv],
    )
    _seed_pip_if_needed(helper_python, label="seed model download helper pip", cwd=repo_root, env=env, monitor_paths=[helper_venv])
    _run_setup_command(
        _pip_install_command(helper_python, ["modelscope", "pysocks", "huggingface-hub", "socksio"]),
        label="install model download helper dependencies",
        cwd=repo_root,
        env=dict(env),
        monitor_paths=[helper_venv],
    )
    return helper_python


def _download_helper_imports_ok(helper_python: Path) -> bool:
    completed = subprocess.run(
        [str(helper_python), "-c", "import modelscope, huggingface_hub"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return completed.returncode == 0


def _venv_python(venv: Path) -> Path:
    if os.name == "nt":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def _download_paddle_models(
    *,
    repo_root: Path,
    runtime_root: Path,
    model_source: str,
    env: Mapping[str, str],
    helper_python: Path,
) -> None:
    root = runtime_root / "models" / "paddlex" / "official_models"
    _download_model_snapshot(
        repo_root=repo_root,
        model_source=model_source,
        modelscope_repo_id=PADDLE_DET_MODELSCOPE_REPO,
        hf_repo_id=PADDLE_DET_HF_REPO,
        target_dir=root / "PP-OCRv5_server_det",
        patterns=("README.md", "config.json", "inference.json", "inference.pdiparams", "inference.yml"),
        env=env,
        label="download PaddleOCR detection model",
        helper_python=helper_python,
    )
    _download_model_snapshot(
        repo_root=repo_root,
        model_source=model_source,
        modelscope_repo_id=PADDLE_REC_MODELSCOPE_REPO,
        hf_repo_id=PADDLE_REC_HF_REPO,
        target_dir=root / "PP-OCRv5_server_rec",
        patterns=("README.md", "config.json", "inference.json", "inference.pdiparams", "inference.yml"),
        env=env,
        label="download PaddleOCR recognition model",
        helper_python=helper_python,
    )
    _require_file(root / "PP-OCRv5_server_det" / "inference.pdiparams")
    _require_file(root / "PP-OCRv5_server_rec" / "inference.pdiparams")


def _download_sam3_models(
    *,
    repo_root: Path,
    runtime_root: Path,
    model_source: str,
    accept_sam3_license: bool,
    env: Mapping[str, str],
    helper_python: Path,
) -> None:
    if model_source == "huggingface" and not accept_sam3_license:
        raise ValueError("SAM3 Hugging Face download requires --accept-sam3-license.")
    if model_source == "modelscope":
        print(f"[drawai-setup] SAM3 artifacts are subject to upstream terms: https://modelscope.cn/models/{SAM3_MODELSCOPE_REPO}")
    source_repo = env.get("DRAWAI_SAM3_SOURCE_REPO") or SAM3_SOURCE_REPO
    source_dir = runtime_root / "source" / "sam3"
    _sync_sam3_source(repo_root=repo_root, source_repo=source_repo, target_dir=source_dir, env=env)
    _download_model_snapshot(
        repo_root=repo_root,
        model_source=model_source,
        modelscope_repo_id=SAM3_MODELSCOPE_REPO,
        hf_repo_id=SAM3_HF_REPO,
        target_dir=runtime_root / "models" / "sam3",
        patterns=("LICENSE", "README.md", "sam3.pt"),
        env=env,
        label="download SAM3 checkpoint",
        helper_python=helper_python,
    )
    source_bpe = source_dir / "sam3" / "assets" / "bpe_simple_vocab_16e6.txt.gz"
    target_bpe = runtime_root / "models" / "sam3" / "bpe_simple_vocab_16e6.txt.gz"
    if source_bpe.is_file():
        print(f"[drawai-setup] syncing SAM3 BPE vocab: {source_bpe} -> {target_bpe}")
        _copy_file(source_bpe, target_bpe)
    else:
        _download_url(SAM3_BPE_URL, target_bpe, label="download SAM3 BPE vocab")
    _require_file(runtime_root / "models" / "sam3" / "sam3.pt")
    _require_file(target_bpe)


def _download_rmbg_models(
    *,
    repo_root: Path,
    runtime_root: Path,
    model_source: str,
    env: Mapping[str, str],
    helper_python: Path,
) -> None:
    _download_model_snapshot(
        repo_root=repo_root,
        model_source=model_source,
        modelscope_repo_id=RMBG_MODELSCOPE_REPO,
        hf_repo_id=RMBG_HF_REPO,
        target_dir=runtime_root / "models" / "rmbg2",
        patterns=(
            "README.md",
            "config.json",
            "preprocessor_config.json",
            "BiRefNet_config.py",
            "birefnet.py",
            "model.safetensors",
        ),
        env=env,
        label="download RMBG-2.0 model",
        helper_python=helper_python,
    )
    _require_file(runtime_root / "models" / "rmbg2" / "model.safetensors")
    _require_file(runtime_root / "models" / "rmbg2" / "config.json")
    _require_file(runtime_root / "models" / "rmbg2" / "birefnet.py")


def _download_model_snapshot(
    *,
    repo_root: Path,
    model_source: str,
    modelscope_repo_id: str,
    hf_repo_id: str,
    target_dir: Path,
    patterns: Sequence[str],
    env: Mapping[str, str],
    label: str,
    helper_python: Path,
) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    if model_source == "modelscope":
        code = _modelscope_snapshot_code()
        command = [
            str(helper_python),
            "-c",
            code,
            modelscope_repo_id,
            str(target_dir),
            *patterns,
        ]
    elif model_source == "huggingface":
        _print_hf_access_hint(env)
        code = _huggingface_snapshot_code()
        command = [
            str(helper_python),
            "-c",
            code,
            hf_repo_id,
            str(target_dir),
            *patterns,
        ]
    else:
        raise ValueError(f"Unsupported model source: {model_source!r}")
    _run_setup_command(command, label=label, cwd=repo_root, env=dict(env), monitor_paths=[target_dir])


def _modelscope_snapshot_code() -> str:
    return textwrap.dedent(
        """
        from __future__ import annotations
        import sys
        from modelscope import snapshot_download

        repo_id = sys.argv[1]
        target_dir = sys.argv[2]
        allow_patterns = sys.argv[3:] or None
        snapshot_download(repo_id, local_dir=target_dir, allow_file_pattern=allow_patterns)
        """
    ).strip()


def _huggingface_snapshot_code() -> str:
    return textwrap.dedent(
        """
        from __future__ import annotations
        import os
        import sys
        from huggingface_hub import snapshot_download
        from huggingface_hub.errors import GatedRepoError

        repo_id = sys.argv[1]
        target_dir = sys.argv[2]
        allow_patterns = sys.argv[3:] or None
        token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN") or os.environ.get("HUGGINGFACE_HUB_TOKEN")
        try:
            snapshot_download(repo_id=repo_id, local_dir=target_dir, allow_patterns=allow_patterns, token=token)
        except GatedRepoError as exc:
            lines = [line for line in str(exc).splitlines() if line.strip()]
            print(f"Cannot access gated Hugging Face repo: {repo_id}", file=sys.stderr)
            print(lines[-1] if lines else type(exc).__name__, file=sys.stderr)
            sys.exit(17)
        """
    ).strip()


def _sync_sam3_source(*, repo_root: Path, source_repo: str, target_dir: Path, env: Mapping[str, str]) -> None:
    if (target_dir / ".git").is_dir():
        _run_setup_command(
            ["git", "-C", str(target_dir), "fetch", "--depth", "1", "origin", "main"],
            label="update SAM3 source",
            cwd=repo_root,
            env=dict(env),
            monitor_paths=[target_dir],
        )
        _run_setup_command(
            ["git", "-C", str(target_dir), "checkout", "--quiet", "FETCH_HEAD"],
            label="checkout SAM3 source",
            cwd=repo_root,
            env=dict(env),
            monitor_paths=[target_dir],
        )
        return
    if target_dir.exists():
        raise RuntimeError(f"SAM3 source target exists but is not a git checkout: {target_dir}")
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    _run_setup_command(
        ["git", "clone", "--depth", "1", source_repo, str(target_dir)],
        label="clone SAM3 source",
        cwd=repo_root,
        env=dict(env),
        monitor_paths=[target_dir.parent],
    )


def _download_url(url: str, target: Path, *, label: str) -> None:
    print(f"[drawai-setup] {label}: {url} -> {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    last_report = started
    last_bytes = 0
    total_bytes = 0
    request = urllib.request.Request(url, headers={"User-Agent": "DrawAI setup"})
    with urllib.request.urlopen(request, timeout=600) as response:
        expected = int(response.headers.get("Content-Length") or "0")
        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as handle:
            temp_path = Path(handle.name)
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
                total_bytes += len(chunk)
                now = time.monotonic()
                if now - last_report >= DIRECT_DOWNLOAD_HEARTBEAT_SECONDS:
                    interval = now - last_report
                    current_rate = (total_bytes - last_bytes) / max(interval, 0.001)
                    average_rate = total_bytes / max(now - started, 0.001)
                    suffix = f" / {_format_bytes(expected)}" if expected else ""
                    print(
                        f"[drawai-setup] {label}: {_format_bytes(total_bytes)}{suffix} "
                        f"current={_format_rate(current_rate)} avg={_format_rate(average_rate)}",
                        flush=True,
                    )
                    last_report = now
                    last_bytes = total_bytes
    temp_path.replace(target)
    elapsed = time.monotonic() - started
    print(
        f"[drawai-setup] {label}: done {_format_bytes(total_bytes)} "
        f"in {_format_duration(elapsed)} avg={_format_rate(total_bytes / max(elapsed, 0.001))}"
    )


def _materialize_runtime_artifacts(*, runtime_root: Path, env: Mapping[str, str]) -> None:
    runtime_sam3_source = runtime_root / "source" / "sam3"
    sam3_source = Path(env.get("DRAWAI_SAM3_SOURCE") or runtime_sam3_source).expanduser().resolve(strict=False)
    if sam3_source != runtime_sam3_source.resolve(strict=False):
        print(f"[drawai-setup] syncing manual SAM3 source: {sam3_source} -> {runtime_sam3_source}")
        _sync_dir_contents(sam3_source, runtime_sam3_source)
    if not runtime_sam3_source.is_dir():
        raise FileNotFoundError(
            "Missing DRAWAI_SAM3_SOURCE for the facebookresearch/sam3 source checkout. "
            "Set it to a local path, or run setup without --bootstrap-only first."
        )

    runtime_python = runtime_venv_python(runtime_root)
    _run_setup_command(
        _pip_install_command(runtime_python, ["-e", str(runtime_sam3_source)]),
        label="install SAM3 source",
        cwd=runtime_root,
        env=dict(env),
        monitor_paths=[runtime_root],
    )

    sam3_checkpoint = Path(env.get("DRAWAI_SAM3_CHECKPOINT_SOURCE") or runtime_root / "models" / "sam3" / "sam3.pt").expanduser()
    sam3_bpe = Path(env.get("DRAWAI_SAM3_BPE_SOURCE") or runtime_root / "models" / "sam3" / "bpe_simple_vocab_16e6.txt.gz").expanduser()
    print("[drawai-setup] syncing SAM3 checkpoint and BPE")
    _copy_file(sam3_checkpoint, runtime_root / "models" / "sam3" / "sam3.pt")
    _copy_file(sam3_bpe, runtime_root / "models" / "sam3" / "bpe_simple_vocab_16e6.txt.gz")

    paddle_source = Path(
        env.get("DRAWAI_PADDLE_MODELS_SOURCE") or runtime_root / "models" / "paddlex" / "official_models"
    ).expanduser()
    print("[drawai-setup] syncing PaddleOCR PP-OCRv5 server models")
    _sync_named_dir(paddle_source / "PP-OCRv5_server_det", runtime_root / "models" / "paddlex" / "official_models")
    _sync_named_dir(paddle_source / "PP-OCRv5_server_rec", runtime_root / "models" / "paddlex" / "official_models")

    rmbg_source = Path(env.get("DRAWAI_RMBG_SOURCE") or runtime_root / "models" / "rmbg2").expanduser()
    print("[drawai-setup] syncing RMBG-2.0")
    _sync_dir_contents(rmbg_source, runtime_root / "models" / "rmbg2")

    gateway_source = env.get("DRAWAI_LOCAL_CODEX_GATEWAY_SOURCE") or ""
    if gateway_source:
        print("[drawai-setup] syncing optional local Codex OpenAI gateway")
        _sync_dir_contents(Path(gateway_source).expanduser(), runtime_root / "tools" / "local-codex-openai-gateway")
    else:
        print("[drawai-setup] skipping optional local Codex OpenAI gateway; Codex Python SDK is the default SVG backend")


def _sync_named_dir(source: Path, target_parent: Path) -> None:
    if not source.is_dir():
        raise FileNotFoundError(f"Required model directory not found: {source}")
    _sync_dir_contents(source, target_parent / source.name)


def _sync_dir_contents(source: Path, target: Path) -> None:
    source = source.expanduser().resolve(strict=False)
    target = target.expanduser().resolve(strict=False)
    if source == target:
        return
    if not source.is_dir():
        raise FileNotFoundError(f"Required directory not found: {source}")
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        if item.name in {".msc", ".mv", "._____temp"}:
            continue
        destination = target / item.name
        if item.is_dir():
            shutil.copytree(item, destination, ignore=shutil.ignore_patterns(".msc", ".mv", "._____temp"))
        else:
            shutil.copy2(item, destination)


def _copy_file(source: Path, target: Path) -> None:
    source = source.expanduser().resolve(strict=False)
    target = target.expanduser().resolve(strict=False)
    if source == target and target.exists():
        return
    if not source.is_file():
        raise FileNotFoundError(f"Required file not found: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def _verify_runtime_files(runtime_root: Path) -> None:
    for path in (
        runtime_root / "models" / "sam3" / "sam3.pt",
        runtime_root / "models" / "sam3" / "bpe_simple_vocab_16e6.txt.gz",
        runtime_root / "models" / "paddlex" / "official_models" / "PP-OCRv5_server_det" / "inference.pdiparams",
        runtime_root / "models" / "paddlex" / "official_models" / "PP-OCRv5_server_rec" / "inference.pdiparams",
        runtime_root / "models" / "rmbg2" / "model.safetensors",
    ):
        _require_file(path)


def _write_model_sources_notice(*, runtime_root: Path, model_source: str) -> None:
    notice = runtime_root / "MODEL_SOURCES.md"
    notice.write_text(
        textwrap.dedent(
            f"""
            # DrawAI Local Runtime Model Sources

            This directory contains locally downloaded model artifacts for DrawAI. Do not
            commit these files to git.

            - Download source: {model_source}
            - PaddleOCR detection: {_model_snapshot_url(model_source, PADDLE_DET_MODELSCOPE_REPO, PADDLE_DET_HF_REPO)} (Apache-2.0)
            - PaddleOCR recognition: {_model_snapshot_url(model_source, PADDLE_REC_MODELSCOPE_REPO, PADDLE_REC_HF_REPO)} (Apache-2.0)
            - SAM3: {_model_snapshot_url(model_source, SAM3_MODELSCOPE_REPO, SAM3_HF_REPO)} and {SAM3_SOURCE_REPO} (Meta SAM License)
            - SAM3 BPE vocab: {SAM3_SOURCE_REPO} source checkout; fallback URL {SAM3_BPE_URL}
            - RMBG-2.0: {_model_snapshot_url(model_source, RMBG_MODELSCOPE_REPO, RMBG_HF_REPO)} (BRIA RMBG-2.0 / CC BY-NC 4.0 terms on the model card)

            Review the upstream licenses and access terms before using these artifacts in a
            redistributed, hosted, or commercial environment.
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )


def _model_snapshot_url(model_source: str, modelscope_repo_id: str, hf_repo_id: str) -> str:
    if model_source == "modelscope":
        return f"https://modelscope.cn/models/{modelscope_repo_id}"
    return f"https://huggingface.co/{hf_repo_id}"


def _print_hf_access_hint(env: Mapping[str, str]) -> None:
    if env.get("HF_TOKEN") or env.get("HUGGING_FACE_HUB_TOKEN") or env.get("HUGGINGFACE_HUB_TOKEN"):
        return
    print("[drawai-setup] HF_TOKEN is not set; gated downloads will rely on any existing Hugging Face CLI login.")


def _run_setup_command(
    command: Sequence[str],
    *,
    label: str,
    cwd: Path,
    env: Mapping[str, str],
    monitor_paths: Sequence[Path],
) -> None:
    print(f"[drawai-setup] starting {label}: {_command_text(command)}", flush=True)
    start = time.monotonic()
    baseline_size = _paths_size(monitor_paths)
    last_report = start
    process = subprocess.Popen(list(command), cwd=cwd, env=dict(env))
    while True:
        returncode = process.poll()
        now = time.monotonic()
        if now - last_report >= SETUP_HEARTBEAT_SECONDS:
            elapsed = now - start
            size_delta = max(0, _paths_size(monitor_paths) - baseline_size)
            print(
                f"[drawai-setup] {label}: elapsed={_format_duration(elapsed)} "
                f"target+={_format_bytes(size_delta)} avg={_format_rate(size_delta / max(elapsed, 0.001))}",
                flush=True,
            )
            last_report = now
        if returncode is not None:
            elapsed = time.monotonic() - start
            size_delta = max(0, _paths_size(monitor_paths) - baseline_size)
            if returncode != 0:
                raise subprocess.CalledProcessError(returncode, list(command))
            print(
                f"[drawai-setup] finished {label}: elapsed={_format_duration(elapsed)} "
                f"target+={_format_bytes(size_delta)} avg={_format_rate(size_delta / max(elapsed, 0.001))}",
                flush=True,
            )
            return
        time.sleep(0.5)


def _seed_pip_if_needed(
    python: Path,
    *,
    label: str,
    cwd: Path,
    env: Mapping[str, str],
    monitor_paths: Sequence[Path],
) -> None:
    if os.name != "nt":
        return
    _run_setup_command(
        [str(python), "-m", "ensurepip", "--upgrade"],
        label=label,
        cwd=cwd,
        env=env,
        monitor_paths=monitor_paths,
    )


def _print_seed_pip(python: Path) -> None:
    if os.name == "nt":
        _print_would_run([str(python), "-m", "ensurepip", "--upgrade"])


def _pip_install_command(
    python: Path,
    args: Sequence[str],
    *,
    prerelease: bool = False,
    reinstall: bool = False,
) -> list[str]:
    if os.name == "nt":
        command = [str(python), "-m", "pip", "install"]
        if prerelease:
            command.append("--pre")
        if reinstall:
            command.append("--force-reinstall")
        command.extend(args)
        return command
    command = ["uv", "pip", "install", "--python", str(python)]
    if prerelease:
        command.append("--prerelease=allow")
    if reinstall:
        command.extend(["--reinstall-package", "torch", "--reinstall-package", "torchvision"])
    command.extend(args)
    return command


def _paths_size(paths: Iterable[Path]) -> int:
    total = 0
    for path in paths:
        total += _path_size(path)
    return total


def _path_size(path: Path) -> int:
    try:
        if path.is_file():
            return path.stat().st_size
        if not path.exists():
            return 0
        total = 0
        for child in path.rglob("*"):
            try:
                if child.is_file():
                    total += child.stat().st_size
            except OSError:
                continue
        return total
    except OSError:
        return 0


def _format_bytes(value: float) -> str:
    units = ("B", "KB", "MB", "GB", "TB")
    amount = float(value)
    for unit in units:
        if abs(amount) < 1024.0 or unit == units[-1]:
            if unit == "B":
                return f"{amount:.0f} {unit}"
            return f"{amount:.1f} {unit}"
        amount /= 1024.0
    return f"{amount:.1f} TB"


def _format_rate(bytes_per_second: float) -> str:
    return f"{_format_bytes(bytes_per_second)}/s"


def _format_duration(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h{minutes:02d}m{sec:02d}s"
    if minutes:
        return f"{minutes}m{sec:02d}s"
    return f"{sec}s"


def _command_text(command: Sequence[str]) -> str:
    return " ".join(str(part) for part in command)


def _print_would_run(command: Sequence[str]) -> None:
    print(f"[drawai-setup] would run: {_command_text(command)}")


def _require_file(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"Expected file is missing: {path}")
