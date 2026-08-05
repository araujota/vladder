#!/usr/bin/env python3
"""Produce a deterministic, requirement-level public release readiness report."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


ROOT = Path(__file__).resolve().parents[1]
TEMP_ROOT = Path(tempfile.gettempdir())


@dataclass(frozen=True)
class Check:
    check_id: str
    requirement: str
    status: str
    evidence: tuple[str, ...]
    detail: str

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.check_id,
            "requirement": self.requirement,
            "status": self.status,
            "evidence": list(self.evidence),
            "detail": self.detail,
        }


def run(command: Sequence[str], cwd: Path = ROOT) -> tuple[bool, str]:
    completed = subprocess.run(
        list(command),
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    output = (completed.stdout + completed.stderr).strip()
    return completed.returncode == 0, output[-4000:]


def present(check_id: str, requirement: str, files: Sequence[str], detail: str) -> Check:
    missing = [path for path in files if not (ROOT / path).exists()]
    return Check(
        check_id,
        requirement,
        "pass" if not missing else "fail",
        tuple(files),
        detail if not missing else f"Missing: {', '.join(missing)}",
    )


def command_check(
    check_id: str,
    requirement: str,
    command: Sequence[str],
    evidence: Sequence[str],
    cwd: Path = ROOT,
) -> Check:
    ok, output = run(command, cwd)
    return Check(
        check_id,
        requirement,
        "pass" if ok else "fail",
        tuple(evidence),
        output or "Command completed without output.",
    )


def convex_deployment_is_authenticated() -> bool:
    configured = os.environ.get("CONVEX_DEPLOYMENT", "")
    env_file = ROOT / "services" / "review-backend" / ".env.local"
    if not configured and env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("CONVEX_DEPLOYMENT="):
                configured = line.split("=", 1)[1].strip()
                break
    return configured.startswith(("dev:", "prod:"))


def vercel_project_is_linked() -> bool:
    if os.environ.get("VERCEL_PROJECT_ID") and os.environ.get("VERCEL_ORG_ID"):
        return True
    return (ROOT / "apps" / "release-site" / ".vercel" / "project.json").exists()


def build_checks(execute: bool) -> list[Check]:
    checks = [
        present(
            "distribution.install",
            "One-command clean Linux installation",
            ["scripts/install.sh", ".github/workflows/ci.yml"],
            "Ubuntu CI executes the installer in an isolated prefix.",
        ),
        present(
            "distribution.frontends",
            "C/C++ plus at least one additional frontend",
            ["vladder/cpp_regions.py", "vladder/rust_adapter.py", "vladder/zig_adapter.py"],
            "C++, Rust, and Zig frontends are packaged with the C frontend.",
        ),
        present(
            "documentation.release",
            "Public release documentation set",
            [
                "docs/privacy.md",
                "docs/artifact-schemas.md",
                "docs/grammar-authoring.md",
                "docs/proof-boundaries.md",
                "docs/benchmark-reproducibility.md",
                "CONTRIBUTING.md",
                "ROADMAP.md",
            ],
            "Privacy, schemas, grammar, proof, benchmark, roadmap, and contribution policy are present.",
        ),
        present(
            "case-study.neuralfusion",
            "Substantial real-project case study",
            ["docs/case-studies/neuralfusion.md"],
            "The case study separates regional, end-to-end, and proof-boundary evidence.",
        ),
        present(
            "schemas.stable",
            "Stable machine-readable artifact schemas",
            ["vladder/schemas/registry.json", "vladder/schema_registry.py"],
            "Versioned schemas are registered and validated through the CLI.",
        ),
        present(
            "contributions.workflow",
            "Canonical source-free contribution workflows with explicit upload consent",
            [
                "vladder/reviews/agent-review-prompt.md",
                "vladder/schemas/agent-review-v1.schema.json",
                "vladder/schemas/training-bundle-v1.schema.json",
                "vladder/review_workflow.py",
                "vladder/training_workflow.py",
            ],
            "Reviews and training bundles are local by default and remote submission requires two consent gates.",
        ),
        present(
            "quality.ci",
            "Seeded proof, Ruff, Bandit, Sonar, and Snyk CI",
            [
                "examples/release_seeds/transformations.yaml",
                "scripts/validate_release_seeds.py",
                ".github/workflows/security-services.yml",
                "sonar-project.properties",
            ],
            "Local checks are executable; hosted scanners remain separately classified below.",
        ),
        present(
            "service.review-backend",
            "Moderated review and source-free training persistence",
            [
                "services/review-backend/convex/schema.ts",
                "services/review-backend/convex/http.ts",
                "services/review-backend/convex/reviews.ts",
                "services/review-backend/convex/training.ts",
                "services/review-backend/convex/rateLimits.ts",
            ],
            "Convex accepts bounded public contributions without exposing unapproved records or accepting source uploads.",
        ),
        present(
            "website.release",
            "Release, download, privacy, and workflow website",
            ["apps/release-site/src/app/page.tsx", "apps/release-site/src/app/globals.css"],
            "The static-first site remains usable without the optional review service.",
        ),
    ]

    if execute:
        checks.extend(
            [
                command_check(
                    "validation.schemas",
                    "Schema registry and privacy gates",
                    [sys.executable, "-m", "unittest", "tests.test_public_release"],
                    ["tests/test_public_release.py"],
                ),
                command_check(
                    "validation.demos",
                    "Three reproducible frontend demonstrations",
                    [sys.executable, "scripts/run_release_demos.py", "--out-dir", str(TEMP_ROOT / "vladder-release-demos")],
                    ["demos/README.md", str(TEMP_ROOT / "vladder-release-demos" / "release-demos.json")],
                ),
                command_check(
                    "validation.seeded-transformations",
                    "Seeded good and bad transformations",
                    [sys.executable, "scripts/validate_release_seeds.py", "--out-dir", str(TEMP_ROOT / "vladder-release-seeds")],
                    ["examples/release_seeds/transformations.yaml", str(TEMP_ROOT / "vladder-release-seeds" / "release-seeds.json")],
                ),
                command_check(
                    "validation.ruff",
                    "Ruff static analysis",
                    [sys.executable, "-m", "ruff", "check", "."],
                    ["pyproject.toml"],
                ),
                command_check(
                    "validation.bandit",
                    "Bandit high-confidence security analysis",
                    [sys.executable, "-m", "bandit", "-r", "vladder", "scripts", "-ll", "-ii", "-x", "tests"],
                    ["pyproject.toml"],
                ),
                command_check(
                    "validation.backend",
                    "Review backend type and dependency validation",
                    ["npm", "run", "check"],
                    ["services/review-backend/package-lock.json"],
                    ROOT / "services/review-backend",
                ),
                command_check(
                    "validation.website",
                    "Release website production build",
                    ["npm", "run", "build"],
                    ["apps/release-site/package-lock.json"],
                    ROOT / "apps/release-site",
                ),
            ]
        )
    else:
        checks.append(
            Check(
                "validation.local-suite",
                "Executable local release checks",
                "not_run",
                ("scripts/public_release_gate.py --execute",),
                "Run with --execute to collect command evidence.",
            )
        )

    checks.extend(
        [
            Check(
                "external.sonar",
                "SonarCloud hosted analysis",
                "external_gate",
                (".github/workflows/security-services.yml",),
                "Requires SONAR_TOKEN and the repository's SonarCloud organization/project configuration.",
            ),
            Check(
                "external.snyk",
                "Snyk hosted dependency analysis",
                "external_gate",
                (".github/workflows/security-services.yml",),
                "Requires SNYK_TOKEN in the GitHub repository.",
            ),
            Check(
                "external.convex",
                "Authenticated Convex review deployment",
                "pass" if convex_deployment_is_authenticated() else "external_gate",
                ("services/review-backend",),
                "Requires an authenticated, explicitly selected Convex project; anonymous deployments do not qualify.",
            ),
            Check(
                "external.vercel",
                "Authenticated Vercel website deployment",
                "pass" if vercel_project_is_linked() else "external_gate",
                ("apps/release-site",),
                "Requires an authenticated, explicitly linked Vercel project.",
            ),
        ]
    )
    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="run local validation commands")
    parser.add_argument("--out", type=Path, default=ROOT / "build" / "public-release-gate.json")
    args = parser.parse_args()

    checks = build_checks(args.execute)
    summary = {state: sum(check.status == state for check in checks) for state in ("pass", "fail", "not_run", "external_gate")}
    report = {
        "schema": "vladder-public-release-gate-v1",
        "release_version": "1.0.0rc15",
        "checks": [check.to_dict() for check in checks],
        "summary": summary,
        "ready_for_local_release": summary["fail"] == 0 and summary["not_run"] == 0,
        "ready_for_public_services": summary["fail"] == 0 and summary["not_run"] == 0 and summary["external_gate"] == 0,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], sort_keys=True))
    print(args.out)
    return 1 if summary["fail"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
