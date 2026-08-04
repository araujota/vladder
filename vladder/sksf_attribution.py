from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any


ADMISSION_STATES = {"admitted", "exploratory", "rejected"}
BOTTLENECK_KINDS = {"cycles", "bandwidth", "cache_traffic", "synchronization"}


@dataclass(frozen=True)
class Bottleneck:
    id: str
    region: str
    kind: str
    metric: str
    value: float
    unit: str
    runtime_fraction: float
    resolution: str
    confidence: str


@dataclass(frozen=True)
class AttributionStudy:
    schema_version: str
    id: str
    target: str
    workload: str
    source_artifact: str
    source_sha256: str
    measurement_class: str
    instrumented: bool
    study_hash: str
    bottlenecks: tuple[Bottleneck, ...]
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GrammarAdmission:
    family: str
    state: str
    study_id: str
    bottleneck_ids: tuple[str, ...]
    target_metric: str
    expected_direction: str
    reason: str
    evidence_hash: str


def load_attribution_study(path: Path, *, verify_source: bool = True) -> AttributionStudy:
    raw = json.loads(path.read_text())
    required = {
        "schema_version", "id", "target", "workload", "source_artifact", "source_sha256",
        "measurement_class", "instrumented", "bottlenecks",
    }
    missing = sorted(required - set(raw))
    if missing:
        raise ValueError("attribution study missing: " + ", ".join(missing))
    source = Path(str(raw["source_artifact"]))
    if not source.is_absolute():
        source = (path.parent / source).resolve()
    if verify_source:
        if not source.is_file():
            raise ValueError(f"attribution source artifact does not exist: {source}")
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        if digest != str(raw["source_sha256"]):
            raise ValueError("attribution source artifact hash mismatch")
    bottlenecks = tuple(_bottleneck(item) for item in raw["bottlenecks"])
    ids = [item.id for item in bottlenecks]
    if len(ids) != len(set(ids)):
        raise ValueError("bottleneck ids must be unique")
    canonical = {key: value for key, value in raw.items() if key != "study_hash"}
    study_hash = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    declared_hash = raw.get("study_hash")
    if declared_hash is not None and declared_hash != study_hash:
        raise ValueError("attribution study hash mismatch")
    return AttributionStudy(
        str(raw["schema_version"]), str(raw["id"]), str(raw["target"]), str(raw["workload"]),
        str(source), str(raw["source_sha256"]), str(raw["measurement_class"]), bool(raw["instrumented"]),
        study_hash, bottlenecks, tuple(str(item) for item in raw.get("limitations", [])),
    )


def evaluate_grammar_admission(
    family: str,
    evidence: dict[str, Any],
    studies: dict[str, AttributionStudy],
    *,
    minimum_runtime_fraction: float = 0.05,
) -> GrammarAdmission:
    study_id = str(evidence.get("study_id", ""))
    bottleneck_ids = tuple(str(value) for value in evidence.get("bottleneck_ids", []))
    target_metric = str(evidence.get("target_metric", ""))
    direction = str(evidence.get("expected_direction", ""))
    if study_id not in studies:
        return _admission(family, "rejected", study_id, bottleneck_ids, target_metric, direction, "missing attribution study", "")
    study = studies[study_id]
    indexed = {item.id: item for item in study.bottlenecks}
    missing = sorted(set(bottleneck_ids) - set(indexed))
    if not bottleneck_ids or missing:
        reason = "no bottleneck cited" if not bottleneck_ids else "unknown bottlenecks: " + ", ".join(missing)
        return _admission(family, "rejected", study_id, bottleneck_ids, target_metric, direction, reason, study.study_hash)
    if direction not in {"decrease", "increase"} or not target_metric:
        return _admission(family, "rejected", study_id, bottleneck_ids, target_metric, direction, "invalid metric hypothesis", study.study_hash)
    selected = [indexed[item] for item in bottleneck_ids]
    if target_metric not in {item.metric for item in selected}:
        return _admission(family, "rejected", study_id, bottleneck_ids, target_metric, direction, "target metric is not present in cited evidence", study.study_hash)
    maximum_share = max(item.runtime_fraction for item in selected)
    if maximum_share < minimum_runtime_fraction:
        return _admission(
            family, "exploratory", study_id, bottleneck_ids, target_metric, direction,
            f"measured runtime fraction {maximum_share:.4f} is below admission threshold {minimum_runtime_fraction:.4f}",
            study.study_hash,
        )
    if study.instrumented and not bool(evidence.get("allow_instrumented_attribution", False)):
        return _admission(family, "exploratory", study_id, bottleneck_ids, target_metric, direction, "instrumented evidence requires explicit exploratory admission", study.study_hash)
    return _admission(family, "admitted", study_id, bottleneck_ids, target_metric, direction, "measured bottleneck supports grammar hypothesis", study.study_hash)


def _bottleneck(raw: dict[str, Any]) -> Bottleneck:
    kind = str(raw["kind"])
    if kind not in BOTTLENECK_KINDS:
        raise ValueError(f"unsupported bottleneck kind {kind}")
    fraction = float(raw["runtime_fraction"])
    if not 0.0 <= fraction <= 1.0:
        raise ValueError("runtime_fraction must be in [0,1]")
    return Bottleneck(
        str(raw["id"]), str(raw["region"]), kind, str(raw["metric"]), float(raw["value"]),
        str(raw["unit"]), fraction, str(raw["resolution"]), str(raw["confidence"]),
    )


def _admission(
    family: str,
    state: str,
    study_id: str,
    bottleneck_ids: tuple[str, ...],
    target_metric: str,
    direction: str,
    reason: str,
    evidence_hash: str,
) -> GrammarAdmission:
    if state not in ADMISSION_STATES:
        raise ValueError(f"invalid admission state {state}")
    return GrammarAdmission(family, state, study_id, bottleneck_ids, target_metric, direction, reason, evidence_hash)
