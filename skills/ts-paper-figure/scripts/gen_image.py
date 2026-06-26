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
import argparse, base64, json, mimetypes, os, sys, time, urllib.request, urllib.error, uuid
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


def _build_edits_request(base, model, prompt, refs, size):
    """Build a multipart/form-data POST to {base}/images/edits with reference image(s)."""
    boundary = "----pb" + uuid.uuid4().hex
    field = "image" if len(refs) == 1 else "image[]"   # OpenAI uses image[] for multiple
    parts = []
    for k, v in (("model", model), ("prompt", prompt), ("size", size), ("n", "1")):
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
    for p in refs:
        fn = p.split("/")[-1]; ct = mimetypes.guess_type(p)[0] or "image/png"
        parts.append((f"--{boundary}\r\nContent-Disposition: form-data; name=\"{field}\"; "
                      f"filename=\"{fn}\"\r\nContent-Type: {ct}\r\n\r\n").encode())
        parts.append(open(p, "rb").read() + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return f"{base}/images/edits", b"".join(parts), f"multipart/form-data; boundary={boundary}"


def _post_multipart(url, body, ctype, key, timeout=300):
    req = urllib.request.Request(url, data=body, method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": ctype})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def render(prompt: str, out_path: Path, retries: int = 3, references=None) -> dict:
    """Render a prompt to a PNG. If reference image(s) are given and the endpoint is a
    gpt-image images-style endpoint, GROUND the render via /images/edits (image-condition);
    otherwise (or on any edits failure) fall back to text->image. Returns a status dict whose
    `path` is "edits" (reference-grounded) or "generations" (text->image)."""
    # MANDATED model: default to gpt-image-2 when unset — NEVER auto-pick another (e.g. gpt-image-1).
    model = os.environ.get("TS_FIG_MODEL", "gpt-image-2").strip() or "gpt-image-2"
    key = os.environ.get("TS_FIG_API_KEY", "").strip()
    base = os.environ.get("TS_FIG_BASE_URL", "").strip().rstrip("/")
    style = os.environ.get("TS_FIG_API_STYLE", "images").strip().lower()
    size = os.environ.get("TS_FIG_SIZE", "1536x1024").strip()   # landscape default (diagrams)
    missing = [n for n, v in (("TS_FIG_API_KEY", key), ("TS_FIG_BASE_URL", base)) if not v]
    if missing:
        return {"ok": False, "error": f"unset env: {', '.join(missing)}"}

    refs = [r for r in (references or []) if r and Path(r).is_file()]
    edits_err = None
    # IMAGE-CONDITION (reference-grounded) path: only for images-style gpt-image-* with a reference.
    if refs and style == "images" and model.lower().startswith("gpt-image"):
        try:
            url, body, ctype = _build_edits_request(base, model, prompt, refs, size)
            j = _post_multipart(url, body, ctype, key)
            data = _extract_image_bytes(j)
            if data:
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_bytes(data)
                return {"ok": True, "out": str(out_path), "bytes": len(data),
                        "style": "images", "path": "edits", "references": refs}
            edits_err = f"edits returned no image (keys={list(j)[:6]})"
        except Exception as e:
            edits_err = f"{type(e).__name__}: {e}"   # graceful fallback below

    res = _render_textonly(prompt, out_path, retries, model, key, base, style, size)
    if res.get("ok"):
        res["path"] = "generations"
        if edits_err:
            res["edits_fallback"] = edits_err
    return res


def _render_textonly(prompt, out_path, retries, model, key, base, style, size):
    if style == "chat":
        # chat gateways control resolution; pass the requested size as a SOFT prompt hint
        # only (no unknown payload field that could break a gateway).
        chat_prompt = f"{prompt}\n\n(Render at approximately {size} resolution.)" if size else prompt
        url = f"{base}/chat/completions"
        payload = {"model": model, "modalities": ["image", "text"],
                   "messages": [{"role": "user", "content": chat_prompt}]}
    else:
        url = f"{base}/images/generations"
        payload = {"model": model, "prompt": prompt, "n": 1, "size": size}
        if model.lower().startswith("gpt-image"):
            # quality knob only. Do NOT send background/output_format: some OpenAI-compatible
            # gateways 422 on them (observed on sogenport 2026-06-22), and they are non-essential
            # (gpt-image returns a b64 PNG regardless). Also do NOT send response_format (rejected).
            payload["quality"] = os.environ.get("TS_FIG_QUALITY", "high")
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
    ap.add_argument("--reference", action="append", default=None,
                    help="reference image path for image-conditioning (repeatable; "
                         "grounds the render on an on-topic MAIN figure)")
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
    result = render(prompt, Path(a.out).resolve(), retries=a.retries, references=a.reference)
    print(json.dumps(result, ensure_ascii=False))
    sys.exit(0 if result.get("ok") else 1)


if __name__ == "__main__":
    main()
