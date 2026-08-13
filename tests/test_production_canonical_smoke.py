from __future__ import annotations

from vladder.canonical_search import LayeredStateHash
from vladder.production_smoke import SMOKE_STAGE_ORDER, run_production_canonical_smoke
from vladder.schema_registry import validate_payload


def test_incremental_hash_disagreement_returns_clean_rematerialization() -> None:
    parent = {"stable": {"value": 1}, "changed": 2}
    child = {"stable": {"value": 1}, "changed": 3}
    layered = LayeredStateHash.build(parent)
    result, fallback, incident = layered.update_or_rematerialize(
        child, changed={"changed": 99},
    )
    assert fallback is True
    assert incident == "incremental state hash differs from clean rematerialization"
    assert result == LayeredStateHash.build(child)


def test_release_blocking_production_canonical_smoke_battery() -> None:
    report = run_production_canonical_smoke()
    assert validate_payload("production-canonical-search-smoke", report)["status"] == "pass"
    assert report["status"] == "PASS"
    assert report["release_blocking"] is True
    assert tuple(report["stage_order"]) == SMOKE_STAGE_ORDER
    assert report["summary"]["passed"] == 8
    assert report["summary"]["failed"] == 0
    assert all(stage["status"] == "PASS" for stage in report["stages"])
