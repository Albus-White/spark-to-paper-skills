# PaperBanana execution and attribution

This suite executes an external PaperBanana checkout through a narrow adapter; it does not vendor the
upstream source. The integration was developed against commit
`836455537e863b5a2f40dace487a782c0bc5ef94` and records the actual checkout origin, commit, and dirty
status for every run. A different checkout is allowed only when pinned and revalidated.

The checked upstream repository contains an Apache License 2.0 file. Its README also states that the
core workflow was developed during a Google internship, that patents were filed, and that similar
logic is restricted for third-party commercial applications. Those statements create a potential
commercial-use concern beyond ordinary source-license checking. Do not represent this suite as legal
clearance; obtain appropriate review before commercial use or redistribution.

Upstream project: `https://github.com/dwzhu-pku/PaperBanana`

PaperBanana may call external model providers. Their credentials, terms, retention policies, content
rules, costs, and generated-output rights remain the operator's responsibility. Keep credentials in
the upstream runtime/environment, never in lifecycle artifacts, copied runtime files, or logs.
The upstream runtime reads its own supported provider variables or ignored local model config;
legacy `TS_FIG_*` variables do not prove that all five PaperBanana stages can execute.
