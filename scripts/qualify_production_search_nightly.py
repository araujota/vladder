#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from qualify_canonical_search import adversarial_campaign
from qualify_production_canonical_search import concurrency_stress, measured_expensive_root, memory_and_footprint


def main() -> int:
    parser = argparse.ArgumentParser(description="Run self-contained nightly canonical-search qualification")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = {
        "schema_version": "vladder-production-search-nightly-v1",
        "adversarial": adversarial_campaign(30),
        "measured_expensive_root": measured_expensive_root(),
        "concurrency": concurrency_stress(),
        "resources": memory_and_footprint(),
    }
    report["status"] = "PASS" if all(
        report[key]["status"] == "PASS"
        for key in ("adversarial", "measured_expensive_root", "concurrency", "resources")
    ) else "FAIL"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": report["status"], "output": str(args.output)}, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
