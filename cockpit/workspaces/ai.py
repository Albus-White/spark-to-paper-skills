#!/usr/bin/env python3
"""Reading-AI proxy — the restrained, on-demand summary / explain / translate /
ask feature (PaperRss's "Reading First, AI Second"), server side.

Talks to any OpenAI-compatible /chat/completions (DeepSeek is the recommended
default). The key lives in the SAME .env the rest of the cockpit uses — nothing
here is stored elsewhere, and text reaches a model ONLY when the user asks (the
page never calls /api/ai on its own). Streaming is the whole point: the first
token should land fast, so the reader feels responsive, not modal.

stdlib only.
"""
from __future__ import annotations
import json
import urllib.request
import urllib.error

DEFAULT_BASE = "https://api.deepseek.com"

# What we read from the .env. The reading-AI keys are separate from the pipeline's
# OpenAI key so a researcher can point reading at a cheap DeepSeek model while the
# figure/vision stages use something else — but we fall back to OPENAI_* so a
# single configured key just works.
def config(env: dict) -> dict:
    base = (env.get("SPARKBOARD_AI_BASE_URL") or "").rstrip("/")
    key = env.get("SPARKBOARD_AI_KEY") or ""
    model = env.get("SPARKBOARD_AI_MODEL") or ""
    if not key:                                   # fall back to a general key
        key = env.get("OPENAI_API_KEY") or ""
        if key and not base:
            base = (env.get("VISION_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
    if not base:
        base = DEFAULT_BASE
    if not model:
        model = "deepseek-chat" if "deepseek" in base else "gpt-4o-mini"
    return {"base": base, "key": key, "model": model}


# Tuned like PaperRss: explanations are short and plain, translations preserve the
# scaffolding of a paper (numbers, symbols, names), summaries drop the preamble.
SYSTEM = {
    "summary": "You summarize a research article for a busy researcher. 3–6 tight "
               "sentences or bullets. No preamble, no 'this article/paper'. Keep the "
               "author's language. Markdown allowed.",
    "explain": "Explain the selected passage in plain language for a researcher, in "
               "the context of the whole article. 100–180 characters. No literary or "
               "reading-comprehension analysis, no padding. Answer in the user's language.",
    "translate": "Translate the selected text into {lang}. Preserve markdown, numbers, "
                 "math symbols and proper names verbatim. Output only the translation.",
    "ask": "Answer the user's question about the selected text, grounded strictly in it "
           "and the article. 120–220 characters, plain language, no padding. If the text "
           "does not support an answer, say so.",
    # Wiki "teach" is citation-bound: it must answer only from the supplied corpus context.
    "teach": "You are a wiki librarian. Answer ONLY from the provided wiki context. Every "
             "claim must be traceable to it; if it is not covered, reply 'not in wiki'. "
             "Cite the note/section you used. Answer in the user's language.",
}


def _messages(op: str, text: str, context: str, target_lang: str) -> list:
    sysmsg = SYSTEM.get(op, SYSTEM["explain"])
    if op == "translate":
        sysmsg = sysmsg.replace("{lang}", target_lang or "简体中文")
    if op == "summary":
        user = "Summarize:\n\n" + (text or "")[:8000]
    elif op == "ask":
        user = f"Selected text:\n{(text or '')[:3000]}\n\nQuestion: {context or ''}"
    elif op == "translate":
        user = (text or "")[:3000]
    elif op == "teach":
        user = f"Wiki context:\n{(context or '')[:8000]}\n\nQuestion: {text or ''}"
    else:  # explain
        extra = ("\n\n[surrounding context]\n" + context[:2000]) if context else ""
        user = f"Passage: {(text or '')[:2000]}{extra}"
    return [{"role": "system", "content": sysmsg}, {"role": "user", "content": user}]


def stream(op: str, text: str, context: str = "", target_lang: str = "", env: dict | None = None):
    """Yield text deltas. Never raises to the caller — connection problems come
    back as a short, honest human line so the popover degrades instead of hanging."""
    cfg = config(env or {})
    if not cfg["key"]:
        yield ("（未配置阅读助手模型：在「设置 → 阅读助手」填入 DeepSeek / OpenAI 兼容的 "
               "Base URL、API Key 与模型名。文本只在你点按后才会发送。）")
        return
    payload = json.dumps({
        "model": cfg["model"],
        "messages": _messages(op, text, context, target_lang),
        "stream": True,
        "temperature": 0.2,
    }).encode("utf-8")
    req = urllib.request.Request(
        cfg["base"].rstrip("/") + "/chat/completions", data=payload,
        headers={"Authorization": "Bearer " + cfg["key"], "Content-Type": "application/json"})
    got = False
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            for raw in r:
                line = raw.decode("utf-8", "replace").strip()
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    obj = json.loads(data)
                except ValueError:
                    continue
                delta = (((obj.get("choices") or [{}])[0]).get("delta") or {}).get("content")
                if delta:
                    got = True
                    yield delta
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = json.loads(e.read().decode("utf-8", "replace")).get("error", {}).get("message", "")
        except Exception:
            pass
        yield f"（模型接口报错 HTTP {e.code}{'：' + detail if detail else ''}）"
        return
    except (urllib.error.URLError, OSError) as e:
        if not got:                               # some proxies refuse SSE — try once, plainly
            yield from _once(cfg, op, text, context, target_lang)
        return


def _once(cfg: dict, op: str, text: str, context: str, target_lang: str):
    payload = json.dumps({
        "model": cfg["model"], "messages": _messages(op, text, context, target_lang),
        "temperature": 0.2,
    }).encode("utf-8")
    req = urllib.request.Request(
        cfg["base"].rstrip("/") + "/chat/completions", data=payload,
        headers={"Authorization": "Bearer " + cfg["key"], "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            obj = json.loads(r.read().decode("utf-8", "replace"))
        yield (((obj.get("choices") or [{}])[0]).get("message") or {}).get("content") or ""
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError) as e:
        yield f"（模型接口连接失败：{type(e).__name__}）"


if __name__ == "__main__":
    # smoke test: python -m cockpit.workspaces.ai  (needs a configured .env or prints the notice)
    import os
    env = dict(os.environ)
    for chunk in stream("explain", "attribution-shift moves failure from model ability to permission coupling.", env=env):
        print(chunk, end="", flush=True)
    print()
