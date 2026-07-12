# Remote-first experiment execution

Formal experiments choose their execution environment before G5 and then freeze it. The selector
tries the external SSH server first; local execution is the fallback only if remote preflight fails
before the environment is locked. After G5, a run must use the locked backend, target, and environment
fingerprint. Never fall back mid-run: that would change hardware/environment and invalidate evidence.

## Client configuration

Set these fields in the suite `.env`:

```bash
TS_EXPERIMENT_EXECUTION_POLICY=remote_first  # remote_first | remote_only | local_only
TS_EXPERIMENT_REMOTE_HOST=gpu.example.org
TS_EXPERIMENT_REMOTE_USER=research
TS_EXPERIMENT_REMOTE_PORT=22
TS_EXPERIMENT_REMOTE_ROOT=/tmp/ts-experiment-runs
TS_EXPERIMENT_REMOTE_ENV_FILE=/opt/ts-paper/experiment.env  # optional, already on server
TS_EXPERIMENT_SSH_IDENTITY_FILE=                            # optional; SSH agent/config also works
TS_EXPERIMENT_SSH_KNOWN_HOSTS=                              # optional custom file
TS_EXPERIMENT_SSH_CONNECT_TIMEOUT_SECONDS=15
TS_EXPERIMENT_SYNC_TIMEOUT_SECONDS=900
TS_EXPERIMENT_ALLOW_LOCAL_FALLBACK=1
```

The server needs `bash`, `python3`, `rsync`, and GNU `timeout`, plus the project-specific experiment
environment, datasets, checkpoints, and GPU stack. SSH is non-interactive (`BatchMode=yes`), so use an
SSH agent/config or identity file rather than a password prompt. Host-key checking is always strict. The client does
not copy `.env`, `.git`, virtual environments, Python caches, or credentials. Put remote-only secrets
in `TS_EXPERIMENT_REMOTE_ENV_FILE` on the server.

## Select and lock

```bash
python scripts/execution_backend.py preflight
python scripts/execution_backend.py select \
  --out research/environment/selected.environment.json
python scripts/lifecycle.py --root research lock-environment \
  --file research/environment/selected.environment.json
```

`select` emits a full environment snapshot and an execution record containing backend, SSH target,
and fingerprint. With `remote_first`, an unavailable/unconfigured remote target selects local only
when local fallback is enabled. `remote_only` fails closed.

## Execute

`run_iteration.py` reads the environment lock. A remote lock causes it to:

1. re-probe the same target and verify the fingerprint;
2. synchronize the workspace to a unique remote attempt directory;
3. execute the workspace-relative command under a remote GNU `timeout`;
4. preserve remote start/exit markers and stdout/stderr;
5. synchronize artifacts back without deleting local-only files;
6. register backend, target, fingerprint, remote directory, transport status, and stop reason.

If transport fails before the remote command starts, only bounded infrastructure retry is legal. If
the start marker exists but no trustworthy exit marker is recoverable, stop as
`remote_outcome_unknown`; do not launch the same experiment locally because that could double-run a
test-set access or consume an untracked budget. Dependency/implementation failures also stop and
require a concrete environment/code change before a new invocation.
