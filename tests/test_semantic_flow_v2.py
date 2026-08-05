from __future__ import annotations

import unittest

from vladder.language_adapter import (
    ProtocolTransition,
    SemanticEffect,
    SemanticFlowEdge,
    SemanticFlowGraph,
    SemanticFlowNode,
    obligation,
)


class SemanticFlowV2Tests(unittest.TestCase):
    def test_typed_obligations_effects_and_protocols_are_hash_bound(self) -> None:
        bounded = obligation("test.bounds", "bounds", "index is below extent", proof_method="Z3")
        graph = SemanticFlowGraph(
            "bounded-copy",
            "cpp",
            "clang-20",
            "llvm",
            "function-hash",
            (
                SemanticFlowNode("input", "Input", "borrow", (), "u8", {}, {}, (bounded,)),
                SemanticFlowNode("output", "Output", "copy", ("input",), "u8", {}, {}, ()),
            ),
            (SemanticFlowEdge("flow", "input", "output", "u8", "borrowed", "arg0", "call", "program-order"),),
            {"exact": True},
            (),
            (bounded,),
            (SemanticEffect("read", "MemoryRead", "execute", "arg0", "result", "program-order", ("input",), ("test.bounds",)),),
            (ProtocolTransition("borrow", "Lifetime", "published", "call", "retired", "call returns", ("test.bounds",)),),
        )
        payload = graph.to_dict()
        self.assertEqual(payload["schema_version"], "semantic-flow-v2")
        self.assertEqual(payload["effects"][0]["obligation_ids"], ("test.bounds",))
        self.assertEqual(payload["protocols"][0]["protocol"], "Lifetime")
        self.assertEqual(len(payload["graph_hash"]), 64)

    def test_unresolved_effect_reference_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "unresolved references"):
            SemanticFlowGraph(
                "invalid",
                "c",
                "clang-20",
                "llvm",
                "function-hash",
                (SemanticFlowNode("input", "Input", "load", (), "u8", {}, {}, ()),),
                (),
                {},
                (),
                effects=(SemanticEffect("read", "MemoryRead", "execute", "arg0", "result", "program-order", ("missing",)),),
            )

    def test_legacy_string_obligations_normalize_deterministically(self) -> None:
        def build() -> SemanticFlowGraph:
            return SemanticFlowGraph(
                "legacy",
                "rust",
                "rustc",
                "mir",
                "function-hash",
                (SemanticFlowNode("input", "Input", "borrow", (), "u8", {}, {}, ("borrow remains live",)),),
                (),
                {},
                (),
            )

        first = build()
        second = build()
        self.assertEqual(first.graph_hash, second.graph_hash)
        item = first.nodes[0].semantic_obligations[0]
        self.assertEqual(item.category, "ownership")
        self.assertEqual(item.proof_method, "compatibility-normalized")


if __name__ == "__main__":
    unittest.main()
