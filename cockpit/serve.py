#!/usr/bin/env python3
"""Spark Cockpit — a local control room for paper runs.

    python -m cockpit            # or: python cockpit/serve.py
    python -m cockpit --port 9000 --runs-dir D:/papers

A stdlib http.server on 127.0.0.1 that OWNS the run subprocesses (runner.py) and
serves one page plus a small JSON API. The browser is only a viewer: the server
keeps running when the window closes, so shutting a tab can never kill a
three-hour run. No websockets and no SSE — the page polls, and a poll is the
whole synchronisation story.

This is not a security boundary: one cooperating operator, one loopback socket.
The single hard rule is the path jail on /api/run/<id>/file — a file endpoint
that escapes its workdir is a correctness bug, and that is why it is checked.

The dashboard is NOT reimplemented here: /api/run/<id>/report shells out to
build_report.py, and --doctor data comes from build_report.py --doctor.

stdlib only.
"""
from __future__ import annotations
import argparse, importlib, inspect, json, os, re, shutil, subprocess, sys, threading, time, webbrowser
import urllib.error, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs, quote

try:
    from . import runner
except ImportError:  # `python cockpit/serve.py` — no package context
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import runner

HERE = Path(__file__).resolve().parent
UI_FILE = HERE / "ui.html"                 # the original single-tool cockpit (kept at /legacy)
UI_INDEX = HERE / "ui" / "index.html"      # the SparkBoard modular shell (served at /)
DEFAULT_PORT = 8765
PORT_TRIES = 10

RUNS: dict = {}                       # id -> runner.Run
RUNS_LOCK = threading.Lock()
RUNS_DIR = Path.home() / "spark-to-paper-runs"

CONTENT_TYPES = {
    ".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg", ".svg": "image/svg+xml", ".gif": "image/gif",
    ".html": "text/html; charset=utf-8", ".json": "application/json",
    ".md": "text/plain; charset=utf-8", ".tex": "text/plain; charset=utf-8",
    ".bib": "text/plain; charset=utf-8", ".log": "text/plain; charset=utf-8",
    ".txt": "text/plain; charset=utf-8", ".csv": "text/plain; charset=utf-8",
    # SparkBoard's own static assets (the modular shell + reader + workspaces)
    ".js": "text/javascript; charset=utf-8", ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8", ".woff2": "font/woff2", ".woff": "font/woff",
    ".ttf": "font/ttf", ".ico": "image/x-icon", ".map": "application/json",
}

# The two directories SparkBoard serves as static web assets, jailed to each root.
UI_DIR = HERE / "ui"
ASSETS_DIR = HERE / "assets"

# The only extensions POST /api/file/write will touch: the paper's own text
# sources. A deliberate save of the user's tex/bib is in scope; a binary or a
# dotfile is not, so anything else is refused before the jail is even consulted.
TEXT_WRITE_EXT = {".tex", ".bib", ".md", ".txt"}

DOCTOR_TTL = 60.0
_doctor_cache = {"t": 0.0, "data": None}


# ---------------------------------------------------------------- state

def doctor() -> dict:
    """Environment checks from build_report.py --doctor. Cached: /api/state is
    polled and every uncached call spawns three `--version` probes."""
    now = time.time()
    if _doctor_cache["data"] is not None and now - _doctor_cache["t"] < DOCTOR_TTL:
        return _doctor_cache["data"]
    data = {"ok": False, "error": "build_report.py --doctor returned no JSON"}
    try:
        r = subprocess.run([sys.executable, str(runner.BUILD_REPORT), "--doctor"],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=90)
        data = json.loads((r.stdout or "").strip().splitlines()[-1])
    except (OSError, ValueError, IndexError, subprocess.SubprocessError) as e:
        data["error"] = f"{type(e).__name__}: {e}"
    _doctor_cache.update(t=now, data=data)
    return data


def scan_runs() -> None:
    """Adopt runs left by a previous server. There is no registry file: a run is
    a workdir with a .cockpit/status.json in it."""
    for st in sorted(RUNS_DIR.glob("*/.cockpit/status.json")):
        wd = st.parent.parent
        if wd.name in RUNS:
            continue
        try:
            RUNS[wd.name] = runner.Run.load(wd)
        except (OSError, ValueError):
            pass  # an unreadable status file hides one run, not the whole list


def get_run(rid: str):
    with RUNS_LOCK:
        return RUNS.get(rid)


# ---------------------------------------------------------------- product tree

TREE_KINDS = {".tex": "tex", ".json": "json", ".bib": "bib", ".pdf": "pdf",
              ".png": "png", ".svg": "svg", ".md": "md", ".log": "log"}

# The workdir layout from ts-paper/SKILL.md, "Working directory & handoff" — the
# same paths the gates resolve. Anything not claimed here is transient by that
# document's own definition, so it lands in "other" rather than in a stage.
# Directories are never walked: build/, experiments/, sections.bak/ and .cockpit/
# are derived, and listing them would bury the page in files nobody opens.
TREE_STAGES = (
    ("input",     ("proposal.md", "references.json", "references.bib",
                   "retrieved_papers.json"), ()),
    ("1 plan",    ("blueprint.json", "template.json"), ()),
    ("2 cite",    ("refs.bib", "claims_map.json", "results.facts.json"), ()),
    ("3 write",   (), ("sections/*.tex",)),
    ("6 figures", (), ("figures/*.png", "figures/*.svg", "figures/*.pdf")),
    ("7 paper",   ("main.tex", "main.pdf", "report.html"), ()),
    ("trace",     (), ("logs/*.md",)),
)


def file_row(wd: Path, p: Path) -> dict:
    st = p.stat()
    return {"path": p.relative_to(wd).as_posix(), "size": st.st_size,
            "mtime": st.st_mtime, "kind": TREE_KINDS.get(p.suffix.lower(), "other")}


def tree_of(wd: Path) -> dict:
    claimed, stages = set(), []
    for label, names, globs in TREE_STAGES:
        found = [wd / n for n in names]
        for pattern in globs:
            found += sorted(wd.glob(pattern))
        files = []
        for p in found:
            if p in claimed or not p.is_file():
                continue
            claimed.add(p)
            files.append(file_row(wd, p))
        if files:
            stages.append({"stage": label, "files": files})
    other = [file_row(wd, p) for p in sorted(wd.iterdir())
             if p.is_file() and p not in claimed]
    return {"stages": stages, "other": other}


# ---------------------------------------------------------------- figures

TEXT_EL = re.compile(rb"<text\b[^>]*>(.*?)</text>", re.I | re.S)
INNER_TAG = re.compile(rb"<[^>]*>")
RASTER = re.compile(rb"<image[\s/>]|data:image", re.I)
FIG_EXT = (".png", ".svg", ".pdf")


def svg_badge(path: Path):
    """(font_ok, image_free) read out of the SVG bytes.

    The badge is the only cheap way to tell a real vector from a bitmap with
    re-typeset text on top, so it must NOT come from the manifest's self-report:
    the manifest is exactly the thing being checked. font_ok = there is a <text>
    element carrying actual characters (tspans stripped); image_free = no
    <image> element and no data: raster anywhere."""
    try:
        data = path.read_bytes()
    except OSError:
        return None, None
    font_ok = any(INNER_TAG.sub(b"", m.group(1)).strip() for m in TEXT_EL.finditer(data))
    return font_ok, RASTER.search(data) is None


def fig_versions(figs: Path, label: str) -> list:
    """The rounds still on disk: the working renders stage 6 keeps beside the
    approved file, plus the SVG redraw rounds under svg_work/."""
    wd = figs.parent
    out = [p for p in sorted(figs.glob(f"{label}_v*.*")) if p.suffix.lower() in FIG_EXT]
    out += sorted((figs / "svg_work" / label).glob("round_*.svg"))
    return [p.relative_to(wd).as_posix() for p in out]


# A figure carries its manifest label ("protocol"), but the two facts a reader
# actually wants — which Figure it is in the paper, and what it shows — live in
# the .tex, not the manifest. We read them straight from the sections rather than
# re-run latexmk or parse the PDF: the number is the includegraphics order, the
# caption is the \caption in the same environment.
FIG_ENV = re.compile(r"\\begin\{(figure\*?)\}(.*?)\\end\{\1\}", re.S)
FIG_INCLUDE = re.compile(r"\\includegraphics(?:\[[^\]]*\])?\{\s*figures/([^}]+?)\s*\}")
FIG_LABEL = re.compile(r"\\label\s*\{[^{}]*\}")
CAP_UNESCAPE = (("\\&", "&"), ("\\%", "%"), ("\\_", "_"), ("\\#", "#"),
                ("\\$", "$"), ("\\{", "{"), ("\\}", "}"), ("~", " "))


def fig_stem(raw: str) -> str:
    """The manifest label is extension-less; an includegraphics path may or may
    not carry one, so strip a known image extension and nothing else."""
    s = raw.strip()
    low = s.lower()
    for ext in FIG_EXT:
        if low.endswith(ext):
            return s[: -len(ext)]
    return s


def braced(s: str, open_idx: int) -> str:
    """Content of the {...} that opens at open_idx, matching balanced braces so a
    caption with nested {} survives. Escaped \\{ \\} do not count as delimiters."""
    depth = i = 0
    esc = False
    for i in range(open_idx, len(s)):
        c = s[i]
        if esc:
            esc = False
        elif c == "\\":
            esc = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return s[open_idx + 1:i]
    return s[open_idx + 1:]


def caption_text(env: str):
    """The \\caption{...} of one figure environment, cleaned to a readable
    sentence: \\label stripped, common escapes unescaped, whitespace collapsed,
    any wrapping braces dropped. Returns None when the environment has none."""
    m = re.search(r"\\caption\*?", env)
    if not m:
        return None
    brace = env.find("{", m.end())
    if brace < 0:
        return None
    s = FIG_LABEL.sub("", braced(env, brace))
    for a, b in CAP_UNESCAPE:
        s = s.replace(a, b)
    s = re.sub(r"\s+", " ", s).strip()
    while len(s) >= 2 and s[0] == "{" and s[-1] == "}":
        s = s[1:-1].strip()
    return s or None


def section_texs(wd: Path) -> list:
    """The section .tex files in the paper's own order: blueprint's section_order
    when it is there, else sorted(sections/*.tex)."""
    secdir = wd / "sections"
    order = None
    try:
        data = json.loads((wd / "blueprint.json").read_text(encoding="utf-8", errors="replace"))
        order = data.get("section_order")
    except (OSError, ValueError):
        order = None
    if isinstance(order, list) and order:
        paths = [secdir / f"{sid}.tex" for sid in order if (secdir / f"{sid}.tex").is_file()]
        if paths:
            return paths
    return sorted(secdir.glob("*.tex"))


def figure_facts(wd: Path):
    """label -> (number, caption) read from the sections. Number is the order the
    figure's includegraphics first appears across the ordered sections (Figure 1,
    2, ...); caption is the \\caption in the same environment. A label placed in no
    .tex simply never lands in either map — that is the null the caller reports."""
    numbers, captions = {}, {}
    n = 0
    for tex in section_texs(wd):
        try:
            text = tex.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in FIG_INCLUDE.finditer(text):
            label = fig_stem(m.group(1))
            if label not in numbers:
                n += 1
                numbers[label] = n
        for env in FIG_ENV.finditer(text):
            body = env.group(2)
            cap = caption_text(body)
            if cap is None:
                continue
            for im in FIG_INCLUDE.finditer(body):
                captions.setdefault(fig_stem(im.group(1)), cap)
    return numbers, captions


def figures_of(wd: Path) -> dict:
    """Manifest facts (engine, rounds, audit) + independent SVG evidence, plus the
    figure's number and caption read from the sections."""
    figs = wd / "figures"
    br = runner._build_report()
    items = []
    if br is not None:
        try:
            items = br.collect_figures(wd)["items"]
        except (OSError, ValueError, KeyError, TypeError):
            items = []   # a broken manifest hides the figures, not the whole page
    numbers, captions = figure_facts(wd)
    out = []
    for f in items:
        label = f["label"]
        svg = figs / f"{label}.svg"
        font_ok, image_free = svg_badge(svg) if svg.is_file() else (None, None)
        out.append({
            "label": label, "number": numbers.get(label),
            "caption": captions.get(label),
            "engine": f["engine"], "type": f["type"],
            "grounding": f.get("grounding"), "ref": f.get("ref"),
            "critic_rounds": f["critic_rounds"], "svg_rounds": f["svg_rounds"],
            "audit_ok": f["audit_ok"], "font_ok": font_ok, "image_free": image_free,
            "files": {ext[1:]: (f"figures/{label}{ext}"
                                if (figs / f"{label}{ext}").is_file() else None)
                      for ext in FIG_EXT},
            "versions": fig_versions(figs, label),
        })
    return {"figures": out}


# -- rich figures for a LIBRARY run (the showcase gallery) --------------------
#
# The live route (/api/run/<id>/figures) serves figures_of straight, with files
# as workdir-relative paths the run's own /file route resolves. A LIBRARY run has
# no such route — its files are reached through /api/file?path=<abs> — so the rich
# adapter rewrites every ref to that jailed URL and folds in the three artefacts a
# showcase wants but figures_of leaves on disk: the generation prompt, the SVG
# audit, and the redraw rounds. No per-figure SSIM exists, so none is emitted.

ROUND_SVG = re.compile(r"round_(\d+)\.svg$", re.I)


def _file_url(p: Path) -> str:
    """A jailed library-file URL. quote() keeps a Windows drive-colon and spaces
    from breaking the query string; /api/file re-jails on read."""
    return "/api/file?path=" + quote(str(p))


def _fig_prompt(figs: Path, label: str):
    """The first ~1.2k chars of the image-model prompt, or None."""
    p = figs / f"{label}.prompt.txt"
    if not p.is_file():
        return None
    try:
        return p.read_text(encoding="utf-8", errors="replace")[:1200]
    except OSError:
        return None


def _fig_audit(figs: Path, label: str):
    """The SVG audit reduced to the chips the gallery shows, or None. cleanliness/
    min_text_px/texts/shapes live under `stats`; warnings is top-level."""
    p = figs / "audit_logs" / f"{label}.audit.json"
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    stats = data.get("stats") or {}
    return {"cleanliness": stats.get("cleanliness"), "min_text_px": stats.get("min_text_px"),
            "texts": stats.get("texts"), "shapes": stats.get("shapes"),
            "warnings": data.get("warnings") or []}


def _fig_rounds(figs: Path, label: str) -> list:
    """The SVG redraw iterations as [{round, svg_url}] from svg_work/<label>/. A
    public/linear run keeps no svg_work/ — its redraw trace lives under
    repair_logs/<label>.*, so fall back to that so the gallery still shows the
    trace instead of an empty rounds strip."""
    d = figs / "svg_work" / label
    out = []
    if d.is_dir():
        for p in sorted(d.glob("round_*.svg")):
            m = ROUND_SVG.search(p.name)
            out.append({"round": int(m.group(1)) if m else None, "svg_url": _file_url(p)})
    if not out:
        rl = figs / "repair_logs"
        if rl.is_dir():
            for p in sorted(rl.glob(f"{label}.*")):
                if not p.is_file():
                    continue
                m = ROUND_SVG.search(p.name)
                out.append({"round": int(m.group(1)) if m else None, "svg_url": _file_url(p)})
    return out


def spark_figures_rich(wd: Path) -> dict:
    """figures_of for a LIBRARY run: files rewritten to /api/file?path= URLs, plus
    prompt + audit + versioned redraw rounds per figure. Honest: no ssim field."""
    figs = wd / "figures"
    out = []
    for f in figures_of(wd)["figures"]:
        label = f["label"]
        files = {ext: (_file_url(figs / f"{label}.{ext}")
                       if (figs / f"{label}.{ext}").is_file() else None)
                 for ext in ("png", "svg", "pdf")}
        out.append({**f, "files": files,
                    "prompt": _fig_prompt(figs, label),
                    "audit": _fig_audit(figs, label),
                    "versions": _fig_rounds(figs, label)})
    return {"figures": out, "workdir": str(wd)}


# ---------------------------------------------------------------- settings

ENV_FILE = runner.PLUGIN_ROOT / ".env"
ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")
SECRETISH = ("KEY", "TOKEN", "SECRET", "PASSWORD")

# The keys the suite's scripts actually read (see .env.example at the plugin root
# and the os.environ.get call sites), grouped the way a user thinks about them.
SETTINGS_GROUPS = (
    {"key": "figure", "title": "Figure model",
     "why": "Draws the schematic figures. Without it the figure stage is skipped.",
     "vars": ("TS_FIG_API_KEY", "TS_FIG_BASE_URL", "TS_FIG_MODEL", "TS_FIG_API_STYLE")},
    {"key": "vision", "title": "Vision QA",
     "why": "Reads back a rendered figure to fix its text and catch defects.",
     "vars": ("OPENAI_API_KEY", "VISION_BASE_URL", "VISION_MODEL")},
    {"key": "embed", "title": "Embeddings + KG",
     "why": "KG-grounded recall and the novelty check. Optional — degrades to web search.",
     "vars": ("TS_EMBED_API_KEY", "TS_EMBED_BASE_URL", "TS_EMBED_MODEL")},
    {"key": "reading-ai", "title": "Reading assistant",
     "why": "The on-demand summary / explain / translate / ask in the reader (Reading "
            "First, AI Second). Any OpenAI-compatible endpoint; DeepSeek is a cheap "
            "default. Text is sent only when you press a key — never on its own.",
     "vars": ("SPARKBOARD_AI_BASE_URL", "SPARKBOARD_AI_KEY", "SPARKBOARD_AI_MODEL")},
    {"key": "overleaf", "title": "Overleaf",
     "why": "Pushes the finished paper to an Overleaf project.",
     "vars": ("OVERLEAF_GIT_URL", "OVERLEAF_TOKEN")},
    {"key": "raster", "title": "Raster fallback",
     "why": "The local vectorizer used only when the native SVG redraw cannot converge.",
     "vars": ("DRAWAI_REPO", "HF_TOKEN")},
    {"key": "remote", "title": "Remote server",
     "why": "Hand a machine to the experiment stage. Name an alias from your own "
            "~/.ssh/config — ssh already knows the host, port and key, so nothing "
            "here is a credential and none is stored.",
     "vars": ("TS_REMOTE_HOST", "TS_REMOTE_WORKDIR")},
)

# remote.py is the one place that knows how to talk to a machine; the settings
# page calls it rather than growing a second ssh implementation.
REMOTE_PY = (Path(__file__).resolve().parent.parent / "skills" / "ts-paper-experiment"
             / "scripts" / "remote.py")

# What we can pass the CLI. Displayed as a dropdown because a typo in a free-text
# model box does not fail until the run has already started.
MODELS = ["opus", "sonnet", "haiku", "claude-opus-5", "claude-fable-5",
          "claude-sonnet-5", "claude-opus-4-8", "claude-haiku-4-5"]
EFFORTS = ["low", "medium", "high", "xhigh", "max"]


def env_read(path: Path) -> dict:
    """KEY=VALUE out of the .env, same rules the skills' _dotenv.py uses."""
    out = {}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, _, v = s.partition("=")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def env_write(path: Path, updates: dict) -> None:
    """Merge into the file. Existing lines are rewritten in place and everything
    else — comments, blank lines, keys we know nothing about — is left alone."""
    lines = (path.read_text(encoding="utf-8", errors="replace").splitlines()
             if path.is_file() else [])
    left = dict(updates)
    for i, line in enumerate(lines):
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        name = s.split("=", 1)[0].strip()
        if name in left:
            lines[i] = f"{name}={left.pop(name)}"
    lines += [f"{name}={value}" for name, value in left.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def settings_state() -> dict:
    env = env_read(ENV_FILE)
    groups = []
    for g in SETTINGS_GROUPS:
        rows = []
        for name in g["vars"]:
            secret = any(w in name for w in SECRETISH)
            value = env.get(name) or os.environ.get(name) or ""
            rows.append({"name": name, "set": bool(value), "secret": secret,
                         "value": None if secret else (value or None)})
        groups.append({"key": g["key"], "title": g["title"], "why": g["why"],
                       "vars": rows, "testable": True})
    # ssh already holds the host, port and key behind each alias, so the machine
    # is chosen from a list rather than retyped — and we never see a credential.
    hosts = remote_call(["hosts"], timeout=15)
    return {"groups": groups, "env_path": str(ENV_FILE),
            "models": MODELS, "efforts": EFFORTS,
            "ssh_hosts": [h["alias"] for h in (hosts.get("hosts") or [])]}


# -- probes: each one actually talks to the thing, or says it cannot ----------

def probe_openai(key: str, base: str, default_base: str, missing: str) -> dict:
    if not key:
        return {"ok": False, "detail": f"not configured — {missing} is empty"}
    base = (base or default_base).rstrip("/")
    if not base:
        return {"ok": False, "detail": "not configured — no base URL"}
    host = urlsplit(base).netloc or base
    req = urllib.request.Request(base + "/models",
                                 headers={"Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            body = json.loads(r.read(200000).decode("utf-8", "replace"))
            n = len(body.get("data") or [])
        return {"ok": True, "detail": f"{host} answered — {n} models listed"}
    except urllib.error.HTTPError as e:
        return {"ok": False, "detail": f"{host} refused: HTTP {e.code} {e.reason}"}
    except (urllib.error.URLError, OSError, ValueError) as e:
        return {"ok": False, "detail": f"{host}: {type(e).__name__}: {e}"}


def probe_overleaf(url: str, token: str) -> dict:
    if not url:
        return {"ok": False, "detail": "not configured — OVERLEAF_GIT_URL is empty"}
    if not shutil.which("git"):
        return {"ok": False, "detail": "git is not on PATH"}
    remote = url
    if token and url.startswith("https://"):
        remote = f"https://git:{quote(token, safe='')}@{url[len('https://'):]}"
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": "echo"}
    try:
        r = subprocess.run(["git", "ls-remote", "--heads", remote], env=env,
                           capture_output=True, text=True, timeout=45)
    except (OSError, subprocess.SubprocessError) as e:
        return {"ok": False, "detail": f"git ls-remote failed: {type(e).__name__}: {e}"}
    if r.returncode == 0:
        n = len([ln for ln in r.stdout.splitlines() if ln.strip()])
        return {"ok": True, "detail": f"git ls-remote ok — {n} branches"}
    # git echoes the remote back on failure, and our remote carries the token
    msg = (r.stderr or "").replace(token, "***") if token else (r.stderr or "")
    tail = [ln for ln in msg.splitlines() if ln.strip()]
    return {"ok": False, "detail": (tail[-1][:160] if tail else
                                    f"git ls-remote exited {r.returncode}")}


def probe_raster(repo: str) -> dict:
    exe = shutil.which("drawai")
    if exe:
        return {"ok": True, "detail": f"drawai runtime on PATH ({exe})"}
    if repo and Path(repo).expanduser().is_dir():
        return {"ok": True, "detail": f"DRAWAI_REPO present ({repo})"}
    return {"ok": False,
            "detail": "not configured — no drawai on PATH and no DRAWAI_REPO directory"}


def remote_call(args: list, timeout: int) -> dict:
    """Run remote.py and return its JSON. It always prints one JSON line, so a
    nonzero exit is still a usable answer (an unreachable host is data)."""
    if not REMOTE_PY.is_file():
        return {"ok": False, "error": f"remote.py not found at {REMOTE_PY}"}
    try:
        r = subprocess.run([sys.executable, str(REMOTE_PY), *args], capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=timeout)
        return json.loads((r.stdout or "").strip().splitlines()[-1])
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired) as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


HOSTS_TTL = 30.0          # ~/.ssh/config barely changes; /api/state is polled every 5 s
_HOSTS_CACHE: list = [0.0, []]


def ssh_hosts() -> list:
    if time.time() - _HOSTS_CACHE[0] > HOSTS_TTL:
        d = remote_call(["hosts"], timeout=15)
        _HOSTS_CACHE[:] = [time.time(), [h["alias"] for h in (d.get("hosts") or [])]]
    return _HOSTS_CACHE[1]


def probe_remote(alias: str) -> dict:
    """Hand-over check: is this machine usable, and how does work reach its GPUs?
    A SLURM login node has no GPU of its own — reporting that as a failure would
    send the user away from a working cluster, so the kind carries the answer."""
    if not alias:
        return {"ok": False, "detail": "not configured — pick a host from your ~/.ssh/config"}
    d = remote_call(["probe", alias], timeout=90)
    if d.get("summary"):
        return {"ok": bool(d.get("reachable")), "detail": d["summary"]}
    return {"ok": False, "detail": d.get("error") or "probe failed"}


def settings_test(group: str) -> dict:
    env = {**env_read(ENV_FILE)}
    for k, v in os.environ.items():
        env.setdefault(k, v)
    if group == "figure":
        return probe_openai(env.get("TS_FIG_API_KEY", ""), env.get("TS_FIG_BASE_URL", ""),
                            "", "TS_FIG_API_KEY")
    if group == "vision":
        return probe_openai(env.get("OPENAI_API_KEY", ""), env.get("VISION_BASE_URL", ""),
                            "https://api.openai.com/v1", "OPENAI_API_KEY")
    if group == "embed":
        return probe_openai(env.get("TS_EMBED_API_KEY", ""), env.get("TS_EMBED_BASE_URL", ""),
                            "", "TS_EMBED_API_KEY")
    if group == "overleaf":
        return probe_overleaf(env.get("OVERLEAF_GIT_URL", ""), env.get("OVERLEAF_TOKEN", ""))
    if group == "raster":
        return probe_raster(env.get("DRAWAI_REPO", ""))
    if group == "remote":
        return probe_remote(env.get("TS_REMOTE_HOST", ""))
    if group == "reading-ai":
        # falls back to the pipeline's OPENAI key, mirroring workspaces/ai.config
        return probe_openai(env.get("SPARKBOARD_AI_KEY", "") or env.get("OPENAI_API_KEY", ""),
                            env.get("SPARKBOARD_AI_BASE_URL", ""),
                            "https://api.deepseek.com", "SPARKBOARD_AI_KEY")
    return {"ok": False, "detail": f"no such group: {group}"}


# ---------------------------------------------------------------- workspace data (jury / wiki / spark-read)
#
# The three tools store everything as files on disk. The reader GUI opens a
# directory (a spark run root, a manuscript's .paper-review, or a compiled wiki
# project) and the workspaces/ adapters turn it into JSON. `path=` is jailed to a
# set of LIBRARY ROOTS the same way /file is jailed to a run's workdir — the GUI
# is not a file browser for the whole disk. Roots = the runs dir plus anything in
# SPARKBOARD_LIBRARY (os.pathsep-separated).

def library_roots() -> set:
    roots = {RUNS_DIR.resolve()}
    for part in (os.environ.get("SPARKBOARD_LIBRARY") or "").split(os.pathsep):
        p = part.strip()
        if p:
            try:
                roots.add(Path(p).expanduser().resolve())
            except OSError:
                pass
    return roots


def jail_lib(path_str: str):
    """A path inside a library root, or None. Same spirit as serve_file's jail."""
    if not path_str:
        return None
    try:
        target = Path(path_str).expanduser().resolve()
    except OSError:
        return None
    for root in library_roots():
        if target == root or root in target.parents:
            return target
    return None


def _find_marker(is_dir: bool, name: str):
    """First directory within the library roots (root + up to 2 levels) that holds
    a child called `name`. Cheap best-effort so the GUI can suggest a real dir to
    open instead of starting empty."""
    for root in library_roots():
        if not root.is_dir():
            continue
        stack = [(root, 0)]
        while stack:
            d, depth = stack.pop()
            m = d / name
            if (m.is_dir() if is_dir else m.is_file()):
                return str(d)
            if depth < 2:
                try:
                    for c in sorted(d.iterdir()):
                        if c.is_dir() and not c.name.startswith("."):
                            stack.append((c, depth + 1))
                except OSError:
                    pass
    return ""


def library_state() -> dict:
    """The operator-configured library roots plus a suggested dir to open per tool.
    Spark opens a paper workdir (blueprint.json) or a run root (.research); Jury a
    manuscript that has been reviewed (.paper-review); Wiki a compiled project (WIKI.md)."""
    return {
        "roots": sorted(str(r) for r in library_roots()),
        "defaults": {
            "spark": _find_marker(False, "blueprint.json") or _find_marker(True, ".research"),
            "jury": _find_marker(True, ".paper-review"),
            "wiki": _find_marker(False, "WIKI.md"),   # a wiki project = the dir holding WIKI.md
        },
    }


# ---------------------------------------------------------------- handler

class Cockpit(BaseHTTPRequestHandler):
    server_version = "SparkCockpit"
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass  # a 1.5 s poll would bury anything worth reading in the console

    # -- replies -----------------------------------------------------------

    def send_payload(self, body: bytes, ctype: str, code: int = 200) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass  # the viewer closed the window mid-poll; the run is unaffected

    def send_json(self, obj, code: int = 200) -> None:
        self.send_payload(json.dumps(obj).encode("utf-8"), "application/json", code)

    def send_text(self, msg: str, code: int) -> None:
        self.send_payload(msg.encode("utf-8"), "text/plain; charset=utf-8", code)

    def read_body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except ValueError:
            return {}

    # -- routing -----------------------------------------------------------

    def do_GET(self):
        url = urlsplit(self.path)
        path, query = url.path, parse_qs(url.query)
        if path in ("/", "/index.html"):
            return self.serve_ui()
        if path == "/legacy":
            return self.serve_ui(legacy=True)
        if path.startswith("/ui/") or path.startswith("/assets/"):
            return self.serve_static(path)
        if path == "/api/state":
            return self.serve_state()
        if path == "/api/settings":
            return self.send_json(settings_state())
        if path == "/api/library":
            return self.send_json(library_state())
        if path == "/api/file":
            return self.serve_libfile(query)
        if path == "/api/spark/figures":
            return self.serve_spark_figures(query)   # rich gallery, not the spark_read adapter
        if path.startswith(("/api/wiki/", "/api/jury/", "/api/spark/")):
            parts = path.split("/")
            return self.serve_ws(parts[2], parts[3] if len(parts) > 3 else "", query)
        if path.startswith("/api/run/"):
            rid, tail = self.split_run(path)
            run = get_run(rid)
            if run is None:
                return self.send_json({"error": f"no such run: {rid}"}, 404)
            if tail == "":
                cursor = query.get("cursor", ["0"])[0]
                return self.serve_run(run, int(cursor) if cursor.isdigit() else 0)
            if tail == "report":
                return self.serve_report(run, query.get("lang", [""])[0])
            if tail == "file":
                return self.serve_file(run, query.get("path", [""])[0])
            if tail == "tree":
                return self.send_json(tree_of(run.workdir))
            if tail == "figures":
                return self.send_json(figures_of(run.workdir))
        return self.send_json({"error": f"no route: {path}"}, 404)

    def do_POST(self):
        path = urlsplit(self.path).path
        if path == "/api/runs":
            return self.create_run(self.read_body())
        if path == "/api/ai":
            return self.serve_ai(self.read_body())
        if path == "/api/settings":
            return self.save_settings(self.read_body())
        if path == "/api/settings/test":
            return self.send_json(settings_test((self.read_body().get("group") or "").strip()))
        if path == "/api/file/write":
            return self.file_write(self.read_body())
        if path.startswith("/api/run/"):
            rid, tail = self.split_run(path)
            run = get_run(rid)
            if run is None:
                return self.send_json({"error": f"no such run: {rid}"}, 404)
            if tail == "reply":
                return self.reply(run, self.read_body())
            if tail == "stop":
                run.stop()
                return self.send_json({"id": run.id, "status": run.status})
        return self.send_json({"error": f"no route: {path}"}, 404)

    @staticmethod
    def split_run(path: str):
        parts = path[len("/api/run/"):].split("/", 1)
        return parts[0], (parts[1] if len(parts) > 1 else "")

    # -- routes ------------------------------------------------------------

    def serve_ui(self, legacy: bool = False):
        """`/` is the SparkBoard modular shell (ui/index.html); `/legacy` is the
        original single-tool cockpit (ui.html). Falling back to the legacy page if
        the shell is somehow missing keeps a broken deploy still usable."""
        page = UI_FILE if (legacy or not UI_INDEX.is_file()) else UI_INDEX
        if not page.is_file():
            return self.send_text(f"missing {page}", 500)
        self.send_payload(page.read_bytes(), "text/html; charset=utf-8")

    def serve_state(self):
        with RUNS_LOCK:
            runs = list(RUNS.values())
        runs.sort(key=lambda r: r.started, reverse=True)
        live = sum(1 for r in runs if r.status in ("running", "waiting"))
        # ssh_hosts rides here so choosing where a run computes is a decision on
        # the start form, not something buried in a settings page.
        self.send_json({"runs": [r.card() for r in runs], "doctor": doctor(),
                        "running": live, "plugin_dir": str(runner.PLUGIN_ROOT),
                        "runs_dir": str(RUNS_DIR), "ssh_hosts": ssh_hosts()})

    def serve_run(self, run, cursor: int):
        """The snapshot plus the three keys the page's header needs. The runner
        derives them; this only guarantees the shape so the page never has to
        special-case a run that started before they existed."""
        snap = run.snapshot(cursor)
        for key, empty in (("status_line", None), ("telemetry", {}),
                           ("health", {"api_error": None, "permission_denials": 0,
                                       "stop_reason": None})):
            if key in snap:
                continue
            value = getattr(run, key, None)
            if callable(value):
                value = value()
            snap[key] = empty if value is None else value
        self.send_json(snap)

    def create_run(self, body: dict):
        spark = (body.get("spark") or "").strip()
        if not spark:
            return self.send_json({"error": "spark is empty"}, 400)
        # model/effort are CLI flags, not stream facts: pass them only when the
        # page actually chose one, so an unset dropdown keeps the CLI's default.
        # remote is the machine this run is handed — per run, because one paper
        # can need a GPU box while another is happy locally.
        picked = {k: (body.get(k) or "").strip() for k in ("model", "effort", "remote")}
        try:
            run = runner.create_run(RUNS_DIR, spark,
                                    (body.get("name") or "").strip(),
                                    body.get("template") or "ts_iieta",
                                    body.get("mode") or "auto",
                                    body.get("review") or "lean",
                                    **{k: v for k, v in picked.items() if v})
        except (RuntimeError, OSError) as e:
            return self.send_json({"error": str(e)}, 500)
        with RUNS_LOCK:
            RUNS[run.id] = run
        self.send_json({"id": run.id})

    def save_settings(self, body: dict):
        raw = body.get("vars")
        if not isinstance(raw, dict) or not raw:
            return self.send_json({"error": "vars is empty"}, 400)
        updates = {k: str(v).strip() for k, v in raw.items() if ENV_NAME.match(str(k))}
        if not updates:
            return self.send_json({"error": "no writable variable names"}, 400)
        try:
            env_write(ENV_FILE, updates)
        except OSError as e:
            return self.send_json({"error": f"could not write {ENV_FILE}: {e}"}, 500)
        self.send_json(settings_state())

    def reply(self, run, body: dict):
        text = (body.get("text") or "").strip()
        if not text:
            return self.send_json({"error": "reply is empty"}, 400)
        if not run.reply(text):
            return self.send_json({"error": f"run is {run.status}, not waiting"}, 409)
        self.send_json({"id": run.id, "status": run.status})

    def serve_report(self, run, lang: str = ""):
        """Regenerate through build_report.py, then serve what it wrote. The page
        it produces refreshes itself, so this route is hit repeatedly by design.
        `lang` picks the dashboard's language; only the two known values reach the
        builder, and anything else falls back to English."""
        lang = lang if lang in ("zh", "en") else "en"
        try:
            subprocess.run([sys.executable, str(runner.BUILD_REPORT), str(run.workdir),
                            "--lang", lang],
                           capture_output=True, timeout=180)
        except (OSError, subprocess.SubprocessError) as e:
            return self.send_text(f"build_report.py failed: {e}", 500)
        report = run.workdir / "report.html"
        if not report.is_file():
            return self.send_text("no report.html — the run has not written anything yet", 404)
        self.send_payload(report.read_bytes(), "text/html; charset=utf-8")

    def serve_file(self, run, rel: str):
        if not rel:
            return self.send_json({"error": "path is required"}, 400)
        wd = run.workdir.resolve()
        target = (wd / rel).resolve()
        # The jail: an absolute rel, or one with enough .., lands outside wd.
        if target != wd and wd not in target.parents:
            return self.send_json({"error": "path is outside the run workdir"}, 403)
        if not target.is_file():
            return self.send_json({"error": f"no such file: {rel}"}, 404)
        ctype = CONTENT_TYPES.get(target.suffix.lower(), "application/octet-stream")
        self.send_payload(target.read_bytes(), ctype)

    def serve_static(self, path: str):
        """SparkBoard's own web assets: /ui/* (the modular shell + workspace
        modules) and /assets/* (fonts). Same path-jail spirit as /file — a static
        route that escapes its root is a bug, so it is checked."""
        root = UI_DIR if path.startswith("/ui/") else ASSETS_DIR
        target = (HERE / path.lstrip("/")).resolve()
        if root.resolve() not in target.parents:
            return self.send_json({"error": "outside the asset root"}, 403)
        if not target.is_file():
            return self.send_text(f"no such asset: {path}", 404)
        ctype = CONTENT_TYPES.get(target.suffix.lower(), "application/octet-stream")
        self.send_payload(target.read_bytes(), ctype)

    def serve_ai(self, body: dict):
        """The restrained reading assistant (summary / explain / translate / ask).
        Streams Server-Sent-Events so the popover fills token-by-token. This is the
        ONE place the cockpit hands a user's text to a model — and only because the
        page asked. (The base cockpit avoids SSE for run polling on purpose; here
        it is exactly right, because a stream IS the interaction.)"""
        try:
            from .workspaces import ai as reading_ai
        except Exception:
            sys.path.insert(0, str(HERE))
            from workspaces import ai as reading_ai
        op = (body.get("op") or "explain").strip()
        text, context = body.get("text") or "", body.get("context") or ""
        target_lang = body.get("target_lang") or "简体中文"
        env = {**env_read(ENV_FILE)}
        for k, v in os.environ.items():
            env.setdefault(k, v)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        try:
            for delta in reading_ai.stream(op, text, context, target_lang, env):
                self.wfile.write(b"data: " + json.dumps({"t": delta}).encode("utf-8") + b"\n\n")
                self.wfile.flush()
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass  # the reader dismissed the popover mid-stream; nothing to clean up

    def serve_ws(self, tool: str, sub: str, query: dict):
        """Dispatch /api/{wiki,jury,spark}/<sub>?path=<dir>[&id=&rel=...] to the
        matching workspaces adapter function. The adapter is imported lazily so
        the server still boots if an adapter is absent (503 rather than a crash),
        and inspect binds only the query params a function actually declares."""
        target = jail_lib(query.get("path", [""])[0])
        if target is None:
            return self.send_json(
                {"error": "path= is required and must sit inside a SparkBoard library root "
                          "(the runs dir, or a directory named in SPARKBOARD_LIBRARY)"}, 400)
        modname = "spark_read" if tool == "spark" else tool
        mod = None
        for qualified in ("cockpit.workspaces." + modname, "workspaces." + modname):
            try:
                mod = importlib.import_module(qualified)
                break
            except ImportError:
                if qualified.startswith("workspaces."):
                    sys.path.insert(0, str(HERE))
                continue
            except Exception:
                break
        if mod is None:
            return self.send_json({"error": f"{tool} adapter is not available yet"}, 503)
        sub = sub.replace("-", "_")               # /api/jury/run-report -> jury.run_report
        if sub.startswith("_") or not sub.isidentifier():   # no private/internal symbols
            return self.send_json({"error": f"no such {tool} view: {sub!r}"}, 404)
        fn = getattr(mod, sub, None)
        if not callable(fn):
            return self.send_json({"error": f"no such {tool} view: {sub!r}"}, 404)
        kwargs = {}
        try:
            extra = list(inspect.signature(fn).parameters)[1:]     # everything after the dir arg
        except (TypeError, ValueError):
            extra = []
        for name in extra:
            v = query.get(name, [None])[0]
            if v is not None:
                kwargs[name] = v
        try:
            # default=str keeps a stray Path/date from a build_report collector from
            # 500-ing the whole panel — the adapters return JSON, this is the seatbelt.
            body = json.dumps(fn(target, **kwargs), default=str).encode("utf-8")
            self.send_payload(body, "application/json")
        except Exception as e:                                    # an adapter bug is data, not a 500 page
            self.send_json({"error": f"{tool}.{sub} failed: {type(e).__name__}: {e}"}, 500)

    def serve_libfile(self, query: dict):
        """Raw bytes for any file inside a library root — the paper PDF, a figure,
        proposal.md, a raw source PDF — so the reader can show real prose and pages.
        Jailed exactly like the adapters' path=, so it is not a file browser for the
        whole disk."""
        target = jail_lib(query.get("path", [""])[0])
        if target is None:
            return self.send_json({"error": "path= must sit inside a SparkBoard library root"}, 400)
        if not target.is_file():
            return self.send_text(f"no such file: {query.get('path', [''])[0]}", 404)
        ctype = CONTENT_TYPES.get(target.suffix.lower(), "application/octet-stream")
        self.send_payload(target.read_bytes(), ctype)

    def serve_spark_figures(self, query: dict):
        """`/api/spark/figures?path=<run>` — the rich figures gallery for a library
        run. Jailed to the library roots like the other library routes; an adapter
        slip is data (a 500 body), never a crashed server."""
        target = jail_lib(query.get("path", [""])[0])
        if target is None:
            return self.send_json(
                {"error": "path= must sit inside a SparkBoard library root"}, 400)
        try:
            body = json.dumps(spark_figures_rich(target), default=str).encode("utf-8")
            self.send_payload(body, "application/json")
        except Exception as e:
            self.send_json({"error": f"spark.figures failed: {type(e).__name__}: {e}"}, 500)

    def file_write(self, body: dict):
        """`POST /api/file/write` {path, content} — the native tex SAVE. A deliberate
        mutation of the user's own file at their explicit action, so it is allowed —
        but jailed to the library roots, restricted to text sources, and made
        reversible by writing a `<name>.bak` of the prior content BEFORE the new
        bytes land. Returns {ok, bytes, bak}."""
        path_str = (body.get("path") or "").strip()
        content = body.get("content")
        if not path_str:
            return self.send_json({"error": "path is required"}, 400)
        if not isinstance(content, str):
            return self.send_json({"error": "content is required and must be a string"}, 400)
        target = jail_lib(path_str)
        if target is None:
            return self.send_json(
                {"error": "path must sit inside a SparkBoard library root"}, 403)
        if target.suffix.lower() not in TEXT_WRITE_EXT:
            return self.send_json(
                {"error": f"refusing to write {target.suffix or 'a file with no extension'} — "
                          f"only {', '.join(sorted(TEXT_WRITE_EXT))} are writable"}, 403)
        if target.is_dir():
            return self.send_json({"error": "path is a directory"}, 400)
        bak = None
        try:
            # reversible: back up the prior content FIRST, only when there is any
            if target.is_file():
                bak_path = target.with_name(target.name + ".bak")
                bak_path.write_bytes(target.read_bytes())
                bak = str(bak_path)
            data = content.encode("utf-8")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        except OSError as e:
            return self.send_json({"error": f"could not write {target}: {e}"}, 500)
        self.send_json({"ok": True, "bytes": len(data), "bak": bak})


# ---------------------------------------------------------------- startup

def bind(port: int) -> ThreadingHTTPServer:
    for p in range(port, port + PORT_TRIES + 1):
        try:
            return ThreadingHTTPServer(("127.0.0.1", p), Cockpit)
        except OSError:
            continue
    raise SystemExit(f"ports {port}-{port + PORT_TRIES} are all busy")


CHROMIUMS = ("chrome", "google-chrome", "msedge", "chromium", "chromium-browser")
CHROMIUM_PATHS = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
)


def open_window(url: str) -> None:
    """App mode when a Chromium is around: the point is a window that looks like
    an app, not one more tab in a browser that already has forty."""
    exe = next((p for p in (shutil.which(n) for n in CHROMIUMS) if p), None)
    if exe is None:
        exe = next((p for p in CHROMIUM_PATHS if Path(p).exists()), None)
    if exe:
        try:
            subprocess.Popen([exe, f"--app={url}", "--window-size=1360,940"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        except OSError:
            pass
    webbrowser.open(url)


def main(argv=None) -> None:
    global RUNS_DIR
    ap = argparse.ArgumentParser(prog="cockpit", description="Spark Cockpit — run papers from a window")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--runs-dir", default=str(RUNS_DIR))
    ap.add_argument("--no-browser", action="store_true", help="serve only; open nothing")
    args = ap.parse_args(argv)

    RUNS_DIR = Path(args.runs_dir).expanduser().resolve()
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    scan_runs()

    httpd = bind(args.port)
    url = f"http://127.0.0.1:{httpd.server_port}/"
    print(f"Spark Cockpit   {url}")
    print(f"  runs          {RUNS_DIR}  ({len(RUNS)} known)")
    print(f"  plugin        {runner.PLUGIN_ROOT}")
    print("  closing the window leaves runs alone; Ctrl+C here stops them with the server.")
    if not args.no_browser:
        open_window(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping live runs...")
    finally:
        httpd.server_close()
        for run in list(RUNS.values()):
            if run.status in ("starting", "running", "waiting"):
                run.stop()


if __name__ == "__main__":
    main()
