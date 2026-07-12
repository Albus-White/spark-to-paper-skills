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

SCHEMA_VERSION = "3.0.0"
PHASES = [
    "INTAKE", "IDEA_DRAFTED", "IDEA_GROUNDED", "RESEARCH_CONTRACT_FROZEN",
    "CODEBASE_LOCKED", "BASELINE_VERIFIED", "IMPLEMENTATION_VERIFIED",
    "PILOT_VERIFIED", "FULL_EXPERIMENT_COMPLETED", "MECHANISM_DIAGNOSED",
    "IDEA_DECIDED", "REVALIDATION_COMPLETED", "CLAIMS_RECONCILED",
    "MANUSCRIPT_HARDENED", "RELEASED",
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
}
STANDARD_REQUIRED_GATES = {
    "IDEA_DRAFTED": ["G0"],
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
    "MANUSCRIPT_HARDENED": list(GATES),
    "RELEASED": list(GATES),
}
PROFILE_PHASES = {
    "proposal": [
        "INTAKE", "IDEA_DRAFTED", "IDEA_GROUNDED", "RESEARCH_CONTRACT_FROZEN",
        "MANUSCRIPT_HARDENED", "RELEASED",
    ],
    "exploratory": [
        "INTAKE", "IDEA_DRAFTED", "IDEA_GROUNDED", "RESEARCH_CONTRACT_FROZEN",
        "CODEBASE_LOCKED", "BASELINE_VERIFIED", "IMPLEMENTATION_VERIFIED",
        "PILOT_VERIFIED", "MECHANISM_DIAGNOSED", "IDEA_DECIDED",
        "CLAIMS_RECONCILED", "MANUSCRIPT_HARDENED", "RELEASED",
    ],
    "standard_empirical": PHASES,
    "high_risk": PHASES,
}
PROFILE_GATE_MILESTONES = {
    "proposal": {
        "IDEA_DRAFTED": ["G0"],
        "IDEA_GROUNDED": ["G1", "G2"],
        "RESEARCH_CONTRACT_FROZEN": ["G3"],
        "MANUSCRIPT_HARDENED": ["G16"],
    },
    "exploratory": {
        "IDEA_DRAFTED": ["G0"],
        "IDEA_GROUNDED": ["G1", "G2"],
        "RESEARCH_CONTRACT_FROZEN": ["G3"],
        "CODEBASE_LOCKED": ["G4", "G5"],
        "BASELINE_VERIFIED": ["G6"],
        "IMPLEMENTATION_VERIFIED": ["G7", "G8"],
        "PILOT_VERIFIED": ["G9"],
        "MECHANISM_DIAGNOSED": ["G12"],
        "IDEA_DECIDED": ["G13"],
        "CLAIMS_RECONCILED": ["G15"],
        "MANUSCRIPT_HARDENED": ["G16"],
    },
}
# Compatibility for callers that inspect the standard empirical path.
REQUIRED_GATES = STANDARD_REQUIRED_GATES
PASSING = {"PASS", "PASS_WITH_EXPLAINED_DEVIATION", "NOT_APPLICABLE"}
IDEA_DECISIONS = {"KEEP", "NARROW_SCOPE", "REVISE_MECHANISM", "REFRAME_PROBLEM", "BRANCH_NEW_IDEA", "REJECT_AND_STOP", "INSUFFICIENT_EVIDENCE"}
FAILURES = {"INFRASTRUCTURE_FAILURE", "DEPENDENCY_FAILURE", "IMPLEMENTATION_FAILURE", "PROTOCOL_FAILURE", "DATA_FAILURE", "BASELINE_REPRODUCTION_FAILURE", "RESOURCE_EXHAUSTED", "HYPOTHESIS_NOT_SUPPORTED", "INCONCLUSIVE", "NONE"}
PROFILES = {"proposal", "exploratory", "standard_empirical", "high_risk"}
MODEL_JUDGMENT_GATES = {"G1", "G2", "G3", "G6", "G7", "G8", "G9", "G12", "G13", "G14", "G15", "G16"}
HIGH_RISK_INDEPENDENT_GATES = {"G3", "G7", "G12", "G14", "G16"}
MANUSCRIPT_ROOT_FILES = {"main.tex", "refs.bib", "template.json", "latexmkrc"}
MANUSCRIPT_ROOT_SUFFIXES = {".sty", ".cls", ".bst"}
MANUSCRIPT_DIRECTORIES = {"sections", "figures", "assets"}
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
        "intake", "ideas", "claims", "grounding/reports", "contracts", "code/upstream",
        "code/integration", "code/adapters", "code/patches", "environment/snapshots",
        "experiments/baseline", "experiments/pilots", "experiments/runs", "experiments/iterations",
        "experiments/branches",
        "evidence", "evidence/results", "decisions", "reports/gates", "reports/design", "reports/code",
        "reports/experiments", "reports/mechanism", "reports/manuscript", "manuscript/sections",
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
        "active": {"idea_id": None, "contract_id": None, "manuscript_id": None},
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


def register_idea(root: Path, payload: dict[str, Any], parent: str | None, level: str, approval: str | None) -> str:
    state = load_state(root)
    required = ["problem", "hypothesis", "proposed_mechanism", "scope", "assumptions", "falsifiers", "claims", "alternative_explanations"]
    missing = [key for key in required if not payload.get(key)]
    if missing:
        raise ValueError(f"idea missing non-empty fields: {missing}")
    if level not in {"L0", "L1", "L2", "L3", "L4"}:
        raise ValueError("idea revision level must be L0..L4")
    if level in {"L2", "L3", "L4"} and not approval_valid(state, approval):
        raise ValueError(f"{level} idea changes require a recorded approved user decision")
    idea_id = next_id(root / "ideas", "idea-v")
    idea = dict(payload)
    idea.update({
        "schema_version": SCHEMA_VERSION, "idea_id": idea_id, "parent_idea_id": parent,
        "status": "ACTIVE", "revision_level": level, "approval": approval,
        "created_at": now(), "content_hash": None,
    })
    idea["content_hash"] = sha256_json({k: v for k, v in idea.items() if k != "content_hash"})
    write_json(root / f"ideas/{idea_id}.json", idea)
    previous = state["active"].get("idea_id")
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
            state["active"]["contract_id"] = None
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
        state["active"]["contract_id"] = None
    save_state(root, state, "resource_envelope_registered", {"sha256": current_hash})


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
    required = ["status", "budget_fit", "deadline_fit", "estimated_cost", "evidence"]
    missing = [key for key in required if key not in feasibility or feasibility[key] in (None, "", [])]
    if missing:
        raise ValueError(f"contract feasibility missing fields: {missing}")
    if feasibility["status"] != "MEASURED":
        raise ValueError("empirical contract feasibility must be MEASURED from a representative microprobe")
    if feasibility["budget_fit"] is not True:
        raise ValueError("contract cannot freeze when the measured feasibility does not fit the budget")
    if feasibility["deadline_fit"] is not True:
        raise ValueError("contract cannot freeze when the measured feasibility misses the user deadline")
    evidence = feasibility["evidence"] if isinstance(feasibility["evidence"], list) else [feasibility["evidence"]]
    missing_paths = [item for item in evidence if not (root / item).exists()]
    if missing_paths:
        raise ValueError(f"feasibility evidence missing: {missing_paths}")


def freeze_contract(root: Path, payload: dict[str, Any], approval: str) -> str:
    state = load_state(root)
    if not approval_valid(state, approval):
        raise ValueError("contract freeze requires a recorded APPROVED approval ID")
    approval_meta = approval_record(state, approval) or {}
    if approval_meta.get("action") != "FREEZE_CONTRACT" or approval_meta.get("scope") != state["active"].get("idea_id"):
        raise ValueError("contract approval must use action FREEZE_CONTRACT and scope the active idea_id")
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
        "claim_ids", "experiments", "study_inputs", "protocols", "outcomes", "comparators",
        "replication_plan", "statistical_plan", "test_set_policy", "stop_conditions", "budget",
    ]
    missing = [key for key in required if not payload.get(key)]
    if missing:
        raise ValueError(f"contract missing non-empty fields: {missing}")
    registry = read_json(root / "claims/claim-registry.json")
    valid_claims = {item["claim_id"] for item in registry.get("claims", []) if item.get("active")}
    unknown = sorted(set(payload["claim_ids"]) - valid_claims)
    if unknown:
        raise ValueError(f"contract references unknown claims: {unknown}")
    replication = payload["replication_plan"]
    if not isinstance(replication, dict) or any(
        replication.get(key) in (None, "", []) for key in ("type", "identifiers", "rationale")
    ):
        raise ValueError("contract replication_plan requires type, identifiers, and rationale")
    budget = payload["budget"]
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
        if budget.get("resource_envelope") != "intake/resource-envelope.json":
            raise ValueError("contract budget must reference intake/resource-envelope.json")
        if budget.get("resource_envelope_hash") != sha256_file(envelope_path):
            raise ValueError("contract budget resource envelope hash is stale")
        if budget.get("deadline_fit") is not True or not budget.get("allocation_rationale"):
            raise ValueError("contract budget requires deadline_fit=true and allocation_rationale")
    experiment_ids: set[str] = set()
    covered_claims: set[str] = set()
    experiment_required = [
        "experiment_id", "claim_ids", "why_it_tests_claim", "positive_interpretation",
        "negative_interpretation", "confounders", "out_of_scope_conclusions",
    ]
    for index, experiment in enumerate(payload["experiments"]):
        if not isinstance(experiment, dict):
            raise ValueError("contract experiments must be structured claim-linked objects")
        missing_experiment = [key for key in experiment_required if key not in experiment or experiment[key] in (None, "", [])]
        if missing_experiment:
            raise ValueError(f"contract experiment {index} missing fields: {missing_experiment}")
        experiment_id = experiment["experiment_id"]
        if experiment_id in experiment_ids:
            raise ValueError(f"duplicate experiment_id: {experiment_id}")
        experiment_ids.add(experiment_id)
        experiment_claims = set(experiment["claim_ids"])
        unknown_experiment_claims = sorted(experiment_claims - set(payload["claim_ids"]))
        if unknown_experiment_claims:
            raise ValueError(f"experiment {experiment_id} references claims outside the contract: {unknown_experiment_claims}")
        covered_claims.update(experiment_claims)
    uncovered = sorted(set(payload["claim_ids"]) - covered_claims)
    if uncovered:
        raise ValueError(f"contract claims lack a planned evaluation/proof unit: {uncovered}")
    validate_feasibility(root, payload, state["profile"])
    contract_id = next_id(root / "contracts", "experiment-contract-v")
    contract = dict(payload)
    source_schema_version = contract.pop("schema_version", contract.get("contract_schema_version", "legacy"))
    contract.update({
        "contract_schema_version": "3.0.0",
        "source_schema_version": source_schema_version,
        "lifecycle_schema_version": SCHEMA_VERSION,
        "contract_id": contract_id,
        "idea_id": state["active"]["idea_id"],
        "status": "FROZEN",
        "approval_id": approval,
        "created_at": now(),
        "content_hash": None,
    })
    contract["content_hash"] = sha256_json({k: v for k, v in contract.items() if k != "content_hash"})
    write_json(root / f"contracts/{contract_id}.json", contract)
    previous = state["active"].get("contract_id")
    state["active"]["contract_id"] = contract_id
    if previous and previous != contract_id:
        invalidate(state, "PROTOCOL_CHANGED", f"froze {contract_id}")
    save_state(root, state, "contract_frozen", {"contract_id": contract_id})
    return contract_id


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


def manuscript_digest(root: Path) -> str:
    active_dir = root / "manuscript" / "active"
    files = sorted(path for path in active_dir.rglob("*") if path.is_file())
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
    if not state["active"].get("idea_id") or not state["active"].get("contract_id"):
        raise ValueError("formal runs require active idea and frozen contract")
    if state["profile"] == "proposal" and payload["run_type"] in {"baseline", "pilot", "full", "revalidation"}:
        raise ValueError("proposal profile cannot register executable empirical runs")
    if state["profile"] == "exploratory" and payload["run_type"] in {"full", "revalidation"}:
        raise ValueError("exploratory profile cannot register confirmatory full/revalidation runs")
    contract = read_json(root / f"contracts/{state['active']['contract_id']}.json")
    if payload["run_type"] in {"baseline", "pilot", "full", "revalidation"}:
        experiment_ids = payload.get("experiment_ids")
        if not isinstance(experiment_ids, list) or not experiment_ids:
            raise ValueError("formal run manifest requires experiment_ids from the frozen contract")
        known_experiments = {item.get("experiment_id") for item in contract.get("experiments", []) if isinstance(item, dict)}
        unknown_experiments = sorted(set(experiment_ids) - known_experiments)
        if unknown_experiments:
            raise ValueError(f"run references unknown contract experiments: {unknown_experiments}")
    branch_id = payload.get("branch_id")
    if branch_id:
        registry = read_json(root / "experiments/branch-registry.json")
        branch = next((item for item in registry.get("branches", []) if item.get("branch_id") == branch_id), None)
        if not branch or branch.get("status") not in {"PROPOSED", "EXECUTING"}:
            raise ValueError(f"run branch_id is unknown or closed: {branch_id}")
        if branch.get("idea_id") != state["active"].get("idea_id") or branch.get("contract_id") != state["active"].get("contract_id"):
            raise ValueError("run branch belongs to a stale Idea or contract")
        if not set(payload.get("experiment_ids") or []).issubset(set(branch.get("experiment_ids") or [])):
            raise ValueError("run experiment_ids exceed the branch authorization")
    experiment_state_path = root / "experiments/state.json"
    experiment_state = read_json(experiment_state_path)
    max_runs = int((contract.get("budget") or {}).get("max_runs", 0) or 0)
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
        "contract_id": state["active"]["contract_id"], "repository_lock_hash": repos.get("lock_hash"),
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
        append_jsonl(root / "experiments/test_access_log.jsonl", {"at": now(), "run_id": run_id, "idea_id": manifest["idea_id"], "contract_id": manifest["contract_id"], "purpose": payload.get("test_access_purpose", "unspecified")})
        experiment_state["test_accesses"] = experiment_state.get("test_accesses", 0) + 1
    experiment_state["runs_registered"] = experiment_state.get("runs_registered", 0) + 1
    failure = payload["failure_class"]
    experiment_state.setdefault("failures", {})[failure] = experiment_state.setdefault("failures", {}).get(failure, 0) + 1
    write_json(experiment_state_path, experiment_state)
    save_state(root, state, "run_registered", {"run_id": run_id, "run_type": payload["run_type"], "failure_class": payload["failure_class"]})
    return run_id


def propose_branch(root: Path, payload: dict[str, Any]) -> str:
    required = [
        "question", "change_class", "hypothesis", "experiment_ids", "expected_observations",
        "rationale", "estimated_cost", "evidence", "stop_condition",
    ]
    missing = [key for key in required if key not in payload or payload[key] in (None, "", [])]
    if missing:
        raise ValueError(f"branch proposal missing fields: {missing}")
    if payload["change_class"] not in {"debug_repair", "implementation", "protocol", "idea", "diagnostic"}:
        raise ValueError("invalid branch change_class")
    state = load_state(root)
    contract_id = state["active"].get("contract_id")
    if not contract_id:
        raise ValueError("branching requires a frozen contract")
    contract = read_json(root / f"contracts/{contract_id}.json")
    known_experiments = {item.get("experiment_id") for item in contract.get("experiments", []) if isinstance(item, dict)}
    unknown = sorted(set(payload["experiment_ids"]) - known_experiments)
    if unknown:
        raise ValueError(f"branch references unknown contract experiments: {unknown}")
    missing_evidence = [item for item in payload["evidence"] if not (root / item).is_file()]
    if missing_evidence:
        raise ValueError(f"branch evidence missing: {missing_evidence}")
    registry_path = root / "experiments/branch-registry.json"
    registry = read_json(registry_path)
    branches = registry.setdefault("branches", [])
    budget = contract["budget"]
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
        "hypothesis": payload["hypothesis"], "experiment_ids": sorted(payload["experiment_ids"]),
    })
    if any(item.get("signature") == signature for item in branches):
        raise ValueError("duplicate scientific branch without a material state change")
    branch_id = f"BR-{len(branches) + 1:03d}"
    branch = {
        **payload, "branch_id": branch_id, "parent_branch_id": parent_id, "depth": depth,
        "idea_id": state["active"].get("idea_id"), "contract_id": contract_id,
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
        contract = read_json(root / f"contracts/{state['active']['contract_id']}.json")
        return (contract.get("revalidation") or {}).get("required") is False
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
    state["phase"] = target
    save_state(root, state, "phase_transition", {"target": target})


def invalidate(state: dict[str, Any], change: str, reason: str) -> None:
    reset = {
        "IDEA_EDITORIAL_CHANGED": ("CLAIMS_RECONCILED", ["G16"]),
        "IDEA_SCOPE_CHANGED": ("IDEA_GROUNDED", ["G3", "G9", "G10", "G11", "G12", "G13", "G14", "G15", "G16"]),
        "IDEA_ESTIMAND_CHANGED": ("IDEA_GROUNDED", ["G3", "G6", "G7", "G8", "G9", "G10", "G11", "G12", "G13", "G14", "G15", "G16"]),
        "IDEA_CORE_CHANGED": ("IDEA_DRAFTED", ["G1", "G2", "G3", "G6", "G7", "G8", "G9", "G10", "G11", "G12", "G13", "G14", "G15", "G16"]),
        "PROTOCOL_CHANGED": ("IDEA_GROUNDED", ["G3", "G6", "G7", "G8", "G9", "G10", "G11", "G12", "G13", "G14", "G15", "G16"]),
        "RESOURCE_ENVELOPE_CHANGED": ("IDEA_GROUNDED", ["G3", "G6", "G7", "G8", "G9", "G10", "G11", "G12", "G13", "G14", "G15", "G16"]),
        "REPOSITORY_CHANGED": ("RESEARCH_CONTRACT_FROZEN", ["G4", "G6", "G7", "G8", "G9", "G10", "G11", "G12", "G13", "G14", "G15", "G16"]),
        "IMPLEMENTATION_CHANGED": ("BASELINE_VERIFIED", ["G7", "G8", "G9", "G10", "G11", "G12", "G13", "G14", "G15", "G16"]),
        "ENVIRONMENT_CHANGED": ("CODEBASE_LOCKED", ["G5", "G6", "G7", "G8", "G9", "G10", "G11", "G12", "G13", "G14", "G15", "G16"]),
        "TEST_CONTAMINATED": ("MECHANISM_DIAGNOSED", ["G13", "G14", "G15", "G16"]),
        "MANUSCRIPT_CHANGED": ("CLAIMS_RECONCILED", ["G16"]),
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
            or known_runs[run_id].get("contract_id") != state["active"].get("contract_id")
        ]
        if stale_runs:
            raise ValueError(f"result fact {fact['fact_id']} references stale runs: {stale_runs}")
        contract = read_json(root / f"contracts/{state['active']['contract_id']}.json")
        experiment_claims = {
            item.get("experiment_id"): set(item.get("claim_ids") or [])
            for item in contract.get("experiments", []) if isinstance(item, dict)
        }
        run_experiments = {
            experiment_id
            for run_id in fact["run_ids"]
            for experiment_id in known_runs[run_id].get("experiment_ids", [])
        }
        unsupported_links = [
            claim_id for claim_id in fact["claim_ids"]
            if not any(claim_id in experiment_claims.get(experiment_id, set()) for experiment_id in run_experiments)
        ]
        if unsupported_links:
            raise ValueError(
                f"result fact {fact['fact_id']} has no claim-linked contract experiment in its runs: {unsupported_links}"
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
    active_contract = state["active"].get("contract_id")
    active_manuscript = state["active"].get("manuscript_id")
    if gate == "G1":
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
            "authorized_run_ids", "contract_id", "repository_lock_hash", "environment_lock_hash",
            "budget_check", "test_access_summary", "raw_outputs",
        ], semantic=False)
        run_ids = set(report.get("authorized_run_ids") or [])
        if not run_ids or not run_ids.issubset({item["run_id"] for item in runs}):
            raise ValueError("full-run integrity must reference successful full run IDs")
        if report.get("contract_id") != active_contract:
            raise ValueError("full-run integrity contract_id is stale")
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


def validate_root(root: Path) -> list[str]:
    errors: list[str] = []
    try:
        state = load_state(root)
    except ValueError as exc:
        return [str(exc)]
    active_idea = state["active"].get("idea_id")
    active_contract = state["active"].get("contract_id")
    active_manuscript = state["active"].get("manuscript_id")
    if active_idea and not (root / f"ideas/{active_idea}.json").exists():
        errors.append(f"active idea missing: {active_idea}")
    if active_contract and not (root / f"contracts/{active_contract}.json").exists():
        errors.append(f"active contract missing: {active_contract}")
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
    mappings = [
        (legacy / "story.json", root / "intake/legacy-story.json"),
        (legacy / "blueprint.json", root / "intake/legacy-blueprint.json"),
        (legacy / "results.facts.json", root / "intake/legacy-results.facts.json"),
        (legacy / "proposal.md", root / "intake/proposal.md"),
    ]
    copied = []
    for source, target in mappings:
        if source.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            copied.append(str(target.relative_to(root)))
    state = load_state(root)
    save_state(root, state, "legacy_artifacts_imported", {"source": str(legacy), "copied": copied})
    write_json(root / "reports/legacy-migration.json", {"source": str(legacy), "copied": copied, "status": "IMPORTED_UNVERIFIED", "created_at": now()})


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
    p = sub.add_parser("freeze-contract"); p.add_argument("--file", required=True); p.add_argument("--approval", required=True)
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
        elif args.command == "freeze-contract": result = {"ok": True, "contract_id": freeze_contract(root, parse_payload(args.file), args.approval)}
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
