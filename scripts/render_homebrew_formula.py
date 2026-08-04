#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any
from urllib.request import urlopen

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 development environments
    import tomli as tomllib


DEPENDENCIES = {"PyYAML": "6.0.3", "z3-solver": "4.16.0.0"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def pypi_sdist(project: str, version: str, metadata: dict[str, Any] | None = None) -> dict[str, str]:
    payload = metadata
    if payload is None:
        with urlopen(f"https://pypi.org/pypi/{project}/{version}/json", timeout=30) as response:
            payload = json.load(response)
    files = payload.get("urls", [])
    matches = [item for item in files if item.get("packagetype") == "sdist"]
    if len(matches) != 1:
        raise ValueError(f"expected one sdist for {project} {version}, found {len(matches)}")
    item = matches[0]
    digest = item.get("digests", {}).get("sha256")
    if not digest or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError(f"missing SHA-256 for {project} {version}")
    return {"url": str(item["url"]), "sha256": str(digest)}


def package_version(root: Path) -> str:
    with (root / "pyproject.toml").open("rb") as handle:
        return str(tomllib.load(handle)["project"]["version"])


def render(
    template: str,
    repository: str,
    version: str,
    source_url: str,
    source_sha256: str,
    resources: dict[str, dict[str, str]],
) -> str:
    substitutions = {
        "@REPOSITORY@": repository,
        "@VERSION@": version,
        "@SOURCE_URL@": source_url,
        "@SOURCE_SHA256@": source_sha256,
        "@PYYAML_URL@": resources["PyYAML"]["url"],
        "@PYYAML_SHA256@": resources["PyYAML"]["sha256"],
        "@Z3_SOLVER_URL@": resources["z3-solver"]["url"],
        "@Z3_SOLVER_SHA256@": resources["z3-solver"]["sha256"],
    }
    result = template
    for marker, value in substitutions.items():
        result = result.replace(marker, value)
    unresolved = sorted(set(re.findall(r"@[A-Z0-9_]+@", result)))
    if unresolved:
        raise ValueError(f"unresolved formula markers: {unresolved}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Render an exact-hash vLadder Homebrew formula")
    parser.add_argument("--repository", required=True, help="GitHub repository as OWNER/REPOSITORY")
    parser.add_argument("--version")
    parser.add_argument("--source-path", type=Path, required=True)
    parser.add_argument("--source-url")
    parser.add_argument("--metadata", type=Path, help="optional JSON map of dependency PyPI responses")
    parser.add_argument("--template", type=Path, default=Path("packaging/homebrew/vladder.rb.in"))
    parser.add_argument("--output", type=Path, default=Path("release/vladder.rb"))
    args = parser.parse_args()

    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.repository):
        raise SystemExit("--repository must be OWNER/REPOSITORY")
    root = Path(__file__).resolve().parent.parent
    version = args.version or package_version(root)
    source = args.source_path.resolve()
    expected_name = f"vladder-{version}.tar.gz"
    if source.name != expected_name:
        raise SystemExit(f"source artifact must be named {expected_name}")
    source_url = args.source_url or f"https://github.com/{args.repository}/releases/download/v{version}/{expected_name}"
    metadata = json.loads(args.metadata.read_text()) if args.metadata else {}
    resources = {
        project: pypi_sdist(project, dependency_version, metadata.get(project))
        for project, dependency_version in DEPENDENCIES.items()
    }
    formula = render(
        args.template.read_text(),
        args.repository,
        version,
        source_url,
        sha256(source),
        resources,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(formula)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
