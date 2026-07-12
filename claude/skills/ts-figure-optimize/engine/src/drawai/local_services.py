from __future__ import annotations

import argparse
import asyncio
import base64
import binascii
import io
import os
import secrets
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException
from PIL import Image, UnidentifiedImageError

from .device_profiles import DEFAULT_LOCAL_DEVICE, LOCAL_DEVICE_CHOICES, resolve_local_model_devices
from .http_utils import DEFAULT_MODEL_BUSY_RETRY_AFTER_SECONDS, model_busy_headers
from .local_runtime import (
    DEFAULT_LOCAL_OCR_DET_LIMIT_SIDE_LEN,
    LocalPaddleOcrProvider,
    LocalRmbgClient,
    LocalRuntimePaths,
    LocalSam3Transport,
)
from .ocr_provider import OCR_BOXES_ENDPOINT, OcrBoxProvider
from .rmbg_client import RMBG_REMOVE_BACKGROUND_PATH
from .sam3_client import SAM3_PROPOSALS_PATH, JsonTransport

MODEL_NAMES = ("sam3", "ocr", "rmbg")


@dataclass(frozen=True)
class LocalServiceSettings:
    runtime_root: Path
    host: str = "127.0.0.1"
    sam_port: int = 18080
    ocr_port: int = 18080
    sam3_device: str = "cpu"
    rmbg_device: str = "cpu"
    paddle_device: str = "cpu"
    ocr_det_limit_side_len: int | None = DEFAULT_LOCAL_OCR_DET_LIMIT_SIDE_LEN
    log_level: str = "info"
    models: tuple[str, ...] = MODEL_NAMES


def create_local_services_app(
    *,
    settings: LocalServiceSettings,
    sam3_transport: JsonTransport | None = None,
    ocr_provider: OcrBoxProvider | None = None,
    rmbg_client: Any | None = None,
) -> FastAPI:
    paths = LocalRuntimePaths.from_root(settings.runtime_root)
    active_sam3 = sam3_transport or LocalSam3Transport(paths=paths, device=settings.sam3_device)
    active_ocr = ocr_provider or LocalPaddleOcrProvider(
        paths=paths,
        device=settings.paddle_device,
        text_det_limit_side_len=settings.ocr_det_limit_side_len,
    )
    active_rmbg = rmbg_client or LocalRmbgClient(paths=paths, device=settings.rmbg_device)
    app = FastAPI(title="DrawAI Local Runtime Services", version="0.1.0")
    app.state.settings = settings
    app.state.local_runtime_paths = paths
    app.state.sam3_transport = active_sam3
    app.state.ocr_provider = active_ocr
    app.state.rmbg_client = active_rmbg
    app.state.sam_lock = threading.Lock()
    app.state.ocr_lock = threading.Lock()
    app.state.rmbg_lock = threading.Lock()
    enabled_models = frozenset(settings.models)

    @app.get("/health")
    @app.get("/v1/health")
    def health() -> dict[str, Any]:
        services = {}
        if "sam3" in enabled_models:
            services["sam3"] = {
                "endpoint": SAM3_PROPOSALS_PATH,
                "port": settings.sam_port,
                "device": settings.sam3_device,
            }
        if "ocr" in enabled_models:
            services["ocr"] = {
                "endpoint": OCR_BOXES_ENDPOINT,
                "port": settings.ocr_port,
                "device": settings.paddle_device,
            }
        if "rmbg" in enabled_models:
            services["rmbg"] = {
                "endpoint": RMBG_REMOVE_BACKGROUND_PATH,
                "port": settings.sam_port,
                "device": settings.rmbg_device,
            }
        return {
            "status": "ok",
            "runtime_root": str(paths.runtime_root),
            "services": services,
        }

    @app.post(SAM3_PROPOSALS_PATH)
    def segment_proposals(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        _require_enabled(enabled_models, "sam3")
        _acquire_model_lock(app.state.sam_lock, "sam3")
        try:
            response, elapsed_ms = app.state.sam3_transport.post_json(SAM3_PROPOSALS_PATH, payload, timeout_s=0.0)
        finally:
            app.state.sam_lock.release()
        response["elapsed_ms"] = response.get("elapsed_ms", elapsed_ms)
        return response

    @app.post(OCR_BOXES_ENDPOINT)
    def ocr_boxes(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        _require_enabled(enabled_models, "ocr")
        _acquire_model_lock(app.state.ocr_lock, "ocr")
        try:
            image_path = _write_request_image(paths, payload)
            return app.state.ocr_provider.extract_boxes(image_path)
        finally:
            app.state.ocr_lock.release()

    @app.post(RMBG_REMOVE_BACKGROUND_PATH)
    def remove_background(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        _require_enabled(enabled_models, "rmbg")
        image = _load_request_image(payload, field="image_base64")
        output_name = _safe_filename(str(payload.get("output_name") or "rmbg.png"))
        timeout_s = float(payload.get("timeout_s") or 0.0)
        model_path = str(payload.get("model_path") or "")
        artifact_prefix = payload.get("artifact_prefix")
        with app.state.rmbg_lock:
            result = app.state.rmbg_client.remove_background(
                image,
                output_name,
                timeout_s=timeout_s,
                model_path=model_path,
                artifact_prefix=str(artifact_prefix) if artifact_prefix is not None else None,
            )
        return {
            "image_base64": _encode_png_base64(result.image),
            "artifacts": result.artifacts,
            "elapsed_ms": result.elapsed_ms,
        }

    return app


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    reexec_error = _maybe_reexec_into_runtime_venv(args, argv)
    if reexec_error:
        print(reexec_error, file=sys.stderr)
        return 2
    settings = LocalServiceSettings(
        runtime_root=Path(args.runtime_root).expanduser().resolve(strict=False),
        host=args.host,
        sam_port=args.sam_port,
        ocr_port=args.ocr_port,
        sam3_device=args.sam3_device,
        rmbg_device=args.rmbg_device,
        paddle_device=args.paddle_device,
        ocr_det_limit_side_len=args.ocr_det_limit_side_len if args.ocr_det_limit_side_len > 0 else None,
        log_level=args.log_level,
        models=_normalize_models(args.models),
    )
    paths = LocalRuntimePaths.from_root(settings.runtime_root)
    try:
        _validate_service_paths(
            paths,
            require_sam="sam3" in settings.models,
            require_ocr="ocr" in settings.models,
            require_rmbg="rmbg" in settings.models,
        )
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    app = create_local_services_app(settings=settings)
    asyncio.run(_serve(app, settings))
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run local DrawAI SAM3, OCR, and RMBG HTTP services.")
    parser.add_argument("models", nargs="*", choices=MODEL_NAMES, help="Model services to enable. Defaults to sam3 ocr rmbg.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--sam-port", type=int, default=18080)
    parser.add_argument("--ocr-port", type=int, default=18080)
    parser.add_argument("--runtime-root", default=".local/drawai_runtime")
    parser.add_argument(
        "--device",
        choices=LOCAL_DEVICE_CHOICES,
        default=os.environ.get("DRAWAI_DEVICE", DEFAULT_LOCAL_DEVICE),
        help="Local runtime device profile. Default: cpu. gpu maps Torch models to cuda; mps maps RMBG to mps.",
    )
    parser.add_argument("--sam3-device", default=os.environ.get("DRAWAI_SAM3_DEVICE", ""))
    parser.add_argument("--rmbg-device", default=os.environ.get("DRAWAI_RMBG_DEVICE", ""))
    parser.add_argument("--paddle-device", default=os.environ.get("DRAWAI_PADDLE_DEVICE", ""))
    parser.add_argument("--ocr-det-limit-side-len", type=int, default=DEFAULT_LOCAL_OCR_DET_LIMIT_SIDE_LEN)
    parser.add_argument("--log-level", default="info")
    args = parser.parse_args(argv)
    devices = resolve_local_model_devices(
        args.device,
        sam3_device=args.sam3_device,
        rmbg_device=args.rmbg_device,
        paddle_device=args.paddle_device,
    )
    args.sam3_device = devices.sam3_device
    args.rmbg_device = devices.rmbg_device
    args.paddle_device = devices.paddle_device
    return args


def _normalize_models(models: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    selected = tuple(dict.fromkeys(models or MODEL_NAMES))
    if not selected:
        return MODEL_NAMES
    return selected


def _require_enabled(enabled_models: frozenset[str], model: str) -> None:
    if model not in enabled_models:
        raise HTTPException(status_code=404, detail=f"{model} service is not enabled")


def _acquire_model_lock(lock: threading.Lock, model: str) -> None:
    if lock.acquire(blocking=False):
        return
    raise HTTPException(
        status_code=503,
        detail={
            "code": "model_busy",
            "model": model,
            "message": f"{model} is busy; retry later.",
            "retry_after_seconds": DEFAULT_MODEL_BUSY_RETRY_AFTER_SECONDS,
        },
        headers=model_busy_headers(),
    )


def _maybe_reexec_into_runtime_venv(args: argparse.Namespace, argv: list[str] | None) -> str:
    if (
        os.environ.get("DRAWAI_LOCAL_RUNTIME_REEXEC") == "1"
        or os.environ.get("DRAWAI_SKIP_LOCAL_RUNTIME_REEXEC") == "1"
    ):
        return ""
    runtime_root = Path(args.runtime_root).expanduser().resolve(strict=False)
    runtime_venv = runtime_root / ".venv"
    if Path(sys.prefix).resolve(strict=False) == runtime_venv.resolve(strict=False):
        return ""
    runtime_python = _runtime_venv_python(runtime_root)
    if not runtime_python.exists():
        return (
            f"Local DrawAI runtime Python not found: {runtime_python}. "
            "Run: uv run drawai setup local --bootstrap-only"
        )
    env = dict(os.environ)
    env["DRAWAI_LOCAL_RUNTIME_REEXEC"] = "1"
    env["DRAWAI_LOCAL_RUNTIME_ROOT"] = str(runtime_root)
    exec_argv = list(argv) if argv is not None else sys.argv[1:]
    os.execve(str(runtime_python), [str(runtime_python), "-m", "drawai.local_services", *exec_argv], env)
    raise AssertionError("os.execve returned unexpectedly")


def _runtime_venv_python(runtime_root: Path) -> Path:
    if os.name == "nt":
        return runtime_root / ".venv" / "Scripts" / "python.exe"
    return runtime_root / ".venv" / "bin" / "python"


async def _serve(app: FastAPI, settings: LocalServiceSettings) -> None:
    import uvicorn

    ports = [settings.sam_port]
    if settings.ocr_port != settings.sam_port:
        ports.append(settings.ocr_port)
    servers = [
        uvicorn.Server(
            uvicorn.Config(
                app,
                host=settings.host,
                port=port,
                log_level=settings.log_level,
            )
        )
        for port in ports
    ]
    await asyncio.gather(*(server.serve() for server in servers))


def _validate_service_paths(paths: LocalRuntimePaths, *, require_sam: bool, require_ocr: bool, require_rmbg: bool) -> None:
    missing: list[Path] = []
    if require_sam:
        missing.extend(path for path in (paths.sam3_checkpoint, paths.sam3_bpe) if not path.exists())
    if require_rmbg:
        missing.extend(path for path in (paths.rmbg_model_dir / "model.safetensors",) if not path.exists())
    if require_ocr:
        missing.extend(
            path
            for path in (
                paths.paddlex_official_models / "PP-OCRv5_server_det" / "inference.pdiparams",
                paths.paddlex_official_models / "PP-OCRv5_server_rec" / "inference.pdiparams",
            )
            if not path.exists()
        )
    if missing:
        details = "\n".join(str(path) for path in missing)
        raise FileNotFoundError(f"Local DrawAI service runtime is missing required model files:\n{details}")


def _load_request_image(payload: dict[str, Any], *, field: str) -> Image.Image:
    image_base64 = payload.get(field)
    if not isinstance(image_base64, str) or not image_base64.strip():
        raise HTTPException(status_code=400, detail=f"request missing required {field} field")
    image_bytes = _decode_base64_image(image_base64)
    try:
        return Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    except (UnidentifiedImageError, OSError) as exc:
        raise HTTPException(status_code=400, detail=f"request {field} is not a valid image") from exc


def _write_request_image(paths: LocalRuntimePaths, payload: dict[str, Any]) -> Path:
    image_base64 = payload.get("image_base64")
    if not isinstance(image_base64, str) or not image_base64.strip():
        raise HTTPException(status_code=400, detail="OCR request missing required image_base64 field")
    image_bytes = _decode_base64_image(image_base64)
    filename = _safe_filename(str(payload.get("filename") or "ocr.png"))
    request_dir = paths.artifacts_root / "ocr_service" / time.strftime("%Y%m%d")
    request_dir.mkdir(parents=True, exist_ok=True)
    target = request_dir / f"{time.strftime('%H%M%S')}_{secrets.token_hex(4)}_{filename}"
    target.write_bytes(image_bytes)
    return target


def _decode_base64_image(value: str) -> bytes:
    data = value.split(",", 1)[1] if "," in value else value
    try:
        return base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=400, detail="request image_base64 is not valid base64") from exc


def _encode_png_base64(image: Image.Image) -> str:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _safe_filename(value: str) -> str:
    name = Path(value).name.replace("/", "_").replace("\\", "_").strip("._")
    return name or "ocr.png"


if __name__ == "__main__":
    raise SystemExit(main())
