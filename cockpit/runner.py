#!/usr/bin/env python3
"""Cockpit run driver — one headless `claude` subprocess per paper run.

The user's own logged-in CLI is driven with BIDIRECTIONAL stream-json, which is
the whole point: the process stays alive after a turn's `result`, so a question
the model asks can be answered from the page and the same session continues.
Auth is inherited from that CLI — nothing here reads or writes a credential.

Windows: `claude` resolves to a .CMD shim and CreateProcess cannot exec a .CMD
directly (WinError 2), so it runs through `cmd /c`. That also means the pid we
hold is cmd.exe's, and only `taskkill /T` reaches the real process underneath.

Nothing about a run depends on an open browser socket: the state a run needs to
survive a closed window lives in the process and in <workdir>/.cockpit/.

stdlib only.
"""
from __future__ import annotations
import json, os, re, shutil, signal, subprocess, sys, threading, time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN_ROOT = HERE.parent                       # the plugin root --plugin-dir loads
BUILD_REPORT = PLUGIN_ROOT / "skills" / "ts-paper" / "scripts" / "build_report.py"

# What the ts-paper pipeline actually uses. Anything absent here fails mid-run.
ALLOWED_TOOLS = "Read,Write,Edit,Glob,Grep,Bash,WebSearch,WebFetch,Task,Skill,TodoWrite"

STAGE_NAMES = ["Route", "Plan", "Cite", "Write", "Refine",
               "Review", "Figures", "LaTeX", "Experiment"]

# Case-SENSITIVE on the literal token the kickoff asks for. A case-insensitive
# "done"/"complete" matches mid-run chatter ("the figure stage is complete"),
# and a false done closes stdin — i.e. ends a run that was still working.
DONE_TOKEN = re.compile(r"\bDONE\b")

STAGE_TTL = 5.0   # /api/state is polled; re-reading every stage log each poll is waste
_STAGE_CACHE: dict = {}


# ---------------------------------------------------------------- stage label

_BR = None
_BR_TRIED = False


def _build_report():
    """build_report.py as a module, or None. It owns stage detection; importing
    it is free (no side effects at import) and keeps one definition of a stage."""
    global _BR, _BR_TRIED
    if not _BR_TRIED:
        _BR_TRIED = True
        try:
            sys.path.insert(0, str(BUILD_REPORT.parent))
            import build_report as mod
            _BR = mod
        except Exception:
            _BR = None
    return _BR


LOG_N = re.compile(r"^(\d+)_.*\.io\.md$")


def _stage_scan(wd: Path) -> str:
    br = _build_report()
    if br is not None:
        try:
            cur = br.collect_stages(wd)["current"]
            return "not started" if cur is None else f"{cur} {br.STAGE_NAMES[cur].lower()}"
        except Exception:
            pass  # fall through to the filename contract below
    ns = [int(m.group(1)) for m in
          (LOG_N.match(p.name) for p in (wd / "logs").glob("*.io.md")) if m]
    ns = [n for n in ns if n < len(STAGE_NAMES)]
    if not ns:
        return "not started"
    return f"{max(ns)} {STAGE_NAMES[max(ns)].lower()}"


def stage_of(wd: Path) -> str:
    key = str(wd)
    now = time.time()
    hit = _STAGE_CACHE.get(key)
    if hit and now - hit[0] < STAGE_TTL:
        return hit[1]
    label = _stage_scan(wd)
    _STAGE_CACHE[key] = (now, label)
    return label


def _stage_at(wd: Path, t) -> str | None:
    """The stage in flight at wall-clock time `t`: the highest-numbered
    logs/<n>_<stage>.io.md whose last write is at or before `t`. Derived purely
    from log mtimes, so it reconstructs the SAME attribution on live ingest and
    on replay — the only reason per-stage tokens survive a server restart.
    Returns the `stage_of`-shaped "<n> <name>" label, or None when there is no
    stage log yet (nothing to attribute to)."""
    try:
        entries = []
        for p in (wd / "logs").glob("*.io.md"):
            m = LOG_N.match(p.name)
            if not m:
                continue
            n = int(m.group(1))
            if 0 <= n < len(STAGE_NAMES):
                entries.append((n, p.stat().st_mtime))
    except OSError:
        return None
    if not entries:
        return None
    if t is None:
        n = max(n for n, _ in entries)
    else:
        seen = [n for n, mt in entries if mt <= t + 1e-6]
        n = max(seen) if seen else min(n for n, _ in entries)
    return f"{n} {STAGE_NAMES[n].lower()}"


# ---------------------------------------------------------------- status line
#
# The one line that says what the run is DOING. Waiting is not the hard part —
# not knowing whether it is reading paper 8 or hung is. So: a human sentence,
# never a tool line, never JSON, never a log tail.

STATUS_PIN = re.compile(r"^STATUS:\s*(.+)$", re.M)

# 。!? end a sentence wherever they appear; a bare "." only when a space or the
# end follows, so "main.pdf" and "v1.2" do not cut the line in half.
SENT_END = re.compile(r"[。！？!?]|\.(?=\s|$)")
MD_LEAD = re.compile(r"^(?:[#>*+\s]|-\s)+|^\d+[.)]\s+")


def first_sentence(text: str, limit: int = 90) -> str:
    """The opening sentence of an assistant message. The model narrates in the
    user's language, so Chinese stops count exactly as much as ASCII ones."""
    fenced = False
    for raw in (text or "").splitlines():
        if raw.lstrip().startswith("```"):
            fenced = not fenced      # a command inside a code block is not a human sentence
            continue
        if fenced:
            continue
        line = " ".join(MD_LEAD.sub("", raw).split())
        if not line:
            continue
        end = SENT_END.search(line)
        if end:
            line = line[:end.start()].strip()
        if line:
            return line if len(line) <= limit else line[:limit - 1].rstrip() + "…"
    return ""


def pinned_status(wd: Path) -> str:
    """A line a skill pinned for itself — `STATUS: ...` in the newest stage log.
    Nothing writes one today; honouring it costs one small read and gives the
    skills a way to say something truer than the narration ever will."""
    logs = [(int(m.group(1)), p) for m, p in
            ((LOG_N.match(p.name), p) for p in (wd / "logs").glob("*.io.md")) if m]
    if not logs:
        return ""
    try:
        text = max(logs, key=lambda it: it[0])[1].read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    hits = STATUS_PIN.findall(text)
    return " ".join(hits[-1].split()) if hits else ""


def status_line(wd: Path, last_assistant: str, stage: str):
    """Pinned line > the model's own opening sentence > the stage it is in."""
    return pinned_status(wd) or first_sentence(last_assistant) or stage or None


# ---------------------------------------------------------------- telemetry
#
# The stream already keeps running totals: every `result` event carries the
# session's cumulative usage/modelUsage/cost, so the LATEST result is the whole
# answer and nothing here accumulates across events.

def telemetry_of(init: dict, result: dict, model=None, effort=None, remote=None,
                 per_stage=None) -> dict:
    """Contract-shaped telemetry from init + the newest result event.

    tokens{} totals ACROSS models. `result.usage` counts the main thread only —
    it misses every subagent (13 web searches on haiku, 147k tokens, in the
    bench run), so it cannot be reconciled with total_cost_usd, which is the sum
    of the per-model costs. modelUsage is the only whole-run token account.

    `per_stage` (accumulated by the Run across every result, not derivable from
    this single snapshot) rides alongside the per-run total: {stage: {in, out}},
    or None when stage attribution was uncertain — an honest 'not captured'."""
    models = {}
    for name, u in (result.get("modelUsage") or {}).items():
        models[name] = {"in": u.get("inputTokens"), "out": u.get("outputTokens"),
                        "cache_read": u.get("cacheReadInputTokens"),
                        "cache_write": u.get("cacheCreationInputTokens"),
                        "cost_usd": u.get("costUSD"),
                        "context_window": u.get("contextWindow"),
                        "max_output": u.get("maxOutputTokens")}

    def total(key):
        vals = [m[key] for m in models.values() if m[key] is not None]
        return sum(vals) if vals else None   # null, not a zero that reads as a measurement

    name = init.get("model") or model
    skills = init.get("skills")
    return {
        "model": name,
        "models": models,
        "tokens": {k: total(k) for k in ("in", "out", "cache_read", "cache_write")},
        "per_stage": per_stage,   # {stage: {in, out}} or None (attribution uncertain)
        "context_window": (models.get(name) or {}).get("context_window"),
        "cost_usd": result.get("total_cost_usd"),
        "turns": result.get("num_turns"),
        "duration_ms": result.get("duration_ms"),
        "effort": effort,                      # a flag we passed; the stream never reports it
        "remote": remote,                      # the machine this run was handed, None = local
        "permission_mode": init.get("permissionMode"),
        "api_key_source": init.get("apiKeySource"),
        "claude_code_version": init.get("claude_code_version"),
        "plugin_errors": init.get("plugin_errors"),
        "skills_loaded": len(skills) if isinstance(skills, list) else None,
    }


def health_of(result: dict) -> dict:
    return {"api_error": result.get("api_error_status"),
            "permission_denials": len(result.get("permission_denials") or []),
            "stop_reason": result.get("stop_reason")}


# ---------------------------------------------------------------- command

def claude_command(model=None, effort=None) -> list:
    exe = shutil.which("claude")
    if not exe:
        raise RuntimeError("`claude` is not on PATH — the Cockpit drives your own logged-in CLI")
    prefix = (["cmd", "/c", exe] if os.name == "nt" and exe.lower().endswith((".cmd", ".bat"))
              else [exe])
    return [*prefix,
            "-p", "--verbose",
            "--output-format", "stream-json",
            "--input-format", "stream-json",
            "--permission-mode", "acceptEdits",
            "--plugin-dir", str(PLUGIN_ROOT),
            "--allowed-tools", ALLOWED_TOOLS,
            *(["--model", model] if model else []),
            *(["--effort", effort] if effort else [])]


def kickoff_text(wd: Path, template: str, mode: str, review: str) -> str:
    routing = ("route it yourself in Stage 0" if mode in ("", "auto", None)
               else f"results_mode = {mode}")
    return f"""Use the ts-paper skill to write a complete paper from this proposal.

proposal:      {wd / 'proposal.md'}
working dir:   {wd}   (the run workdir — every artifact goes here)
template:      {template}
results mode:  {routing}
review tier:   {review}

Run the pipeline end to end until {wd / 'main.pdf'} compiles clean.

You are being driven from the Spark Cockpit: a window with a reply box, not a
terminal. When a decision is genuinely the author's — a missing API key, an
ambiguous route, an author-required review issue, a claim only I can confirm —
ask ONE clear question in plain language and end your turn there. I will answer
and you continue in this same session. Do not guess your way past an author
decision, and do not stop to ask about mechanics you can settle yourself.

When the paper is finished, write DONE on its own line and give the absolute
path to main.pdf.
"""


# ---------------------------------------------------------------- rendering

TOOL_FIELDS = ("file_path", "path", "notebook_path", "command", "pattern",
               "query", "url", "skill", "description", "prompt")


# A column of `python "D:/paper-spark/skills/ts-paper-cite/scripts/doi2bib.py"`
# elides to `python "D:/paper-spa…` and says nothing. The leaf is the only part
# that identifies the call, so keep that and drop the directories.
LONG_PATH = re.compile(r'(?<![\w.])(?:[A-Za-z]:)?[\\/][^\s"\']{12,}')


def shorten_paths(text: str) -> str:
    def leaf(m):
        parts = re.split(r"[\\/]", m.group(0))
        return parts[-1] or m.group(0)
    return LONG_PATH.sub(leaf, text)


def tool_line(item: dict) -> dict:
    """Tool name + ONE short target. The user is watching a paper get written,
    not debugging — a raw input dump is noise at this altitude."""
    inp = item.get("input") or {}
    target = ""
    for k in TOOL_FIELDS:
        v = inp.get(k)
        if isinstance(v, str) and v.strip():
            target = " ".join(v.split())
            break
    target = shorten_paths(target)
    if len(target) > 120:
        target = target[:117] + "..."
    return {"kind": "tool", "text": target, "label": item.get("name") or "tool"}


def render(ev: dict) -> list:
    """One raw stream-json event -> zero or more items the page shows.

    "user" events are tool results echoed back; they are the noisiest thing in
    the stream and carry nothing the tool line did not already say."""
    kind = ev.get("type")
    if kind == "assistant":
        out = []
        for item in (ev.get("message") or {}).get("content") or []:
            if item.get("type") == "text":
                text = (item.get("text") or "").strip()
                if text:
                    out.append({"kind": "assistant", "text": text})
            elif item.get("type") == "tool_use":
                out.append(tool_line(item))
        return out
    if kind == "result":
        return [{"kind": "result",
                 "text": "turn ended with an error" if ev.get("is_error") else "turn complete"}]
    if kind == "user_reply":   # ours, not the CLI's — what the user typed back
        return [note("user", ev.get("text") or "")]
    return []


def note(kind: str, text: str) -> dict:
    return {"kind": kind, "text": text}


def session_line(sid: str) -> dict:
    return note("system", f"session {sid[:8]} live")


def replay(path: Path, on_event=None) -> list:
    """Rebuild the visible transcript of a run this server did not start.
    A fresh system/init arrives per turn with the SAME session_id — show it once.

    `on_event` gets every raw event: telemetry and the status line are derived
    from the stream, so replaying the log is what makes them survive a restart."""
    items, seen = [], set()
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return items
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if on_event is not None:
            on_event(ev)
        t = ev.get("t")
        if ev.get("type") == "system":
            sid = ev.get("session_id")
            if sid and sid not in seen:
                seen.add(sid)
                items.append({**session_line(sid), "t": t})
            continue
        items += [{**it, "t": t} for it in render(ev)]
    return items


# ---------------------------------------------------------------- one run

SLUG = re.compile(r"[^A-Za-z0-9._-]+")


def make_workdir(runs_dir: Path, name: str) -> Path:
    base = SLUG.sub("-", (name or "").strip()).strip("-.")[:60]
    if not base:
        base = datetime.now().strftime("paper-%Y%m%d-%H%M%S")
    wd, n = runs_dir / base, 2
    while wd.exists():
        wd, n = runs_dir / f"{base}-{n}", n + 1
    wd.mkdir(parents=True)
    return wd


class Run:
    """One paper run: a workdir, a subprocess, and the transcript so far."""

    def __init__(self, workdir: Path, name: str, status: str = "stopped",
                 started: str = "", session_id=None, model=None, effort=None,
                 remote=None):
        self.workdir = workdir
        self.id = workdir.name
        self.name = name or workdir.name
        self.status = status
        self.started = started or datetime.now().isoformat(timespec="seconds")
        self.session_id = session_id
        self.model = model            # what we PASS as --model / --effort. Neither is
        self.effort = effort          # reported in the stream, so report what we set.
        self.remote = remote          # the ssh alias this run was handed, or None for local
        self.proc = None
        self.events = []
        self.question = None
        self.last_assistant = ""
        self.init_info = {}           # newest system/init
        self.last_result = {}         # newest result — the stream's own running totals
        self.per_stage = {}           # {stage_label: {"in": x, "out": y}} booked per result
        self._tele_prev = {"in": 0, "out": 0}   # last cumulative in/out, for the delta
        self._per_stage_ok = True     # cleared the instant attribution turns uncertain
        self.lock = threading.Lock()
        self.state_dir = workdir / ".cockpit"

    # -- lifecycle ---------------------------------------------------------

    def start(self, template: str, mode: str, review: str) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.status = "starting"
        kw = {} if os.name == "nt" else {"start_new_session": True}  # so stop() can kill the tree
        errlog = open(self.state_dir / "stderr.log", "ab")
        # Compute is per-run, not per-machine: one paper can be handed a GPU box
        # while another runs locally, so the choice rides this run's environment
        # instead of the shared .env.
        env = dict(os.environ)
        if self.remote:
            env["TS_REMOTE_HOST"] = self.remote
        else:
            env.pop("TS_REMOTE_HOST", None)
        self.proc = subprocess.Popen(
            claude_command(self.model, self.effort), cwd=str(self.workdir.parent),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errlog, env=env,
            text=True, encoding="utf-8", errors="replace", bufsize=1, **kw)
        errlog.close()  # the child holds its own dup of the handle
        self._send(kickoff_text(self.workdir, template, mode, review))
        self.status = "running"
        self.save()
        threading.Thread(target=self._reader, daemon=True).start()

    @classmethod
    def load(cls, wd: Path):
        """A run from a previous server. Its process is gone — mid-run states are
        reported as stopped rather than left looking live."""
        st = json.loads((wd / ".cockpit" / "status.json").read_text(encoding="utf-8",
                                                                   errors="replace"))
        status = st.get("status") or "stopped"
        if status in ("starting", "running", "waiting"):
            status = "stopped"
        run = cls(wd, st.get("name") or wd.name, status=status,
                  started=st.get("started") or "", session_id=st.get("session_id"),
                  model=st.get("model"), effort=st.get("effort"),
                  remote=st.get("remote"))
        run.events = replay(wd / ".cockpit" / "events.ndjson", run.absorb)
        return run

    def save(self) -> None:
        try:
            self.state_dir.mkdir(parents=True, exist_ok=True)
            (self.state_dir / "status.json").write_text(json.dumps({
                "id": self.id, "name": self.name, "status": self.status,
                "session_id": self.session_id, "started": self.started,
                "model": self.model, "effort": self.effort, "remote": self.remote,
                "pid": self.proc.pid if self.proc else None}, indent=2), encoding="utf-8")
        except OSError:
            pass  # a run must not die because its status file could not be written

    def stop(self) -> None:
        proc = self.proc
        with self.lock:
            self.status, self.question = "stopped", None
        self.save()
        if proc is None or proc.poll() is not None:
            return
        if os.name == "nt":
            # the pid is the cmd.exe shim's; /T is what reaches claude underneath
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                           capture_output=True)
        else:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except OSError:
                proc.terminate()
        self._record(note("system", "stopped by you"))

    # -- talking to the model ----------------------------------------------

    def _send(self, text: str) -> None:
        line = json.dumps({"type": "user", "message": {
            "role": "user", "content": [{"type": "text", "text": text}]}})
        self.proc.stdin.write(line + "\n")
        self.proc.stdin.flush()

    def reply(self, text: str) -> bool:
        """False when the run is not actually waiting on the user (-> 409)."""
        with self.lock:
            if self.status != "waiting" or self.proc is None or self.proc.poll() is not None:
                return False
            self.status, self.question = "running", None
        self._record(note("user", text))
        try:
            self._send(text)
        except (OSError, ValueError):
            with self.lock:
                self.status = "error"
            self._record(note("system", "could not reach the run — its process is gone"))
            self.save()
            return True
        # the CLI never echoes our turn, so without this line a reopened run
        # shows the model answering a question nobody asked
        self._log({"type": "user_reply", "text": text})
        self.save()
        return True

    def _log(self, ev: dict) -> None:
        ev["t"] = time.time()
        try:
            with open(self.state_dir / "events.ndjson", "a", encoding="utf-8") as f:
                f.write(json.dumps(ev) + "\n")
        except OSError:
            pass

    # -- reading the stream ------------------------------------------------

    def _reader(self) -> None:
        raw = self.state_dir / "events.ndjson"
        with self.proc.stdout as out, open(raw, "a", encoding="utf-8") as log:
            for line in out:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except ValueError:
                    continue
                ev["t"] = time.time()   # our own stamp: raw events carry no clock
                log.write(json.dumps(ev) + "\n")
                log.flush()
                self._ingest(ev)
        code = self.proc.wait()
        with self.lock:
            if self.status not in ("done", "stopped"):
                self.status = "error"
                self.question = None
                self.events.append({"kind": "system", "t": time.time(),
                                    "text": f"the run's process exited (code {code})"})
        self.save()

    def absorb(self, ev: dict) -> None:
        """Everything the page needs that is NOT transcript: telemetry and the
        material for the status line. Live and on replay, same path — which is
        the only reason a restarted server can still show them."""
        kind = ev.get("type")
        if kind == "system":
            if ev.get("subtype") == "init":
                self.init_info = ev
        elif kind == "result":
            self.last_result = ev          # cumulative already; keeping the latest is the sum
            self._attr_stage_tokens(ev)    # book this turn's token delta to its stage
        elif kind == "assistant":
            for item in (ev.get("message") or {}).get("content") or []:
                if item.get("type") == "text" and (item.get("text") or "").strip():
                    self.last_assistant = item["text"].strip()

    def _attr_stage_tokens(self, ev: dict) -> None:
        """Best-effort per-stage token attribution: the delta of the session's
        cumulative modelUsage since the previous result, booked to the stage that
        was in flight when this result landed (`_stage_at` on the event's clock,
        so live and replay agree). Fully guarded — the instant anything is
        uncertain it gives up (per_stage -> None) rather than report a fiction,
        and an accounting slip is never allowed to break the run."""
        if not self._per_stage_ok:
            return
        try:
            cur_in = cur_out = 0
            seen = False
            for u in (ev.get("modelUsage") or {}).values():
                i, o = u.get("inputTokens"), u.get("outputTokens")
                if i is not None:
                    cur_in += i
                    seen = True
                if o is not None:
                    cur_out += o
                    seen = True
            if not seen:
                return                       # no token account in this result
            d_in = cur_in - self._tele_prev["in"]
            d_out = cur_out - self._tele_prev["out"]
            self._tele_prev = {"in": cur_in, "out": cur_out}
            if d_in < 0 or d_out < 0:
                return                       # a new session reset the counter — rebaseline, skip
            stage = _stage_at(self.workdir, ev.get("t"))
            if stage is None:
                return                       # no stage log yet — nothing to attribute to
            slot = self.per_stage.setdefault(stage, {"in": 0, "out": 0})
            slot["in"] += d_in
            slot["out"] += d_out
        except Exception:
            self._per_stage_ok = False       # uncertain -> honest null, never a crash
            self.per_stage = {}

    def _ingest(self, ev: dict) -> None:
        t = ev.get("t")
        self.absorb(ev)
        if ev.get("type") == "system":
            sid = ev.get("session_id")
            if sid and sid != self.session_id:
                self.session_id = sid
                self._record(session_line(sid), t)
                self.save()
            return
        for item in render(ev):
            self._record(item, t)
        if ev.get("type") == "result":
            self._on_result()

    def _on_result(self) -> None:
        """A result ends the turn. The process stays alive, so the only two
        readings are: the paper is finished, or the run is waiting on the user.

        Done needs FILE evidence — main.pdf on disk — not the model's word."""
        finished = (self.workdir / "main.pdf").is_file() and DONE_TOKEN.search(self.last_assistant)
        with self.lock:
            if self.status == "stopped":
                return
            self.status = "done" if finished else "waiting"
            self.question = None if finished else (self.last_assistant or "")
        self.save()
        if finished:
            self._record(note("system", f"paper ready — {self.workdir / 'main.pdf'}"))
            try:
                self.proc.stdin.close()   # nothing left to ask; let the CLI exit
            except OSError:
                pass

    # -- state the server hands to the page --------------------------------

    def _record(self, item: dict, t=None) -> None:
        with self.lock:
            self.events.append({**item, "t": t or time.time()})

    def title(self) -> str:
        try:
            bp = json.loads((self.workdir / "blueprint.json").read_text(
                encoding="utf-8", errors="replace"))
            return str(bp.get("paper_title") or "").strip() or self.name
        except (OSError, ValueError, AttributeError):
            return self.name

    def artifacts(self) -> dict:
        wd = self.workdir
        figs = [f"figures/{p.name}" for p in sorted((wd / "figures").glob("*"))
                if p.suffix.lower() in (".png", ".svg", ".pdf")]
        return {
            "pdf": "main.pdf" if (wd / "main.pdf").is_file() else None,
            "report": (wd / "report.html").is_file(),
            "proposal": "proposal.md" if (wd / "proposal.md").is_file() else None,
            "figures": figs,
            "sections": [f"sections/{p.name}" for p in sorted((wd / "sections").glob("*.tex"))],
        }

    def telemetry(self) -> dict:
        # a copy so a poll's json.dumps can't race the reader thread mutating it;
        # None (not {}) when attribution is uncertain or nothing has landed yet
        per_stage = ({k: dict(v) for k, v in self.per_stage.items()}
                     if self._per_stage_ok and self.per_stage else None)
        return telemetry_of(self.init_info, self.last_result, self.model,
                            self.effort, self.remote, per_stage=per_stage)

    def health(self) -> dict:
        return health_of(self.last_result)

    def status_line(self):
        stage = stage_of(self.workdir)
        if stage == "not started" and self.status in ("starting", "running"):
            # the biggest text on the page must never read "not started" while the
            # process is alive and has simply not narrated anything yet
            stage = "starting up — waiting for the first output"
        return status_line(self.workdir, self.last_assistant, stage)

    def card(self) -> dict:
        return {"id": self.id, "title": self.title(), "status": self.status,
                "stage": stage_of(self.workdir), "started": self.started,
                "needs_reply": self.status == "waiting", "workdir": str(self.workdir)}

    def snapshot(self, cursor: int = 0) -> dict:
        with self.lock:
            n = len(self.events)
            cursor = max(0, min(cursor, n))
            new = self.events[cursor:]
            status, question = self.status, self.question
            last = self.last_assistant
        stage = stage_of(self.workdir)
        return {"id": self.id, "status": status, "stage": stage,
                "cursor": n, "events": new, "needs_reply": status == "waiting",
                "question": question if status == "waiting" else None,
                "status_line": status_line(self.workdir, last, stage),
                "telemetry": self.telemetry(), "health": self.health(),
                "workdir": str(self.workdir), "artifacts": self.artifacts()}


def create_run(runs_dir: Path, spark: str, name: str, template: str,
               mode: str, review: str, model=None, effort=None, remote=None) -> Run:
    wd = make_workdir(runs_dir, name or spark[:40])
    (wd / "proposal.md").write_text(spark.strip() + "\n", encoding="utf-8")
    run = Run(wd, name or wd.name, status="starting", model=model, effort=effort,
              remote=remote)
    run.start(template, mode, review)
    return run
