#!/usr/bin/env python3
"""Show how to MANUALLY promote candidate lessons into golden rules.

This script intentionally does NOT modify any files. Promotion of a candidate
rule into `resources/golden_rules.md` requires explicit human approval. This
tool only prints the procedure and lists current candidates for convenience.
"""

from __future__ import annotations

import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))

CANDIDATE_FILE = os.path.join(SKILL_DIR, "memory", "lessons_candidate.md")
GOLDEN_FILE = os.path.join(SKILL_DIR, "resources", "golden_rules.md")
CHANGELOG_FILE = os.path.join(SKILL_DIR, "memory", "rule_change_log.md")


INSTRUCTIONS = f"""
========================================================================
 promote_lessons.py — MANUAL promotion only (no automatic changes)
========================================================================

Candidate rules are NEVER auto-promoted. To promote a candidate into an
active golden rule, a human must approve it. Follow these steps:

  1. Review candidates in:
       {os.path.relpath(CANDIDATE_FILE, os.getcwd())}

  2. Get explicit user/author approval for the specific candidate.

  3. Add the approved rule to the golden rules table in:
       {os.path.relpath(GOLDEN_FILE, os.getcwd())}
     Assign the next free GR-### id and write a one-line imperative rule.

  4. Record the promotion in the change log:
       {os.path.relpath(CHANGELOG_FILE, os.getcwd())}
     Include: date, change type = promote, rule id, from/to text,
     approved-by, and source paper/candidate.

  5. (Optional) Move the promoted candidate's curated form into:
       memory/lessons_validated.md
     and mark its Status in lessons_candidate.md as 'promoted'.

This tool will not edit any of these files for you.
========================================================================
"""


def list_candidates() -> None:
    if not os.path.isfile(CANDIDATE_FILE):
        print(f"(No candidate file found at {CANDIDATE_FILE})")
        return
    with open(CANDIDATE_FILE, "r", encoding="utf-8", errors="replace") as fh:
        content = fh.read()

    rule_ids = [
        line.strip()
        for line in content.splitlines()
        if line.strip().lower().startswith("rule id:")
    ]
    print("Current candidate 'Rule ID:' lines:")
    if not rule_ids:
        print("  (none yet — append candidates using the format in the file header)")
    else:
        for rid in rule_ids:
            print(f"  - {rid}")
    print()


def main() -> int:
    print(INSTRUCTIONS)
    list_candidates()
    return 0


if __name__ == "__main__":
    sys.exit(main())
