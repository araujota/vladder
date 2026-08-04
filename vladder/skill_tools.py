from __future__ import annotations

from importlib.resources import as_file, files
from pathlib import Path
import re
import shutil
import hashlib
from typing import Any


def bundled_skill() -> Any:
    return files("vladder").joinpath("skills", "vladder")


def validate_skill(path: Path | None = None) -> dict[str, object]:
    if path is None:
        resource = bundled_skill()
        text = resource.joinpath("SKILL.md").read_text(encoding="utf-8")
        source = str(resource)
    else:
        source_path = path.resolve()
        text = (source_path / "SKILL.md").read_text()
        source = str(source_path)
    match = re.match(r"^---\n(.*?)\n---\n", text, flags=re.DOTALL)
    errors: list[str] = []
    if not match:
        errors.append("SKILL.md is missing YAML frontmatter")
    else:
        frontmatter = match.group(1)
        if not re.search(r"^name:\s*vladder\s*$", frontmatter, flags=re.MULTILINE):
            errors.append("skill name must be vladder")
        description = re.search(r"^description:\s*(.+)$", frontmatter, flags=re.MULTILINE)
        if not description or len(description.group(1).strip()) < 40:
            errors.append("skill description is missing or too short")
    if len(text.splitlines()) > 500:
        errors.append("SKILL.md exceeds 500 lines")
    return {"status": "pass" if not errors else "fail", "source": source, "errors": errors}


def _tree_hash(path: Path) -> str:
    digest = hashlib.sha256()
    for item in sorted(candidate for candidate in path.rglob("*") if candidate.is_file()):
        digest.update(str(item.relative_to(path)).encode("utf-8"))
        digest.update(item.read_bytes())
    return digest.hexdigest()


def install_skill(target_root: Path, force: bool = False) -> dict[str, object]:
    target = target_root.expanduser().resolve() / "vladder"
    validation = validate_skill()
    if validation["status"] != "pass":
        raise RuntimeError("bundled vLadder skill is invalid")
    target.parent.mkdir(parents=True, exist_ok=True)
    resource = bundled_skill()
    with as_file(resource) as source:
        source_hash = _tree_hash(source)
        if target.exists() and _tree_hash(target) == source_hash:
            return {"status": "pass", "target": str(target), "already_current": True, "validation": validate_skill(target)}
        if target.exists() and not force:
            raise FileExistsError(f"skill target exists and differs: {target}; pass --force to replace it")
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target)
    installed_validation = validate_skill(target)
    if installed_validation["status"] != "pass":
        raise RuntimeError("installed vLadder skill failed validation")
    return {"status": "pass", "target": str(target), "validation": installed_validation}
