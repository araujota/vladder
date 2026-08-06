#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import zipfile

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 development environments
    import tomli as tomllib


REQUIRED_RELEASE_FILES = (
    ".github/workflows/ci.yml",
    ".github/workflows/release.yml",
    ".github/workflows/test-publish.yml",
    "CHANGELOG.md",
    "docs/releasing.md",
    "packaging/homebrew/vladder.rb.in",
    "scripts/render_homebrew_formula.py",
)


def project_version(root: Path) -> str:
    with (root / "pyproject.toml").open("rb") as handle:
        return str(tomllib.load(handle)["project"]["version"])


def runtime_version(root: Path) -> str:
    text = (root / "vladder" / "__init__.py").read_text()
    match = re.search(r'^__version__\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not match:
        raise ValueError("vladder/__init__.py does not declare __version__")
    return match.group(1)


def artifact_version(path: Path) -> str | None:
    if path.suffix == ".whl":
        match = re.match(r"vladder-([^-]+)-", path.name)
        return match.group(1) if match else None
    if path.name.endswith(".tar.gz"):
        match = re.match(r"vladder-(.+)\.tar\.gz$", path.name)
        return match.group(1) if match else None
    return None


def git_check(root: Path) -> tuple[bool, str]:
    result = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        return False, "not a Git worktree"
    if result.stdout.strip():
        return False, "Git worktree is not clean"
    return True, "clean"


def inspect_archive(path: Path) -> tuple[bool, str]:
    try:
        if path.suffix == ".whl":
            with zipfile.ZipFile(path) as archive:
                names = archive.namelist()
        else:
            with tarfile.open(path) as archive:
                names = archive.getnames()
    except (OSError, tarfile.TarError, zipfile.BadZipFile) as error:
        return False, f"unreadable archive: {error}"
    forbidden = [name for name in names if "release-validation" in name or "__pycache__" in name]
    return (not forbidden, "clean" if not forbidden else f"forbidden entries: {forbidden[:5]}")


def preflight(
    root: Path,
    repository: str | None = None,
    tag: str | None = None,
    dist_dir: Path | None = None,
    require_git: bool = False,
    require_artifacts: bool = False,
) -> dict[str, object]:
    root = root.resolve()
    version = project_version(root)
    checks: list[dict[str, object]] = []

    def add(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "status": "pass" if passed else "fail", "detail": detail})

    runtime = runtime_version(root)
    add("version_identity", version == runtime, f"project={version} runtime={runtime}")
    readme = (root / "README.md").read_text()
    changelog = (root / "CHANGELOG.md").read_text() if (root / "CHANGELOG.md").exists() else ""
    add("readme_version", version in readme, version)
    add("changelog_version", version in changelog, version)
    missing = [name for name in REQUIRED_RELEASE_FILES if not (root / name).is_file()]
    add("release_files", not missing, "complete" if not missing else f"missing: {missing}")

    if repository is not None:
        valid_repository = bool(re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository)) and "OWNER" not in repository
        add("repository", valid_repository, repository)
    if tag is not None:
        add("tag_identity", tag == f"v{version}", f"tag={tag} expected=v{version}")

    git_ok, git_detail = git_check(root)
    if require_git:
        add("git", git_ok, git_detail)
    else:
        checks.append({"name": "git", "status": "pass" if git_ok else "pending", "detail": git_detail})

    artifact_root = (dist_dir or root / "dist").resolve()
    artifacts = sorted(path for path in artifact_root.glob("vladder-*") if path.is_file())
    matching = [path for path in artifacts if artifact_version(path) == version]
    wheel = [path for path in matching if path.suffix == ".whl"]
    sdist = [path for path in matching if path.name.endswith(".tar.gz")]
    if matching or require_artifacts:
        add("artifacts", bool(wheel) and bool(sdist), f"wheel={len(wheel)} sdist={len(sdist)}")
    else:
        checks.append({"name": "artifacts", "status": "pending", "detail": "build has not produced distributions"})
    for path in matching:
        clean, detail = inspect_archive(path)
        add(f"artifact:{path.name}", clean, detail)

    status = "pass" if all(item["status"] != "fail" for item in checks) else "fail"
    return {
        "schema_version": "vladder-release-preflight-v1",
        "status": status,
        "version": version,
        "repository": repository,
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate vLadder release identity and artifacts")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--repository", help="GitHub repository as OWNER/REPOSITORY")
    parser.add_argument("--tag", help="release tag matching the project version, for example v<VERSION>")
    parser.add_argument("--dist-dir", type=Path)
    parser.add_argument("--require-git", action="store_true")
    parser.add_argument("--require-artifacts", action="store_true")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = preflight(args.root, args.repository, args.tag, args.dist_dir, args.require_git, args.require_artifacts)
    output = json.dumps(result, indent=2, sort_keys=True) + "\n"
    print(output, end="")
    if args.out:
        args.out.write_text(output)
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
