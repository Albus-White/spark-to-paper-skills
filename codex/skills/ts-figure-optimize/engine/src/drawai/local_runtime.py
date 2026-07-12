from __future__ import annotations

import base64
import gc
import importlib.util
import io
import json
import math
import os
import shutil
import sys
import time
import types
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from PIL import Image, ImageDraw, ImageFont

from ._local_runtime_fs import create_windows_junction as _create_windows_junction
from .ocr_provider import normalize_ocr_boxes_payload
from .rmbg_client import RmbgResult


DEFAULT_PROJECT_ROOT = Path.cwd()
DEFAULT_RUNTIME_ROOT = DEFAULT_PROJECT_ROOT / ".local" / "drawai_runtime"
DEFAULT_DET_BOX_THRESH = 0.75
DEFAULT_REC_SCORE_THRESH = 0.85
DEFAULT_LOCAL_OCR_DET_LIMIT_SIDE_LEN = 1280


@dataclass(frozen=True)
class LocalRuntimePaths:
    runtime_root: Path = DEFAULT_RUNTIME_ROOT

    @property
    def models_root(self) -> Path:
        return self.runtime_root / "models"

    @property
    def sam3_checkpoint(self) -> Path:
        return self.models_root / "sam3" / "sam3.pt"

    @property
    def sam3_bpe(self) -> Path:
        return self.models_root / "sam3" / "bpe_simple_vocab_16e6.txt.gz"

    @property
    def rmbg_model_dir(self) -> Path:
        return self.models_root / "rmbg2"

    @property
    def paddlex_official_models(self) -> Path:
        return self.models_root / "paddlex" / "official_models"

    @property
    def paddle_home(self) -> Path:
        return self.runtime_root / "paddle_home"

    @property
    def artifacts_root(self) -> Path:
        return self.runtime_root / "artifacts"

    @classmethod
    def from_root(cls, runtime_root: str | Path | None = None) -> "LocalRuntimePaths":
        root = Path(runtime_root or os.environ.get("DRAWAI_LOCAL_RUNTIME_ROOT") or DEFAULT_RUNTIME_ROOT)
        return cls(runtime_root=root.expanduser().resolve())

    def validate(self) -> None:
        required_paths = [
            self.sam3_checkpoint,
            self.sam3_bpe,
            self.rmbg_model_dir / "model.safetensors",
            self.paddlex_official_models / "PP-OCRv5_server_det" / "inference.pdiparams",
            self.paddlex_official_models / "PP-OCRv5_server_rec" / "inference.pdiparams",
        ]
        missing = [path for path in required_paths if not path.exists()]
        if missing:
            details = "\n".join(str(path) for path in missing)
            raise FileNotFoundError(f"Local DrawAI runtime is missing required model files:\n{details}")


@dataclass(frozen=True)
class LocalRuntimeComponents:
    sam3_transport: "LocalSam3Transport"
    ocr_provider: "LocalPaddleOcrProvider"
    rmbg_client: "LocalRmbgClient"


def build_local_runtime_components(
    *,
    runtime_root: str | Path | None = None,
    sam3_device: str = "cpu",
    rmbg_device: str = "cpu",
    paddle_device: str = "cpu",
    ocr_det_limit_side_len: int | None = DEFAULT_LOCAL_OCR_DET_LIMIT_SIDE_LEN,
) -> LocalRuntimeComponents:
    paths = LocalRuntimePaths.from_root(runtime_root)
    paths.validate()
    return LocalRuntimeComponents(
        sam3_transport=LocalSam3Transport(paths=paths, device=sam3_device),
        ocr_provider=LocalPaddleOcrProvider(
            paths=paths,
            device=paddle_device,
            text_det_limit_side_len=ocr_det_limit_side_len,
        ),
        rmbg_client=LocalRmbgClient(paths=paths, device=rmbg_device),
    )


class LocalSam3Transport:
    def __init__(self, *, paths: LocalRuntimePaths, device: str = "cpu") -> None:
        self.paths = paths
        self.device = device
        self._processor: Any | None = None

    def post_json(self, path: str, payload: dict[str, Any], timeout_s: float) -> tuple[dict[str, Any], float]:
        if path.rstrip("/") != "/v1/segment/proposals":
            raise ValueError(f"Unsupported local SAM3 endpoint: {path!r}")
        started = time.monotonic()
        image = _load_sam_image(payload)
        job_prefix = str(payload.get("artifact_prefix") or "sam3").strip() or "sam3"
        job_id = f"{_safe_job_prefix(job_prefix)}_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        output_dir = self.paths.artifacts_root / "sam3" / job_id
        output_dir.mkdir(parents=True, exist_ok=True)
        image.save(output_dir / "input.png")
        result = self._run_segmentation(payload, image, output_dir)
        elapsed_ms = (time.monotonic() - started) * 1000
        return result, elapsed_ms

    def _processor_runtime(self) -> Any:
        if self._processor is not None:
            return self._processor

        install_sam3_edt_fallback_if_needed()
        import sam3.model.vitdet as sam3_vitdet
        import torch
        from sam3.model.sam3_image_processor import Sam3Processor
        from sam3.model_builder import build_sam3_image_model

        def _safe_sam3_addmm_act(activation: Any, linear: Any, mat1: Any) -> Any:
            output = linear(mat1)
            if activation in (torch.nn.functional.relu, torch.nn.ReLU):
                return torch.nn.functional.relu(output)
            if activation in (torch.nn.functional.gelu, torch.nn.GELU):
                return torch.nn.functional.gelu(output)
            raise ValueError(f"Unexpected SAM3 activation {activation}")

        sam3_vitdet.addmm_act = _safe_sam3_addmm_act
        device = _resolve_sam3_torch_device(self.device)
        with _sam3_torch_runtime_device_patch(torch, device):
            model = build_sam3_image_model(
                device=device,
                bpe_path=str(self.paths.sam3_bpe),
                checkpoint_path=str(self.paths.sam3_checkpoint),
                load_from_HF=False,
            )
            self._processor = Sam3Processor(model, device=device)
        return self._processor

    def release_runtime(self) -> None:
        self._processor = None
        gc.collect()
        _empty_torch_cache()

    def _run_segmentation(self, payload: Mapping[str, Any], image: Image.Image, output_dir: Path) -> dict[str, Any]:
        import torch

        device = _resolve_sam3_torch_device(self.device)
        with _sam3_torch_runtime_device_patch(torch, device):
            return self._run_segmentation_impl(payload, image, output_dir)

    def _run_segmentation_impl(self, payload: Mapping[str, Any], image: Image.Image, output_dir: Path) -> dict[str, Any]:
        processor = self._processor_runtime()
        specs = _normalize_sam_prompt_specs(payload)
        width, height = image.size
        inference_state = processor.set_image(image)
        raw_regions: list[dict[str, Any]] = []
        return_masks = bool(payload.get("return_masks", False))
        mask_dir = output_dir / "masks"
        if return_masks:
            mask_dir.mkdir(parents=True, exist_ok=True)

        for spec in specs:
            processor.set_confidence_threshold(spec["confidence_threshold"])
            state = processor.set_text_prompt(prompt=spec["text"], state=inference_state)
            for box in spec["positive_boxes"]:
                state = processor.add_geometric_prompt(box=box, label=True, state=state)
            for box in spec["negative_boxes"]:
                state = processor.add_geometric_prompt(box=box, label=False, state=state)

            boxes = _tensor_to_list(state["boxes"])
            scores = _tensor_to_list(state["scores"])
            masks = state.get("masks")
            ranked = sorted(
                enumerate(zip(boxes, scores)),
                key=lambda item: float(item[1][1]),
                reverse=True,
            )[: spec["max_masks"]]
            for local_index, (box, score) in ranked:
                x1, y1, x2, y2 = [int(round(float(value))) for value in box[:4]]
                x1, y1 = max(0, x1), max(0, y1)
                x2, y2 = min(width, x2), min(height, y2)
                if x2 <= x1 or y2 <= y1:
                    continue
                region_id = f"{spec['id']}_{len(raw_regions) + 1:03d}"
                mask_path = None
                geometry = None
                if return_masks and masks is not None:
                    mask_name = f"{region_id}.png"
                    _save_mask_png(masks[local_index], mask_dir / mask_name)
                    mask_path = f"masks/{mask_name}"
                    geometry = {
                        "kind": "mask",
                        "mask_path": mask_path,
                        "bbox": [x1, y1, x2, y2],
                        "coordinate_system": "figure_image_pixels",
                    }
                region = {
                    "id": region_id,
                    "label": f"<SAM>{len(raw_regions) + 1:03d}",
                    "prompt_id": spec["id"],
                    "prompt": spec["text"],
                    "level": spec["level"],
                    "score": float(score),
                    "bbox": [x1, y1, x2, y2],
                    "area_ratio": ((x2 - x1) * (y2 - y1)) / float(width * height),
                }
                if mask_path:
                    region["mask_path"] = mask_path
                if geometry:
                    region["geometry"] = geometry
                raw_regions.append(region)

        box_regions = [
            {
                "id": index,
                "label": region["label"],
                "x1": region["bbox"][0],
                "y1": region["bbox"][1],
                "x2": region["bbox"][2],
                "y2": region["bbox"][3],
                "score": region["score"],
                "prompt": region["prompt"],
            }
            for index, region in enumerate(raw_regions)
        ]
        merge_threshold = float(payload.get("merge_threshold") or 0.0)
        merged_boxes = _merge_overlapping_boxes(box_regions, merge_threshold)
        regions = [
            {
                "id": f"region_{index + 1:03d}",
                "label": box.get("label", f"<SAM>{index + 1:03d}"),
                "prompt": box.get("prompt"),
                "score": float(box.get("score", 0.0)),
                "bbox": [box["x1"], box["y1"], box["x2"], box["y2"]],
                "area_ratio": ((box["x2"] - box["x1"]) * (box["y2"] - box["y1"])) / float(width * height),
            }
            for index, box in enumerate(merged_boxes)
        ]

        artifacts: dict[str, Any] = {"regions_json": str(output_dir / "regions.json")}
        if return_masks:
            artifacts["mask_dir"] = str(mask_dir)
        if bool(payload.get("return_overlay", True)):
            overlay_path = output_dir / "overlay.png"
            _draw_sam_overlay(image, regions, overlay_path)
            artifacts["overlay"] = str(overlay_path)
        else:
            artifacts["overlay"] = None

        result = {
            "job_id": output_dir.name,
            "image": {"width": width, "height": height, "mode": image.mode},
            "prompts": specs,
            "regions": regions,
            "raw_regions": raw_regions,
            "artifacts": artifacts,
            "created_at": int(time.time()),
        }
        (output_dir / "regions.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result


class LocalPaddleOcrProvider:
    def __init__(
        self,
        *,
        paths: LocalRuntimePaths,
        device: str = "cpu",
        text_det_box_thresh: float = DEFAULT_DET_BOX_THRESH,
        text_rec_score_thresh: float = DEFAULT_REC_SCORE_THRESH,
        text_det_limit_side_len: int | None = DEFAULT_LOCAL_OCR_DET_LIMIT_SIDE_LEN,
        text_det_limit_type: str = "max",
    ) -> None:
        self.paths = paths
        self.device = device
        self.text_det_box_thresh = text_det_box_thresh
        self.text_rec_score_thresh = text_rec_score_thresh
        self.text_det_limit_side_len = (
            int(text_det_limit_side_len)
            if text_det_limit_side_len is not None and int(text_det_limit_side_len) > 0
            else None
        )
        self.text_det_limit_type = text_det_limit_type
        self._ocr: Any | None = None

    def extract_boxes(self, image_path: Path) -> dict[str, Any]:
        started = time.monotonic()
        ocr = self._ocr_runtime()
        raw_result = ocr.predict(str(Path(image_path).resolve()))
        blocks = _extract_paddle_blocks(raw_result)
        boxes = [
            {
                "id": block["id"],
                "bbox": _bbox_dict_to_xyxy(block["bbox"]),
                "confidence": block["confidence"],
                "source": "local_paddleocr",
                "text": block["text"],
            }
            for block in blocks
        ]
        normalized = normalize_ocr_boxes_payload(
            {"ocr_text_boxes": boxes},
            default_source="local_paddleocr",
        )
        normalized["provider"] = "local_paddleocr"
        normalized["elapsed_ms"] = round((time.monotonic() - started) * 1000, 3)
        return normalized

    def _ocr_runtime(self) -> Any:
        if self._ocr is not None:
            return self._ocr

        previous_home = self._prepare_paddle_model_home()
        os.environ.setdefault("FLAGS_allocator_strategy", "auto_growth")
        os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

        try:
            if importlib.util.find_spec("torch") is not None:
                import torch  # noqa: F401 - preload Torch DLLs before Paddle on Windows.
            import paddle
            from paddleocr import PaddleOCR

            paddle.set_device(self.device)
            self._ocr = PaddleOCR(
                ocr_version="PP-OCRv5",
                text_detection_model_name="PP-OCRv5_server_det",
                text_detection_model_dir=str(self.paths.paddlex_official_models / "PP-OCRv5_server_det"),
                text_recognition_model_name="PP-OCRv5_server_rec",
                text_recognition_model_dir=str(self.paths.paddlex_official_models / "PP-OCRv5_server_rec"),
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
                text_det_limit_side_len=self.text_det_limit_side_len,
                text_det_limit_type=self.text_det_limit_type if self.text_det_limit_side_len else None,
                text_det_box_thresh=self.text_det_box_thresh,
                text_rec_score_thresh=self.text_rec_score_thresh,
                return_word_box=True,
                device=self.device,
                engine="paddle_static",
                enable_hpi=False,
                use_tensorrt=False,
                enable_cinn=False,
            )
        finally:
            _restore_env_var("HOME", previous_home)
        return self._ocr

    def release_runtime(self) -> None:
        self._ocr = None
        gc.collect()

    def _prepare_paddle_model_home(self) -> str | None:
        previous_home = os.environ.get("HOME")
        model_root = self.paths.paddle_home / ".paddlex" / "official_models"
        model_root.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_paddlex_official_models(model_root)
        os.environ["HOME"] = str(self.paths.paddle_home)
        return previous_home

    def _ensure_paddlex_official_models(self, model_root: Path) -> None:
        if model_root.exists():
            return
        try:
            model_root.symlink_to(self.paths.paddlex_official_models, target_is_directory=True)
            return
        except OSError:
            if os.name == "nt" and _create_windows_junction(model_root, self.paths.paddlex_official_models):
                return
            if model_root.exists():
                return
            shutil.copytree(self.paths.paddlex_official_models, model_root)


class LocalRmbgClient:
    def __init__(self, *, paths: LocalRuntimePaths, device: str = "cpu") -> None:
        self.paths = paths
        self.device = device
        self._model: Any | None = None
        self._transform_image: Any | None = None
        self._torch: Any | None = None
        self._transforms: Any | None = None

    def remove_background(
        self,
        image: Image.Image,
        output_name: str,
        *,
        timeout_s: float,
        model_path: str = "",
        artifact_prefix: str | None = None,
    ) -> RmbgResult:
        del timeout_s, artifact_prefix
        started = time.monotonic()
        active_model_path = Path(model_path).expanduser() if model_path else self.paths.rmbg_model_dir
        self._ensure_model(active_model_path)
        image_rgb = image.convert("RGB")
        input_tensor = self._transform_image(image_rgb).unsqueeze(0).to(self._resolved_device)
        with self._torch.no_grad():
            pred = _extract_rmbg_mask(self._model(input_tensor))
        pred_pil = self._transforms.ToPILImage()(pred)
        mask = pred_pil.resize(image_rgb.size)
        output = image_rgb.copy()
        output.putalpha(mask)
        return RmbgResult(
            image=output.convert("RGBA"),
            artifacts={
                "model_path": str(active_model_path),
                "output_name": output_name,
                "runtime": "local_rmbg2",
            },
            elapsed_ms=round((time.monotonic() - started) * 1000, 3),
        )

    def _ensure_model(self, model_path: Path) -> None:
        if self._model is not None:
            return

        import torch
        from torchvision import transforms
        from transformers import AutoModelForImageSegmentation

        self._torch = torch
        self._transforms = transforms
        self._resolved_device = _resolve_torch_device(self.device)
        self._model = AutoModelForImageSegmentation.from_pretrained(
            str(model_path),
            trust_remote_code=True,
            local_files_only=True,
        ).eval().to(self._resolved_device)
        self._transform_image = transforms.Compose(
            [
                transforms.Resize((1024, 1024)),
                transforms.ToTensor(),
                transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
            ]
        )

    def release_runtime(self) -> None:
        self._model = None
        self._transform_image = None
        gc.collect()
        _empty_torch_cache()


def _resolve_torch_device(requested: str) -> str:
    normalized = str(requested or "auto").strip().lower()
    if normalized != "auto":
        return normalized

    import torch

    if torch.cuda.is_available():
        return "cuda"
    if _torch_mps_available(torch):
        return "mps"
    return "cpu"


def _resolve_sam3_torch_device(requested: str) -> str:
    normalized = str(requested or "auto").strip().lower()
    if normalized == "mps":
        return "cpu"
    if normalized == "auto":
        import torch

        if torch.cuda.is_available():
            return "cuda"
        return "cpu"
    return _resolve_torch_device(normalized)


def install_sam3_edt_fallback_if_needed() -> None:
    if "sam3.model.edt" in sys.modules:
        return
    if importlib.util.find_spec("triton") is not None:
        return

    module = types.ModuleType("sam3.model.edt")
    module.edt_triton = _sam3_cpu_edt_fallback
    sys.modules["sam3.model.edt"] = module


def _sam3_cpu_edt_fallback(data: Any) -> Any:
    import cv2
    import numpy as np
    import torch

    if data.dim() != 3:
        raise AssertionError("SAM3 EDT fallback expects a tensor with shape BxHxW")
    device = data.device
    masks = data.detach().to("cpu").numpy().astype("uint8")
    distances = [cv2.distanceTransform(mask, cv2.DIST_L2, 0) for mask in masks]
    return torch.from_numpy(np.stack(distances)).to(device=device, dtype=torch.float32)


@contextmanager
def _sam3_torch_factory_device_patch(torch_module: Any, device: str) -> Any:
    if str(device).startswith("cuda"):
        yield
        return
    factory_names = ("arange", "empty", "full", "ones", "tensor", "zeros")
    originals = {
        name: getattr(torch_module, name)
        for name in factory_names
        if callable(getattr(torch_module, name, None))
    }

    def redirect_factory(original: Any) -> Any:
        def redirected(*args: Any, **kwargs: Any) -> Any:
            if kwargs.get("device") == "cuda":
                kwargs = dict(kwargs)
                kwargs["device"] = device
            return original(*args, **kwargs)

        return redirected

    for name, original in originals.items():
        setattr(torch_module, name, redirect_factory(original))
    try:
        yield
    finally:
        for name, original in originals.items():
            setattr(torch_module, name, original)


@contextmanager
def _sam3_torch_runtime_device_patch(torch_module: Any, device: str) -> Any:
    with _sam3_torch_factory_device_patch(torch_module, device):
        if str(device).startswith("cuda"):
            yield
            return
        tensor_type = getattr(torch_module, "Tensor", None)
        original_pin_memory = getattr(tensor_type, "pin_memory", None)
        if not callable(original_pin_memory):
            yield
            return

        def pin_memory_without_cuda(self: Any, *args: Any, **kwargs: Any) -> Any:
            return self

        tensor_type.pin_memory = pin_memory_without_cuda
        try:
            yield
        finally:
            tensor_type.pin_memory = original_pin_memory


def _torch_mps_available(torch_module: Any) -> bool:
    backends = getattr(torch_module, "backends", None)
    mps_backend = getattr(backends, "mps", None)
    is_available = getattr(mps_backend, "is_available", None)
    return bool(is_available()) if callable(is_available) else False


def _empty_torch_cache() -> None:
    try:
        import torch
    except ModuleNotFoundError:
        return
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    mps = getattr(torch, "mps", None)
    if mps is not None and hasattr(torch.mps, "empty_cache"):
        torch.mps.empty_cache()


def _restore_env_var(name: str, value: str | None) -> None:
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value


def _load_sam_image(payload: Mapping[str, Any]) -> Image.Image:
    image_base64 = payload.get("image_base64")
    image_path = payload.get("image_path")
    if bool(image_base64) == bool(image_path):
        raise ValueError("Provide exactly one of image_base64 or image_path.")
    if isinstance(image_base64, str):
        raw = base64.b64decode(image_base64.split(",", 1)[1] if "," in image_base64 else image_base64)
        image = Image.open(io.BytesIO(raw))
    else:
        path = Path(str(image_path)).expanduser()
        image = Image.open(path)
    return _normalize_image_for_sam(image)


def _normalize_image_for_sam(image: Image.Image) -> Image.Image:
    if image.mode == "RGB":
        return image.copy()
    has_alpha = image.mode in {"RGBA", "LA"} or (image.mode == "P" and "transparency" in image.info)
    if not has_alpha:
        return image.convert("RGB")
    rgba = image.convert("RGBA")
    white_background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
    white_background.alpha_composite(rgba)
    return white_background.convert("RGB")


def _normalize_sam_prompt_specs(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    prompts = payload.get("prompts") or []
    if not isinstance(prompts, list):
        raise ValueError("SAM3 prompts must be a list")
    default_threshold = _clamp_float(payload.get("confidence_threshold", 0.35), 0.0, 1.0)
    default_max_masks = _clamp_int(payload.get("max_masks", 80), 1, 500)
    specs: list[dict[str, Any]] = []
    used_ids: set[str] = set()
    for index, item in enumerate(prompts, start=1):
        if isinstance(item, str):
            text = item.strip()
            prompt_id = f"prompt_{index:03d}"
            level = None
            threshold = default_threshold
            max_masks = default_max_masks
            positive_boxes: list[list[float]] = []
            negative_boxes: list[list[float]] = []
        elif isinstance(item, Mapping):
            text = str(item.get("text") or "").strip()
            prompt_id = str(item.get("id") or f"prompt_{index:03d}").strip()
            level_value = item.get("level")
            level = str(level_value).strip() if level_value is not None else None
            threshold = (
                default_threshold
                if item.get("confidence_threshold") is None
                else _clamp_float(item["confidence_threshold"], 0.0, 1.0)
            )
            max_masks = (
                default_max_masks
                if item.get("max_masks") is None
                else _clamp_int(item["max_masks"], 1, 500)
            )
            positive_boxes = _geometric_boxes(item.get("positive_boxes"))
            negative_boxes = _geometric_boxes(item.get("negative_boxes"))
        else:
            raise ValueError(f"Unsupported SAM3 prompt type: {type(item).__name__}")

        if not text:
            continue
        if prompt_id in used_ids:
            prompt_id = f"{prompt_id}_{index:03d}"
        used_ids.add(prompt_id)
        specs.append(
            {
                "id": prompt_id,
                "text": text,
                "level": level,
                "confidence_threshold": threshold,
                "max_masks": max_masks,
                "positive_boxes": positive_boxes,
                "negative_boxes": negative_boxes,
            }
        )
    if not specs:
        raise ValueError("At least one non-empty SAM3 prompt is required.")
    return specs


def _geometric_boxes(value: Any) -> list[list[float]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("SAM3 geometric boxes must be lists")
    return [[float(component) for component in list(box)[:4]] for box in value]


def _tensor_to_list(value: Any) -> Any:
    try:
        import torch
    except ModuleNotFoundError:
        torch = None
    if torch is not None and isinstance(value, torch.Tensor):
        return value.detach().cpu().tolist()
    return value


def _save_mask_png(mask_tensor: Any, path: Path) -> None:
    mask = mask_tensor.detach().cpu()
    if mask.ndim == 3:
        mask = mask.squeeze(0)
    image = Image.fromarray((mask.numpy().astype("uint8")) * 255, mode="L")
    image.save(path)


def _draw_sam_overlay(image: Image.Image, regions: list[Mapping[str, Any]], output_path: Path) -> None:
    overlay = image.copy()
    draw = ImageDraw.Draw(overlay)
    for region in regions:
        x1, y1, x2, y2 = region["bbox"]
        label = str(region.get("label") or "")
        draw.rectangle([x1, y1, x2, y2], fill="#808080", outline="black", width=3)
        font = _label_font(int(x2) - int(x1), int(y2) - int(y1))
        cx = (int(x1) + int(x2)) // 2
        cy = (int(y1) + int(y2)) // 2
        draw.text((cx, cy), label, fill="white", anchor="mm", font=font)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    overlay.save(output_path)


def _label_font(box_width: int, box_height: int) -> ImageFont.ImageFont:
    font_size = max(12, min(48, min(box_width, box_height) // 4))
    for font_path in (
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ):
        path = Path(font_path)
        if path.exists():
            return ImageFont.truetype(str(path), font_size)
    return ImageFont.load_default()


def _merge_overlapping_boxes(boxes: list[dict[str, Any]], overlap_threshold: float) -> list[dict[str, Any]]:
    if overlap_threshold <= 0 or len(boxes) <= 1:
        return boxes
    working = [dict(box) for box in boxes]
    merged = True
    while merged:
        merged = False
        for left_index, left in enumerate(working):
            if merged:
                break
            for right_index in range(left_index + 1, len(working)):
                right = working[right_index]
                ratio = _overlap_ratio(left, right)
                if ratio < overlap_threshold:
                    continue
                left_area = _box_area(left)
                right_area = _box_area(right)
                smaller = max(1.0, min(left_area, right_area))
                if max(left_area, right_area) / smaller > 4.0:
                    continue
                new_box = _merge_two_boxes(left, right)
                working = [
                    box
                    for index, box in enumerate(working)
                    if index not in {left_index, right_index}
                ]
                working.append(new_box)
                merged = True
                break
    return working


def _overlap_ratio(left: Mapping[str, Any], right: Mapping[str, Any]) -> float:
    x1 = max(float(left["x1"]), float(right["x1"]))
    y1 = max(float(left["y1"]), float(right["y1"]))
    x2 = min(float(left["x2"]), float(right["x2"]))
    y2 = min(float(left["y2"]), float(right["y2"]))
    intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    if intersection <= 0:
        return 0.0
    return intersection / max(1.0, min(_box_area(left), _box_area(right)))


def _box_area(box: Mapping[str, Any]) -> float:
    return max(0.0, float(box["x2"]) - float(box["x1"])) * max(0.0, float(box["y2"]) - float(box["y1"]))


def _merge_two_boxes(left: Mapping[str, Any], right: Mapping[str, Any]) -> dict[str, Any]:
    left_score = float(left.get("score") or 0.0)
    right_score = float(right.get("score") or 0.0)
    best = left if left_score >= right_score else right
    return {
        "id": best.get("id"),
        "label": best.get("label"),
        "x1": int(round(min(float(left["x1"]), float(right["x1"])))),
        "y1": int(round(min(float(left["y1"]), float(right["y1"])))),
        "x2": int(round(max(float(left["x2"]), float(right["x2"])))),
        "y2": int(round(max(float(left["y2"]), float(right["y2"])))),
        "score": max(left_score, right_score),
        "prompt": best.get("prompt"),
    }


def _extract_paddle_blocks(raw_result: Any) -> list[dict[str, Any]]:
    pages = list(raw_result or [])
    blocks: list[dict[str, Any]] = []
    for page in pages:
        data = _paddle_page_to_dict(page)
        texts = list(data.get("rec_texts") or [])
        scores = list(data.get("rec_scores") or [])
        polys = data.get("rec_polys")
        if polys is None:
            polys = data.get("dt_polys")
        boxes = data.get("rec_boxes")
        polys = list(polys) if polys is not None else []
        boxes = list(boxes) if boxes is not None else []
        for index, text in enumerate(texts):
            points = polys[index] if index < len(polys) else _box_points(boxes[index] if index < len(boxes) else [])
            bbox = _bbox_from_points(points)
            if bbox is None:
                continue
            blocks.append(
                {
                    "id": f"ocr_{len(blocks) + 1:03d}",
                    "text": str(text),
                    "confidence": float(scores[index]) if index < len(scores) else 0.0,
                    "bbox": bbox,
                    "points": [
                        [float(point[0]), float(point[1])]
                        for point in ([] if points is None else list(points))
                    ],
                    "source": "local_paddleocr",
                }
            )
    return blocks


def _paddle_page_to_dict(page: Any) -> dict[str, Any]:
    if isinstance(page, dict):
        data = dict(page)
        return dict(data["res"]) if isinstance(data.get("res"), dict) else data
    json_attr = getattr(page, "json", None)
    if isinstance(json_attr, dict):
        return dict(json_attr["res"]) if isinstance(json_attr.get("res"), dict) else dict(json_attr)
    if callable(json_attr):
        value = json_attr()
        if isinstance(value, dict):
            return dict(value["res"]) if isinstance(value.get("res"), dict) else dict(value)
    to_dict = getattr(page, "to_dict", None)
    if callable(to_dict):
        value = to_dict()
        if isinstance(value, dict):
            return dict(value["res"]) if isinstance(value.get("res"), dict) else value
    if hasattr(page, "get") and hasattr(page, "keys"):
        return {key: page.get(key) for key in page.keys()}
    return {}


def _box_points(raw_box: Any) -> list[list[float]]:
    values = list(raw_box) if raw_box is not None else []
    if len(values) >= 4 and not isinstance(values[0], (list, tuple)):
        x0, y0, x1, y1 = [float(value) for value in values[:4]]
        return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
    return values


def _bbox_from_points(points: Any) -> dict[str, float] | None:
    pairs: list[tuple[float, float]] = []
    for point in [] if points is None else list(points):
        if not isinstance(point, (list, tuple)):
            point = list(point)
        if len(point) >= 2:
            pairs.append((float(point[0]), float(point[1])))
    if not pairs:
        return None
    xs = [point[0] for point in pairs]
    ys = [point[1] for point in pairs]
    return {"x": min(xs), "y": min(ys), "w": max(xs) - min(xs), "h": max(ys) - min(ys)}


def _bbox_dict_to_xyxy(bbox: Mapping[str, Any]) -> list[int | float]:
    x = float(bbox["x"])
    y = float(bbox["y"])
    w = float(bbox["w"])
    h = float(bbox["h"])
    return [_clean_number(x), _clean_number(y), _clean_number(x + w), _clean_number(y + h)]


def _extract_rmbg_mask(model_output: Any) -> Any:
    import torch

    candidates: list[Any] = []

    def collect(value: Any) -> None:
        if isinstance(value, torch.Tensor):
            if value.ndim >= 3:
                candidates.append(value)
            return
        if isinstance(value, (list, tuple)):
            for item in value:
                collect(item)

    collect(model_output)
    mask_candidates = [
        tensor
        for tensor in candidates
        if tensor.ndim >= 4 and tensor.shape[-3] == 1
    ]
    if not mask_candidates:
        mask_candidates = [tensor for tensor in candidates if tensor.ndim >= 3]
    if not mask_candidates:
        raise RuntimeError("RMBG model did not return a usable mask tensor")
    mask = max(mask_candidates, key=lambda tensor: tensor.shape[-2] * tensor.shape[-1])
    if mask.ndim == 4:
        mask = mask[0]
    if mask.ndim == 3:
        mask = mask[0]
    if mask.ndim != 2:
        raise RuntimeError(f"Unexpected RMBG mask dimensions: {tuple(mask.shape)}")
    if float(mask.min()) < 0.0 or float(mask.max()) > 1.0:
        mask = mask.sigmoid()
    return mask.detach().cpu()


def _clamp_float(value: Any, low: float, high: float) -> float:
    return max(low, min(high, float(value)))


def _clamp_int(value: Any, low: int, high: int) -> int:
    return max(low, min(high, int(value)))


def _clean_number(value: float) -> int | float:
    if math.isfinite(value) and abs(value - round(value)) < 1e-6:
        return int(round(value))
    return round(value, 3)


def _safe_job_prefix(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_", "."} else "_" for char in value).strip("._") or "job"
