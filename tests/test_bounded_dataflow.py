from __future__ import annotations

from dataclasses import replace
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from vladder.dataflow_audit import _selected_source, classify_cpp_dataflow
from vladder.dataflow_grammar import load_bounded_dataflow_grammar
from vladder.dataflow_ir import BoundedDataflowContract, DATAFLOW_FAMILIES, build_bounded_dataflow_graph
from vladder.dataflow_lowering import emit_dataflow_cpp, run_dataflow_differential
from vladder.dataflow_multilang import emit_dataflow_native, run_native_dataflow_differential
from vladder.dataflow_proof import prove_dataflow_candidate
from vladder.cli import main


class BoundedDataflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.grammar = load_bounded_dataflow_grammar()

    def test_grammar_has_complete_executable_coverage(self) -> None:
        coverage = self.grammar.coverage()
        self.assertEqual(coverage["status"], "pass")
        self.assertEqual(coverage["family_count"], 5)
        self.assertEqual(coverage["terminal_count"], 17)
        self.assertEqual(set(self.grammar.sources), DATAFLOW_FAMILIES)
        for family in coverage["families"]:
            classes = family["native_lowering_classes"]
            self.assertEqual(set(classes), {"c", "cpp", "rust", "zig", "julia"})
            self.assertEqual(set(classes["cpp"].values()), {"native_physical"})
            for language in ("c", "rust", "zig", "julia"):
                for terminal, lowering_class in classes[language].items():
                    expected = (
                        "native_semantic"
                        if self.grammar.terminals[terminal]["isa"] == "scalar"
                        else "semantic_scalar_fallback"
                    )
                    self.assertEqual(lowering_class, expected)
        for family in DATAFLOW_FAMILIES:
            contract = BoundedDataflowContract(family=family)
            for derivation in self.grammar.search(contract):
                candidate = emit_dataflow_cpp(contract, derivation)
                self.assertIn('extern "C"', candidate.source)
                self.assertEqual(candidate.derivation_hash, derivation.derivation_hash)
                self.assertNotEqual(candidate.graph_hash, derivation.target_graph_hash)

    def test_graphs_are_deterministic_and_protocol_typed(self) -> None:
        for family in DATAFLOW_FAMILIES:
            contract = BoundedDataflowContract(family=family)
            target = self.grammar.family_terminals(family)[0]
            first = build_bounded_dataflow_graph(contract, target)
            second = build_bounded_dataflow_graph(contract, target)
            self.assertEqual(first.graph_hash, second.graph_hash)
            self.assertEqual(first.semantic_graph.semantic_ir, "bounded-dataflow-v1")
        state = build_bounded_dataflow_graph(
            BoundedDataflowContract(family="stateful-delta-transducer"),
            "transactional-delta",
        ).semantic_graph
        self.assertEqual({item.id for item in state.protocols}, {"delta.commit", "delta.rollback"})
        self.assertEqual({item.id for item in state.effects}, {"dataflow.output.write", "dataflow.state.publish"})

    def test_every_terminal_compiles_and_matches_differential_oracle(self) -> None:
        with tempfile.TemporaryDirectory(prefix="vladder-dataflow-tests-") as temporary:
            root = Path(temporary)
            for family in sorted(DATAFLOW_FAMILIES):
                contract = BoundedDataflowContract(family=family, max_elements=64)
                for derivation in self.grammar.search(contract):
                    with self.subTest(family=family, target=derivation.target):
                        candidate = emit_dataflow_cpp(contract, derivation)
                        report = run_dataflow_differential(contract, candidate, root / family / derivation.target)
                        self.assertEqual(report["status"], "PASS", report)

    def test_shared_grammar_emits_every_native_language(self) -> None:
        with tempfile.TemporaryDirectory(prefix="vladder-dataflow-native-") as temporary:
            root = Path(temporary)
            for language in ("c", "rust", "zig", "julia"):
                if language == "zig" and not shutil.which("zig"):
                    continue
                if language == "julia" and not shutil.which("julia"):
                    continue
                for family in sorted(DATAFLOW_FAMILIES):
                    contract = BoundedDataflowContract(family=family, max_elements=64)
                    for derivation in self.grammar.search(contract):
                        with self.subTest(language=language, family=family, target=derivation.target):
                            candidate = emit_dataflow_native(contract, derivation, language)
                            self.assertEqual(candidate.derivation_hash, derivation.derivation_hash)
                            report = run_native_dataflow_differential(
                                contract, candidate, root / language / family / derivation.target,
                            )
                            self.assertEqual(report["status"], "PASS", report)

    def test_output_modes_and_capacity_policies_are_executable(self) -> None:
        with tempfile.TemporaryDirectory(prefix="vladder-compaction-contracts-") as temporary:
            for output_mode in ("index-only", "value-only", "index-value"):
                for capacity_policy in ("fail-unchanged", "truncate"):
                    contract = BoundedDataflowContract(
                        family="predicate-stable-compaction",
                        output_mode=output_mode,
                        capacity_policy=capacity_policy,
                    )
                    derivation = self.grammar.derive(contract, "guarded-avx512-compress")
                    candidate = emit_dataflow_cpp(contract, derivation)
                    report = run_dataflow_differential(
                        contract,
                        candidate,
                        Path(temporary) / output_mode / capacity_policy,
                    )
                    self.assertEqual(report["status"], "PASS", report)

    def test_runtime_sized_u32_compaction_closes_exact_preflight_and_alias_dispatch(self) -> None:
        contract = BoundedDataflowContract(
            family="predicate-stable-compaction",
            max_elements=None,
            element_bits=32,
            output_mode="index-only",
            capacity_policy="fail-input-extent-unchanged",
            aliasing="runtime-guarded-disjoint",
        )
        with tempfile.TemporaryDirectory(prefix="vladder-runtime-compaction-") as temporary:
            for derivation in self.grammar.search(contract):
                with self.subTest(target=derivation.target):
                    candidate = emit_dataflow_cpp(contract, derivation)
                    self.assertIn("std::uint32_t* current", candidate.source)
                    self.assertIn("ordered_fallback", candidate.source)
                    report = prove_dataflow_candidate(
                        contract,
                        derivation,
                        candidate,
                        Path(temporary) / derivation.target,
                    )
                    self.assertEqual(report["status"], "PASS", report)
                    obligations = {item["id"] for item in report["obligations"]}
                    self.assertIn("runtime-extent-block-induction", obligations)
                    self.assertIn("alias-dispatch-completeness", obligations)

    def test_proof_binds_source_graph_and_state_obligations(self) -> None:
        contract = BoundedDataflowContract(family="stateful-delta-transducer", max_elements=64)
        derivation = self.grammar.derive(contract, "mask-transactional-delta")
        candidate = emit_dataflow_cpp(contract, derivation)
        with tempfile.TemporaryDirectory(prefix="vladder-dataflow-proof-") as temporary:
            report = prove_dataflow_candidate(contract, derivation, candidate, Path(temporary))
            self.assertEqual(report["status"], "PASS", report)
            statuses = {item["id"]: item["status"] for item in report["obligations"]}
            self.assertEqual(statuses["delta-reconstruction"], "PASS")
            self.assertEqual(statuses["commit-rollback-atomicity"], "PASS")
            self.assertEqual(statuses["stable-delta-sequence"], "PASS")
            self.assertEqual(report["alive2"]["status"], "not_applicable")

            tampered = replace(candidate, source=candidate.source + "\n// changed after derivation\n")
            rejected = prove_dataflow_candidate(
                contract,
                derivation,
                tampered,
                Path(temporary) / "tampered",
                run_differential=False,
            )
            self.assertEqual(rejected["status"], "FAIL")
            self.assertEqual(rejected["obligations"][0]["id"], "native-source-binding")
            self.assertEqual(rejected["obligations"][0]["status"], "FAIL")

    def test_cpp_container_closure_is_explicit_and_fails_closed(self) -> None:
        reserve_only = classify_cpp_dataflow(
            "void f(std::vector<uint32_t>& out) noexcept { out.reserve(64); out.push_back(1); }",
            "f",
        )
        self.assertEqual(reserve_only["container_closure"]["status"], "bounded_container_contract_required")
        self.assertTrue(reserve_only["container_closure"]["reserve_without_capacity_proof"])

        checked = classify_cpp_dataflow(
            "void f(std::vector<uint32_t>& changed) noexcept { "
            "if (changed.capacity() - changed.size() >= 64) changed.push_back(uint32_t{1}); }",
            "f",
        )
        self.assertEqual(checked["container_closure"]["status"], "no_growth_container_closure_candidate")
        self.assertEqual(checked["families"][0]["family"], "predicate-stable-compaction")
        self.assertIn("whole application equivalence", checked["claim_boundary"])

    def test_unresolved_cpp_selection_does_not_scan_whole_translation_unit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "unit.cpp"
            source.write_text("void unrelated() { changed.push_back(1); }\n")
            self.assertEqual(_selected_source({"status": "adapter_required"}, source), "")

    def test_codec_field_boundary_rejects_unexecutable_shapes(self) -> None:
        with self.assertRaisesRegex(ValueError, "u16/u16/u32"):
            BoundedDataflowContract(family="fixed-width-codec", field_widths=(17, 15, 32))

    def test_graph_cli_returns_success_with_machine_status(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            contract = Path(temporary) / "contract.json"
            contract.write_text(json.dumps({"family": "predicate-stable-compaction"}))
            output = io.StringIO()
            with redirect_stdout(output):
                status = main([
                    "dataflow", "graph", "--contract", str(contract),
                    "--target", "mask-prefix-stable",
                ])
            self.assertEqual(status, 0)
            self.assertEqual(json.loads(output.getvalue())["status"], "pass")

    def test_block_quality_proof_classes_never_collapse(self) -> None:
        expected = {
            "exact-encoded": "exact_encoded_identity",
            "exact-decoded": "exact_decoded_identity",
            "bounded-quality": "bounded_quality_only",
        }
        with tempfile.TemporaryDirectory(prefix="vladder-block-proof-class-") as temporary:
            for quality, classification in expected.items():
                contract = BoundedDataflowContract(family="quantized-block-4x4", quality_class=quality)
                derivation = self.grammar.derive(contract, "fused-4x4-block")
                candidate = emit_dataflow_cpp(contract, derivation)
                report = prove_dataflow_candidate(
                    contract,
                    derivation,
                    candidate,
                    Path(temporary) / quality,
                    run_differential=False,
                )
                self.assertEqual(report["status"], "PASS")
                self.assertEqual(report["proof_classification"], classification)


if __name__ == "__main__":
    unittest.main()
