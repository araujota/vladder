#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vladder.production_smoke import write_production_canonical_smoke


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the release-blocking production canonical-search smoke battery")
    parser.add_argument("--out", type=Path, default=Path("build/production-canonical-search-smoke.json"))
    args = parser.parse_args()
    report = write_production_canonical_smoke(args.out)
    print(json.dumps({
        "status": report["status"],
        "passed": report["summary"]["passed"],
        "failed": report["summary"]["failed"],
        "duration_ms": report["summary"]["duration_ms"],
        "artifact": str(args.out.resolve()),
    }, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
