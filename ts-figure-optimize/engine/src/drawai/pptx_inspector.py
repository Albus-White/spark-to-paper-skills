from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import Any


def _count_ppt_tag(xml: str, qualified_name: str) -> int:
    return len(re.findall(rf"<{re.escape(qualified_name)}(?:[\s>/])", xml))


def inspect_pptx_structure(path: str | Path) -> dict[str, Any]:
    pptx_path = Path(path)
    with zipfile.ZipFile(pptx_path) as zf:
        names = zf.namelist()
        slide_names = [
            name
            for name in names
            if name.startswith("ppt/slides/slide") and name.endswith(".xml")
        ]
        media_names = [name for name in names if name.startswith("ppt/media/")]
        slide_xml = "\n".join(
            zf.read(name).decode("utf-8", errors="replace") for name in slide_names
        )

    shape_tag_count = _count_ppt_tag(slide_xml, "p:sp")
    picture_tag_count = _count_ppt_tag(slide_xml, "p:pic")
    connector_tag_count = _count_ppt_tag(slide_xml, "p:cxnSp")
    text_run_count = _count_ppt_tag(slide_xml, "a:t")
    svg_media_count = sum(1 for name in media_names if name.lower().endswith((".svg", ".svgz")))
    return {
        "slide_count": len(slide_names),
        "media_count": len(media_names),
        "svg_media_count": svg_media_count,
        "shape_tag_count": shape_tag_count,
        "picture_tag_count": picture_tag_count,
        "connector_tag_count": connector_tag_count,
        "text_run_count": text_run_count,
        "is_single_screenshot_like": picture_tag_count == 1 and shape_tag_count <= 2 and svg_media_count == 0,
    }
