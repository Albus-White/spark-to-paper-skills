#!/usr/bin/env python3
"""story_lint.py — validate the 8-field Story (deterministic gate before story->paper handoff).

    python3 story_lint.py <workdir>     # validates <workdir>/story.json

The Story is the structured proposal ts-paper consumes. This checks the schema is complete and
not polluted by LLM schema-echo noise (a product failure mode), so a malformed story fails loudly.
"""
from __future__ import annotations
import json, re, sys
from pathlib import Path

FIELDS = ["title", "abstract", "problem_framing", "gap_pattern", "solution",
          "method_skeleton", "innovation_claims", "experiments_plan"]
NOISE = {"string", "todo", "tbd", "n/a", "none", "...", "<...>", "placeholder", "lorem ipsum"}


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"ok": False, "error": "usage: story_lint.py <workdir>"})); sys.exit(2)
    wd = Path(sys.argv[1]).resolve()
    sp = wd / "story.json"
    if not sp.exists():
        print(json.dumps({"ok": False, "error": f"no story.json in {wd}"})); sys.exit(2)
    s = json.loads(sp.read_text())
    issues = []

    for f in FIELDS:
        if f not in s:
            issues.append(f"missing field: {f}"); continue
        v = s[f]
        if f == "innovation_claims":
            if not isinstance(v, list) or not v:
                issues.append("innovation_claims must be a non-empty list")
            elif any(not str(x).strip() or str(x).strip().lower() in NOISE for x in v):
                issues.append("innovation_claims has empty/placeholder entries")
        else:
            if not isinstance(v, str):
                issues.append(f"{f} must be a string")
            elif not v.strip():
                issues.append(f"{f} is empty")
            elif v.strip().lower() in NOISE:
                issues.append(f"{f} is a placeholder/noise token: {v!r}")

    # method_skeleton should read like steps, not one trivial line
    ms = str(s.get("method_skeleton", ""))
    if ms and len(ms.split()) < 12:
        issues.append("method_skeleton too thin (need concrete steps)")
    # title sanity
    t = str(s.get("title", ""))
    if t and (len(t.split()) > 20 or len(t) > 180):
        issues.append(f"title too long: {len(t.split())} words")
    # fabricated-result guard: no bare percentages / 'outperforms by X%'.
    # Check each field/claim string INDEPENDENTLY (not one joined blob) so a forecast cue in
    # one field can't mask a fabricated result stated in another (cross-field leak).
    pieces = [str(s.get(f, "")) for f in FIELDS if f != "innovation_claims"]
    pieces += [str(x) for x in (s.get("innovation_claims") or [])]
    # always-fire tells: bare %, SOTA-by / outperform-by (the original guard).
    fab_always = r"\d+(?:\.\d+)?\s*%|state-of-the-art by|outperform[s]? by"
    # additional result tells: "from X to Y" phrasing, x-multipliers, signed metric deltas
    # (BLEU/mAP/dB/points/F1/accuracy/AUC). Kept conservative: do NOT flag forward-looking
    # forecasts ("we expect a 2x reduction", "aims to improve from 0.81 to 0.93").
    fab_result = (
        r"\bfrom\s+\d+(?:\.\d+)?\s+to\s+\d+(?:\.\d+)?\b"
        r"|(?<![\w.])\d+(?:\.\d+)?\s*[x×]\b"
        r"|[+\-]\s?\d+(?:\.\d+)?\s*(?:BLEU|mAP|dB|points?|pts?|F1|accuracy|AUC)\b"
    )
    FORECAST = re.compile(
        r"\b(expect(?:ed|s)?|anticipat\w+|aim(?:s|ed)?|will|plan(?:s|ned)?|hop\w+|"
        r"target(?:s|ed|ing)?|project(?:s|ed|ing)?|forecast\w*|should|could|would|"
        r"intend\w*|seek\w*|goal|envision\w*)\b", re.I)
    fabricated = False
    for piece in pieces:
        if re.search(fab_always, piece, re.I):
            fabricated = True
            break
        for m in re.finditer(fab_result, piece, re.I):
            # a real (not forecast) claim unless a forecast cue precedes it nearby IN THE SAME piece
            if not FORECAST.search(piece[max(0, m.start() - 60):m.start()]):
                fabricated = True
                break
        if fabricated:
            break
    if fabricated:
        issues.append("story states a fabricated result/number (this is a proposal — keep it forward-looking)")

    report = {"ok": not issues, "n_issues": len(issues), "issues": issues,
              "fields_present": [f for f in FIELDS if f in s]}
    print(json.dumps(report, indent=2, ensure_ascii=False))
    sys.exit(0 if not issues else 1)


if __name__ == "__main__":
    main()
