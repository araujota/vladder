from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import yaml

from vladder.agent_workflow import build_promotion_summary, initialize_workflow_manifest
from vladder.closure_bindings import (
    cpp_effect_footprint,
    julia_effect_footprint,
    rust_effect_footprint,
    zig_effect_footprint,
)
from vladder.protocol_envelopes import protocol_registry, validate_protocol_application
from vladder.rust_semantics import RustEffectSummary
from vladder.semantic_closure import (
    CallRelation,
    EffectFootprint,
    FunctionSummary,
    compose_system_graph,
    prove_system_graph,
)
from vladder.system_closure import run_system_closure


def summary(
    identifier: str,
    *,
    calls: tuple[CallRelation, ...] = (),
    effects: EffectFootprint = EffectFootprint(),
    candidates: int = 0,
) -> FunctionSummary:
    return FunctionSummary(
        identifier, "cpp", "clang-20", f"body-{identifier}", f"graph-{identifier}",
        effects, calls, candidates,
    )


class SemanticClosureTests(unittest.TestCase):
    def test_effect_lattice_is_deterministic_and_monotone(self) -> None:
        left = EffectFootprint(("b", "a"), ("dst",), ("cleanup",))
        right = EffectFootprint(("a",), ("global",), ("publish",))
        joined = left.join(right)
        self.assertEqual(joined.reads, ("a", "b"))
        self.assertTrue(joined.contains(left))
        self.assertTrue(joined.contains(right))
        self.assertEqual(joined, right.join(left))

    def test_definition_visible_chain_closes_and_proves(self) -> None:
        helper = summary("helper", effects=EffectFootprint(("argmem",)))
        relation = CallRelation(
            "root.helper", "root", ("helper",), "definition", "helper",
            EffectFootprint(("argmem",)), authority="definition-hash",
            crossing="call-preserving-only",
        )
        root = summary("root", calls=(relation,), candidates=7)
        graph = compose_system_graph("chain", (root, helper))
        self.assertEqual(graph["closure"], "closed")
        self.assertEqual(graph["computational_candidate_count"], 7)
        self.assertEqual(graph["protocol_summary_candidate_count"], 0)
        with tempfile.TemporaryDirectory() as directory:
            proof = prove_system_graph(graph, Path(directory))
            self.assertEqual(proof["status"], "PASS")

    def test_recursive_component_reaches_finite_fixpoint(self) -> None:
        left_call = CallRelation(
            "left.right", "left", ("right",), "definition", "right", EffectFootprint(),
            authority="definition-hash", crossing="call-preserving-only",
        )
        right_call = CallRelation(
            "right.left", "right", ("left",), "definition", "left", EffectFootprint(),
            authority="definition-hash", crossing="call-preserving-only",
        )
        graph = compose_system_graph(
            "recursive",
            (
                summary("left", calls=(left_call,), effects=EffectFootprint(flags=("cleanup",))),
                summary("right", calls=(right_call,), effects=EffectFootprint(flags=("publish",))),
            ),
        )
        self.assertEqual(graph["recursive_components"], [["left", "right"]])
        for function in graph["functions"]:
            self.assertEqual(set(function["transitive_effects"]["flags"]), {"cleanup", "publish"})

    def test_finite_dispatch_set_composes_without_open_callback_search(self) -> None:
        dispatch = CallRelation(
            "root.dispatch", "root", ("left", "right"), "finite_dispatch", "selected_handler",
            EffectFootprint(), authority="contract", crossing="call-preserving-only",
            provenance={"finite_target_guard": "handler_id in {left,right}"},
        )
        graph = compose_system_graph(
            "dispatch", (summary("root", calls=(dispatch,)), summary("left"), summary("right"))
        )
        self.assertEqual(graph["closure"], "closed")
        self.assertEqual(len(graph["edges"]), 2)

    def test_opaque_callback_is_local_and_verbose(self) -> None:
        opaque = CallRelation(
            "submit.callback", "submit", (), "opaque", "callback(payload)",
            EffectFootprint(flags=("callback",), unknown=True), authority="opaque", crossing="forbidden",
            provenance={
                "native_construct": "Callback&&",
                "missing_contract": "finite callback target set",
                "next_action": "retain submission and optimize the closed payload encoder",
            },
        )
        graph = compose_system_graph(
            "boundary",
            (summary("encode", candidates=4), summary("submit", calls=(opaque,))),
        )
        rows = {item["id"]: item for item in graph["functions"]}
        self.assertEqual(rows["encode"]["closure"], "closed")
        self.assertEqual(rows["submit"]["closure"], "partial_with_local_subgraphs")
        self.assertEqual(graph["computational_candidate_count"], 4)
        self.assertEqual(graph["boundaries"][0]["missing_contract"], "finite callback target set")

    def test_protocol_registry_adds_no_candidate_dimensions(self) -> None:
        registry = protocol_registry()
        self.assertGreaterEqual(len(registry["envelopes"]), 7)
        self.assertEqual(registry["candidate_dimensions_added"], 0)

    def test_protocol_application_fails_closed_until_every_guard_is_bound(self) -> None:
        registry = protocol_registry()
        envelope = next(item for item in registry["envelopes"] if item["id"] == "bounded-no-growth-append")
        incomplete = validate_protocol_application({
            "envelope": "bounded-no-growth-append",
            "established_guards": envelope["applicability_guards"][:-1],
        })
        self.assertEqual(incomplete["status"], "requires_guard_evidence")
        self.assertEqual(incomplete["crossing"], "forbidden")
        closed = validate_protocol_application({
            "envelope": "bounded-no-growth-append",
            "established_guards": envelope["applicability_guards"],
            "proof_method": "Z3 capacity + typed triviality",
        })
        self.assertEqual(closed["status"], "closed")
        self.assertEqual(closed["crossing"], "permitted")

    def test_language_bindings_share_effect_vocabulary(self) -> None:
        cpp = cpp_effect_footprint({
            "memory_effect": "argmem: readwrite", "allocation_calls": ["malloc"],
            "deallocation_calls": ["free"], "unwind_operations": False, "nounwind": True,
            "synchronization_operations": False, "volatile_operations": False,
            "external_calls": [], "indirect_calls": 0, "global_stores": 0,
        })
        rust = rust_effect_footprint(RustEffectSummary(
            True, True, False, True, True, True, True, (), (), (),
        ))
        zig = zig_effect_footprint("pub fn f(a: []u8) void { defer allocator.free(a); }")
        julia = julia_effect_footprint("invoke jl_gc_alloc", "", allocated_bytes=64)
        for item in (cpp, rust, zig, julia):
            self.assertTrue(set(item.flags) <= {
                "allocate", "deallocate", "cleanup", "unwind", "synchronize", "atomic",
                "volatile", "publish", "invalidate", "external_io", "callback",
                "nondeterminism", "nontermination",
            })
        self.assertIn("allocate", cpp.flags)
        self.assertIn("allocate", rust.flags)
        self.assertIn("deallocate", zig.flags)
        self.assertIn("allocate", julia.flags)

    def test_manifest_workflow_emits_decisive_artifacts(self) -> None:
        relation = CallRelation(
            "root.helper", "root", ("helper",), "definition", "helper", EffectFootprint(),
            authority="definition-hash", crossing="call-preserving-only",
        )
        manifest = {
            "system": "fixture",
            "functions": [summary("root", calls=(relation,), candidates=3).to_dict(), summary("helper").to_dict()],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = root / "system.yaml"
            manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=True))
            report = run_system_closure(manifest_path, root / "out")
            self.assertEqual(report["status"], "pass")
            self.assertTrue((root / "out" / "system-flow-graph.json").exists())
            stored = json.loads((root / "out" / "system-closure-report.json").read_text())
            self.assertEqual(stored["system_graph"]["computational_candidate_count"], 3)
            self.assertFalse(stored["candidate_generation_performed"])

    def test_manifest_can_ingest_existing_inspection_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inspection = root / "cpp-support.json"
            inspection.write_text(json.dumps({"compositional_summary": summary("captured").to_dict()}))
            manifest_path = root / "system.yaml"
            manifest_path.write_text(yaml.safe_dump({"system": "captured", "reports": [inspection.name]}))
            report = run_system_closure(manifest_path, root / "out")
            self.assertEqual(report["system_graph"]["functions"][0]["id"], "captured")

    def test_agent_workflow_has_an_explicit_system_closure_route(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workflow = initialize_workflow_manifest("system", root / "workflow.yaml")
            self.assertEqual(workflow["region"]["action"], "closure")
            report = {
                "schema_version": "system-closure-workflow-v1",
                "status": "pass",
                "system_graph": {"functions": [{"id": "f"}], "closure": "closed"},
                "proof": {"status": "PASS"},
                "boundary_summary": [],
                "next_action": "run attributed grammar",
            }
            summary_report = build_promotion_summary(
                report, report_path=root / "system-closure-report.json", workflow_kind="system"
            )
            self.assertTrue(summary_report["states"]["meaningful_semantic_coverage"])
            self.assertTrue(summary_report["states"]["candidate_proved"])
            self.assertFalse(summary_report["states"]["candidate_generated"])


if __name__ == "__main__":
    unittest.main()
