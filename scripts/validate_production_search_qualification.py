#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from vladder.production_search import PRODUCTION_SEARCH_VERSION


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate checked-in production search qualification")
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("docs/reports/production-canonical-search-rc28-summary.json"),
    )
    args = parser.parse_args()
    report = json.loads(args.report.read_text())
    errors = []
    if report.get("schema_version") != "vladder-production-canonical-search-qualification-summary-v1":
        errors.append("unexpected qualification summary schema")
    if report.get("production_engine_version") != PRODUCTION_SEARCH_VERSION:
        errors.append("qualification summary does not match the production engine")
    if report.get("status") != "PASS":
        errors.append("qualification status is not PASS")
    if report.get("disposition") != "PRODUCTION_CANONICAL_SEARCH_APPROVED":
        errors.append("production canonical search is not approved")
    failed = sorted(key for key, value in report.get("gates", {}).items() if value is not True)
    if failed:
        errors.append(f"failed gates: {failed}")
    if len(report.get("real_system_roots", ())) < 3:
        errors.append("fewer than three real source systems were qualified")
    print(json.dumps({
        "status": "FAIL" if errors else "PASS",
        "report": str(args.report),
        "production_engine_version": PRODUCTION_SEARCH_VERSION,
        "errors": errors,
    }, indent=2, sort_keys=True))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
