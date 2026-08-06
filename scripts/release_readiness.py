#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vladder.release_readiness import (
    TARGETS, evaluate_release_readiness, refresh_online_release_readiness, write_release_readiness,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate vLadder functionality, access, artifacts, and release channels")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--execute", action="store_true", help="run full tests, builds, clean installs, and local services")
    parser.add_argument("--online", action="store_true", help="inspect GitHub, PyPI, Homebrew, and hosted service state")
    parser.add_argument("--require-target", choices=TARGETS, default="local_development")
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--reuse-local-report", type=Path, help="refresh online state on an existing --execute report")
    parser.add_argument("--out", type=Path, default=Path("build/release-readiness.json"))
    args = parser.parse_args()
    if args.reuse_local_report:
        if not args.online:
            parser.error("--reuse-local-report requires --online")
        report = refresh_online_release_readiness(json.loads(args.reuse_local_report.read_text()), args.root)
    else:
        report = evaluate_release_readiness(
            args.root, execute=args.execute, online=args.online, work_directory=args.work_dir,
        )
    write_release_readiness(report, args.out)
    print(json.dumps({"summary": report["summary"], "targets": report["targets"]}, sort_keys=True))
    print(args.out.resolve())
    return 0 if report["targets"][args.require_target]["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
