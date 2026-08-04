#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
import tarfile
import zipfile


FORBIDDEN_PARTS = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".git",
    "third_party",
    "node_modules",
    "build",
}
FORBIDDEN_SUFFIXES = {".gguf", ".onnx", ".safetensors", ".pyc", ".o", ".so", ".a"}
REQUIRED_TREE = {
    ".github/workflows/ci.yml",
    ".github/workflows/release.yml",
    ".github/workflows/test-publish.yml",
    "CHANGELOG.md",
    "LICENSE",
    "README.md",
    "docs/releasing.md",
    "packaging/homebrew/vladder.rb.in",
    "pyproject.toml",
    "vladder/__init__.py",
    "vladder/grammars/vladder-v1/capabilities.json",
    "vladder/grammars/lifetime-v1/grammar.json",
    "vladder/skills/vladder/SKILL.md",
    "vladder/skills/vladder/references/lifetime.md",
    "scripts/install.sh",
}
REQUIRED_PACKAGE_SUFFIXES = {
    "vladder/grammars/vladder-v1/capabilities.json",
    "vladder/grammars/lifetime-v1/grammar.json",
    "vladder/skills/vladder/SKILL.md",
    "vladder/skills/vladder/references/lifetime.md",
}
REQUIRED_SDIST_SUFFIXES = {
    "CHANGELOG.md",
    "LICENSE",
    "README.md",
    "docs/releasing.md",
    "packaging/homebrew/vladder.rb.in",
    "scripts/install.sh",
    "scripts/audit_release.py",
    "scripts/release_preflight.py",
    "scripts/render_homebrew_formula.py",
    "examples/lifetime/lifetime_corpus.yaml",
    "examples/lifetime/lifetime_trace.json",
}


def _is_forbidden(path: PurePosixPath, *, allow_egg_info: bool = False) -> bool:
    return (
        any(
            part in FORBIDDEN_PARTS
            or part.startswith("out-")
            or (part.endswith(".egg-info") and not allow_egg_info)
            for part in path.parts
        )
        or path.suffix.lower() in FORBIDDEN_SUFFIXES
        or path.name in {".env", ".env.local", "credentials.json"}
    )


def audit_tree(root: Path) -> dict[str, object]:
    failures: list[str] = []
    for required in sorted(REQUIRED_TREE):
        if not (root / required).exists():
            failures.append(f"missing required release file: {required}")
    scanned = 0
    for item in root.rglob("*"):
        relative = PurePosixPath(item.relative_to(root).as_posix())
        if ".git" in relative.parts:
            continue
        if _is_forbidden(relative):
            failures.append(f"forbidden release residue: {relative}")
        if item.is_file():
            scanned += 1
            if item.stat().st_size > 20 * 1024 * 1024:
                failures.append(f"oversized release file: {relative}")
    return {"kind": "tree", "root": str(root), "files_scanned": scanned, "status": "pass" if not failures else "fail", "failures": failures}


def _archive_names(path: Path) -> list[str]:
    if path.suffix == ".whl" or zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            return archive.namelist()
    with tarfile.open(path) as archive:
        return archive.getnames()


def audit_artifact(path: Path) -> dict[str, object]:
    names = _archive_names(path)
    normalized = [PurePosixPath(name) for name in names if not name.endswith("/")]
    allow_egg_info = path.suffixes[-2:] == [".tar", ".gz"]
    failures = [
        f"forbidden packaged residue: {name}"
        for name in normalized
        if _is_forbidden(name, allow_egg_info=allow_egg_info)
    ]
    for suffix in sorted(REQUIRED_PACKAGE_SUFFIXES):
        if not any(str(name).endswith(suffix) for name in normalized):
            failures.append(f"missing packaged resource: {suffix}")
    if allow_egg_info:
        for suffix in sorted(REQUIRED_SDIST_SUFFIXES):
            if not any(str(name).endswith(suffix) for name in normalized):
                failures.append(f"missing source-distribution resource: {suffix}")
    return {"kind": "artifact", "path": str(path), "files_scanned": len(normalized), "status": "pass" if not failures else "fail", "failures": failures}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, help="audit a source tree; defaults to the current directory when no artifacts are supplied")
    parser.add_argument("--artifact", type=Path, action="append", default=[])
    args = parser.parse_args()
    reports = []
    if args.root is not None:
        reports.append(audit_tree(args.root.resolve()))
    elif not args.artifact:
        reports.append(audit_tree(Path.cwd().resolve()))
    reports.extend(audit_artifact(path.resolve()) for path in args.artifact)
    result = {"schema_version": "vladder-release-audit-v1", "status": "pass" if all(report["status"] == "pass" for report in reports) else "fail", "reports": reports}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
