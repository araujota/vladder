from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Iterable, Sequence
import urllib.error
import urllib.request

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10
    import tomli as tomllib

from . import __version__
from .contribution_transport import contribution_contract_errors


REPORT_VERSION = "vladder-release-readiness-v2"
STATUSES = {"pass", "fail", "not_run", "setup_required", "unavailable", "warning"}
TARGETS = (
    "local_development",
    "release_candidate",
    "github_release",
    "pypi",
    "homebrew",
    "formal_release",
)
CORE_BLOCKS = TARGETS
DEFAULT_BLOCKS = CORE_BLOCKS


@dataclass(frozen=True)
class ReadinessCheck:
    check_id: str
    level: str
    requirement: str
    status: str
    detail: str
    evidence: tuple[str, ...] = ()
    remediation: str | None = None
    blocks: tuple[str, ...] = DEFAULT_BLOCKS

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise ValueError(f"unsupported readiness status: {self.status}")
        unknown = sorted(set(self.blocks) - set(TARGETS))
        if unknown:
            raise ValueError(f"unknown readiness targets: {unknown}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.check_id,
            "level": self.level,
            "requirement": self.requirement,
            "status": self.status,
            "detail": self.detail,
            "evidence": list(self.evidence),
            "remediation": self.remediation,
            "blocks": list(self.blocks),
        }


def _run(command: Sequence[str], cwd: Path, timeout: int = 900) -> tuple[int, str]:
    try:
        completed = subprocess.run(
            list(command), cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=timeout, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return 127, str(error)
    return completed.returncode, completed.stdout.strip()[-6000:]


def _command_check(
    check_id: str,
    level: str,
    requirement: str,
    command: Sequence[str],
    root: Path,
    *,
    evidence: Iterable[str] = (),
    remediation: str | None = None,
    blocks: tuple[str, ...] = DEFAULT_BLOCKS,
    cwd: Path | None = None,
    timeout: int = 900,
) -> ReadinessCheck:
    code, output = _run(command, cwd or root, timeout)
    return ReadinessCheck(
        check_id, level, requirement, "pass" if code == 0 else "fail",
        output or f"Command exited {code} without output.", tuple(evidence), remediation, blocks,
    )


def _not_run(
    check_id: str, level: str, requirement: str, command: str,
    blocks: tuple[str, ...] = DEFAULT_BLOCKS,
) -> ReadinessCheck:
    return ReadinessCheck(
        check_id, level, requirement, "not_run", f"Not executed: {command}", (command,),
        f"Run the readiness check with --execute to collect {check_id} evidence.", blocks,
    )


def _read_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _runtime_version(root: Path) -> str:
    match = re.search(
        r'^__version__\s*=\s*"([^"]+)"', (root / "vladder" / "__init__.py").read_text(), re.MULTILINE,
    )
    if not match:
        raise ValueError("vladder/__init__.py has no __version__")
    return match.group(1)


def _presence_check(root: Path, check_id: str, level: str, requirement: str, paths: Sequence[str]) -> ReadinessCheck:
    missing = [item for item in paths if not (root / item).exists()]
    return ReadinessCheck(
        check_id, level, requirement, "pass" if not missing else "fail",
        "All required files are present." if not missing else f"Missing: {', '.join(missing)}",
        tuple(paths), "Restore or add the missing release files." if missing else None,
    )


def _static_checks(root: Path, channels: dict[str, Any]) -> list[ReadinessCheck]:
    checks: list[ReadinessCheck] = []
    project = _read_toml(root / "pyproject.toml")["project"]
    version = str(project["version"])
    runtime = _runtime_version(root)
    identity_ok = version == runtime == __version__ or version == runtime
    checks.append(ReadinessCheck(
        "source.version-identity", "source", "One version across project and runtime", "pass" if identity_ok else "fail",
        f"pyproject={version}, runtime={runtime}, executing={__version__}",
        ("pyproject.toml", "vladder/__init__.py"), "Synchronize all release version declarations.",
    ))
    project_urls = project.get("urls", {})
    required_urls = {"Homepage", "Repository", "Issues", "Changelog"}
    missing_urls = sorted(required_urls - set(project_urls))
    checks.append(ReadinessCheck(
        "source.pypi-metadata", "source", "Complete public package metadata", "pass" if not missing_urls else "fail",
        "Project URLs and package metadata are complete." if not missing_urls else f"Missing project URLs: {missing_urls}",
        ("pyproject.toml",), "Add stable Homepage, Repository, Issues, and Changelog URLs.",
    ))
    checks.extend([
        _presence_check(root, "source.documentation", "documentation", "Release, support, security, and proof documentation", (
            "README.md", "CHANGELOG.md", "LICENSE", "CONTRIBUTING.md", "ROADMAP.md", "SECURITY.md",
            "docs/releasing.md", "docs/privacy.md", "docs/proof-boundaries.md",
            "docs/benchmark-reproducibility.md", "docs/artifact-schemas.md",
        )),
        _presence_check(root, "functionality.major-surfaces", "functionality", "Major optimization surfaces are present", (
            "vladder/automatic.py", "vladder/cpp_regions.py", "vladder/rust_adapter.py", "vladder/zig_adapter.py",
            "vladder/julia_adapter.py", "vladder/lifetime_graph.py", "vladder/deep_grammar.py",
            "vladder/gpu_workflow.py", "vladder/prior_workflow.py", "vladder/contribution_transport.py",
        )),
        _presence_check(root, "access.installers", "access", "Documented pip, source, skill, and Homebrew access paths", (
            "scripts/install.sh", "vladder/skills/vladder/SKILL.md", "packaging/homebrew/vladder.rb.in",
        )),
        _presence_check(root, "channels.workflows", "channels", "CI, TestPyPI, release, and security workflows", (
            ".github/workflows/ci.yml", ".github/workflows/release.yml",
            ".github/workflows/test-publish.yml", ".github/workflows/security-services.yml",
        )),
    ])
    publish_workflows = [
        (root / ".github" / "workflows" / name).read_text() for name in ("release.yml", "test-publish.yml")
    ]
    workflow_text = "\n".join(publish_workflows)
    oidc_ok = all(
        "id-token: write" in text and "pypa/gh-action-pypi-publish@release/v1" in text
        for text in publish_workflows
    )
    static_secret = any(marker in workflow_text for marker in ("PYPI_API_TOKEN", "password:", "username:"))
    checks.append(ReadinessCheck(
        "pypi.oidc-workflows", "channels", "PyPI and TestPyPI use OIDC Trusted Publishing", "pass" if oidc_ok and not static_secret else "fail",
        "OIDC jobs are present without static publishing credentials." if oidc_ok and not static_secret else "OIDC markers are missing or static credentials are referenced.",
        (".github/workflows/release.yml", ".github/workflows/test-publish.yml"),
        "Use id-token: write with pypa/gh-action-pypi-publish and no API token.", ("pypi", "formal_release"),
    ))
    package_dependencies = {re.split(r"[<>=!~ ]", item, 1)[0].lower() for item in project.get("dependencies", [])}
    template = (root / "packaging/homebrew/vladder.rb.in").read_text()
    resource_names = set(re.findall(r'^\s*resource\s+"([^"]+)"', template, re.MULTILINE))
    required_resources = {
        "attrs", "jsonschema", "jsonschema-specifications", "pyyaml", "referencing", "rpds-py", "z3-solver",
    }
    missing_resources = sorted(required_resources - resource_names)
    direct_dependencies = {"pyyaml", "z3-solver", "jsonschema"}
    checks.append(ReadinessCheck(
        "homebrew.python-resource-closure", "artifacts", "Homebrew formula closes direct and transitive Python runtime dependencies",
        "pass" if not missing_resources and direct_dependencies <= package_dependencies else "fail",
        f"Resources={sorted(resource_names)}; project dependencies={sorted(package_dependencies)}",
        ("packaging/homebrew/vladder.rb.in", "pyproject.toml"),
        "Add all direct and transitive Python runtime resources with exact hashes.", ("homebrew", "formal_release"),
    ))
    expected_repository = channels["github"]["repository"]
    unresolved = []
    for path in (root / "README.md", root / "docs" / "releasing.md"):
        text = path.read_text()
        if "OWNER/REPOSITORY" in text or "OWNER/tap" in text:
            unresolved.append(str(path.relative_to(root)))
    checks.append(ReadinessCheck(
        "access.no-public-placeholders", "access", "Install and release instructions use real public identifiers", "pass" if not unresolved else "setup_required",
        f"Repository={expected_repository}; unresolved placeholders={unresolved}",
        tuple(unresolved), "Replace OWNER placeholders with the configured repository and tap identifiers.",
        ("github_release", "pypi", "homebrew", "formal_release"),
    ))
    return checks


def _build_artifacts(root: Path, work: Path) -> tuple[list[ReadinessCheck], list[Path]]:
    checks: list[ReadinessCheck] = []
    dist = work / "dist"
    dist.mkdir(parents=True, exist_ok=True)
    checks.append(_command_check(
        "artifacts.build", "artifacts", "Build one wheel and one sdist", [sys.executable, "-m", "build", "--outdir", str(dist)], root,
        evidence=(str(dist),), remediation="Install the dev dependencies and fix PEP 517 build failures.", timeout=600,
    ))
    artifacts = sorted(dist.glob("vladder-*"))
    if checks[-1].status != "pass":
        return checks, artifacts
    checks.append(_command_check(
        "artifacts.twine", "artifacts", "PyPI metadata renders cleanly", [sys.executable, "-m", "twine", "check", *map(str, artifacts)], root,
        evidence=tuple(map(str, artifacts)), remediation="Fix invalid package metadata or README rendering.", timeout=300,
    ))
    checks.append(_command_check(
        "artifacts.audit", "artifacts", "Distributions contain required resources and no release residue",
        [sys.executable, "scripts/audit_release.py", *sum((["--artifact", str(item)] for item in artifacts), [])], root,
        evidence=tuple(map(str, artifacts)), remediation="Fix package data and source distribution inclusion rules.", timeout=300,
    ))
    sdist = next((item for item in artifacts if item.name.endswith(".tar.gz")), None)
    if sdist is not None:
        formula = work / "vladder.rb"
        repository = _read_toml(root / "release" / "channels.toml")["github"]["repository"]
        checks.append(_command_check(
            "artifacts.homebrew-render", "artifacts", "Render the exact release formula and all pinned resources",
            [
                sys.executable, "scripts/render_homebrew_formula.py", "--repository", repository,
                "--version", str(_read_toml(root / "pyproject.toml")["project"]["version"]),
                "--source-path", str(sdist), "--output", str(formula),
            ],
            root,
            evidence=(str(sdist), "packaging/homebrew/vladder.rb.in"),
            remediation="Correct formula resources, versions, source identity, or PyPI resource hashes.",
            blocks=("homebrew", "formal_release"),
            timeout=300,
        ))
        if checks[-1].status == "pass":
            checks.append(_command_check(
                "artifacts.homebrew-ruby", "artifacts", "Rendered Homebrew formula is valid Ruby",
                ["ruby", "-c", str(formula)], root, evidence=(str(formula),),
                remediation="Fix Homebrew formula syntax.", blocks=("homebrew", "formal_release"), timeout=60,
            ))
    for kind, artifact in (("wheel", next((item for item in artifacts if item.suffix == ".whl"), None)), ("sdist", sdist)):
        if artifact is None:
            checks.append(ReadinessCheck(
                f"access.clean-install-{kind}", "access", f"Clean {kind} installation", "fail", f"No {kind} artifact was built.",
                (), "Build both wheel and sdist artifacts.",
            ))
            continue
        prefix = work / f"install-{kind}"
        code, output = _run([sys.executable, "-m", "venv", str(prefix)], root, 180)
        if code == 0:
            code, output = _run([str(prefix / "bin" / "pip"), "install", str(artifact)], root, 600)
        commands = (
            [str(prefix / "bin" / "vladder"), "--version"],
            [str(prefix / "bin" / "vladder"), "schema", "list"],
            [str(prefix / "bin" / "vladder"), "lower", "validate"],
            [str(prefix / "bin" / "vladder"), "skill", "validate"],
            [str(prefix / "bin" / "vladder"), "doctor"],
        )
        command_outputs = [output]
        if code == 0:
            for command in commands:
                code, item_output = _run(command, root, 180)
                command_outputs.append(item_output)
                if code != 0:
                    break
        checks.append(ReadinessCheck(
            f"access.clean-install-{kind}", "access", f"Clean {kind} install exposes usable CLI, schemas, grammar, skill, and doctor",
            "pass" if code == 0 else "fail", "\n".join(command_outputs)[-6000:], (str(artifact),),
            f"Install and exercise the {kind} in an empty virtual environment; fix missing resources or dependencies.",
        ))
    return checks, artifacts


def _execution_checks(root: Path, work: Path) -> tuple[list[ReadinessCheck], list[Path]]:
    checks = [
        _command_check(
            "validation.source-audit", "source", "Source tree contains required release inputs and no forbidden residue",
            [sys.executable, "scripts/audit_release.py", "--root", "."], root,
            evidence=("scripts/audit_release.py",), remediation="Remove release residue or restore required public files.", timeout=300,
        ),
        _command_check(
            "validation.full-tests", "functionality", "Complete supported-language, grammar, proof, GPU, lifetime, prior, and release test suite",
            [sys.executable, "-m", "pytest", "-q"], root, evidence=("tests",),
            remediation="Resolve every failing or unexpectedly skipped release test.", timeout=1800,
        ),
        _command_check(
            "validation.ruff", "quality", "Ruff correctness analysis", [sys.executable, "-m", "ruff", "check", "."], root,
            evidence=("pyproject.toml",), remediation="Fix Ruff correctness failures.", timeout=300,
        ),
        _command_check(
            "validation.bandit", "quality", "Bandit medium/high-confidence security analysis",
            [sys.executable, "-m", "bandit", "-r", "vladder", "scripts", "-ll", "-ii", "-x", "tests"], root,
            evidence=("pyproject.toml",), remediation="Resolve medium/high-confidence security findings.", timeout=300,
        ),
        _command_check(
            "validation.openspec", "governance", "All OpenSpec changes validate strictly",
            ["openspec", "validate", "--all", "--strict"], root, evidence=("openspec",),
            remediation="Complete or repair every active OpenSpec workflow.", timeout=300,
        ),
        _command_check(
            "validation.production-canonical-search-smoke",
            "functionality",
            "Production canonical identity, POR, resume, concurrency, cost, and scaling smoke battery",
            [
                sys.executable,
                "scripts/run_production_canonical_smoke.py",
                "--out",
                str(work / "production-canonical-search-smoke.json"),
            ],
            root,
            evidence=("scripts/run_production_canonical_smoke.py",),
            remediation="Resolve every production canonical-search smoke failure before release.",
            timeout=300,
        ),
        _command_check(
            "validation.release-demos", "functionality", "Reproducible public frontend demonstrations",
            [sys.executable, "scripts/run_release_demos.py", "--out-dir", str(work / "demos")], root,
            evidence=("demos/README.md",), remediation="Fix all documented release demonstrations.", timeout=900,
        ),
        _command_check(
            "validation.seeded-transformations", "functionality", "Known valid and invalid transformations retain expected dispositions",
            [sys.executable, "scripts/validate_release_seeds.py", "--out-dir", str(work / "seeds")], root,
            evidence=("examples/release_seeds/transformations.yaml",), remediation="Restore proof and rejection behavior.", timeout=300,
        ),
        _command_check(
            "validation.public-surface", "access", "Agent workflow, schemas, consent, case study, and public-service surfaces",
            [sys.executable, "scripts/public_release_gate.py", "--execute", "--out", str(work / "public-release-gate.json")], root,
            evidence=("scripts/public_release_gate.py",), remediation="Resolve the failed public workflow requirement.", timeout=900,
        ),
        _command_check(
            "access.installer-smoke", "access", "One-command installer creates a usable isolated CLI",
            [
                "bash", "scripts/install.sh", "--no-system-packages", "--without-alive2",
                "--without-language-tools", "--prefix", str(work / "installer-prefix"),
            ],
            root,
            evidence=("scripts/install.sh",),
            remediation="Fix the isolated installer or its core-tool diagnostics.",
            timeout=900,
        ),
        _command_check(
            "validation.backend", "services", "Convex contribution backend type-checks",
            ["npm", "run", "check"], root, cwd=root / "services" / "review-backend",
            evidence=("services/review-backend/package-lock.json",), remediation="Install backend dependencies and resolve TypeScript errors.", timeout=300,
        ),
        _command_check(
            "validation.website", "services", "Release website builds for production",
            ["npm", "run", "build"], root, cwd=root / "apps" / "release-site",
            evidence=("apps/release-site/package-lock.json",), remediation="Install site dependencies and resolve production build failures.", timeout=600,
        ),
    ]
    artifact_checks, artifacts = _build_artifacts(root, work)
    checks.extend(artifact_checks)
    return checks, artifacts


def _http_json(url: str) -> tuple[int, dict[str, Any] | None]:
    try:
        with urllib.request.urlopen(url, timeout=20) as response:  # nosec B310 - configured HTTPS services
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, None
    except (OSError, ValueError):
        return 0, None


def _gh_json(root: Path, arguments: Sequence[str]) -> tuple[int, Any, str]:
    code, output = _run(["gh", *arguments], root, 120)
    if code != 0:
        return code, None, output
    try:
        return code, json.loads(output), output
    except json.JSONDecodeError:
        return code, None, output


def _online_checks(root: Path, channels: dict[str, Any]) -> list[ReadinessCheck]:
    checks: list[ReadinessCheck] = []
    repository = channels["github"]["repository"]
    if shutil.which("gh") is None:
        return [ReadinessCheck(
            "github.authentication", "channels", "Authenticated GitHub channel inspection", "unavailable",
            "gh is unavailable on this host.", (), "Install and authenticate GitHub CLI.",
            ("github_release", "pypi", "homebrew", "formal_release"),
        )]
    code, repo, detail = _gh_json(root, ["repo", "view", repository, "--json", "nameWithOwner,visibility,defaultBranchRef,url"])
    repo_ok = code == 0 and repo and repo.get("visibility") == "PUBLIC" and repo.get("defaultBranchRef", {}).get("name") == channels["github"]["default_branch"]
    checks.append(ReadinessCheck(
        "github.repository", "channels", "Public GitHub repository and default branch", "pass" if repo_ok else "setup_required",
        json.dumps(repo, sort_keys=True) if repo else detail, (f"https://github.com/{repository}",),
        "Create or correct the public repository and default main branch.", ("github_release", "pypi", "homebrew", "formal_release"),
    ))
    branch = channels["github"]["default_branch"]
    code, protection, detail = _gh_json(root, ["api", f"repos/{repository}/branches/{branch}/protection"])
    checks.append(ReadinessCheck(
        "github.branch-protection", "channels", "Main branch protection requires CI", "pass" if code == 0 else "setup_required",
        json.dumps(protection, sort_keys=True)[-3000:] if protection else detail,
        (f"https://github.com/{repository}/settings/branches",),
        "Protect main and require the CI workflow before merge.", ("github_release", "pypi", "homebrew", "formal_release"),
    ))
    code, runs, detail = _gh_json(root, [
        "run", "list", "--repo", repository, "--workflow", "CI", "--branch", branch, "--limit", "1",
        "--json", "conclusion,status,url,headSha,createdAt",
    ])
    latest = runs[0] if code == 0 and isinstance(runs, list) and runs else None
    ci_ok = bool(latest and latest.get("status") == "completed" and latest.get("conclusion") == "success")
    checks.append(ReadinessCheck(
        "github.latest-ci", "channels", "Latest main CI is green", "pass" if ci_ok else "fail",
        json.dumps(latest, sort_keys=True) if latest else detail, (), "Fix the latest failing CI jobs and rerun CI.",
        ("github_release", "pypi", "homebrew", "formal_release"),
    ))
    code, environments, detail = _gh_json(root, ["api", f"repos/{repository}/environments"])
    environment_rows = environments.get("environments", []) if isinstance(environments, dict) else []
    environment_names = {item.get("name") for item in environment_rows}
    for channel_name in ("pypi", "testpypi", "homebrew"):
        expected = channels[channel_name]["environment"]
        row = next((item for item in environment_rows if item.get("name") == expected), None)
        protected = bool(row and row.get("protection_rules"))
        checks.append(ReadinessCheck(
            f"github.environment-{channel_name}", "channels", f"Protected {expected} GitHub environment",
            "pass" if expected in environment_names and protected else "setup_required",
            json.dumps(row, sort_keys=True) if row else f"Existing environments: {sorted(environment_names)}",
            (f"https://github.com/{repository}/settings/environments",),
            f"Create environment {expected} and require maintainer approval.",
            (("pypi", "formal_release") if channel_name in {"pypi", "testpypi"} else ("homebrew", "formal_release")),
        ))
    for channel_name, base in (("pypi", "https://pypi.org"), ("testpypi", "https://test.pypi.org")):
        project = channels[channel_name]["project"]
        status, payload = _http_json(f"{base}/pypi/{project}/json")
        attested = bool(channels[channel_name].get("trusted_publisher_configured"))
        waiver = channels[channel_name] if channel_name == "testpypi" else {}
        waiver_valid = bool(
            waiver.get("waived")
            and str(waiver.get("waived_by", "")).strip()
            and re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(waiver.get("waived_at", "")))
            and str(waiver.get("waiver_reason", "")).strip()
        )
        project_state = "published" if status == 200 else "unclaimed" if status == 404 else "unreachable"
        latest = payload.get("info", {}).get("version") if payload else None
        release_version = str(_read_toml(root / "pyproject.toml")["project"]["version"])
        ready = attested and status in {200, 404}
        if channel_name == "testpypi":
            ready = attested and status == 200 and latest == release_version
        check_status = "pass" if ready else "warning" if waiver_valid else "setup_required"
        requirement = f"{channel_name} project or pending Trusted Publisher is configured"
        detail = f"project_state={project_state}; manifest_attestation={attested}; latest={latest}; expected={release_version}"
        remediation = (
            f"Configure the {channel_name} pending/existing Trusted Publisher for {repository}, workflow "
            f"{channels[channel_name]['workflow']}, environment {channels[channel_name]['environment']}; "
            "publish this exact candidate to TestPyPI; then set the manifest attestation true."
            if channel_name == "testpypi"
            else
            f"Configure the {channel_name} pending/existing Trusted Publisher for {repository}, workflow "
            f"{channels[channel_name]['workflow']}, environment {channels[channel_name]['environment']}; "
            "then set the manifest attestation true."
        )
        if channel_name == "testpypi" and waiver_valid and not ready:
            requirement = "Exact-candidate TestPyPI trial or explicit owner waiver"
            detail += (
                f"; waived_by={waiver['waived_by']}; waived_at={waiver['waived_at']}; "
                f"waiver_reason={waiver['waiver_reason']}"
            )
            remediation = "No action required for this release; create a TestPyPI account before removing the recorded waiver."
        checks.append(ReadinessCheck(
            f"{channel_name}.trusted-publisher", "channels", requirement,
            check_status,
            detail,
            (f"{base}/manage/account/publishing/",),
            remediation,
            ("pypi", "formal_release"),
        ))
    code, variables, _ = _gh_json(root, ["variable", "list", "--repo", repository, "--json", "name,value"])
    variable_map = {item["name"]: item["value"] for item in variables} if code == 0 and isinstance(variables, list) else {}
    code, secrets, _ = _gh_json(root, ["secret", "list", "--repo", repository, "--json", "name"])
    secret_names = {item["name"] for item in secrets} if code == 0 and isinstance(secrets, list) else set()
    homebrew = channels["homebrew"]
    variable_ok = variable_map.get(homebrew["repository_variable"]) == homebrew["tap_repository"]
    secret_ok = homebrew["write_secret"] in secret_names
    checks.append(ReadinessCheck(
        "homebrew.github-configuration", "channels", "Homebrew tap variable and scoped write secret exist",
        "pass" if variable_ok and secret_ok else "setup_required",
        f"variable_present={variable_ok}; secret_present={secret_ok}", (),
        f"Set repository variable {homebrew['repository_variable']}={homebrew['tap_repository']} and environment secret {homebrew['write_secret']} with tap-only write access.",
        ("homebrew", "formal_release"),
    ))
    code, tap, detail = _gh_json(root, ["repo", "view", homebrew["tap_repository"], "--json", "nameWithOwner,visibility,defaultBranchRef,url"])
    tap_ok = code == 0 and tap and tap.get("visibility") == "PUBLIC" and bool(homebrew.get("tap_configured"))
    checks.append(ReadinessCheck(
        "homebrew.tap", "channels", "Public Homebrew tap exists and is configured", "pass" if tap_ok else "setup_required",
        json.dumps(tap, sort_keys=True) if tap else detail, (f"https://github.com/{homebrew['tap_repository']}",),
        f"Create the public {homebrew['tap_repository']} repository, initialize it with brew tap-new, and set tap_configured=true.",
        ("homebrew", "formal_release"),
    ))
    health_url = channels["services"]["contribution_health_url"]
    status, health = _http_json(health_url)
    contract_errors = contribution_contract_errors(health)
    health_ok = status == 200 and not contract_errors
    health_detail = {
        "http_status": status,
        "contract_errors": contract_errors,
        "health": health,
    }
    checks.append(ReadinessCheck(
        "services.contribution-health", "services",
        "Production contribution service implements the package endpoint contract",
        "pass" if health_ok else "fail", json.dumps(health_detail, sort_keys=True), (health_url,),
        "Deploy the matching Convex contribution backend and verify its versioned health contract.",
        ("formal_release",),
    ))
    return checks


def _deferred_checks() -> list[ReadinessCheck]:
    return [
        ReadinessCheck(
            "channels.online", "channels", "Online GitHub, PyPI, Homebrew, and service checks", "not_run",
            "Online checks were not requested.", (), "Run with --online.",
            ("github_release", "pypi", "homebrew", "formal_release"),
        ),
    ]


def _target_summary(checks: Sequence[ReadinessCheck]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for target in TARGETS:
        blockers = [item for item in checks if target in item.blocks and item.status not in {"pass", "warning"}]
        result[target] = {
            "ready": not blockers,
            "blocker_count": len(blockers),
            "blockers": [item.check_id for item in blockers],
        }
    return result


def _clean_worktree_check(root: Path) -> ReadinessCheck:
    git_code, git_output = _run(["git", "status", "--porcelain"], root, 30)
    git_clean = git_code == 0 and not git_output
    return ReadinessCheck(
        "source.clean-worktree", "source", "Release is cut from a clean reviewed worktree",
        "pass" if git_clean else "setup_required", "clean" if git_clean else "Worktree contains uncommitted changes.",
        (), "Commit reviewed changes before tagging.", ("github_release", "pypi", "homebrew", "formal_release"),
    )


def _finalize_report(report: dict[str, Any], checks: Sequence[ReadinessCheck]) -> dict[str, Any]:
    report["checks"] = [item.to_dict() for item in checks]
    report["summary"] = {status: sum(item.status == status for item in checks) for status in sorted(STATUSES)}
    report["targets"] = _target_summary(checks)
    report["next_actions"] = []
    for item in checks:
        if item.status not in {"pass", "warning"} and item.remediation and item.remediation not in report["next_actions"]:
            report["next_actions"].append(item.remediation)
    return report


def evaluate_release_readiness(
    root: Path,
    *,
    execute: bool = False,
    online: bool = False,
    work_directory: Path | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    channels_path = root / "release" / "channels.toml"
    channels = _read_toml(channels_path)
    checks = _static_checks(root, channels)
    artifacts: list[Path] = []
    if execute:
        work = (work_directory or Path(tempfile.mkdtemp(prefix="vladder-release-readiness-"))).resolve()
        work.mkdir(parents=True, exist_ok=True)
        executed, artifacts = _execution_checks(root, work)
        checks.extend(executed)
    else:
        work = work_directory
        for item in (
            ("validation.full-tests", "functionality", "Complete supported-language and workflow test suite", "python -m pytest -q"),
            ("validation.quality", "quality", "Static and security analysis", "python -m ruff; python -m bandit"),
            ("validation.openspec", "governance", "Strict OpenSpec validation", "openspec validate --all --strict"),
            (
                "validation.production-canonical-search-smoke",
                "functionality",
                "Production canonical-search smoke battery",
                "vladder release smoke-canonical-search",
            ),
            ("artifacts.build", "artifacts", "Build, audit, and clean-install wheel and sdist", "python -m build"),
        ):
            checks.append(_not_run(*item))
    checks.extend(_online_checks(root, channels) if online else _deferred_checks())
    checks.append(_clean_worktree_check(root))
    report = {
        "schema_version": REPORT_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "release_version": _read_toml(root / "pyproject.toml")["project"]["version"],
        "root": str(root),
        "modes": {"execute": execute, "online": online},
        "channel_manifest": str(channels_path),
        "artifacts": [str(item) for item in artifacts],
        "work_directory": str(work) if work else None,
    }
    return _finalize_report(report, checks)


def refresh_online_release_readiness(report: dict[str, Any], root: Path) -> dict[str, Any]:
    root = root.resolve()
    if report.get("schema_version") != REPORT_VERSION:
        raise ValueError(f"cannot refresh report schema {report.get('schema_version')!r}")
    expected_version = str(_read_toml(root / "pyproject.toml")["project"]["version"])
    if report.get("release_version") != expected_version or Path(str(report.get("root"))).resolve() != root:
        raise ValueError("local report does not match this source root and release version")
    if not report.get("modes", {}).get("execute"):
        raise ValueError("online refresh requires a report produced with --execute")
    dynamic_ids = {
        "channels.online", "github.repository", "github.branch-protection", "github.latest-ci",
        "github.environment-pypi", "github.environment-testpypi", "github.environment-homebrew",
        "pypi.trusted-publisher", "testpypi.trusted-publisher", "homebrew.github-configuration",
        "homebrew.tap", "services.contribution-health", "source.clean-worktree",
    }
    checks = [
        ReadinessCheck(
            item["id"], item["level"], item["requirement"], item["status"], item["detail"],
            tuple(item.get("evidence", ())), item.get("remediation"), tuple(item.get("blocks", ())),
        )
        for item in report["checks"]
        if item["id"] not in dynamic_ids
    ]
    channels = _read_toml(root / "release" / "channels.toml")
    checks.extend(_online_checks(root, channels))
    checks.append(_clean_worktree_check(root))
    report = dict(report)
    report["generated_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    report["modes"] = {"execute": True, "online": True, "reused_local_evidence": True}
    return _finalize_report(report, checks)


def write_release_readiness(report: dict[str, Any], output: Path) -> None:
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
