#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from publication_contracts import dump_envelope


def main() -> int:
    parser = argparse.ArgumentParser(description="Derive a publication calibration envelope without choosing quotas")
    parser.add_argument("--policy", required=True)
    parser.add_argument("--venue-profile", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    result = dump_envelope(Path(args.policy), Path(args.venue_profile))
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
