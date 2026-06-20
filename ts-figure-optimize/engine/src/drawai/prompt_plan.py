from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Sam3Prompt:
    id: str
    text: str
    confidence_threshold: float


DEFAULT_SAM3_PROMPTS: tuple[Sam3Prompt, ...] = (
    Sam3Prompt("arrow", "arrow", 0.30),
    Sam3Prompt("border", "border", 0.30),
    Sam3Prompt("content_box", "content box", 0.15),
    Sam3Prompt("grid", "grid", 0.30),
    Sam3Prompt("icon", "icon", 0.30),
    Sam3Prompt("picture", "picture", 0.30),
)
