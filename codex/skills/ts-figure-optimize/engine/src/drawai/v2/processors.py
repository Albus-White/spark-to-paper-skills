from __future__ import annotations

import math
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from PIL import Image

from drawai.asset_geometry import geometry_crop
from drawai.rmbg_client import RmbgResult

from .packages import element_dir, read_asset_package, write_asset_package
from .schema import AssetPackage, AssetStatus, ElementPlan, utc_now


class AssetProcessor(Protocol):
    processor_type: str

    def process(
        self,
        root: str | Path,
        plan: ElementPlan,
        *,
        source_image_path: str | Path | None = None,
    ) -> AssetPackage:
        ...


@dataclass(frozen=True)
class _ProcessOutcome:
    status: AssetStatus
    input_refs: dict[str, Any] = field(default_factory=dict)
    output_refs: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] | None = None
    editable_payload: dict[str, Any] | None = None
    failure: str | None = None


class _BaseProcessor:
    processor_type: str

    def process(
        self,
        root: str | Path,
        plan: ElementPlan,
        *,
        source_image_path: str | Path | None = None,
    ) -> AssetPackage:
        root_path = Path(root).expanduser().resolve()
        started_at = utc_now()
        base_input_refs = _input_refs(root_path, plan, source_image_path)
        try:
            outcome = self._process(
                root_path,
                plan,
                source_image_path=source_image_path,
            )
            ended_at = utc_now()
            run = _processor_run(
                self.processor_type,
                status=outcome.status,
                started_at=started_at,
                ended_at=ended_at,
                input_refs={**base_input_refs, **outcome.input_refs},
                output_refs=outcome.output_refs,
                metadata=outcome.metadata,
            )
            return _write_package(
                root_path,
                plan,
                processor_type=self.processor_type,
                status=outcome.status,
                processor_run=run,
                result=outcome.result,
                editable_payload=outcome.editable_payload,
                failure=outcome.failure,
                metadata=outcome.metadata,
            )
        except Exception as exc:
            ended_at = utc_now()
            run = _processor_run(
                self.processor_type,
                status="failed",
                started_at=started_at,
                ended_at=ended_at,
                input_refs=base_input_refs,
                output_refs={},
                metadata={"failure_type": type(exc).__name__},
            )
            try:
                _write_package(
                    root_path,
                    plan,
                    processor_type=self.processor_type,
                    status="failed",
                    processor_run=run,
                    failure=str(exc),
                )
            except Exception as failure_write_error:
                exc.add_note(
                    f"failed to persist failed asset package: {failure_write_error}"
                )
            raise

    def _process(
        self,
        root: Path,
        plan: ElementPlan,
        *,
        source_image_path: str | Path | None,
    ) -> _ProcessOutcome:
        raise NotImplementedError


class NoProcessProcessor(_BaseProcessor):
    processor_type = "no_process"

    def _process(
        self,
        root: Path,
        plan: ElementPlan,
        *,
        source_image_path: str | Path | None,
    ) -> _ProcessOutcome:
        return _ProcessOutcome(
            status="ok",
            metadata={
                "reason": "Element is structural and does not require asset materialization.",
            },
        )


class CropProcessor(_BaseProcessor):
    processor_type = "crop"

    def _process(
        self,
        root: Path,
        plan: ElementPlan,
        *,
        source_image_path: str | Path | None,
    ) -> _ProcessOutcome:
        source_path = _resolve_source_image(root, source_image_path)
        result_id = _new_result_id(self.processor_type)
        result_dir = _result_dir(root, plan.element_id, result_id)
        result_path = result_dir / "crop.png"
        crop, crop_bbox = _crop_plan_image(
            root,
            source_path,
            plan,
        )
        crop.save(result_path)
        metadata = _crop_metadata(root, source_path, crop, crop_bbox)
        result = _raster_result(
            root,
            processor_type=self.processor_type,
            result_id=result_id,
            path=result_path,
            metadata=metadata,
        )
        return _ProcessOutcome(
            status="ok",
            input_refs={"source_image": _path_ref(root, source_path)},
            output_refs={"result_id": result_id, "files": [result["path"]]},
            metadata=metadata,
            result=result,
        )


class CropNoBgProcessor(_BaseProcessor):
    processor_type = "crop_nobg"

    def __init__(self, *, rmbg_client: Any | None = None) -> None:
        self.rmbg_client = rmbg_client

    def _process(
        self,
        root: Path,
        plan: ElementPlan,
        *,
        source_image_path: str | Path | None,
    ) -> _ProcessOutcome:
        if self.rmbg_client is None:
            raise RuntimeError("rmbg_client is required for crop_nobg processing")

        source_path = _resolve_source_image(root, source_image_path)
        result_id = _new_result_id(self.processor_type)
        result_dir = _result_dir(root, plan.element_id, result_id)
        result_path = result_dir / "crop_nobg.png"
        crop, crop_bbox = _crop_plan_image(root, source_path, plan)
        rmbg = _remove_background(
            self.rmbg_client,
            crop,
            output_name=f"{plan.element_id}_{result_id}",
            timeout_s=_rmbg_timeout_s(plan),
            model_path=_rmbg_model_path(plan),
            artifact_prefix=f"drawai_v2/{plan.element_id}/{result_id}",
        )
        rmbg.image.convert("RGBA").save(result_path)

        metadata = {
            **_crop_metadata(root, source_path, rmbg.image, crop_bbox),
            "rmbg_elapsed_ms": rmbg.elapsed_ms,
            "rmbg_artifacts": rmbg.artifacts,
        }
        result = _raster_result(
            root,
            processor_type=self.processor_type,
            result_id=result_id,
            path=result_path,
            metadata=metadata,
        )
        return _ProcessOutcome(
            status="ok",
            input_refs={"source_image": _path_ref(root, source_path)},
            output_refs={"result_id": result_id, "files": [result["path"]]},
            metadata=metadata,
            result=result,
        )


class SvgSelfDrawProcessor(_BaseProcessor):
    processor_type = "svg_self_draw"

    def _process(
        self,
        root: Path,
        plan: ElementPlan,
        *,
        source_image_path: str | Path | None,
    ) -> _ProcessOutcome:
        result_id = _new_result_id(self.processor_type)
        editable_payload = {
            "kind": "svg_self_draw_constraints",
            "element_id": plan.element_id,
            "element_type": plan.element_type,
            "bbox": list(plan.bbox),
            "geometry": _jsonable(plan.geometry),
            "z_order": plan.z_order,
            "confidence": plan.confidence,
            "processing_intent": plan.processing_intent.to_dict(),
            "source_candidate_ids": list(plan.source_candidate_ids),
            "review_status": plan.review_status,
            "change_reason": plan.change_reason,
        }
        result = {
            "result_id": result_id,
            "processor_type": self.processor_type,
            "status": "ok",
            "kind": "editable_payload",
            "path": None,
            "files": [],
            "metadata": {"editable_payload_kind": editable_payload["kind"]},
            "created_at": utc_now(),
        }
        return _ProcessOutcome(
            status="ok",
            output_refs={"result_id": result_id, "files": []},
            metadata={"editable_payload_kind": editable_payload["kind"]},
            result=result,
            editable_payload=editable_payload,
        )


class ImageGenerateProcessor(_BaseProcessor):
    processor_type = "image_generate"

    def __init__(self, *, image_generate: Callable[..., Any] | None = None) -> None:
        self.image_generate = image_generate or _default_image_generate()

    def _process(
        self,
        root: Path,
        plan: ElementPlan,
        *,
        source_image_path: str | Path | None,
    ) -> _ProcessOutcome:
        result_id = _new_result_id(self.processor_type)
        result_dir = _result_dir(root, plan.element_id, result_id)
        prompt = _prompt_from_plan(plan)
        provider_result = self.image_generate(
            prompt=prompt,
            output_dir=result_dir,
            task_name="drawai.v2.image_generate.v1",
            output_stem="image_generate",
            runtime_config=_runtime_config(plan),
        )
        provider_payload = _provider_payload(provider_result, root=root)
        output_path = _first_provider_image_path(
            provider_result,
            provider_payload,
            root=root,
            result_dir=result_dir,
        )
        metadata = {"provider": provider_payload}
        result = _raster_result(
            root,
            processor_type=self.processor_type,
            result_id=result_id,
            path=output_path,
            metadata=metadata,
        )
        return _ProcessOutcome(
            status="ok",
            output_refs={"result_id": result_id, "files": [result["path"]]},
            metadata=metadata,
            result=result,
        )


class ImageEditProcessor(_BaseProcessor):
    processor_type = "image_edit"

    def __init__(self, *, image_edit: Callable[..., Any] | None = None) -> None:
        self.image_edit = image_edit or _default_image_edit()

    def _process(
        self,
        root: Path,
        plan: ElementPlan,
        *,
        source_image_path: str | Path | None,
    ) -> _ProcessOutcome:
        source_path = _resolve_source_image(root, source_image_path)
        result_id = _new_result_id(self.processor_type)
        result_dir = _result_dir(root, plan.element_id, result_id)
        edit_source_path = result_dir / "source.png"
        crop, crop_bbox = _crop_plan_image(root, source_path, plan)
        crop.save(edit_source_path)

        prompt = _prompt_from_plan(plan)
        provider_result = self.image_edit(
            source_image_path=edit_source_path,
            prompt=prompt,
            output_dir=result_dir,
            task_name="drawai.v2.image_edit.v1",
            output_stem="image_edit",
            runtime_config=_runtime_config(plan),
        )
        provider_payload = _provider_payload(provider_result, root=root)
        output_path = _first_provider_image_path(
            provider_result,
            provider_payload,
            root=root,
            result_dir=result_dir,
        )
        source_crop_ref = {
            "kind": "source_crop",
            "path": _artifact_relpath(root, edit_source_path),
            "media_type": "image/png",
        }
        metadata = {
            "source_crop": {
                "path": source_crop_ref["path"],
                "crop_bbox_xyxy": list(crop_bbox),
            },
            "provider": provider_payload,
        }
        result = _raster_result(
            root,
            processor_type=self.processor_type,
            result_id=result_id,
            path=output_path,
            metadata=metadata,
        )
        result["files"] = [source_crop_ref, *result["files"]]
        return _ProcessOutcome(
            status="ok",
            input_refs={"source_image": _path_ref(root, source_path)},
            output_refs={
                "result_id": result_id,
                "files": [metadata["source_crop"]["path"], result["path"]],
            },
            metadata=metadata,
            result=result,
        )


class ChartRebuildReservedProcessor(_BaseProcessor):
    processor_type = "chart_rebuild_reserved"

    def _process(
        self,
        root: Path,
        plan: ElementPlan,
        *,
        source_image_path: str | Path | None,
    ) -> _ProcessOutcome:
        message = (
            "chart_rebuild_reserved is reserved for a future chart rebuilding processor"
        )
        return _ProcessOutcome(
            status="unsupported",
            output_refs={},
            metadata={"reason": message},
            failure=message,
        )


def processor_for_type(
    processing_type: str,
    providers: Mapping[str, Any] | None = None,
) -> AssetProcessor:
    providers = providers or {}
    if processing_type == "no_process":
        return NoProcessProcessor()
    if processing_type == "crop":
        return CropProcessor()
    if processing_type == "crop_nobg":
        return CropNoBgProcessor(rmbg_client=providers.get("rmbg_client"))
    if processing_type == "svg_self_draw":
        return SvgSelfDrawProcessor()
    if processing_type == "image_generate":
        return ImageGenerateProcessor(image_generate=providers.get("image_generate"))
    if processing_type == "image_edit":
        return ImageEditProcessor(image_edit=providers.get("image_edit"))
    if processing_type == "chart_rebuild_reserved":
        return ChartRebuildReservedProcessor()
    raise ValueError(f"unknown processing_type: {processing_type}")


def _crop_plan_image(
    root: Path,
    source_path: Path,
    plan: ElementPlan,
) -> tuple[Image.Image, tuple[int, int, int, int]]:
    geometry = _safe_crop_geometry(root, plan.geometry)
    with Image.open(source_path) as source:
        crop_bbox = _crop_bounds_from_plan_bbox(plan.bbox, source.size)
        crop = geometry_crop(source, crop_bbox, geometry, base_dir=root)
        crop.load()
    return crop, crop_bbox


def _crop_bounds_from_plan_bbox(
    bbox: tuple[float, float, float, float],
    image_size: tuple[int, int],
) -> tuple[int, int, int, int]:
    if len(bbox) != 4:
        raise ValueError("invalid crop bounds: plan bbox must contain four values")
    x, y, width, height = (float(value) for value in bbox)
    if not all(math.isfinite(value) for value in (x, y, width, height)):
        raise ValueError("invalid crop bounds: plan bbox values must be finite")
    if width <= 0 or height <= 0:
        raise ValueError("invalid crop bounds: plan bbox must have positive area")

    image_width, image_height = image_size
    left = max(0, min(image_width, math.floor(x)))
    top = max(0, min(image_height, math.floor(y)))
    right = max(0, min(image_width, math.ceil(x + width)))
    bottom = max(0, min(image_height, math.ceil(y + height)))
    if right <= left or bottom <= top:
        raise ValueError(
            f"invalid crop bounds after clamping: {[left, top, right, bottom]}"
        )
    return (left, top, right, bottom)


def _safe_crop_geometry(root: Path, geometry: Mapping[str, Any]) -> Mapping[str, Any]:
    if not isinstance(geometry, Mapping):
        return geometry
    raw_mask_path = _raw_geometry_mask_path(geometry)
    if not raw_mask_path:
        return geometry

    resolved = _resolve_geometry_mask_path(root, raw_mask_path)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(
            f"geometry mask_path must resolve under run root: {raw_mask_path}"
        ) from exc

    normalized = dict(geometry)
    for key in ("mask_path", "path", "alpha_mask_path"):
        if key in normalized:
            normalized[key] = _path_ref(root, resolved)
            break
    return normalized


def _raw_geometry_mask_path(geometry: Mapping[str, Any]) -> str:
    kind = str(geometry.get("kind") or geometry.get("type") or "").strip().lower()
    if kind not in {"mask", "segmentation", "alpha_mask", "bitmap_mask"}:
        if not any(key in geometry for key in ("mask_path", "path", "alpha_mask_path")):
            return ""
    for key in ("mask_path", "path", "alpha_mask_path"):
        value = geometry.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _resolve_geometry_mask_path(root: Path, raw_mask_path: str) -> Path:
    path = Path(raw_mask_path).expanduser()
    if path.is_absolute():
        return path.resolve(strict=False)
    return (root / path).resolve(strict=False)


def _remove_background(
    rmbg_client: Any,
    crop: Image.Image,
    output_name: str,
    *,
    timeout_s: float,
    model_path: str,
    artifact_prefix: str,
) -> RmbgResult:
    result = rmbg_client.remove_background(
        crop,
        output_name,
        timeout_s=timeout_s,
        model_path=model_path,
        artifact_prefix=artifact_prefix,
    )
    if isinstance(result, RmbgResult):
        return result
    if isinstance(result, Mapping):
        image = result.get("image")
        if not isinstance(image, Image.Image):
            raise RuntimeError("RMBG client response mapping must include a PIL image")
        artifacts = result.get("artifacts")
        return RmbgResult(
            image=image,
            artifacts=dict(artifacts) if isinstance(artifacts, Mapping) else {},
            elapsed_ms=float(result.get("elapsed_ms", 0.0)),
        )
    if isinstance(result, Image.Image):
        return RmbgResult(image=result, artifacts={}, elapsed_ms=0.0)
    raise RuntimeError(f"RMBG client returned unsupported result type: {type(result).__name__}")


def _crop_metadata(
    root: Path,
    source_path: Path,
    crop: Image.Image,
    crop_bbox: tuple[int, int, int, int],
) -> dict[str, Any]:
    return {
        "source_image": _path_ref(root, source_path),
        "crop_bbox_xyxy": list(crop_bbox),
        "width": crop.width,
        "height": crop.height,
    }


def _raster_result(
    root: Path,
    *,
    processor_type: str,
    result_id: str,
    path: Path,
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"processor result image is missing: {path}")
    rel_path = _artifact_relpath(root, path)
    width, height = _image_size(path)
    return {
        "result_id": result_id,
        "processor_type": processor_type,
        "status": "ok",
        "kind": "raster",
        "path": rel_path,
        "files": [
            {
                "kind": "raster",
                "path": rel_path,
                "media_type": "image/png",
            }
        ],
        "metadata": _jsonable(metadata),
        "width": width,
        "height": height,
        "created_at": utc_now(),
    }


def _write_package(
    root: Path,
    plan: ElementPlan,
    *,
    processor_type: str,
    status: AssetStatus,
    processor_run: Mapping[str, Any],
    result: Mapping[str, Any] | None = None,
    editable_payload: Mapping[str, Any] | None = None,
    failure: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> AssetPackage:
    existing = _existing_package(root, plan.element_id)
    processor_runs = list(existing.get("processor_runs", []) if existing else [])
    all_results = list(existing.get("all_results", []) if existing else [])
    files = list(existing.get("files", []) if existing else [])
    package_metadata = dict(existing.get("metadata", {}) if existing else {})

    processor_runs.append(_jsonable(processor_run))
    if result is not None:
        result_payload = _jsonable(result)
        all_results.append(result_payload)
        _append_result_files(files, result_payload)

    if metadata:
        package_metadata.update(
            {
                "last_processor_type": processor_type,
                "last_status": status,
                "last_run_metadata": _jsonable(metadata),
            }
        )

    package = AssetPackage(
        asset_id=str(existing.get("asset_id") if existing else _asset_id(plan, processor_type)),
        element_id=plan.element_id,
        processor_type=processor_type,
        status=status,
        files=tuple(files),
        metadata=package_metadata,
        processor_runs=tuple(processor_runs),
        all_results=tuple(all_results),
        active_result=_jsonable(result) if status == "ok" and result is not None else None,
        editable_payload=_jsonable(editable_payload) if status == "ok" else None,
        failure=failure,
        created_at=str(existing.get("created_at") if existing else utc_now()),
    )
    return write_asset_package(root, package)


def _existing_package(root: Path, element_id: str) -> dict[str, Any] | None:
    package_path = element_dir(root, element_id) / "asset_package.json"
    if not package_path.is_file():
        return None
    return read_asset_package(root, element_id)


def _append_result_files(files: list[str], result: Mapping[str, Any]) -> None:
    path = result.get("path")
    if isinstance(path, str) and path and path not in files:
        files.append(path)
    result_files = result.get("files")
    if not isinstance(result_files, list):
        return
    for file_ref in result_files:
        if not isinstance(file_ref, Mapping):
            continue
        file_path = file_ref.get("path")
        if isinstance(file_path, str) and file_path and file_path not in files:
            files.append(file_path)


def _processor_run(
    processor_type: str,
    *,
    status: AssetStatus,
    started_at: str,
    ended_at: str,
    input_refs: Mapping[str, Any],
    output_refs: Mapping[str, Any],
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "processor_type": processor_type,
        "status": status,
        "started_at": started_at,
        "ended_at": ended_at,
        "input_refs": _jsonable(input_refs),
        "output_refs": _jsonable(output_refs),
        "metadata": _jsonable(metadata),
    }


def _input_refs(
    root: Path,
    plan: ElementPlan,
    source_image_path: str | Path | None,
) -> dict[str, Any]:
    refs: dict[str, Any] = {
        "element_id": plan.element_id,
        "processing_type": plan.processing_intent.processing_type,
        "source_candidate_ids": list(plan.source_candidate_ids),
    }
    if source_image_path is not None:
        refs["source_image"] = _source_path_ref(root, Path(source_image_path))
    return refs


def _resolve_source_image(root: Path, source_image_path: str | Path | None) -> Path:
    if source_image_path is not None:
        raw_path = Path(source_image_path).expanduser()
        if raw_path.is_absolute():
            resolved = raw_path.resolve(strict=False)
        else:
            resolved = (root / raw_path).resolve(strict=False)
            resolved.relative_to(root)
        if not resolved.is_file():
            raise FileNotFoundError(f"source image is missing: {resolved}")
        return resolved

    for relative_path in (Path("inputs") / "figure.png", Path("inputs") / "original.png"):
        candidate = (root / relative_path).resolve(strict=False)
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("source image is missing: inputs/figure.png or inputs/original.png")


def _result_dir(root: Path, element_id: str, result_id: str) -> Path:
    path = element_dir(root, element_id) / "results" / result_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _new_result_id(processor_type: str) -> str:
    return f"{processor_type}_{uuid.uuid4().hex[:12]}"


def _asset_id(plan: ElementPlan, processor_type: str) -> str:
    return f"{plan.element_id}:{processor_type}"


def _rmbg_timeout_s(plan: ElementPlan) -> float:
    value = plan.processing_intent.parameters.get("timeout_s")
    if value is None:
        value = plan.processing_intent.parameters.get("rmbg_timeout_s", 60.0)
    return float(value)


def _rmbg_model_path(plan: ElementPlan) -> str:
    value = plan.processing_intent.parameters.get("rmbg_model_path")
    if value is None:
        value = plan.processing_intent.parameters.get("model_path", "")
    return str(value)


def _prompt_from_plan(plan: ElementPlan) -> str:
    prompt = str(plan.processing_intent.parameters.get("prompt") or "").strip()
    if prompt:
        return prompt
    return (
        f"Create a clean {plan.processing_intent.object_type} asset for "
        f"{plan.element_type} element {plan.element_id}. {plan.change_reason}"
    ).strip()


def _runtime_config(plan: ElementPlan) -> dict[str, Any] | None:
    value = plan.processing_intent.parameters.get("runtime_config")
    if isinstance(value, Mapping):
        return dict(value)
    return None


def _provider_payload(provider_result: Any, *, root: Path) -> dict[str, Any]:
    if hasattr(provider_result, "to_dict"):
        payload = provider_result.to_dict()
    elif isinstance(provider_result, Mapping):
        payload = dict(provider_result)
    else:
        payload = {
            "type": type(provider_result).__name__,
            "repr": repr(provider_result),
        }
    if not isinstance(payload, Mapping):
        raise ValueError("image provider result must serialize to a mapping")
    return _normalize_provider_metadata(dict(payload), root=root)


def _normalize_provider_metadata(value: Any, *, root: Path) -> Any:
    if isinstance(value, Path):
        return _path_ref(root, value)
    if isinstance(value, Mapping):
        return {
            str(key): _normalize_provider_metadata(item, root=root)
            for key, item in value.items()
        }
    if isinstance(value, tuple | list):
        return [_normalize_provider_metadata(item, root=root) for item in value]
    if isinstance(value, str):
        path = Path(value).expanduser()
        if path.is_absolute():
            return _path_ref(root, path)
    return value


def _first_provider_image_path(
    provider_result: Any,
    payload: Mapping[str, Any],
    *,
    root: Path,
    result_dir: Path,
) -> Path:
    first_path: Path | None = None
    seen: set[Path] = set()
    for raw_path in _provider_image_paths(provider_result, payload):
        path = _resolve_provider_path(root, raw_path)
        if path in seen:
            continue
        seen.add(path)
        if not path.is_file():
            continue
        _require_provider_result_path(result_dir, path)
        if first_path is None:
            first_path = path
    if first_path is not None:
        return first_path
    raise ValueError("image provider did not return an image file path")


def _provider_image_paths(
    provider_result: Any,
    payload: Mapping[str, Any],
) -> list[str | Path]:
    paths: list[str | Path] = []
    for image in getattr(provider_result, "images", ()) or ():
        raw_path = getattr(image, "path", None)
        if raw_path:
            paths.append(raw_path)

    images = payload.get("images")
    if isinstance(images, list):
        for image in images:
            if not isinstance(image, Mapping):
                continue
            raw_path = image.get("path") or image.get("source_path")
            if raw_path:
                paths.append(str(raw_path))
    return paths


def _resolve_provider_path(root: Path, raw_path: str | Path) -> Path:
    path = Path(raw_path).expanduser()
    if path.is_absolute():
        return path.resolve(strict=False)
    return (root / path).resolve(strict=False)


def _require_provider_result_path(result_dir: Path, path: Path) -> None:
    try:
        path.relative_to(result_dir)
    except ValueError as exc:
        raise ValueError(
            f"image provider result file must be under assigned result directory: {path}"
        ) from exc


def _image_size(path: Path) -> tuple[int, int]:
    with Image.open(path) as image:
        return image.size


def _path_ref(root: Path, path: Path) -> str:
    resolved = path.expanduser().resolve(strict=False)
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError:
        return str(resolved)


def _source_path_ref(root: Path, path: Path) -> str:
    raw_path = path.expanduser()
    if raw_path.is_absolute():
        return _path_ref(root, raw_path)
    resolved = (root / raw_path).resolve(strict=False)
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError:
        return str(resolved)


def _artifact_relpath(root: Path, path: Path) -> str:
    resolved = path.expanduser().resolve(strict=False)
    return resolved.relative_to(root).as_posix()


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_jsonable(item) for item in value]
    return value


def _default_image_generate() -> Callable[..., Any]:
    from drawai.codex_python_sdk_imagegen import invoke_codex_python_sdk_imagegen

    return invoke_codex_python_sdk_imagegen


def _default_image_edit() -> Callable[..., Any]:
    from drawai.codex_python_sdk_imagegen import invoke_codex_python_sdk_image_edit

    return invoke_codex_python_sdk_image_edit


__all__ = [
    "AssetProcessor",
    "ChartRebuildReservedProcessor",
    "CropNoBgProcessor",
    "CropProcessor",
    "ImageEditProcessor",
    "ImageGenerateProcessor",
    "NoProcessProcessor",
    "SvgSelfDrawProcessor",
    "processor_for_type",
]
