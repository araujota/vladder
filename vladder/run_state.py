from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any


@dataclass
class ContentAddressedRun:
    root: Path
    identity: dict[str, Any]

    @property
    def key(self) -> str:
        canonical = json.dumps(self.identity, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()

    @property
    def directory(self) -> Path:
        return self.root / self.key

    def initialize(self) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        identity_path = self.directory / "identity.json"
        canonical = json.dumps(self.identity, indent=2, sort_keys=True) + "\n"
        if identity_path.exists() and identity_path.read_text() != canonical:
            raise RuntimeError("content-address collision or modified run identity")
        identity_path.write_text(canonical)
        return self.directory

    def complete_step(self, step: str, artifacts: list[Path]) -> None:
        missing = [str(path) for path in artifacts if not path.exists()]
        if missing:
            raise ValueError("cannot complete step with missing artifacts: " + ", ".join(missing))
        state = self.state()
        state[step] = {"status": "complete", "artifacts": [_artifact(path) for path in artifacts]}
        (self.directory / "state.json").write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")

    def step_is_valid(self, step: str) -> bool:
        record = self.state().get(step)
        if not isinstance(record, dict) or record.get("status") != "complete":
            return False
        return all(_artifact(Path(item["path"])) == item for item in record.get("artifacts", []))

    def state(self) -> dict[str, Any]:
        path = self.directory / "state.json"
        return json.loads(path.read_text()) if path.exists() else {}


def _artifact(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {"path": str(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
