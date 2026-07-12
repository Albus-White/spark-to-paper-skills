from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

P = Path(__file__).parents[1] / "scripts/run_iteration.py"
spec = importlib.util.spec_from_file_location("ri", P)
ri = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = ri
spec.loader.exec_module(ri)

IDEA = {
    "problem": "p", "hypothesis": "h", "proposed_mechanism": "m", "scope": "s",
    "assumptions": ["a"], "falsifiers": ["f"], "claims": ["c"],
    "alternative_explanations": ["x"],
}
CLAIM = {
    "claim_text": "c", "claim_type": "empirical result claim", "essential": True,
    "strength": "bounded", "scope": "s", "required_evidence": ["formal run"],
}
CONTRACT = {
    "claim_ids": ["C-001"], "experiments": [{"experiment_id": "E-001", "claim_ids": ["C-001"],
        "why_it_tests_claim": "direct fixture", "positive_interpretation": "support",
        "negative_interpretation": "reject", "confounders": ["none"], "out_of_scope_conclusions": ["other tasks"]}],
    "study_inputs": ["d"], "protocols": ["s"], "outcomes": ["m"], "comparators": ["b"],
    "replication_plan": {"type": "random_seed", "identifiers": [1], "rationale": "fixture"},
    "statistical_plan": {"aggregate": "mean"},
    "test_set_policy": {"max_access": 1}, "stop_conditions": ["budget"],
    "budget": {"max_runs": 10, "max_branches": 4, "max_branch_depth": 2},
    "feasibility": {
        "status": "MEASURED", "budget_fit": True, "deadline_fit": True,
        "estimated_cost": {"seconds": 1}, "evidence": ["reports/design/feasibility.json"],
    },
}
REPO = {
    "purpose": "benchmark", "url": "https://example.org/repo.git",
    "official_status": "official", "license": "MIT",
    "local_path": "code/upstream/repo", "modification_mode": "read_only",
}


class IterationTest(unittest.TestCase):
    def test_protocol_failure_is_not_auto_retryable(self):
        self.assertIn("PROTOCOL_FAILURE", ri.NO_AUTO_RETRY)
        self.assertNotIn("PROTOCOL_FAILURE", ri.AUTO_RETRY)

    def test_implementation_failure_requires_state_change(self):
        self.assertIn("IMPLEMENTATION_FAILURE", ri.STATE_CHANGE_REQUIRED)
        self.assertNotIn("IMPLEMENTATION_FAILURE", ri.AUTO_RETRY)

    def test_only_infrastructure_failure_is_automatically_retryable(self):
        self.assertEqual(ri.AUTO_RETRY, {"INFRASTRUCTURE_FAILURE"})

    def test_unknown_failure_is_inconclusive(self):
        self.assertEqual(ri.classify("strange scientific outcome", 1), "INCONCLUSIVE")

    def test_transport_failure_is_infrastructure(self):
        self.assertEqual(ri.classify("", 255, transport_error=True), "INFRASTRUCTURE_FAILURE")

    def test_success_is_none(self):
        self.assertEqual(ri.classify("", 0), "NONE")

    def test_attempt_and_timeout_budgets_have_hard_caps(self):
        self.assertEqual(ri.MAX_ATTEMPTS, 3)
        self.assertEqual(ri.MIN_TIMEOUT_SECONDS, 60)
        self.assertEqual(ri.MAX_TIMEOUT_SECONDS, 86400)

    def _workspace(self, base: Path, environment=None):
        root = base / "research"
        work = base / "work"; work.mkdir()
        ri.rlc.init_layout(root, "standard_empirical", "test")
        ri.rlc.register_resource_envelope(root, {
            "source": "USER_PROVIDED", "deadline": {"max_elapsed_hours": 2, "hard": True},
            "compute": [{"backend": "local", "hardware": "fixture", "count": 1}],
            "financial_limit": {"status": "KNOWN", "amount": 0}, "human_review": {"hours": 0},
            "priorities": ["correctness"], "constraints": [], "assumptions": [], "confirmed_by_user": True,
        })
        idea_id = ri.rlc.register_idea(root, IDEA, None, "L0", None)
        ri.rlc.register_claim(root, CLAIM)
        ri.rlc.write_json(root / "reports/design/feasibility.json", {"seconds": 1})
        contract = {**CONTRACT, "budget": {**CONTRACT["budget"],
            "resource_envelope": "intake/resource-envelope.json",
            "resource_envelope_hash": ri.rlc.sha256_file(root / "intake/resource-envelope.json"),
            "deadline_fit": True, "allocation_rationale": "fixture microprobe fits"}}
        ri.rlc.write_json(root / "grounding/research_contract.candidate.json", contract)
        judgment_path = "reports/gates/G3.judgment.json"
        evidence = ["grounding/research_contract.candidate.json", "reports/design/feasibility.json"]
        ri.rlc.write_json(root / judgment_path, {
            "artifact_type": "scientific_judgment", "gate": "G3", "verdict": "PASS",
            "conclusion": "The bounded fixture contract is feasible.",
            "checks": [{"question": "Is the contract feasible?", "verdict": "SUPPORTED", "rationale": "The microprobe fits the budget.", "evidence": evidence}],
            "limitations": ["Synthetic fixture"], "blocking_issues": [],
            "reviewer": {"id": "fixture", "model_or_human": "test-model", "independent": True, "context_artifacts": evidence},
        })
        approval = ri.rlc.record_approval(root, "FREEZE_CONTRACT", "APPROVED", idea_id, [judgment_path], "main-model")
        ri.rlc.freeze_contract(root, contract, approval)
        repo = root / REPO["local_path"]
        repo.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.email", "fixture@example.org"], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.name", "Fixture"], check=True)
        (repo / "README.md").write_text("fixture", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "README.md"], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "fixture"], check=True)
        subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", REPO["url"]], check=True)
        commit = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
        ri.rlc.register_repo(root, {**REPO, "commit": commit})
        environment = environment or ri.backend.local_environment_snapshot()
        ri.rlc.lock_environment(root, environment)
        config = base / "config.json"; config.write_text(json.dumps({"lr": 1e-3}))
        return root, work, config

    def _run(self, root: Path, work: Path, config: Path, command: str, max_attempts: int = 1):
        argv = [
            "run_iteration.py", "--root", str(root), "--run-type", "pilot",
            "--experiment-id", "E-001",
            "--command", command, "--config", str(config), "--replicate-id", "seed-1", "--random-seed", "1",
            "--input-hash", "dataset=" + "d" * 64, "--protocol-hash", "e" * 64, "--max-attempts", str(max_attempts),
            "--timeout-seconds", "60", "--cwd", str(work),
        ]
        with patch.object(sys, "argv", argv):
            return ri.main()

    def test_local_locked_backend_executes_and_records_provenance(self):
        with tempfile.TemporaryDirectory() as td:
            root, work, config = self._workspace(Path(td))
            self.assertEqual(self._run(root, work, config, "printf ok > artifact.txt"), 0)
            manifest = ri.rlc.read_json(root / "experiments/runs/run-0001/run_manifest.json")
            self.assertEqual(manifest["execution_backend"], "local")
            self.assertTrue(manifest["execution_environment_fingerprint"])
            self.assertEqual((work / "artifact.txt").read_text(), "ok")

    def test_implementation_failure_does_not_repeat_unchanged_command(self):
        with tempfile.TemporaryDirectory() as td:
            root, work, config = self._workspace(Path(td))
            command = f"{sys.executable} -c \"raise RuntimeError('implementation bug')\""
            self.assertEqual(self._run(root, work, config, command, max_attempts=3), 1)
            summary = ri.rlc.read_json(root / "experiments/iterations/iteration-001/iteration_summary.json")
            self.assertEqual(len(summary["attempts"]), 1)
            self.assertEqual(summary["stop_reason"], "state_change_required")

    def test_locked_remote_backend_executes_end_to_end(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td); bindir = base / "bin"; bindir.mkdir()
            (bindir / "ssh").write_text(textwrap.dedent("""\
                #!/usr/bin/env python3
                import subprocess, sys
                raise SystemExit(subprocess.run(["bash", "-lc", sys.argv[-1]]).returncode)
            """))
            (bindir / "rsync").write_text(textwrap.dedent("""\
                #!/usr/bin/env python3
                import shutil, sys
                from pathlib import Path
                source, destination = sys.argv[-2:]
                def local(value): return Path(value.split(":", 1)[1] if ":" in value else value.rstrip("/"))
                src, dst = local(source), local(destination); dst.mkdir(parents=True, exist_ok=True)
                for item in src.iterdir():
                    if item.name in {".git", ".env", ".venv", "__pycache__"}: continue
                    target = dst / item.name
                    if item.is_dir(): shutil.copytree(item, target, dirs_exist_ok=True)
                    else: shutil.copy2(item, target)
            """))
            (bindir / "ssh").chmod(0o755); (bindir / "rsync").chmod(0o755)
            env = {
                "PATH": f"{bindir}:{os.environ['PATH']}",
                "TS_EXPERIMENT_EXECUTION_POLICY": "remote_first",
                "TS_EXPERIMENT_REMOTE_HOST": "fakehost",
                "TS_EXPERIMENT_REMOTE_USER": "",
                "TS_EXPERIMENT_REMOTE_ROOT": str(base / "remote"),
                "TS_EXPERIMENT_REMOTE_ENV_FILE": "",
                "TS_EXPERIMENT_SSH_IDENTITY_FILE": "",
                "TS_EXPERIMENT_SSH_KNOWN_HOSTS": "",
            }
            with patch.dict(os.environ, env):
                selection = ri.backend.select_environment(ri.backend.load_settings())
                self.assertEqual(selection["backend"], "remote", selection)
                root, work, config = self._workspace(base, selection["environment"])
                self.assertEqual(self._run(root, work, config, "printf remote > remote.txt"), 0)
            manifest = ri.rlc.read_json(root / "experiments/runs/run-0001/run_manifest.json")
            self.assertEqual(manifest["execution_backend"], "remote")
            self.assertEqual((work / "remote.txt").read_text(), "remote")


if __name__ == "__main__":
    unittest.main()
