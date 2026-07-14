from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts/publication_contracts.py"
spec = importlib.util.spec_from_file_location("publication_contracts", SCRIPT)
contracts = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(contracts)


class PublicationContractTest(unittest.TestCase):
    def policy(self, minimum=None):
        return {
            "source": "COMPILED_FROM_USER_REQUEST", "target_venue": "Venue", "venue_selection_policy": "USER_SELECTED",
            "citation_policy": {"minimum_unique_cited_references": minimum},
            "figure_policy": {
                "measured_evidence_route": "DETERMINISTIC_OR_ORIGINAL_EVIDENCE",
                "original_observation_route": "ORIGINAL_EVIDENCE",
                "exact_structure_route": "DOMAIN_NATIVE",
                "explanatory_synthesis_route": "PAPERBANANA_REQUIRED",
                "drawai_policy": "USE_IF_AVAILABLE_AFTER_RASTER_APPROVAL",
            },
            "requirements": [],
            "research_preferences": {"field": "fixture science", "paper_archetype": "method"},
            "deadline": {"status": "KNOWN", "days": 7},
            "resource_limits": {"compute": "fixture", "financial": "none", "api": "none", "storage": "fixture"},
            "human_review": {"available": True}, "priorities": ["validity"],
            "degradation_policy": {"acceptable": ["narrow scope"], "unacceptable": ["padding"]},
            "assumptions": {"unknowns": [], "confirmed": ["fixture"]},
        }

    def venue(self, root: Path):
        papers = []
        samples = [
            {"page_count": 8, "unique_cited_references": 34, "total_figures": 5, "table_count": 2, "evaluation_count": 3},
            {"page_count": 10, "unique_cited_references": 52, "total_figures": 6, "table_count": 3, "evaluation_count": 4},
            {"page_count": 9, "unique_cited_references": 48, "total_figures": 6, "table_count": 1, "evaluation_count": 3},
        ]
        for index, values in enumerate(samples):
            pdf = root / f"paper-{index}.pdf"; pdf.write_bytes(f"paper {index}".encode())
            metrics = {
                **values,
                "figure_roles": {"evidence": values["total_figures"] - 2, "explanation": 2},
                "evaluation_kinds": {"benchmark": values["evaluation_count"]},
                "evidence_dimensions": {"datasets": index + 1, "comparators": 4},
                "evaluation_difficulty": {
                    "rating": "moderate", "drivers": ["multi-condition comparison"],
                    "rationale": "fixture difficulty is explicit",
                },
            }
            papers.append({"title": f"Paper {index}", "venue": "Venue", "year": 2026, "article_type": "method",
                           "source": {"doi": f"10.1000/{index}"}, "pdf": {"path": str(pdf), "sha256": contracts.sha256_file(pdf)},
                           "relevance": "matched", "metrics": metrics})
        aggregates = contracts.compute_venue_aggregates(papers)
        return {"venue_profile_id": "venue-profile-v-001", "venue_basis": {"venues": ["Venue"]},
                "research_scope": "fixture", "corpus_criteria": {"accepted": True}, "papers": papers,
                "aggregates": aggregates, "official_constraints": {},
                "sample_sufficiency": {"verdict": "SUFFICIENT", "rationale": "coverage", "coverage": "three archetypes", "stopping_reason": "saturation"},
                "evaluation_difficulty_synthesis": {"typical": "moderate", "drivers": ["matched comparisons"]},
                "limitations": ["fixture"], "reviewer": {"id": "model"}}

    def contract(self, policy, venue):
        envelope = contracts.derive_publication_envelope(policy, venue)
        figures = [
            {"figure_id": "measured", "class": "measured_evidence", "purpose": "primary outcome", "route": "DETERMINISTIC_OR_ORIGINAL_EVIDENCE", "source_of_truth": "canonical facts", "claim_ids": ["C-001"], "section_role": "results"},
            {"figure_id": "observation", "class": "original_observation", "purpose": "show observed case", "route": "ORIGINAL_EVIDENCE", "source_of_truth": "source image", "claim_ids": ["C-001"], "section_role": "results"},
            {"figure_id": "structure", "class": "exact_structure", "purpose": "show exact apparatus", "route": "DOMAIN_NATIVE", "source_of_truth": "registered geometry", "claim_ids": ["C-001"], "section_role": "methods"},
            {"figure_id": "overview", "class": "explanatory_synthesis", "purpose": "explain method", "route": "PAPERBANANA_REQUIRED", "source_of_truth": "method contract", "claim_ids": ["C-001"], "section_role": "methods", "drawai_policy": "USE_IF_AVAILABLE_AFTER_RASTER_APPROVAL"},
            {"figure_id": "mechanism", "class": "explanatory_synthesis", "purpose": "explain mechanism", "route": "PAPERBANANA_REQUIRED", "source_of_truth": "mechanism evidence", "claim_ids": ["C-001"], "section_role": "discussion", "drawai_policy": "USE_IF_AVAILABLE_AFTER_RASTER_APPROVAL"},
        ]
        return {
            "idea_id": "idea-v-001", "research_program_id": "research-program-v-001",
            "research_program_hash": "a" * 64, "claim_registry_hash": "b" * 64,
            "claim_ids": ["C-001"], "paper_archetype": "method",
            "calibration_envelope": envelope,
            "targets": {"page_range": [8, 10], "minimum_unique_cited_references": 45, "figure_count": 5, "table_count": 2},
            "target_rationales": {"page_range": "venue span", "minimum_unique_cited_references": "claim coverage and venue density", "figure_count": "five distinct scientific roles", "table_count": "primary and robustness evidence"},
            "section_plan": [{"section_id": "body", "purpose": "present the complete argument"}], "figure_plan": figures,
            "table_plan": [
                {"table_id": "main", "purpose": "primary", "source_of_truth": "canonical facts", "claim_ids": ["C-001"], "section_role": "results"},
                {"table_id": "robust", "purpose": "robustness", "source_of_truth": "canonical facts", "claim_ids": ["C-001"], "section_role": "results"},
            ],
            "citation_coverage_requirements": {"claims": True}, "deadline_allocation": {"writing": "day 1"},
            "deviations": [],
            "manuscript_content_policy": {"internal_provenance_location": "artifact_package", "reader_relevant_reproducibility_only": True, "forbid_page_filler": True, "allowed_internal_identifiers": []},
        }

    def test_envelope_reports_distribution_without_choosing_a_quota(self):
        with tempfile.TemporaryDirectory() as temp:
            venue = self.venue(Path(temp))
            envelope = contracts.derive_publication_envelope(self.policy(), venue)
            self.assertEqual(envelope["sample_size"], 3)
            self.assertEqual(envelope["metrics"]["page_count"]["observed_range"], [8.0, 10.0])
            self.assertEqual(envelope["metrics"]["evaluation_count"]["observed_range"], [3.0, 4.0])
            self.assertEqual(envelope["interpretation"], "observed_calibration_not_a_quota")
            self.assertNotIn("target", envelope)

    def test_no_global_forty_reference_floor(self):
        policy = self.policy(minimum=None)
        contracts.validate_user_policy(policy)
        policy["citation_policy"]["minimum_unique_cited_references"] = 12
        contracts.validate_user_policy(policy)

    def test_user_minimum_is_enforced_after_model_selects_target(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); venue = self.venue(root); policy = self.policy(minimum=50)
            payload = self.contract(policy, venue)
            payload["targets"]["minimum_unique_cited_references"] = 49
            with self.assertRaisesRegex(ValueError, "user's explicit minimum"):
                contracts.validate_publication_contract(payload, policy, venue)

    def test_declared_venue_statistics_cannot_drift_from_papers(self):
        with tempfile.TemporaryDirectory() as temp:
            venue = self.venue(Path(temp)); venue["aggregates"]["means"]["total_figures"] += 1
            with self.assertRaisesRegex(ValueError, "not reproducible"):
                contracts.validate_venue_profile(Path(temp), venue)

    def test_figure_routes_follow_source_of_truth_class(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); venue = self.venue(root); policy = self.policy()
            payload = self.contract(policy, venue)
            contracts.validate_publication_contract(payload, policy, venue)
            payload["figure_plan"][2]["route"] = "PAPERBANANA_REQUIRED"
            with self.assertRaisesRegex(ValueError, "class/source route"):
                contracts.validate_publication_contract(payload, policy, venue)

    def test_outside_observed_range_requires_explained_deviation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); venue = self.venue(root); policy = self.policy()
            payload = self.contract(policy, venue)
            payload["targets"]["page_range"] = [12, 14]
            with self.assertRaisesRegex(ValueError, "without a deviation"):
                contracts.validate_publication_contract(payload, policy, venue)
            payload["deviations"] = [{"metric": "page_count", "rationale": "official supplement policy", "evidence": ["official rule"]}]
            contracts.validate_publication_contract(payload, policy, venue)


if __name__ == "__main__":
    unittest.main()
