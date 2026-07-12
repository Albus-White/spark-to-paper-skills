# Repository and Version Governance

Prefer official benchmark and author repositories when they implement the relevant task and protocol.
Use a maintained third-party repository only with an explicit status and rationale. Implement locally
only the smallest missing component; review it against the mathematics and contract.

Register a repository only after the lifecycle verifies its real local Git HEAD and origin. Use a full
object ID, record license and official status, and keep the checkout clean. Select one mode:

- `read_only`: no local changes;
- `adapters_only`: upstream stays clean; integration code lives in `code/adapters` or `code/integration`;
- `patch_stack`: upstream stays clean; ordered patch files live in `code/patches` and are hash-bound;
- `fork`: changes are committed in a pinned fork.

Do not resolve a dependency or source conflict by taking whichever side builds. Record conflicting
versions and write a conflict-resolution report with the base commit, resolved dependencies,
behavioral checks, and remaining risks. The main model judges which behavior matches the frozen
contract and primary sources; executable reference/regression tests verify the chosen integration.

Changing commit, patch hash, dependency resolution, evaluator, checkpoint, or submodule creates a new
repository/environment lock and invalidates affected executable evidence. Credentials never belong in
repository URLs or lock files.
