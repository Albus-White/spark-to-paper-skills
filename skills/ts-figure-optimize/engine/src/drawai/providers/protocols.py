from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from PIL import Image

from drawai.rmbg_client import RmbgResult


@runtime_checkable
class JsonPostTransport(Protocol):
    def post_json(self, path: str, payload: dict[str, Any], timeout_s: float) -> tuple[dict[str, Any], float]:
        ...


@runtime_checkable
class OcrDetector(Protocol):
    def extract_boxes(self, image_path: Path) -> dict[str, Any]:
        ...


@runtime_checkable
class BackgroundRemover(Protocol):
    def remove_background(
        self,
        image: Image.Image,
        output_name: str,
        *,
        timeout_s: float,
        model_path: str = "",
        artifact_prefix: str | None = None,
    ) -> RmbgResult:
        ...


@runtime_checkable
class SvgGenerator(Protocol):
    def __call__(self, **kwargs: Any) -> Any:
        ...


@runtime_checkable
class PptExporter(Protocol):
    def __call__(self, svg_path: Path, output_path: Path) -> Any:
        ...
