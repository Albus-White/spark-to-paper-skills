#!/usr/bin/env python3
"""reflow_tex.py — normalize a LaTeX section BODY so each prose paragraph (and each \\item /
\\caption) is ONE physical line, instead of hard-wrapped at ~100 columns.

WHY. The write stage emits prose hard-wrapped mid-sentence every ~100 chars. In LaTeX a single
newline is just a space, so this has ZERO effect on the compiled PDF — but a human browsing the
`.tex` source sees every paragraph chopped into many short lines ("换行太频繁, 不像正常写作"). This
joins those soft-wrapped continuation lines back into one logical line per paragraph.

SAFE BY CONSTRUCTION. It only ever turns the single '\\n' between two CONTINUATION lines into a
space, and NEVER touches:
  * blank lines — paragraph breaks are preserved exactly;
  * whitespace/alignment-significant environments (equation/align/.../tabular/algorithmic/
    verbatim/...) — emitted verbatim, never joined;
  * lines that START a new logical unit — a \\subsection / \\begin / \\end / \\label /
    \\includegraphics / \\State... / \\toprule... line, a `%` comment line, or a line that ends
    with a forced break `\\\\`;
  * any line carrying an active (unescaped) `%` — left on its own line so a join can never comment
    out the following text.
\\item / \\bibitem / \\caption are "wrappable" boundaries: they start a fresh logical line that the
following soft-wrapped continuation lines fold back into (so a 4-line \\item becomes one line) —
without merging two separate \\items together.

Because a single newline == a space in LaTeX, the compiled PDF is unchanged (the suite's acceptance
test asserts pdftotext(before) == pdftotext(after)). Idempotent: reflow(reflow(x)) == reflow(x).

Usage:
  python reflow_tex.py <workdir>     # reflow every workdir/sections/*.tex (excl .proc) in place
  python reflow_tex.py <file.tex>    # reflow one file in place
  python reflow_tex.py               # stdin -> stdout
"""
from __future__ import annotations
import json, re, sys
from pathlib import Path

# Environments where line breaks / `&` alignment / spacing are SIGNIFICANT -> emit verbatim.
_VERBATIM_ENVS = {"equation", "align", "alignat", "gather", "multline", "eqnarray", "displaymath",
                  "split", "array", "tabular", "tabularx", "tabular*", "matrix", "bmatrix", "pmatrix",
                  "vmatrix", "cases", "algorithmic", "verbatim", "Verbatim", "lstlisting", "minted",
                  "tikzpicture"}
_BEGIN = re.compile(r"\\begin\{([^}]*)\}")
_END = re.compile(r"\\end\{([^}]*)\}")

# A STANDALONE line keeps its own line and nothing folds into it.
_STANDALONE = re.compile(
    r"^(?:%"                                               # comment line (incl %%)
    r"|\\(?:sub)*section\*?\b|\\paragraph\b"
    r"|\\label\b|\\includegraphics\b|\\centering\b|\\hline\b"
    r"|\\(?:top|mid|bottom)rule\b|\\cmidrule\b"
    r"|\\(?:State|Statex|For|EndFor|While|EndWhile|If|ElsIf|Else|EndIf|Loop|EndLoop|Repeat|Until"
    r"|Require|Ensure|Function|EndFunction|Procedure|EndProcedure|Return|Comment)\b"
    r"|\\par\b|\\noindent\b|\\medskip\b|\\smallskip\b|\\bigskip\b|\\vspace\b|\\hspace\b"
    r"|\\newpage\b|\\clearpage\b|\\vfill\b|\\hfill\b"
    r"|\\begin\b|\\end\b)")
# A WRAPPABLE line starts a logical line that following continuation lines fold into.
_WRAPPABLE = re.compile(r"^(?:\\item\b|\\bibitem\b|\\caption(?:of|setup)?\b)")
_ACTIVE_PCT = re.compile(r"(?<!\\)%")                      # an unescaped % (active comment)


def _depth_delta(line: str) -> int:
    d = 0
    for m in _BEGIN.finditer(line):
        if m.group(1) in _VERBATIM_ENVS:
            d += 1
    for m in _END.finditer(line):
        if m.group(1) in _VERBATIM_ENVS:
            d -= 1
    return d


def reflow(text: str) -> str:
    out: list[str] = []
    buf: list[str] = []
    depth = 0   # >0 == inside a whitespace-significant environment

    def flush():
        if buf:
            out.append(" ".join(buf))
            buf.clear()

    for raw in text.split("\n"):
        line = raw.rstrip()
        stripped = line.strip()

        if depth > 0:                                     # inside verbatim env: pass through
            flush()
            out.append(line)
            depth = max(0, depth + _depth_delta(line))
            continue

        d = _depth_delta(line)
        if stripped == "":                                # blank line -> paragraph break
            flush()
            out.append("")
            continue
        if d > 0:                                         # this line OPENS a verbatim env
            flush()
            out.append(line)
            depth = max(0, depth + d)
            continue
        if _ACTIVE_PCT.search(line):                      # active comment anywhere -> own line
            flush()
            out.append(line)
            depth = max(0, depth + d)
            continue
        if _STANDALONE.match(stripped):                   # structural line -> own line, no fold-in
            flush()
            out.append(line)
            depth = max(0, depth + d)
            continue
        if _WRAPPABLE.match(stripped):                    # \item/\caption -> start a foldable line
            flush()
            buf.append(stripped)
            if stripped.endswith("\\\\"):
                flush()
            continue
        # plain prose continuation -> fold into the current logical line
        buf.append(stripped)
        if stripped.endswith("\\\\"):
            flush()
    flush()

    result = "\n".join(out)
    result = re.sub(r"\n{3,}", "\n\n", result).strip("\n")
    return result + "\n" if result else ""


def main() -> int:
    flags = {a for a in sys.argv[1:] if a.startswith("-")}
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if not args:
        sys.stdout.write(reflow(sys.stdin.read()))
        return 0
    target = Path(args[0])
    if target.is_dir():
        sd = target / "sections" if (target / "sections").is_dir() else target
        files = [f for f in sorted(sd.glob("*.tex")) if not f.name.endswith(".proc.tex")]
    elif target.is_file():
        files = [target]
    else:
        print(json.dumps({"ok": False, "error": f"no such path: {target}"}))
        return 2
    changed = []
    for f in files:
        txt = f.read_text(encoding="utf-8")
        norm = reflow(txt)
        if norm != txt:
            f.write_text(norm, encoding="utf-8")
            changed.append(f.name)
    print(json.dumps({"ok": True, "reflowed": [f.name for f in files], "changed": changed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
