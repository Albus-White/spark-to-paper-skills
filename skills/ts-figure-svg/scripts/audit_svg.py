#!/usr/bin/env python3
"""audit_svg.py — the gate for a NATIVE semantic SVG figure (the "paperbanana+" redraw).

Every check here exists because it caught a real defect in the recorded PaperBanana->SVG sessions:
overflow, text-on-text, icon-through-text, floating elements, dangling connectors, stroke-scaled
arrowheads, sub-legible print size, and glyph-triggered font fallback. "It renders" is not a gate.

Stdlib only. Text boxes are measured with Adobe core-14 **Times** advance widths -- exact for the
mandated Times New Roman / Nimbus Roman stack (they are metric-compatible), so no renderer is needed.

  python3 audit_svg.py fig.svg [--min-font-px 20] [--pad 3] [--json out.json]
  python3 audit_svg.py --selftest

Exit 0 = clean, 1 = errors, 2 = usage/parse failure.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

SVG_NS = "http://www.w3.org/2000/svg"
XLINK = "http://www.w3.org/1999/xlink"

# A raster masquerading as a figure, a live document, or an escape hatch out of "editable vector".
FORBIDDEN_TAGS = {"image", "foreignObject", "script", "iframe", "video", "audio", "canvas"}
SHAPE_TAGS = {"rect", "circle", "ellipse", "line", "polyline", "polygon", "path"}
# Shapes that can *cover* text when drawn later. A stroked-only path cannot.
FILLABLE = {"rect", "circle", "ellipse", "polygon", "path"}

# Adobe core-14 advance widths (units/1000 em) for codepoints 32..126.
_W_ROMAN = (
    "250 333 408 500 500 833 778 333 333 333 500 564 250 333 250 278 500 500 500 500 500 500 500 "
    "500 500 500 278 278 564 564 564 444 921 722 667 667 722 611 556 722 722 333 389 722 611 889 "
    "722 722 556 722 667 556 611 722 722 944 722 722 611 333 278 333 469 500 333 444 500 444 500 "
    "444 333 500 500 278 278 500 278 778 500 500 500 500 333 389 278 500 500 722 500 500 444 480 "
    "200 480 541"
)
_W_BOLD = (
    "250 333 555 500 500 1000 833 333 333 333 500 570 250 333 250 278 500 500 500 500 500 500 500 "
    "500 500 500 333 333 570 570 570 500 930 722 667 722 722 667 611 778 778 389 500 778 667 944 "
    "722 778 611 778 722 556 667 722 722 1000 722 722 667 333 278 333 581 500 333 500 556 444 556 "
    "444 333 500 556 278 333 556 278 833 556 500 556 556 444 389 333 556 500 722 500 500 444 394 "
    "220 394 520"
)
WIDTHS = {k: [int(x) for x in v.split()] for k, v in (("normal", _W_ROMAN), ("bold", _W_BOLD))}
ASCENT, DESCENT = 0.683, 0.217          # Times cap/ascender and descender, in em
SUB_FLOOR = 0.7                         # a sub/superscript may go this far under the body floor

# Codepoints outside what a Times text font reliably covers -> silent fallback to another family in
# the exported PDF (the historical "check-mark rendered in DejaVu Sans" defect). Draw these as paths.
_GLYPH_OK = set("‘’“”–—…·×±° ")


def _local(tag) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _num(v, default=None):
    if v is None:
        return default
    m = re.match(r"\s*(-?\d*\.?\d+(?:[eE][-+]?\d+)?)", str(v))
    return float(m.group(1)) if m else default


def _len_px(v, parent_px, default=None):
    """Resolve a CSS length to px. pt->px at 96/72; em/% relative to the parent font size."""
    if v is None:
        return default
    s = str(v).strip()
    n = _num(s)
    if n is None:
        return default
    if s.endswith("pt"):
        return n * 96.0 / 72.0
    if s.endswith("em"):
        return n * parent_px
    if s.endswith("%"):
        return n * parent_px / 100.0
    return n


# ---------------------------------------------------------------- geometry


class Box:
    __slots__ = ("x0", "y0", "x1", "y1")

    def __init__(self, x0, y0, x1, y1):
        self.x0, self.y0, self.x1, self.y1 = min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)

    @property
    def w(self):
        return self.x1 - self.x0

    @property
    def h(self):
        return self.y1 - self.y0

    @property
    def area(self):
        return self.w * self.h

    def inter_area(self, o) -> float:
        return max(0.0, min(self.x1, o.x1) - max(self.x0, o.x0)) * \
               max(0.0, min(self.y1, o.y1) - max(self.y0, o.y0))

    def margins(self, outer):
        """How far each edge sits inside `outer`. Negative == sticking out."""
        return (self.x0 - outer.x0, self.y0 - outer.y0, outer.x1 - self.x1, outer.y1 - self.y1)

    def as_list(self):
        return [round(v, 2) for v in (self.x0, self.y0, self.x1, self.y1)]


def _hull(points) -> Box | None:
    pts = [p for p in points if p is not None]
    if not pts:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return Box(min(xs), min(ys), max(xs), max(ys))


IDENT = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def mat_mul(m, n):
    a, b, c, d, e, f = m
    A, B, C, D, E, F = n
    return (a * A + c * B, b * A + d * B, a * C + c * D, b * C + d * D, a * E + c * F + e, b * E + d * F + f)


def mat_apply(m, x, y):
    a, b, c, d, e, f = m
    return (a * x + c * y + e, b * x + d * y + f)


def parse_transform(s: str):
    """translate/scale/rotate/matrix. skewX/skewY are reported by the caller, not silently applied."""
    m = IDENT
    for name, args in re.findall(r"(\w+)\s*\(([^)]*)\)", s or ""):
        v = [float(x) for x in re.findall(r"-?\d*\.?\d+(?:[eE][-+]?\d+)?", args)]
        if name == "translate" and v:
            m = mat_mul(m, (1, 0, 0, 1, v[0], v[1] if len(v) > 1 else 0))
        elif name == "scale" and v:
            m = mat_mul(m, (v[0], 0, 0, v[1] if len(v) > 1 else v[0], 0, 0))
        elif name == "rotate" and v:
            a = math.radians(v[0])
            cos, sin = math.cos(a), math.sin(a)
            r = (cos, sin, -sin, cos, 0, 0)
            if len(v) >= 3:
                r = mat_mul(mat_mul((1, 0, 0, 1, v[1], v[2]), r), (1, 0, 0, 1, -v[1], -v[2]))
            m = mat_mul(m, r)
        elif name == "matrix" and len(v) >= 6:
            m = mat_mul(m, tuple(v[:6]))
    return m


_PATH_TOK = re.compile(r"([MmLlHhVvCcSsQqTtAaZz])|(-?\d*\.?\d+(?:[eE][-+]?\d+)?)")
_ARGC = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4, "T": 2, "A": 7, "Z": 0}


def path_points(d: str):
    """Every on-curve point plus every control point: a conservative superset of the true bbox."""
    toks, out = _PATH_TOK.findall(d or ""), []
    i, cmd, cx, cy, sx, sy = 0, None, 0.0, 0.0, 0.0, 0.0
    nums = []
    seq = []
    for c, n in toks:
        seq.append(("c", c) if c else ("n", float(n)))
    while i < len(seq):
        kind, val = seq[i]
        if kind == "c":
            cmd = val
            i += 1
            if cmd in "Zz":
                cx, cy = sx, sy
                out.append((cx, cy))
            continue
        if cmd is None:
            i += 1
            continue
        up = cmd.upper()
        rel = cmd.islower()
        k = _ARGC.get(up, 0)
        nums = []
        while len(nums) < k and i < len(seq) and seq[i][0] == "n":
            nums.append(seq[i][1])
            i += 1
        if len(nums) < k:
            break
        if up == "M":
            cx, cy = (cx + nums[0], cy + nums[1]) if rel else (nums[0], nums[1])
            sx, sy = cx, cy
            out.append((cx, cy))
            cmd = "l" if rel else "L"       # implicit lineto for repeated pairs
        elif up == "L":
            cx, cy = (cx + nums[0], cy + nums[1]) if rel else (nums[0], nums[1])
            out.append((cx, cy))
        elif up == "H":
            cx = cx + nums[0] if rel else nums[0]
            out.append((cx, cy))
        elif up == "V":
            cy = cy + nums[0] if rel else nums[0]
            out.append((cx, cy))
        elif up in ("C", "S", "Q", "T"):
            pts = [(nums[j], nums[j + 1]) for j in range(0, k, 2)]
            abspts = [(cx + px, cy + py) if rel else (px, py) for px, py in pts]
            out.extend(abspts)
            cx, cy = abspts[-1]
        elif up == "A":
            rx, ry = abs(nums[0]), abs(nums[1])
            ex, ey = (cx + nums[5], cy + nums[6]) if rel else (nums[5], nums[6])
            # conservative: the arc stays within rx/ry of the chord
            for px, py in ((cx, cy), (ex, ey)):
                out.extend([(px - rx, py - ry), (px + rx, py + ry)])
            cx, cy = ex, ey
    return out


def shape_box(el, tag) -> Box | None:
    g = lambda k, d=None: _num(el.get(k), d)  # noqa: E731
    if tag == "rect":
        x, y, w, h = g("x", 0), g("y", 0), g("width"), g("height")
        return Box(x, y, x + w, y + h) if w is not None and h is not None else None
    if tag == "circle":
        cx, cy, r = g("cx", 0), g("cy", 0), g("r")
        return Box(cx - r, cy - r, cx + r, cy + r) if r is not None else None
    if tag == "ellipse":
        cx, cy, rx, ry = g("cx", 0), g("cy", 0), g("rx"), g("ry")
        return Box(cx - rx, cy - ry, cx + rx, cy + ry) if rx is not None and ry is not None else None
    if tag == "line":
        return Box(g("x1", 0), g("y1", 0), g("x2", 0), g("y2", 0))
    if tag in ("polyline", "polygon"):
        v = [float(x) for x in re.findall(r"-?\d*\.?\d+(?:[eE][-+]?\d+)?", el.get("points", ""))]
        return _hull(list(zip(v[0::2], v[1::2])))
    if tag == "path":
        return _hull(path_points(el.get("d", "")))
    return None


def endpoints(el, tag):
    """Start/end of a connector, for the dangling-connector check."""
    if tag == "line":
        return [(_num(el.get("x1"), 0), _num(el.get("y1"), 0)),
                (_num(el.get("x2"), 0), _num(el.get("y2"), 0))]
    if tag == "path":
        pts = path_points(el.get("d", ""))
        return [pts[0], pts[-1]] if pts else []
    return []


# ---------------------------------------------------------------- CSS + cascade

_INHERIT = ("font-size", "font-family", "font-weight", "text-anchor", "letter-spacing",
            "fill", "fill-opacity", "opacity")


def parse_css(text: str) -> dict:
    """`.cls, text { k: v }` -> {selector: {k: v}}. Enough for the class/tag styling these figures use."""
    rules = {}
    for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", re.sub(r"/\*.*?\*/", "", text or "", flags=re.S)):
        decls = {}
        for kv in body.split(";"):
            if ":" in kv:
                k, v = kv.split(":", 1)
                decls[k.strip().lower()] = v.strip()
        for s in sel.split(","):
            s = s.strip()
            if s:
                rules.setdefault(s, {}).update(decls)
    return rules


def declared(el, css: dict, tag: str) -> tuple[dict, list]:
    """Real SVG cascade: presentation attribute < tag rule < class rule < style attribute.

    A presentation attribute loses to ANY stylesheet rule. That is the white-text trap: a global
    `text { fill: #1a1a1a }` silently beats `<text fill="#fff">` on a coloured pill, and the label
    renders dark-on-dark — invisible at 1x, obvious at 4x. Returns the overridden attrs so the caller
    can flag it.
    """
    out, beaten = {}, []
    for k in _INHERIT + ("stroke",):
        if el.get(k) is not None:
            out[k] = el.get(k)
    ruled = dict(css.get(tag, {}))
    for cls in (el.get("class") or "").split():
        ruled.update(css.get("." + cls, {}))
    for k, v in ruled.items():
        if k in out and out[k] != v:
            beaten.append((k, out[k], v))
        out[k] = v
    for kv in (el.get("style") or "").split(";"):
        if ":" in kv:
            k, v = kv.split(":", 1)
            out[k.strip().lower()] = v.strip()
    return out, beaten


def text_width(s, fs, weight) -> float:
    tbl = WIDTHS["bold" if str(weight).strip() in ("bold", "600", "700", "800", "900") else "normal"]
    adv = 0.0
    for ch in s:
        o = ord(ch)
        adv += tbl[o - 32] if 32 <= o <= 126 else 500      # unknown glyph ~ digit width
    return adv * fs / 1000.0


# ---------------------------------------------------------------- the audit


class Audit:
    def __init__(self, args):
        self.a = args
        self.errors, self.warnings = [], []
        self.texts, self.shapes = [], []      # (order, id, Box, meta)
        self.ids, self.refs, self.defs = {}, [], set()

    def err(self, code, detail, **kw):
        self.errors.append({"code": code, "detail": detail, **kw})

    def warn(self, code, detail, **kw):
        self.warnings.append({"code": code, "detail": detail, **kw})

    # -- traversal ------------------------------------------------
    def walk(self, el, mat, inherited, order=[0], in_defs=False):  # noqa: B006 (document-order counter)
        tag = _local(el.tag)
        if tag in FORBIDDEN_TAGS:
            self.err("forbidden_element",
                     f"<{tag}> — a native figure must be real vector objects, not an embedded/foreign "
                     f"payload (a traced or pasted raster is the defect this blocks)", id=el.get("id"))
        eid = el.get("id")
        if eid:
            if eid in self.ids:
                self.err("duplicate_id", f"id='{eid}' used more than once (breaks url(#) references)")
            self.ids[eid] = tag

        tr = el.get("transform")
        if tr and re.search(r"\bskew[XY]\s*\(", tr):
            self.warn("skew_transform", f"skew() on <{tag}> id={eid!r}: bounding boxes are approximate here")
        mat = mat_mul(mat, parse_transform(tr)) if tr else mat

        d, beaten = declared(el, self.css, tag)
        for k, attr_v, rule_v in beaten:
            if k in ("fill", "font-size", "font-family", "font-weight"):
                self.err("presentation_attr_beaten",
                         f"<{tag} id={eid!r}> {k}=\"{attr_v}\" is a presentation attribute, so the "
                         f"stylesheet's {k}:{rule_v} wins — set a class instead (e.g. .inverse{{fill:#fff}})")
        cur = dict(inherited)
        for k in _INHERIT:
            if k in d:
                cur[k] = d[k]
        if "font-size" in d:
            cur["font-size-px"] = _len_px(d["font-size"], inherited.get("font-size-px", 16.0),
                                          inherited.get("font-size-px", 16.0))

        for k in ("href", f"{{{XLINK}}}href", "fill", "stroke", "marker-end", "marker-start", "marker-mid"):
            v = el.get(k) or d.get(k.split("}")[-1])
            if not v:
                continue
            v = v.strip()
            if v.startswith("data:"):
                self.err("data_uri", f"<{tag}> {k}=data:… — an inlined blob is not an editable object",
                         id=eid)
            elif re.match(r"^(https?:|//|file:)", v):
                self.err("external_reference", f"<{tag}> {k}={v[:60]} — the SVG must be self-contained", id=eid)
            else:
                # url(#id) anywhere; a bare #id only from href (a bare '#abc' in fill is a hex colour)
                m = re.match(r"url\(\s*#([^)\s]+)\s*\)", v) or \
                    (re.match(r"^#(.+)$", v) if k.endswith("href") else None)
                if m:
                    self.refs.append((m.group(1), tag, eid, k))

        # Templates (defs/symbol/marker/clipPath/…) are not painted where they sit — geometry-checking
        # them reports every glyph and arrowhead as "off canvas". Structure checks still apply.
        in_defs = in_defs or tag in ("defs", "symbol", "marker", "clipPath", "mask", "pattern")

        if tag == "text" and not in_defs:
            self._text(el, mat, cur, order)
        elif tag == "use" and not in_defs:
            ref = (el.get("href") or el.get(f"{{{XLINK}}}href") or "").lstrip("#")
            src = self.by_id.get(ref)
            b = shape_box(src, _local(src.tag)) if src is not None else None
            if b:
                m2 = mat_mul(mat, (1, 0, 0, 1, _num(el.get("x"), 0.0), _num(el.get("y"), 0.0)))
                order[0] += 1
                self.shapes.append({"order": order[0], "id": eid or f"use:{ref}", "tag": "use",
                                    "box": self._tbox(b, m2), "fill": str(cur.get("fill") or "none").lower(),
                                    "opacity": _num(cur.get("fill-opacity", cur.get("opacity", 1)), 1.0),
                                    "ends": [], "marker": ""})
        elif tag in SHAPE_TAGS and not in_defs:
            b = shape_box(el, tag)
            if b:
                # An arrowhead paints outside the path's own bbox, so a connector whose coordinates sit
                # inside the viewBox can still have its head clipped at the canvas edge.
                grow = max((self._marker_size(d.get(f"marker-{e}") or el.get(f"marker-{e}"))
                            for e in ("start", "mid", "end")), default=0.0)
                if grow:
                    b = _hull([(b.x0 - grow, b.y0 - grow), (b.x1 + grow, b.y1 + grow)])
                order[0] += 1
                self.shapes.append({
                    "order": order[0], "id": eid, "tag": tag, "box": self._tbox(b, mat),
                    "fill": str(cur.get("fill") or "none").strip().lower(),
                    "opacity": _num(cur.get("fill-opacity", cur.get("opacity", 1)), 1.0),
                    "ends": [mat_apply(mat, *p) for p in endpoints(el, tag)],
                    "marker": (d.get("marker-end") or el.get("marker-end") or ""),
                })
        elif tag == "marker":
            self._marker(el)

        for child in el:
            self.walk(child, mat, cur, order, in_defs)

    def _marker_size(self, ref) -> float:
        m = re.match(r"url\(\s*#([^)\s]+)\s*\)", str(ref or "").strip())
        el = self.by_id.get(m.group(1)) if m else None
        if el is None:
            return 0.0
        return max(_num(el.get("markerWidth"), 3.0), _num(el.get("markerHeight"), 3.0))

    def _tbox(self, b: Box, mat) -> Box:
        c = [mat_apply(mat, x, y) for x, y in
             ((b.x0, b.y0), (b.x1, b.y0), (b.x0, b.y1), (b.x1, b.y1))]
        return _hull(c)

    def _text(self, el, mat, cur, order):
        fs_user = cur.get("font-size-px", 16.0)
        weight, anchor = cur.get("font-weight", "normal"), cur.get("text-anchor", "start")
        fam = str(cur.get("font-family", ""))
        if self.a.font_family and fam:
            first = fam.split(",")[0].strip().strip("'\"").lower()
            if first != self.a.font_family.lower():
                self.err("font_stack", f"font-family starts with {first!r}, must start with "
                                       f"{self.a.font_family!r} (id={el.get('id')!r})")
        elif self.a.font_family and not fam:
            self.warn("font_unset", f"<text id={el.get('id')!r}> inherits no font-family")

        eff_px = fs_user * self.scale
        if eff_px + 1e-6 < self.a.min_font_px:
            self.err("font_too_small",
                     f"{eff_px:.1f}px effective (< {self.a.min_font_px}) — shrinking text to make it fit is "
                     f"the forbidden fix; grow the canvas, re-wrap, or cut words instead", id=el.get("id"))

        # SVG text advances horizontally across its tspans. A tspan restarts the line only when it sets
        # its own x/y; dx/dy merely nudge, so a subscript keeps flowing (getting this wrong reports every
        # `E<tspan dy=6>1</tspan>` as a text-on-text collision).
        segs = [{"ax": _num(el.get("x"), 0.0), "ay": _num(el.get("y"), 0.0), "dx": 0.0, "dy": 0.0,
                 "s": (el.text or "").strip(), "fs": fs_user, "w": weight}]
        for sp in el:
            if _local(sp.tag) != "tspan":
                continue
            d, _ = declared(sp, self.css, "tspan")
            sfs = _len_px(d.get("font-size"), fs_user, fs_user) or fs_user
            if sfs * self.scale + 1e-6 < self.a.min_font_px * SUB_FLOOR:
                self.err("font_too_small",
                         f"<tspan> at {sfs * self.scale:.1f}px is below even the sub/superscript floor "
                         f"({self.a.min_font_px * SUB_FLOOR:.0f}px)", id=el.get("id"))
            shift = str(sp.get("baseline-shift") or d.get("baseline-shift") or "").strip()
            bs = 0.20 * sfs if shift == "sub" else -0.33 * sfs if shift == "super" else 0.0
            segs.append({"ax": _num(sp.get("x")), "ay": _num(sp.get("y")),
                         "dx": _num(sp.get("dx"), 0.0), "dy": _num(sp.get("dy"), 0.0) + bs,
                         "s": (sp.text or "").strip(), "fs": sfs, "w": d.get("font-weight", weight)})
            if sp.tail and sp.tail.strip():
                segs.append({"ax": None, "ay": None, "dx": 0.0, "dy": 0.0,
                             "s": sp.tail.strip(), "fs": fs_user, "w": weight})

        # Lay out on one advancing pen, grouping into lines (a new absolute x/y starts a line), then
        # shift each line by text-anchor -- the anchor applies to the whole line, not to each segment.
        lines, pen_x, pen_y = [], 0.0, 0.0
        for s in segs:
            if s["ax"] is not None or s["ay"] is not None or not lines:
                pen_x = (s["ax"] if s["ax"] is not None else pen_x) + s["dx"]
                pen_y = (s["ay"] if s["ay"] is not None else pen_y) + s["dy"]
                lines.append({"x0": pen_x, "runs": [], "adv": 0.0})
            else:
                pen_x += s["dx"]
                pen_y += s["dy"]
            if not s["s"]:
                continue
            w = text_width(s["s"], s["fs"], s["w"])
            lines[-1]["runs"].append({"x": pen_x, "y": pen_y, "s": s["s"], "fs": s["fs"], "adv": w})
            lines[-1]["adv"] = pen_x + w - lines[-1]["x0"]
            pen_x += w

        for line in lines:
            shift = (-line["adv"] / 2.0 if anchor == "middle"
                     else -line["adv"] if anchor == "end" else 0.0)
            for r in line["runs"]:
                bad = sorted({c for c in r["s"] if ord(c) > 0x7F and c not in _GLYPH_OK})
                if bad:
                    self.err("glyph_fallback_risk",
                             f"{''.join(bad)!r} in {r['s'][:40]!r} — outside the Times text repertoire, so "
                             f"the PDF silently falls back to another family; draw the mark as a <path> or "
                             f"reword", id=el.get("id"))
                raw = Box(r["x"] + shift, r["y"] - ASCENT * r["fs"],
                          r["x"] + shift + r["adv"], r["y"] + DESCENT * r["fs"])
                order[0] += 1
                self.texts.append({"order": order[0], "id": el.get("id"), "box": self._tbox(raw, mat),
                                   "s": r["s"][:60], "fs": r["fs"],
                                   "px": round(r["fs"] * self.scale, 1)})

    def _marker(self, el):
        mid = el.get("id")
        self.defs.add(mid)
        units = (el.get("markerUnits") or "strokeWidth").strip()
        mw, mh = _num(el.get("markerWidth"), 3.0), _num(el.get("markerHeight"), 3.0)
        if units != "userSpaceOnUse":
            self.err("marker_scales_with_stroke",
                     f"<marker id={mid!r}> markerUnits='{units}' — the head multiplies by stroke-width, "
                     f"so a 3px stroke turns a 6-unit arrow into ~18px of overlap. Use userSpaceOnUse.")
        if max(mw, mh) > self.a.max_marker:
            self.err("marker_too_big",
                     f"<marker id={mid!r}> {mw}x{mh} > {self.a.max_marker} — oversized heads collide with "
                     f"cards and text; small heads are the house style.")

    # -- cross-object checks ---------------------------------------
    def geometry(self):
        canvas, pad = self.canvas, self.a.pad
        for t in self.texts:
            b = t["box"]
            if min(b.margins(canvas)) < -self.a.tol:
                self.err("canvas_overflow", f"text {t['s']!r} leaves the canvas",
                         id=t["id"], bbox=b.as_list())
        for s in self.shapes:
            if min(s["box"].margins(canvas)) < -self.a.tol:
                self.err("canvas_overflow", f"<{s['tag']}> leaves the canvas",
                         id=s["id"], bbox=s["box"].as_list())

        # text vs text
        for i in range(len(self.texts)):
            for j in range(i + 1, len(self.texts)):
                a, b = self.texts[i], self.texts[j]
                ia = a["box"].inter_area(b["box"])
                if ia > 1.0 and ia > 0.08 * min(a["box"].area or 1, b["box"].area or 1):
                    self.err("text_overlap", f"{a['s']!r} overlaps {b['s']!r} ({ia:.0f}px²)",
                             id=a["id"], bbox=a["box"].as_list())

        # text vs its nearest enclosing card, and later shapes drawn over text
        containers = [s for s in self.shapes if s["tag"] in ("rect", "ellipse", "circle")
                      and s["box"].area > 0]
        for t in self.texts:
            b = t["box"]
            cx, cy = (b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2
            encl = [s for s in containers
                    if s["box"].x0 <= cx <= s["box"].x1 and s["box"].y0 <= cy <= s["box"].y1
                    and s["order"] < t["order"] and s["box"].area >= b.area]
            if not encl:
                self.warn("floating_text",
                          f"{t['s']!r} sits in no card — free-floating labels are the 'drifting element' "
                          f"defect; anchor it to a container or the alignment grid", id=t["id"])
            else:
                host = min(encl, key=lambda s: s["box"].area)
                m = min(b.margins(host["box"]))
                need = max(pad, self.a.pad_em * t["fs"])
                if m < need:
                    self.err("container_overflow" if m < 0 else "container_hug",
                             f"{t['s']!r} clears its card by {m:.1f} (need {need:.1f}) — "
                             f"'just barely inside' is not a pass",
                             id=t["id"], bbox=b.as_list(), container=host["id"])
            for s in self.shapes:
                if (s["order"] > t["order"] and s["tag"] in FILLABLE
                        and s["fill"] not in ("none", "") and (s["opacity"] or 1) > 0.85
                        and s["box"].inter_area(b) > 0.5 * (b.area or 1)):
                    self.err("shape_over_text",
                             f"<{s['tag']} id={s['id']!r}> is painted after {t['s']!r} and covers it — "
                             f"z-order defect (icons/cards cutting labels in half)",
                             id=t["id"], bbox=b.as_list())
                    break

        # connectors that stop in mid-air instead of docking on a port
        boxes = [s["box"] for s in containers]
        for s in self.shapes:
            if s["tag"] not in ("line", "path") or not s["ends"]:
                continue
            for px, py in s["ends"]:
                if boxes and min(self._edge_dist(px, py, bb) for bb in boxes) > self.a.port_gap:
                    self.warn("dangling_connector",
                              f"<{s['tag']} id={s['id']!r}> endpoint ({px:.0f},{py:.0f}) docks on nothing "
                              f"(> {self.a.port_gap} from any card edge)", id=s["id"])
                    break

    @staticmethod
    def _edge_dist(x, y, b: Box) -> float:
        dx = max(b.x0 - x, 0, x - b.x1)
        dy = max(b.y0 - y, 0, y - b.y1)
        if dx == 0 and dy == 0:      # inside the card counts as docked
            return 0.0
        return math.hypot(dx, dy)

    # -- driver ----------------------------------------------------
    def run(self, path: Path) -> dict:
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError as exc:
            self.err("xml_parse_error", str(exc))
            return self.report(path)

        vb = re.split(r"[ ,]+", (root.get("viewBox") or "").strip())
        if len(vb) == 4:
            x, y, w, h = (float(v) for v in vb)
            self.canvas = Box(x, y, x + w, y + h)
        else:
            w, h = _num(root.get("width")), _num(root.get("height"))
            if not (w and h):
                self.err("no_canvas", "neither viewBox nor width/height — the canvas is undefined")
                return self.report(path)
            self.canvas = Box(0, 0, w, h)
        out_w = _len_px(root.get("width"), self.canvas.w, self.canvas.w) or self.canvas.w
        self.scale = out_w / self.canvas.w if self.canvas.w else 1.0

        self.css = {}
        for st in root.iter(f"{{{SVG_NS}}}style"):
            self.css.update(parse_css("".join(st.itertext())))
        self.by_id = {e.get("id"): e for e in root.iter() if e.get("id")}

        self.walk(root, IDENT, {"font-size-px": 16.0}, [0])
        for ref, tag, eid, attr in self.refs:
            if ref not in self.ids:
                self.err("unresolved_reference",
                         f"<{tag} id={eid!r}> {attr} points at #{ref}, which does not exist "
                         f"(a marker/gradient that silently renders as nothing)")
        if not self.texts:
            self.err("no_text", "no <text> at all — a figure whose labels are not live text is not editable")
        self.cleanliness()
        self.geometry()
        return self.report(path)

    def cleanliness(self):
        """prims / (prims + path-likes). A hand-drawn figure is mostly rectangles, lines and circles;
        an auto-traced raster is ~100% <path>. On the recorded pair: hand-authored 0.60+ vs a pixel
        trace at 59430 paths / 1 rect = 0.00002. This is the machine-checkable form of "never trace"."""
        prim = sum(1 for s in self.shapes if s["tag"] in ("rect", "circle", "ellipse", "line", "polyline"))
        complex_ = sum(1 for s in self.shapes if s["tag"] in ("path", "polygon"))
        self.clean = prim / (prim + complex_) if (prim + complex_) else 1.0
        if prim + complex_ >= 20 and self.clean < self.a.min_cleanliness:
            self.err("path_soup",
                     f"semantic cleanliness {self.clean:.3f} < {self.a.min_cleanliness} "
                     f"({prim} primitives vs {complex_} path/polygon) — this reads as a traced or "
                     f"machine-converted raster, not a figure drawn from the paper's structure")

    def report(self, path) -> dict:
        return {
            "ok": not self.errors,
            "svg": str(path),
            "stats": {
                "texts": len(self.texts), "shapes": len(self.shapes),
                "canvas": self.canvas.as_list() if getattr(self, "canvas", None) else None,
                "min_text_px": min((t["px"] for t in self.texts), default=None),
                "cleanliness": round(getattr(self, "clean", 1.0), 3),
                "bytes": Path(path).stat().st_size if Path(path).is_file() else None,
            },
            "errors": self.errors,
            "warnings": self.warnings,
        }


def build_parser():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("svg", nargs="?", help="the native SVG to audit")
    p.add_argument("--min-font-px", type=float, default=20.0,
                   help="legibility floor at the SVG's own output width (default 20)")
    p.add_argument("--font-family", default="Times New Roman",
                   help="required first entry of every font stack ('' to disable)")
    p.add_argument("--max-marker", type=float, default=8.0, help="max markerWidth/Height (default 8)")
    p.add_argument("--pad", type=float, default=4.0, help="min text-to-card margin, absolute (default 4)")
    p.add_argument("--pad-em", type=float, default=0.35,
                   help="min text-to-card margin as a fraction of font size (default 0.35); the "
                        "effective clearance is max(--pad, --pad-em x font-size)")
    p.add_argument("--min-cleanliness", type=float, default=0.35,
                   help="min primitives/(primitives+paths); below this the SVG is a traced raster")
    p.add_argument("--tol", type=float, default=0.5, help="canvas overflow tolerance (default 0.5)")
    p.add_argument("--port-gap", type=float, default=6.0,
                   help="max distance a connector end may sit from a card edge (default 6)")
    p.add_argument("--json", help="also write the report here")
    p.add_argument("--quiet", action="store_true", help="print only the one-line verdict")
    p.add_argument("--selftest", action="store_true")
    return p


def selftest() -> int:
    import tempfile
    args = build_parser().parse_args(["x.svg"])
    # Each defect below is one that actually shipped in the recorded sessions.
    dirty = """<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100" viewBox="0 0 200 100">
      <style>text{font-family:'Times New Roman';font-size:20px;fill:#111}</style>
      <defs><marker id="a" markerWidth="12" markerHeight="12" markerUnits="strokeWidth"/></defs>
      <rect id="card" x="10" y="10" width="60" height="30" fill="#eee"/>
      <text id="t1" x="12" y="30">overflowing label</text>
      <text id="t2" x="12" y="32">collides</text>
      <text id="t3" x="120" y="90" style="font-size:6px">tiny ✓</text>
      <text id="t4" x="120" y="20" fill="#fff">white on a pill</text>
      <line id="l1" x1="150" y1="20" x2="199" y2="20" marker-end="url(#nope)"/>
      <rect id="cover" x="115" y="80" width="60" height="20" fill="#333"/>
    </svg>"""
    # A connector whose own coordinates are inside the canvas, but whose arrowhead is not.
    clipped = """<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100" viewBox="0 0 200 100">
      <style>text{font-family:'Times New Roman';font-size:20px}</style>
      <defs><marker id="ar" markerWidth="8" markerHeight="6" markerUnits="userSpaceOnUse"
            ><path d="M0 0 L8 3 L0 6 Z"/></marker></defs>
      <rect id="c" x="10" y="20" width="120" height="60" fill="#eef"/>
      <text id="tx" x="25" y="58">Encoder</text>
      <path id="p" d="M130 50 L198 50" stroke="#333" marker-end="url(#ar)"/>
    </svg>"""
    # 40 <path> and one <rect>: the shape of an auto-traced raster.
    soup_paths = "".join(f'<path d="M{i} {i} L{i+2} {i+2} Z" fill="#888"/>' for i in range(40))
    soup = f"""<svg xmlns="http://www.w3.org/2000/svg" width="400" height="200" viewBox="0 0 400 200">
      <style>text{{font-family:'Times New Roman';font-size:22px}}</style>
      <rect id="bg" x="0" y="0" width="400" height="200" fill="#fff"/>
      <text id="lbl" x="20" y="180">traced</text>{soup_paths}</svg>"""
    clean = """<svg xmlns="http://www.w3.org/2000/svg" width="400" height="200" viewBox="0 0 400 200">
      <style>text{font-family:'Times New Roman';font-size:22px}.inverse{fill:#fff}</style>
      <defs><marker id="ar" markerWidth="6.4" markerHeight="4.8" refX="6.1" refY="2.4"
            orient="auto" markerUnits="userSpaceOnUse"><path d="M0 0 L6.4 2.4 L0 4.8 Z"/></marker></defs>
      <rect id="c1" x="20" y="40" width="150" height="60" fill="#eef"/>
      <text id="a1" x="35" y="78">Encoder</text>
      <rect id="c2" x="230" y="40" width="150" height="60" fill="#3a5a9b"/>
      <text id="a2" class="inverse" x="245" y="78">Decoder</text>
      <path id="p1" d="M170 70 L224 70" stroke="#333" marker-end="url(#ar)"/>
    </svg>"""
    with tempfile.TemporaryDirectory() as td:
        def w(name, src):
            p = Path(td) / name
            p.write_text(src)
            return p

        codes = {e["code"] for e in Audit(args).run(w("d.svg", dirty))["errors"]}
        for want in ("marker_scales_with_stroke", "marker_too_big", "container_overflow", "text_overlap",
                     "font_too_small", "glyph_fallback_risk", "unresolved_reference", "shape_over_text",
                     "presentation_attr_beaten"):
            assert want in codes, f"selftest: {want} not detected (got {sorted(codes)})"

        rc = Audit(args).run(w("clip.svg", clipped))
        assert any(e["code"] == "canvas_overflow" for e in rc["errors"]), \
            f"selftest: clipped arrowhead not detected ({rc['errors']})"

        rs = Audit(args).run(w("soup.svg", soup))
        assert any(e["code"] == "path_soup" for e in rs["errors"]), \
            f"selftest: path soup not detected ({rs['stats']})"

        ok = Audit(args).run(w("c.svg", clean))
        assert ok["ok"], f"selftest: clean SVG failed with {ok['errors']}"
        assert ok["stats"]["texts"] == 2, ok["stats"]
    print("selftest ok — 9 defect classes + clipped marker + path soup caught; clean SVG passes")
    return 0


def main() -> int:
    args = build_parser().parse_args()
    if args.selftest:
        return selftest()
    if not args.svg:
        build_parser().print_usage()
        return 2
    path = Path(args.svg)
    if not path.is_file():
        print(f"no such file: {path}", file=sys.stderr)
        return 2
    rep = Audit(args).run(path)
    if args.json:
        Path(args.json).write_text(json.dumps(rep, indent=2), encoding="utf-8")
    if not args.quiet:
        for e in rep["errors"]:
            print(f"ERROR  {e['code']}: {e['detail']}")
        for w in rep["warnings"]:
            print(f"warn   {w['code']}: {w['detail']}")
    s = rep["stats"]
    print(f"{'PASS' if rep['ok'] else 'FAIL'}  {path.name}  "
          f"{len(rep['errors'])} errors, {len(rep['warnings'])} warnings  "
          f"[{s['texts']} text, {s['shapes']} shapes, min {s['min_text_px']}px, "
          f"clean {s['cleanliness']}]")
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
