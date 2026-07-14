# Paper Wiki Integration

Paper Wiki is a persistent, file-based cited research memory, not a vector database and not the
canonical research lifecycle. Its useful structure is:

- `raw/`: append-only source material;
- `wiki/papers/`: source-grounded paper records;
- `wiki/concepts/`: reverse-linked conceptual synthesis;
- `wiki/gaps/`: evidence-backed open questions with novelty unverified;
- `WIKI.md` and `.paper-wiki`: workspace contract and sentinel.

The native actions are `init`, `compile`, `search`, `critique`, `ideate`, and `teach`. Use the external
Paper Wiki project's own Skill for those actions. This suite consumes only an immutable snapshot plus
primary-source paths selected from it.

For lifecycle use, distinguish three states:

- `BUILDING`: incomplete corpus; retrieval may be useful but coverage claims are unsafe;
- `ACTIVE`: maintained corpus; snapshot is usable with a fresh delta search;
- `FROZEN`: reproducible historical view; preferred for Idea selection and audit.

The main model records maturity and coverage in the Idea candidate artifact. The snapshot script
verifies file identity only; it cannot certify corpus quality, source support, or novelty.

