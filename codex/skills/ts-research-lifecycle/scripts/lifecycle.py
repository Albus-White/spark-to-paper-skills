#!/usr/bin/env python3
"""Research Lifecycle Core for spark-to-paper.

Stdlib-only, deterministic lifecycle/state/provenance manager. Scientific judgment remains in
Codex skills and reviewers; this module validates contracts, state transitions, evidence links,
and invalidation rules.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from publication_contracts import (
    compute_venue_aggregates,
    derive_publication_envelope,
    validate_publication_contract,
    validate_user_policy,
    validate_venue_profile,
)

SCHEMA_VERSION = "5.0.0"
PHASES = [
    "INTAKE", "USER_POLICY_LOCKED", "SCIENCE_PROFILED", "VENUE_PROFILED",
    "IDEA_DRAFTED", "IDEA_GROUNDED", "RESEARCH_CONTRACT_FROZEN",
    "CODEBASE_LOCKED", "BASELINE_VERIFIED", "IMPLEMENTATION_VERIFIED",
    "PILOT_VERIFIED", "FULL_EXPERIMENT_COMPLETED", "MECHANISM_DIAGNOSED",
    "IDEA_DECIDED", "REVALIDATION_COMPLETED", "CLAIMS_RECONCILED",
    "PUBLICATION_CONTRACT_FROZEN", "CITATIONS_COMPLETE", "MANUSCRIPT_DRAFTED",
    "MANUSCRIPT_REFINED", "MANUSCRIPT_HARDENED", "FIGURES_COMPLETE",
    "LATEX_COMPILED", "RELEASE_AUDITED", "RELEASED",
]
TERMINAL_PHASES = {
    "STOPPED_HYPOTHESIS_REJECTED", "STOPPED_NO_VALID_PROTOCOL",
    "STOPPED_BASELINE_UNRESOLVED", "STOPPED_RESOURCE_LIMIT",
    "STOPPED_DATA_UNAVAILABLE", "STOPPED_LICENSE_BLOCKED",
    "STOPPED_AUTHOR_DECISION_REQUIRED",
}
GATES = {
    "G0": "Intake Integrity", "G1": "Idea Falsifiability", "G2": "Evidence Grounding",
    "G3": "Research Contract Approval", "G4": "Repository & License",
    "G5": "Environment Reproducibility", "G6": "Baseline Reproduction",
    "G7": "Implementation Review", "G8": "Scientific Sanity", "G9": "Pilot",
    "G10": "Full Run Integrity", "G11": "Result Provenance", "G12": "Mechanism Diagnosis",
    "G13": "Idea Decision", "G14": "Independent Revalidation",
    "G15": "Claim Reconciliation", "G16": "Manuscript Adversarial Review",
    "V1": "Venue Calibration", "M1": "Publication Contract",
    "M2": "Citation Completion", "M3": "Complete Draft",
    "M4": "Holistic Refinement", "M5": "Figure Program Completion",
    "M6": "Release Audit",
}
STANDARD_REQUIRED_GATES = {
    "USER_POLICY_LOCKED": ["G0"],
    "SCIENCE_PROFILED": ["G0"],
    "VENUE_PROFILED": ["G0", "V1"],
    "IDEA_DRAFTED": ["G0", "V1"],
    "IDEA_GROUNDED": ["G0", "G1", "G2"],
    "RESEARCH_CONTRACT_FROZEN": ["G0", "G1", "G2", "G3"],
    "CODEBASE_LOCKED": ["G0", "G1", "G2", "G3", "G4", "G5"],
    "BASELINE_VERIFIED": ["G0", "G1", "G2", "G3", "G4", "G5", "G6"],
    "IMPLEMENTATION_VERIFIED": ["G0", "G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8"],
    "PILOT_VERIFIED": ["G0", "G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "G9"],
    "FULL_EXPERIMENT_COMPLETED": ["G0", "G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "G9", "G10", "G11"],
    "MECHANISM_DIAGNOSED": ["G0", "G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "G9", "G10", "G11", "G12"],
    "IDEA_DECIDED": ["G0", "G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "G9", "G10", "G11", "G12", "G13"],
    "REVALIDATION_COMPLETED": list(GATES)[:15],
    "CLAIMS_RECONCILED": list(GATES)[:16],
    "PUBLICATION_CONTRACT_FROZEN": list(GATES)[:16] + ["V1", "M1"],
    "CITATIONS_COMPLETE": list(GATES)[:16] + ["V1", "M1", "M2"],
    "MANUSCRIPT_DRAFTED": list(GATES)[:16] + ["V1", "M1", "M2", "M3"],
    "MANUSCRIPT_REFINED": list(GATES)[:16] + ["V1", "M1", "M2", "M3", "M4"],
    "MANUSCRIPT_HARDENED": list(GATES)[:16] + ["V1", "M1", "M2", "M3", "M4", "G16"],
    "FIGURES_COMPLETE": list(GATES)[:16] + ["V1", "M1", "M2", "M3", "M4", "G16", "M5"],
    "LATEX_COMPILED": list(GATES)[:16] + ["V1", "M1", "M2", "M3", "M4", "G16", "M5"],
    "RELEASE_AUDITED": list(GATES),
    "RELEASED": list(GATES),
}
PROFILE_PHASES = {
    "proposal": [
        "INTAKE", "USER_POLICY_LOCKED", "SCIENCE_PROFILED", "VENUE_PROFILED",
        "IDEA_DRAFTED", "IDEA_GROUNDED", "RESEARCH_CONTRACT_FROZEN",
        "CLAIMS_RECONCILED", "PUBLICATION_CONTRACT_FROZEN", "CITATIONS_COMPLETE",
        "MANUSCRIPT_DRAFTED", "MANUSCRIPT_REFINED", "MANUSCRIPT_HARDENED",
        "FIGURES_COMPLETE", "LATEX_COMPILED", "RELEASE_AUDITED", "RELEASED",
    ],
    "exploratory": [
        "INTAKE", "USER_POLICY_LOCKED", "SCIENCE_PROFILED", "VENUE_PROFILED",
        "IDEA_DRAFTED", "IDEA_GROUNDED", "RESEARCH_CONTRACT_FROZEN",
        "CODEBASE_LOCKED", "BASELINE_VERIFIED", "IMPLEMENTATION_VERIFIED",
        "PILOT_VERIFIED", "MECHANISM_DIAGNOSED", "IDEA_DECIDED",
        "CLAIMS_RECONCILED", "PUBLICATION_CONTRACT_FROZEN", "CITATIONS_COMPLETE",
        "MANUSCRIPT_DRAFTED", "MANUSCRIPT_REFINED", "MANUSCRIPT_HARDENED",
        "FIGURES_COMPLETE", "LATEX_COMPILED", "RELEASE_AUDITED", "RELEASED",
    ],
    "standard_empirical": PHASES,
    "high_risk": PHASES,
}
PROFILE_GATE_MILESTONES = {
    "proposal": {
        "USER_POLICY_LOCKED": ["G0"],
        "VENUE_PROFILED": ["V1"],
        "IDEA_GROUNDED": ["G1", "G2"],
        "RESEARCH_CONTRACT_FROZEN": ["G3"],
        "CLAIMS_RECONCILED": ["G15"],
        "PUBLICATION_CONTRACT_FROZEN": ["M1"],
        "CITATIONS_COMPLETE": ["M2"],
        "MANUSCRIPT_DRAFTED": ["M3"],
        "MANUSCRIPT_REFINED": ["M4"],
        "MANUSCRIPT_HARDENED": ["G16"],
        "FIGURES_COMPLETE": ["M5"],
        "RELEASE_AUDITED": ["M6"],
    },
    "exploratory": {
        "USER_POLICY_LOCKED": ["G0"],
        "VENUE_PROFILED": ["V1"],
        "IDEA_GROUNDED": ["G1", "G2"],
        "RESEARCH_CONTRACT_FROZEN": ["G3"],
        "CODEBASE_LOCKED": ["G4", "G5"],
        "BASELINE_VERIFIED": ["G6"],
        "IMPLEMENTATION_VERIFIED": ["G7", "G8"],
        "PILOT_VERIFIED": ["G9"],
        "MECHANISM_DIAGNOSED": ["G12"],
        "IDEA_DECIDED": ["G13"],
        "CLAIMS_RECONCILED": ["G15"],
        "PUBLICATION_CONTRACT_FROZEN": ["M1"],
        "CITATIONS_COMPLETE": ["M2"],
        "MANUSCRIPT_DRAFTED": ["M3"],
        "MANUSCRIPT_REFINED": ["M4"],
        "MANUSCRIPT_HARDENED": ["G16"],
        "FIGURES_COMPLETE": ["M5"],
        "RELEASE_AUDITED": ["M6"],
    },
}
# Compatibility for callers that inspect the standard empirical path.
REQUIRED_GATES = STANDARD_REQUIRED_GATES
PASSING = {"PASS", "PASS_WITH_EXPLAINED_DEVIATION", "NOT_APPLICABLE"}
IDEA_DECISIONS = {"KEEP", "NARROW_SCOPE", "REVISE_MECHANISM", "REFRAME_PROBLEM", "BRANCH_NEW_IDEA", "REJECT_AND_STOP", "INSUFFICIENT_EVIDENCE"}
FAILURES = {"INFRASTRUCTURE_FAILURE", "DEPENDENCY_FAILURE", "IMPLEMENTATION_FAILURE", "PROTOCOL_FAILURE", "DATA_FAILURE", "BASELINE_REPRODUCTION_FAILURE", "RESOURCE_EXHAUSTED", "HYPOTHESIS_NOT_SUPPORTED", "INCONCLUSIVE", "NONE"}
PROFILES = {"proposal", "exploratory", "standard_empirical", "high_risk"}
RUN_TYPES = {"baseline", "pilot", "full", "revalidation", "diagnostic", "analysis", "user_supplied_import"}
MODEL_JUDGMENT_GATES = {"G1", "G2", "G3", "G6", "G7", "G8", "G9", "G12", "G13", "G14", "G15", "G16"}
HIGH_RISK_INDEPENDENT_GATES = {"G3", "G7", "G12", "G14", "G16"}
MANUSCRIPT_ROOT_FILES = {"main.tex", "refs.bib", "template.json", "latexmkrc"}
MANUSCRIPT_ROOT_SUFFIXES = {".sty", ".cls", ".bst"}
MANUSCRIPT_DIRECTORIES = {"sections", "figures", "assets"}
SCHEDULE_CHECKPOINT_PHASES = {
    "CODEBASE_LOCKED", "FULL_EXPERIMENT_COMPLETED", "PUBLICATION_CONTRACT_FROZEN",
    "FIGURES_COMPLETE", "RELEASE_AUDITED",
}
SECRET_PATTERNS = (
    re.compile(r"(?i)\b([A-Z0-9_]*(?:API_KEY|TOKEN|PASSWORD|SECRET))=([^\s]+)"),
    re.compile(r"\b(?:sk|ghp|github_pat)-?[A-Za-z0-9_\-]{20,}\b"),
    re.compile(r"https?://[^:/\s]+:[^@\s]+@"),
)


def phase_sequence(profile: str) -> list[str]:
    return PROFILE_PHASES[profile]


def required_gates_for(profile: str, phase: str) -> list[str]:
    if profile in {"standard_empirical", "high_risk"}:
        return list(STANDARD_REQUIRED_GATES.get(phase, []))
    required: list[str] = []
    milestones = PROFILE_GATE_MILESTONES[profile]
    for item in phase_sequence(profile):
        required.extend(milestones.get(item, []))
        if item == phase:
            break
    return required


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"missing JSON file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_jsonl(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False) + "\n")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_json(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def redact_secrets(text: str) -> str:
    value = SECRET_PATTERNS[0].sub(lambda match: f"{match.group(1)}=[REDACTED]", str(text))
    value = SECRET_PATTERNS[1].sub("[REDACTED_TOKEN]", value)
    value = SECRET_PATTERNS[2].sub(lambda match: match.group(0).split("://", 1)[0] + "://[REDACTED]@", value)
    return value


def contains_secret(text: str) -> bool:
    assignments = SECRET_PATTERNS[0].finditer(text)
    if any(match.group(2) not in {"[REDACTED]", "REDACTED", "***"} for match in assignments):
        return True
    return any(pattern.search(text) for pattern in SECRET_PATTERNS[1:])


def state_path(root: Path) -> Path:
    return root / "research_state.json"


def load_state(root: Path) -> dict[str, Any]:
    state = read_json(state_path(root))
    validate_state(state)
    return state


def save_state(root: Path, state: dict[str, Any], event: str, details: dict[str, Any] | None = None) -> None:
    state["updated_at"] = now()
    state.setdefault("history", []).append({"at": state["updated_at"], "event": event, "details": details or {}})
    write_json(state_path(root), state)


def validate_state(state: dict[str, Any]) -> None:
    required = {"schema_version", "run_id", "profile", "phase", "active", "gates", "invalidations", "approvals", "blockers", "history"}
    missing = sorted(required - set(state))
    if missing:
        raise ValueError(f"research_state missing fields: {missing}")
    if state["profile"] not in PROFILES:
        raise ValueError(f"invalid profile: {state['profile']}")
    if state["phase"] not in set(PHASES) | TERMINAL_PHASES:
        raise ValueError(f"invalid phase: {state['phase']}")
    if state["phase"] not in TERMINAL_PHASES and state["phase"] not in phase_sequence(state["profile"]):
        raise ValueError(f"phase {state['phase']} is not part of profile {state['profile']}")
    if not isinstance(state["gates"], dict):
        raise ValueError("gates must be an object")


def init_layout(root: Path, profile: str, run_id: str) -> None:
    if profile not in PROFILES:
        raise ValueError(f"profile must be one of {sorted(PROFILES)}")
    dirs = [
        "intake", "memory", "calibration/papers", "discovery", "ideas", "claims", "grounding/reports", "contracts", "code/upstream",
        "code/integration", "code/adapters", "code/patches", "environment/snapshots",
        "experiments/baseline", "experiments/pilots", "experiments/runs", "experiments/iterations",
        "experiments/branches",
        "evidence", "evidence/results", "decisions", "reports/gates", "reports/design", "reports/code",
        "reports/experiments", "reports/mechanism", "reports/manuscript", "reports/release", "reports/schedule", "manuscript/sections",
        "manuscript/figures", "logs",
    ]
    root.mkdir(parents=True, exist_ok=True)
    for name in dirs:
        (root / name).mkdir(parents=True, exist_ok=True)
    if state_path(root).exists():
        raise ValueError(f"research lifecycle already initialized: {root}")
    state = {
        "schema_version": SCHEMA_VERSION, "run_id": run_id, "profile": profile,
        "phase": "INTAKE", "created_at": now(), "updated_at": now(),
        "active": {
            "user_policy_id": None,
            "idea_seed_id": None,
            "memory_snapshot_id": None,
            "science_profile_id": None,
            "venue_corpus_id": None,
            "venue_profile_id": None,
            "venue_profile_judgment_id": None,
            "idea_candidates_id": None,
            "idea_selection_id": None,
            "idea_id": None,
            "research_program_id": None,
            "publication_contract_id": None,
            "bibliography_coverage": None,
            "figure_routing": None,
            "manuscript_id": None,
            "publication_judgment_id": None,
            "schedule_checkpoint": None,
            "release_audit_id": None,
        },
        "gates": {}, "invalidations": [], "approvals": [], "blockers": [], "history": [],
        "policy": {"phase_sequence": phase_sequence(profile), "required_gates": {
            phase: required_gates_for(profile, phase) for phase in phase_sequence(profile)
        }},
    }
    save_state(root, state, "lifecycle_initialized", {"profile": profile})
    write_json(root / "claims/claim-registry.json", {"schema_version": SCHEMA_VERSION, "claims": []})
    write_json(root / "code/repos.lock.json", {"schema_version": SCHEMA_VERSION, "repositories": [], "lock_hash": None})
    write_json(root / "environment/environment.lock.json", {"schema_version": SCHEMA_VERSION, "status": "UNLOCKED", "environment": {}, "lock_hash": None})
    write_json(root / "experiments/state.json", {"schema_version": SCHEMA_VERSION, "runs_registered": 0, "test_accesses": 0, "failures": {}, "stop_reason": None})
    write_json(root / "experiments/branch-registry.json", {"schema_version": SCHEMA_VERSION, "branches": []})
    (root / "evidence/evidence-index.jsonl").touch()
    (root / "experiments/test_access_log.jsonl").touch()


def next_id(directory: Path, prefix: str) -> str:
    numbers = []
    for path in directory.glob(f"{prefix}-*.json"):
        try:
            numbers.append(int(path.stem.rsplit("-", 1)[1]))
        except ValueError:
            pass
    return f"{prefix}-{max(numbers, default=0) + 1:03d}"


def register_idea_seed(root: Path, payload: dict[str, Any]) -> str:
    state = load_state(root)
    policy_id = state["active"].get("user_policy_id")
    if not policy_id:
        raise ValueError("register user policy before the Idea seed")
    required = ["seed_text", "source", "constraints", "open_questions"]
    missing = [key for key in required if key not in payload or payload[key] in (None, "")]
    if missing:
        raise ValueError(f"Idea seed missing fields: {missing}")
    if payload["source"] not in {"USER_PROVIDED", "SUPPLIED_PROPOSAL", "IMPORTED_UNVERIFIED"}:
        raise ValueError("Idea seed source is invalid")
    if not isinstance(payload["constraints"], list) or not isinstance(payload["open_questions"], list):
        raise ValueError("Idea seed constraints and open_questions must be lists")
    policy_path = root / f"intake/{policy_id}.json"
    record = {
        **payload,
        "user_policy_id": policy_id,
        "user_policy_hash": sha256_file(policy_path),
    }
    previous = state["active"].get("idea_seed_id")
    if previous and _same_registered_payload(root / f"intake/{previous}.json", record):
        save_state(root, state, "idea_seed_reconfirmed", {"idea_seed_id": previous})
        return previous
    seed_id, path = _write_versioned_artifact(root, "intake", "idea-seed-v", record)
    state["active"]["idea_seed_id"] = seed_id
    if previous and previous != seed_id:
        invalidate(state, "IDEA_SEED_CHANGED", f"registered {seed_id}")
        for key in ("idea_candidates_id", "idea_selection_id", "idea_id", "research_program_id", "publication_contract_id"):
            state["active"][key] = None
    save_state(root, state, "idea_seed_registered", {"idea_seed_id": seed_id, "path": path})
    return seed_id


def register_memory_snapshot(root: Path, payload: dict[str, Any]) -> str:
    state = load_state(root)
    if state["active"].get("idea_id"):
        raise ValueError("a new memory snapshot cannot silently alter an active Idea; reopen discovery or create an Idea branch")
    if payload.get("artifact_type") != "paper_wiki_snapshot" or not payload.get("snapshot_sha256"):
        raise ValueError("memory snapshot must be a Paper Wiki snapshot with snapshot_sha256")
    files = payload.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError("memory snapshot requires a non-empty files list")
    identities = []
    for index, item in enumerate(files):
        if not isinstance(item, dict) or not item.get("path") or not item.get("sha256"):
            raise ValueError(f"memory snapshot file {index} requires path and sha256")
        identities.append({"path": item["path"], "sha256": item["sha256"]})
    observed = hashlib.sha256(
        json.dumps(identities, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if observed != payload["snapshot_sha256"]:
        raise ValueError("memory snapshot_sha256 is not reproducible from its file identities")
    previous = state["active"].get("memory_snapshot_id")
    if previous and _same_registered_payload(root / f"memory/{previous}.json", payload):
        save_state(root, state, "memory_snapshot_reconfirmed", {"memory_snapshot_id": previous})
        return previous
    snapshot_id, path = _write_versioned_artifact(root, "memory", "paper-wiki-snapshot-v", payload)
    state["active"]["memory_snapshot_id"] = snapshot_id
    if previous and previous != snapshot_id:
        state["active"]["idea_candidates_id"] = None
        state["active"]["idea_selection_id"] = None
    save_state(root, state, "memory_snapshot_registered", {"memory_snapshot_id": snapshot_id, "path": path})
    return snapshot_id


def register_idea_candidates(root: Path, payload: dict[str, Any]) -> str:
    state = load_state(root)
    active = state["active"]
    seed_id = active.get("idea_seed_id")
    frontier_id = active.get("science_profile_id")
    venue_id = active.get("venue_profile_id")
    if not all((seed_id, frontier_id, venue_id)):
        raise ValueError("Idea candidates require an Idea seed, science profile, and venue profile")
    bindings = {
        "idea_seed_id": seed_id,
        "idea_seed_hash": sha256_file(root / f"intake/{seed_id}.json"),
        "science_profile_id": frontier_id,
        "science_profile_hash": sha256_file(root / f"calibration/{frontier_id}.json"),
        "venue_profile_id": venue_id,
        "venue_profile_hash": sha256_file(root / f"calibration/{venue_id}.json"),
    }
    memory_id = active.get("memory_snapshot_id")
    if memory_id:
        bindings.update({
            "memory_snapshot_id": memory_id,
            "memory_snapshot_hash": sha256_file(root / f"memory/{memory_id}.json"),
        })
    if any(payload.get(key) != value for key, value in bindings.items()):
        raise ValueError("Idea candidates have missing or stale lifecycle bindings")
    required = ["generation_basis", "fresh_search", "candidates", "limitations", "reviewer"]
    missing = [key for key in required if payload.get(key) in (None, "", [])]
    if missing:
        raise ValueError(f"Idea candidate artifact missing fields: {missing}")
    candidates = payload["candidates"]
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("Idea candidates must be a non-empty list")
    candidate_required = [
        "candidate_id", "problem", "hypothesis", "proposed_mechanism", "scope", "assumptions",
        "falsifiers", "claims", "alternative_explanations", "minimum_validation_path",
        "closest_work", "evidence", "why_might_fail",
    ]
    seen: set[str] = set()
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            raise ValueError(f"Idea candidate {index} must be an object")
        absent = [key for key in candidate_required if candidate.get(key) in (None, "", [])]
        if absent:
            raise ValueError(f"Idea candidate {index} missing fields: {absent}")
        if candidate["candidate_id"] in seen:
            raise ValueError(f"duplicate Idea candidate ID: {candidate['candidate_id']}")
        seen.add(candidate["candidate_id"])
    record_id, path = _write_versioned_artifact(root, "discovery", "idea-candidates-v", payload)
    active["idea_candidates_id"] = record_id
    active["idea_selection_id"] = None
    save_state(root, state, "idea_candidates_registered", {"idea_candidates_id": record_id, "path": path})
    return record_id


def register_idea_selection(root: Path, payload: dict[str, Any]) -> str:
    state = load_state(root)
    candidates_id = state["active"].get("idea_candidates_id")
    if not candidates_id:
        raise ValueError("register Idea candidates before selection")
    candidates_path = root / f"discovery/{candidates_id}.json"
    if payload.get("idea_candidates_id") != candidates_id or payload.get("idea_candidates_hash") != sha256_file(candidates_path):
        raise ValueError("Idea selection is not bound to the active candidate set")
    required = [
        "selected_candidate_id", "decision", "comparison", "rationale", "evidence", "uncertainty",
        "rejected_candidates", "reviewer",
    ]
    missing = [key for key in required if key not in payload or payload[key] in (None, "")]
    if missing:
        raise ValueError(f"Idea selection missing fields: {missing}")
    candidates = read_json(candidates_path).get("candidates", [])
    ids = {item.get("candidate_id") for item in candidates}
    selected = payload["selected_candidate_id"]
    if selected not in ids:
        raise ValueError("selected_candidate_id is not present in the active candidate set")
    rejected = set(payload["rejected_candidates"])
    if rejected != ids - {selected}:
        raise ValueError("rejected_candidates must exactly list the non-selected candidates")
    selection_id, path = _write_versioned_artifact(root, "discovery", "idea-selection-v", payload)
    state["active"]["idea_selection_id"] = selection_id
    save_state(root, state, "idea_selection_registered", {"idea_selection_id": selection_id, "path": path})
    return selection_id


def register_idea(root: Path, payload: dict[str, Any], parent: str | None, level: str, approval: str | None) -> str:
    state = load_state(root)
    required = [
        "problem", "hypothesis", "proposed_mechanism", "scope", "assumptions", "falsifiers",
        "claims", "alternative_explanations", "minimum_validation_path",
    ]
    missing = [key for key in required if not payload.get(key)]
    if missing:
        raise ValueError(f"idea missing non-empty fields: {missing}")
    if level not in {"L0", "L1", "L2", "L3", "L4"}:
        raise ValueError("idea revision level must be L0..L4")
    if level in {"L2", "L3", "L4"} and not approval_valid(state, approval):
        raise ValueError(f"{level} idea changes require a recorded approved user decision")
    previous = state["active"].get("idea_id")
    if previous is None:
        selection_id = state["active"].get("idea_selection_id")
        candidates_id = state["active"].get("idea_candidates_id")
        if not selection_id or not candidates_id:
            raise ValueError("the first active Idea requires a registered candidate set and selection judgment")
        selection = read_json(root / f"discovery/{selection_id}.json")
        candidates_record = read_json(root / f"discovery/{candidates_id}.json")
        selected_id = selection.get("selected_candidate_id")
        selected = next(
            (item for item in candidates_record.get("candidates", []) if item.get("candidate_id") == selected_id),
            None,
        )
        if selected is None:
            raise ValueError("active Idea selection no longer resolves to a candidate")
        drift = [key for key in required if payload.get(key) != selected.get(key)]
        if drift:
            raise ValueError(f"first active Idea differs from the selected candidate: {drift}")
        payload = {**payload, "candidate_id": selected_id, "selection_id": selection_id}
    idea_id = next_id(root / "ideas", "idea-v")
    idea = dict(payload)
    idea.update({
        "schema_version": SCHEMA_VERSION, "idea_id": idea_id, "parent_idea_id": parent,
        "status": "ACTIVE", "revision_level": level, "approval": approval,
        "created_at": now(), "content_hash": None,
    })
    idea["content_hash"] = sha256_json({k: v for k, v in idea.items() if k != "content_hash"})
    write_json(root / f"ideas/{idea_id}.json", idea)
    state["active"]["idea_id"] = idea_id
    if previous and previous != idea_id:
        change = {
            "L0": "IDEA_EDITORIAL_CHANGED",
            "L1": "IDEA_SCOPE_CHANGED",
            "L2": "IDEA_ESTIMAND_CHANGED",
            "L3": "IDEA_CORE_CHANGED",
            "L4": "IDEA_CORE_CHANGED",
        }[level]
        invalidate(state, change, f"registered {idea_id}")
        if level != "L0":
            state["active"]["research_program_id"] = None
            state["active"]["publication_contract_id"] = None
        experiment_state = read_json(root / "experiments/state.json")
        if level in {"L2", "L3", "L4"} and experiment_state.get("test_accesses", 0) > 0:
            invalidate(state, "TEST_CONTAMINATED", f"{idea_id} was generated after test evidence was accessed")
    save_state(root, state, "idea_registered", {"idea_id": idea_id, "parent": parent, "level": level})
    return idea_id


def register_claim(root: Path, claim: dict[str, Any]) -> str:
    required = ["claim_text", "claim_type", "essential", "strength", "scope", "required_evidence"]
    missing = [key for key in required if key not in claim or claim[key] in (None, "", [])]
    if missing:
        raise ValueError(f"claim missing fields: {missing}")
    state = load_state(root)
    if not state["active"].get("idea_id"):
        raise ValueError("register an idea before claims")
    registry_path = root / "claims/claim-registry.json"
    registry = read_json(registry_path)
    claim_id = f"C-{len(registry.get('claims', [])) + 1:03d}"
    record = dict(claim)
    record.update({"claim_id": claim_id, "idea_id": state["active"]["idea_id"], "support_status": "UNVERIFIED", "active": True, "created_at": now()})
    registry.setdefault("claims", []).append(record)
    write_json(registry_path, registry)
    save_state(root, state, "claim_registered", {"claim_id": claim_id})
    return claim_id


def update_claim(root: Path, claim_id: str, support_status: str, action: str, evidence: list[str], allowed_wording: str) -> None:
    valid = {"SUPPORTED", "PARTIALLY_SUPPORTED", "UNSUPPORTED", "CONTRADICTED", "INCONCLUSIVE", "NEEDS_AUTHOR_CONFIRMATION", "UNVERIFIED"}
    if support_status not in valid:
        raise ValueError(f"invalid support status: {support_status}")
    if not evidence:
        raise ValueError("claim update requires evidence")
    missing = [item for item in evidence if not (root / item).exists()]
    if missing:
        raise ValueError(f"claim evidence missing: {missing}")
    path = root / "claims/claim-registry.json"
    registry = read_json(path)
    matches = [item for item in registry.get("claims", []) if item.get("claim_id") == claim_id]
    if not matches:
        raise ValueError(f"unknown claim: {claim_id}")
    claim = matches[0]
    claim.update({
        "support_status": support_status,
        "action": action,
        "evidence": evidence,
        "evidence_hashes": {item: sha256_file(root / item) for item in evidence},
        "allowed_wording": allowed_wording,
        "updated_at": now(),
    })
    write_json(path, registry)
    state = load_state(root)
    save_state(root, state, "claim_updated", {"claim_id": claim_id, "support_status": support_status, "action": action})


def approval_valid(state: dict[str, Any], approval: str | None) -> bool:
    if not approval:
        return False
    return any(item.get("approval_id") == approval and item.get("decision") == "APPROVED" for item in state.get("approvals", []))


def approval_record(state: dict[str, Any], approval: str | None) -> dict[str, Any] | None:
    return next((item for item in state.get("approvals", []) if item.get("approval_id") == approval), None)


def idea_evidence_compatible(root: Path, source_idea_id: str | None, active_idea_id: str | None) -> bool:
    """Return true when evidence differs from the active Idea only by L0 editorial revisions."""
    if not source_idea_id or not active_idea_id:
        return False
    current = active_idea_id
    while current:
        if current == source_idea_id:
            return True
        idea_path = root / f"ideas/{current}.json"
        if not idea_path.is_file():
            return False
        idea = read_json(idea_path)
        if idea.get("revision_level") != "L0":
            return False
        current = idea.get("parent_idea_id")
    return False


def record_approval(root: Path, action: str, decision: str, scope: str, evidence: list[str], actor: str) -> str:
    if decision not in {"APPROVED", "REJECTED"}:
        raise ValueError("approval decision must be APPROVED or REJECTED")
    if not evidence:
        raise ValueError("approval requires evidence")
    missing = [item for item in evidence if not (root / item).exists()]
    if missing:
        raise ValueError(f"approval evidence missing: {missing}")
    state = load_state(root)
    approval_id = f"AP-{len(state.get('approvals', [])) + 1:03d}"
    record = {
        "approval_id": approval_id, "action": action, "decision": decision, "scope": scope,
        "evidence": evidence, "evidence_hashes": {item: sha256_file(root / item) for item in evidence},
        "actor": actor, "at": now(),
    }
    state.setdefault("approvals", []).append(record)
    save_state(root, state, "approval_recorded", {"approval_id": approval_id, "action": action, "decision": decision})
    return approval_id


def register_resource_envelope(root: Path, payload: dict[str, Any]) -> None:
    required = [
        "source", "deadline", "compute", "financial_limit", "human_review",
        "priorities", "constraints", "assumptions", "confirmed_by_user",
    ]
    missing = [key for key in required if key not in payload or payload[key] in (None, "")]
    if missing:
        raise ValueError(f"resource envelope missing fields: {missing}")
    if payload["source"] not in {"USER_PROVIDED", "USER_CONFIRMED_ASSUMPTIONS"}:
        raise ValueError("resource envelope source must be USER_PROVIDED or USER_CONFIRMED_ASSUMPTIONS")
    if payload["confirmed_by_user"] is not True:
        raise ValueError("empirical resource envelope must be explicitly confirmed by the user")
    if not isinstance(payload["compute"], list) or not isinstance(payload["priorities"], list):
        raise ValueError("resource envelope compute and priorities must be lists")
    serialized = json.dumps(payload, ensure_ascii=False)
    if contains_secret(serialized) or "PRIVATE KEY-----" in serialized:
        raise ValueError("resource envelope must contain capabilities/targets, never credentials")
    path = root / "intake/resource-envelope.json"
    previous = read_json(path) if path.is_file() else None
    previous_hash = sha256_file(path) if previous is not None else None
    if previous is not None:
        previous_payload = {key: previous.get(key) for key in required}
        current_payload = {key: payload.get(key) for key in required}
        if previous_payload == current_payload:
            state = load_state(root)
            save_state(root, state, "resource_envelope_reconfirmed", {"sha256": previous_hash})
            return
    record = {**payload, "schema_version": SCHEMA_VERSION, "captured_at": now()}
    write_json(path, record)
    current_hash = sha256_file(path)
    state = load_state(root)
    if previous_hash and previous_hash != current_hash:
        invalidate(state, "RESOURCE_ENVELOPE_CHANGED", "user resource envelope changed")
        state["active"]["research_program_id"] = None
        state["active"]["publication_contract_id"] = None
    save_state(root, state, "resource_envelope_registered", {"sha256": current_hash})


def _write_versioned_artifact(root: Path, directory: str, prefix: str, payload: dict[str, Any]) -> tuple[str, str]:
    artifact_id = next_id(root / directory, prefix)
    id_key = f"{prefix.removesuffix('-v').replace('-', '_')}_id"
    previous = sorted((root / directory).glob(f"{prefix}-*.json"))
    lineage = {
        "record_version": len(previous) + 1,
        "source_hashes": payload.get("source_hashes", {}),
        "supersedes": previous[-1].stem if previous else None,
        "created_by": payload.get("created_by", "main-model"),
        "reason": payload.get("reason", "initial registration" if not previous else "superseding registration"),
    }
    record = {**payload, **lineage, "schema_version": SCHEMA_VERSION, id_key: artifact_id,
              "created_at": now(), "content_hash": None}
    record["content_hash"] = sha256_json({key: value for key, value in record.items() if key != "content_hash"})
    path = root / directory / f"{artifact_id}.json"
    write_json(path, record)
    return artifact_id, path.relative_to(root).as_posix()


def _same_registered_payload(path: Path, payload: dict[str, Any]) -> bool:
    if not path.is_file():
        return False
    current = read_json(path)
    return all(current.get(key) == value for key, value in payload.items())


def register_user_policy(root: Path, payload: dict[str, Any]) -> str:
    validate_user_policy(payload)
    state = load_state(root)
    previous = state["active"].get("user_policy_id")
    if previous and _same_registered_payload(root / f"intake/{previous}.json", payload):
        save_state(root, state, "user_policy_reconfirmed", {"user_policy_id": previous})
        return previous
    policy_id, path = _write_versioned_artifact(root, "intake", "user-policy-v", payload)
    state["active"]["user_policy_id"] = policy_id
    if previous and previous != policy_id:
        invalidate(state, "USER_POLICY_CHANGED", f"registered {policy_id}")
        for key in (
            "idea_seed_id", "memory_snapshot_id", "idea_candidates_id", "idea_selection_id", "idea_id",
            "science_profile_id", "venue_corpus_id", "venue_profile_id", "venue_profile_judgment_id",
            "research_program_id", "publication_contract_id",
        ):
            state["active"][key] = None
    save_state(root, state, "user_policy_registered", {"user_policy_id": policy_id, "path": path})
    return policy_id


def register_science_profile(root: Path, payload: dict[str, Any]) -> str:
    state = load_state(root)
    seed_id = state["active"].get("idea_seed_id")
    if not seed_id:
        raise ValueError("register the Idea seed before the science profile")
    seed_path = root / f"intake/{seed_id}.json"
    bindings = {"idea_seed_id": seed_id, "idea_seed_hash": sha256_file(seed_path)}
    if any(payload.get(key) != value for key, value in bindings.items()):
        raise ValueError("science profile must bind the active Idea seed")
    required = [
        "research_scope", "corpus_protocol", "primary_sources", "closest_work", "benchmark_landscape",
        "scientific_conventions", "evidence_conventions", "writing_conventions", "open_questions",
        "freshness", "limitations", "reviewer",
    ]
    missing = [key for key in required if not payload.get(key)]
    if missing:
        raise ValueError(f"science profile missing non-empty fields: {missing}")
    if not isinstance(payload["primary_sources"], list) or not payload["primary_sources"]:
        raise ValueError("science profile requires primary_sources")
    for index, source in enumerate(payload["primary_sources"]):
        required_source = ("title", "venue", "year", "source", "full_text", "relevance", "read_scope")
        if not isinstance(source, dict) or any(source.get(key) in (None, "", []) for key in required_source):
            raise ValueError(f"science profile source {index} requires {', '.join(required_source)}")
        identity = source["source"]
        if not isinstance(identity, dict) or not any(identity.get(key) for key in ("doi", "url", "official_path")):
            raise ValueError(f"science profile source {index} requires DOI, URL, or official_path")
        full_text = source["full_text"]
        if not isinstance(full_text, dict) or not full_text.get("path") or not full_text.get("sha256"):
            raise ValueError(f"science profile source {index} requires a local full-text path and sha256")
        path = Path(str(full_text["path"]))
        path = path if path.is_absolute() else root / path
        if not path.is_file() or sha256_file(path) != full_text["sha256"]:
            raise ValueError(f"science profile source {index} full text is missing or hash-mismatched")
    previous = state["active"].get("science_profile_id")
    if previous and _same_registered_payload(root / f"calibration/{previous}.json", payload):
        save_state(root, state, "science_profile_reconfirmed", {"science_profile_id": previous})
        return previous
    artifact_id, path = _write_versioned_artifact(root, "calibration", "science-profile-v", payload)
    state["active"]["science_profile_id"] = artifact_id
    if previous and previous != artifact_id:
        invalidate(state, "SCIENCE_PROFILE_CHANGED", f"registered {artifact_id}")
        for key in (
            "idea_candidates_id", "idea_selection_id", "idea_id",
            "venue_corpus_id", "venue_profile_id", "venue_profile_judgment_id",
            "research_program_id", "publication_contract_id",
        ):
            state["active"][key] = None
    save_state(root, state, "science_profile_registered", {"science_profile_id": artifact_id, "path": path})
    return artifact_id


def register_venue_corpus(root: Path, payload: dict[str, Any]) -> str:
    state = load_state(root)
    policy_id = state["active"].get("user_policy_id")
    science_id = state["active"].get("science_profile_id")
    if not policy_id or not science_id:
        raise ValueError("venue corpus requires an active user policy and science profile")
    policy_path = root / f"intake/{policy_id}.json"
    science_path = root / f"calibration/{science_id}.json"
    bindings = {
        "user_policy_id": policy_id,
        "user_policy_hash": sha256_file(policy_path),
        "science_profile_id": science_id,
        "science_profile_hash": sha256_file(science_path),
    }
    if any(payload.get(key) != value for key, value in bindings.items()):
        raise ValueError("venue corpus policy/science-profile bindings are missing or stale")
    policy = read_json(policy_path)
    venue_basis = payload.get("venue_basis")
    if not isinstance(venue_basis, dict):
        raise ValueError("venue corpus venue_basis must be an object")
    if not policy.get("target_venue"):
        required_selection = ("type", "venues", "selection_rationale", "official_sources", "format_and_evidence_differences")
        if venue_basis.get("type") != "MODEL_SELECTED_LEADING_VENUES" or any(
            venue_basis.get(key) in (None, "", []) for key in required_selection
        ):
            raise ValueError("unspecified venue requires a documented leading-venue selection, official sources, and differences")
    elif not venue_basis.get("venues") or policy["target_venue"] not in venue_basis["venues"]:
        raise ValueError("user-selected target venue must appear in venue_basis.venues")
    required = (
        "venue_basis", "research_scope", "paper_archetype", "inclusion_criteria",
        "exclusion_criteria", "time_window", "publication_status", "stopping_rule",
        "candidate_sources", "reviewer",
    )
    if any(payload.get(key) in (None, "", []) for key in required):
        raise ValueError(f"venue corpus requires {', '.join(required)}")
    if not isinstance(payload["inclusion_criteria"], list) or not isinstance(payload["exclusion_criteria"], list):
        raise ValueError("venue corpus inclusion/exclusion criteria must be lists")
    candidates = payload["candidate_sources"]
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("venue corpus candidate_sources must be a non-empty list")
    identities: set[str] = set()
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict) or any(
            not candidate.get(key) for key in ("paper_id", "title", "venue", "accepted_status")
        ):
            raise ValueError(f"venue corpus candidate {index} lacks paper_id/title/venue/accepted_status")
        identity = str(candidate.get("doi") or candidate.get("official_url") or "")
        if not identity:
            raise ValueError(f"venue corpus candidate {index} requires DOI or official_url")
        if identity in identities:
            raise ValueError(f"duplicate venue corpus source: {identity}")
        identities.add(identity)
    previous = state["active"].get("venue_corpus_id")
    if previous and _same_registered_payload(root / f"calibration/{previous}.json", payload):
        save_state(root, state, "venue_corpus_reconfirmed", {"venue_corpus_id": previous})
        return previous
    corpus_id, path = _write_versioned_artifact(root, "calibration", "venue-corpus-v", payload)
    state["active"]["venue_corpus_id"] = corpus_id
    if previous and previous != corpus_id:
        invalidate(state, "VENUE_CORPUS_CHANGED", f"registered {corpus_id}")
        state["active"]["idea_candidates_id"] = None
        state["active"]["idea_selection_id"] = None
        state["active"]["idea_id"] = None
        state["active"]["venue_profile_id"] = None
        state["active"]["venue_profile_judgment_id"] = None
        state["active"]["research_program_id"] = None
        state["active"]["publication_contract_id"] = None
    save_state(root, state, "venue_corpus_registered", {"venue_corpus_id": corpus_id, "path": path})
    return corpus_id


def register_venue_profile(root: Path, payload: dict[str, Any]) -> str:
    state = load_state(root)
    policy_id = state["active"].get("user_policy_id")
    corpus_id = state["active"].get("venue_corpus_id")
    if not policy_id or not corpus_id:
        raise ValueError("register a user policy and frozen venue corpus before the venue profile")
    policy_path = root / f"intake/{policy_id}.json"
    if payload.get("user_policy_id") != policy_id or payload.get("user_policy_hash") != sha256_file(policy_path):
        raise ValueError("venue profile must bind the active user policy ID and file hash")
    corpus_path = root / f"calibration/{corpus_id}.json"
    if payload.get("venue_corpus_id") != corpus_id or payload.get("venue_corpus_hash") != sha256_file(corpus_path):
        raise ValueError("venue profile must bind the active frozen venue corpus")
    corpus = read_json(corpus_path)
    corpus_sources = {
        str(item.get("doi") or item.get("official_url"))
        for item in corpus.get("candidate_sources", [])
    }
    profile_sources = {
        str((item.get("source") or {}).get("doi") or (item.get("source") or {}).get("url") or (item.get("source") or {}).get("official_path"))
        for item in payload.get("papers", []) if isinstance(item, dict)
    }
    if profile_sources != corpus_sources:
        raise ValueError("venue profile paper sources must exactly match the pre-frozen venue corpus")
    validate_venue_profile(root, payload)
    previous = state["active"].get("venue_profile_id")
    if previous and _same_registered_payload(root / f"calibration/{previous}.json", payload):
        save_state(root, state, "venue_profile_reconfirmed", {"venue_profile_id": previous})
        return previous
    profile_id, path = _write_versioned_artifact(root, "calibration", "venue-profile-v", payload)
    state["active"]["venue_profile_id"] = profile_id
    if previous and previous != profile_id:
        invalidate(state, "VENUE_PROFILE_CHANGED", f"registered {profile_id}")
        state["active"]["idea_candidates_id"] = None
        state["active"]["idea_selection_id"] = None
        state["active"]["idea_id"] = None
        state["active"]["venue_profile_judgment_id"] = None
        state["active"]["research_program_id"] = None
        state["active"]["publication_contract_id"] = None
    save_state(root, state, "venue_profile_registered", {"venue_profile_id": profile_id, "path": path})
    return profile_id


def set_venue_judgment(root: Path, payload: dict[str, Any]) -> str:
    state = load_state(root)
    profile_id = state["active"].get("venue_profile_id")
    if not profile_id:
        raise ValueError("venue judgment requires an active venue profile")
    profile_path = root / f"calibration/{profile_id}.json"
    if payload.get("venue_profile_id") != profile_id or payload.get("venue_profile_hash") != sha256_file(profile_path):
        raise ValueError("venue judgment must bind the active venue profile and hash")
    required = (
        "verdict", "comparability", "profile_confidence", "mean_distortion_review",
        "evidence_program_review", "limitations", "reviewer",
    )
    if any(payload.get(key) in (None, "", []) for key in required):
        raise ValueError(f"venue judgment requires {', '.join(required)}")
    if payload["verdict"] not in {"PASS", "PASS_WITH_EXPLAINED_DEVIATION"}:
        raise ValueError("venue judgment must pass before VENUE_PROFILED")
    previous = state["active"].get("venue_profile_judgment_id")
    if previous and _same_registered_payload(root / f"calibration/{previous}.json", payload):
        save_state(root, state, "venue_judgment_reconfirmed", {"venue_profile_judgment_id": previous})
        return previous
    judgment_id, path = _write_versioned_artifact(root, "calibration", "venue-profile-judgment-v", payload)
    state["active"]["venue_profile_judgment_id"] = judgment_id
    if previous and previous != judgment_id:
        invalidate(state, "VENUE_JUDGMENT_CHANGED", f"registered {judgment_id}")
        state["active"]["idea_candidates_id"] = None
        state["active"]["idea_selection_id"] = None
        state["active"]["idea_id"] = None
        state["active"]["research_program_id"] = None
        state["active"]["publication_contract_id"] = None
    save_state(root, state, "venue_judgment_registered", {"venue_profile_judgment_id": judgment_id, "path": path})
    return judgment_id


def freeze_publication_contract(root: Path, payload: dict[str, Any], approval: str) -> str:
    state = load_state(root)
    if not approval_valid(state, approval):
        raise ValueError("publication contract freeze requires a recorded APPROVED approval ID")
    approval_meta = approval_record(state, approval) or {}
    if approval_meta.get("action") != "FREEZE_PUBLICATION_CONTRACT" or approval_meta.get("scope") != state["active"].get("idea_id"):
        raise ValueError("publication approval must use FREEZE_PUBLICATION_CONTRACT and scope the active idea")
    policy_id = state["active"].get("user_policy_id")
    venue_id = state["active"].get("venue_profile_id")
    program_id = state["active"].get("research_program_id")
    if not policy_id or not venue_id or not program_id:
        raise ValueError("publication contract requires active user policy, venue profile, and research program")
    policy_path = root / f"intake/{policy_id}.json"
    venue_path = root / f"calibration/{venue_id}.json"
    program_path = root / f"contracts/{program_id}.json"
    claims_path = root / "claims/claim-registry.json"
    policy = read_json(policy_path)
    venue = read_json(venue_path)
    bindings = {
        "user_policy_id": policy_id,
        "user_policy_hash": sha256_file(policy_path),
        "venue_profile_id": venue_id,
        "venue_profile_hash": sha256_file(venue_path),
        "research_program_id": program_id,
        "research_program_hash": sha256_file(program_path),
        "claim_registry_hash": sha256_file(claims_path),
    }
    if any(payload.get(key) != value for key, value in bindings.items()):
        raise ValueError("publication contract policy/venue bindings are missing or stale")
    if payload.get("idea_id") != state["active"].get("idea_id"):
        raise ValueError("publication contract must bind the active idea")
    registry = read_json(claims_path)
    active_claims = {item["claim_id"] for item in registry.get("claims", []) if item.get("active")}
    if set(payload.get("claim_ids", [])) != active_claims:
        raise ValueError("publication contract claim_ids must exactly equal the active claim set")
    validate_publication_contract(payload, policy, venue)
    contract_id, path = _write_versioned_artifact(root, "contracts", "publication-contract-v", payload)
    previous = state["active"].get("publication_contract_id")
    state["active"]["publication_contract_id"] = contract_id
    if previous and previous != contract_id:
        invalidate(state, "PUBLICATION_CONTRACT_CHANGED", f"froze {contract_id}")
        state["active"]["publication_judgment_id"] = None
        state["active"]["release_audit_id"] = None
    save_state(root, state, "publication_contract_frozen", {"publication_contract_id": contract_id, "path": path})
    return contract_id


def validate_feasibility(root: Path, payload: dict[str, Any], profile: str) -> None:
    feasibility = payload.get("feasibility")
    if profile == "proposal":
        if not isinstance(feasibility, dict) or not feasibility.get("status"):
            raise ValueError("proposal contract requires feasibility.status")
        if feasibility.get("status") not in {"PLANNED_ONLY", "MEASURED", "NOT_REQUIRED"}:
            raise ValueError("proposal feasibility.status must be PLANNED_ONLY, MEASURED, or NOT_REQUIRED")
        return
    if not isinstance(feasibility, dict):
        raise ValueError("empirical contract requires a feasibility object before freeze")
    required = ["status", "budget_fit", "deadline_fit", "estimated_cost", "probes", "projection_rationale"]
    missing = [key for key in required if key not in feasibility or feasibility[key] in (None, "", [])]
    if missing:
        raise ValueError(f"contract feasibility missing fields: {missing}")
    if feasibility["status"] != "MEASURED":
        raise ValueError("empirical contract feasibility must be MEASURED from a representative microprobe")
    if feasibility["budget_fit"] is not True:
        raise ValueError("contract cannot freeze when the measured feasibility does not fit the budget")
    if feasibility["deadline_fit"] is not True:
        raise ValueError("contract cannot freeze when the measured feasibility misses the user deadline")
    probes = feasibility["probes"]
    if not isinstance(probes, list) or not probes:
        raise ValueError("empirical feasibility requires at least one representative probe")
    measured = 0
    for index, probe in enumerate(probes):
        if not isinstance(probe, dict) or any(probe.get(key) in (None, "", []) for key in ("component", "status", "rationale")):
            raise ValueError(f"feasibility probe {index} requires component, status, and rationale")
        if probe["status"] not in {"MEASURED", "NOT_APPLICABLE"}:
            raise ValueError(f"feasibility probe {index} status is invalid")
        if probe["status"] == "MEASURED":
            measured += 1
            if not probe.get("measurement") or not probe.get("evidence"):
                raise ValueError(f"measured feasibility probe {index} requires measurement and evidence")
            evidence = probe["evidence"] if isinstance(probe["evidence"], list) else [probe["evidence"]]
            missing_paths = [item for item in evidence if not (root / item).exists()]
            if missing_paths:
                raise ValueError(f"feasibility probe {index} evidence missing: {missing_paths}")
    if measured == 0:
        raise ValueError("empirical feasibility requires at least one measured dominant-cost probe")


def freeze_research_program(root: Path, payload: dict[str, Any], approval: str) -> str:
    state = load_state(root)
    if not approval_valid(state, approval):
        raise ValueError("contract freeze requires a recorded APPROVED approval ID")
    approval_meta = approval_record(state, approval) or {}
    if approval_meta.get("action") != "FREEZE_RESEARCH_PROGRAM" or approval_meta.get("scope") != state["active"].get("idea_id"):
        raise ValueError("research-program approval must use action FREEZE_RESEARCH_PROGRAM and scope the active idea_id")
    design_judgments = []
    for artifact in approval_meta.get("evidence", []):
        path = root / artifact
        if path.suffix != ".json":
            continue
        try:
            value = read_json(path)
        except ValueError:
            continue
        if value.get("artifact_type") == "scientific_judgment" and value.get("gate") == "G3" and value.get("verdict") in {"PASS", "PASS_WITH_EXPLAINED_DEVIATION"}:
            design_judgments.append(artifact)
    if not design_judgments:
        raise ValueError("contract approval must cite a passing G3 scientific judgment artifact")
    required = [
        "claim_ids", "evaluation_units", "study_inputs", "protocol", "outcomes", "comparators",
        "analysis_plan", "test_set_policy", "stop_conditions", "resource_plan", "feasibility",
        "benchmark_policy", "venue_alignment", "revalidation_policy", "idea_iteration_policy",
    ]
    missing = [key for key in required if not payload.get(key)]
    if missing:
        raise ValueError(f"contract missing non-empty fields: {missing}")
    policy_id = state["active"].get("user_policy_id")
    venue_id = state["active"].get("venue_profile_id")
    science_id = state["active"].get("science_profile_id")
    venue_judgment_id = state["active"].get("venue_profile_judgment_id")
    if not all((policy_id, venue_id, science_id, venue_judgment_id)):
        raise ValueError("research program requires active policy, science profile, venue profile, and venue judgment")
    venue_judgment = read_json(root / f"calibration/{venue_judgment_id}.json")
    if venue_judgment.get("venue_profile_id") != venue_id or venue_judgment.get("venue_profile_hash") != sha256_file(root / f"calibration/{venue_id}.json"):
        raise ValueError("research program cannot freeze against a stale venue judgment")
    bindings = {
        "user_policy_id": policy_id,
        "user_policy_hash": sha256_file(root / f"intake/{policy_id}.json"),
        "science_profile_id": science_id,
        "science_profile_hash": sha256_file(root / f"calibration/{science_id}.json"),
        "venue_profile_id": venue_id,
        "venue_profile_hash": sha256_file(root / f"calibration/{venue_id}.json"),
    }
    if any(payload.get(key) != value for key, value in bindings.items()):
        raise ValueError("research program policy/science/venue bindings are missing or stale")
    venue = read_json(root / f"calibration/{venue_id}.json")
    alignment = payload["venue_alignment"]
    required_alignment = ("observed_evidence_dimensions", "selected_program_summary", "rationale", "deviations")
    if not isinstance(alignment, dict) or any(alignment.get(key) in (None, "", []) for key in required_alignment[:-1]) or "deviations" not in alignment:
        raise ValueError(f"venue_alignment requires {', '.join(required_alignment)}")
    if alignment["observed_evidence_dimensions"] != venue["aggregates"]["evidence_dimension_means"]:
        raise ValueError("venue_alignment observations are stale")
    if not isinstance(alignment["deviations"], list):
        raise ValueError("venue_alignment.deviations must be a list")
    revalidation = payload["revalidation_policy"]
    if not isinstance(revalidation, dict) or any(key not in revalidation for key in ("required", "rationale", "independence_axis", "trigger")):
        raise ValueError("revalidation_policy requires required, rationale, independence_axis, and trigger")
    if state["profile"] == "high_risk" and revalidation.get("required") is not True:
        raise ValueError("high-risk research requires independent revalidation")
    benchmark = payload["benchmark_policy"]
    benchmark_path = root / "grounding/benchmark_candidates.json"
    if not isinstance(benchmark, dict) or not all(benchmark.get(key) for key in ("artifact", "artifact_hash", "classification", "action", "rationale")):
        raise ValueError("benchmark_policy requires artifact, hash, classification, action, and rationale")
    if benchmark.get("artifact") != "grounding/benchmark_candidates.json" or not benchmark_path.is_file():
        raise ValueError("benchmark_policy must bind grounding/benchmark_candidates.json")
    if benchmark.get("artifact_hash") != sha256_file(benchmark_path):
        raise ValueError("benchmark_policy artifact hash is stale")
    applicable = {"DIRECT", "ADAPTED", "PARTIAL", "PUBLIC_BENCHMARK"}
    if benchmark["classification"] in applicable and benchmark["action"] not in {"ACQUIRE_AND_REPRODUCE", "ACQUIRE_ADAPT_AND_REPRODUCE"}:
        raise ValueError("an applicable public benchmark must be acquired and reproduced")
    resource_plan = payload["resource_plan"]
    required_resource_plan = ("stage_budgets", "deadline_fit", "reserve", "replan_triggers", "allocation_rationale")
    if not isinstance(resource_plan, dict) or any(resource_plan.get(key) in (None, "", []) for key in required_resource_plan):
        raise ValueError(f"research program resource_plan requires {', '.join(required_resource_plan)}")
    if not isinstance(resource_plan["stage_budgets"], dict) or not resource_plan["stage_budgets"]:
        raise ValueError("resource_plan.stage_budgets must contain the applicable stages")
    if resource_plan["deadline_fit"] is not True:
        raise ValueError("research program cannot freeze when resource_plan.deadline_fit is false")
    iteration = payload["idea_iteration_policy"]
    if not isinstance(iteration, dict) or not all(iteration.get(key) for key in ("allowed_levels", "diagnosis_before_revision", "negative_result_policy", "stop_rule")):
        raise ValueError("idea_iteration_policy is incomplete")
    registry = read_json(root / "claims/claim-registry.json")
    valid_claims = {item["claim_id"] for item in registry.get("claims", []) if item.get("active")}
    unknown = sorted(set(payload["claim_ids"]) - valid_claims)
    if unknown:
        raise ValueError(f"contract references unknown claims: {unknown}")
    budget = resource_plan
    if not isinstance(budget, dict):
        raise ValueError("contract budget must be an object")
    for key in ("max_runs", "max_branches", "max_branch_depth"):
        if key not in budget or not isinstance(budget[key], int):
            raise ValueError(f"contract budget requires integer {key}")
    if not 1 <= budget["max_runs"] <= 10_000:
        raise ValueError("contract budget.max_runs must be between 1 and 10000")
    if not 0 <= budget["max_branches"] <= 32:
        raise ValueError("contract budget.max_branches must be between 0 and 32")
    if not 0 <= budget["max_branch_depth"] <= 4:
        raise ValueError("contract budget.max_branch_depth must be between 0 and 4")
    if state["profile"] != "proposal":
        envelope_path = root / "intake/resource-envelope.json"
        if not envelope_path.is_file():
            raise ValueError("empirical contract requires a user-confirmed intake/resource-envelope.json")
        envelope = read_json(envelope_path)
        if envelope.get("confirmed_by_user") is not True:
            raise ValueError("empirical resource envelope is not user-confirmed")
        if resource_plan.get("resource_envelope") != "intake/resource-envelope.json":
            raise ValueError("resource_plan must reference intake/resource-envelope.json")
        if resource_plan.get("resource_envelope_hash") != sha256_file(envelope_path):
            raise ValueError("resource_plan resource envelope hash is stale")
    unit_ids: set[str] = set()
    covered_claims: set[str] = set()
    unit_required = [
        "unit_id", "kind", "claim_ids", "question", "why_it_tests_claim", "protocol_summary",
        "positive_interpretation", "negative_interpretation", "confounders", "out_of_scope_conclusions",
        "difficulty", "stop_condition",
    ]
    valid_kinds = {"benchmark", "experiment", "simulation", "observational_analysis", "qualitative_study", "proof", "artifact_evaluation"}
    for index, unit in enumerate(payload["evaluation_units"]):
        if not isinstance(unit, dict):
            raise ValueError("evaluation units must be structured claim-linked objects")
        missing_unit = [key for key in unit_required if key not in unit or unit[key] in (None, "", [])]
        if missing_unit:
            raise ValueError(f"evaluation unit {index} missing fields: {missing_unit}")
        unit_id = unit["unit_id"]
        if unit_id in unit_ids:
            raise ValueError(f"duplicate unit_id: {unit_id}")
        if unit["kind"] not in valid_kinds:
            raise ValueError(f"evaluation unit {unit_id} has an invalid kind")
        unit_ids.add(unit_id)
        unit_claims = set(unit["claim_ids"])
        unknown_unit_claims = sorted(unit_claims - set(payload["claim_ids"]))
        if unknown_unit_claims:
            raise ValueError(f"evaluation unit {unit_id} references claims outside the contract: {unknown_unit_claims}")
        covered_claims.update(unit_claims)
    uncovered = sorted(set(payload["claim_ids"]) - covered_claims)
    if uncovered:
        raise ValueError(f"contract claims lack a planned evaluation/proof unit: {uncovered}")
    validate_feasibility(root, payload, state["profile"])
    program_id = next_id(root / "contracts", "research-program-v")
    contract = dict(payload)
    source_schema_version = contract.pop("schema_version", contract.get("contract_schema_version", "legacy"))
    contract.update({
        "contract_schema_version": "5.0.0",
        "source_schema_version": source_schema_version,
        "lifecycle_schema_version": SCHEMA_VERSION,
        "research_program_id": program_id,
        "idea_id": state["active"]["idea_id"],
        "status": "FROZEN",
        "approval_id": approval,
        "created_at": now(),
        "content_hash": None,
    })
    contract["content_hash"] = sha256_json({k: v for k, v in contract.items() if k != "content_hash"})
    write_json(root / f"contracts/{program_id}.json", contract)
    previous = state["active"].get("research_program_id")
    state["active"]["research_program_id"] = program_id
    if previous and previous != program_id:
        invalidate(state, "PROTOCOL_CHANGED", f"froze {program_id}")
    save_state(root, state, "research_program_frozen", {"research_program_id": program_id})
    return program_id


def manuscript_files(source: Path) -> list[Path]:
    if source.is_file():
        return [source]
    files: list[Path] = []
    for path in sorted(source.iterdir()):
        if path.is_symlink():
            continue
        if path.is_file() and (path.name in MANUSCRIPT_ROOT_FILES or path.suffix in MANUSCRIPT_ROOT_SUFFIXES):
            files.append(path)
        elif path.is_dir() and path.name in MANUSCRIPT_DIRECTORIES:
            files.extend(sorted(item for item in path.rglob("*") if item.is_file() and not item.is_symlink()))
    return files


def register_manuscript(root: Path, source: Path) -> str:
    if not source.exists():
        raise ValueError(f"manuscript source does not exist: {source}")
    files = manuscript_files(source)
    if not files:
        raise ValueError("manuscript source contains no allowlisted manuscript files")
    if source.is_dir() and not any(path.relative_to(source).as_posix() == "main.tex" for path in files):
        raise ValueError("manuscript directory requires main.tex")
    digest_payload = []
    for path in files:
        rel = path.name if source.is_file() else path.relative_to(source).as_posix()
        digest_payload.append({"path": rel, "sha256": sha256_file(path)})
    manuscript_hash = sha256_json(digest_payload)
    state = load_state(root)
    previous_id = state["active"].get("manuscript_id")
    if previous_id:
        previous = read_json(root / f"manuscript/{previous_id}.json")
        if previous.get("content_hash") == manuscript_hash:
            return previous_id
        invalidate(state, "MANUSCRIPT_CHANGED", f"registered manuscript hash {manuscript_hash}")
        state["active"]["publication_judgment_id"] = None
        state["active"]["release_audit_id"] = None
    manuscript_id = f"manuscript-v{len(list((root / 'manuscript').glob('manuscript-v*.json'))) + 1:03d}"
    active_dir = root / "manuscript" / "active"
    if active_dir.exists():
        shutil.rmtree(active_dir)
    active_dir.mkdir(parents=True)
    if source.is_file():
        shutil.copy2(source, active_dir / source.name)
    else:
        for path in files:
            target = active_dir / path.relative_to(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    record = {
        "schema_version": SCHEMA_VERSION,
        "manuscript_id": manuscript_id,
        "source": str(source.resolve()),
        "scope": {
            "root_files": sorted(MANUSCRIPT_ROOT_FILES),
            "root_suffixes": sorted(MANUSCRIPT_ROOT_SUFFIXES),
            "directories": sorted(MANUSCRIPT_DIRECTORIES),
        },
        "content_hash": manuscript_hash,
        "files": digest_payload,
        "created_at": now(),
    }
    write_json(root / f"manuscript/{manuscript_id}.json", record)
    state["active"]["manuscript_id"] = manuscript_id
    save_state(root, state, "manuscript_registered", {"manuscript_id": manuscript_id, "content_hash": manuscript_hash})
    return manuscript_id


def register_bibliography_coverage(root: Path, payload: dict[str, Any]) -> str:
    state = load_state(root)
    contract_id = state["active"].get("publication_contract_id")
    if not contract_id:
        raise ValueError("bibliography coverage requires an active publication contract")
    contract_path = root / f"contracts/{contract_id}.json"
    contract = read_json(contract_path)
    required = [
        "publication_contract_id", "publication_contract_hash", "planned_citation_keys",
        "sources", "claim_coverage", "source_quality_review", "reviewer",
    ]
    missing = [key for key in required if not payload.get(key)]
    if missing:
        raise ValueError(f"bibliography coverage missing non-empty fields: {missing}")
    if payload["publication_contract_id"] != contract_id or payload["publication_contract_hash"] != sha256_file(contract_path):
        raise ValueError("bibliography coverage publication contract binding is stale")
    keys = payload["planned_citation_keys"]
    if not isinstance(keys, list) or len(keys) != len(set(keys)):
        raise ValueError("planned_citation_keys must be a unique list")
    target = int(contract["targets"]["minimum_unique_cited_references"])
    if len(keys) < target:
        raise ValueError(f"bibliography coverage has {len(keys)} keys but requires at least {target}")
    sources = payload["sources"]
    if not isinstance(sources, list):
        raise ValueError("bibliography coverage sources must be a list")
    source_by_key: dict[str, dict[str, Any]] = {}
    required_source_fields = (
        "bibkey", "metadata_verification_source", "source_type", "supported_claims",
        "intended_sections", "evidence_note", "limitations", "inspected_status",
    )
    for index, source in enumerate(sources):
        if not isinstance(source, dict) or any(source.get(key) in (None, "", []) for key in required_source_fields):
            raise ValueError(f"bibliography source {index} lacks complete evidence coverage fields")
        if not source.get("doi") and not source.get("official_url"):
            raise ValueError(f"bibliography source {index} requires DOI or official_url")
        if source["bibkey"] in source_by_key:
            raise ValueError(f"duplicate bibliography source record: {source['bibkey']}")
        if source["inspected_status"] not in {"FULL_TEXT", "ABSTRACT_WITH_LIMITATION", "OFFICIAL_RECORD"}:
            raise ValueError(f"bibliography source {source['bibkey']} has invalid inspected_status")
        source_by_key[source["bibkey"]] = source
    if set(source_by_key) != set(keys):
        raise ValueError("bibliography source records must exactly equal planned_citation_keys")
    active_claims = set(contract["claim_ids"])
    covered_claims = set()
    for item in payload["claim_coverage"]:
        if not isinstance(item, dict) or not item.get("claim_id") or not item.get("source_keys"):
            raise ValueError("bibliography claim_coverage entries require claim_id and source_keys")
        if not set(item["source_keys"]).issubset(source_by_key):
            raise ValueError(f"claim coverage for {item['claim_id']} references unknown bibliography keys")
        covered_claims.add(item["claim_id"])
    if covered_claims != active_claims:
        raise ValueError("bibliography claim coverage must exactly cover the publication contract claims")
    path = root / "manuscript/bibliography-coverage.json"
    if _same_registered_payload(path, payload):
        state["active"]["bibliography_coverage"] = path.relative_to(root).as_posix()
        save_state(root, state, "bibliography_coverage_reconfirmed", {"path": path.relative_to(root).as_posix()})
        return path.relative_to(root).as_posix()
    previous_hash = sha256_file(path) if path.is_file() else None
    record = {**payload, "schema_version": SCHEMA_VERSION, "created_at": now()}
    write_json(path, record)
    if previous_hash and previous_hash != sha256_file(path):
        invalidate(state, "BIBLIOGRAPHY_COVERAGE_CHANGED", "bibliography coverage changed")
        state["active"]["publication_judgment_id"] = None
        state["active"]["release_audit_id"] = None
    state["active"]["bibliography_coverage"] = path.relative_to(root).as_posix()
    save_state(root, state, "bibliography_coverage_registered", {"path": path.relative_to(root).as_posix(), "count": len(keys)})
    return path.relative_to(root).as_posix()


def register_figure_routing(root: Path, payload: dict[str, Any]) -> str:
    state = load_state(root)
    contract_id = state["active"].get("publication_contract_id")
    if not contract_id:
        raise ValueError("figure routing requires an active publication contract")
    contract_path = root / f"contracts/{contract_id}.json"
    contract = read_json(contract_path)
    if payload.get("publication_contract_id") != contract_id or payload.get("publication_contract_hash") != sha256_file(contract_path):
        raise ValueError("figure routing publication contract binding is stale")
    routes = payload.get("figures")
    if not isinstance(routes, list):
        raise ValueError("figure routing figures must be a list, including an explicit empty list")
    planned = {item["figure_id"]: item for item in contract["figure_plan"]}
    routed = {item.get("figure_id"): item for item in routes if isinstance(item, dict)}
    if set(routed) != set(planned) or len(routed) != len(routes):
        raise ValueError("figure routing IDs must exactly equal publication contract figure IDs")
    for figure_id, route in routed.items():
        expected = planned[figure_id]
        route_required = (
            "section_role", "claim_ids", "semantic_type", "caption", "source_of_truth", "required_content",
            "forbidden_content", "renderer", "renderer_rationale",
            "final_formats", "accessibility", "typography",
        )
        if any(route.get(key) in (None, "", []) for key in route_required):
            raise ValueError(f"figure routing for {figure_id} lacks complete route contract fields")
        if route.get("class") != expected["class"] or route.get("route") != expected["route"]:
            raise ValueError(f"figure routing for {figure_id} differs from the frozen publication contract")
        if set(route["claim_ids"]) != set(expected["claim_ids"]):
            raise ValueError(f"figure routing for {figure_id} changes its frozen claim bindings")
        if expected["class"] == "measured_evidence" and not route.get("fact_ids"):
            raise ValueError(f"measured evidence figure {figure_id} requires canonical fact_ids")
        if expected["class"] in {"original_observation", "exact_structure"} and not route.get("source_artifacts"):
            raise ValueError(f"{expected['class']} figure {figure_id} requires source_artifacts")
        if expected["class"] == "explanatory_synthesis":
            budget = route.get("candidate_budget")
            if not isinstance(budget, dict) or not isinstance(budget.get("planned_candidates"), int) or budget["planned_candidates"] < 1:
                raise ValueError(f"PaperBanana figure {figure_id} requires a positive model-selected candidate budget")
            if not budget.get("resource_basis") or not budget.get("rationale") or not budget.get("stop_conditions"):
                raise ValueError(f"PaperBanana figure {figure_id} candidate budget is incomplete")
            if route.get("drawai_status") not in {"AVAILABLE_REQUIRED", "UNAVAILABLE_EVIDENCED_SKIP"}:
                raise ValueError(f"PaperBanana figure {figure_id} requires an explicit DrawAI preflight status")
            preflight = route.get("drawai_preflight")
            if not preflight or not (root / preflight).is_file():
                raise ValueError(f"PaperBanana figure {figure_id} requires DrawAI preflight evidence")
    path = root / "manuscript/figure-routing.json"
    if _same_registered_payload(path, payload):
        state["active"]["figure_routing"] = path.relative_to(root).as_posix()
        save_state(root, state, "figure_routing_reconfirmed", {"path": path.relative_to(root).as_posix()})
        return path.relative_to(root).as_posix()
    previous_hash = sha256_file(path) if path.is_file() else None
    write_json(path, {**payload, "schema_version": SCHEMA_VERSION, "created_at": now()})
    if previous_hash and previous_hash != sha256_file(path):
        invalidate(state, "FIGURE_ROUTING_CHANGED", "figure routing changed")
        state["active"]["publication_judgment_id"] = None
        state["active"]["release_audit_id"] = None
    state["active"]["figure_routing"] = path.relative_to(root).as_posix()
    save_state(root, state, "figure_routing_registered", {"path": path.relative_to(root).as_posix(), "count": len(routes)})
    return path.relative_to(root).as_posix()


def register_publication_judgment(root: Path, payload: dict[str, Any]) -> str:
    state = load_state(root)
    contract_id = state["active"].get("publication_contract_id")
    manuscript_id = state["active"].get("manuscript_id")
    if not contract_id or not manuscript_id:
        raise ValueError("publication judgment requires active publication contract and manuscript")
    contract_path = root / f"contracts/{contract_id}.json"
    manuscript_path = root / f"manuscript/{manuscript_id}.json"
    bindings = {
        "publication_contract_id": contract_id,
        "publication_contract_hash": sha256_file(contract_path),
        "manuscript_id": manuscript_id,
        "manuscript_hash": sha256_file(manuscript_path),
    }
    if any(payload.get(key) != value for key, value in bindings.items()):
        raise ValueError("publication judgment contract/manuscript bindings are missing or stale")
    required = (
        "figure_role_completeness", "citation_relevance", "experiment_claim_coverage",
        "venue_scale_substance", "claim_argument_consistency", "cross_section_consistency",
        "method_result_alignment", "redundancy_and_filler_review", "internal_provenance_boundary",
        "limitations_and_negative_results", "rendered_pdf_review", "page_scale", "verdict", "reviewer",
    )
    if any(payload.get(key) in (None, "", []) for key in required):
        raise ValueError(f"publication judgment requires {', '.join(required)}")
    if not isinstance(payload.get("deviations"), list):
        raise ValueError("publication judgment deviations must be an explicit list")
    latex = read_json(root / "reports/manuscript/latex-verdict.json")
    contract = read_json(contract_path)
    rendered_review = payload["rendered_pdf_review"]
    if not isinstance(rendered_review, dict) or any(
        key not in rendered_review
        for key in ("pdf_sha256", "actual_pdf_reviewed", "layout_findings", "blocking_issues")
    ):
        raise ValueError("rendered_pdf_review requires pdf_sha256, actual_pdf_reviewed, layout_findings, and blocking_issues")
    if rendered_review["pdf_sha256"] != latex.get("pdf_sha256") or rendered_review["actual_pdf_reviewed"] is not True:
        raise ValueError("publication judgment must bind and inspect the actual compiled PDF")
    if not isinstance(rendered_review["layout_findings"], list) or not isinstance(rendered_review["blocking_issues"], list):
        raise ValueError("rendered_pdf_review findings and blocking issues must be explicit lists")
    if rendered_review["blocking_issues"]:
        raise ValueError("publication judgment cannot pass with unresolved rendered-PDF blockers")
    page_scale = payload["page_scale"]
    expected_page_scale = {
        "actual_pages": latex.get("page_count"),
        "target_range": contract.get("targets", {}).get("page_range"),
    }
    if not isinstance(page_scale, dict) or any(page_scale.get(key) != value for key, value in expected_page_scale.items()):
        raise ValueError("publication judgment page_scale must bind actual PDF pages and the frozen page range")
    if page_scale.get("verdict") not in {"WITHIN_TARGET", "EXPLAINED_DEVIATION"} or not page_scale.get("rationale"):
        raise ValueError("publication judgment page_scale requires a verdict and substantive rationale")
    lower, upper = expected_page_scale["target_range"]
    within = lower <= expected_page_scale["actual_pages"] <= upper
    if within != (page_scale["verdict"] == "WITHIN_TARGET"):
        raise ValueError("publication judgment page_scale verdict disagrees with the actual target interval")
    if payload["verdict"] not in {"PASS", "PASS_WITH_EXPLAINED_DEVIATION"}:
        raise ValueError("publication judgment must pass before release audit")
    judgment_id, path = _write_versioned_artifact(root, "reports/manuscript", "publication-judgment-v", payload)
    previous = state["active"].get("publication_judgment_id")
    state["active"]["publication_judgment_id"] = judgment_id
    if previous and previous != judgment_id:
        state["active"]["release_audit_id"] = None
        state["gates"].pop("M6", None)
    save_state(root, state, "publication_judgment_registered", {"publication_judgment_id": judgment_id, "path": path})
    return judgment_id


def record_schedule_checkpoint(root: Path, payload: dict[str, Any]) -> str:
    state = load_state(root)
    program_id = state["active"].get("research_program_id")
    if not program_id:
        raise ValueError("schedule checkpoint requires an active frozen research program")
    program_path = root / f"contracts/{program_id}.json"
    if payload.get("research_program_id") != program_id or payload.get("research_program_hash") != sha256_file(program_path):
        raise ValueError("schedule checkpoint must bind the active research program and hash")
    required = (
        "completed_phase", "next_phase", "elapsed", "remaining_schedule",
        "projected_completion", "deadline_fit", "replan_required", "action", "evidence", "reviewer",
    )
    if any(payload.get(key) in (None, "", []) for key in required):
        raise ValueError(f"schedule checkpoint requires {', '.join(required)}")
    if payload["next_phase"] not in phase_sequence(state["profile"]):
        raise ValueError("schedule checkpoint next_phase is not legal for the active profile")
    if not isinstance(payload["remaining_schedule"], dict) or not payload["remaining_schedule"]:
        raise ValueError("schedule checkpoint requires non-empty remaining_schedule")
    evidence = payload["evidence"] if isinstance(payload["evidence"], list) else [payload["evidence"]]
    missing = [item for item in evidence if not (root / item).is_file()]
    if missing:
        raise ValueError(f"schedule checkpoint evidence missing: {missing}")
    if payload["deadline_fit"] is not True:
        if payload["replan_required"] is not True or payload["action"] not in {
            "NARROW_IDEA", "WEAKEN_CLAIMS", "CHANGE_VENUE", "EXTEND_DEADLINE", "STOP",
        }:
            raise ValueError("deadline miss requires an explicit bounded replan action")
    elif payload["replan_required"] is not False or payload["action"] != "CONTINUE":
        raise ValueError("deadline-fit checkpoint must use replan_required=false and action=CONTINUE")
    checkpoint_id = f"schedule-checkpoint-v{len(list((root / 'reports/schedule').glob('schedule-checkpoint-v*.json'))) + 1:03d}"
    record = {
        **payload, "schema_version": SCHEMA_VERSION, "schedule_checkpoint_id": checkpoint_id,
        "evidence_hashes": {item: sha256_file(root / item) for item in evidence}, "created_at": now(),
    }
    path = root / f"reports/schedule/{checkpoint_id}.json"
    write_json(path, record)
    state["active"]["schedule_checkpoint"] = path.relative_to(root).as_posix()
    save_state(root, state, "schedule_checkpoint_recorded", {
        "schedule_checkpoint_id": checkpoint_id, "next_phase": payload["next_phase"],
        "deadline_fit": payload["deadline_fit"], "action": payload["action"],
    })
    return path.relative_to(root).as_posix()


def register_release_audit(root: Path, payload: dict[str, Any]) -> str:
    state = load_state(root)
    contract_id = state["active"].get("publication_contract_id")
    manuscript_id = state["active"].get("manuscript_id")
    required = [
        "publication_contract_id", "publication_contract_hash", "manuscript_id", "manuscript_hash",
        "publication_judgment_id", "publication_judgment_hash", "citation_verdict",
        "figure_verdict", "latex_verdict", "claim_verdict", "blocking_issues", "reviewer",
    ]
    missing = [key for key in required if key not in payload]
    if missing:
        raise ValueError(f"release audit missing fields: {missing}")
    if not contract_id or payload["publication_contract_id"] != contract_id:
        raise ValueError("release audit must bind the active publication contract")
    contract_path = root / f"contracts/{contract_id}.json"
    if payload["publication_contract_hash"] != sha256_file(contract_path):
        raise ValueError("release audit publication contract hash is stale")
    if not manuscript_id or payload["manuscript_id"] != manuscript_id:
        raise ValueError("release audit must bind the active manuscript")
    manuscript_path = root / f"manuscript/{manuscript_id}.json"
    if payload["manuscript_hash"] != sha256_file(manuscript_path):
        raise ValueError("release audit manuscript record hash is stale")
    judgment_id = state["active"].get("publication_judgment_id")
    judgment_path = root / f"reports/manuscript/{judgment_id}.json" if judgment_id else None
    if not judgment_id or payload["publication_judgment_id"] != judgment_id or not judgment_path or not judgment_path.is_file():
        raise ValueError("release audit requires the active publication judgment")
    if payload["publication_judgment_hash"] != sha256_file(judgment_path):
        raise ValueError("release audit publication judgment hash is stale")
    for key in ("citation_verdict", "figure_verdict", "latex_verdict", "claim_verdict"):
        if payload[key] != "PASS":
            raise ValueError(f"release audit {key} must PASS")
    if payload["blocking_issues"]:
        raise ValueError("release audit cannot retain blocking issues")
    audit_id, path = _write_versioned_artifact(root, "reports/release", "release-audit-v", payload)
    state["active"]["release_audit_id"] = audit_id
    save_state(root, state, "release_audit_registered", {"release_audit_id": audit_id, "path": path})
    return audit_id


def register_latex_verdict(root: Path, payload: dict[str, Any], pdf_source: Path) -> str:
    state = load_state(root)
    manuscript_id = state["active"].get("manuscript_id")
    if not manuscript_id:
        raise ValueError("LaTeX verdict requires an active manuscript")
    if payload.get("compiled") is not True or payload.get("error_count") != 0 or not payload.get("input_hash"):
        raise ValueError("LaTeX verdict requires compiled=true, error_count=0, and input_hash")
    if not isinstance(payload.get("page_count"), int) or payload["page_count"] < 1:
        raise ValueError("LaTeX verdict requires the final PDF page_count")
    if not pdf_source.is_file() or pdf_source.suffix.lower() != ".pdf":
        raise ValueError("LaTeX verdict requires the compiled PDF artifact")
    pdf_hash = sha256_file(pdf_source)
    if payload.get("pdf_sha256") and payload["pdf_sha256"] != pdf_hash:
        raise ValueError("provided LaTeX PDF hash does not match the artifact")
    try:
        info = subprocess.check_output(["pdfinfo", str(pdf_source)], text=True, stderr=subprocess.STDOUT, timeout=20)
        match = re.search(r"^Pages:\s+(\d+)\s*$", info, re.MULTILINE)
        if match and int(match.group(1)) != payload["page_count"]:
            raise ValueError("provided LaTeX page_count does not match pdfinfo")
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        pass
    target = root / f"manuscript/compiled/{manuscript_id}.pdf"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(pdf_source, target)
    report_path = root / "reports/manuscript/latex-verdict.json"
    record = {
        **payload,
        "schema_version": SCHEMA_VERSION,
        "manuscript_id": manuscript_id,
        "manuscript_record_hash": sha256_file(root / f"manuscript/{manuscript_id}.json"),
        "pdf": target.relative_to(root).as_posix(),
        "pdf_sha256": pdf_hash,
        "registered_at": now(),
    }
    if report_path.is_file():
        previous = read_json(report_path)
        stable_keys = ("input_hash", "manuscript_id", "manuscript_record_hash", "pdf_sha256")
        if all(previous.get(key) == record.get(key) for key in stable_keys):
            save_state(root, state, "latex_verdict_reconfirmed", {"input_hash": record["input_hash"]})
            return report_path.relative_to(root).as_posix()
        invalidate(state, "LATEX_VERDICT_CHANGED", "registered compile verdict changed")
        state["active"]["publication_judgment_id"] = None
        state["active"]["release_audit_id"] = None
    write_json(report_path, record)
    save_state(root, state, "latex_verdict_registered", {"path": report_path.relative_to(root).as_posix(), "input_hash": record["input_hash"]})
    return report_path.relative_to(root).as_posix()


def manuscript_digest(root: Path) -> str:
    active_dir = root / "manuscript" / "active"
    files = manuscript_files(active_dir)
    return sha256_json([{"path": path.relative_to(active_dir).as_posix(), "sha256": sha256_file(path)} for path in files])


def register_repo(root: Path, payload: dict[str, Any]) -> None:
    required = ["purpose", "url", "commit", "official_status", "license", "local_path", "modification_mode"]
    missing = [key for key in required if not payload.get(key)]
    if missing:
        raise ValueError(f"repository missing fields: {missing}")
    commit = str(payload["commit"])
    if not re.fullmatch(r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}", commit):
        raise ValueError("repository commit must be a full pinned Git object ID")
    mode = payload["modification_mode"]
    if mode not in {"read_only", "adapters_only", "patch_stack", "fork"}:
        raise ValueError("repository modification_mode must be read_only, adapters_only, patch_stack, or fork")
    if contains_secret(str(payload["url"])):
        raise ValueError("repository URL must not contain embedded credentials")
    try:
        checkout = (root / payload["local_path"]).resolve()
        checkout.relative_to(root.resolve())
    except (OSError, ValueError) as exc:
        raise ValueError("repository local_path must stay within the research root") from exc
    if not checkout.is_dir():
        raise ValueError(f"repository checkout does not exist: {payload['local_path']}")
    try:
        observed_commit = subprocess.check_output(
            ["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True, stderr=subprocess.STDOUT, timeout=20
        ).strip()
        observed_remote = subprocess.check_output(
            ["git", "-C", str(checkout), "config", "--get", "remote.origin.url"],
            text=True, stderr=subprocess.STDOUT, timeout=20,
        ).strip()
        dirty = subprocess.check_output(
            ["git", "-C", str(checkout), "status", "--porcelain", "--untracked-files=all"],
            text=True, stderr=subprocess.STDOUT, timeout=20,
        ).splitlines()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ValueError(f"cannot inspect repository checkout: {exc}") from exc
    if observed_commit.lower() != commit.lower():
        raise ValueError(f"repository checkout HEAD {observed_commit} does not match pinned commit {commit}")
    if dirty:
        raise ValueError("registered repository checkout must be clean; commit fork changes or keep adapters/patches outside upstream")
    patches = payload.get("patches") or []
    if mode == "patch_stack" and not patches:
        raise ValueError("patch_stack repository requires hash-bound patches")
    for index, patch in enumerate(patches):
        if not isinstance(patch, dict) or not patch.get("path") or not patch.get("sha256"):
            raise ValueError(f"repository patch {index} requires path and sha256")
        patch_path = root / patch["path"]
        if not patch_path.is_file() or sha256_file(patch_path) != patch["sha256"]:
            raise ValueError(f"repository patch missing or changed: {patch.get('path')}")
    conflicts = payload.get("version_conflicts") or []
    if conflicts:
        report_path = payload.get("conflict_resolution_report")
        if not report_path or not (root / report_path).is_file():
            raise ValueError("version conflicts require a conflict_resolution_report")
        report = read_json(root / report_path)
        for key in ("base_commit", "resolved_dependencies", "behavioral_checks", "remaining_risks"):
            if key not in report:
                raise ValueError(f"conflict resolution report missing {key}")
    lock_path = root / "code/repos.lock.json"
    lock = read_json(lock_path)
    repos = lock.setdefault("repositories", [])
    if any(item.get("url") == payload["url"] and item.get("commit") == commit for item in repos):
        raise ValueError("repository already registered")
    repos.append({
        **payload,
        "url": redact_secrets(str(payload["url"])),
        "commit": observed_commit,
        "observed_remote": redact_secrets(observed_remote),
        "checkout_clean": not dirty,
        "registered_at": now(),
    })
    lock["lock_hash"] = sha256_json(repos)
    write_json(lock_path, lock)
    state = load_state(root)
    if len(repos) > 1 or state["gates"].get("G4"):
        invalidate(state, "REPOSITORY_CHANGED", payload["url"])
    save_state(root, state, "repository_registered", {"url": payload["url"], "commit": commit})


def lock_environment(root: Path, payload: dict[str, Any]) -> None:
    required = ["os", "python", "framework", "dependencies", "hardware"]
    missing = [key for key in required if not payload.get(key)]
    if missing:
        raise ValueError(f"environment missing fields: {missing}")
    record = {"schema_version": SCHEMA_VERSION, "status": "LOCKED", "environment": payload, "locked_at": now()}
    record["lock_hash"] = sha256_json(payload)
    old = read_json(root / "environment/environment.lock.json")
    write_json(root / "environment/environment.lock.json", record)
    state = load_state(root)
    if old.get("lock_hash") and old.get("lock_hash") != record["lock_hash"]:
        invalidate(state, "ENVIRONMENT_CHANGED", "environment lock changed")
    save_state(root, state, "environment_locked", {"lock_hash": record["lock_hash"]})


def register_run(root: Path, payload: dict[str, Any]) -> str:
    state = load_state(root)
    required = [
        "run_type", "command", "replicate_id", "config", "input_artifact_hashes",
        "protocol_hash", "status", "failure_class", "test_set_accessed",
    ]
    missing = [key for key in required if key not in payload]
    if missing:
        raise ValueError(f"run manifest missing fields: {missing}")
    if payload["failure_class"] not in FAILURES:
        raise ValueError(f"invalid failure_class: {payload['failure_class']}")
    if payload["run_type"] not in RUN_TYPES:
        raise ValueError(f"invalid run_type: {payload['run_type']}")
    if not isinstance(payload["input_artifact_hashes"], dict) or not payload["input_artifact_hashes"]:
        raise ValueError("run input_artifact_hashes must be a non-empty object")
    invalid_hashes = [
        key for key, value in payload["input_artifact_hashes"].items()
        if not key or not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", value)
    ]
    if invalid_hashes:
        raise ValueError(f"run input artifacts require SHA-256 hashes: {invalid_hashes}")
    if not isinstance(payload["protocol_hash"], str) or not re.fullmatch(r"[0-9a-fA-F]{64}", payload["protocol_hash"]):
        raise ValueError("run protocol_hash must be SHA-256")
    if not state["active"].get("idea_id") or not state["active"].get("research_program_id"):
        raise ValueError("formal runs require active Idea and frozen research program")
    if state["profile"] == "proposal" and payload["run_type"] in {"baseline", "pilot", "full", "revalidation"}:
        raise ValueError("proposal profile cannot register executable empirical runs")
    if state["profile"] == "exploratory" and payload["run_type"] in {"full", "revalidation"}:
        raise ValueError("exploratory profile cannot register confirmatory full/revalidation runs")
    program_id = state["active"]["research_program_id"]
    contract = read_json(root / f"contracts/{program_id}.json")
    unit_ids = payload.get("evaluation_unit_ids")
    if not isinstance(unit_ids, list) or not unit_ids:
        raise ValueError("run manifest requires evaluation_unit_ids from the frozen research program")
    known_units = {item.get("unit_id") for item in contract.get("evaluation_units", []) if isinstance(item, dict)}
    unknown_units = sorted(set(unit_ids) - known_units)
    if unknown_units:
        raise ValueError(f"run references unknown evaluation units: {unknown_units}")
    branch_id = payload.get("branch_id")
    if branch_id:
        registry = read_json(root / "experiments/branch-registry.json")
        branch = next((item for item in registry.get("branches", []) if item.get("branch_id") == branch_id), None)
        if not branch or branch.get("status") not in {"PROPOSED", "EXECUTING"}:
            raise ValueError(f"run branch_id is unknown or closed: {branch_id}")
        if branch.get("idea_id") != state["active"].get("idea_id") or branch.get("research_program_id") != program_id:
            raise ValueError("run branch belongs to a stale Idea or research program")
        if not set(payload.get("evaluation_unit_ids") or []).issubset(set(branch.get("evaluation_unit_ids") or [])):
            raise ValueError("run evaluation_unit_ids exceed the branch authorization")
    experiment_state_path = root / "experiments/state.json"
    experiment_state = read_json(experiment_state_path)
    max_runs = int((contract.get("resource_plan") or {}).get("max_runs", 0) or 0)
    if max_runs and experiment_state.get("runs_registered", 0) >= max_runs:
        raise ValueError(f"experiment run budget exhausted ({max_runs})")
    max_test = int((contract.get("test_set_policy") or {}).get("max_test_access", (contract.get("test_set_policy") or {}).get("max_access", 0)) or 0)
    if payload.get("test_set_accessed") and max_test and experiment_state.get("test_accesses", 0) >= max_test:
        raise ValueError(f"test-set access budget exhausted ({max_test})")
    repos = read_json(root / "code/repos.lock.json")
    env = read_json(root / "environment/environment.lock.json")
    locked_execution = ((env.get("environment") or {}).get("execution") or {}) \
        if isinstance(env.get("environment"), dict) else {}
    if locked_execution:
        execution_mismatches = [
            key for key, payload_key in (
                ("backend", "execution_backend"),
                ("target", "execution_target"),
                ("fingerprint", "execution_environment_fingerprint"),
            )
            if payload.get(payload_key) != locked_execution.get(key)
        ]
        if execution_mismatches:
            raise ValueError(f"run execution does not match environment lock: {execution_mismatches}")
    elif payload.get("execution_backend") == "remote":
        raise ValueError("remote run requires an execution-aware remote environment lock")
    run_id = f"run-{len(list((root / 'experiments/runs').glob('run-*'))) + 1:04d}"
    run_dir = root / f"experiments/runs/{run_id}"
    manifest = dict(payload)
    manifest["command_hash"] = hashlib.sha256(str(payload["command"]).encode("utf-8")).hexdigest()
    manifest["command"] = redact_secrets(str(payload["command"]))
    manifest.update({
        "schema_version": SCHEMA_VERSION, "run_id": run_id, "idea_id": state["active"]["idea_id"],
        "research_program_id": program_id, "repository_lock_hash": repos.get("lock_hash"),
        "environment_lock_hash": env.get("lock_hash"), "config_hash": sha256_json(payload["config"]),
        "created_at": now(),
    })
    if payload["run_type"] in {"baseline", "pilot", "full", "revalidation"} and (not repos.get("lock_hash") or not env.get("lock_hash")):
        raise ValueError("baseline/pilot/full/revalidation runs require repository and environment locks")
    write_json(run_dir / "run_manifest.json", manifest)
    if branch_id:
        for item in registry["branches"]:
            if item.get("branch_id") == branch_id:
                item["status"] = "EXECUTING"
                item.setdefault("run_ids", []).append(run_id)
        write_json(root / "experiments/branch-registry.json", registry)
    if payload.get("test_set_accessed"):
        append_jsonl(root / "experiments/test_access_log.jsonl", {"at": now(), "run_id": run_id, "idea_id": manifest["idea_id"], "research_program_id": manifest["research_program_id"], "purpose": payload.get("test_access_purpose", "unspecified")})
        experiment_state["test_accesses"] = experiment_state.get("test_accesses", 0) + 1
    experiment_state["runs_registered"] = experiment_state.get("runs_registered", 0) + 1
    failure = payload["failure_class"]
    experiment_state.setdefault("failures", {})[failure] = experiment_state.setdefault("failures", {}).get(failure, 0) + 1
    write_json(experiment_state_path, experiment_state)
    save_state(root, state, "run_registered", {"run_id": run_id, "run_type": payload["run_type"], "failure_class": payload["failure_class"]})
    return run_id


def propose_branch(root: Path, payload: dict[str, Any]) -> str:
    required = [
        "question", "change_class", "hypothesis", "evaluation_unit_ids", "expected_observations",
        "rationale", "estimated_cost", "evidence", "stop_condition",
    ]
    missing = [key for key in required if key not in payload or payload[key] in (None, "", [])]
    if missing:
        raise ValueError(f"branch proposal missing fields: {missing}")
    if payload["change_class"] not in {"debug_repair", "implementation", "protocol", "idea", "diagnostic"}:
        raise ValueError("invalid branch change_class")
    state = load_state(root)
    program_id = state["active"].get("research_program_id")
    if not program_id:
        raise ValueError("branching requires a frozen research program")
    contract = read_json(root / f"contracts/{program_id}.json")
    known_units = {item.get("unit_id") for item in contract.get("evaluation_units", []) if isinstance(item, dict)}
    unknown = sorted(set(payload["evaluation_unit_ids"]) - known_units)
    if unknown:
        raise ValueError(f"branch references unknown evaluation units: {unknown}")
    missing_evidence = [item for item in payload["evidence"] if not (root / item).is_file()]
    if missing_evidence:
        raise ValueError(f"branch evidence missing: {missing_evidence}")
    registry_path = root / "experiments/branch-registry.json"
    registry = read_json(registry_path)
    branches = registry.setdefault("branches", [])
    budget = contract["resource_plan"]
    if len(branches) >= budget["max_branches"]:
        raise ValueError("contract branch budget exhausted")
    parent_id = payload.get("parent_branch_id")
    parent = next((item for item in branches if item.get("branch_id") == parent_id), None) if parent_id else None
    if parent_id and (not parent or parent.get("status") != "EVALUATED"):
        raise ValueError("parent branch must exist and be evaluated")
    depth = int(parent.get("depth", 0) + 1) if parent else 0
    if depth > budget["max_branch_depth"]:
        raise ValueError("contract branch depth exhausted")
    signature = sha256_json({
        "parent": parent_id, "question": payload["question"], "change_class": payload["change_class"],
        "hypothesis": payload["hypothesis"], "evaluation_unit_ids": sorted(payload["evaluation_unit_ids"]),
    })
    if any(item.get("signature") == signature for item in branches):
        raise ValueError("duplicate scientific branch without a material state change")
    branch_id = f"BR-{len(branches) + 1:03d}"
    branch = {
        **payload, "branch_id": branch_id, "parent_branch_id": parent_id, "depth": depth,
        "idea_id": state["active"].get("idea_id"), "research_program_id": program_id,
        "signature": signature, "status": "PROPOSED", "run_ids": [],
        "evidence_hashes": {item: sha256_file(root / item) for item in payload["evidence"]},
        "created_at": now(),
    }
    branches.append(branch)
    write_json(registry_path, registry)
    save_state(root, state, "branch_proposed", {"branch_id": branch_id, "change_class": payload["change_class"]})
    return branch_id


def evaluate_branch(root: Path, branch_id: str, payload: dict[str, Any]) -> None:
    required = ["outcome", "scientific_interpretation", "decision", "claim_implications", "evidence", "reviewer", "limitations"]
    missing = [key for key in required if key not in payload or payload[key] in (None, "", [])]
    if missing:
        raise ValueError(f"branch evaluation missing fields: {missing}")
    if payload["outcome"] not in {"SUPPORTED", "PARTIAL", "UNSUPPORTED", "INCONCLUSIVE", "INVALID"}:
        raise ValueError("invalid branch outcome")
    decisions = {"PROMOTE", "REJECT", "RETAIN_DIAGNOSTIC", "REVISE_CONTRACT", "EVOLVE_IDEA", "STOP"}
    if payload["decision"] not in decisions:
        raise ValueError("invalid branch decision")
    registry_path = root / "experiments/branch-registry.json"
    registry = read_json(registry_path)
    branch = next((item for item in registry.get("branches", []) if item.get("branch_id") == branch_id), None)
    if not branch or branch.get("status") not in {"EXECUTING", "PROPOSED"}:
        raise ValueError("branch is unknown or already evaluated")
    if not branch.get("run_ids"):
        raise ValueError("branch evaluation requires at least one branch-bound run")
    run_paths = [root / f"experiments/runs/{run_id}/run_manifest.json" for run_id in branch["run_ids"]]
    if any(not path.is_file() for path in run_paths):
        raise ValueError("branch run manifest is missing")
    if branch["change_class"] == "protocol" and payload["decision"] not in {"REVISE_CONTRACT", "REJECT", "STOP"}:
        raise ValueError("protocol branches cannot be promoted under the unchanged contract")
    if branch["change_class"] == "idea" and payload["decision"] not in {"EVOLVE_IDEA", "REJECT", "STOP"}:
        raise ValueError("Idea branches require explicit Idea evolution, rejection, or stop")
    if payload["decision"] == "PROMOTE" and payload["outcome"] not in {"SUPPORTED", "PARTIAL"}:
        raise ValueError("only supported or partially supported branches can be promoted")
    missing_evidence = [item for item in payload["evidence"] if not (root / item).is_file()]
    if missing_evidence:
        raise ValueError(f"branch evaluation evidence missing: {missing_evidence}")
    branch["evaluation"] = {
        **payload,
        "evidence_hashes": {item: sha256_file(root / item) for item in payload["evidence"]},
        "evaluated_at": now(),
    }
    branch["status"] = "EVALUATED"
    write_json(registry_path, registry)
    state = load_state(root)
    if payload["decision"] == "PROMOTE" and branch["change_class"] in {"debug_repair", "implementation"}:
        invalidate(state, "IMPLEMENTATION_CHANGED", f"promoted {branch_id}")
    save_state(root, state, "branch_evaluated", {"branch_id": branch_id, "outcome": payload["outcome"], "decision": payload["decision"]})


def record_evidence(root: Path, payload: dict[str, Any]) -> None:
    required = ["source_artifacts", "derived_artifact", "supports", "evidence_type"]
    missing = [key for key in required if not payload.get(key)]
    if missing:
        raise ValueError(f"evidence missing fields: {missing}")
    missing_paths = [item for item in payload["source_artifacts"] if not (root / item).exists()]
    if missing_paths:
        raise ValueError(f"evidence source artifacts do not exist: {missing_paths}")
    derived = root / payload["derived_artifact"]
    if not derived.exists() or not derived.is_file():
        raise ValueError(f"derived evidence artifact does not exist: {payload['derived_artifact']}")
    record = {
        **payload,
        "recorded_at": now(),
        "source_hashes": {item: sha256_file(root / item) for item in payload["source_artifacts"]},
        "derived_hash": sha256_file(derived),
    }
    append_jsonl(root / "evidence/evidence-index.jsonl", record)
    state = load_state(root)
    save_state(root, state, "evidence_recorded", {"derived_artifact": payload["derived_artifact"]})


def gate_is_required(state: dict[str, Any], gate: str) -> bool:
    return any(gate in required_gates_for(state["profile"], phase) for phase in phase_sequence(state["profile"]))


def not_applicable_allowed(root: Path, state: dict[str, Any], gate: str) -> bool:
    if not gate_is_required(state, gate):
        return True
    if gate == "G6":
        decision = read_json(root / "grounding/benchmark_candidates.json").get("decision", {})
        return decision.get("classification") in {
            "INAPPLICABLE", "NO_PUBLIC_BENCHMARK", "ACCESS_BLOCKED", "LICENSE_BLOCKED",
            "NO_VALID_PUBLIC_BENCHMARK", "ADJACENT_BENCHMARK_ONLY", "BENCHMARK_INCOMPATIBLE",
        }
    if gate == "G12" and state["profile"] == "exploratory":
        return True
    if gate == "G14" and state["profile"] == "standard_empirical":
        contract = read_json(root / f"contracts/{state['active']['research_program_id']}.json")
        return (contract.get("revalidation_policy") or {}).get("required") is False
    return False


def validate_judgment(root: Path, state: dict[str, Any], gate: str, verdict: str, judgment: str | None) -> tuple[str, str, set[str]]:
    if gate not in MODEL_JUDGMENT_GATES:
        if judgment:
            raise ValueError(f"{gate} is deterministic and does not accept a scientific judgment artifact")
        return "", "", set()
    if not judgment:
        raise ValueError(f"{gate} requires a structured main-model scientific judgment artifact")
    path = root / judgment
    report = read_json(path)
    required = ["artifact_type", "gate", "verdict", "conclusion", "checks", "limitations", "reviewer"]
    missing = [key for key in required if key not in report or report[key] in (None, "", [])]
    if missing:
        raise ValueError(f"scientific judgment missing fields: {missing}")
    if report["artifact_type"] != "scientific_judgment" or report["gate"] != gate or report["verdict"] != verdict:
        raise ValueError("scientific judgment identity/verdict does not match the gate request")
    reviewer = report["reviewer"]
    if not isinstance(reviewer, dict) or not reviewer.get("id") or not reviewer.get("model_or_human"):
        raise ValueError("scientific judgment requires reviewer.id and reviewer.model_or_human")
    context_artifacts = reviewer.get("context_artifacts")
    if not isinstance(context_artifacts, list) or not context_artifacts:
        raise ValueError("scientific judgment requires the minimal context_artifacts seen by the reviewer")
    if state["profile"] == "high_risk" and gate in HIGH_RISK_INDEPENDENT_GATES and reviewer.get("independent") is not True:
        raise ValueError(f"high-risk {gate} requires an independent reviewer")
    if state["profile"] == "high_risk" and gate == "G16":
        confirmation = approval_record(state, report.get("human_confirmation_approval_id"))
        if (
            not confirmation
            or confirmation.get("decision") != "APPROVED"
            or confirmation.get("actor") != "user"
            or confirmation.get("action") != "CONFIRM_RELEASE"
            or confirmation.get("scope") != state["active"].get("idea_id")
        ):
            raise ValueError("high-risk G16 requires a user CONFIRM_RELEASE approval scoped to the active Idea")
        if not set(context_artifacts).intersection(confirmation.get("evidence", [])):
            raise ValueError("high-risk release confirmation must bind at least one reviewed context artifact")
    checks = report["checks"]
    if not isinstance(checks, list) or not checks:
        raise ValueError("scientific judgment checks must be a non-empty list")
    referenced: set[str] = set(context_artifacts)
    for index, check in enumerate(checks):
        if not isinstance(check, dict):
            raise ValueError(f"scientific judgment check {index} must be an object")
        missing_check = [key for key in ("question", "verdict", "rationale", "evidence") if not check.get(key)]
        if missing_check:
            raise ValueError(f"scientific judgment check {index} missing fields: {missing_check}")
        if check["verdict"] not in {"SUPPORTED", "PARTIAL", "UNSUPPORTED", "UNCERTAIN", "NOT_APPLICABLE"}:
            raise ValueError(f"scientific judgment check {index} has invalid verdict")
        if not isinstance(check["evidence"], list):
            raise ValueError(f"scientific judgment check {index}.evidence must be a list")
        referenced.update(check["evidence"])
    missing_artifacts = sorted(item for item in referenced if not (root / item).is_file())
    if missing_artifacts:
        raise ValueError(f"scientific judgment references missing artifacts: {missing_artifacts}")
    if verdict == "NOT_APPLICABLE":
        if not report.get("applicability_rationale") or not report.get("counterfactual_trigger"):
            raise ValueError("NOT_APPLICABLE judgment requires applicability_rationale and counterfactual_trigger")
    if report.get("blocking_issues") and verdict in PASSING:
        raise ValueError("a passing scientific judgment cannot retain blocking_issues")
    return judgment, sha256_file(path), referenced


def set_gate(
    root: Path,
    gate: str,
    verdict: str,
    evidence: list[str],
    summary: str,
    reviewer: str,
    judgment: str | None = None,
) -> None:
    if gate not in GATES:
        raise ValueError(f"unknown gate: {gate}")
    if verdict not in PASSING | {"FAIL", "BLOCKED", "AUTHOR_REQUIRED"}:
        raise ValueError("invalid gate verdict")
    if not evidence:
        raise ValueError("gate verdict requires evidence artifacts")
    missing = [item for item in evidence if not (root / item).exists()]
    if missing:
        raise ValueError(f"gate evidence does not exist: {missing}")
    state = load_state(root)
    if verdict == "NOT_APPLICABLE" and not not_applicable_allowed(root, state, gate):
        raise ValueError(f"{gate} cannot be NOT_APPLICABLE for profile {state['profile']}")
    judgment_path, judgment_hash, judgment_evidence = validate_judgment(root, state, gate, verdict, judgment)
    check_gate_preconditions(root, state, gate, verdict, evidence, judgment_evidence)
    report = {
        "schema_version": SCHEMA_VERSION, "gate": gate, "name": GATES[gate], "verdict": verdict,
        "summary": summary, "reviewer": reviewer, "evidence": evidence,
        "evidence_hashes": {item: sha256_file(root / item) for item in evidence},
        "judgment": judgment_path or None,
        "judgment_hash": judgment_hash or None,
        "evaluated_at": now(),
    }
    report_path = root / f"reports/gates/{gate}.json"
    write_json(report_path, report)
    state["gates"][gate] = {"verdict": verdict, "report": str(report_path.relative_to(root)), "evaluated_at": report["evaluated_at"]}
    state["blockers"] = [item for item in state.get("blockers", []) if item.get("gate") != gate]
    if verdict not in PASSING:
        state["blockers"].append({"gate": gate, "verdict": verdict, "summary": summary, "at": now()})
    save_state(root, state, "gate_evaluated", {"gate": gate, "verdict": verdict})


def transition(root: Path, target: str) -> None:
    state = load_state(root)
    if target in TERMINAL_PHASES:
        raise ValueError("terminal states require the stop command with evidence")
    sequence = phase_sequence(state["profile"])
    if target not in sequence:
        raise ValueError(f"phase {target} is not part of profile {state['profile']}")
    current_idx = sequence.index(state["phase"]) if state["phase"] in sequence else -1
    target_idx = sequence.index(target)
    if target_idx != current_idx + 1:
        raise ValueError(f"transitions must be sequential: {state['phase']} -> {target} is illegal")
    missing = []
    for gate in required_gates_for(state["profile"], target):
        if state["gates"].get(gate, {}).get("verdict") not in PASSING:
            missing.append(gate)
    if missing:
        raise ValueError(f"cannot enter {target}; unresolved gates: {missing}")
    check_transition_artifacts(root, state, target)
    state["phase"] = target
    save_state(root, state, "phase_transition", {"target": target})


def check_transition_artifacts(root: Path, state: dict[str, Any], target: str) -> None:
    active = state["active"]
    requirements = {
        "USER_POLICY_LOCKED": ("user_policy_id", "intake/{value}.json"),
        "SCIENCE_PROFILED": ("science_profile_id", "calibration/{value}.json"),
        "VENUE_PROFILED": ("venue_profile_id", "calibration/{value}.json"),
        "IDEA_DRAFTED": ("idea_id", "ideas/{value}.json"),
        "RESEARCH_CONTRACT_FROZEN": ("research_program_id", "contracts/{value}.json"),
        "PUBLICATION_CONTRACT_FROZEN": ("publication_contract_id", "contracts/{value}.json"),
        "CITATIONS_COMPLETE": ("bibliography_coverage", "{value}"),
        "MANUSCRIPT_DRAFTED": ("manuscript_id", "manuscript/{value}.json"),
        "FIGURES_COMPLETE": ("figure_routing", "{value}"),
        "RELEASE_AUDITED": ("release_audit_id", "reports/release/{value}.json"),
        "RELEASED": ("release_audit_id", "reports/release/{value}.json"),
    }
    if target in requirements:
        key, pattern = requirements[target]
        value = active.get(key)
        if not value or not (root / pattern.format(value=value)).is_file():
            raise ValueError(f"cannot enter {target}; active {key} artifact is missing")
    if target == "SCIENCE_PROFILED":
        seed_id = active.get("idea_seed_id")
        if not seed_id or not (root / f"intake/{seed_id}.json").is_file():
            raise ValueError("cannot enter SCIENCE_PROFILED; active Idea seed is missing")
    if target == "VENUE_PROFILED":
        for key in ("venue_corpus_id", "venue_profile_judgment_id"):
            value = active.get(key)
            if not value or not (root / f"calibration/{value}.json").is_file():
                raise ValueError(f"cannot enter VENUE_PROFILED; active {key} artifact is missing")
    if target == "IDEA_DRAFTED":
        for key in ("idea_seed_id", "idea_candidates_id", "idea_selection_id"):
            value = active.get(key)
            directory = "intake" if key == "idea_seed_id" else "discovery"
            if not value or not (root / directory / f"{value}.json").is_file():
                raise ValueError(f"cannot enter IDEA_DRAFTED; active {key} artifact is missing")
    if target in SCHEDULE_CHECKPOINT_PHASES:
        checkpoint_relative = active.get("schedule_checkpoint")
        if not checkpoint_relative or not (root / checkpoint_relative).is_file():
            raise ValueError(f"cannot enter {target}; a current schedule checkpoint is required")
        checkpoint = read_json(root / checkpoint_relative)
        program_id = active.get("research_program_id")
        program_path = root / f"contracts/{program_id}.json" if program_id else None
        if checkpoint.get("next_phase") != target:
            raise ValueError(f"cannot enter {target}; latest schedule checkpoint targets {checkpoint.get('next_phase')}")
        if not program_path or not program_path.is_file() or checkpoint.get("research_program_hash") != sha256_file(program_path):
            raise ValueError(f"cannot enter {target}; schedule checkpoint research program binding is stale")
        if checkpoint.get("deadline_fit") is not True or checkpoint.get("replan_required") is not False:
            raise ValueError(f"cannot enter {target}; schedule checkpoint requires replan before continuing")
    if target == "USER_POLICY_LOCKED" and state["profile"] != "proposal":
        envelope = root / "intake/resource-envelope.json"
        if not envelope.is_file() or read_json(envelope).get("confirmed_by_user") is not True:
            raise ValueError("empirical user policy lock requires a user-confirmed resource envelope")
    if target == "MANUSCRIPT_REFINED":
        report = read_json(root / "reports/manuscript/refinement-report.json")
        required = ["input_manuscript_id", "input_manuscript_hash", "issues_addressed", "claim_preservation", "reviewer"]
        missing = [key for key in required if key not in report or report[key] in (None, "")]
        if missing:
            raise ValueError(f"refinement report missing fields: {missing}")
    if target == "LATEX_COMPILED":
        report = read_json(root / "reports/manuscript/latex-verdict.json")
        required = ["compiled", "error_count", "input_hash", "pdf", "pdf_sha256"]
        missing = [key for key in required if key not in report or report[key] in (None, "")]
        if missing:
            raise ValueError(f"LaTeX verdict missing fields: {missing}")
        if report.get("compiled") is not True or report.get("error_count") != 0:
            raise ValueError("LATEX_COMPILED requires compiled=true and error_count=0")
        pdf = root / report["pdf"]
        if not pdf.is_file() or sha256_file(pdf) != report["pdf_sha256"]:
            raise ValueError("LaTeX verdict PDF is missing or hash-mismatched")


def invalidate(state: dict[str, Any], change: str, reason: str) -> None:
    publication_gates = ["M1", "M2", "M3", "M4", "G16", "M5", "M6"]
    reset = {
        "USER_POLICY_CHANGED": ("INTAKE", list(GATES)),
        "IDEA_SEED_CHANGED": ("USER_POLICY_LOCKED", ["G1", "G2", "G3"] + publication_gates),
        "SCIENCE_PROFILE_CHANGED": ("USER_POLICY_LOCKED", ["V1", "G1", "G2", "G3"] + publication_gates),
        "VENUE_CORPUS_CHANGED": ("SCIENCE_PROFILED", ["V1", "G2", "G3"] + publication_gates),
        "VENUE_PROFILE_CHANGED": ("SCIENCE_PROFILED", ["V1", "G2", "G3"] + publication_gates),
        "VENUE_JUDGMENT_CHANGED": ("SCIENCE_PROFILED", ["V1", "G2", "G3"] + publication_gates),
        "IDEA_EDITORIAL_CHANGED": ("CLAIMS_RECONCILED", publication_gates),
        "IDEA_SCOPE_CHANGED": ("IDEA_GROUNDED", ["G3", "G9", "G10", "G11", "G12", "G13", "G14", "G15"] + publication_gates),
        "IDEA_ESTIMAND_CHANGED": ("IDEA_GROUNDED", ["G3", "G6", "G7", "G8", "G9", "G10", "G11", "G12", "G13", "G14", "G15"] + publication_gates),
        "IDEA_CORE_CHANGED": ("VENUE_PROFILED", ["G1", "G2", "G3", "G6", "G7", "G8", "G9", "G10", "G11", "G12", "G13", "G14", "G15"] + publication_gates),
        "PROTOCOL_CHANGED": ("IDEA_GROUNDED", ["G3", "G6", "G7", "G8", "G9", "G10", "G11", "G12", "G13", "G14", "G15"] + publication_gates),
        "RESOURCE_ENVELOPE_CHANGED": ("USER_POLICY_LOCKED", ["V1", "G2", "G3", "G6", "G7", "G8", "G9", "G10", "G11", "G12", "G13", "G14", "G15"] + publication_gates),
        "REPOSITORY_CHANGED": ("RESEARCH_CONTRACT_FROZEN", ["G4", "G6", "G7", "G8", "G9", "G10", "G11", "G12", "G13", "G14", "G15"] + publication_gates),
        "IMPLEMENTATION_CHANGED": ("BASELINE_VERIFIED", ["G7", "G8", "G9", "G10", "G11", "G12", "G13", "G14", "G15"] + publication_gates),
        "ENVIRONMENT_CHANGED": ("CODEBASE_LOCKED", ["G5", "G6", "G7", "G8", "G9", "G10", "G11", "G12", "G13", "G14", "G15"] + publication_gates),
        "TEST_CONTAMINATED": ("MECHANISM_DIAGNOSED", ["G13", "G14", "G15"] + publication_gates),
        "PUBLICATION_CONTRACT_CHANGED": ("CLAIMS_RECONCILED", publication_gates),
        "BIBLIOGRAPHY_COVERAGE_CHANGED": ("PUBLICATION_CONTRACT_FROZEN", ["M2", "M3", "M4", "G16", "M5", "M6"]),
        "FIGURE_ROUTING_CHANGED": ("MANUSCRIPT_HARDENED", ["M5", "M6"]),
        "LATEX_VERDICT_CHANGED": ("FIGURES_COMPLETE", ["M6"]),
        "MANUSCRIPT_CHANGED": ("CITATIONS_COMPLETE", ["M3", "M4", "G16", "M5", "M6"]),
    }
    if change not in reset:
        raise ValueError(f"unknown invalidation change: {change}")
    phase, gates = reset[change]
    sequence = phase_sequence(state["profile"])
    if phase not in sequence:
        global_index = PHASES.index(phase)
        phase = max((item for item in sequence if PHASES.index(item) <= global_index), key=PHASES.index)
    for gate in gates:
        state["gates"].pop(gate, None)
    if state["phase"] in sequence and sequence.index(state["phase"]) > sequence.index(phase):
        state["phase"] = phase
    state["invalidations"].append({"at": now(), "change": change, "reason": reason, "reset_phase": phase, "invalidated_gates": gates})


def explicit_invalidate(root: Path, change: str, reason: str) -> None:
    state = load_state(root)
    invalidate(state, change, reason)
    save_state(root, state, "artifacts_invalidated", {"change": change, "reason": reason})


def record_decision(root: Path, payload: dict[str, Any]) -> str:
    required = ["decision", "rationale", "evidence", "approval"]
    missing = [key for key in required if not payload.get(key)]
    if missing:
        raise ValueError(f"decision missing fields: {missing}")
    if payload["decision"] not in IDEA_DECISIONS:
        raise ValueError(f"invalid idea decision: {payload['decision']}")
    level = payload.get("revision_level", "L0")
    if level in {"L2", "L3", "L4"} and not approval_valid(load_state(root), payload.get("approval")):
        raise ValueError(f"{level} Idea decision requires a recorded approval ID")
    missing_evidence = [item for item in payload["evidence"] if not (root / item).exists()]
    if missing_evidence:
        raise ValueError(f"decision evidence missing: {missing_evidence}")
    decision_id = f"DR-{len(list((root / 'decisions').glob('DR-*.json'))) + 1:03d}"
    record = {**payload, "decision_id": decision_id, "created_at": now()}
    write_json(root / f"decisions/{decision_id}.json", record)
    state = load_state(root)
    save_state(root, state, "idea_decision_recorded", {"decision_id": decision_id, "decision": payload["decision"]})
    return decision_id


def stop(root: Path, target: str, reason: str, evidence: list[str]) -> None:
    if target not in TERMINAL_PHASES:
        raise ValueError("stop target must be a terminal phase")
    if not evidence:
        raise ValueError("stop requires evidence")
    missing = [item for item in evidence if not (root / item).exists()]
    if missing:
        raise ValueError(f"stop evidence missing: {missing}")
    state = load_state(root)
    state["phase"] = target
    experiment_state = read_json(root / "experiments/state.json")
    experiment_state["stop_reason"] = {"phase": target, "reason": reason, "evidence": evidence, "at": now()}
    write_json(root / "experiments/state.json", experiment_state)
    save_state(root, state, "research_stopped", {"target": target, "reason": reason, "evidence": evidence})


def successful_runs(root: Path, run_type: str) -> list[dict[str, Any]]:
    result = []
    for path in (root / "experiments/runs").glob("run-*/run_manifest.json"):
        run = read_json(path)
        if run.get("run_type") == run_type and run.get("status") == "completed" and run.get("failure_class") == "NONE":
            result.append(run)
    return result


def validate_results_manifest(root: Path) -> None:
    path = root / "evidence/results/results-manifest.jsonl"
    if not path.is_file():
        raise ValueError("G11 requires evidence/results/results-manifest.jsonl")
    facts: list[dict[str, Any]] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            fact = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid results manifest line {line_number}: {exc}") from exc
        if not isinstance(fact, dict):
            raise ValueError(f"results manifest line {line_number} must be an object")
        facts.append(fact)
    if not facts:
        raise ValueError("results manifest must contain at least one fact")
    known_runs = {
        path.parent.name: read_json(path)
        for path in (root / "experiments/runs").glob("run-*/run_manifest.json")
    }
    state = load_state(root)
    active_claims = {
        item.get("claim_id") for item in read_json(root / "claims/claim-registry.json").get("claims", [])
        if item.get("active")
    }
    seen: set[str] = set()
    for index, fact in enumerate(facts):
        required = ["fact_id", "claim_ids", "value", "unit", "run_ids", "source_artifacts", "source_hashes", "aggregation"]
        missing = [key for key in required if key not in fact or fact[key] in (None, "", [])]
        if missing:
            raise ValueError(f"result fact {index} missing fields: {missing}")
        if fact["fact_id"] in seen:
            raise ValueError(f"duplicate result fact_id: {fact['fact_id']}")
        seen.add(fact["fact_id"])
        unknown_claims = [claim_id for claim_id in fact["claim_ids"] if claim_id not in active_claims]
        if unknown_claims:
            raise ValueError(f"result fact {fact['fact_id']} references unknown/inactive claims: {unknown_claims}")
        unknown_runs = [run_id for run_id in fact["run_ids"] if run_id not in known_runs]
        if unknown_runs:
            raise ValueError(f"result fact {fact['fact_id']} references unknown runs: {unknown_runs}")
        unsuccessful = [run_id for run_id in fact["run_ids"] if known_runs[run_id].get("status") != "completed"]
        if unsuccessful:
            raise ValueError(f"result fact {fact['fact_id']} references incomplete runs: {unsuccessful}")
        stale_runs = [
            run_id for run_id in fact["run_ids"]
            if not idea_evidence_compatible(root, known_runs[run_id].get("idea_id"), state["active"].get("idea_id"))
            or known_runs[run_id].get("research_program_id") != state["active"].get("research_program_id")
        ]
        if stale_runs:
            raise ValueError(f"result fact {fact['fact_id']} references stale runs: {stale_runs}")
        contract = read_json(root / f"contracts/{state['active']['research_program_id']}.json")
        unit_claims = {
            item.get("unit_id"): set(item.get("claim_ids") or [])
            for item in contract.get("evaluation_units", []) if isinstance(item, dict)
        }
        run_units = {
            unit_id
            for run_id in fact["run_ids"]
            for unit_id in known_runs[run_id].get("evaluation_unit_ids", [])
        }
        unsupported_links = [
            claim_id for claim_id in fact["claim_ids"]
            if not any(claim_id in unit_claims.get(unit_id, set()) for unit_id in run_units)
        ]
        if unsupported_links:
            raise ValueError(
                f"result fact {fact['fact_id']} has no claim-linked evaluation unit in its runs: {unsupported_links}"
            )
        if not isinstance(fact["source_hashes"], dict):
            raise ValueError(f"result fact {fact['fact_id']}.source_hashes must be an object")
        for artifact in fact["source_artifacts"]:
            artifact_path = root / artifact
            if not artifact_path.is_file():
                raise ValueError(f"result fact {fact['fact_id']} source missing: {artifact}")
            if fact["source_hashes"].get(artifact) != sha256_file(artifact_path):
                raise ValueError(f"result fact {fact['fact_id']} source hash mismatch: {artifact}")
        aggregation = fact["aggregation"]
        if not isinstance(aggregation, dict) or not aggregation.get("method") or not aggregation.get("code_artifact"):
            raise ValueError(f"result fact {fact['fact_id']} requires aggregation.method and code_artifact")
        code_path = root / aggregation["code_artifact"]
        if not code_path.is_file() or aggregation.get("code_hash") != sha256_file(code_path):
            raise ValueError(f"result fact {fact['fact_id']} aggregation code is missing or changed")


def require_report(
    root: Path,
    relative: str,
    gate_evidence: list[str],
    judgment_evidence: set[str],
    required: list[str],
    *,
    semantic: bool = True,
) -> dict[str, Any]:
    if relative not in gate_evidence:
        raise ValueError(f"gate evidence must include {relative}")
    if semantic and relative not in judgment_evidence:
        raise ValueError(f"scientific judgment must cite {relative}")
    report = read_json(root / relative)
    missing = [key for key in required if key not in report or report[key] in (None, "")]
    if missing:
        raise ValueError(f"{relative} missing fields: {missing}")
    return report


def require_artifact_refs(root: Path, values: Any, label: str) -> None:
    if not isinstance(values, list) or not values:
        raise ValueError(f"{label} must be a non-empty list")
    for value in values:
        if isinstance(value, str):
            path, expected = value, None
        elif isinstance(value, dict):
            path, expected = value.get("path"), value.get("sha256")
        else:
            raise ValueError(f"{label} entries must be paths or path/hash objects")
        if not path or not (root / path).is_file():
            raise ValueError(f"{label} artifact missing: {path}")
        if expected and expected != sha256_file(root / path):
            raise ValueError(f"{label} artifact hash mismatch: {path}")


def validate_verification_suite(root: Path, relative: str) -> None:
    script = Path(__file__).with_name("validate_verification_suite.py")
    spec = importlib.util.spec_from_file_location("verification_suite_validator", script)
    if spec is None or spec.loader is None:
        raise ValueError("verification suite validator cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    issues = module.validate(read_json(root / relative), root)
    if issues:
        raise ValueError("invalid verification suite: " + "; ".join(issues))


def check_gate_preconditions(
    root: Path,
    state: dict[str, Any],
    gate: str,
    verdict: str,
    gate_evidence: list[str],
    judgment_evidence: set[str],
) -> None:
    if verdict not in PASSING:
        return
    active_idea = state["active"].get("idea_id")
    active_contract = state["active"].get("research_program_id")
    active_manuscript = state["active"].get("manuscript_id")
    if gate == "G0":
        policy_id = state["active"].get("user_policy_id")
        if not policy_id or not (root / f"intake/{policy_id}.json").is_file():
            raise ValueError("G0 requires an active user policy")
        validate_user_policy(read_json(root / f"intake/{policy_id}.json"))
    elif gate == "V1":
        profile_id = state["active"].get("venue_profile_id")
        judgment_id = state["active"].get("venue_profile_judgment_id")
        if not profile_id or not judgment_id:
            raise ValueError("V1 requires an active venue profile and independent venue judgment")
        if not (root / f"calibration/{profile_id}.json").is_file() or not (root / f"calibration/{judgment_id}.json").is_file():
            raise ValueError("V1 venue profile or judgment artifact is missing")
        validate_venue_profile(root, read_json(root / f"calibration/{profile_id}.json"))
        judgment = read_json(root / f"calibration/{judgment_id}.json")
        if judgment.get("venue_profile_hash") != sha256_file(root / f"calibration/{profile_id}.json"):
            raise ValueError("V1 venue judgment is stale")
        required_evidence = {f"calibration/{profile_id}.json", f"calibration/{judgment_id}.json"}
        if not required_evidence.issubset(set(gate_evidence)):
            raise ValueError("V1 gate evidence must bind both venue profile and venue judgment")
    elif gate == "G1":
        if not active_idea:
            raise ValueError("G1 requires an active Idea")
        idea = read_json(root / f"ideas/{active_idea}.json")
        if not idea.get("falsifiers") or not idea.get("alternative_explanations"):
            raise ValueError("G1 requires falsifiers and alternative explanations")
    elif gate == "G2":
        relative = "grounding/benchmark_candidates.json"
        require_report(root, relative, gate_evidence, judgment_evidence, ["candidates", "decision"])
        validator_path = Path(__file__).with_name("validate_research_artifacts.py")
        spec = importlib.util.spec_from_file_location("research_artifact_validator", validator_path)
        if spec is None or spec.loader is None:
            raise ValueError("benchmark artifact validator cannot be loaded")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        issues: list[str] = []
        module.validate_benchmarks(read_json(root / relative), issues)
        if issues:
            raise ValueError("invalid benchmark search artifact: " + "; ".join(issues))
    elif gate == "G3" and not active_contract:
        raise ValueError("G3 requires an active frozen contract")
    elif gate == "G4":
        lock = read_json(root / "code/repos.lock.json")
        if not lock.get("repositories") or not lock.get("lock_hash"):
            raise ValueError("G4 requires at least one pinned repository")
    elif gate == "G5":
        env = read_json(root / "environment/environment.lock.json")
        if env.get("status") != "LOCKED" or not env.get("lock_hash"):
            raise ValueError("G5 requires a locked environment")
    elif gate == "G6" and verdict == "NOT_APPLICABLE":
        require_report(
            root, "grounding/benchmark_candidates.json", gate_evidence, judgment_evidence,
            ["candidates", "decision"],
        )
    elif gate == "G6":
        runs = successful_runs(root, "baseline")
        if not runs:
            raise ValueError("G6 requires a successful baseline run")
        report = require_report(root, "reports/experiments/baseline-reproduction.json", gate_evidence, judgment_evidence, [
            "baseline", "official_source", "expected_behavior", "expected_source", "run_ids",
            "actual_outputs", "comparison", "deviations", "limitations",
        ])
        known = {item["run_id"] for item in runs}
        if not set(report.get("run_ids") or []).issubset(known) or not report.get("run_ids"):
            raise ValueError("baseline reproduction must reference successful baseline run IDs")
        require_artifact_refs(root, report.get("actual_outputs"), "baseline actual_outputs")
    elif gate == "G7":
        report = require_report(root, "reports/code/implementation-review.json", gate_evidence, judgment_evidence, [
            "implementation_summary", "contract_alignment", "reviewed_artifacts", "risks",
            "findings", "limitations", "reviewer",
        ])
        require_artifact_refs(root, report.get("reviewed_artifacts"), "implementation reviewed_artifacts")
    elif gate == "G8":
        relative = "reports/code/verification-suite.json"
        require_report(root, relative, gate_evidence, judgment_evidence, ["selection_judgment", "tests"])
        validate_verification_suite(root, relative)
    elif gate == "G9" and verdict != "NOT_APPLICABLE":
        runs = successful_runs(root, "pilot")
        if not runs:
            raise ValueError("G9 requires a successful pilot run")
        report = require_report(root, "reports/experiments/pilot-assessment.json", gate_evidence, judgment_evidence, [
            "run_ids", "feasibility", "signal_assessment", "variance_assessment", "protocol_observations",
            "failure_modes", "budget_projection", "decision", "limitations",
        ])
        if not set(report.get("run_ids") or []).issubset({item["run_id"] for item in runs}) or not report.get("run_ids"):
            raise ValueError("pilot assessment must reference successful pilot run IDs")
    elif gate == "G10":
        runs = successful_runs(root, "full")
        if not runs:
            raise ValueError("G10 requires a successful full run")
        report = require_report(root, "reports/experiments/full-run-integrity.json", gate_evidence, judgment_evidence, [
            "authorized_run_ids", "research_program_id", "repository_lock_hash", "environment_lock_hash",
            "budget_check", "test_access_summary", "raw_outputs",
        ], semantic=False)
        run_ids = set(report.get("authorized_run_ids") or [])
        if not run_ids or not run_ids.issubset({item["run_id"] for item in runs}):
            raise ValueError("full-run integrity must reference successful full run IDs")
        if report.get("research_program_id") != active_contract:
            raise ValueError("full-run integrity research_program_id is stale")
        if report.get("repository_lock_hash") != read_json(root / "code/repos.lock.json").get("lock_hash"):
            raise ValueError("full-run integrity repository lock hash mismatch")
        if report.get("environment_lock_hash") != read_json(root / "environment/environment.lock.json").get("lock_hash"):
            raise ValueError("full-run integrity environment lock hash mismatch")
        require_artifact_refs(root, report.get("raw_outputs"), "full-run raw_outputs")
    elif gate == "G11":
        if not successful_runs(root, "full"):
            raise ValueError("G11 requires a successful full run")
        validate_results_manifest(root)
    elif gate == "G12" and verdict != "NOT_APPLICABLE":
        require_report(root, "reports/mechanism/mechanism-diagnosis.json", gate_evidence, judgment_evidence, [
            "mechanism_predictions", "observations", "alternative_explanations", "discriminating_evidence",
            "verdict", "claim_implications", "limitations",
        ])
    elif gate == "G13" and not list((root / "decisions").glob("DR-*.json")):
        raise ValueError("G13 requires a recorded Idea decision")
    elif gate == "G14" and verdict != "NOT_APPLICABLE":
        runs = successful_runs(root, "revalidation")
        if not runs:
            raise ValueError("G14 requires a successful independent revalidation run")
        report = require_report(root, "reports/experiments/independent-revalidation.json", gate_evidence, judgment_evidence, [
            "run_ids", "independence_dimensions", "compared_facts", "conclusion", "limitations",
        ])
        if not set(report.get("run_ids") or []).issubset({item["run_id"] for item in runs}) or not report.get("run_ids"):
            raise ValueError("revalidation report must reference successful revalidation run IDs")
        if not report.get("independence_dimensions"):
            raise ValueError("revalidation report must state concrete independence dimensions")
    elif gate == "G15":
        registry = read_json(root / "claims/claim-registry.json")
        unresolved = [item.get("claim_id") for item in registry.get("claims", []) if item.get("active") and item.get("support_status") == "UNVERIFIED"]
        if unresolved:
            raise ValueError(f"G15 has unresolved claims: {unresolved}")
        if "claims/claim-registry.json" not in gate_evidence or "claims/claim-registry.json" not in judgment_evidence:
            raise ValueError("G15 judgment and gate evidence must bind claims/claim-registry.json")
    elif gate == "G16":
        manuscript_id = state["active"].get("manuscript_id")
        if not manuscript_id or not (root / f"manuscript/{manuscript_id}.json").exists():
            raise ValueError("G16 requires a registered active manuscript artifact")
    elif gate == "M1":
        publication_id = state["active"].get("publication_contract_id")
        if not publication_id or not (root / f"contracts/{publication_id}.json").is_file():
            raise ValueError("M1 requires an active frozen publication contract")
    elif gate == "M2":
        coverage = state["active"].get("bibliography_coverage")
        if not coverage or not (root / coverage).is_file():
            raise ValueError("M2 requires registered bibliography coverage")
    elif gate == "M3":
        if not active_manuscript or not (root / f"manuscript/{active_manuscript}.json").is_file():
            raise ValueError("M3 requires a complete registered manuscript")
    elif gate == "M4":
        require_report(root, "reports/manuscript/refinement-report.json", gate_evidence, judgment_evidence, [
            "input_manuscript_id", "input_manuscript_hash", "issues_addressed", "claim_preservation", "reviewer",
        ], semantic=False)
    elif gate == "M5":
        routing = state["active"].get("figure_routing")
        if not routing or not (root / routing).is_file():
            raise ValueError("M5 requires registered figure routing")
        require_report(root, "reports/manuscript/figure-program-report.json", gate_evidence, judgment_evidence, [
            "publication_contract_id", "expected_figure_ids", "completed_figure_ids", "route_validation", "visual_review", "reviewer",
        ], semantic=False)
    elif gate == "M6":
        audit_id = state["active"].get("release_audit_id")
        if not audit_id or not (root / f"reports/release/{audit_id}.json").is_file():
            raise ValueError("M6 requires a registered release audit")


def validate_root(root: Path) -> list[str]:
    errors: list[str] = []
    try:
        state = load_state(root)
    except ValueError as exc:
        return [str(exc)]
    active_idea = state["active"].get("idea_id")
    active_contract = state["active"].get("research_program_id")
    active_manuscript = state["active"].get("manuscript_id")
    if active_idea and not (root / f"ideas/{active_idea}.json").exists():
        errors.append(f"active idea missing: {active_idea}")
    if active_contract and not (root / f"contracts/{active_contract}.json").exists():
        errors.append(f"active contract missing: {active_contract}")
    active_paths = {
        "user_policy_id": "intake/{value}.json",
        "idea_seed_id": "intake/{value}.json",
        "memory_snapshot_id": "memory/{value}.json",
        "science_profile_id": "calibration/{value}.json",
        "venue_corpus_id": "calibration/{value}.json",
        "venue_profile_id": "calibration/{value}.json",
        "venue_profile_judgment_id": "calibration/{value}.json",
        "idea_candidates_id": "discovery/{value}.json",
        "idea_selection_id": "discovery/{value}.json",
        "research_program_id": "contracts/{value}.json",
        "publication_contract_id": "contracts/{value}.json",
        "bibliography_coverage": "{value}",
        "figure_routing": "{value}",
        "publication_judgment_id": "reports/manuscript/{value}.json",
        "schedule_checkpoint": "{value}",
        "release_audit_id": "reports/release/{value}.json",
    }
    for key, pattern in active_paths.items():
        value = state["active"].get(key)
        if value and not (root / pattern.format(value=value)).is_file():
            errors.append(f"active {key} artifact missing: {value}")
    policy_id = state["active"].get("user_policy_id")
    if policy_id:
        try:
            validate_user_policy(read_json(root / f"intake/{policy_id}.json"))
        except ValueError as exc:
            errors.append(str(exc))
    venue_id = state["active"].get("venue_profile_id")
    if venue_id:
        try:
            venue_profile = read_json(root / f"calibration/{venue_id}.json")
            validate_venue_profile(root, venue_profile)
            corpus_id = state["active"].get("venue_corpus_id")
            if not corpus_id or venue_profile.get("venue_corpus_id") != corpus_id:
                errors.append("active venue profile is not bound to the active venue corpus")
            elif venue_profile.get("venue_corpus_hash") != sha256_file(root / f"calibration/{corpus_id}.json"):
                errors.append("active venue profile corpus hash is stale")
            judgment_id = state["active"].get("venue_profile_judgment_id")
            if judgment_id:
                judgment = read_json(root / f"calibration/{judgment_id}.json")
                if judgment.get("venue_profile_id") != venue_id or judgment.get("venue_profile_hash") != sha256_file(root / f"calibration/{venue_id}.json"):
                    errors.append("active venue judgment is stale")
        except ValueError as exc:
            errors.append(str(exc))
    publication_id = state["active"].get("publication_contract_id")
    if publication_id and policy_id and venue_id:
        try:
            validate_publication_contract(
                read_json(root / f"contracts/{publication_id}.json"),
                read_json(root / f"intake/{policy_id}.json"),
                read_json(root / f"calibration/{venue_id}.json"),
            )
        except ValueError as exc:
            errors.append(str(exc))
    if active_manuscript:
        manuscript_record = root / f"manuscript/{active_manuscript}.json"
        if not manuscript_record.exists():
            errors.append(f"active manuscript missing: {active_manuscript}")
        elif manuscript_digest(root) != read_json(manuscript_record).get("content_hash"):
            errors.append(f"active manuscript changed after registration: {active_manuscript}")
    for approval in state.get("approvals", []):
        for artifact, expected in approval.get("evidence_hashes", {}).items():
            path = root / artifact
            if not path.is_file():
                errors.append(f"approval {approval.get('approval_id')} evidence missing: {artifact}")
            elif sha256_file(path) != expected:
                errors.append(f"approval {approval.get('approval_id')} evidence changed: {artifact}")
    try:
        claims = read_json(root / "claims/claim-registry.json").get("claims", [])
    except ValueError as exc:
        errors.append(str(exc)); claims = []
    for claim in claims:
        for artifact, expected in (claim.get("evidence_hashes") or {}).items():
            path = root / artifact
            if not path.is_file():
                errors.append(f"claim {claim.get('claim_id')} evidence missing: {artifact}")
            elif sha256_file(path) != expected:
                errors.append(f"claim {claim.get('claim_id')} evidence changed: {artifact}")
    branch_registry = root / "experiments/branch-registry.json"
    if branch_registry.is_file():
        try:
            branches = read_json(branch_registry).get("branches", [])
        except ValueError as exc:
            errors.append(str(exc)); branches = []
        for branch in branches:
            bindings = dict(branch.get("evidence_hashes") or {})
            bindings.update((branch.get("evaluation") or {}).get("evidence_hashes") or {})
            for artifact, expected in bindings.items():
                path = root / artifact
                if not path.is_file():
                    errors.append(f"branch {branch.get('branch_id')} evidence missing: {artifact}")
                elif sha256_file(path) != expected:
                    errors.append(f"branch {branch.get('branch_id')} evidence changed: {artifact}")
            for run_id in branch.get("run_ids", []):
                run_path = root / f"experiments/runs/{run_id}/run_manifest.json"
                if not run_path.is_file():
                    errors.append(f"branch {branch.get('branch_id')} run missing: {run_id}")
    for gate, meta in state["gates"].items():
        try:
            report = read_json(root / meta["report"])
            for artifact, expected in report.get("evidence_hashes", {}).items():
                path = root / artifact
                if not path.exists():
                    errors.append(f"{gate} evidence missing: {artifact}")
                elif sha256_file(path) != expected:
                    errors.append(f"{gate} evidence changed after evaluation: {artifact}")
            judgment = report.get("judgment")
            if judgment:
                judgment_path = root / judgment
                if not judgment_path.is_file():
                    errors.append(f"{gate} judgment missing: {judgment}")
                elif sha256_file(judgment_path) != report.get("judgment_hash"):
                    errors.append(f"{gate} judgment changed after evaluation: {judgment}")
        except (KeyError, ValueError) as exc:
            errors.append(f"invalid gate {gate}: {exc}")
    phase = state["phase"]
    if phase in PHASES:
        for gate in required_gates_for(state["profile"], phase):
            if state["gates"].get(gate, {}).get("verdict") not in PASSING:
                errors.append(f"phase {phase} lacks passing {gate}")
    if any(item.get("gate") in state["gates"] and state["gates"][item["gate"]].get("verdict") in PASSING for item in state.get("blockers", [])):
        errors.append("state contains a stale blocker for a passing gate")
    secret_names = {".env", "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", "private_key"}
    for path in root.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(root)
        if path.name in secret_names or path.suffix.lower() in {".pem", ".p12", ".pfx"}:
            errors.append(f"credential-like file must not be stored in research state: {relative}")
            continue
        if path.stat().st_size <= 1_000_000:
            try:
                prefix = path.read_bytes()[:4096]
            except OSError:
                continue
            if b"-----BEGIN " in prefix and b"PRIVATE KEY-----" in prefix:
                errors.append(f"private key material detected in research state: {relative}")
                continue
            try:
                decoded = prefix.decode("utf-8")
            except UnicodeDecodeError:
                continue
            if contains_secret(decoded):
                errors.append(f"credential-like token detected in research state: {relative}")
    return errors


def migrate_legacy(root: Path, legacy: Path, profile: str) -> None:
    init_layout(root, profile, legacy.name)
    categories = {
        "user_policy_candidate": [
            "research/intake/resource-envelope.json", "intake/resource-envelope.json",
            "resource-envelope.json",
        ],
        "venue_profile_candidate": [
            "research/calibration/venue-profile.json", "research/venue-study.json",
            "venue-study.json", "venue_study.json",
        ],
        "research_program_candidate": [
            "research/contracts/experiment-contract.json", "research/contracts/research-contract.json",
            "experiment-contract.json", "research_contract.json",
        ],
        "claims_candidate": [
            "research/claims/claim-registry.json", "claim_registry.json",
        ],
        "results_candidate": [
            "research/evidence/results/results-manifest.jsonl", "results.facts.json",
        ],
        "publication_contract_candidate": ["blueprint.json", "research/blueprint.json"],
        "bibliography_candidate": ["refs.bib", "research/refs.bib"],
        "figure_candidate": ["figures/figures.manifest.json", "research/figures/figures.manifest.json"],
        "manuscript_candidate": [
            "main.tex", "main.pdf", "assemble.json", "latex_verdict.json",
            "research/reports/manuscript/latex-verdict.json",
        ],
        "legacy_state": ["research/research_state.json", "research_state.json"],
        "legacy_idea_material": ["story.json", "proposal.md"],
    }
    copied: list[str] = []
    candidates: list[dict[str, Any]] = []
    import_root = root / "intake/imported-v3"
    candidate_root = root / "reports/migration-candidates"
    for category, relatives in categories.items():
        sources = []
        seen: set[Path] = set()
        for relative in relatives:
            source = legacy / relative
            if not source.is_file() or source.resolve() in seen:
                continue
            seen.add(source.resolve())
            target = import_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            copied_path = target.relative_to(root).as_posix()
            copied.append(copied_path)
            sources.append({
                "source": str(source.resolve()),
                "imported_copy": copied_path,
                "sha256": sha256_file(target),
            })
        if not sources:
            continue
        candidate = {
            "schema_version": SCHEMA_VERSION,
            "candidate_type": category,
            "status": "IMPORTED_UNVERIFIED",
            "sources": sources,
            "may_not_satisfy_v5_schema": True,
            "inherited_gate_verdicts": "INVALIDATED",
            "required_next_action": "model review and explicit v5 registration",
            "created_at": now(),
        }
        candidate_path = candidate_root / f"{category}.json"
        write_json(candidate_path, candidate)
        candidates.append({
            "candidate_type": category,
            "artifact": candidate_path.relative_to(root).as_posix(),
            "sha256": sha256_file(candidate_path),
        })
    state = load_state(root)
    save_state(root, state, "legacy_artifacts_imported", {
        "source": str(legacy), "copied": copied, "candidates": candidates,
        "inherited_gate_verdicts": "INVALIDATED",
    })
    write_json(root / "reports/legacy-migration.json", {
        "schema_version": SCHEMA_VERSION,
        "source": str(legacy),
        "source_kind": "v3_or_older",
        "copied": copied,
        "candidates": candidates,
        "status": "IMPORTED_UNVERIFIED",
        "phase_after_import": "INTAKE",
        "old_gate_verdicts_inherited": False,
        "old_compile_verdict_inherited": False,
        "created_at": now(),
    })


def snapshot_environment() -> dict[str, Any]:
    def command(args: list[str]) -> str:
        try:
            return subprocess.check_output(args, stderr=subprocess.STDOUT, text=True, timeout=20).strip()
        except Exception:
            return "unavailable"
    return {
        "os": command(["uname", "-a"]), "python": sys.version.split()[0],
        "framework": os.environ.get("RLC_FRAMEWORK", "unspecified"),
        "dependencies": command([sys.executable, "-m", "pip", "freeze"]).splitlines(),
        "hardware": {"gpu": command(["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"]), "cpu": command(["uname", "-m"])},
        "cuda": command(["nvcc", "--version"]),
    }


def parse_payload(value: str) -> dict[str, Any]:
    return read_json(Path(value))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Research Lifecycle Core")
    parser.add_argument("--root", default=".", help="research run root")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("init"); p.add_argument("--profile", choices=sorted(PROFILES), default="standard_empirical"); p.add_argument("--run-id", default="research_run")
    p = sub.add_parser("register-idea"); p.add_argument("--file", required=True); p.add_argument("--parent"); p.add_argument("--level", default="L0"); p.add_argument("--approval")
    p = sub.add_parser("register-claim"); p.add_argument("--file", required=True)
    p = sub.add_parser("update-claim"); p.add_argument("claim_id"); p.add_argument("--support-status", required=True); p.add_argument("--action", required=True); p.add_argument("--evidence", action="append", required=True); p.add_argument("--allowed-wording", required=True)
    p = sub.add_parser("approve"); p.add_argument("--action", required=True); p.add_argument("--decision", choices=["APPROVED", "REJECTED"], required=True); p.add_argument("--scope", required=True); p.add_argument("--evidence", action="append", required=True); p.add_argument("--actor", default="user")
    p = sub.add_parser("register-resource-envelope"); p.add_argument("--file", required=True)
    p = sub.add_parser("register-user-policy"); p.add_argument("--file", required=True)
    p = sub.add_parser("register-idea-seed"); p.add_argument("--file", required=True)
    p = sub.add_parser("register-memory-snapshot"); p.add_argument("--file", required=True)
    p = sub.add_parser("register-science-profile"); p.add_argument("--file", required=True)
    p = sub.add_parser("register-venue-corpus"); p.add_argument("--file", required=True)
    p = sub.add_parser("register-venue-profile"); p.add_argument("--file", required=True)
    p = sub.add_parser("set-venue-judgment"); p.add_argument("--file", required=True)
    p = sub.add_parser("register-idea-candidates"); p.add_argument("--file", required=True)
    p = sub.add_parser("register-idea-selection"); p.add_argument("--file", required=True)
    p = sub.add_parser("freeze-research-program"); p.add_argument("--file", required=True); p.add_argument("--approval", required=True)
    p = sub.add_parser("freeze-publication-contract"); p.add_argument("--file", required=True); p.add_argument("--approval", required=True)
    p = sub.add_parser("register-bibliography-coverage"); p.add_argument("--file", required=True)
    p = sub.add_parser("register-figure-routing"); p.add_argument("--file", required=True)
    p = sub.add_parser("register-publication-judgment"); p.add_argument("--file", required=True)
    p = sub.add_parser("record-schedule-checkpoint"); p.add_argument("--file", required=True)
    p = sub.add_parser("register-latex-verdict"); p.add_argument("--file", required=True); p.add_argument("--pdf", required=True)
    p = sub.add_parser("register-release-audit"); p.add_argument("--file", required=True)
    p = sub.add_parser("register-repo"); p.add_argument("--file", required=True)
    p = sub.add_parser("lock-environment"); p.add_argument("--file"); p.add_argument("--snapshot", action="store_true")
    p = sub.add_parser("register-run"); p.add_argument("--file", required=True)
    p = sub.add_parser("propose-branch"); p.add_argument("--file", required=True)
    p = sub.add_parser("evaluate-branch"); p.add_argument("branch_id"); p.add_argument("--file", required=True)
    p = sub.add_parser("record-evidence"); p.add_argument("--file", required=True)
    p = sub.add_parser("set-gate"); p.add_argument("gate", choices=sorted(GATES)); p.add_argument("--verdict", required=True); p.add_argument("--evidence", action="append", required=True); p.add_argument("--summary", required=True); p.add_argument("--reviewer", default="main-model"); p.add_argument("--judgment")
    p = sub.add_parser("transition"); p.add_argument("target", choices=PHASES + sorted(TERMINAL_PHASES))
    p = sub.add_parser("stop"); p.add_argument("target", choices=sorted(TERMINAL_PHASES)); p.add_argument("--reason", required=True); p.add_argument("--evidence", action="append", required=True)
    p = sub.add_parser("invalidate"); p.add_argument("change"); p.add_argument("--reason", required=True)
    p = sub.add_parser("record-decision"); p.add_argument("--file", required=True)
    p = sub.add_parser("register-manuscript"); p.add_argument("source")
    p = sub.add_parser("migrate-legacy"); p.add_argument("legacy"); p.add_argument("--profile", choices=sorted(PROFILES), default="standard_empirical")
    sub.add_parser("validate"); sub.add_parser("status")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    root = Path(args.root).resolve()
    try:
        if args.command == "init": init_layout(root, args.profile, args.run_id); result = {"ok": True, "root": str(root)}
        elif args.command == "register-idea": result = {"ok": True, "idea_id": register_idea(root, parse_payload(args.file), args.parent, args.level, args.approval)}
        elif args.command == "register-claim": result = {"ok": True, "claim_id": register_claim(root, parse_payload(args.file))}
        elif args.command == "update-claim": update_claim(root, args.claim_id, args.support_status, args.action, args.evidence, args.allowed_wording); result = {"ok": True, "claim_id": args.claim_id}
        elif args.command == "approve": result = {"ok": True, "approval_id": record_approval(root, args.action, args.decision, args.scope, args.evidence, args.actor)}
        elif args.command == "register-resource-envelope": register_resource_envelope(root, parse_payload(args.file)); result = {"ok": True, "resource_envelope": "intake/resource-envelope.json"}
        elif args.command == "register-user-policy": result = {"ok": True, "user_policy_id": register_user_policy(root, parse_payload(args.file))}
        elif args.command == "register-idea-seed": result = {"ok": True, "idea_seed_id": register_idea_seed(root, parse_payload(args.file))}
        elif args.command == "register-memory-snapshot": result = {"ok": True, "memory_snapshot_id": register_memory_snapshot(root, parse_payload(args.file))}
        elif args.command == "register-science-profile": result = {"ok": True, "science_profile_id": register_science_profile(root, parse_payload(args.file))}
        elif args.command == "register-venue-corpus": result = {"ok": True, "venue_corpus_id": register_venue_corpus(root, parse_payload(args.file))}
        elif args.command == "register-venue-profile": result = {"ok": True, "venue_profile_id": register_venue_profile(root, parse_payload(args.file))}
        elif args.command == "set-venue-judgment": result = {"ok": True, "venue_profile_judgment_id": set_venue_judgment(root, parse_payload(args.file))}
        elif args.command == "register-idea-candidates": result = {"ok": True, "idea_candidates_id": register_idea_candidates(root, parse_payload(args.file))}
        elif args.command == "register-idea-selection": result = {"ok": True, "idea_selection_id": register_idea_selection(root, parse_payload(args.file))}
        elif args.command == "freeze-research-program": result = {"ok": True, "research_program_id": freeze_research_program(root, parse_payload(args.file), args.approval)}
        elif args.command == "freeze-publication-contract": result = {"ok": True, "publication_contract_id": freeze_publication_contract(root, parse_payload(args.file), args.approval)}
        elif args.command == "register-bibliography-coverage": result = {"ok": True, "path": register_bibliography_coverage(root, parse_payload(args.file))}
        elif args.command == "register-figure-routing": result = {"ok": True, "path": register_figure_routing(root, parse_payload(args.file))}
        elif args.command == "register-publication-judgment": result = {"ok": True, "publication_judgment_id": register_publication_judgment(root, parse_payload(args.file))}
        elif args.command == "record-schedule-checkpoint": result = {"ok": True, "path": record_schedule_checkpoint(root, parse_payload(args.file))}
        elif args.command == "register-latex-verdict": result = {"ok": True, "path": register_latex_verdict(root, parse_payload(args.file), Path(args.pdf).resolve())}
        elif args.command == "register-release-audit": result = {"ok": True, "release_audit_id": register_release_audit(root, parse_payload(args.file))}
        elif args.command == "register-repo": register_repo(root, parse_payload(args.file)); result = {"ok": True}
        elif args.command == "lock-environment": lock_environment(root, snapshot_environment() if args.snapshot else parse_payload(args.file)); result = {"ok": True}
        elif args.command == "register-run": result = {"ok": True, "run_id": register_run(root, parse_payload(args.file))}
        elif args.command == "propose-branch": result = {"ok": True, "branch_id": propose_branch(root, parse_payload(args.file))}
        elif args.command == "evaluate-branch": evaluate_branch(root, args.branch_id, parse_payload(args.file)); result = {"ok": True, "branch_id": args.branch_id}
        elif args.command == "record-evidence": record_evidence(root, parse_payload(args.file)); result = {"ok": True}
        elif args.command == "set-gate": set_gate(root, args.gate, args.verdict, args.evidence, args.summary, args.reviewer, args.judgment); result = {"ok": True, "gate": args.gate}
        elif args.command == "transition": transition(root, args.target); result = {"ok": True, "phase": args.target}
        elif args.command == "stop": stop(root, args.target, args.reason, args.evidence); result = {"ok": True, "phase": args.target}
        elif args.command == "invalidate": explicit_invalidate(root, args.change, args.reason); result = {"ok": True}
        elif args.command == "record-decision": result = {"ok": True, "decision_id": record_decision(root, parse_payload(args.file))}
        elif args.command == "register-manuscript": result = {"ok": True, "manuscript_id": register_manuscript(root, Path(args.source).resolve())}
        elif args.command == "migrate-legacy": migrate_legacy(root, Path(args.legacy).resolve(), args.profile); result = {"ok": True, "root": str(root)}
        elif args.command == "validate":
            errors = validate_root(root); result = {"ok": not errors, "errors": errors}; print(json.dumps(result, indent=2)); return 0 if not errors else 1
        elif args.command == "status": result = load_state(root)
        else: raise AssertionError(args.command)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
