#!/usr/bin/env python3
"""Run the real upstream PaperBanana pipeline and preserve stage-level evidence."""
from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import _dotenv  # noqa: E402,F401


REQUIRED_UPSTREAM = (
    "utils/paperviz_processor.py",
    "agents/retriever_agent.py",
    "agents/planner_agent.py",
    "agents/stylist_agent.py",
    "agents/visualizer_agent.py",
    "agents/critic_agent.py",
)
STAGE_KEYS = ("retriever", "planner", "stylist", "visualizer", "critic")
SECRET = re.compile(r"(?i)(api[_-]?key|token|password|secret)(\s*[=:]\s*)(\S+)")


NEUTRAL_RETRIEVER_PROMPT = """
You are the Retriever in an academic-figure pipeline. Select up to ten references that best match
both the scientific domain and communicative purpose of the target. Prefer useful visual structure,
not superficial keyword overlap. Return strict JSON: {"top10_diagrams": ["id", ...]}.
""".strip()

NEUTRAL_STYLIST_PROMPT = """
You are the Stylist in an academic-figure pipeline. Refine the Planner description using the supplied
field- and venue-specific style guide. Preserve every scientific relation and required label. Improve
hierarchy, density, typography, palette, and domain specificity without adding content. Output only
the final detailed description.
""".strip()

NEUTRAL_CRITIC_PROMPT = """
You are the Critic in an academic-figure pipeline. Inspect the actual generated image against the
scientific source and caption. Check semantic fidelity, missing or invented objects and relations,
text correctness, hierarchy, legibility, and generic-box degeneration. Return strict JSON with
critic_suggestions and revised_description. Use 'No changes needed.' only when no material defect is
visible.
""".strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def redact(text: str) -> str:
    return SECRET.sub(lambda match: f"{match.group(1)}{match.group(2)}<redacted>", text)


def locate_upstream(explicit: str | None) -> Path:
    candidates = []
    if explicit:
        candidates.append(Path(explicit).expanduser())
    if os.environ.get("TS_PAPERBANANA_ROOT"):
        candidates.append(Path(os.environ["TS_PAPERBANANA_ROOT"]).expanduser())
    candidates.extend([
        Path.home() / "idea2paper-skills" / "PaperBanana",
        Path.home() / "PaperBanana",
    ])
    for candidate in candidates:
        root = candidate.resolve()
        if all((root / relative).is_file() for relative in REQUIRED_UPSTREAM):
            return root
    raise ValueError("PaperBanana upstream checkout not found; set TS_PAPERBANANA_ROOT or --paperbanana-root")


def git_identity(root: Path, allow_dirty: bool) -> dict[str, Any]:
    try:
        head = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True,
            timeout=30, check=True,
        ).stdout.strip()
        origin = subprocess.run(
            ["git", "-C", str(root), "config", "--get", "remote.origin.url"], capture_output=True,
            text=True, timeout=30, check=False,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain"], capture_output=True, text=True,
            timeout=30, check=True,
        ).stdout
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ValueError(f"cannot establish PaperBanana Git identity: {exc}") from exc
    dirty = bool(status.strip())
    if dirty and not allow_dirty:
        raise ValueError("PaperBanana checkout is dirty; pin a clean checkout or pass --allow-dirty with an audited diff")
    return {"root": str(root), "origin": origin, "commit": head, "dirty": dirty,
            "dirty_status_sha256": hashlib.sha256(status.encode("utf-8")).hexdigest() if dirty else None}


def choose_python(root: Path, explicit: str | None) -> Path:
    candidates = [Path(explicit).expanduser()] if explicit else []
    candidates.extend([root / ".venv/bin/python", root / "venv/bin/python", Path(sys.executable)])
    for candidate in candidates:
        if candidate and candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate.absolute()
    raise ValueError("no executable Python is available for PaperBanana")


def validate_provider_routing(main_model: str, image_model: str, providers: set[str]) -> None:
    def require(provider: str, purpose: str) -> None:
        if provider not in providers:
            raise ValueError(f"PaperBanana {purpose} model requires the {provider} provider")

    if main_model.startswith("openrouter/"):
        require("OpenRouter", "main")
    elif main_model.startswith("claude-"):
        require("Anthropic", "main")
    elif main_model.startswith(("gpt-", "o1-", "o3-", "o4-")):
        require("OpenAI", "main")
    elif not providers:
        raise ValueError("PaperBanana main model requires at least one configured upstream provider")

    if "gpt-image" in image_model:
        require("OpenAI", "image")
    elif "OpenRouter" not in providers:
        require("Gemini", "image")


def resolve(pipeline: Path, value: Any) -> Path:
    path = Path(str(value or ""))
    return path if path.is_absolute() else pipeline / path


def prepare_runtime(pipeline: Path, upstream: Path, run_input: dict[str, Any]) -> tuple[Path, list[dict[str, Any]]]:
    runtime = pipeline / "paperbanana" / "runtime"
    (runtime / "data/PaperBananaBench/diagram/images").mkdir(parents=True, exist_ok=True)
    (runtime / "style_guides").mkdir(parents=True, exist_ok=True)
    (runtime / "configs").mkdir(parents=True, exist_ok=True)

    style_path = resolve(pipeline, run_input.get("style_guide"))
    if not style_path.is_file():
        raise ValueError("paperbanana/input.json style_guide is missing")
    shutil.copy2(style_path, runtime / "style_guides/neurips2025_diagram_style_guide.md")

    retrieval_path = pipeline / "references/retrieval.json"
    retrieval = read_object(retrieval_path)
    attempted = retrieval.get("attempted_sources")
    if not isinstance(attempted, list) or not attempted:
        raise ValueError("PaperBanana requires a real accepted-paper reference search before execution")
    candidates = retrieval.get("candidates", [])
    decision = retrieval.get("decision", {})
    if not isinstance(candidates, list) or not isinstance(decision, dict):
        raise ValueError("references/retrieval.json requires candidates and a decision")
    selected_ids = set(decision.get("selected_reference_ids") or [])
    if decision.get("status") == "SELECTED" and not selected_ids:
        raise ValueError("selected PaperBanana references require selected_reference_ids")
    if decision.get("status") not in {"SELECTED", "NO_SUITABLE_REFERENCE"}:
        raise ValueError("PaperBanana reference decision is invalid")
    selected = [item for item in candidates if isinstance(item, dict) and item.get("reference_id") in selected_ids]
    if selected_ids != {item.get("reference_id") for item in selected}:
        raise ValueError("PaperBanana selected_reference_ids contain unknown candidates")
    reference_records = []
    for index, item in enumerate(selected):
        if not isinstance(item, dict) or any(item.get(key) in (None, "", []) for key in ("source", "image", "reason_selected", "content", "visual_intent")):
            raise ValueError(f"selected PaperBanana reference {index} is incomplete")
        image = resolve(pipeline, item["image"])
        if not image.is_file():
            raise ValueError(f"selected PaperBanana reference image is missing: {item['image']}")
        suffix = image.suffix.lower() or ".png"
        target_name = f"reference-{index:03d}{suffix}"
        target = runtime / "data/PaperBananaBench/diagram/images" / target_name
        shutil.copy2(image, target)
        reference_records.append({
            "id": f"field-ref-{index:03d}",
            "content": item["content"],
            "visual_intent": item["visual_intent"],
            "path_to_gt_image": f"images/{target_name}",
            "source": item["source"],
            "source_image_sha256": sha256(image),
            "reason_selected": item["reason_selected"],
        })
    (runtime / "data/PaperBananaBench/diagram/ref.json").write_text(
        json.dumps(reference_records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return runtime, reference_records


def image_bytes(value: str) -> bytes:
    raw = value.split(",", 1)[1] if "," in value else value
    return base64.b64decode(raw)


def save_stage_images(result: dict[str, Any], output_dir: Path) -> dict[str, dict[str, str]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    images = {}
    for key, value in sorted(result.items()):
        if not key.endswith("_base64_jpg") or not isinstance(value, str) or len(value) < 100:
            continue
        try:
            from PIL import Image
            image = Image.open(BytesIO(image_bytes(value)))
            target = output_dir / f"{key.removesuffix('_base64_jpg')}.png"
            image.save(target, format="PNG")
        except Exception as exc:
            raise ValueError(f"PaperBanana stage image {key} is invalid: {exc}") from exc
        images[key] = {"path": str(target), "sha256": sha256(target)}
    return images


def final_image_key(result: dict[str, Any], images: dict[str, Any]) -> str:
    preferred = result.get("eval_image_field")
    if preferred in images:
        return str(preferred)
    critic = sorted(
        (key for key in images if "_critic_desc" in key),
        key=lambda key: int(re.search(r"critic_desc(\d+)", key).group(1)),
    )
    if critic:
        return critic[-1]
    for key in ("target_diagram_stylist_desc0_base64_jpg", "target_diagram_desc0_base64_jpg"):
        if key in images:
            return key
    raise ValueError("PaperBanana result has no usable visualizer output")


def trace_candidate(result: dict[str, Any], candidate_id: str, output_dir: Path) -> dict[str, Any]:
    images = save_stage_images(result, output_dir)
    selected_key = final_image_key(result, images)
    text_trace = {
        key: value for key, value in sorted(result.items())
        if isinstance(value, (str, int, float, bool, list, dict)) and not key.endswith("_base64_jpg")
    }
    stages = {
        "retriever": {"reference_ids": result.get("top10_references", []), "ran": "top10_references" in result},
        "planner": {"description": result.get("target_diagram_desc0"), "ran": bool(result.get("target_diagram_desc0"))},
        "stylist": {"description": result.get("target_diagram_stylist_desc0"), "ran": bool(result.get("target_diagram_stylist_desc0"))},
        "visualizer": {"images": images, "ran": bool(images)},
        "critic": {
            "suggestions": [value for key, value in sorted(result.items()) if "critic_suggestions" in key],
            "revisions": [value for key, value in sorted(result.items()) if re.search(r"critic_desc\d+$", key)],
            "ran": any("critic_suggestions" in key for key in result),
        },
    }
    missing = [key for key in STAGE_KEYS if not stages[key]["ran"]]
    if missing:
        raise ValueError(f"upstream PaperBanana candidate lacks executed stages: {missing}")
    final = Path(images[selected_key]["path"])
    return {
        "candidate_id": candidate_id,
        "stages": stages,
        "trace": text_trace,
        "final_image": str(final),
        "final_sha256": sha256(final),
        "selected_upstream_key": selected_key,
    }


async def worker(pipeline: Path, upstream: Path, report_path: Path) -> None:
    run_input = read_object(pipeline / "paperbanana/input.json")
    runtime, references = prepare_runtime(pipeline, upstream, run_input)
    sys.path.insert(0, str(upstream))
    from agents.critic_agent import CriticAgent
    from agents.planner_agent import PlannerAgent
    from agents.polish_agent import PolishAgent
    from agents.retriever_agent import RetrieverAgent
    from agents.stylist_agent import StylistAgent
    from agents.vanilla_agent import VanillaAgent
    from agents.visualizer_agent import VisualizerAgent
    from utils import generation_utils
    from utils.config import ExpConfig
    from utils.paperviz_processor import PaperVizProcessor

    providers = set(generation_utils.reinitialize_clients())
    validate_provider_routing(
        str(run_input["main_model_name"]), str(run_input["image_gen_model_name"]), providers
    )

    config = ExpConfig(
        dataset_name="PaperBananaBench",
        task_name="diagram",
        split_name="lifecycle",
        exp_mode="demo_full",
        retrieval_setting="auto" if references else "none",
        planner_metaphor=bool(run_input.get("planner_metaphor", False)),
        max_critic_rounds=int(run_input["max_critic_rounds"]),
        main_model_name=str(run_input["main_model_name"]),
        image_gen_model_name=str(run_input["image_gen_model_name"]),
        work_dir=runtime,
    )
    retriever = RetrieverAgent(exp_config=config); retriever.system_prompt = NEUTRAL_RETRIEVER_PROMPT
    stylist = StylistAgent(exp_config=config); stylist.system_prompt = NEUTRAL_STYLIST_PROMPT
    critic = CriticAgent(exp_config=config); critic.system_prompt = NEUTRAL_CRITIC_PROMPT
    processor = PaperVizProcessor(
        exp_config=config,
        vanilla_agent=VanillaAgent(exp_config=config),
        planner_agent=PlannerAgent(exp_config=config),
        visualizer_agent=VisualizerAgent(exp_config=config),
        stylist_agent=stylist,
        critic_agent=critic,
        retriever_agent=retriever,
        polish_agent=PolishAgent(exp_config=config),
    )
    candidate_count = int(run_input["candidate_count"])
    data_list = [{
        "filename": f"lifecycle_candidate_{index}",
        "candidate_id": f"pb-{index + 1:03d}",
        "caption": run_input["caption"],
        "content": run_input["content"],
        "visual_intent": run_input["caption"],
        "additional_info": {"rounded_ratio": run_input.get("aspect_ratio", "16:9")},
        "max_critic_rounds": int(run_input["max_critic_rounds"]),
    } for index in range(candidate_count)]

    candidates = []
    async for result in processor.process_queries_batch(data_list, max_concurrent=min(candidate_count, 8), do_eval=False):
        candidate_id = str(result.get("candidate_id") or result.get("filename") or f"pb-{len(candidates) + 1:03d}")
        candidates.append(trace_candidate(result, candidate_id, pipeline / "renders" / candidate_id))
    report_path.write_text(json.dumps({
        "workflow": "PaperBanana",
        "mode": "demo_full",
        "retrieval_setting": config.retrieval_setting,
        "candidate_count": candidate_count,
        "max_critic_rounds": config.max_critic_rounds,
        "models": {"main": config.main_model_name, "image": config.image_gen_model_name},
        "providers": sorted(providers),
        "reference_count": len(references),
        "candidates": candidates,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def validate_input(pipeline: Path, run_input: dict[str, Any]) -> None:
    required = (
        "content", "content_derivation", "caption", "candidate_count", "max_critic_rounds",
        "main_model_name", "image_gen_model_name", "style_guide", "semantic_plan_sha256",
        "retrieval_sha256",
    )
    missing = [key for key in required if run_input.get(key) in (None, "", [])]
    if missing:
        raise ValueError(f"paperbanana/input.json missing fields: {missing}")
    plan = read_object(pipeline / "search_plan.json")
    if run_input["candidate_count"] != plan.get("planned_candidates"):
        raise ValueError("PaperBanana candidate_count must equal the frozen search plan")
    if not isinstance(run_input["candidate_count"], int) or not 1 <= run_input["candidate_count"] <= min(int(plan["safety_cap"]), 32):
        raise ValueError("PaperBanana candidate_count is outside its bounded plan")
    if not isinstance(run_input["max_critic_rounds"], int) or not 1 <= run_input["max_critic_rounds"] <= 5:
        raise ValueError("PaperBanana max_critic_rounds must be between 1 and 5")
    semantic = pipeline / "paperbanana/semantic_plan.json"
    retrieval = pipeline / "references/retrieval.json"
    if not semantic.is_file() or run_input["semantic_plan_sha256"] != sha256(semantic):
        raise ValueError("paperbanana/input.json is not bound to the reviewed semantic plan")
    if not retrieval.is_file() or run_input["retrieval_sha256"] != sha256(retrieval):
        raise ValueError("paperbanana/input.json is not bound to the reviewed reference search")
    contract = read_object(pipeline / "figure_contract.json")
    if run_input["caption"] != contract.get("caption"):
        raise ValueError("paperbanana/input.json caption differs from the frozen figure contract")


def execute(args: argparse.Namespace) -> dict[str, Any]:
    pipeline = Path(args.pipeline).resolve()
    run_input_path = pipeline / "paperbanana/input.json"
    run_input = read_object(run_input_path)
    validate_input(pipeline, run_input)
    upstream = locate_upstream(args.paperbanana_root)
    identity = git_identity(upstream, args.allow_dirty)
    python = choose_python(upstream, args.python)
    worker_report = pipeline / "paperbanana/worker-report.json"
    command = [str(python), str(Path(__file__).resolve()), "_worker", str(pipeline), str(upstream), str(worker_report)]
    started = datetime.now(timezone.utc).isoformat()
    result = subprocess.run(command, capture_output=True, text=True, timeout=args.timeout_seconds, check=False)
    (pipeline / "paperbanana/stdout.log").write_text(redact(result.stdout), encoding="utf-8")
    (pipeline / "paperbanana/stderr.log").write_text(redact(result.stderr), encoding="utf-8")
    if result.returncode != 0 or not worker_report.is_file():
        raise ValueError(f"upstream PaperBanana execution failed with return code {result.returncode}")
    report = read_object(worker_report)
    candidates = report.get("candidates", [])
    if len(candidates) != run_input["candidate_count"]:
        raise ValueError("upstream PaperBanana did not produce the frozen candidate count")
    for candidate in candidates:
        if any(not (candidate.get("stages", {}).get(stage) or {}).get("ran") for stage in STAGE_KEYS):
            raise ValueError("worker report does not prove all PaperBanana stages executed")

    run_record = {
        "workflow": "PaperBanana",
        "executor": "upstream_papervizprocessor_adapter",
        "upstream": identity,
        "python": str(python),
        "started_at": started,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "returncode": result.returncode,
        "input": {"path": str(run_input_path), "sha256": sha256(run_input_path)},
        "semantic_plan": {"path": str(pipeline / "paperbanana/semantic_plan.json"), "sha256": sha256(pipeline / "paperbanana/semantic_plan.json")},
        "reference_search": {"path": str(pipeline / "references/retrieval.json"), "sha256": sha256(pipeline / "references/retrieval.json")},
        "style_guide": {"path": str(resolve(pipeline, run_input["style_guide"])), "sha256": sha256(resolve(pipeline, run_input["style_guide"]))},
        "mode": report["mode"],
        "retrieval_setting": report["retrieval_setting"],
        "models": report["models"],
        "candidate_count": report["candidate_count"],
        "max_critic_rounds": report["max_critic_rounds"],
        "stages": list(STAGE_KEYS),
        "candidates": candidates,
        "worker_report": {"path": str(worker_report), "sha256": sha256(worker_report)},
    }
    run_path = pipeline / "paperbanana/run.json"
    run_path.write_text(json.dumps(run_record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {"results": [
        {"id": item["candidate_id"], "ok": True, "output": item["final_image"], "sha256": item["final_sha256"], "producer": "PaperBanana"}
        for item in candidates
    ]}
    (pipeline / "renders/render_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"run": str(run_path), "candidates": len(candidates), "upstream_commit": identity["commit"]}


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("pipeline")
    run.add_argument("--paperbanana-root")
    run.add_argument("--python")
    run.add_argument("--timeout-seconds", type=int, default=7200)
    run.add_argument("--allow-dirty", action="store_true")
    worker_parser = sub.add_parser("_worker")
    worker_parser.add_argument("pipeline")
    worker_parser.add_argument("upstream")
    worker_parser.add_argument("report")
    args = parser.parse_args()
    try:
        if args.command == "_worker":
            asyncio.run(worker(Path(args.pipeline).resolve(), Path(args.upstream).resolve(), Path(args.report).resolve()))
            return 0
        if not 60 <= args.timeout_seconds <= 21_600:
            raise ValueError("timeout-seconds must be between 60 and 21600")
        output = execute(args)
    except (OSError, ValueError, KeyError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, **output}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
