from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

P = Path(__file__).parents[1] / "scripts/execution_backend.py"
sys.path.insert(0, str(P.parent))
spec = importlib.util.spec_from_file_location("rlc_backend_test", P)
backend = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = backend
spec.loader.exec_module(backend)


def settings(**overrides):
    values = {
        "policy": "remote_first", "host": "gpu.example.org", "user": "research",
        "port": 22, "remote_root": "/tmp/ts-experiment-runs", "remote_env_file": "",
        "identity_file": "", "known_hosts_file": "", "connect_timeout_seconds": 10,
        "sync_timeout_seconds": 60, "allow_local_fallback": True,
    }
    values.update(overrides)
    return backend.RemoteExperimentSettings(**values)


def environment(kind="remote", target="research@gpu.example.org:22", fingerprint="fp"):
    return {
        "os": "linux", "python": "3.12", "framework": "torch", "dependencies": [],
        "hardware": {"gpu": "gpu", "cpu": "x86"}, "cuda": "12",
        "execution": {"backend": kind, "target": target, "fingerprint": fingerprint},
    }


class ExecutionBackendTest(unittest.TestCase):
    def test_remote_is_selected_before_local(self):
        remote_env = environment()
        with patch.object(backend.RemoteExecutor, "probe", return_value={"ok": True, "environment": remote_env}):
            report = backend.select_environment(settings())
        self.assertTrue(report["ok"])
        self.assertEqual(report["backend"], "remote")
        self.assertEqual(report["environment"], remote_env)

    def test_local_is_only_prelock_fallback(self):
        local_env = environment("local", "localhost", "local-fp")
        with patch.object(backend.RemoteExecutor, "probe", return_value={"ok": False, "error": "offline"}), \
                patch.object(backend, "local_environment_snapshot", return_value=local_env):
            report = backend.select_environment(settings())
        self.assertEqual(report["backend"], "local")
        self.assertIn("remote_preflight_failed", report["fallback_reason"])

    def test_remote_only_does_not_fallback(self):
        with patch.object(backend.RemoteExecutor, "probe", return_value={"ok": False, "error": "offline"}):
            report = backend.select_environment(settings(policy="remote_only"))
        self.assertFalse(report["ok"])
        self.assertNotIn("environment", report)

    def test_locked_backend_rejects_target_or_fingerprint_drift(self):
        lock = {"status": "LOCKED", "environment": environment()}
        self.assertEqual(backend.validate_locked_backend(lock, environment()), [])
        issues = backend.validate_locked_backend(lock, environment(target="other:22", fingerprint="new"))
        self.assertEqual(len(issues), 2)

    def test_remote_execute_recovers_exit_and_logs_from_synced_metadata(self):
        executor = backend.RemoteExecutor(settings())
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            token = "run-1"

            def fake_rsync(_source, _destination, *, inbound):
                if inbound:
                    meta = cwd / ".ts-execution" / token
                    meta.mkdir(parents=True)
                    (meta / "started_at").write_text("now")
                    (meta / "exit_code").write_text("0\n")
                    (meta / "stdout.log").write_text("remote-ok\n")
                    (meta / "stderr.log").write_text("")
                return backend.ProcessResult(0)

            with patch.object(backend, "_run", side_effect=[backend.ProcessResult(0), backend.ProcessResult(0)]), \
                    patch.object(executor, "_rsync", side_effect=fake_rsync):
                result = executor.execute("python train.py", cwd=cwd, token=token, timeout_seconds=60)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "remote-ok\n")
            self.assertFalse(result.transport_error)

    def test_remote_started_without_exit_is_outcome_unknown(self):
        executor = backend.RemoteExecutor(settings())
        with tempfile.TemporaryDirectory() as td:
            cwd = Path(td)
            token = "run-2"

            def fake_rsync(_source, _destination, *, inbound):
                if inbound:
                    meta = cwd / ".ts-execution" / token
                    meta.mkdir(parents=True)
                    (meta / "started_at").write_text("now")
                return backend.ProcessResult(0)

            with patch.object(backend, "_run", side_effect=[backend.ProcessResult(0), backend.ProcessResult(255)]), \
                    patch.object(executor, "_rsync", side_effect=fake_rsync):
                result = executor.execute("python train.py", cwd=cwd, token=token, timeout_seconds=60)
            self.assertTrue(result.transport_error)
            self.assertTrue(result.outcome_unknown)

    def test_local_timeout_terminates_process_group(self):
        with tempfile.TemporaryDirectory() as td:
            result = backend.execute_local("sleep 10", cwd=Path(td), timeout_seconds=1)
        self.assertEqual(result.returncode, 124)
        self.assertTrue(result.timed_out)

    def test_remote_executor_end_to_end_with_ssh_rsync_transport(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bindir = root / "bin"; bindir.mkdir()
            fake_ssh = bindir / "ssh"
            fake_ssh.write_text(textwrap.dedent("""\
                #!/usr/bin/env python3
                import subprocess, sys
                result = subprocess.run(["bash", "-lc", sys.argv[-1]])
                raise SystemExit(result.returncode)
            """))
            fake_rsync = bindir / "rsync"
            fake_rsync.write_text(textwrap.dedent("""\
                #!/usr/bin/env python3
                import shutil, sys
                from pathlib import Path
                source, destination = sys.argv[-2:]
                def local(value):
                    return Path(value.split(":", 1)[1] if ":" in value else value.rstrip("/"))
                src, dst = local(source), local(destination)
                dst.mkdir(parents=True, exist_ok=True)
                for item in src.iterdir():
                    if item.name in {".git", ".env", ".venv", "__pycache__"}: continue
                    target = dst / item.name
                    if item.is_dir(): shutil.copytree(item, target, dirs_exist_ok=True)
                    else: shutil.copy2(item, target)
            """))
            fake_ssh.chmod(0o755); fake_rsync.chmod(0o755)
            work = root / "work"; work.mkdir(); (work / "input.txt").write_text("x")
            remote_root = root / "remote"
            config = settings(remote_root=str(remote_root))
            with patch.dict(os.environ, {"PATH": f"{bindir}:{os.environ['PATH']}"}):
                executor = backend.RemoteExecutor(config)
                probe = executor.probe()
                self.assertTrue(probe["ok"], probe)
                result = executor.execute(
                    "printf 'remote-result' > result.txt", cwd=work,
                    token="integration-run", timeout_seconds=60,
                )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((work / "result.txt").read_text(), "remote-result")
            self.assertFalse(result.transport_error)


if __name__ == "__main__":
    unittest.main()
