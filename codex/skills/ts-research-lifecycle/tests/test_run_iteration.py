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


SCRIPT = Path(__file__).parents[1] / "scripts/run_iteration.py"
spec = importlib.util.spec_from_file_location("run_iteration_v5", SCRIPT)
run_iteration = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = run_iteration
assert spec.loader
spec.loader.exec_module(run_iteration)


class IterationV5Test(unittest.TestCase):
    def test_protocol_failure_is_not_auto_retryable(self):
        self.assertIn("PROTOCOL_FAILURE", run_iteration.NO_AUTO_RETRY)
        self.assertNotIn("PROTOCOL_FAILURE", run_iteration.AUTO_RETRY)

    def test_implementation_failure_requires_state_change(self):
        self.assertIn("IMPLEMENTATION_FAILURE", run_iteration.STATE_CHANGE_REQUIRED)
        self.assertNotIn("IMPLEMENTATION_FAILURE", run_iteration.AUTO_RETRY)

    def test_only_infrastructure_failure_is_automatically_retryable(self):
        self.assertEqual(run_iteration.AUTO_RETRY, {"INFRASTRUCTURE_FAILURE"})

    def test_unknown_failure_is_inconclusive(self):
        self.assertEqual(run_iteration.classify("unclassified scientific outcome", 1), "INCONCLUSIVE")

    def test_transport_failure_is_infrastructure(self):
        self.assertEqual(run_iteration.classify("", 255, transport_error=True), "INFRASTRUCTURE_FAILURE")

    def test_success_is_none(self):
        self.assertEqual(run_iteration.classify("", 0), "NONE")

    def test_attempt_and_timeout_budgets_have_hard_caps(self):
        self.assertEqual(run_iteration.MAX_ATTEMPTS, 3)
        self.assertEqual(run_iteration.MIN_TIMEOUT_SECONDS, 60)
        self.assertEqual(run_iteration.MAX_TIMEOUT_SECONDS, 86_400)

    def workspace(self, base: Path, environment: dict | None = None):
        root = base / "research"
        work = base / "work"
        work.mkdir()
        run_iteration.rlc.init_layout(root, "standard_empirical", "iteration-test")
        idea_id = "idea-v-001"
        program_id = "research-program-v-001"
        run_iteration.rlc.write_json(root / f"ideas/{idea_id}.json", {
            "idea_id": idea_id, "parent_idea_id": None, "revision_level": "L0", "status": "ACTIVE",
        })
        run_iteration.rlc.write_json(root / f"contracts/{program_id}.json", {
            "research_program_id": program_id,
            "evaluation_units": [{"unit_id": "EU-001", "claim_ids": ["C-001"]}],
            "resource_plan": {"max_runs": 10, "max_branches": 2, "max_branch_depth": 1},
            "test_set_policy": {"max_test_access": 1},
        })
        state = run_iteration.rlc.load_state(root)
        state["active"]["idea_id"] = idea_id
        state["active"]["research_program_id"] = program_id
        run_iteration.rlc.save_state(root, state, "minimal_frozen_fixture")

        checkout = root / "code/upstream/repo"
        checkout.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(checkout)], check=True)
        subprocess.run(["git", "-C", str(checkout), "config", "user.email", "fixture@example.org"], check=True)
        subprocess.run(["git", "-C", str(checkout), "config", "user.name", "Fixture"], check=True)
        (checkout / "README.md").write_text("fixture", encoding="utf-8")
        subprocess.run(["git", "-C", str(checkout), "add", "README.md"], check=True)
        subprocess.run(["git", "-C", str(checkout), "commit", "-q", "-m", "fixture"], check=True)
        subprocess.run(["git", "-C", str(checkout), "remote", "add", "origin", "https://example.org/repo.git"], check=True)
        commit = subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True).strip()
        run_iteration.rlc.register_repo(root, {
            "purpose": "author implementation", "url": "https://example.org/repo.git", "commit": commit,
            "official_status": "official", "license": "MIT", "local_path": "code/upstream/repo",
            "modification_mode": "read_only",
        })
        run_iteration.rlc.lock_environment(root, environment or run_iteration.backend.local_environment_snapshot())
        config = base / "config.json"
        config.write_text(json.dumps({"mode": "fixture"}), encoding="utf-8")
        return root, work, config

    def execute(self, root: Path, work: Path, config: Path, command: str, max_attempts: int = 1) -> int:
        argv = [
            "run_iteration.py", "--root", str(root), "--run-type", "pilot",
            "--evaluation-unit-id", "EU-001", "--command", command,
            "--config", str(config), "--replicate-id", "group-1", "--random-seed", "1",
            "--input-hash", "observations=" + "d" * 64, "--protocol-hash", "e" * 64,
            "--max-attempts", str(max_attempts), "--timeout-seconds", "60", "--cwd", str(work),
        ]
        with patch.object(sys, "argv", argv):
            return run_iteration.main()

    def test_local_locked_backend_executes_and_records_provenance(self):
        with tempfile.TemporaryDirectory() as temp:
            root, work, config = self.workspace(Path(temp))
            self.assertEqual(self.execute(root, work, config, "printf ok > artifact.txt"), 0)
            manifest = run_iteration.rlc.read_json(root / "experiments/runs/run-0001/run_manifest.json")
            self.assertEqual(manifest["execution_backend"], "local")
            self.assertEqual(manifest["evaluation_unit_ids"], ["EU-001"])
            self.assertEqual(manifest["research_program_id"], "research-program-v-001")
            self.assertTrue(manifest["execution_environment_fingerprint"])
            self.assertEqual((work / "artifact.txt").read_text(), "ok")

    def test_implementation_failure_does_not_repeat_unchanged_command(self):
        with tempfile.TemporaryDirectory() as temp:
            root, work, config = self.workspace(Path(temp))
            command = f"{sys.executable} -c \"raise RuntimeError('implementation bug')\""
            self.assertEqual(self.execute(root, work, config, command, max_attempts=3), 1)
            summary = run_iteration.rlc.read_json(root / "experiments/iterations/iteration-001/iteration_summary.json")
            self.assertEqual(len(summary["attempts"]), 1)
            self.assertEqual(summary["stop_reason"], "state_change_required")

    def test_locked_remote_backend_executes_end_to_end(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            bindir = base / "bin"
            bindir.mkdir()
            (bindir / "ssh").write_text(textwrap.dedent("""\
                #!/usr/bin/env python3
                import subprocess, sys
                raise SystemExit(subprocess.run(["bash", "-lc", sys.argv[-1]]).returncode)
            """), encoding="utf-8")
            (bindir / "rsync").write_text(textwrap.dedent("""\
                #!/usr/bin/env python3
                import shutil, sys
                from pathlib import Path
                source, destination = sys.argv[-2:]
                def local(value): return Path(value.split(":", 1)[1] if ":" in value else value.rstrip("/"))
                src, dst = local(source), local(destination)
                dst.mkdir(parents=True, exist_ok=True)
                for item in src.iterdir():
                    if item.name in {".git", ".env", ".venv", "__pycache__"}: continue
                    target = dst / item.name
                    if item.is_dir(): shutil.copytree(item, target, dirs_exist_ok=True)
                    else: shutil.copy2(item, target)
            """), encoding="utf-8")
            (bindir / "ssh").chmod(0o755)
            (bindir / "rsync").chmod(0o755)
            environment = {
                "PATH": f"{bindir}:{os.environ['PATH']}",
                "TS_EXPERIMENT_EXECUTION_POLICY": "remote_first",
                "TS_EXPERIMENT_REMOTE_HOST": "fakehost",
                "TS_EXPERIMENT_REMOTE_USER": "",
                "TS_EXPERIMENT_REMOTE_ROOT": str(base / "remote"),
                "TS_EXPERIMENT_REMOTE_ENV_FILE": "",
                "TS_EXPERIMENT_SSH_IDENTITY_FILE": "",
                "TS_EXPERIMENT_SSH_KNOWN_HOSTS": "",
            }
            with patch.dict(os.environ, environment):
                selection = run_iteration.backend.select_environment(run_iteration.backend.load_settings())
                self.assertEqual(selection["backend"], "remote", selection)
                root, work, config = self.workspace(base, selection["environment"])
                self.assertEqual(self.execute(root, work, config, "printf remote > remote.txt"), 0)
            manifest = run_iteration.rlc.read_json(root / "experiments/runs/run-0001/run_manifest.json")
            self.assertEqual(manifest["execution_backend"], "remote")
            self.assertEqual((work / "remote.txt").read_text(), "remote")


if __name__ == "__main__":
    unittest.main()
