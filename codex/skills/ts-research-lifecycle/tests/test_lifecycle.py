from __future__ import annotations

import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "scripts/lifecycle.py"
spec = importlib.util.spec_from_file_location("lifecycle", MODULE_PATH)
lifecycle = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(lifecycle)


def write(path: Path, value) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


IDEA = {
    "problem": "Robust forecasting under sparse observations",
    "hypothesis": "A masked consistency objective improves sparse-regime generalization",
    "proposed_mechanism": "Consistency regularizes representations when observations are missing",
    "scope": "multivariate forecasting with 30-70% missingness",
    "assumptions": ["missingness is observable"],
    "falsifiers": ["no gain over matched regularization baselines"],
    "claims": ["improves sparse-regime accuracy"],
    "alternative_explanations": ["gain comes only from additional compute"],
}
CLAIM = {
    "claim_text": "The objective improves sparse-regime accuracy",
    "claim_type": "empirical result claim", "essential": True, "strength": "bounded",
    "scope": "30-70% missingness", "required_evidence": ["multi-seed benchmark comparison"],
}
CONTRACT = {
    "claim_ids": ["C-001"], "experiments": [{
        "experiment_id": "E-001", "claim_ids": ["C-001"],
        "why_it_tests_claim": "matched comparison measures the claimed sparse-regime effect",
        "positive_interpretation": "supports the bounded claim", "negative_interpretation": "weakens or rejects the claim",
        "confounders": ["additional compute"], "out_of_scope_conclusions": ["dense-regime superiority"],
    }],
    "study_inputs": ["canonical benchmark"], "protocols": ["official split and preprocessing"],
    "outcomes": ["MAE"], "comparators": ["official baseline"],
    "replication_plan": {"type": "random_seeds", "identifiers": [1, 2, 3], "rationale": "pilot variance"},
    "statistical_plan": {"aggregate": "mean/std"},
    "test_set_policy": {"max_access": 1, "development": "validation only"},
    "stop_conditions": ["budget exhausted", "hypothesis rejected"],
    "budget": {"max_runs": 12, "max_branches": 4, "max_branch_depth": 2},
    "feasibility": {
        "status": "MEASURED", "budget_fit": True, "deadline_fit": True,
        "estimated_cost": {"seconds": 1}, "evidence": ["reports/design/feasibility.json"],
    },
    "revalidation": {"required": False, "rationale": "Synthetic fixture"},
}
REPO = {"purpose": "official benchmark", "url": "https://example.org/repo.git", "official_status": "official", "license": "MIT", "local_path": "code/upstream/repo", "modification_mode": "read_only"}
ENV = {"os": "linux", "python": "3.12", "framework": "pytorch-2.4", "dependencies": ["torch==2.4"], "hardware": {"gpu": "test"}}


class LifecycleTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "run"
        lifecycle.init_layout(self.root, "standard_empirical", "test")
        lifecycle.register_resource_envelope(self.root, {
            "source": "USER_PROVIDED", "deadline": {"max_elapsed_hours": 24, "hard": True},
            "compute": [{"backend": "local", "hardware": "test GPU", "count": 1, "availability_hours": 12}],
            "financial_limit": {"currency": "USD", "amount": 10}, "human_review": {"hours": 1},
            "priorities": ["scientific validity", "deadline"], "constraints": [], "assumptions": [],
            "confirmed_by_user": True,
        })
        repo = self.root / REPO["local_path"]
        repo.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.email", "fixture@example.org"], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.name", "Fixture"], check=True)
        (repo / "README.md").write_text("fixture", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "README.md"], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "fixture"], check=True)
        subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", REPO["url"]], check=True)
        commit = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
        self.repo = {**REPO, "commit": commit}

    def tearDown(self):
        self.tmp.cleanup()

    def bootstrap(self):
        idea = lifecycle.register_idea(self.root, IDEA, None, "L0", None)
        claim = lifecycle.register_claim(self.root, CLAIM)
        lifecycle.write_json(self.root / "reports/design/feasibility.json", {"seconds": 1})
        contract_payload = self.bound_contract(CONTRACT)
        lifecycle.write_json(self.root / "grounding/research_contract.candidate.json", contract_payload)
        judgment = self.judgment("G3", ["grounding/research_contract.candidate.json", "reports/design/feasibility.json"])
        approval = lifecycle.record_approval(self.root, "FREEZE_CONTRACT", "APPROVED", idea, [judgment], "main-model")
        contract = lifecycle.freeze_contract(self.root, contract_payload, approval)
        lifecycle.register_repo(self.root, self.repo)
        lifecycle.lock_environment(self.root, ENV)
        lifecycle.write_json(self.root / "grounding/benchmark_candidates.json", {"candidates": [], "decision": {"classification": "NO_PUBLIC_BENCHMARK", "rationale": "fixture", "search_scope": "official repositories and primary papers"}})
        return idea, claim, contract

    def register_test_run(self, run_type, test=False):
        return lifecycle.register_run(self.root, {"run_type": run_type, "experiment_ids": ["E-001"], "command": run_type, "replicate_id": "seed-1", "random_seed": 1, "config": {"type": run_type}, "input_artifact_hashes": {"dataset": "d" * 64}, "protocol_hash": "e" * 64, "status": "completed", "failure_class": "NONE", "test_set_accessed": test, "test_access_purpose": "final confirmation" if test else "none"})

    def bound_contract(self, contract):
        envelope = self.root / "intake/resource-envelope.json"
        return {
            **contract,
            "budget": {
                **contract["budget"], "resource_envelope": "intake/resource-envelope.json",
                "resource_envelope_hash": lifecycle.sha256_file(envelope), "deadline_fit": True,
                "allocation_rationale": "The measured microprobe fits the user-confirmed deadline and compute envelope.",
            },
        }

    def evidence(self, name="evidence.txt"):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("verified", encoding="utf-8")
        return name

    def baseline_report(self, run_id):
        output = self.evidence("experiments/baseline/output.json")
        path = "reports/experiments/baseline-reproduction.json"
        lifecycle.write_json(self.root / path, {
            "baseline": "official baseline", "official_source": "https://example.org/paper",
            "expected_behavior": "matches the published fixture", "expected_source": "https://example.org/paper#table-1",
            "run_ids": [run_id], "actual_outputs": [output], "comparison": "matched",
            "deviations": [], "limitations": ["synthetic fixture"],
        })
        return path

    def implementation_report(self):
        code = self.evidence("code/integration/implementation.py")
        path = "reports/code/implementation-review.json"
        lifecycle.write_json(self.root / path, {
            "implementation_summary": "Masked consistency fixture", "contract_alignment": "aligned",
            "reviewed_artifacts": [{"path": code, "sha256": lifecycle.sha256_file(self.root / code)}],
            "risks": ["mask leakage"], "findings": [], "limitations": ["fixture"], "reviewer": "main-model",
        })
        return path

    def verification_report(self):
        proof = self.evidence("reports/code/mask-leakage-proof.txt")
        path = "reports/code/verification-suite.json"
        lifecycle.write_json(self.root / path, {
            "selection_judgment": {
                "implementation_summary": "Masked consistency fixture", "reviewer": "main-model",
                "risks": [{"risk_id": "R1", "failure_mode": "mask leakage", "scientific_consequence": "invalid comparison",
                           "rationale": "custom mask path", "applicable": True, "covered_by": ["T1"]}],
            },
            "tests": [{"test_id": "T1", "purpose": "detect leakage", "command": "fixture-test",
                       "oracle": "sealed values are inaccessible", "observed": "sealed", "status": "PASS", "evidence": [proof]}],
        })
        return path

    def pilot_report(self, run_id):
        path = "reports/experiments/pilot-assessment.json"
        lifecycle.write_json(self.root / path, {
            "run_ids": [run_id], "feasibility": "feasible", "signal_assessment": "measurable",
            "variance_assessment": "bounded", "protocol_observations": ["split remained sealed"],
            "failure_modes": [], "budget_projection": {"fits": True}, "decision": "proceed",
            "limitations": ["small fixture"],
        })
        return path

    def full_integrity_report(self, run_id, output):
        state = lifecycle.load_state(self.root)
        path = "reports/experiments/full-run-integrity.json"
        lifecycle.write_json(self.root / path, {
            "authorized_run_ids": [run_id], "contract_id": state["active"]["contract_id"],
            "repository_lock_hash": lifecycle.read_json(self.root / "code/repos.lock.json")["lock_hash"],
            "environment_lock_hash": lifecycle.read_json(self.root / "environment/environment.lock.json")["lock_hash"],
            "budget_check": {"within_budget": True}, "test_access_summary": {"count": 1},
            "raw_outputs": [output],
        })
        return path

    def mechanism_report(self):
        path = "reports/mechanism/mechanism-diagnosis.json"
        lifecycle.write_json(self.root / path, {
            "mechanism_predictions": ["consistency reduces sparse error"], "observations": ["bounded gain"],
            "alternative_explanations": ["compute"], "discriminating_evidence": ["matched compute"],
            "verdict": "MECHANISM_SUPPORTED", "claim_implications": "retain bounded claim",
            "limitations": ["fixture"],
        })
        return path

    def judgment(self, gate, evidence, verdict="PASS", independent=True):
        path = f"reports/gates/{gate}.judgment.json"
        lifecycle.write_json(self.root / path, {
            "artifact_type": "scientific_judgment", "gate": gate, "verdict": verdict,
            "conclusion": "Evidence supports the bounded fixture decision.",
            "checks": [{"question": "Is the bounded decision supported?", "verdict": "SUPPORTED", "rationale": "Fixture evidence is explicit.", "evidence": evidence}],
            "limitations": ["Synthetic test fixture"], "blocking_issues": [],
            "reviewer": {"id": f"fixture-{gate}", "model_or_human": "test-model", "independent": independent, "context_artifacts": evidence},
            **({"applicability_rationale": "The benchmark is absent.", "counterfactual_trigger": "A compatible public benchmark would make this applicable."} if verdict == "NOT_APPLICABLE" else {}),
        })
        return path

    def set_gate(self, gate, evidence, verdict="PASS"):
        existing = self.root / f"reports/gates/{gate}.judgment.json"
        judgment = f"reports/gates/{gate}.judgment.json" if gate in lifecycle.MODEL_JUDGMENT_GATES and existing.is_file() else None
        if gate in lifecycle.MODEL_JUDGMENT_GATES and not judgment:
            judgment = self.judgment(gate, evidence, verdict)
        lifecycle.set_gate(self.root, gate, verdict, evidence, "verified", "fixture", judgment)

    def freeze(self, contract):
        state = lifecycle.load_state(self.root)
        contract = self.bound_contract(contract)
        lifecycle.write_json(self.root / "grounding/research_contract.candidate.json", contract)
        judgment = self.judgment("G3", ["grounding/research_contract.candidate.json", "reports/design/feasibility.json"])
        approval = lifecycle.record_approval(self.root, "FREEZE_CONTRACT", "APPROVED", state["active"]["idea_id"], [judgment], "main-model")
        return lifecycle.freeze_contract(self.root, contract, approval)

    def test_init_layout_and_validate(self):
        self.assertEqual(lifecycle.load_state(self.root)["phase"], "INTAKE")
        self.assertEqual(lifecycle.validate_root(self.root), [])

    def test_illegal_phase_jump_is_blocked(self):
        with self.assertRaisesRegex(ValueError, "sequential"):
            lifecycle.transition(self.root, "IDEA_GROUNDED")

    def test_gate_requires_real_evidence(self):
        with self.assertRaisesRegex(ValueError, "does not exist"):
            lifecycle.set_gate(self.root, "G0", "PASS", ["missing.md"], "ok", "reviewer")

    def test_idea_requires_falsifiability(self):
        bad = dict(IDEA); bad["falsifiers"] = []
        with self.assertRaisesRegex(ValueError, "falsifiers"):
            lifecycle.register_idea(self.root, bad, None, "L0", None)

    def test_major_idea_change_requires_approval(self):
        lifecycle.register_idea(self.root, IDEA, None, "L0", None)
        with self.assertRaisesRegex(ValueError, "recorded approved"):
            lifecycle.register_idea(self.root, IDEA, "idea-v-001", "L3", None)
        evidence = self.evidence("approval.md")
        approval = lifecycle.record_approval(self.root, "revise mechanism", "APPROVED", "Idea L3", [evidence], "user")
        evolved = lifecycle.register_idea(self.root, {**IDEA, "proposed_mechanism": "revised mechanism"}, "idea-v-001", "L3", approval)
        self.assertEqual(evolved, "idea-v-002")

    def test_formal_run_requires_locks_and_contract(self):
        lifecycle.register_idea(self.root, IDEA, None, "L0", None)
        lifecycle.register_claim(self.root, CLAIM)
        lifecycle.write_json(self.root / "reports/design/feasibility.json", {"seconds": 1})
        self.freeze(CONTRACT)
        run = {"run_type": "full", "experiment_ids": ["E-001"], "command": "train", "replicate_id": "seed-1", "config": {}, "input_artifact_hashes": {"dataset": "d" * 64}, "protocol_hash": "e" * 64, "status": "completed", "failure_class": "NONE", "test_set_accessed": False}
        with self.assertRaisesRegex(ValueError, "locks"):
            lifecycle.register_run(self.root, run)

    def test_repo_must_be_pinned(self):
        bad = dict(self.repo); bad["commit"] = "main"
        with self.assertRaisesRegex(ValueError, "full pinned Git object ID"):
            lifecycle.register_repo(self.root, bad)

    def test_evidence_hash_change_breaks_validation(self):
        evidence = self.evidence()
        lifecycle.set_gate(self.root, "G0", "PASS", [evidence], "intake verified", "reviewer")
        self.assertEqual(lifecycle.validate_root(self.root), [])
        (self.root / evidence).write_text("tampered", encoding="utf-8")
        self.assertTrue(any("changed after evaluation" in item for item in lifecycle.validate_root(self.root)))

    def test_protocol_change_invalidates_downstream_gates(self):
        self.bootstrap()
        evidence = self.evidence()
        baseline = self.register_test_run("baseline")
        artifacts = {"G2": "grounding/benchmark_candidates.json", "G6": self.baseline_report(baseline), "G7": self.implementation_report(), "G8": self.verification_report()}
        for gate in ("G0", "G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8"):
            self.set_gate(gate, [artifacts.get(gate, evidence)])
        state = lifecycle.load_state(self.root)
        state["phase"] = "IMPLEMENTATION_VERIFIED"
        lifecycle.save_state(self.root, state, "test_setup")
        self.freeze({**CONTRACT, "outcomes": ["MAE", "RMSE"]})
        state = lifecycle.load_state(self.root)
        self.assertEqual(state["phase"], "IDEA_GROUNDED")
        self.assertNotIn("G6", state["gates"])
        self.assertIn("G2", state["gates"])

    def test_test_access_is_logged(self):
        self.bootstrap()
        run = {"run_type": "full", "experiment_ids": ["E-001"], "command": "evaluate", "replicate_id": "seed-1", "config": {"model": "x"}, "input_artifact_hashes": {"dataset": "d" * 64}, "protocol_hash": "e" * 64, "status": "completed", "failure_class": "NONE", "test_set_accessed": True, "test_access_purpose": "final confirmation"}
        run_id = lifecycle.register_run(self.root, run)
        text = (self.root / "experiments/test_access_log.jsonl").read_text()
        self.assertIn(run_id, text)

    def test_execution_backend_must_match_environment_lock(self):
        self.bootstrap()
        execution = {"backend": "remote", "target": "research@gpu.example.org:22", "fingerprint": "fp"}
        lifecycle.lock_environment(self.root, {**ENV, "execution": execution})
        run = {"run_type": "pilot", "experiment_ids": ["E-001"], "command": "train", "replicate_id": "seed-1", "config": {},
               "input_artifact_hashes": {"dataset": "d" * 64}, "protocol_hash": "e" * 64, "status": "completed",
               "failure_class": "NONE", "test_set_accessed": False}
        with self.assertRaisesRegex(ValueError, "does not match environment lock"):
            lifecycle.register_run(self.root, run)
        run.update({"execution_backend": "remote", "execution_target": execution["target"],
                    "execution_environment_fingerprint": execution["fingerprint"]})
        self.assertTrue(lifecycle.register_run(self.root, run).startswith("run-"))

    def test_run_and_test_access_budgets_are_enforced(self):
        self.bootstrap()
        contract_path = self.root / "contracts/experiment-contract-v-001.json"
        contract = lifecycle.read_json(contract_path)
        contract["budget"]["max_runs"] = 1
        contract["test_set_policy"]["max_test_access"] = 1
        lifecycle.write_json(contract_path, contract)
        run = {"run_type": "full", "experiment_ids": ["E-001"], "command": "evaluate", "replicate_id": "seed-1", "config": {}, "input_artifact_hashes": {"dataset": "d" * 64}, "protocol_hash": "e" * 64, "status": "completed", "failure_class": "NONE", "test_set_accessed": True}
        lifecycle.register_run(self.root, run)
        with self.assertRaisesRegex(ValueError, "run budget exhausted"):
            lifecycle.register_run(self.root, run)

    def test_claim_update_requires_evidence(self):
        self.bootstrap()
        with self.assertRaisesRegex(ValueError, "requires evidence"):
            lifecycle.update_claim(self.root, "C-001", "SUPPORTED", "keep", [], "bounded")
        evidence = self.evidence("claim.txt")
        lifecycle.update_claim(self.root, "C-001", "PARTIALLY_SUPPORTED", "weaken", [evidence], "only under sparse conditions")
        claim = lifecycle.read_json(self.root / "claims/claim-registry.json")["claims"][0]
        self.assertEqual(claim["support_status"], "PARTIALLY_SUPPORTED")
        self.assertEqual(claim["action"], "weaken")

    def test_hypothesis_rejection_is_a_valid_evidence_backed_stop(self):
        self.bootstrap()
        evidence = self.evidence("negative-result.json")
        lifecycle.stop(self.root, "STOPPED_HYPOTHESIS_REJECTED", "Matched baselines falsified the claim", [evidence])
        self.assertEqual(lifecycle.load_state(self.root)["phase"], "STOPPED_HYPOTHESIS_REJECTED")
        stop = lifecycle.read_json(self.root / "experiments/state.json")["stop_reason"]
        self.assertEqual(stop["evidence"], [evidence])

    def test_idea_evolution_after_test_access_invalidates_confirmation(self):
        self.bootstrap()
        self.register_test_run("full", test=True)
        evidence = self.evidence("approval-evolution.md")
        approval = lifecycle.record_approval(self.root, "narrow scope", "APPROVED", "Idea L2", [evidence], "user")
        lifecycle.register_idea(self.root, {**IDEA, "scope": "only 50-70% missingness"}, "idea-v-001", "L2", approval)
        state = lifecycle.load_state(self.root)
        changes = [item["change"] for item in state["invalidations"]]
        self.assertIn("TEST_CONTAMINATED", changes)
        self.assertIsNone(state["active"]["contract_id"])

    def test_environment_change_invalidates_baseline(self):
        self.bootstrap()
        evidence = self.evidence()
        baseline = self.register_test_run("baseline")
        baseline_report = self.baseline_report(baseline)
        for gate in ("G0", "G1", "G2", "G3", "G4", "G5", "G6"):
            gate_evidence = baseline_report if gate == "G6" else "grounding/benchmark_candidates.json" if gate == "G2" else evidence
            self.set_gate(gate, [gate_evidence])
        state = lifecycle.load_state(self.root); state["phase"] = "BASELINE_VERIFIED"; lifecycle.save_state(self.root, state, "fixture")
        lifecycle.lock_environment(self.root, {**ENV, "framework": "pytorch-2.5"})
        state = lifecycle.load_state(self.root)
        self.assertEqual(state["phase"], "CODEBASE_LOCKED")
        self.assertNotIn("G6", state["gates"])

    def test_legacy_migration_is_unverified(self):
        legacy = Path(self.tmp.name) / "legacy"; legacy.mkdir()
        write(legacy / "story.json", {"title": "old"})
        target = Path(self.tmp.name) / "migrated"
        lifecycle.migrate_legacy(target, legacy, "proposal")
        report = lifecycle.read_json(target / "reports/legacy-migration.json")
        self.assertEqual(report["status"], "IMPORTED_UNVERIFIED")
        self.assertEqual(lifecycle.load_state(target)["phase"], "INTAKE")

    def test_full_happy_path_gates_and_transitions(self):
        self.bootstrap()
        evidence = self.evidence()
        manuscript = Path(self.tmp.name) / "paper"; manuscript.mkdir(); (manuscript / "main.tex").write_text("verified manuscript")
        lifecycle.register_manuscript(self.root, manuscript)
        baseline_run = self.register_test_run("baseline")
        pilot_run = self.register_test_run("pilot")
        full_run = self.register_test_run("full", test=True)
        raw = self.evidence("evidence/results/raw.json")
        code = self.evidence("code/integration/aggregate.py")
        baseline_report = self.baseline_report(baseline_run)
        implementation_report = self.implementation_report()
        verification_report = self.verification_report()
        pilot_report = self.pilot_report(pilot_run)
        full_report = self.full_integrity_report(full_run, raw)
        mechanism_report = self.mechanism_report()
        fact = {
            "fact_id": "F-001", "claim_ids": ["C-001"], "value": 0.5, "unit": "MAE",
            "run_ids": [full_run], "source_artifacts": [raw],
            "source_hashes": {raw: lifecycle.sha256_file(self.root / raw)},
            "aggregation": {"method": "direct", "code_artifact": code, "code_hash": lifecycle.sha256_file(self.root / code)},
        }
        manifest = self.root / "evidence/results/results-manifest.jsonl"
        manifest.write_text(json.dumps(fact) + "\n", encoding="utf-8")
        decision = {"decision": "KEEP", "rationale": "evidence supports bounded claim", "evidence": [evidence], "approval": "NOT_REQUIRED", "revision_level": "L0"}
        decision_id = lifecycle.record_decision(self.root, decision)
        lifecycle.update_claim(self.root, "C-001", "SUPPORTED", "keep", [evidence], "bounded sparse-regime claim")
        target_sequence = lifecycle.PHASES[1:]
        for target in target_sequence:
            for gate in lifecycle.REQUIRED_GATES.get(target, []):
                if gate not in lifecycle.load_state(self.root)["gates"]:
                    verdict = "NOT_APPLICABLE" if gate == "G14" else "PASS"
                    gate_evidence = {
                        "G2": ["grounding/benchmark_candidates.json"],
                        "G3": ["grounding/research_contract.candidate.json", "reports/design/feasibility.json"],
                        "G6": [baseline_report],
                        "G7": [implementation_report],
                        "G8": [verification_report],
                        "G9": [pilot_report],
                        "G10": [full_report],
                        "G11": ["evidence/results/results-manifest.jsonl"],
                        "G12": [mechanism_report],
                        "G13": [f"decisions/{decision_id}.json"],
                        "G15": ["claims/claim-registry.json"],
                    }.get(gate, [evidence])
                    self.set_gate(gate, gate_evidence, verdict)
            lifecycle.transition(self.root, target)
        self.assertEqual(lifecycle.load_state(self.root)["phase"], "RELEASED")
        self.assertEqual(lifecycle.validate_root(self.root), [])

    def test_manuscript_registration_is_versioned_and_invalidates_review(self):
        self.bootstrap()
        manuscript = Path(self.tmp.name) / "paper"; manuscript.mkdir(); (manuscript / "main.tex").write_text("v1")
        first = lifecycle.register_manuscript(self.root, manuscript)
        self.assertEqual(first, lifecycle.register_manuscript(self.root, manuscript))
        evidence = self.evidence()
        state = lifecycle.load_state(self.root); state["phase"] = "MANUSCRIPT_HARDENED"; lifecycle.save_state(self.root, state, "fixture")
        self.set_gate("G16", [evidence])
        (manuscript / "main.tex").write_text("v2")
        second = lifecycle.register_manuscript(self.root, manuscript)
        state = lifecycle.load_state(self.root)
        self.assertNotEqual(first, second)
        self.assertEqual(state["phase"], "CLAIMS_RECONCILED")
        self.assertNotIn("G16", state["gates"])

    def test_semantic_gate_cannot_pass_from_file_existence_alone(self):
        lifecycle.register_idea(self.root, IDEA, None, "L0", None)
        evidence = self.evidence()
        with self.assertRaisesRegex(ValueError, "structured main-model scientific judgment"):
            lifecycle.set_gate(self.root, "G1", "PASS", [evidence], "looks good", "pipeline-sync")

    def test_implementation_gate_rejects_empty_shell_report(self):
        self.bootstrap()
        report = "reports/code/implementation-review.json"
        lifecycle.write_json(self.root / report, {"ok": True})
        judgment = self.judgment("G7", [report])
        with self.assertRaisesRegex(ValueError, "missing fields"):
            lifecycle.set_gate(self.root, "G7", "PASS", [report], "reviewed", "main-model", judgment)

    def test_formal_run_must_link_to_frozen_experiment(self):
        self.bootstrap()
        with self.assertRaisesRegex(ValueError, "experiment_ids"):
            lifecycle.register_run(self.root, {
                "run_type": "pilot", "command": "train", "replicate_id": "specimen-1", "config": {},
                "input_artifact_hashes": {"specimens": "d" * 64}, "protocol_hash": "e" * 64, "status": "completed",
                "failure_class": "NONE", "test_set_accessed": False,
            })

    def test_scientific_branch_ledger_preserves_negative_branch_without_metric_chasing(self):
        self.bootstrap()
        evidence = self.evidence("reports/experiments/branch-question.md")
        proposal = {
            "question": "Does the observed gain come only from additional compute?",
            "change_class": "diagnostic", "hypothesis": "matched compute removes the apparent gain",
            "experiment_ids": ["E-001"],
            "expected_observations": {"supports": "gain disappears", "refutes": "gain remains"},
            "rationale": "distinguishes the main mechanism from the strongest alternative",
            "estimated_cost": {"runs": 1}, "evidence": [evidence],
            "stop_condition": "one matched diagnostic run completes",
        }
        branch_id = lifecycle.propose_branch(self.root, proposal)
        with self.assertRaisesRegex(ValueError, "duplicate scientific branch"):
            lifecycle.propose_branch(self.root, proposal)
        run_id = lifecycle.register_run(self.root, {
            "run_type": "baseline", "branch_id": branch_id, "experiment_ids": ["E-001"],
            "command": "matched-diagnostic", "replicate_id": "case-1", "config": {},
            "input_artifact_hashes": {"fixture": "d" * 64}, "protocol_hash": "e" * 64,
            "status": "completed", "failure_class": "NONE", "test_set_accessed": False,
        })
        result = self.evidence("experiments/branches/matched-result.json")
        lifecycle.evaluate_branch(self.root, branch_id, {
            "outcome": "UNSUPPORTED", "scientific_interpretation": "The diagnostic did not support the branch hypothesis.",
            "decision": "REJECT", "claim_implications": "retain the bounded main claim",
            "evidence": [result], "reviewer": "main-model", "limitations": ["single diagnostic condition"],
        })
        branch = lifecycle.read_json(self.root / "experiments/branch-registry.json")["branches"][0]
        self.assertEqual(branch["run_ids"], [run_id])
        self.assertEqual(branch["evaluation"]["decision"], "REJECT")
        self.assertEqual(branch["status"], "EVALUATED")

    def test_no_valid_public_benchmark_allows_evidence_backed_g6_not_applicable(self):
        self.bootstrap()
        benchmark = "grounding/benchmark_candidates.json"
        judgment = self.judgment("G6", [benchmark], verdict="NOT_APPLICABLE")
        lifecycle.set_gate(
            self.root, "G6", "NOT_APPLICABLE", [benchmark],
            "No compatible public baseline exists; use the contract alternative evaluation.",
            "main-model", judgment,
        )
        self.assertEqual(lifecycle.load_state(self.root)["gates"]["G6"]["verdict"], "NOT_APPLICABLE")

    def test_resource_envelope_change_requires_contract_refreeze_but_preserves_grounding(self):
        self.bootstrap()
        lifecycle.register_resource_envelope(self.root, {
            "source": "USER_PROVIDED", "deadline": {"max_elapsed_hours": 8, "hard": True},
            "compute": [{"backend": "remote", "target": "gpu.example.org", "hardware": "A100", "count": 2}],
            "financial_limit": {"currency": "USD", "amount": 20}, "human_review": {"hours": 1},
            "priorities": ["scientific validity", "speed"], "constraints": [], "assumptions": [],
            "confirmed_by_user": True,
        })
        state = lifecycle.load_state(self.root)
        self.assertIsNone(state["active"]["contract_id"])
        self.assertEqual(state["active"]["idea_id"], "idea-v-001")
        self.assertTrue(any(item["change"] == "RESOURCE_ENVELOPE_CHANGED" for item in state["invalidations"]))

    def test_identical_resource_envelope_registration_is_idempotent(self):
        _, _, contract_id = self.bootstrap()
        envelope_path = self.root / "intake/resource-envelope.json"
        original_hash = lifecycle.sha256_file(envelope_path)
        payload = json.loads(envelope_path.read_text(encoding="utf-8"))
        payload.pop("schema_version", None)
        payload.pop("captured_at", None)
        lifecycle.register_resource_envelope(self.root, payload)
        state = lifecycle.load_state(self.root)
        self.assertEqual(lifecycle.sha256_file(envelope_path), original_hash)
        self.assertEqual(state["active"]["contract_id"], contract_id)

    def test_resource_envelope_rejects_unconfirmed_model_assumptions(self):
        with self.assertRaisesRegex(ValueError, "confirmed"):
            lifecycle.register_resource_envelope(self.root, {
                "source": "USER_CONFIRMED_ASSUMPTIONS", "deadline": {"status": "UNKNOWN"},
                "compute": [], "financial_limit": {"status": "UNKNOWN"}, "human_review": {"status": "UNKNOWN"},
                "priorities": [], "constraints": [], "assumptions": ["local compute"], "confirmed_by_user": False,
            })

    def test_manuscript_registration_excludes_research_data_and_credentials(self):
        paper = Path(self.tmp.name) / "paper"; paper.mkdir()
        (paper / "main.tex").write_text("paper")
        (paper / "sections").mkdir(); (paper / "sections/method.tex").write_text("method")
        (paper / "research/environment").mkdir(parents=True); (paper / "research/environment/private_key").write_text("secret")
        (paper / "input/data").mkdir(parents=True); (paper / "input/data/raw.csv").write_text("sensitive")
        manuscript_id = lifecycle.register_manuscript(self.root, paper)
        files = [item["path"] for item in lifecycle.read_json(self.root / f"manuscript/{manuscript_id}.json")["files"]]
        self.assertEqual(files, ["main.tex", "sections/method.tex"])

    def test_validate_root_rejects_private_key_material(self):
        key = self.root / "environment/id_ed25519"
        key.write_text("-----BEGIN OPENSSH PRIVATE KEY-----\nsecret")
        self.assertTrue(any("credential-like file" in issue for issue in lifecycle.validate_root(self.root)))

    def test_run_manifest_and_logs_redact_credentials_but_keep_command_hash(self):
        self.bootstrap()
        run_id = lifecycle.register_run(self.root, {
            "run_type": "pilot", "experiment_ids": ["E-001"],
            "command": "API_TOKEN=super-secret-token-value python train.py",
            "replicate_id": "seed-1", "config": {}, "input_artifact_hashes": {"dataset": "d" * 64}, "protocol_hash": "e" * 64,
            "status": "completed", "failure_class": "NONE", "test_set_accessed": False,
        })
        manifest = lifecycle.read_json(self.root / f"experiments/runs/{run_id}/run_manifest.json")
        self.assertIn("[REDACTED]", manifest["command"])
        self.assertEqual(len(manifest["command_hash"]), 64)
        self.assertNotIn("super-secret-token-value", json.dumps(manifest))

    def test_l0_revision_preserves_empirical_evidence_and_only_reopens_review(self):
        idea_id, _, contract_id = self.bootstrap()
        state = lifecycle.load_state(self.root)
        state["phase"] = "CLAIMS_RECONCILED"
        for gate in ("G4", "G5", "G10", "G11", "G15", "G16"):
            state["gates"][gate] = {"verdict": "PASS", "report": "reports/gates/G0.json"}
        lifecycle.save_state(self.root, state, "fixture")
        revised = lifecycle.register_idea(
            self.root, {**IDEA, "hypothesis": IDEA["hypothesis"] + "."}, idea_id, "L0", None
        )
        state = lifecycle.load_state(self.root)
        self.assertEqual(state["active"]["contract_id"], contract_id)
        self.assertEqual(state["phase"], "CLAIMS_RECONCILED")
        self.assertNotIn("G16", state["gates"])
        self.assertTrue(all(gate in state["gates"] for gate in ("G4", "G5", "G10", "G11", "G15")))
        self.assertTrue(lifecycle.idea_evidence_compatible(self.root, idea_id, revised))

    def test_high_risk_release_requires_scoped_human_confirmation(self):
        root = Path(self.tmp.name) / "high-risk"
        lifecycle.init_layout(root, "high_risk", "high-risk-test")
        idea_id = lifecycle.register_idea(root, IDEA, None, "L0", None)
        paper = Path(self.tmp.name) / "high-risk-paper"; paper.mkdir(); (paper / "main.tex").write_text("paper")
        lifecycle.register_manuscript(root, paper)
        context = "manuscript/active/main.tex"
        wrong = lifecycle.record_approval(root, "FREEZE_CONTRACT", "APPROVED", idea_id, [context], "user")
        judgment = "reports/gates/G16.judgment.json"
        payload = {
            "artifact_type": "scientific_judgment", "gate": "G16", "verdict": "PASS",
            "conclusion": "The bounded manuscript is release-ready.",
            "checks": [{"question": "Is release justified?", "verdict": "SUPPORTED", "rationale": "Reviewed artifact is explicit.", "evidence": [context]}],
            "limitations": ["Synthetic fixture"], "blocking_issues": [],
            "reviewer": {"id": "independent-reviewer", "model_or_human": "test-model", "independent": True, "context_artifacts": [context]},
            "human_confirmation_approval_id": wrong,
        }
        lifecycle.write_json(root / judgment, payload)
        with self.assertRaisesRegex(ValueError, "CONFIRM_RELEASE"):
            lifecycle.set_gate(root, "G16", "PASS", [context], "reviewed", "independent", judgment)
        approval = lifecycle.record_approval(root, "CONFIRM_RELEASE", "APPROVED", idea_id, [context], "user")
        payload["human_confirmation_approval_id"] = approval
        lifecycle.write_json(root / judgment, payload)
        lifecycle.set_gate(root, "G16", "PASS", [context], "reviewed", "independent", judgment)
        self.assertEqual(lifecycle.load_state(root)["gates"]["G16"]["verdict"], "PASS")

    def test_proposal_profile_reaches_release_without_empirical_gates(self):
        root = Path(self.tmp.name) / "proposal"
        lifecycle.init_layout(root, "proposal", "proposal-test")
        idea_id = lifecycle.register_idea(root, IDEA, None, "L0", None)
        lifecycle.register_claim(root, {
            "claim_text": "The stated assumptions imply a bounded stability property",
            "claim_type": "theoretical claim", "essential": True, "strength": "conditional",
            "scope": "under the registered assumptions", "required_evidence": ["proof obligations and counterexamples"],
        })
        intake = "grounding/research_idea.json"; lifecycle.write_json(root / intake, IDEA)
        lifecycle.set_gate(root, "G0", "PASS", [intake], "intake", "pipeline-sync")
        lifecycle.transition(root, "IDEA_DRAFTED")
        benchmark = "grounding/benchmark_candidates.json"
        lifecycle.write_json(root / benchmark, {"candidates": [], "decision": {"classification": "NO_PUBLIC_BENCHMARK", "rationale": "searched", "search_scope": "official repositories and primary papers"}})

        def judge(gate, evidence):
            path = f"reports/gates/{gate}.judgment.json"
            lifecycle.write_json(root / path, {
                "artifact_type": "scientific_judgment", "gate": gate, "verdict": "PASS",
                "conclusion": "The proposal statement is evidence-bounded.",
                "checks": [{"question": "Is this bounded?", "verdict": "SUPPORTED", "rationale": "The evidence is explicit.", "evidence": evidence}],
                "limitations": ["No empirical results are claimed"], "blocking_issues": [],
                "reviewer": {"id": f"proposal-{gate}", "model_or_human": "main-model", "independent": False, "context_artifacts": evidence},
            })
            return path

        for gate in ("G1", "G2"):
            evidence = [intake, benchmark]
            lifecycle.set_gate(root, gate, "PASS", evidence, "grounded", "main-model", judge(gate, evidence))
        lifecycle.transition(root, "IDEA_GROUNDED")
        candidate = "grounding/research_contract.candidate.json"
        proposal_contract = {
            **CONTRACT,
            "experiments": [{
                "experiment_id": "E-001", "claim_ids": ["C-001"],
                "why_it_tests_claim": "the proof unit checks each stated implication",
                "positive_interpretation": "supports the conditional theorem",
                "negative_interpretation": "requires weakening or rejecting the theorem",
                "confounders": ["hidden assumptions"], "out_of_scope_conclusions": ["unconditional stability"],
            }],
            "study_inputs": ["formal assumptions and definitions"], "protocols": ["proof and counterexample analysis"],
            "outcomes": ["satisfied proof obligations"], "comparators": ["closest prior bound"],
            "replication_plan": {"type": "deterministic_proof_cases", "identifiers": ["main", "boundary"], "rationale": "cover theorem and boundary"},
            "feasibility": {"status": "NOT_REQUIRED"},
        }
        lifecycle.write_json(root / candidate, proposal_contract)
        design = judge("G3", [candidate, benchmark])
        approval = lifecycle.record_approval(root, "FREEZE_CONTRACT", "APPROVED", idea_id, [design], "main-model")
        lifecycle.freeze_contract(root, proposal_contract, approval)
        lifecycle.set_gate(root, "G3", "PASS", [candidate, benchmark], "approved", "main-model", design)
        lifecycle.transition(root, "RESEARCH_CONTRACT_FROZEN")
        paper = Path(self.tmp.name) / "proposal-paper"; paper.mkdir(); (paper / "main.tex").write_text("proposal")
        lifecycle.register_manuscript(root, paper)
        review = judge("G16", ["manuscript/active/main.tex"])
        lifecycle.set_gate(root, "G16", "PASS", ["manuscript/active/main.tex"], "reviewed", "main-model", review)
        lifecycle.transition(root, "MANUSCRIPT_HARDENED")
        lifecycle.transition(root, "RELEASED")
        self.assertEqual(lifecycle.load_state(root)["phase"], "RELEASED")
        self.assertFalse(any(gate in lifecycle.load_state(root)["gates"] for gate in ("G4", "G10", "G11", "G14")))


if __name__ == "__main__":
    unittest.main()
