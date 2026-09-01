#!/usr/bin/env python3
"""Export digest-only OProver capture records for `shred seal-authentic-trace`."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from shred.oprover_export import export_saved_attempts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", action="append", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--expected-attempts", required=True, type=int)
    args = parser.parse_args()
    print(
        json.dumps(
            export_saved_attempts(args.input, args.output, args.expected_attempts),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
