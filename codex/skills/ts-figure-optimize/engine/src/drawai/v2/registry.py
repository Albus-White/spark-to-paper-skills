from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


@dataclass(frozen=True)
class ElementTypeSpec:
    name: str
    schema_version: str
    capabilities: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProcessingTypeSpec:
    name: str
    schema_version: str


@dataclass
class DrawAiRegistry:
    _element_types: dict[str, ElementTypeSpec] = field(default_factory=dict)
    _processing_types: dict[str, ProcessingTypeSpec] = field(default_factory=dict)

    @classmethod
    def core(cls) -> DrawAiRegistry:
        registry = cls()
        for element_type in (
            "text",
            "icon",
            "picture",
            "table",
            "chart",
            "diagram",
            "arrow",
            "frame",
            "grid",
            "symbol",
            "content_box",
            "unknown",
        ):
            registry.register_element_type(
                element_type,
                schema_version=f"drawai.core.element.{element_type}.v1",
            )
        for processing_type in (
            "no_process",
            "svg_self_draw",
            "crop",
            "crop_nobg",
            "image_generate",
            "image_edit",
            "chart_rebuild_reserved",
        ):
            registry.register_processing_type(
                processing_type,
                schema_version=f"drawai.core.processing.{processing_type}.v1",
            )
        return registry

    def register_element_type(
        self,
        name: str,
        *,
        schema_version: str,
        capabilities: Iterable[str] = (),
    ) -> None:
        if not name:
            raise ValueError("element_type is required")
        if not schema_version:
            raise ValueError("schema_version is required")
        self._element_types[name] = ElementTypeSpec(
            name=name,
            schema_version=schema_version,
            capabilities=tuple(capabilities),
        )

    def register_processing_type(self, name: str, *, schema_version: str) -> None:
        if not name:
            raise ValueError("processing_type is required")
        if not schema_version:
            raise ValueError("schema_version is required")
        self._processing_types[name] = ProcessingTypeSpec(
            name=name,
            schema_version=schema_version,
        )

    def has_element_type(self, name: str) -> bool:
        return name in self._element_types

    def has_processing_type(self, name: str) -> bool:
        return name in self._processing_types


def default_registry() -> DrawAiRegistry:
    return DrawAiRegistry.core()
