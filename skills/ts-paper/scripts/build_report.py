#!/usr/bin/env python3
"""SparkBoard — render a run's workdir into a self-refreshing static report.html.

    python build_report.py <workdir>      # write <workdir>/report.html, print one JSON line
    python build_report.py --doctor       # print one JSON object of environment checks
    python build_report.py --from-hook    # PostToolUse hook entry; silent no-op off-workdir

There is no server, no state directory, no cache and no watcher: the page is a
plain file that re-reads itself every 15 s via <meta http-equiv="refresh">, and
every number on it comes from a file the pipeline already wrote.

The ONLY subprocesses this script spawns are the two read-only linters
(draft_lint.py, citations_lint.py, ~0.2 s each) and the version probes used by
--doctor. It never runs latexmk, assemble_paper.py, or run_gates.py: `all`
re-runs assemble_paper.py, i.e. a recompile, which a report must never cause.

Sibling script paths resolve relative to THIS file, exactly like run_gates.py, so
the script is workdir- and cwd-independent. stdlib only.

Every read passes encoding="utf-8", errors="replace" and the write passes
encoding="utf-8": on a Windows cp936 box a bare open() raises UnicodeDecodeError
on every logs/*.io.md file in a real workdir.
"""
from __future__ import annotations

import base64
import html
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILLS_ROOT = HERE.parent.parent  # .../skills (the suite root holding ts-paper-*)
DRAFT_LINT = SKILLS_ROOT / "ts-paper-write" / "scripts" / "draft_lint.py"
CITATIONS_LINT = SKILLS_ROOT / "ts-paper-cite" / "scripts" / "citations_lint.py"

GATE_TIMEOUT = 30    # the linters take ~0.2 s; this only bounds a wedged process
PROBE_TIMEOUT = 10   # `<tool> --version` probes for --doctor
REFRESH_SECONDS = 15

# The rail is fixed at 0-8 so a half-finished run still shows what is coming.
# Titles come from each log's own "# Stage <n> — <title>" heading when present.
STAGE_NAMES = ["Route", "Plan", "Cite", "Write", "Refine",
               "Review", "Figures", "LaTeX", "Experiment"]

E = html.escape


# ---------------------------------------------------------------- i18n
# The report's OWN CHROME is translatable; the run's data (paper title, figure
# captions, review quotes, file paths, LaTeX/compile errors, model ids) is NEVER
# translated. LANG is a module global set once from --lang; default "en" so a bare
# CLI run and the standalone artifact stay English. The Cockpit passes --lang zh.
LANG = "en"


def set_lang(x) -> None:
    global LANG
    LANG = "zh" if str(x).lower().startswith("zh") else "en"


# Stage-rail display names. STAGE_NAMES (above) stays the stable English key set
# used for the machine status string; this only changes what the rail shows.
STAGE_NAMES_L = {
    "en": STAGE_NAMES,
    "zh": ["路由", "规划", "引用", "撰写", "精修", "评审", "图表", "LaTeX", "实验"],
}


def stage_name(i: int) -> str:
    names = STAGE_NAMES_L.get(LANG, STAGE_NAMES)
    return names[i] if 0 <= i < len(names) else STAGE_NAMES[i]


def count_phrase(n, en_word: str, zh_word: str) -> str:
    """A count with its noun, pluralised in English, classifier-joined in Chinese."""
    if LANG == "zh":
        return f"{n} {zh_word}"
    return f"{n} {en_word}" + ("" if n == 1 else "s")


L = {
    "en": {
        "eyebrow": "Spark-to-Paper · Run Report",
        "pill_done": "DONE", "pill_nostage": "NO STAGE LOGS YET",
        "pill_stage": "STAGE {0} / {1} · {2}", "official": "official",
        "by_workdir": "workdir", "by_template": "template", "by_mode": "mode",
        "by_firstlog": "first log", "by_generated": "generated",
        "fresh_none_b": "Not compiled yet",
        "fresh_none_s": "no main.pdf in this workdir — the LaTeX stage has not produced a PDF.",
        "fresh_stale_b": "PDF is out of date",
        "fresh_stale_s": ('main.pdf was compiled {0}, but <span class="mono">{1}</span> changed at {2}. '
                          'What you would open is not what the sections now say — recompile before reading.'),
        "fresh_fresh_b": "PDF current",
        "fresh_fresh_s": "compiled {0}, newer than every sections/*.tex, main.tex and refs.bib.",
        "rail_now": "Now:",
        "rail_done": "All Definition-of-Done rows observed green.",
        "rail_nostage": 'No <span class="mono">logs/&lt;n&gt;_&lt;stage&gt;.io.md</span> written yet.',
        "rail_last": "<b>{0}</b> — last written {1}", "rail_also": "also: {0}",
        "ask_title": "Waiting for you",
        "ask_badjson": "A question was pinned, but its JSON did not parse:",
        "ask_how": ('<b>Reply in your Claude Code chat window</b> — the run is waiting there. '
                    'This page only observes. · asked {0} in <span class="mono">{1}</span>'),
        "gates_title": "Gates", "gates_sub": "read-only linters, re-run on every refresh",
        "col_gate": "Gate", "col_verdict": "Verdict", "col_detail": "Detail",
        "col_where": "Where", "col_rule": "Rule",
        "v_pass": "PASS", "v_issues": "ISSUES", "v_notyet": "NOT YET", "v_noresult": "NO RESULT",
        "gate_cite_detail": "{0} entries · {1} cited · {2} issues · {3} warnings",
        "gate_draft_detail": "{0} · {1}",
        "latex_title": "LaTeX build",
        "latex_none": "Not compiled yet — no main.log in this workdir.",
        "lx_clean": "CLEAN", "lx_degraded": "DEGRADED", "lx_nopdf": "NO PDF", "lx_error": "ERROR",
        "lx_pages": "Pages", "lx_compiled": "Compiled", "lx_size": "PDF size",
        "lx_overfull": "Overfull hbox", "lx_nopdf_val": "no PDF produced", "lx_bytes": "{0:,} bytes",
        "col_source": "Source", "col_message": "Message",
        "col_kind": "Kind", "col_key": "Key",
        "lx_errnote": ('A <span class="mono">file:line</span> is exact — open it there. A bare '
                       '<span class="mono">sections/&lt;id&gt;.tex</span> means the compiler reported the '
                       'generated <span class="mono">build/&lt;id&gt;.proc.tex</span>, whose line numbers do '
                       'not survive the mapping: match on the context text instead.'),
        "lx_undefnote": ('Undefined citations/references ship as <span class="mono">[?]</span> '
                         'marks in the PDF.'),
        "lx_clean_empty": "No errors and no undefined citations or references in main.log.",
        "review_title": "Adversarial review — stage 5",
        "review_none": "Not run yet — no logs/5_review.io.md.",
        "col_id": "ID", "col_sev": "Sev", "col_section": "Section", "col_issue": "Issue",
        "review_close": "close: {0}",
        "review_leftover_rows": "Not parsed as issue bullets — shown verbatim:",
        "review_leftover_norows": "DECISIONS block — no issue bullet matched, shown verbatim:",
        "review_authreq": "AUTHOR-REQUIRED — surfaced, not silently edited:",
        "figs_title": "Figure workshop",
        "figs_none": "No figures/figures.manifest.json yet.",
        "figs_empty": "Manifest present but lists no figures.",
        "figs_vector": "{0} / {1} vector",
        "fig_pngonly": "PNG only", "fig_noartifact": "no artifact",
        "fig_critique": "critique r{0}", "fig_nocritlog": "no critique log",
        "fig_svgr": "svg r{0}", "fig_audit_ok": "audit ✓", "fig_audit_bad": "audit ✗",
        "fig_zoom": "enlarge figure",
        "bp_title": "Blueprint", "bp_none": "No blueprint.json yet.",
        "bp_sections": "Sections", "bp_abstract": " + abstract", "bp_words": "Word target",
        "bp_contrib": "Contributions", "bp_figs": "Figures planned",
        "bp_tabs": "Tables planned", "bp_notation": "Notation entries",
        "refs_title": "References", "refs_none": "No refs.bib yet.",
        "refs_entries": "refs.bib entries", "refs_cited": "Cited in text",
        "refs_issues": "Issues · warnings", "refs_resolved": "BibTeX resolved",
        "refs_densest": "Densest section",
        "dod_title": "Definition of done",
        "dod_review_ran": "Adversarial review ran · {0} logged",
        "dod_review_noparse": "Adversarial review ran · no issue bullet parsed",
        "dod_review_absent": "Adversarial review — no logs/5_review.io.md",
        "dod_cite_ok": "Every \\cite resolves · {0}/{1} · {2} issues",
        "dod_cite_notobs": "Citations gate — not observed",
        "dod_draft": "Draft gate clean · {0}",
        "dod_draft_notobs": "Draft gate — not observed",
        "dod_figs": "Editable vector figures — {0} / {1}",
        "dod_figs_nomani": "Figures — no manifest yet",
        "dod_pdf_ok": "main.pdf compiled clean · {0} pages",
        "dod_pdf_degraded": "main.pdf compiled with warnings · {0} undefined, {1} errors",
        "dod_pdf_nopdf": "main.pdf — compile produced no PDF",
        "dod_pdf_notcompiled": "main.pdf — not compiled yet",
        "dod_fresh_ok": "PDF is newer than every source file",
        "dod_fresh_stale": "PDF is older than a source file — recompile",
        "dod_fresh_none": "PDF freshness — nothing compiled",
        "env_title": "Environment", "env_optkeys": "Optional keys",
        "env_absent": "absent", "env_present": "present", "env_none": "none set",
        "env_tex": "TeX",
        "foot_gen": "generated by build_report.py · {0} · auto-refreshes every {1} s",
        "foot_truth": "truth source: {0} — closing this page never stops the run",
    },
    "zh": {
        "eyebrow": "Spark-to-Paper · 运行报告",
        "pill_done": "已完成", "pill_nostage": "尚无阶段日志",
        "pill_stage": "阶段 {0} / {1} · {2}", "official": "官方",
        "by_workdir": "工作目录", "by_template": "模板", "by_mode": "模式",
        "by_firstlog": "首条日志", "by_generated": "生成于",
        "fresh_none_b": "尚未编译",
        "fresh_none_s": "此工作目录下没有 main.pdf —— LaTeX 阶段还没生成 PDF。",
        "fresh_stale_b": "PDF 已过期",
        "fresh_stale_s": ('main.pdf 编译于 {0},但 <span class="mono">{1}</span> 在 {2} 又改过。'
                          '你现在打开的并不是各章节最新的内容 —— 阅读前请重新编译。'),
        "fresh_fresh_b": "PDF 最新",
        "fresh_fresh_s": "编译于 {0},比所有 sections/*.tex、main.tex 和 refs.bib 都新。",
        "rail_now": "当前:",
        "rail_done": "完成标准各项均已观测为绿。",
        "rail_nostage": '尚未写入任何 <span class="mono">logs/&lt;n&gt;_&lt;stage&gt;.io.md</span>。',
        "rail_last": "<b>{0}</b> —— 最后写入 {1}", "rail_also": "另有: {0}",
        "ask_title": "等待你的输入",
        "ask_badjson": "已置顶一个问题,但它的 JSON 无法解析:",
        "ask_how": ('<b>请在 Claude Code 聊天窗口回复</b> —— 运行正在那里等待,本页只作观测。'
                    ' · 提问于 {0},位于 <span class="mono">{1}</span>'),
        "gates_title": "门禁", "gates_sub": "只读检查器,每次刷新都会重跑",
        "col_gate": "门禁", "col_verdict": "结论", "col_detail": "详情",
        "col_where": "位置", "col_rule": "规则",
        "v_pass": "通过", "v_issues": "有问题", "v_notyet": "尚未", "v_noresult": "无结果",
        "gate_cite_detail": "{0} 条目 · {1} 被引 · {2} 问题 · {3} 警告",
        "gate_draft_detail": "{0} · {1}",
        "latex_title": "LaTeX 编译",
        "latex_none": "尚未编译 —— 此工作目录下没有 main.log。",
        "lx_clean": "干净", "lx_degraded": "有降级", "lx_nopdf": "无 PDF", "lx_error": "错误",
        "lx_pages": "页数", "lx_compiled": "编译于", "lx_size": "PDF 大小",
        "lx_overfull": "溢出框", "lx_nopdf_val": "未生成 PDF", "lx_bytes": "{0:,} 字节",
        "col_source": "来源", "col_message": "信息",
        "col_kind": "类型", "col_key": "键",
        "lx_errnote": ('<span class="mono">file:line</span> 是精确定位 —— 直接打开那一行。若只是一个 '
                       '<span class="mono">sections/&lt;id&gt;.tex</span>,说明编译器报的是生成的 '
                       '<span class="mono">build/&lt;id&gt;.proc.tex</span>,其行号在映射后已失效:'
                       '请改用上下文文本来定位。'),
        "lx_undefnote": ('未定义的引用/交叉引用会在 PDF 里显示成 <span class="mono">[?]</span> 标记。'),
        "lx_clean_empty": "main.log 中没有错误,也没有未定义的引用或交叉引用。",
        "review_title": "对抗性评审 —— 阶段 5",
        "review_none": "尚未运行 —— 没有 logs/5_review.io.md。",
        "col_id": "编号", "col_sev": "级别", "col_section": "章节", "col_issue": "问题",
        "review_close": "关闭条件: {0}",
        "review_leftover_rows": "未解析为问题条目 —— 原样展示:",
        "review_leftover_norows": "DECISIONS 块 —— 没有匹配到问题条目,原样展示:",
        "review_authreq": "AUTHOR-REQUIRED —— 已呈现,未擅自修改:",
        "figs_title": "图表工坊",
        "figs_none": "还没有 figures/figures.manifest.json。",
        "figs_empty": "清单存在,但没有列出任何图。",
        "figs_vector": "{0} / {1} 为矢量",
        "fig_pngonly": "仅 PNG", "fig_noartifact": "无产物",
        "fig_critique": "批评 r{0}", "fig_nocritlog": "缺批评日志",
        "fig_svgr": "svg r{0}", "fig_audit_ok": "审计 ✓", "fig_audit_bad": "审计 ✗",
        "fig_zoom": "放大查看图",
        "bp_title": "蓝图", "bp_none": "还没有 blueprint.json。",
        "bp_sections": "章节", "bp_abstract": " + 摘要", "bp_words": "字数目标",
        "bp_contrib": "贡献点", "bp_figs": "计划图数",
        "bp_tabs": "计划表数", "bp_notation": "记号条目",
        "refs_title": "参考文献", "refs_none": "还没有 refs.bib。",
        "refs_entries": "refs.bib 条目", "refs_cited": "正文引用",
        "refs_issues": "问题 · 警告", "refs_resolved": "BibTeX 已解析",
        "refs_densest": "引用最密章节",
        "dod_title": "完成标准",
        "dod_review_ran": "对抗性评审已执行 · 记录 {0}",
        "dod_review_noparse": "对抗性评审已执行 · 未解析出问题条目",
        "dod_review_absent": "对抗性评审 —— 缺 logs/5_review.io.md",
        "dod_cite_ok": "每个 \\cite 都可解析 · {0}/{1} · {2} 个问题",
        "dod_cite_notobs": "引用门禁 —— 未观测",
        "dod_draft": "草稿门禁干净 · {0}",
        "dod_draft_notobs": "草稿门禁 —— 未观测",
        "dod_figs": "可编辑矢量图 —— {0} / {1}",
        "dod_figs_nomani": "图表 —— 还没有清单",
        "dod_pdf_ok": "main.pdf 编译干净 · {0} 页",
        "dod_pdf_degraded": "main.pdf 编译带警告 · {0} 处未定义,{1} 个错误",
        "dod_pdf_nopdf": "main.pdf —— 编译未产出 PDF",
        "dod_pdf_notcompiled": "main.pdf —— 尚未编译",
        "dod_fresh_ok": "PDF 比所有源文件都新",
        "dod_fresh_stale": "PDF 比某个源文件旧 —— 请重新编译",
        "dod_fresh_none": "PDF 新鲜度 —— 未编译任何内容",
        "env_title": "环境", "env_optkeys": "可选密钥",
        "env_absent": "缺失", "env_present": "存在", "env_none": "未设置",
        "env_tex": "TeX",
        "foot_gen": "由 build_report.py 生成 · {0} · 每 {1} 秒自动刷新",
        "foot_truth": "数据来源: {0} —— 关闭本页不会中断运行",
    },
}


def t(key: str) -> str:
    """Look up a chrome string for the current LANG, falling back to English then
    the key itself, so a missing translation degrades to readable text."""
    d = L.get(LANG) or L["en"]
    v = d.get(key)
    if v is None:
        v = L["en"].get(key, key)
    return v


# ---------------------------------------------------------------- io helpers

def read_text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def read_bytes(p: Path) -> bytes:
    try:
        return p.read_bytes()
    except OSError:
        return b""


def read_json(p: Path):
    """Parsed JSON, or None — a corrupt artifact degrades one panel, not the page."""
    try:
        return json.loads(p.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return None


def mtime(p: Path):
    try:
        return p.stat().st_mtime
    except OSError:
        return None


def clock(ts) -> str:
    return datetime.fromtimestamp(ts).strftime("%H:%M") if ts else "—"


def stamp(ts) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S") if ts else "—"


# ---------------------------------------------------------------- collectors

def collect_masthead(wd: Path) -> dict:
    bp = read_json(wd / "blueprint.json") or {}
    tpl = read_json(wd / "template.json") or {}
    return {
        "title": bp.get("paper_title") or wd.name,
        "have_title": bool(bp.get("paper_title")),
        "template": tpl.get("display_name") or tpl.get("name") or "—",
        "template_id": tpl.get("name") or "—",
        "official": bool(tpl.get("official")),
        "results_mode": tpl.get("results_mode") or "—",
        "provenance": tpl.get("provenance") or "",
        "keywords": bp.get("keywords") or "",
    }


def collect_freshness(wd: Path) -> dict:
    """Is main.pdf older than the sources it was built from?

    A stale PDF presented as the current paper is the one lie this page exists to
    prevent, so the comparison is mtime-based and reported even when it is fine."""
    pdf_t = mtime(wd / "main.pdf")
    newest_p, newest_t = None, None
    sources = [wd / "main.tex", wd / "refs.bib"]
    sec = wd / "sections"
    if sec.is_dir():
        sources += sorted(sec.glob("*.tex"))
    for p in sources:
        t = mtime(p)
        if t is not None and (newest_t is None or t > newest_t):
            newest_p, newest_t = p, t
    if pdf_t is None:
        return {"state": "none", "pdf_t": None, "src": newest_p, "src_t": newest_t}
    if newest_t is not None and newest_t > pdf_t + 1:  # 1 s slack for same-run writes
        return {"state": "stale", "pdf_t": pdf_t, "src": newest_p, "src_t": newest_t}
    return {"state": "fresh", "pdf_t": pdf_t, "src": newest_p, "src_t": newest_t}


# The stage number comes from the FILENAME — logs/<n>_<stage>.io.md is the documented
# contract. The first-line heading is only a display title; its wording is free-form.
STAGE_N = re.compile(r"^(\d+)_")
STAGE_H = re.compile(r"^#+\s*(?:Stage\s*\d+\s*[—:-]\s*)?(.+)$")


def collect_stages(wd: Path) -> dict:
    """Enumerate logs/*.io.md — never whitelist the stage set: conditional logs
    (data, idea2story, kg_build, novelty) carry no number and are listed as extras."""
    rail = [{"n": i, "name": STAGE_NAMES[i], "title": "", "t": None, "path": None}
            for i in range(len(STAGE_NAMES))]
    extra, logs = [], []
    logdir = wd / "logs"
    if logdir.is_dir():
        for p in sorted(logdir.glob("*.md")):
            if p.name == "index.md":
                continue
            mn = STAGE_N.match(p.name)
            n = int(mn.group(1)) if mn else None
            head = (read_text(p).splitlines() or [""])[0]
            mh = STAGE_H.match(head.strip())
            title = mh.group(1).strip() if mh else p.name[:-3]
            rec = {"n": n, "title": title, "t": mtime(p), "path": p, "name": p.name}
            logs.append(rec)
            if n is not None and 0 <= n < len(rail):
                rail[n].update(title=title, t=rec["t"], path=p)
            else:
                extra.append(rec)
    present = [s["n"] for s in rail if s["path"] is not None]
    return {"rail": rail, "extra": extra, "logs": logs,
            "current": max(present) if present else None,
            "index": read_text(wd / "logs" / "index.md")}


ASK_FENCE = re.compile(r"```sparkboard-ask[ \t]*\r?\n(.*?)```", re.S)


def collect_ask(stages: dict):
    """A pinned ```sparkboard-ask fence in the most recently written stage log.

    Absent is the normal case and renders nothing. Malformed JSON inside the
    fence renders the raw text — a question the user cannot see is worse than an
    ugly one."""
    logs = [r for r in stages["logs"] if r["t"] is not None]
    if not logs:
        return None
    newest = max(logs, key=lambda r: (r["t"], r["n"] if r["n"] is not None else -1))
    m = ASK_FENCE.search(read_text(newest["path"]))
    if not m:
        return None
    raw = m.group(1).strip()
    ask = {"raw": raw, "t": newest["t"], "source": newest["name"],
           "question": "", "options": [], "evidence": ""}
    try:
        data = json.loads(raw)
    except ValueError:
        return ask
    if not isinstance(data, dict):
        return ask
    opts = data.get("options") or []
    ask["question"] = str(data.get("question") or "")
    ask["options"] = [str(o) for o in opts] if isinstance(opts, list) else [str(opts)]
    ask["evidence"] = str(data.get("evidence") or "")
    if ask["question"]:
        ask["raw"] = ""  # parsed cleanly; no need for the fallback block
    return ask


def run_linter(script: Path, wd: Path, required: str, label: str) -> dict:
    """Run one read-only linter and parse its JSON. citations_lint.py prints
    indent=2, i.e. MULTI-LINE JSON — parse the whole stdout, not the last line."""
    out = {"label": label, "script": script.name, "state": "skip", "note": "", "data": {}}
    if not (wd / required).exists():
        out["note"] = f"{required} not present yet"
        return out
    if not script.exists():
        out["state"] = "error"
        out["note"] = f"gate script not found: {script}"
        return out
    try:
        r = subprocess.run([sys.executable, str(script), str(wd)],
                           capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=GATE_TIMEOUT)
    except subprocess.TimeoutExpired:
        out["state"] = "error"
        out["note"] = f"gate did not finish within {GATE_TIMEOUT}s"
        return out
    except OSError as e:
        out["state"] = "error"
        out["note"] = f"could not run gate: {e}"
        return out
    text = (r.stdout or "").strip()
    data = None
    if text:
        try:
            data = json.loads(text)
        except ValueError:
            try:
                data = json.loads(text.splitlines()[-1])
            except (ValueError, IndexError):
                data = None
    if not isinstance(data, dict):
        out["state"] = "error"
        out["note"] = f"gate printed no JSON (exit {r.returncode})"
        return out
    out["data"] = data
    out["state"] = "pass" if data.get("ok") else "fail"
    return out


def collect_gates(wd: Path) -> dict:
    return {
        "draft": run_linter(DRAFT_LINT, wd, "sections", "draft_lint"),
        "cites": run_linter(CITATIONS_LINT, wd, "refs.bib", "citations_lint"),
    }


# ---------------------------------------------------------------- main.log

WRAP = 79
OUT_LINE = re.compile(r"^Output written on (\S+) \((\d+) pages?, (\d+) bytes\)\.")
FILE_OPEN = re.compile(r'\((?:"([^"]+\.\w+)"|([^()\s{}"]+\.\w+))')
BANG = re.compile(r"^! (.*)$")
LNUM = re.compile(r"^l\.(\d+)\s?(.*)$")
WARN_UNDEF = re.compile(
    r"^LaTeX Warning: (Citation|Reference) `([^']+)' on page (\d+) undefined on input line (\d+)\.")
WARN_SUMM = re.compile(r"^LaTeX Warning: There were undefined (references|citations)\.")
OVERFULL = re.compile(r"^Overfull \\hbox \(([\d.]+)pt too wide\)")
BIB_USED = re.compile(r"You've used (\d+) entries")


def unwrap(text: str) -> list:
    """TeX hard-wraps message text at exactly 79 columns, splitting words and
    paths mid-token; rejoin before any matching."""
    out, buf = [], ""
    for ln in text.splitlines():
        buf += ln
        if len(ln) == WRAP:
            continue
        out.append(buf)
        buf = ""
    if buf:
        out.append(buf)
    return out


def collect_latex(wd: Path) -> dict:
    log = wd / "main.log"
    res = {"present": False, "pages": None, "bytes": None, "errors": [],
           "undefined": [], "summary": [], "overfull": 0, "bib_entries": None,
           "t": mtime(log), "pdf_t": mtime(wd / "main.pdf")}
    if not log.is_file():
        return res
    res["present"] = True
    lines = unwrap(read_text(log))
    stack = []
    for i, ln in enumerate(lines):
        for j, ch in enumerate(ln):
            if ch == "(":
                m = FILE_OPEN.match(ln, j)
                if m:
                    stack.append(m.group(1) or m.group(2))
            elif ch == ")" and stack:
                stack.pop()
        m = OUT_LINE.match(ln)
        if m:
            res["pages"], res["bytes"] = int(m.group(2)), int(m.group(3))
            continue
        m = BANG.match(ln)
        if m and "Fatal error occurred" not in ln:
            # -halt-on-error means at most one real error; the fatal trailer also
            # starts with "!" and must not be counted as a second one.
            lnum, ctx = None, ""
            for nxt in lines[i + 1:i + 8]:
                mm = LNUM.match(nxt)
                if mm:
                    lnum, ctx = int(mm.group(1)), mm.group(2)
                    break
            res["errors"].append({"file": stack[-1] if stack else "main.tex",
                                  "line": lnum, "message": m.group(1).strip(),
                                  "context": ctx.strip()})
            continue
        m = WARN_UNDEF.match(ln)
        if m:
            res["undefined"].append({"kind": m.group(1), "key": m.group(2),
                                     "page": m.group(3), "line": m.group(4)})
            continue
        if WARN_SUMM.match(ln):
            res["summary"].append(ln)
            continue
        if OVERFULL.match(ln):
            res["overfull"] += 1
    blg = wd / "main.blg"
    if blg.is_file():
        m = BIB_USED.search(read_text(blg))
        if m:
            res["bib_entries"] = int(m.group(1))
    # latexmk exits 0 and writes a PDF even with unresolved cites/refs, so the
    # verdict is derived here rather than from any exit code.
    if res["pages"] is None:
        res["verdict"] = "failed"
    elif res["errors"] or res["undefined"] or res["summary"]:
        res["verdict"] = "degraded"
    else:
        res["verdict"] = "ok"
    return res


def source_of(procfile: str, line=None) -> str:
    """Where the author should look. build/<sid>.proc.tex is generated, so it maps
    to sections/<sid>.tex and the line number is dropped — it does not survive the
    mapping. Every other file (main.tex, a .sty) is the real file the compiler read,
    so its line number is exact and is what makes the error findable."""
    name = Path(procfile.replace("\\", "/")).name
    if name.endswith(".proc.tex"):
        return f"sections/{name[:-len('.proc.tex')]}.tex"
    return f"{procfile}:{line}" if line else procfile


# ---------------------------------------------------------------- review

ISSUE = re.compile(r"^- \*\*(?P<id>[A-Z]-\d+)\s+(?P<sev>\w+)\s*\|\s*"
                   r"(?P<section>[^*|]+?)\*\*\s*\|(?P<rest>.*)$")


def _block(text: str, prefix: str) -> str:
    """Body of the first '## <prefix>...' section. Headings are decorated per
    stage ('## DECISIONS — issues (...)'), so match by prefix, never equality."""
    lines = text.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if ln.startswith("## ") and ln[3:].upper().startswith(prefix):
            start = i + 1
            break
    if start is None:
        return ""
    end = len(lines)
    for j in range(start, len(lines)):
        if lines[j].startswith("## "):
            end = j
            break
    return "\n".join(lines[start:end]).strip()


def collect_review(wd: Path) -> dict:
    p = wd / "logs" / "5_review.io.md"
    res = {"present": False, "issues": [], "leftover": "", "author_required": "",
           "t": mtime(p)}
    if not p.is_file():
        return res
    text = read_text(p)
    res["present"] = True
    body = _block(text, "DECISIONS")
    leftover = []
    for ln in body.splitlines():
        m = ISSUE.match(ln)
        if not m:
            if ln.strip():
                leftover.append(ln)
            continue
        f = [x.strip() for x in m.group("rest").split("|")]
        f += [""] * (4 - len(f))
        res["issues"].append({
            "id": m.group("id"), "sev": m.group("sev").lower(),
            "section": m.group("section").strip(),
            "quote": f[0], "criterion": f[1],
            "verdict": f[2].strip("*"), "fix": f[3],
        })
    # Anything the pattern did not claim is shown verbatim rather than dropped.
    res["leftover"] = "\n".join(leftover).strip()
    res["author_required"] = _block(text, "AUTHOR-REQUIRED")
    return res


# ---------------------------------------------------------------- figures

def collect_figures(wd: Path) -> dict:
    figs = wd / "figures"
    man = read_json(figs / "figures.manifest.json")
    res = {"present": man is not None, "items": [], "vector": 0}
    if not isinstance(man, dict):
        return res
    for f in man.get("figures", []):
        if not isinstance(f, dict):
            continue
        label = str(f.get("label", "?"))
        pdf = (figs / f"{label}.pdf").is_file()
        svg = (figs / f"{label}.svg").is_file()
        png = (figs / f"{label}.png").is_file()
        ref = str(f.get("reference_used") or "")
        # Thumbnail for the click-to-zoom lightbox. Only the SVG is inlined (as a
        # base64 data: URI so the page stays self-contained and makes no request):
        # it is small and vector, so it scales cleanly when enlarged. The PNGs are
        # >1 MB each and would bloat a page that reloads every 15 s.
        thumb = ""
        if svg:
            raw = read_bytes(figs / f"{label}.svg")
            if raw:
                thumb = "data:image/svg+xml;base64," + base64.b64encode(raw).decode("ascii")
        # Round counts come from the manifest and the gate-enforced repair log — never
        # from render intermediates, which stage 6 deletes once a figure is approved.
        audit = read_json(figs / "audit_logs" / f"{label}.audit.json")
        res["items"].append({
            "label": label, "type": str(f.get("type") or "—"),
            "engine": str(f.get("engine") or "—"),
            "grounding": str(f.get("grounding") or "—"), "ref": ref,
            "critic_rounds": f.get("critic_rounds"),
            "repaired": (figs / "repair_logs" / f"{label}.log").is_file(),
            "pdf": pdf, "svg": svg, "png": png, "thumb": thumb,
            "svg_rounds": f.get("svg_rounds"),
            "audit_ok": None if audit is None else bool(audit.get("ok")),
        })
        if pdf or svg:
            res["vector"] += 1
    return res


# ---------------------------------------------------------------- references

BIB = re.compile(r"(?m)^@(\w+)\s*[{(]\s*([^,\s]+)\s*,")


def collect_refs(wd: Path, gates: dict, latex: dict) -> dict:
    p = wd / "refs.bib"
    res = {"present": p.is_file(), "entries": 0, "cited": None, "issues": None,
           "warnings": None, "per_section": {}, "bib_entries": latex.get("bib_entries")}
    if res["present"]:
        entries = [t.lower() for t, _ in BIB.findall(read_text(p))]
        res["entries"] = len([t for t in entries
                              if t not in ("string", "comment", "preamble")])
    d = gates["cites"].get("data") or {}
    if d:
        res["cited"] = d.get("n_cited")
        res["issues"] = d.get("n_issues")
        res["warnings"] = d.get("n_warnings")
        res["per_section"] = d.get("cites_per_section") or {}
    return res


# ---------------------------------------------------------------- DoD

def collect_dod(review, refs, gates, figs, latex, fresh) -> list:
    """Every row is derived from evidence gathered above; an unobserved signal is
    reported as unobserved, never as a pass."""
    rows = []

    if review["present"]:
        n = len(review["issues"])
        if n or not review["leftover"]:
            rows.append(("y", t("dod_review_ran").format(count_phrase(n, "issue", "个问题"))))
        else:
            # The log is there but nothing parsed as an issue — say so rather than
            # green-light a file we could not read.
            rows.append(("p", t("dod_review_noparse")))
    else:
        rows.append(("n", t("dod_review_absent")))

    c = gates["cites"]
    if c["state"] in ("pass", "fail"):
        d = c["data"]
        ok = (d.get("n_issues") == 0) and bool(d.get("n_cited"))
        rows.append(("y" if ok else "n",
                     t("dod_cite_ok").format(d.get("n_cited"), d.get("n_entries"), d.get("n_issues"))))
    else:
        rows.append(("n", t("dod_cite_notobs")))

    d = gates["draft"]
    if d["state"] in ("pass", "fail"):
        n = d["data"].get("n", 0)
        rows.append(("y" if d["state"] == "pass" else "n",
                     t("dod_draft").format(count_phrase(n, "violation", "处违规"))))
    else:
        rows.append(("n", t("dod_draft_notobs")))

    if figs["present"]:
        tot = len(figs["items"])
        v = figs["vector"]
        mark = "y" if tot and v == tot else ("p" if v else "n")
        rows.append((mark, t("dod_figs").format(v, tot)))
    else:
        rows.append(("n", t("dod_figs_nomani")))

    if latex["present"]:
        if latex["verdict"] == "ok":
            rows.append(("y", t("dod_pdf_ok").format(latex["pages"])))
        elif latex["verdict"] == "degraded":
            rows.append(("p", t("dod_pdf_degraded").format(len(latex["undefined"]), len(latex["errors"]))))
        else:
            rows.append(("n", t("dod_pdf_nopdf")))
    else:
        rows.append(("n", t("dod_pdf_notcompiled")))

    if fresh["state"] == "fresh":
        rows.append(("y", t("dod_fresh_ok")))
    elif fresh["state"] == "stale":
        rows.append(("n", t("dod_fresh_stale")))
    else:
        rows.append(("n", t("dod_fresh_none")))
    return rows


# ---------------------------------------------------------------- doctor

OPTIONAL_KEYS = ("OPENROUTER_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY")


VERSIONISH = re.compile(r"\d+\.\d+")


def probe(exe: str, args) -> dict:
    """Presence + the version line of `<exe> --version`. Never spends a model call.

    Not line[0]: latexmk on a CP936 Windows console prints two codepage banner
    lines before "Latexmk, John Collins, ... Version 4.88"."""
    path = shutil.which(exe)
    if not path:
        return {"present": False}
    out = {"present": True, "path": path}
    try:
        r = subprocess.run([path, *args], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=PROBE_TIMEOUT)
        lines = [l.strip() for l in
                 ((r.stdout or "") + "\n" + (r.stderr or "")).splitlines() if l.strip()]
        if lines:
            picked = next((l for l in lines if VERSIONISH.search(l)), lines[0])
            out["version"] = picked[:90]
    except (OSError, subprocess.SubprocessError):
        pass  # present but unreportable is still present
    return out


# ------------------------------------------------- installed copies of this suite

# A manifest Claude Code rejects is a SILENT failure: the plugin is skipped, and
# the reason lands only in plugin_errors[] of the session's system/init event,
# which nobody reads. So a user's installed copy of this suite can be dead for
# weeks while the checkout in front of them looks perfect. Seen in the wild:
# "repository": {"type": "git", "url": "..."} — valid in package.json, rejected
# here, because the plugin schema wants repository as a plain string.

MANIFEST_GLOBS = ("skills/*/.claude-plugin/plugin.json",
                  "plugins/*/.claude-plugin/plugin.json",
                  "plugins/*/*/.claude-plugin/plugin.json")

JSON_TYPE = {dict: "object", list: "array", bool: "boolean",
             int: "number", float: "number", type(None): "null"}


def load_manifest(p: Path) -> tuple[dict | None, str | None]:
    """(manifest, problem). A manifest that will not parse is itself the problem."""
    try:
        data = json.loads(p.read_text(encoding="utf-8", errors="replace"))
    except OSError as e:
        return None, f"cannot read the manifest: {e.strerror or e}"
    except ValueError as e:
        return None, f"not valid JSON: {e}"
    if not isinstance(data, dict):
        return None, "top level is not a JSON object"
    return data, None


def manifest_problem(m: dict) -> str | None:
    """What the official loader checks before it will load a plugin at all."""
    for field in ("name", "version"):
        if not isinstance(m.get(field), str) or not m[field].strip():
            return f"{field} is missing or not a string"
    repo = m.get("repository")
    if repo is not None and not isinstance(repo, str):
        return (f"repository must be a string, not a JSON {JSON_TYPE.get(type(repo), 'value')}"
                " — Claude Code refuses to load the plugin")
    return None


def installed_copies() -> dict:
    """Installed copies of THIS plugin, and whether Claude Code can load each one.

    A copy counts as ours when its manifest name matches ours, or when the folder
    is named like our plugin root — the second rule is what still identifies a
    manifest too broken to read a name out of."""
    own, _ = load_manifest(SKILLS_ROOT.parent / ".claude-plugin" / "plugin.json")
    own_name = (own or {}).get("name")
    own_dir = SKILLS_ROOT.parent.name
    cfg = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
    blind = ("only these locations are scanned — a copy loaded from anywhere else "
             "(claude --plugin-dir, a marketplace clone outside the config dir) is "
             "invisible here")
    if not cfg.is_dir():
        return {"copies": [], "checked": [], "config_dir": str(cfg),
                "note": f"no {cfg} — nothing is installed there to check"}
    copies: list[dict] = []
    seen: set[str] = set()
    for g in MANIFEST_GLOBS:
        try:
            found = sorted(cfg.glob(g))
        except OSError:
            continue  # an unreadable branch of the tree is not a plugin problem
        for p in found:
            root = p.parent.parent
            key = str(root).lower()  # Windows hands back two spellings of one path
            if key in seen:
                continue
            m, problem = load_manifest(p)
            if root.name != own_dir and not (own_name and (m or {}).get("name") == own_name):
                continue
            seen.add(key)
            problem = problem or manifest_problem(m)
            copies.append({"path": str(root), "ok": problem is None, "problem": problem})
    return {"copies": copies, "config_dir": str(cfg), "note": blind,
            "checked": [str(cfg / g) for g in MANIFEST_GLOBS]}


def doctor() -> dict:
    """Only what stops the pipeline from starting. Optional keys are reported by
    NAME ONLY — a value is never read into this process's output."""
    env_keys = sorted(k for k in os.environ
                      if k.startswith(("TS_FIG_", "TS_EMBED_")) or k in OPTIONAL_KEYS)
    latexmk = probe("latexmk", ["--version"])
    if latexmk.get("present"):
        tex = probe("pdflatex", ["--version"])
        if tex.get("version"):
            latexmk["distro"] = tex["version"]
    return {
        "ok": True,
        "python": {"present": True, "version": sys.version.split()[0],
                   "executable": sys.executable},
        "claude": probe("claude", ["--version"]),
        "latexmk": latexmk,
        "installed": installed_copies(),
        "optional_keys_present": env_keys,
        "optional_keys_checked": ["TS_FIG_*", "TS_EMBED_*", *OPTIONAL_KEYS],
        "checked_at": stamp(datetime.now().timestamp()),
    }


# ---------------------------------------------------------------- CSS

CSS = """
:root {
  --bg: #f7f5f1; --card: #fffdf9; --line: #e3ded4; --line-strong: #cfc8ba;
  --ink: #211d17; --muted: #71695c; --faint: #a49b8c;
  --accent: #b45327; --accent-ink: #93411d; --accent-soft: #f6e7dd;
  --ok: #2f7d4f; --ok-soft: #e3efe7; --bad: #b23227; --bad-soft: #f6e2df;
  --warn: #9a6a15; --warn-soft: #f5ecd6; --pending: #b0a898; --pending-soft: #efece5;
  --thumb-bg: #f1ede5;
  --serif: Georgia, "Times New Roman", "Songti SC", SimSun, "Noto Serif CJK SC", "Microsoft YaHei", serif;
  --sans: system-ui, "Segoe UI", -apple-system, "PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif;
  --mono: ui-monospace, "Cascadia Code", Consolas, Menlo, "Microsoft YaHei", "PingFang SC", monospace;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #171310; --card: #1f1a15; --line: #352e24; --line-strong: #4a4133;
    --ink: #ece7dd; --muted: #a1988a; --faint: #7c7466;
    --accent: #e0855c; --accent-ink: #eb9e7b; --accent-soft: #35251c;
    --ok: #6fbf8f; --ok-soft: #1d2f24; --bad: #e08379; --bad-soft: #392019;
    --warn: #d9a955; --warn-soft: #352b17; --pending: #6f6759; --pending-soft: #262119;
    --thumb-bg: #262119;
  }
}
:root[data-theme="dark"] {
  --bg: #171310; --card: #1f1a15; --line: #352e24; --line-strong: #4a4133;
  --ink: #ece7dd; --muted: #a1988a; --faint: #7c7466;
  --accent: #e0855c; --accent-ink: #eb9e7b; --accent-soft: #35251c;
  --ok: #6fbf8f; --ok-soft: #1d2f24; --bad: #e08379; --bad-soft: #392019;
  --warn: #d9a955; --warn-soft: #352b17; --pending: #6f6759; --pending-soft: #262119;
  --thumb-bg: #262119;
}
:root[data-theme="light"] {
  --bg: #f7f5f1; --card: #fffdf9; --line: #e3ded4; --line-strong: #cfc8ba;
  --ink: #211d17; --muted: #71695c; --faint: #a49b8c;
  --accent: #b45327; --accent-ink: #93411d; --accent-soft: #f6e7dd;
  --ok: #2f7d4f; --ok-soft: #e3efe7; --bad: #b23227; --bad-soft: #f6e2df;
  --warn: #9a6a15; --warn-soft: #f5ecd6; --pending: #b0a898; --pending-soft: #efece5;
  --thumb-bg: #f1ede5;
}
* { box-sizing: border-box; }
body { background: var(--bg); color: var(--ink); font-family: var(--sans);
  font-size: 14.5px; line-height: 1.55; margin: 0; padding: 24px 16px 56px; }
.wrap { max-width: 1120px; margin: 0 auto; }

header.masthead { text-align: center; padding: 30px 20px 26px;
  border-top: 3px solid var(--ink); border-bottom: 1px solid var(--line-strong);
  margin-bottom: 22px; position: relative; }
.eyebrow { font-size: 11.5px; letter-spacing: 0.18em; text-transform: uppercase;
  color: var(--accent-ink); font-weight: 650; margin-bottom: 14px; }
h1.paper-title { font-family: var(--serif); font-size: clamp(23px, 3.4vw, 33px);
  font-weight: 500; line-height: 1.25; margin: 0 auto 14px; max-width: 21em;
  text-wrap: balance; overflow-wrap: break-word; }
.byline { font-family: var(--mono); font-size: 12px; color: var(--muted);
  display: flex; justify-content: center; gap: 8px 22px; flex-wrap: wrap; }
.byline b { color: var(--ink); font-weight: 600; }
.status-pill { position: absolute; top: 14px; right: 0; background: var(--accent-soft);
  color: var(--accent-ink); border: 1px solid var(--accent); border-radius: 999px;
  font-size: 11.5px; font-weight: 700; letter-spacing: 0.06em; padding: 4px 13px; }
.status-pill .dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%;
  background: var(--accent); margin-right: 7px; animation: pulse 1.6s ease-in-out infinite; }
@keyframes pulse { 50% { opacity: 0.3; } }
@media (prefers-reduced-motion: reduce) { .status-pill .dot { animation: none; } }

.banner { border: 1px solid var(--line-strong); border-left: 4px solid var(--line-strong);
  border-radius: 6px; padding: 9px 14px; font-size: 13px; margin-bottom: 24px;
  display: flex; gap: 6px 14px; align-items: baseline; flex-wrap: wrap; }
.banner b { font-weight: 650; }
.banner.stale { border-color: var(--warn); background: var(--warn-soft); color: var(--warn); }
.banner.stale b { color: var(--warn); }
.banner.fresh { border-color: var(--ok); background: transparent; color: var(--muted); }
.banner.fresh b { color: var(--ok); }
.banner.none { color: var(--muted); }

.rail-block { margin-bottom: 26px; }
.rail-scroll { overflow-x: auto; padding-bottom: 6px; }
.rail { display: flex; align-items: flex-start; min-width: 860px; }
.stage { flex: 1; text-align: center; position: relative; padding-top: 4px; min-width: 88px; }
.stage::before { content: ""; position: absolute; top: 19px; left: -50%;
  width: 100%; height: 2px; background: var(--line-strong); }
.stage:first-child::before { display: none; }
.stage.done::before, .stage.active::before { background: var(--ok); }
.stage .node { position: relative; z-index: 1; width: 30px; height: 30px; border-radius: 50%;
  margin: 0 auto 8px; display: flex; align-items: center; justify-content: center;
  font-family: var(--mono); font-size: 12.5px; font-weight: 700;
  border: 2px solid var(--line-strong); background: var(--card); color: var(--faint); }
.stage.done .node { border-color: var(--ok); background: var(--ok); color: var(--card); }
.stage.active .node { border-color: var(--accent); background: var(--accent-soft);
  color: var(--accent-ink); box-shadow: 0 0 0 4px var(--accent-soft); }
.stage .s-name { font-size: 12.5px; font-weight: 650; }
.stage .s-sub { font-family: var(--mono); font-size: 10.5px; color: var(--muted); margin-top: 1px; }
.stage.pending .s-name { color: var(--faint); font-weight: 500; }
.stage.active .s-name { color: var(--accent-ink); }
.rail-caption { margin-top: 12px; display: flex; justify-content: space-between;
  gap: 12px; flex-wrap: wrap; align-items: baseline; }
.rail-now { font-size: 13px; color: var(--muted); }
.rail-now b { color: var(--ink); }

.grid { display: grid; grid-template-columns: minmax(0, 1fr) 320px; gap: 18px; align-items: start; }
@media (max-width: 900px) { .grid { grid-template-columns: 1fr; } }
.col { display: flex; flex-direction: column; gap: 18px; min-width: 0; }
.card { background: var(--card); border: 1px solid var(--line); border-radius: 8px;
  padding: 16px 18px; }
.card h2 { font-size: 12px; letter-spacing: 0.14em; text-transform: uppercase;
  color: var(--muted); font-weight: 700; margin: 0 0 12px; display: flex;
  justify-content: space-between; align-items: baseline; gap: 10px; flex-wrap: wrap; }

.attention { border-left: 4px solid var(--warn); background: var(--warn-soft);
  border-color: var(--warn); margin-bottom: 18px; }
.attention h2 { color: var(--warn); }
.attention .q { font-size: 15px; font-weight: 600; margin-bottom: 8px; }
.attention ul { margin: 0 0 10px; padding-left: 20px; }
.attention li { margin-bottom: 3px; }
.attention .how { font-size: 12.5px; color: var(--muted);
  border-top: 1px dashed var(--warn); padding-top: 8px; }
.attention .how b { color: var(--warn); }

.tbl-scroll { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
th { text-align: left; font-size: 10.5px; text-transform: uppercase; letter-spacing: 0.1em;
  color: var(--faint); font-weight: 700; padding: 0 10px 6px 0;
  border-bottom: 1px solid var(--line-strong); white-space: nowrap; }
td { padding: 7px 10px 7px 0; border-bottom: 1px solid var(--line); vertical-align: top; }
tr:last-child td { border-bottom: none; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
.mono { font-family: var(--mono); font-size: 12px; }
.dim { color: var(--muted); }
.empty { color: var(--faint); font-size: 13px; }

pre.raw { font-family: var(--mono); font-size: 11.5px; line-height: 1.5;
  background: var(--thumb-bg); border: 1px solid var(--line); border-radius: 6px;
  padding: 10px 12px; margin: 10px 0 0; overflow-x: auto; white-space: pre; }

.chip { display: inline-block; font-size: 11px; font-weight: 700; border-radius: 999px;
  padding: 1.5px 9px; white-space: nowrap; }
.chip.ok { background: var(--ok-soft); color: var(--ok); }
.chip.bad { background: var(--bad-soft); color: var(--bad); }
.chip.warn { background: var(--warn-soft); color: var(--warn); }
.chip.off { background: var(--pending-soft); color: var(--pending); }
.chip.acc { background: var(--accent-soft); color: var(--accent-ink); }
.sev { font-family: var(--mono); font-size: 10.5px; font-weight: 700; padding: 1px 7px;
  border-radius: 3px; }
.sev.blocker { background: var(--bad); color: var(--card); }
.sev.major { background: var(--bad-soft); color: var(--bad); }
.sev.minor { background: var(--warn-soft); color: var(--warn); }
.sev.nit, .sev.other { background: var(--pending-soft); color: var(--pending); }

.figs { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px; }
.fig-card { border: 1px solid var(--line); border-radius: 6px; background: var(--card);
  padding: 10px 11px 11px; }
.fig-card .flabel { font-family: var(--mono); font-size: 11.5px; font-weight: 600;
  margin-bottom: 6px; overflow-wrap: anywhere; }
.fig-card .ftags { display: flex; gap: 5px; flex-wrap: wrap; }
.fig-card .fref { font-family: var(--mono); font-size: 10.5px; color: var(--faint);
  margin-top: 6px; overflow-wrap: anywhere; }

.dod { list-style: none; margin: 0; padding: 0; font-size: 13px; }
.dod li { display: flex; gap: 9px; align-items: baseline; padding: 5px 0;
  border-bottom: 1px solid var(--line); }
.dod li:last-child { border-bottom: none; }
.dod .mk { font-family: var(--mono); font-size: 12px; font-weight: 700; width: 15px; flex: none; }
.dod .mk.y { color: var(--ok); }
.dod .mk.n { color: var(--pending); }
.dod .mk.p { color: var(--accent-ink); }

.kv { font-size: 13px; }
.kv .row { display: flex; justify-content: space-between; gap: 12px; padding: 4.5px 0;
  border-bottom: 1px solid var(--line); }
.kv .row:last-child { border-bottom: none; }
.kv .k { color: var(--muted); }
.kv .v { font-family: var(--mono); font-size: 12px; text-align: right;
  font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }

footer { margin-top: 30px; border-top: 1px solid var(--line-strong); padding-top: 12px;
  font-family: var(--mono); font-size: 11.5px; color: var(--faint); display: flex;
  justify-content: space-between; gap: 8px 24px; flex-wrap: wrap; }

/* Collapsible cards — a click on the heading toggles the body. Enhancement only:
   with JS off every card stays open, exactly as before. */
.card h2.collapser { cursor: pointer; user-select: none; }
.card h2.collapser::after { content: "\\25be"; margin-left: auto; padding-left: 8px;
  font-size: 11px; color: var(--faint); transition: transform 0.15s; }
.card.collapsed h2.collapser::after { transform: rotate(-90deg); }
.card.collapsed .card-body { display: none; }
@media (prefers-reduced-motion: reduce) { .card h2.collapser::after { transition: none; } }

/* Figure thumbnail + click-to-zoom lightbox — an in-page overlay, no navigation
   and no request: the enlarged image is the same inlined data: URI as the thumb. */
.fig-thumb { display: block; width: 100%; height: 116px; object-fit: contain;
  background: var(--thumb-bg); border: 1px solid var(--line); border-radius: 5px;
  margin-bottom: 8px; cursor: zoom-in; }
#lightbox { position: fixed; inset: 0; z-index: 1000; display: none;
  align-items: center; justify-content: center; padding: 24px;
  background: rgba(0, 0, 0, 0.82); cursor: zoom-out; }
#lightbox.open { display: flex; }
#lightbox img { max-width: 96vw; max-height: 92vh; background: #fff;
  border-radius: 8px; box-shadow: 0 10px 44px rgba(0, 0, 0, 0.55); }
"""


# ---------------------------------------------------------------- inlined JS
# Self-contained: no external request, works inside the Cockpit iframe AND when
# report.html is opened over file://. Two enhancements only — collapsible cards
# and a click-to-zoom lightbox — both degrade to the plain page with JS off.
# Collapse state is kept in sessionStorage so the 15 s meta-refresh does not fight
# it; where sessionStorage is unavailable (some file:// sandboxes) it silently
# falls back to per-view toggling.
REPORT_JS = r"""
(function () {
  function enhance() {
    document.querySelectorAll('section.card').forEach(function (card, i) {
      var h2 = card.querySelector(':scope > h2');
      if (!h2) return;
      h2.classList.add('collapser');
      var body = document.createElement('div');
      body.className = 'card-body';
      while (h2.nextSibling) { body.appendChild(h2.nextSibling); }
      card.appendChild(body);
      var key = 'sb-collapse:' + (h2.textContent || i).trim().slice(0, 48);
      try { if (sessionStorage.getItem(key) === '1') card.classList.add('collapsed'); } catch (e) {}
      h2.addEventListener('click', function () {
        var on = card.classList.toggle('collapsed');
        try { sessionStorage.setItem(key, on ? '1' : '0'); } catch (e) {}
      });
    });
    var lb = document.getElementById('lightbox');
    var lbImg = lb ? lb.querySelector('img') : null;
    document.querySelectorAll('.fig-thumb').forEach(function (img) {
      img.addEventListener('click', function (e) {
        e.stopPropagation();
        if (!lb) return;
        lbImg.src = img.getAttribute('src');
        lb.classList.add('open');
      });
    });
    if (lb) { lb.addEventListener('click', function () { lb.classList.remove('open'); }); }
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && lb) { lb.classList.remove('open'); }
    });
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', enhance);
  } else { enhance(); }
})();
"""


# ---------------------------------------------------------------- renderers

def chip(text: str, kind: str = "off") -> str:
    return f'<span class="chip {kind}">{E(text)}</span>'


def kv_card(title: str, rows) -> str:
    body = "".join(f'<div class="row"><span class="k">{E(k)}</span>'
                   f'<span class="v">{E(str(v))}</span></div>' for k, v in rows)
    return f'<section class="card"><h2>{E(title)}</h2><div class="kv">{body}</div></section>'


def render_masthead(wd: Path, mast: dict, stages: dict, done: bool, now: float) -> str:
    cur = stages["current"]
    if done:
        pill = t("pill_done")
        dot = ""
    elif cur is None:
        pill = t("pill_nostage")
        dot = ""
    else:
        nm = stage_name(cur)
        pill = t("pill_stage").format(cur, len(STAGE_NAMES) - 1,
                                      nm.upper() if LANG == "en" else nm)
        dot = '<span class="dot"></span>'
    started = min([s["t"] for s in stages["rail"] if s["t"]] or [now])
    tpl = mast["template_id"] + (f' · {t("official")}' if mast["official"] else "")
    return (
        '<header class="masthead">'
        f'<div class="status-pill">{dot}{E(pill)}</div>'
        f'<div class="eyebrow">{E(t("eyebrow"))}</div>'
        f'<h1 class="paper-title">{E(mast["title"])}</h1>'
        '<div class="byline">'
        f'<span>{E(t("by_workdir"))} <b>{E(wd.name)}</b></span>'
        f'<span>{E(t("by_template"))} <b>{E(tpl)}</b></span>'
        f'<span>{E(t("by_mode"))} <b>{E(mast["results_mode"])}</b></span>'
        f'<span>{E(t("by_firstlog"))} <b>{E(clock(started))}</b></span>'
        f'<span>{E(t("by_generated"))} <b>{E(clock(now))}</b></span>'
        '</div></header>'
    )


def render_freshness(fresh: dict) -> str:
    if fresh["state"] == "none":
        return (f'<div class="banner none"><b>{E(t("fresh_none_b"))}</b>'
                f'<span>{t("fresh_none_s")}</span></div>')
    if fresh["state"] == "stale":
        src = fresh["src"].name if fresh["src"] else "a source file"
        sentence = t("fresh_stale_s").format(
            E(stamp(fresh["pdf_t"])), E(src), E(stamp(fresh["src_t"])))
        return (f'<div class="banner stale"><b>{E(t("fresh_stale_b"))}</b>'
                f'<span>{sentence}</span></div>')
    sentence = t("fresh_fresh_s").format(E(stamp(fresh["pdf_t"])))
    return (f'<div class="banner fresh"><b>{E(t("fresh_fresh_b"))}</b>'
            f'<span>{sentence}</span></div>')


def render_rail(stages: dict, done: bool) -> str:
    cur = stages["current"]
    cells = []
    for s in stages["rail"]:
        if s["path"] is None:
            cls, sub = "pending", "—"
        elif not done and s["n"] == cur:
            cls, sub = "active", clock(s["t"])
        else:
            cls, sub = "done", clock(s["t"])
        tip = f' title="{E(s["title"])}"' if s["title"] else ""
        cells.append(f'<div class="stage {cls}"{tip}><div class="node">{s["n"]}</div>'
                     f'<div class="s-name">{E(stage_name(s["n"]))}</div>'
                     f'<div class="s-sub">{E(sub)}</div></div>')
    if done:
        now_line = t("rail_done")
    elif cur is None:
        now_line = t("rail_nostage")
    else:
        r = stages["rail"][cur]
        now_line = t("rail_last").format(E(r["title"] or stage_name(r["n"])), E(stamp(r["t"])))
    extra = ""
    if stages["extra"]:
        names = ", ".join(r["name"] for r in stages["extra"])
        extra = f'<span class="mono dim">{E(t("rail_also").format(names))}</span>'
    return ('<section class="rail-block"><div class="rail-scroll"><div class="rail">'
            + "".join(cells) + '</div></div><div class="rail-caption">'
            f'<div class="rail-now">{E(t("rail_now"))} {now_line}</div>{extra}</div></section>')


def render_ask(ask) -> str:
    if not ask:
        return ""
    parts = [f'<section class="card attention"><h2>{E(t("ask_title"))}</h2>']
    if ask["question"]:
        parts.append(f'<div class="q">{E(ask["question"])}</div>')
        if ask["options"]:
            parts.append("<ul>" + "".join(f"<li>{E(o)}</li>" for o in ask["options"]) + "</ul>")
        if ask["evidence"]:
            parts.append(f'<pre class="raw">{E(ask["evidence"])}</pre>')
    else:
        # Malformed JSON in the fence: show it raw rather than swallow the question.
        parts.append(f'<div class="q">{E(t("ask_badjson"))}</div>')
        parts.append(f'<pre class="raw">{E(ask["raw"])}</pre>')
    parts.append('<div class="how">'
                 + t("ask_how").format(E(clock(ask["t"])), E(ask["source"]))
                 + '</div>')
    parts.append("</section>")
    return "".join(parts)


def _gate_row(g: dict, detail: str) -> str:
    kinds = {"pass": ("v_pass", "ok"), "fail": ("v_issues", "bad"),
             "skip": ("v_notyet", "off"), "error": ("v_noresult", "warn")}
    key, kind = kinds[g["state"]]
    text = t(key)
    return (f'<tr><td class="mono">{E(g["label"])}</td><td>{chip(text, kind)}</td>'
            f'<td class="dim">{detail}</td></tr>')


def _cite_row(item, where: str) -> str:
    """citations_lint issues and warnings share the {rule, key, n, band, note}
    shape; anything else is shown verbatim rather than dropped."""
    if not isinstance(item, dict):
        return f'<tr><td class="mono">{E(where)}</td><td class="mono">—</td>' \
               f'<td class="dim">{E(str(item))}</td></tr>'
    detail = str(item.get("note") or item.get("key") or "")
    if item.get("n") is not None:
        detail = f'n={item.get("n")} band={item.get("band")} — {detail}'
    return (f'<tr><td class="mono">{E(str(item.get("key") or where))}</td>'
            f'<td class="mono">{E(str(item.get("rule", "")))}</td>'
            f'<td class="dim">{E(detail)}</td></tr>')


def render_gates(gates: dict) -> str:
    d, c = gates["draft"], gates["cites"]
    if d["state"] in ("pass", "fail"):
        n = d["data"].get("n", 0)
        d_detail = t("gate_draft_detail").format(
            E(str(d["data"].get("template", ""))), count_phrase(n, "violation", "处违规"))
    else:
        d_detail = E(d["note"])
    if c["state"] in ("pass", "fail"):
        x = c["data"]
        c_detail = t("gate_cite_detail").format(
            x.get("n_entries"), x.get("n_cited"), x.get("n_issues"), x.get("n_warnings"))
    else:
        c_detail = E(c["note"])
    rows = [_gate_row(d, d_detail), _gate_row(c, c_detail)]
    lists = []
    for v in (d["data"].get("violations") or []):
        if isinstance(v, dict):
            lists.append(f'<tr><td class="mono">{E(str(v.get("file", "")))}</td>'
                         f'<td class="mono">{E(str(v.get("rule", "")))}</td>'
                         f'<td class="dim">{E(str(v.get("snippet", "")))}</td></tr>')
    for it in (c["data"].get("issues") or []):
        lists.append(_cite_row(it, "refs.bib"))
    for w in (c["data"].get("warnings") or []):
        lists.append(_cite_row(w, ""))
    detail = ""
    if lists:
        detail = ('<div class="tbl-scroll" style="margin-top:14px"><table>'
                  f'<tr><th>{E(t("col_where"))}</th><th>{E(t("col_rule"))}</th>'
                  f'<th>{E(t("col_detail"))}</th></tr>'
                  + "".join(lists) + "</table></div>")
    return (f'<section class="card"><h2>{E(t("gates_title"))} '
            '<span class="dim" style="text-transform:none;letter-spacing:0">'
            f'{E(t("gates_sub"))}</span></h2>'
            '<div class="tbl-scroll"><table>'
            f'<tr><th>{E(t("col_gate"))}</th><th>{E(t("col_verdict"))}</th>'
            f'<th>{E(t("col_detail"))}</th></tr>'
            + "".join(rows) + "</table></div>" + detail + "</section>")


def render_latex(latex: dict) -> str:
    if not latex["present"]:
        return (f'<section class="card"><h2>{E(t("latex_title"))}</h2>'
                f'<div class="empty">{E(t("latex_none"))}</div></section>')
    verdict = {"ok": (t("lx_clean"), "ok"), "degraded": (t("lx_degraded"), "warn"),
               "failed": (t("lx_nopdf"), "bad")}[latex["verdict"]]
    head = chip(*verdict)
    rows = [(t("lx_pages"), latex["pages"] if latex["pages"] is not None else t("lx_nopdf_val")),
            (t("lx_compiled"), stamp(latex["t"]))]
    if latex["bytes"]:
        rows.append((t("lx_size"), t("lx_bytes").format(latex["bytes"])))
    if latex["overfull"]:
        rows.append((t("lx_overfull"), latex["overfull"]))
    body = "".join(f'<div class="row"><span class="k">{E(k)}</span>'
                   f'<span class="v">{E(str(v))}</span></div>' for k, v in rows)
    parts = [f'<section class="card"><h2>{E(t("latex_title"))} {head}</h2><div class="kv">{body}</div>']
    if latex["errors"]:
        rows = "".join(
            f'<tr><td class="mono">{E(source_of(e["file"], e["line"]))}</td>'
            f'<td>{chip(t("lx_error"), "bad")}</td>'
            f'<td><div>{E(e["message"])}</div>'
            f'<div class="mono dim">{E(e["context"])}</div></td></tr>'
            for e in latex["errors"])
        parts.append('<div class="tbl-scroll" style="margin-top:12px"><table>'
                     f'<tr><th>{E(t("col_source"))}</th><th></th><th>{E(t("col_message"))}</th></tr>'
                     + rows + '</table></div>'
                     '<div class="dim" style="font-size:12px;margin-top:8px">'
                     + t("lx_errnote") + '</div>')
    if latex["undefined"] or latex["summary"]:
        rows = "".join(
            f'<tr><td class="mono">{E(u["kind"])}</td><td class="mono">{E(u["key"])}</td>'
            f'<td class="dim">page {E(u["page"])} · input line {E(u["line"])}</td></tr>'
            for u in latex["undefined"])
        note = ('<div class="dim" style="font-size:12px;margin-top:8px">'
                + t("lx_undefnote") + '</div>') if latex["undefined"] or latex["summary"] else ""
        parts.append('<div class="tbl-scroll" style="margin-top:12px"><table>'
                     f'<tr><th>{E(t("col_kind"))}</th><th>{E(t("col_key"))}</th>'
                     f'<th>{E(t("col_where"))}</th></tr>'
                     + (rows or f'<tr><td colspan="3" class="dim">{E("; ".join(latex["summary"]))}</td></tr>')
                     + "</table></div>" + note)
    if not latex["errors"] and not latex["undefined"] and not latex["summary"]:
        parts.append('<div class="empty" style="margin-top:10px">'
                     + E(t("lx_clean_empty")) + '</div>')
    parts.append("</section>")
    return "".join(parts)


def render_review(review: dict) -> str:
    if not review["present"]:
        return (f'<section class="card"><h2>{E(t("review_title"))}</h2>'
                f'<div class="empty">{E(t("review_none"))}</div></section>')
    sev_rank = {"blocker": 0, "major": 1, "minor": 2, "nit": 3}
    counts = {}
    for i in review["issues"]:
        counts[i["sev"]] = counts.get(i["sev"], 0) + 1
    summary = " · ".join(f"{n} {s}" for s, n in
                             sorted(counts.items(), key=lambda kv: sev_rank.get(kv[0], 9)))
    rows = []
    for i in review["issues"]:
        sev_cls = i["sev"] if i["sev"] in sev_rank else "other"
        v = i["verdict"].lower()
        if any(k in v for k in ("fix", "resolved", "closed")):
            vchip = chip(i["verdict"] or "closed", "ok")
        elif any(k in v for k in ("defer", "drop", "wontfix", "author")):
            vchip = chip(i["verdict"], "off")
        else:
            vchip = chip(i["verdict"] or "—", "warn")
        rows.append(f'<tr><td class="mono">{E(i["id"])}</td>'
                    f'<td><span class="sev {sev_cls}">{E(i["sev"].upper())}</span></td>'
                    f'<td class="dim">{E(i["section"])}</td>'
                    f'<td>{E(i["quote"])}<div class="dim" style="margin-top:3px">'
                    f'{E(t("review_close").format(i["criterion"]))}</div></td>'
                    f'<td>{vchip}</td></tr>')
    parts = [f'<section class="card"><h2>{E(t("review_title"))} ']
    parts.append(chip(count_phrase(len(review["issues"]), "issue", "个问题")
                      + (f" · {summary}" if summary else ""),
                      "ok" if review["issues"] else "off"))
    parts.append("</h2>")
    if rows:
        parts.append('<div class="tbl-scroll"><table>'
                     f'<tr><th>{E(t("col_id"))}</th><th>{E(t("col_sev"))}</th>'
                     f'<th>{E(t("col_section"))}</th><th>{E(t("col_issue"))}</th>'
                     f'<th>{E(t("col_verdict"))}</th></tr>'
                     + "".join(rows) + "</table></div>")
    if review["leftover"]:
        label = t("review_leftover_rows") if rows else t("review_leftover_norows")
        parts.append(f'<div class="dim" style="font-size:12px;margin-top:12px">{E(label)}</div>'
                     f'<pre class="raw">{E(review["leftover"])}</pre>')
    if review["author_required"]:
        parts.append('<div class="dim" style="font-size:12px;margin-top:14px">'
                     f'{E(t("review_authreq"))}</div>'
                     f'<pre class="raw">{E(review["author_required"])}</pre>')
    parts.append("</section>")
    return "".join(parts)


def render_figures(figs: dict) -> str:
    if not figs["present"]:
        return (f'<section class="card"><h2>{E(t("figs_title"))}</h2>'
                f'<div class="empty">{E(t("figs_none"))}</div></section>')
    if not figs["items"]:
        return (f'<section class="card"><h2>{E(t("figs_title"))}</h2>'
                f'<div class="empty">{E(t("figs_empty"))}</div></section>')
    cards = []
    for f in figs["items"]:
        tags = [chip(f["engine"], "acc")]
        if f["pdf"] and f["svg"]:
            tags.append(chip("PDF + SVG", "ok"))
        elif f["pdf"] or f["svg"]:
            tags.append(chip("PDF" if f["pdf"] else "SVG", "ok"))
        elif f["png"]:
            tags.append(chip(t("fig_pngonly"), "warn"))
        else:
            tags.append(chip(t("fig_noartifact"), "bad"))
        if f["critic_rounds"]:
            tags.append(chip(t("fig_critique").format(f["critic_rounds"]), "off"))
            # The gate reads the log, not the manifest: claimed rounds with no log is a red stage 6.
            if not f["repaired"]:
                tags.append(chip(t("fig_nocritlog"), "bad"))
        if f["svg_rounds"]:
            tags.append(chip(t("fig_svgr").format(f["svg_rounds"]), "off"))
        if f["audit_ok"] is not None:
            tags.append(chip(t("fig_audit_ok") if f["audit_ok"] else t("fig_audit_bad"),
                             "ok" if f["audit_ok"] else "bad"))
        # Inlined vector thumbnail — click enlarges the same data: URI (see lightbox).
        thumb = ""
        if f["thumb"]:
            thumb = (f'<img class="fig-thumb" src="{f["thumb"]}" loading="lazy" '
                     f'alt="{E(f["label"])}" title="{E(t("fig_zoom"))}">')
        cards.append(f'<div class="fig-card">{thumb}<div class="flabel">{E(f["label"])}</div>'
                     f'<div class="ftags">{"".join(tags)}</div>'
                     f'<div class="fref">{E(f["type"])} · {E(f["ref"] or f["grounding"])}</div></div>')
    return (f'<section class="card"><h2>{E(t("figs_title"))} '
            + chip(t("figs_vector").format(figs["vector"], len(figs["items"])), "ok"
                   if figs["vector"] == len(figs["items"]) else "warn")
            + '</h2><div class="figs">' + "".join(cards) + "</div></section>")


def render_blueprint(wd: Path) -> str:
    bp = read_json(wd / "blueprint.json")
    if not isinstance(bp, dict):
        return (f'<section class="card"><h2>{E(t("bp_title"))}</h2>'
                f'<div class="empty">{E(t("bp_none"))}</div></section>')
    order = bp.get("section_order") or []
    secs = bp.get("sections") or {}
    lo = hi = 0
    nfig = ntab = 0
    for sid in order:
        s = secs.get(sid) or {}
        band = s.get("target_words") or []
        if isinstance(band, list) and len(band) == 2:
            try:
                lo += int(band[0]); hi += int(band[1])
            except (TypeError, ValueError):
                pass
        nfig += len(s.get("figures") or [])
        ntab += len(s.get("tables") or [])
    abstract = t("bp_abstract") if (wd / "sections" / "abstract.tex").is_file() else ""
    rows = [(t("bp_sections"), f"{len(order)}{abstract}"),
            (t("bp_words"), f"{lo}–{hi}" if hi else "—"),
            (t("bp_contrib"), len(bp.get("contributions") or [])),
            (t("bp_figs"), nfig),
            (t("bp_tabs"), ntab),
            (t("bp_notation"), len(bp.get("notation") or {}))]
    return kv_card(t("bp_title"), rows)


def render_refs(refs: dict) -> str:
    if not refs["present"]:
        return (f'<section class="card"><h2>{E(t("refs_title"))}</h2>'
                f'<div class="empty">{E(t("refs_none"))}</div></section>')
    per = refs["per_section"] or {}
    densest = max(per.items(), key=lambda kv: kv[1]) if per else None
    rows = [(t("refs_entries"), refs["entries"])]
    if refs["cited"] is not None:
        rows.append((t("refs_cited"), refs["cited"]))
        rows.append((t("refs_issues"), f'{refs["issues"]} · {refs["warnings"]}'))
    if refs["bib_entries"] is not None:
        rows.append((t("refs_resolved"), refs["bib_entries"]))
    if densest:
        rows.append((t("refs_densest"), f"{densest[0]} · {densest[1]}"))
    return kv_card(t("refs_title"), rows)


def render_dod(rows) -> str:
    marks = {"y": "✓", "p": "◐", "n": "·"}
    body = "".join(f'<li><span class="mk {m}">{marks[m]}</span>{E(label)}</li>'
                   for m, label in rows)
    return (f'<section class="card"><h2>{E(t("dod_title"))}</h2>'
            f'<ul class="dod">{body}</ul></section>')


def render_env(doc: dict) -> str:
    def one(d: dict) -> str:
        if not d.get("present"):
            return t("env_absent")
        return d.get("version") or t("env_present")
    rows = [("claude", one(doc["claude"])),
            ("Python", doc["python"]["version"]),
            ("latexmk", one(doc["latexmk"]))]
    if doc["latexmk"].get("distro"):
        rows.append((t("env_tex"), doc["latexmk"]["distro"]))
    keys = doc["optional_keys_present"]
    rows.append((t("env_optkeys"), ", ".join(keys) if keys else t("env_none")))
    return kv_card(t("env_title"), rows)


def render_page(wd: Path, data: dict) -> str:
    mast = data["mast"]
    title = f'SparkBoard — {mast["title"][:70]}'
    body = "".join([
        render_masthead(wd, mast, data["stages"], data["done"], data["now"]),
        render_freshness(data["fresh"]),
        render_rail(data["stages"], data["done"]),
        render_ask(data["ask"]),
        '<div class="grid"><div class="col">',
        render_gates(data["gates"]),
        render_latex(data["latex"]),
        render_review(data["review"]),
        render_figures(data["figs"]),
        '</div><div class="col">',
        render_blueprint(wd),
        render_refs(data["refs"]),
        render_dod(data["dod"]),
        render_env(data["doctor"]),
        "</div></div>",
        '<footer>'
        f'<span>{E(t("foot_gen").format(stamp(data["now"]), REFRESH_SECONDS))}</span>'
        f'<span>{E(t("foot_truth").format(str(wd)))}</span></footer>',
    ])
    lang_attr = "zh" if LANG == "zh" else "en"
    return (f'<!doctype html>\n<html lang="{lang_attr}">\n<head>\n'
            '<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f'<meta http-equiv="refresh" content="{REFRESH_SECONDS}">\n'
            f"<title>{E(title)}</title>\n<style>{CSS}</style>\n</head>\n"
            f'<body>\n<div class="wrap">{body}</div>\n'
            '<div id="lightbox" role="dialog" aria-modal="true"><img alt=""></div>\n'
            f"<script>{REPORT_JS}</script>\n"
            '</body>\n</html>\n')


# ---------------------------------------------------------------- build

def build(wd: Path) -> dict:
    """Gather every panel independently, then write report.html. A panel whose
    input is missing renders as 'not yet'; none of them can fail the page."""
    warnings = []
    mast = collect_masthead(wd)
    if not mast["have_title"]:
        warnings.append("no blueprint.json paper_title; using the workdir name")
    fresh = collect_freshness(wd)
    if fresh["state"] == "stale":
        warnings.append("main.pdf is older than a source file")
    stages = collect_stages(wd)
    ask = collect_ask(stages)
    gates = collect_gates(wd)
    for g in gates.values():
        if g["state"] == "error":
            warnings.append(f'{g["label"]}: {g["note"]}')
    latex = collect_latex(wd)
    review = collect_review(wd)
    figs = collect_figures(wd)
    refs = collect_refs(wd, gates, latex)
    dod = collect_dod(review, refs, gates, figs, latex, fresh)
    done = all(m == "y" for m, _ in dod)
    data = {"mast": mast, "fresh": fresh, "stages": stages, "ask": ask, "gates": gates,
            "latex": latex, "review": review, "figs": figs, "refs": refs, "dod": dod,
            "done": done, "doctor": doctor(), "now": datetime.now().timestamp()}
    out = wd / "report.html"
    out.write_text(render_page(wd, data), encoding="utf-8")
    cur = stages["current"]
    stage = "done" if done else (f"{cur} {STAGE_NAMES[cur].lower()}" if cur is not None
                                 else "not started")
    return {"ok": True, "report": str(out), "stage": stage, "warnings": warnings}


def is_workdir(d: Path) -> bool:
    """blueprint.json, or a logs/ holding at least one stage log. A bare logs/ is
    not enough: every git repo has .git/logs/."""
    if (d / "blueprint.json").is_file():
        return True
    logs = d / "logs"
    return logs.is_dir() and any(logs.glob("*.io.md"))


def find_workdir(start: Path):
    """Walk up from a written path to the enclosing paper workdir."""
    p = start if start.is_dir() else start.parent
    for cand in [p, *p.parents]:
        if is_workdir(cand):
            return cand
    return None


def from_hook() -> None:
    """PostToolUse entry. Silent on every path that is not a paper workdir, and
    silent on every exception: a hook must never break a run."""
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        ti = payload.get("tool_input") or {}
        cands = [ti.get("file_path"), ti.get("path"), ti.get("notebook_path"),
                 payload.get("cwd")]
        for c in cands:
            if not c:
                continue
            wd = find_workdir(Path(str(c)))
            if wd is not None:
                build(wd)
                return
    except Exception:
        pass  # deliberately total: no hook failure may surface to the session


def parse_lang(argv: list) -> list:
    """Pull --lang zh / --lang=zh out of argv (any position), set LANG, and return
    the remaining args so the positional workdir parse is unaffected. Default en."""
    rest, i = [], 0
    lang = "en"
    while i < len(argv):
        a = argv[i]
        if a == "--lang":
            if i + 1 < len(argv):
                lang = argv[i + 1]
                i += 2
                continue
            i += 1
            continue
        if a.startswith("--lang="):
            lang = a[len("--lang="):]
            i += 1
            continue
        rest.append(a)
        i += 1
    set_lang(lang)
    return rest


def main() -> None:
    argv = parse_lang(sys.argv[1:])
    if "--doctor" in argv:
        print(json.dumps(doctor()))
        sys.exit(0)
    if "--from-hook" in argv:
        from_hook()
        sys.exit(0)
    if not argv:
        print(json.dumps({"ok": False,
                          "error": "usage: build_report.py <workdir> | --doctor | --from-hook"}))
        sys.exit(1)
    wd = Path(argv[0]).resolve()
    if not wd.is_dir():
        print(json.dumps({"ok": False, "error": f"workdir not a directory: {wd}"}))
        sys.exit(1)
    try:
        print(json.dumps(build(wd)))
    except OSError as e:
        print(json.dumps({"ok": False, "error": f"could not write report.html: {e}"}))
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
