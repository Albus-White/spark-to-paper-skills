from __future__ import annotations

import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "scripts/lifecycle.py"
spec = importlib.util.spec_from_file_location("lifecycle_v5", MODULE_PATH)
lifecycle = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(lifecycle)


IDEA = {
    "problem": "Estimate treatment effects under sparse observations",
    "hypothesis": "A calibrated estimator reduces sparse-regime error",
    "proposed_mechanism": "Calibration limits missingness-induced bias",
    "scope": "matched observations with 30-70% missingness",
    "assumptions": ["missingness indicators are observed"],
    "falsifiers": ["no gain over a matched calibrated comparator"],
    "claims": ["reduces sparse-regime estimation error"],
    "alternative_explanations": ["the gain comes only from extra compute"],
    "minimum_validation_path": "matched pilot followed by held-out confirmation",
}


class LifecycleV5Test(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "research"
        lifecycle.init_layout(self.root, "standard_empirical", "v5-test")
        lifecycle.register_resource_envelope(self.root, {
            "source": "USER_PROVIDED",
            "deadline": {"status": "KNOWN", "max_elapsed_hours": 24, "hard": True},
            "compute": [{"backend": "local", "hardware": "fixture", "count": 1, "availability_hours": 12}],
            "financial_limit": {"currency": "USD", "amount": 10},
            "human_review": {"hours": 1},
            "priorities": ["scientific validity", "deadline"],
            "constraints": [],
            "assumptions": [],
            "confirmed_by_user": True,
        })
        self.policy_id = lifecycle.register_user_policy(self.root, {
            "source": "COMPILED_FROM_USER_REQUEST",
            "target_venue": "Fixture Journal",
            "venue_selection_policy": "USER_SELECTED",
            "citation_policy": {"minimum_unique_cited_references": 12},
            "figure_policy": {
                "measured_evidence_route": "DETERMINISTIC_OR_ORIGINAL_EVIDENCE",
                "original_observation_route": "ORIGINAL_EVIDENCE",
                "exact_structure_route": "DOMAIN_NATIVE",
                "explanatory_synthesis_route": "PAPERBANANA_REQUIRED",
                "drawai_policy": "USE_IF_AVAILABLE_AFTER_RASTER_APPROVAL",
            },
            "requirements": ["scientific validity"],
            "research_preferences": {"field": "measurement science", "paper_archetype": "empirical method"},
            "deadline": {"status": "KNOWN", "max_elapsed_hours": 24},
            "resource_limits": {"compute": "fixture", "financial": "USD 10", "api": "none", "storage": "local"},
            "human_review": {"hours": 1},
            "priorities": ["scientific validity", "deadline"],
            "degradation_policy": {"acceptable": ["narrow claims"], "unacceptable": ["fabricated evidence", "page filler"]},
            "assumptions": {"unknowns": [], "confirmed": ["fixture resources"]},
        })
        self.seed_id = lifecycle.register_idea_seed(self.root, {
            "seed_text": "Improve treatment-effect estimation with sparse observations.",
            "source": "USER_PROVIDED",
            "constraints": ["one local compute worker"],
            "open_questions": ["which calibration mechanism is defensible"],
        })
        source_text = self.root / "calibration/papers/science-source.txt"
        source_text.parent.mkdir(parents=True, exist_ok=True)
        source_text.write_text("Primary source full text fixture.", encoding="utf-8")
        self.science_payload = {
            "idea_seed_id": self.seed_id,
            "idea_seed_hash": lifecycle.sha256_file(self.root / f"intake/{self.seed_id}.json"),
            "research_scope": "sparse-observation treatment-effect estimation",
            "corpus_protocol": {"queries": ["sparse treatment effect calibration"], "stopping_rule": "closest-work saturation"},
            "primary_sources": [{
                "title": "Calibrated Sparse Estimation",
                "venue": "Leading Field Journal",
                "year": 2025,
                "source": {"doi": "10.1000/science-source"},
                "full_text": {"path": "calibration/papers/science-source.txt", "sha256": lifecycle.sha256_file(source_text)},
                "relevance": "closest method family",
                "read_scope": "methods, evaluation, limitations",
            }],
            "closest_work": [{"title": "Calibrated Sparse Estimation", "difference": "does not test the proposed mechanism"}],
            "benchmark_landscape": {"searched": True, "status": "no directly applicable public benchmark"},
            "scientific_conventions": {"estimand": "matched effect difference"},
            "evidence_conventions": {"replication": "independent observation groups"},
            "writing_conventions": {"argument_style": "claim-evidence-limitation"},
            "open_questions": ["robustness to missingness mechanism"],
            "freshness": {"searched_at": "2026-07-13", "cutoff": "2026-07-13"},
            "limitations": ["synthetic fixture corpus"],
            "reviewer": {"id": "main-model"},
        }
        self.science_id = lifecycle.register_science_profile(self.root, self.science_payload)
        venue_pdf = self.root / "calibration/papers/accepted.pdf"
        venue_pdf.write_bytes(b"accepted paper fixture")
        self.corpus_id = lifecycle.register_venue_corpus(self.root, {
            "user_policy_id": self.policy_id,
            "user_policy_hash": lifecycle.sha256_file(self.root / f"intake/{self.policy_id}.json"),
            "science_profile_id": self.science_id,
            "science_profile_hash": lifecycle.sha256_file(self.root / f"calibration/{self.science_id}.json"),
            "venue_basis": {"type": "USER_SELECTED", "venues": ["Fixture Journal"]},
            "research_scope": "sparse-observation treatment-effect estimation",
            "paper_archetype": "empirical method",
            "inclusion_criteria": ["accepted full research article", "comparable archetype"],
            "exclusion_criteria": ["review", "editorial", "short abstract"],
            "time_window": "2024-2026",
            "publication_status": "accepted or published",
            "stopping_rule": "fixture corpus boundary",
            "candidate_sources": [{
                "paper_id": "VP-001", "title": "Accepted Fixture", "venue": "Fixture Journal",
                "accepted_status": "published", "official_url": "https://example.org/accepted",
            }],
            "reviewer": {"id": "main-model"},
        })
        metrics = {
            "page_count": 8,
            "unique_cited_references": 22,
            "total_figures": 3,
            "table_count": 2,
            "evaluation_count": 2,
            "figure_roles": {"measured evidence": 2, "method explanation": 1},
            "evaluation_kinds": {"matched comparison": 1, "robustness analysis": 1},
            "evidence_dimensions": {"conditions": 2, "comparators": 1},
            "evaluation_difficulty": {
                "rating": "moderate", "drivers": ["matched observations"],
                "rationale": "requires controlled comparisons but no specialized facility",
            },
        }
        papers = [{
            "title": "Accepted Fixture", "venue": "Fixture Journal", "year": 2026,
            "article_type": "method", "source": {"url": "https://example.org/accepted"},
            "pdf": {"path": "calibration/papers/accepted.pdf", "sha256": lifecycle.sha256_file(venue_pdf)},
            "relevance": "same field and archetype", "metrics": metrics,
        }]
        self.venue_payload = {
            "user_policy_id": self.policy_id,
            "user_policy_hash": lifecycle.sha256_file(self.root / f"intake/{self.policy_id}.json"),
            "venue_corpus_id": self.corpus_id,
            "venue_corpus_hash": lifecycle.sha256_file(self.root / f"calibration/{self.corpus_id}.json"),
            "venue_basis": {"type": "USER_SELECTED", "venues": ["Fixture Journal"]},
            "research_scope": "sparse-observation treatment-effect estimation",
            "corpus_criteria": {"accepted": True, "comparable_archetype": True},
            "papers": papers,
            "aggregates": lifecycle.compute_venue_aggregates(papers),
            "sample_sufficiency": {
                "verdict": "SUFFICIENT_WITH_LIMITATIONS", "rationale": "fixture coverage",
                "coverage": "one synthetic comparable paper", "stopping_reason": "test boundary",
            },
            "evaluation_difficulty_synthesis": {
                "typical": "moderate", "drivers": ["matched comparisons"], "uncertainty": "single-paper fixture",
            },
            "limitations": ["single synthetic paper"],
            "reviewer": {"id": "main-model"},
        }
        self.venue_id = lifecycle.register_venue_profile(self.root, self.venue_payload)
        self.venue_judgment_id = lifecycle.set_venue_judgment(self.root, {
            "venue_profile_id": self.venue_id,
            "venue_profile_hash": lifecycle.sha256_file(self.root / f"calibration/{self.venue_id}.json"),
            "verdict": "PASS_WITH_EXPLAINED_DEVIATION",
            "comparability": "same field and paper archetype",
            "profile_confidence": "LOW_FIXTURE_ONLY",
            "mean_distortion_review": "single item is retained as an observation, not a quota",
            "evidence_program_review": "evaluation count, kinds, dimensions, and difficulty are explicit",
            "limitations": ["synthetic one-paper fixture"],
            "reviewer": {"id": "independent-fixture"},
        })
        lifecycle.write_json(self.root / "grounding/benchmark_candidates.json", {
            "candidates": [],
            "decision": {
                "classification": "NO_VALID_PUBLIC_BENCHMARK",
                "rationale": "no benchmark matches the estimand",
                "search_scope": "primary papers, official repositories, and benchmark indexes",
            },
        })
        candidates_payload = {
            "idea_seed_id": self.seed_id,
            "idea_seed_hash": lifecycle.sha256_file(self.root / f"intake/{self.seed_id}.json"),
            "science_profile_id": self.science_id,
            "science_profile_hash": lifecycle.sha256_file(self.root / f"calibration/{self.science_id}.json"),
            "venue_profile_id": self.venue_id,
            "venue_profile_hash": lifecycle.sha256_file(self.root / f"calibration/{self.venue_id}.json"),
            "generation_basis": {"seed": "preserved", "closest_work": "compared", "benchmark": "searched"},
            "fresh_search": {"performed": True, "cutoff": "2026-07-13"},
            "candidates": [{
                "candidate_id": "KEEP-SEED", **IDEA,
                "closest_work": [{"title": "Calibrated Sparse Estimation", "difference": "new mechanism test"}],
                "evidence": ["calibration/papers/science-source.txt"],
                "why_might_fail": ["calibration may not transfer under severe missingness"],
            }],
            "limitations": ["fixture candidate set"],
            "reviewer": {"id": "main-model"},
        }
        self.candidates_id = lifecycle.register_idea_candidates(self.root, candidates_payload)
        self.selection_id = lifecycle.register_idea_selection(self.root, {
            "idea_candidates_id": self.candidates_id,
            "idea_candidates_hash": lifecycle.sha256_file(self.root / f"discovery/{self.candidates_id}.json"),
            "selected_candidate_id": "KEEP-SEED",
            "decision": "SELECT",
            "comparison": "single faithful candidate retained after closest-work comparison",
            "rationale": "falsifiable and feasible within the user envelope",
            "evidence": ["calibration/papers/science-source.txt"],
            "uncertainty": ["mechanism transfer remains unverified"],
            "rejected_candidates": [],
            "reviewer": {"id": "main-model"},
        })
        self.idea_id = lifecycle.register_idea(self.root, IDEA, None, "L0", None)
        self.claim_id = lifecycle.register_claim(self.root, {
            "claim_text": "The calibrated estimator reduces sparse-regime error",
            "claim_type": "empirical result claim", "essential": True, "strength": "bounded",
            "scope": "30-70% missingness", "required_evidence": ["claim-linked held-out evaluation"],
        })

    def tearDown(self):
        self.temp.cleanup()

    def judgment(self, gate: str, evidence: list[str], *, independent: bool = True, suffix: str = "") -> str:
        relative = f"reports/gates/{gate}{suffix}.judgment.json"
        lifecycle.write_json(self.root / relative, {
            "artifact_type": "scientific_judgment", "gate": gate, "verdict": "PASS",
            "conclusion": "The bounded fixture decision is supported.",
            "checks": [{
                "question": "Is the bounded decision supported?", "verdict": "SUPPORTED",
                "rationale": "The cited fixture evidence is explicit.", "evidence": evidence,
            }],
            "limitations": ["synthetic fixture"], "blocking_issues": [],
            "reviewer": {
                "id": f"fixture-{gate}{suffix}", "model_or_human": "test-model",
                "independent": independent, "context_artifacts": evidence,
            },
        })
        return relative

    def research_program(self) -> dict:
        feasibility_evidence = self.root / "reports/design/feasibility.json"
        feasibility_evidence.write_text("measured one representative unit", encoding="utf-8")
        return {
            "user_policy_id": self.policy_id,
            "user_policy_hash": lifecycle.sha256_file(self.root / f"intake/{self.policy_id}.json"),
            "science_profile_id": self.science_id,
            "science_profile_hash": lifecycle.sha256_file(self.root / f"calibration/{self.science_id}.json"),
            "venue_profile_id": self.venue_id,
            "venue_profile_hash": lifecycle.sha256_file(self.root / f"calibration/{self.venue_id}.json"),
            "claim_ids": [self.claim_id],
            "evaluation_units": [{
                "unit_id": "EU-001", "kind": "observational_analysis", "claim_ids": [self.claim_id],
                "question": "Does calibration reduce held-out sparse-regime error?",
                "why_it_tests_claim": "directly measures the bounded claim",
                "protocol_summary": "matched split, fixed preprocessing, held-out confirmation",
                "positive_interpretation": "supports the bounded claim",
                "negative_interpretation": "weakens or rejects the claim",
                "confounders": ["extra compute"], "out_of_scope_conclusions": ["dense-regime superiority"],
                "difficulty": {"rating": "moderate", "drivers": ["matched split"]},
                "stop_condition": "predeclared precision or resource limit",
            }],
            "study_inputs": ["matched observation set"],
            "protocol": {"split": "held out", "preprocessing": "fixed before confirmation"},
            "outcomes": ["absolute estimation error"],
            "comparators": ["matched calibrated baseline"],
            "analysis_plan": {"estimand": "paired error difference", "uncertainty": "interval over groups"},
            "test_set_policy": {"max_test_access": 1, "development": "validation only"},
            "stop_conditions": ["budget exhausted", "hypothesis rejected", "protocol invalid"],
            "resource_plan": {
                "stage_budgets": {"acquisition": "1 hour", "pilot": "2 hours", "confirmation": "4 hours", "publication": "4 hours"},
                "deadline_fit": True, "reserve": {"hours": 2},
                "replan_triggers": ["projected completion exceeds deadline"],
                "allocation_rationale": "the measured dominant-cost unit fits the confirmed envelope",
                "max_runs": 12, "max_branches": 3, "max_branch_depth": 2,
                "resource_envelope": "intake/resource-envelope.json",
                "resource_envelope_hash": lifecycle.sha256_file(self.root / "intake/resource-envelope.json"),
            },
            "feasibility": {
                "status": "MEASURED", "budget_fit": True, "deadline_fit": True,
                "estimated_cost": {"seconds_per_unit": 1},
                "probes": [{
                    "component": "dominant evaluation unit", "status": "MEASURED",
                    "rationale": "dominates projected runtime", "measurement": "1 second per unit",
                    "evidence": ["reports/design/feasibility.json"],
                }],
                "projection_rationale": "measured unit cost multiplied by the frozen run program plus reserve",
            },
            "benchmark_policy": {
                "artifact": "grounding/benchmark_candidates.json",
                "artifact_hash": lifecycle.sha256_file(self.root / "grounding/benchmark_candidates.json"),
                "classification": "NO_VALID_PUBLIC_BENCHMARK", "action": "USE_CONTRACT_ALTERNATIVE",
                "rationale": "the searched public benchmarks do not match the estimand",
            },
            "venue_alignment": {
                "observed_evidence_dimensions": self.venue_payload["aggregates"]["evidence_dimension_means"],
                "selected_program_summary": "one primary held-out unit plus mechanism-sensitive checks",
                "rationale": "claim validity and resources determine the program; venue observations calibrate completeness",
                "deviations": [],
            },
            "revalidation_policy": {
                "required": False, "rationale": "standard-risk fixture",
                "independence_axis": "new observation groups", "trigger": "material Idea revision or disputed result",
            },
            "idea_iteration_policy": {
                "allowed_levels": ["L0", "L1", "L2"], "diagnosis_before_revision": True,
                "negative_result_policy": "preserve and weaken or reject claims",
                "stop_rule": "bounded branches and no metric-only winner selection",
            },
        }

    def freeze_program(self, *, action: str = "FREEZE_RESEARCH_PROGRAM", suffix: str = "") -> str:
        program = self.research_program()
        if suffix:
            program["protocol"] = {**program["protocol"], "revision": suffix}
        candidate = f"grounding/research-program{suffix}.candidate.json"
        lifecycle.write_json(self.root / candidate, program)
        evidence = [candidate, "reports/design/feasibility.json"]
        judgment = self.judgment("G3", evidence, suffix=suffix)
        approval = lifecycle.record_approval(self.root, action, "APPROVED", self.idea_id, [judgment], "user")
        return lifecycle.freeze_research_program(self.root, program, approval)

    def lock_repo_and_environment(self) -> None:
        checkout = self.root / "code/upstream/repo"
        checkout.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(checkout)], check=True)
        subprocess.run(["git", "-C", str(checkout), "config", "user.email", "fixture@example.org"], check=True)
        subprocess.run(["git", "-C", str(checkout), "config", "user.name", "Fixture"], check=True)
        (checkout / "README.md").write_text("fixture", encoding="utf-8")
        subprocess.run(["git", "-C", str(checkout), "add", "README.md"], check=True)
        subprocess.run(["git", "-C", str(checkout), "commit", "-q", "-m", "fixture"], check=True)
        subprocess.run(["git", "-C", str(checkout), "remote", "add", "origin", "https://example.org/repo.git"], check=True)
        commit = subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True).strip()
        lifecycle.register_repo(self.root, {
            "purpose": "author implementation", "url": "https://example.org/repo.git", "commit": commit,
            "official_status": "official", "license": "MIT", "local_path": "code/upstream/repo",
            "modification_mode": "read_only",
        })
        lifecycle.lock_environment(self.root, {
            "os": "linux", "python": "3.12", "framework": "domain-runtime-1",
            "dependencies": ["fixture==1"], "hardware": {"cpu": "fixture"},
        })

    def run_payload(self, unit_id: str = "EU-001", *, branch_id: str | None = None) -> dict:
        return {
            "run_type": "pilot", "evaluation_unit_ids": [unit_id], "command": "run-fixture",
            "replicate_id": "group-1", "random_seed": None, "config": {"mode": "fixture"},
            "input_artifact_hashes": {"observations": "d" * 64}, "protocol_hash": "e" * 64,
            "status": "completed", "failure_class": "NONE", "test_set_accessed": False,
            "test_access_purpose": "none", **({"branch_id": branch_id} if branch_id else {}),
        }

    def test_schema_inventory_is_v5_and_valid_json(self):
        schema_dir = MODULE_PATH.parents[1] / "schemas"
        expected = {
            "idea_seed.schema.json", "idea_candidates.schema.json", "idea_selection.schema.json",
            "paper_wiki_snapshot.schema.json", "science_profile.schema.json", "venue_profile.schema.json",
            "research_program_contract.schema.json", "publication_contract.schema.json",
            "publication_judgment.schema.json", "figure_routing.schema.json", "run_manifest.schema.json",
        }
        self.assertTrue(expected.issubset({path.name for path in schema_dir.glob("*.json")}))
        for name in expected:
            self.assertIsInstance(json.loads((schema_dir / name).read_text(encoding="utf-8")), dict)

    def test_complete_discovery_chain_is_valid_and_has_one_active_idea(self):
        self.assertEqual(lifecycle.validate_root(self.root), [])
        state = lifecycle.load_state(self.root)
        self.assertEqual(state["active"]["idea_id"], self.idea_id)
        self.assertNotIn("contract_id", state["active"])

    def test_first_active_idea_cannot_bypass_candidate_selection(self):
        other = Path(self.temp.name) / "other"
        lifecycle.init_layout(other, "proposal", "bypass")
        with self.assertRaisesRegex(ValueError, "candidate set and selection"):
            lifecycle.register_idea(other, IDEA, None, "L0", None)

    def test_science_profile_is_bound_to_real_full_text(self):
        source = self.root / "calibration/papers/science-source.txt"
        source.write_text("tampered", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "hash-mismatched"):
            lifecycle.register_science_profile(self.root, self.science_payload)

    def test_venue_aggregation_accepts_domain_specific_role_vocabularies(self):
        first = self.venue_payload["papers"][0]["metrics"]
        second = {
            **first, "figure_roles": {"microscopy": 1, "mechanism diagram": 2},
            "evaluation_kinds": {"specimen study": 2},
            "evidence_dimensions": {"specimens": 4},
        }
        aggregates = lifecycle.compute_venue_aggregates([
            {"metrics": first}, {"metrics": second},
        ])
        self.assertIn("microscopy", aggregates["figure_role_means"])
        self.assertIn("specimens", aggregates["evidence_dimension_means"])

    def test_venue_profile_cannot_change_the_prefrozen_source_set(self):
        changed = json.loads(json.dumps(self.venue_payload))
        changed["papers"][0]["source"] = {"url": "https://example.org/different"}
        with self.assertRaisesRegex(ValueError, "exactly match"):
            lifecycle.register_venue_profile(self.root, changed)

    def test_research_program_requires_scoped_freeze_action(self):
        with self.assertRaisesRegex(ValueError, "FREEZE_RESEARCH_PROGRAM"):
            self.freeze_program(action="FREEZE_CONTRACT")
        program_id = self.freeze_program()
        stored = lifecycle.read_json(self.root / f"contracts/{program_id}.json")
        self.assertEqual(stored["research_program_id"], program_id)
        self.assertNotIn("contract_id", stored)

    def test_formal_run_requires_known_evaluation_unit_and_locks(self):
        self.freeze_program()
        with self.assertRaisesRegex(ValueError, "unknown evaluation units"):
            lifecycle.register_run(self.root, self.run_payload("EU-UNKNOWN"))
        with self.assertRaisesRegex(ValueError, "repository and environment locks"):
            lifecycle.register_run(self.root, self.run_payload())
        self.lock_repo_and_environment()
        run_id = lifecycle.register_run(self.root, self.run_payload())
        manifest = lifecycle.read_json(self.root / f"experiments/runs/{run_id}/run_manifest.json")
        self.assertEqual(manifest["evaluation_unit_ids"], ["EU-001"])
        self.assertEqual(manifest["research_program_id"], lifecycle.load_state(self.root)["active"]["research_program_id"])

    def test_result_fact_must_follow_claim_linked_unit_run_and_raw_hashes(self):
        self.freeze_program()
        self.lock_repo_and_environment()
        run_id = lifecycle.register_run(self.root, self.run_payload())
        raw = self.root / "evidence/results/raw.json"
        raw.write_text('{"value": 0.42}', encoding="utf-8")
        aggregation = self.root / "code/integration/aggregate.py"
        aggregation.write_text("print(0.42)", encoding="utf-8")
        fact = {
            "fact_id": "F-001", "claim_ids": [self.claim_id], "value": 0.42, "unit": "absolute error",
            "run_ids": [run_id], "source_artifacts": ["evidence/results/raw.json"],
            "source_hashes": {"evidence/results/raw.json": lifecycle.sha256_file(raw)},
            "aggregation": {
                "method": "direct fixture extraction", "code_artifact": "code/integration/aggregate.py",
                "code_hash": lifecycle.sha256_file(aggregation),
            },
        }
        (self.root / "evidence/results/results-manifest.jsonl").write_text(json.dumps(fact) + "\n", encoding="utf-8")
        lifecycle.validate_results_manifest(self.root)
        fact["claim_ids"] = ["C-999"]
        (self.root / "evidence/results/results-manifest.jsonl").write_text(json.dumps(fact) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unknown/inactive claims"):
            lifecycle.validate_results_manifest(self.root)

    def test_major_idea_evolution_requires_approval_and_invalidates_program(self):
        self.freeze_program()
        evolved = {**IDEA, "hypothesis": "A stratified calibration mechanism reduces sparse-regime error"}
        with self.assertRaisesRegex(ValueError, "require a recorded approved"):
            lifecycle.register_idea(self.root, evolved, self.idea_id, "L2", None)
        evidence = self.root / "decisions/idea-evolution-review.txt"
        evidence.write_text("user reviewed the estimand change", encoding="utf-8")
        approval = lifecycle.record_approval(
            self.root, "EVOLVE_IDEA", "APPROVED", self.idea_id,
            ["decisions/idea-evolution-review.txt"], "user",
        )
        lifecycle.register_idea(self.root, evolved, self.idea_id, "L2", approval)
        self.assertIsNone(lifecycle.load_state(self.root)["active"]["research_program_id"])

    def test_research_program_revision_invalidates_old_g3(self):
        first = self.freeze_program()
        first_path = f"contracts/{first}.json"
        judgment = self.judgment("G3", [first_path], suffix="-gate")
        lifecycle.set_gate(self.root, "G3", "PASS", [first_path], "frozen program reviewed", "fixture", judgment)
        self.assertIn("G3", lifecycle.load_state(self.root)["gates"])
        self.freeze_program(suffix="-v2")
        self.assertNotIn("G3", lifecycle.load_state(self.root)["gates"])

    def test_negative_hypothesis_result_is_a_valid_evidence_backed_stop(self):
        evidence = self.root / "reports/experiments/negative-result.json"
        evidence.write_text('{"supported": false}', encoding="utf-8")
        lifecycle.stop(
            self.root, "STOPPED_HYPOTHESIS_REJECTED", "held-out evidence rejected the hypothesis",
            ["reports/experiments/negative-result.json"],
        )
        state = lifecycle.load_state(self.root)
        self.assertEqual(state["phase"], "STOPPED_HYPOTHESIS_REJECTED")
        stop_record = lifecycle.read_json(self.root / "experiments/state.json")["stop_reason"]
        self.assertIn("negative-result.json", stop_record["evidence"][0])

    def test_branch_ledger_preserves_an_unsupported_alternative(self):
        self.freeze_program()
        self.lock_repo_and_environment()
        branch_evidence = self.root / "reports/experiments/branch-question.txt"
        branch_evidence.write_text("alternative calibration question", encoding="utf-8")
        branch_id = lifecycle.propose_branch(self.root, {
            "question": "Does stratification explain the signal?", "change_class": "diagnostic",
            "hypothesis": "stratification isolates the effect", "evaluation_unit_ids": ["EU-001"],
            "expected_observations": ["error decreases only in one stratum"],
            "rationale": "discriminates a plausible alternative", "estimated_cost": "one bounded run",
            "evidence": ["reports/experiments/branch-question.txt"], "stop_condition": "one diagnostic run",
        })
        lifecycle.register_run(self.root, self.run_payload(branch_id=branch_id))
        outcome = self.root / "reports/experiments/branch-outcome.txt"
        outcome.write_text("alternative unsupported", encoding="utf-8")
        lifecycle.evaluate_branch(self.root, branch_id, {
            "outcome": "UNSUPPORTED", "scientific_interpretation": "stratification does not explain the signal",
            "decision": "RETAIN_DIAGNOSTIC", "claim_implications": "no claim expansion",
            "evidence": ["reports/experiments/branch-outcome.txt"], "reviewer": {"id": "main-model"},
            "limitations": ["single diagnostic run"],
        })
        branch = lifecycle.read_json(self.root / "experiments/branch-registry.json")["branches"][0]
        self.assertEqual(branch["evaluation"]["outcome"], "UNSUPPORTED")
        self.assertEqual(branch["evaluation"]["decision"], "RETAIN_DIAGNOSTIC")

    def test_manuscript_registration_keeps_only_reader_facing_files(self):
        source = Path(self.temp.name) / "paper"
        (source / "sections").mkdir(parents=True)
        (source / "research").mkdir()
        (source / "main.tex").write_text("\\input{sections/body}", encoding="utf-8")
        (source / "sections/body.tex").write_text("reader-facing body", encoding="utf-8")
        (source / "research/internal.json").write_text('{"sha256": "secret audit data"}', encoding="utf-8")
        manuscript_id = lifecycle.register_manuscript(self.root, source)
        record = lifecycle.read_json(self.root / f"manuscript/{manuscript_id}.json")
        paths = {item["path"] for item in record["files"]}
        self.assertEqual(paths, {"main.tex", "sections/body.tex"})

    def test_publication_judgment_requires_coherence_filler_and_actual_pdf_review(self):
        source = Path(self.temp.name) / "publication"
        source.mkdir()
        (source / "main.tex").write_text("reader-facing paper", encoding="utf-8")
        manuscript_id = lifecycle.register_manuscript(self.root, source)
        publication_id = "publication-contract-v-999"
        lifecycle.write_json(self.root / f"contracts/{publication_id}.json", {"targets": {"page_range": [7, 9]}})
        state = lifecycle.load_state(self.root)
        state["active"]["publication_contract_id"] = publication_id
        lifecycle.save_state(self.root, state, "publication_fixture")
        pdf = Path(self.temp.name) / "paper.pdf"
        pdf.write_bytes(b"fixture pdf")
        lifecycle.register_latex_verdict(self.root, {
            "compiled": True, "error_count": 0, "input_hash": "a" * 64, "page_count": 8,
        }, pdf)
        latex = lifecycle.read_json(self.root / "reports/manuscript/latex-verdict.json")
        contract_path = self.root / f"contracts/{publication_id}.json"
        manuscript_path = self.root / f"manuscript/{manuscript_id}.json"
        payload = {
            "publication_contract_id": publication_id,
            "publication_contract_hash": lifecycle.sha256_file(contract_path),
            "manuscript_id": manuscript_id, "manuscript_hash": lifecycle.sha256_file(manuscript_path),
            "figure_role_completeness": "all planned roles are present",
            "citation_relevance": "citations support their local claims",
            "experiment_claim_coverage": "claims match the available evidence",
            "venue_scale_substance": "length comes from scientific substance, not padding",
            "claim_argument_consistency": "abstract, body, and conclusion use the same bounded claims",
            "cross_section_consistency": "terms, assumptions, and notation are consistent",
            "method_result_alignment": "reported outcomes correspond to the declared protocol",
            "redundancy_and_filler_review": "no duplicated argument or audit appendix remains",
            "internal_provenance_boundary": "hashes and gate ledgers remain in the artifact package",
            "limitations_and_negative_results": "limitations and negative outcomes are visible",
            "rendered_pdf_review": {
                "pdf_sha256": latex["pdf_sha256"], "actual_pdf_reviewed": True,
                "layout_findings": [], "blocking_issues": [],
            },
            "page_scale": {
                "actual_pages": 8, "target_range": [7, 9], "verdict": "WITHIN_TARGET",
                "rationale": "the compiled paper is within the selected calibration range",
            },
            "deviations": [], "verdict": "PASS", "reviewer": {"id": "main-model"},
        }
        incomplete = dict(payload)
        incomplete.pop("redundancy_and_filler_review")
        with self.assertRaisesRegex(ValueError, "redundancy_and_filler_review"):
            lifecycle.register_publication_judgment(self.root, incomplete)
        judgment_id = lifecycle.register_publication_judgment(self.root, payload)
        self.assertTrue((self.root / f"reports/manuscript/{judgment_id}.json").is_file())

    def test_high_risk_semantic_gate_requires_independent_review(self):
        other = Path(self.temp.name) / "high-risk"
        lifecycle.init_layout(other, "high_risk", "risk")
        context = other / "reports/design/context.txt"
        context.parent.mkdir(parents=True, exist_ok=True)
        context.write_text("risk context", encoding="utf-8")
        judgment = other / "reports/gates/G3.judgment.json"
        lifecycle.write_json(judgment, {
            "artifact_type": "scientific_judgment", "gate": "G3", "verdict": "PASS",
            "conclusion": "fixture", "checks": [{
                "question": "valid?", "verdict": "SUPPORTED", "rationale": "fixture",
                "evidence": ["reports/design/context.txt"],
            }],
            "limitations": ["fixture"], "blocking_issues": [],
            "reviewer": {
                "id": "same-context-reviewer", "model_or_human": "test-model", "independent": False,
                "context_artifacts": ["reports/design/context.txt"],
            },
        })
        state = lifecycle.load_state(other)
        with self.assertRaisesRegex(ValueError, "independent reviewer"):
            lifecycle.validate_judgment(other, state, "G3", "PASS", "reports/gates/G3.judgment.json")

    def test_resource_envelope_change_invalidates_program_but_preserves_grounding(self):
        self.freeze_program()
        lifecycle.register_resource_envelope(self.root, {
            "source": "USER_PROVIDED", "deadline": {"status": "KNOWN", "max_elapsed_hours": 12, "hard": True},
            "compute": [{"backend": "local", "hardware": "fixture", "count": 1}],
            "financial_limit": {"currency": "USD", "amount": 5}, "human_review": {"hours": 1},
            "priorities": ["scientific validity"], "constraints": ["shorter deadline"],
            "assumptions": [], "confirmed_by_user": True,
        })
        state = lifecycle.load_state(self.root)
        self.assertIsNone(state["active"]["research_program_id"])
        self.assertEqual(state["active"]["idea_id"], self.idea_id)
        self.assertEqual(state["active"]["science_profile_id"], self.science_id)

    def test_secret_redaction_and_private_key_audit(self):
        self.assertNotIn("secret-value", lifecycle.redact_secrets("API_KEY=secret-value"))
        private_key = self.root / "id_ed25519"
        private_key.write_text("-----BEGIN PRIVATE KEY-----\nfixture", encoding="utf-8")
        errors = lifecycle.validate_root(self.root)
        self.assertTrue(any("credential-like file" in item or "private key" in item for item in errors))

    def test_g0_and_phase_transitions_use_registered_artifacts(self):
        policy_path = f"intake/{self.policy_id}.json"
        lifecycle.set_gate(self.root, "G0", "PASS", [policy_path], "policy is complete", "deterministic")
        lifecycle.transition(self.root, "USER_POLICY_LOCKED")
        lifecycle.transition(self.root, "SCIENCE_PROFILED")
        self.assertEqual(lifecycle.load_state(self.root)["phase"], "SCIENCE_PROFILED")


if __name__ == "__main__":
    unittest.main()
