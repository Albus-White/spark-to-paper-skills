from __future__ import annotations

from .document import (
    BOX_IR_COORDINATE_SYSTEM,
    BOX_IR_SCHEMA,
    BOX_IR_VERSION,
    CONTROLLED_BOX_TYPES,
    build_raw_box_ir,
    normalize_box_type,
    validate_box_ir,
)
from .merge import merge_box_ir
from .prompt_ir import SVG_TEMPLATE_IR_SCHEMA, build_svg_template_ir

__all__ = [
    "BOX_IR_COORDINATE_SYSTEM",
    "BOX_IR_SCHEMA",
    "BOX_IR_VERSION",
    "CONTROLLED_BOX_TYPES",
    "SVG_TEMPLATE_IR_SCHEMA",
    "build_raw_box_ir",
    "build_svg_template_ir",
    "merge_box_ir",
    "normalize_box_type",
    "validate_box_ir",
]
