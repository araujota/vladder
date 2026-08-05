#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml
import z3


def _affine(seed: dict[str, Any]) -> tuple[z3.Solver, z3.ExprRef]:
    x = z3.BitVec(f"x_{seed['id'].replace('-', '_')}", 32)
    reference = seed["reference"]
    candidate = seed["candidate"]
    ref = x * int(reference["multiplier"]) + int(reference["addend"])
    cand = (
        x * int(candidate["x_terms"])
        + (x << int(candidate["shift"])) * int(candidate["shifted_x_terms"])
        + int(candidate["addend"])
    )
    solver = z3.Solver()
    solver.add(ref != cand)
    return solver, x


def _mask_count(seed: dict[str, Any]) -> tuple[z3.Solver, z3.ExprRef]:
    mask = z3.BitVec(f"mask_{seed['id'].replace('-', '_')}", 8)
    candidate_mask = z3.BitVecVal(int(seed["candidate_mask"]), 8)
    reference = z3.Sum([z3.If(z3.Extract(i, i, mask) == 1, 1, 0) for i in range(8)])
    candidate = z3.Sum([z3.If(z3.Extract(i, i, mask & candidate_mask) == 1, 1, 0) for i in range(8)])
    solver = z3.Solver()
    solver.add(reference != candidate)
    return solver, mask


def validate(manifest: Path, output: Path) -> dict[str, Any]:
    raw = yaml.safe_load(manifest.resolve().read_text())
    if raw.get("schema_version") != "vladder-release-seeds-v1":
        raise ValueError("unsupported release seed manifest")
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    for seed in raw.get("seeds", []):
        if seed["family"] == "u32-affine":
            solver, witness = _affine(seed)
        elif seed["family"] == "u8-mask-count":
            solver, witness = _mask_count(seed)
        else:
            raise ValueError(f"unknown seeded family {seed['family']!r}")
        result = solver.check()
        disposition = "accept" if result == z3.unsat else "reject"
        counterexample = None
        if result == z3.sat:
            counterexample = str(solver.model().eval(witness, model_completion=True))
        smt_path = output / f"{seed['id']}.smt2"
        smt_path.write_text(solver.to_smt2())
        rows.append({
            "id": seed["id"],
            "family": seed["family"],
            "expected": seed["expected"],
            "actual": disposition,
            "status": "pass" if disposition == seed["expected"] else "fail",
            "solver_result": str(result),
            "counterexample": counterexample,
            "artifact": str(smt_path),
        })
    report = {
        "schema_version": "vladder-release-seed-results-v1",
        "status": "pass" if rows and all(row["status"] == "pass" for row in rows) else "fail",
        "accepted_seed_count": sum(row["actual"] == "accept" for row in rows),
        "rejected_seed_count": sum(row["actual"] == "reject" for row in rows),
        "seeds": rows,
    }
    (output / "release-seeds.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate seeded good and bad semantic transformations")
    parser.add_argument("--manifest", default="examples/release_seeds/transformations.yaml")
    parser.add_argument("--out-dir", default="release-validation/seeds")
    args = parser.parse_args()
    report = validate(Path(args.manifest), Path(args.out_dir))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
