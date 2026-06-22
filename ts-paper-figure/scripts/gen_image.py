#!/usr/bin/env python3
"""gen_image.py — the ONLY irreducible piece of the figure pipeline: call an external
image model to render ONE prompt into a PNG. Everything else (planning the prompt,
critiquing the result, refining, inserting into LaTeX) is done by Claude Code natively.

Claude cannot draw pixels, so this thin tool exists. It does NOT reason about figures —
it just renders the exact prompt Claude hands it.

Config (image model only — text/planning/critique is Claude, needs no config):
  TS_FIG_MODEL      image model name        e.g. gemini-3.1-flash-image-preview
  TS_FIG_API_KEY    image API key
  TS_FIG_BASE_URL   OpenAI-compatible base  e.g. https://sogenport.com/v1
  TS_FIG_API_STYLE  images | chat           default "images"
                    ("images" = OpenAI /images/generations; "chat" = /chat/completions
                     with image output, for nano-banana-style gateways)
  TS_FIG_SIZE       image size              default "1536x1024"
                    (images style only; in chat style it is appended to the prompt as a hint)
  TS_FIG_QUALITY    render quality          default "high"  (gpt-image-* models only)

Usage:
  python3 gen_image.py --prompt-file PROMPT.txt --out figures/overview.png
  python3 gen_image.py --prompt "a clean flat vector schematic of ..." --out fig.png
  echo "<prompt>" | python3 gen_image.py --out fig.png        # prompt on stdin

Prints a JSON status line. Exit 0 on a saved PNG, non-zero otherwise — so Claude can
see whether to retry/refine.
"""
from __future__ import annotations

import _dotenv  # noqa: F401  -- auto-load unified .env for API keys
import argparse, base64, json, os, sys, time, urllib.request, urllib.error
from pathlib import Path


def _post_json(url: str, payload: dict, key: str, timeout: int = 180) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _extract_image_bytes(j: dict) -> bytes | None:
    """Pull image bytes out of either an images-style or chat-style response."""
    # images style: {"data":[{"b64_json":...}|{"url":...}]}
    for d in (j.get("data") or []):
        if isinstance(d, dict) and d.get("b64_json"):
            return base64.b64decode(d["b64_json"])
        if isinstance(d, dict) and d.get("url"):
            with urllib.request.urlopen(d["url"], timeout=120) as r:
                return r.read()
    # chat style: choices[0].message.{images|content}
    for ch in (j.get("choices") or []):
        msg = (ch or {}).get("message") or {}
        for im in (msg.get("images") or []):
            u = (im.get("image_url") or {}).get("url") or im.get("url") or ""
            if u.startswith("data:"):
                return base64.b64decode(u.split(",", 1)[1])
            if u.startswith("http"):
                with urllib.request.urlopen(u, timeout=120) as r:
                    return r.read()
        c = msg.get("content")
        if isinstance(c, str) and c.startswith("data:"):
            return base64.b64decode(c.split(",", 1)[1])
    return None


def render(prompt: str, out_path: Path, retries: int = 3) -> dict:
    # MANDATED model: default to gpt-image-2 when unset — NEVER auto-pick another (e.g. gpt-image-1).
    model = os.environ.get("TS_FIG_MODEL", "gpt-image-2").strip() or "gpt-image-2"
    key = os.environ.get("TS_FIG_API_KEY", "").strip()
    base = os.environ.get("TS_FIG_BASE_URL", "").strip().rstrip("/")
    style = os.environ.get("TS_FIG_API_STYLE", "images").strip().lower()
    missing = [n for n, v in (("TS_FIG_API_KEY", key), ("TS_FIG_BASE_URL", base)) if not v]
    if missing:
        return {"ok": False, "error": f"unset env: {', '.join(missing)}"}

    if style == "chat":
        # chat gateways control resolution; pass the requested size as a SOFT prompt hint
        # only (no unknown payload field that could break a gateway).
        size = os.environ.get("TS_FIG_SIZE", "1536x1024").strip()
        chat_prompt = f"{prompt}\n\n(Render at approximately {size} resolution.)" if size else prompt
        url = f"{base}/chat/completions"
        payload = {"model": model, "modalities": ["image", "text"],
                   "messages": [{"role": "user", "content": chat_prompt}]}
    else:
        size = os.environ.get("TS_FIG_SIZE", "1536x1024").strip()   # landscape default (diagrams)
        url = f"{base}/images/generations"
        payload = {"model": model, "prompt": prompt, "n": 1, "size": size}
        if model.lower().startswith("gpt-image"):
            # mirror the product's GPT-Image quality knobs; these models always return b64_json
            # and REJECT response_format, so don't send it.
            payload.update({"quality": os.environ.get("TS_FIG_QUALITY", "high"),
                            "background": "opaque", "output_format": "png"})
        else:
            payload["response_format"] = "b64_json"   # DALL·E-style

    last = ""
    for attempt in range(1, retries + 1):
        try:
            j = _post_json(url, payload, key)
            data = _extract_image_bytes(j)
            if data:
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_bytes(data)
                return {"ok": True, "out": str(out_path), "bytes": len(data),
                        "style": style, "attempt": attempt}
            last = f"no image in response (keys={list(j)[:6]}); try TS_FIG_API_STYLE=chat?"
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}: {e.read().decode(errors='ignore')[:200]}"
        except Exception as e:
            last = f"{type(e).__name__}: {e}"
        if attempt < retries:
            time.sleep(4 * attempt)
    return {"ok": False, "error": last, "attempts": retries}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", default=None)
    ap.add_argument("--prompt-file", default=None)
    ap.add_argument("--out", required=True)
    ap.add_argument("--retries", type=int, default=3)
    a = ap.parse_args()
    if a.prompt is not None:
        prompt = a.prompt
    elif a.prompt_file:
        prompt = Path(a.prompt_file).read_text()
    else:
        prompt = sys.stdin.read()
    prompt = prompt.strip()
    if not prompt:
        print(json.dumps({"ok": False, "error": "empty prompt"})); sys.exit(2)
    result = render(prompt, Path(a.out).resolve(), retries=a.retries)
    print(json.dumps(result, ensure_ascii=False))
    sys.exit(0 if result.get("ok") else 1)


if __name__ == "__main__":
    main()
