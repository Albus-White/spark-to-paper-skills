from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


TEST_DIR = Path(__file__).resolve().parent
fixture_spec = importlib.util.spec_from_file_location("lifecycle_fixture_module", TEST_DIR / "test_lifecycle.py")
fixture_module = importlib.util.module_from_spec(fixture_spec)
assert fixture_spec.loader
fixture_spec.loader.exec_module(fixture_module)
lifecycle = fixture_module.lifecycle


class ProposalEndToEndTest(unittest.TestCase):
    def test_proposal_reaches_release_with_actual_pdf_judgment(self):
        fixture = fixture_module.LifecycleV5Test("test_schema_inventory_is_v5_and_valid_json")
        fixture.setUp()
        try:
            program = fixture.research_program()
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp) / "research"
                shutil.copytree(fixture.root, root)
                state = lifecycle.load_state(root)
                state["profile"] = "proposal"
                state["phase"] = "INTAKE"
                state["gates"] = {}
                state["blockers"] = []
                state["invalidations"] = []
                state["active"]["research_program_id"] = None
                state["active"]["publication_contract_id"] = None
                state["active"]["bibliography_coverage"] = None
                state["active"]["figure_routing"] = None
                state["active"]["manuscript_id"] = None
                state["active"]["publication_judgment_id"] = None
                state["active"]["schedule_checkpoint"] = None
                state["active"]["release_audit_id"] = None
                state["policy"] = {
                    "phase_sequence": lifecycle.phase_sequence("proposal"),
                    "required_gates": {
                        phase: lifecycle.required_gates_for("proposal", phase)
                        for phase in lifecycle.phase_sequence("proposal")
                    },
                }
                lifecycle.save_state(root, state, "proposal_fixture")

                def write_judgment(gate: str, evidence: list[str], label: str = "gate") -> str:
                    relative = f"reports/gates/{gate}.proposal.{label}.judgment.json"
                    lifecycle.write_json(root / relative, {
                        "artifact_type": "scientific_judgment", "gate": gate, "verdict": "PASS",
                        "conclusion": "The proposal statement is bounded by the cited artifacts.",
                        "checks": [{
                            "question": "Is the proposal claim calibrated?", "verdict": "SUPPORTED",
                            "rationale": "The proposal preserves unknown outcomes and explicit limitations.",
                            "evidence": evidence,
                        }],
                        "limitations": ["synthetic end-to-end fixture"], "blocking_issues": [],
                        "reviewer": {
                            "id": f"proposal-{gate}", "model_or_human": "test-model",
                            "independent": True, "context_artifacts": evidence,
                        },
                    })
                    return relative

                def set_semantic_gate(gate: str, evidence: list[str]) -> None:
                    judgment = write_judgment(gate, evidence)
                    lifecycle.set_gate(root, gate, "PASS", evidence, "proposal fixture reviewed", "fixture", judgment)

                policy_id = state["active"]["user_policy_id"]
                venue_id = state["active"]["venue_profile_id"]
                venue_judgment_id = state["active"]["venue_profile_judgment_id"]
                idea_id = state["active"]["idea_id"]

                policy_path = f"intake/{policy_id}.json"
                lifecycle.set_gate(root, "G0", "PASS", [policy_path], "policy complete", "fixture")
                lifecycle.transition(root, "USER_POLICY_LOCKED")
                lifecycle.transition(root, "SCIENCE_PROFILED")
                v1_evidence = [f"calibration/{venue_id}.json", f"calibration/{venue_judgment_id}.json"]
                lifecycle.set_gate(root, "V1", "PASS", v1_evidence, "venue calibrated", "fixture")
                lifecycle.transition(root, "VENUE_PROFILED")
                lifecycle.transition(root, "IDEA_DRAFTED")
                set_semantic_gate("G1", [f"ideas/{idea_id}.json"])
                set_semantic_gate("G2", ["grounding/benchmark_candidates.json"])
                lifecycle.transition(root, "IDEA_GROUNDED")

                lifecycle.write_json(root / "grounding/research-program.candidate.json", program)
                g3_evidence = ["grounding/research-program.candidate.json", "reports/design/feasibility.json"]
                g3_judgment = write_judgment("G3", g3_evidence, "freeze")
                approval = lifecycle.record_approval(
                    root, "FREEZE_RESEARCH_PROGRAM", "APPROVED", idea_id, [g3_judgment], "user"
                )
                program_id = lifecycle.freeze_research_program(root, program, approval)
                lifecycle.set_gate(
                    root, "G3", "PASS", [f"contracts/{program_id}.json"],
                    "research program frozen", "fixture", write_judgment("G3", [f"contracts/{program_id}.json"], "gate"),
                )
                lifecycle.transition(root, "RESEARCH_CONTRACT_FROZEN")

                reconciliation = root / "reports/design/proposal-claim-reconciliation.txt"
                reconciliation.write_text("Outcome remains unknown; claim is prospective.", encoding="utf-8")
                lifecycle.update_claim(
                    root, fixture.claim_id, "INCONCLUSIVE", "KEEP_PROSPECTIVE",
                    ["reports/design/proposal-claim-reconciliation.txt"],
                    "We hypothesize that the method may reduce sparse-regime error.",
                )
                set_semantic_gate("G15", ["claims/claim-registry.json"])
                lifecycle.transition(root, "CLAIMS_RECONCILED")

                policy_file = root / f"intake/{policy_id}.json"
                venue_file = root / f"calibration/{venue_id}.json"
                envelope = lifecycle.derive_publication_envelope(
                    lifecycle.read_json(policy_file), lifecycle.read_json(venue_file)
                )
                publication = {
                    "user_policy_id": policy_id, "user_policy_hash": lifecycle.sha256_file(policy_file),
                    "venue_profile_id": venue_id, "venue_profile_hash": lifecycle.sha256_file(venue_file),
                    "research_program_id": program_id,
                    "research_program_hash": lifecycle.sha256_file(root / f"contracts/{program_id}.json"),
                    "claim_registry_hash": lifecycle.sha256_file(root / "claims/claim-registry.json"),
                    "idea_id": idea_id, "claim_ids": [fixture.claim_id], "paper_archetype": "proposal",
                    "calibration_envelope": envelope,
                    "targets": {
                        "page_range": [8, 8], "minimum_unique_cited_references": 22,
                        "figure_count": 0, "table_count": 0,
                    },
                    "target_rationales": {
                        "page_range": "matches the comparable fixture paper",
                        "minimum_unique_cited_references": "matches relevant source density",
                        "figure_count": "the synthetic proposal fixture exercises the no-figure route",
                        "table_count": "the synthetic proposal fixture contains no tabular artifact",
                    },
                    "section_plan": [{"section_id": "body", "purpose": "present the bounded proposal"}],
                    "figure_plan": [], "table_plan": [],
                    "citation_coverage_requirements": {"all_active_claims": True},
                    "deadline_allocation": {"writing": "within the frozen proposal reserve"},
                    "deviations": [
                        {"metric": "total_figures", "rationale": "synthetic lifecycle fixture", "evidence": ["no visual claim"]},
                        {"metric": "table_count", "rationale": "synthetic lifecycle fixture", "evidence": ["no tabular claim"]},
                    ],
                    "manuscript_content_policy": {
                        "internal_provenance_location": "artifact_package",
                        "reader_relevant_reproducibility_only": True,
                        "forbid_page_filler": True,
                        "allowed_internal_identifiers": [],
                    },
                }
                candidate_path = "reports/manuscript/publication-contract.candidate.json"
                lifecycle.write_json(root / candidate_path, publication)
                publication_approval = lifecycle.record_approval(
                    root, "FREEZE_PUBLICATION_CONTRACT", "APPROVED", idea_id, [candidate_path], "user"
                )
                publication_id = lifecycle.freeze_publication_contract(root, publication, publication_approval)
                schedule_evidence = root / "reports/schedule/publication.txt"
                schedule_evidence.write_text("proposal publication path fits", encoding="utf-8")
                lifecycle.record_schedule_checkpoint(root, {
                    "research_program_id": program_id,
                    "research_program_hash": lifecycle.sha256_file(root / f"contracts/{program_id}.json"),
                    "completed_phase": "CLAIMS_RECONCILED", "next_phase": "PUBLICATION_CONTRACT_FROZEN",
                    "elapsed": "fixture", "remaining_schedule": {"hours": 1},
                    "projected_completion": "within deadline", "deadline_fit": True,
                    "replan_required": False, "action": "CONTINUE",
                    "evidence": ["reports/schedule/publication.txt"], "reviewer": {"id": "fixture"},
                })
                lifecycle.set_gate(root, "M1", "PASS", [f"contracts/{publication_id}.json"], "publication frozen", "fixture")
                lifecycle.transition(root, "PUBLICATION_CONTRACT_FROZEN")

                keys = [f"ref-{index:02d}" for index in range(22)]
                contract_path = root / f"contracts/{publication_id}.json"
                coverage = lifecycle.register_bibliography_coverage(root, {
                    "publication_contract_id": publication_id,
                    "publication_contract_hash": lifecycle.sha256_file(contract_path),
                    "planned_citation_keys": keys,
                    "sources": [{
                        "bibkey": key, "doi": f"10.1000/{index}",
                        "metadata_verification_source": "fixture registry", "source_type": "primary",
                        "supported_claims": [fixture.claim_id], "intended_sections": ["body"],
                        "evidence_note": "grounds the proposal context", "limitations": ["synthetic source"],
                        "inspected_status": "FULL_TEXT",
                    } for index, key in enumerate(keys)],
                    "claim_coverage": [{"claim_id": fixture.claim_id, "source_keys": keys}],
                    "source_quality_review": {"verdict": "PASS", "rationale": "fixture coverage"},
                    "reviewer": {"id": "main-model"},
                })
                lifecycle.set_gate(root, "M2", "PASS", [coverage], "coverage complete", "fixture")
                lifecycle.transition(root, "CITATIONS_COMPLETE")

                paper = Path(temp) / "paper"
                (paper / "sections").mkdir(parents=True)
                (paper / "main.tex").write_text("\\input{sections/body}", encoding="utf-8")
                (paper / "sections/body.tex").write_text("A bounded proposal with unknown outcomes.", encoding="utf-8")
                manuscript_id = lifecycle.register_manuscript(root, paper)
                manuscript_path = root / f"manuscript/{manuscript_id}.json"
                lifecycle.set_gate(root, "M3", "PASS", [f"manuscript/{manuscript_id}.json"], "draft complete", "fixture")
                lifecycle.transition(root, "MANUSCRIPT_DRAFTED")

                refinement = "reports/manuscript/refinement-report.json"
                lifecycle.write_json(root / refinement, {
                    "input_manuscript_id": manuscript_id,
                    "input_manuscript_hash": lifecycle.sha256_file(manuscript_path),
                    "issues_addressed": ["prospective language and consistency"],
                    "claim_preservation": "preserved", "reviewer": {"id": "main-model"},
                })
                lifecycle.set_gate(root, "M4", "PASS", [refinement], "refined", "fixture")
                lifecycle.transition(root, "MANUSCRIPT_REFINED")
                set_semantic_gate("G16", [f"manuscript/{manuscript_id}.json"])
                lifecycle.transition(root, "MANUSCRIPT_HARDENED")

                routing = lifecycle.register_figure_routing(root, {
                    "publication_contract_id": publication_id,
                    "publication_contract_hash": lifecycle.sha256_file(contract_path),
                    "figures": [],
                })
                figure_report = "reports/manuscript/figure-program-report.json"
                lifecycle.write_json(root / figure_report, {
                    "publication_contract_id": publication_id, "expected_figure_ids": [],
                    "completed_figure_ids": [], "route_validation": "PASS",
                    "visual_review": "NOT_APPLICABLE_NO_FIGURES", "reviewer": {"id": "main-model"},
                })
                (root / "reports/schedule/figures.txt").write_text("no figure work remains", encoding="utf-8")
                lifecycle.record_schedule_checkpoint(root, {
                    "research_program_id": program_id,
                    "research_program_hash": lifecycle.sha256_file(root / f"contracts/{program_id}.json"),
                    "completed_phase": "MANUSCRIPT_HARDENED", "next_phase": "FIGURES_COMPLETE",
                    "elapsed": "fixture", "remaining_schedule": {"hours": 1},
                    "projected_completion": "within deadline", "deadline_fit": True,
                    "replan_required": False, "action": "CONTINUE", "evidence": ["reports/schedule/figures.txt"],
                    "reviewer": {"id": "fixture"},
                })
                lifecycle.set_gate(root, "M5", "PASS", [routing, figure_report], "figure program complete", "fixture")
                lifecycle.transition(root, "FIGURES_COMPLETE")

                pdf = Path(temp) / "main.pdf"
                pdf.write_bytes(b"proposal pdf fixture")
                lifecycle.register_latex_verdict(root, {
                    "compiled": True, "error_count": 0, "input_hash": "f" * 64, "page_count": 8,
                }, pdf)
                lifecycle.transition(root, "LATEX_COMPILED")
                latex = lifecycle.read_json(root / "reports/manuscript/latex-verdict.json")
                judgment_id = lifecycle.register_publication_judgment(root, {
                    "publication_contract_id": publication_id,
                    "publication_contract_hash": lifecycle.sha256_file(contract_path),
                    "manuscript_id": manuscript_id, "manuscript_hash": lifecycle.sha256_file(manuscript_path),
                    "figure_role_completeness": "no figures are planned in this explained fixture deviation",
                    "citation_relevance": "all planned sources ground proposal context",
                    "experiment_claim_coverage": "the claim remains prospective and outcomes unknown",
                    "venue_scale_substance": "the fixture binds scale without filler",
                    "claim_argument_consistency": "all sections retain prospective claim wording",
                    "cross_section_consistency": "scope and terminology are consistent",
                    "method_result_alignment": "no result is claimed",
                    "redundancy_and_filler_review": "no duplicate or audit filler is present",
                    "internal_provenance_boundary": "internal lifecycle artifacts are absent from the manuscript",
                    "limitations_and_negative_results": "unknown outcomes are explicit",
                    "rendered_pdf_review": {
                        "pdf_sha256": latex["pdf_sha256"], "actual_pdf_reviewed": True,
                        "layout_findings": [], "blocking_issues": [],
                    },
                    "page_scale": {
                        "actual_pages": 8, "target_range": [8, 8], "verdict": "WITHIN_TARGET",
                        "rationale": "the compiled fixture matches the frozen range",
                    },
                    "deviations": ["synthetic no-figure proposal"],
                    "verdict": "PASS_WITH_EXPLAINED_DEVIATION", "reviewer": {"id": "main-model"},
                })
                judgment_path = root / f"reports/manuscript/{judgment_id}.json"
                audit_id = lifecycle.register_release_audit(root, {
                    "publication_contract_id": publication_id,
                    "publication_contract_hash": lifecycle.sha256_file(contract_path),
                    "manuscript_id": manuscript_id, "manuscript_hash": lifecycle.sha256_file(manuscript_path),
                    "publication_judgment_id": judgment_id,
                    "publication_judgment_hash": lifecycle.sha256_file(judgment_path),
                    "citation_verdict": "PASS", "figure_verdict": "PASS", "latex_verdict": "PASS",
                    "claim_verdict": "PASS", "blocking_issues": [], "reviewer": {"id": "fixture-audit"},
                })
                (root / "reports/schedule/release.txt").write_text("release audit fits", encoding="utf-8")
                lifecycle.record_schedule_checkpoint(root, {
                    "research_program_id": program_id,
                    "research_program_hash": lifecycle.sha256_file(root / f"contracts/{program_id}.json"),
                    "completed_phase": "LATEX_COMPILED", "next_phase": "RELEASE_AUDITED",
                    "elapsed": "fixture", "remaining_schedule": {"hours": 0},
                    "projected_completion": "complete", "deadline_fit": True,
                    "replan_required": False, "action": "CONTINUE", "evidence": ["reports/schedule/release.txt"],
                    "reviewer": {"id": "fixture"},
                })
                lifecycle.set_gate(root, "M6", "PASS", [f"reports/release/{audit_id}.json"], "release audited", "fixture")
                lifecycle.transition(root, "RELEASE_AUDITED")
                lifecycle.transition(root, "RELEASED")
                self.assertEqual(lifecycle.validate_root(root), [])
                self.assertEqual(lifecycle.load_state(root)["phase"], "RELEASED")
        finally:
            fixture.tearDown()


if __name__ == "__main__":
    unittest.main()
