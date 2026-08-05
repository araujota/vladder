from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from vladder.deep_audit import audit_expert_manifest, extract_named_source_region
from vladder.deep_benchmark import compile_deep_harness
from vladder.deep_grammar import DeepGrammar, load_deep_grammar, search_deep_grammar
from vladder.deep_ir import DeepKernelContract, build_deep_realization_graph, inspect_source_realization
from vladder.deep_lowering import emit_deep_candidate
from vladder.deep_proof import prove_deep_candidate, prove_vector_byte_accumulate_alive2


ROOT = Path(__file__).resolve().parents[1]


class DeepGrammarTests(unittest.TestCase):
    def test_rust_shift_predicate_normalizes_to_shared_utf8_semantics(self) -> None:
        source = "pub fn count(values: &[u8]) -> usize { values.iter().filter(|&&byte| (byte >> 6) != 0b10).count() }"
        realization = inspect_source_realization(source, "rust", "count")
        self.assertTrue(realization.representable)
        self.assertEqual(realization.predicate, "utf8-leading-byte")
        self.assertEqual(realization.realization, "scalar")

    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = DeepKernelContract("exact-byte-predicate-reduction", "equal-u8")
        cls.grammar = load_deep_grammar()
        cls.search = search_deep_grammar(cls.contract, cls.grammar)
        cls.derivations = {item.target: item for item in cls.search.derivations}

    def test_shared_graph_vocabulary_is_language_neutral(self) -> None:
        graphs = {
            language: build_deep_realization_graph(self.contract, "simd-mask-popcount", source_language=language)
            for language in ("c", "cpp", "rust", "zig", "julia")
        }
        self.assertEqual({graph.semantic_shape_hash for graph in graphs.values()}, {graphs["c"].semantic_shape_hash})
        c_graph = graphs["c"]
        kinds = {node.kind for node in c_graph.semantic_graph.nodes}
        self.assertTrue({"LaneMap", "Pack", "MaskExtract", "PopulationCount", "HorizontalReduce", "Tail", "Fuse", "ComplexityBound"} <= kinds)
        self.assertEqual(c_graph.semantic_graph.to_dict()["schema_version"], "semantic-flow-v2")
        self.assertEqual(len({graph.semantic_graph.graph_hash for graph in graphs.values()}), 5)

    def test_all_high_value_families_participate_in_reachable_realizations(self) -> None:
        observed = {rule.family for derivation in self.search.derivations for rule in derivation.rules}
        self.assertEqual(observed, {
            "lane-decomposition", "lane-mask-population", "bitvector-algebra",
            "reduction-topology", "alignment-tail", "load-traversal",
            "table-constant-synthesis", "fusion-materialization",
            "algorithmic-representation", "isa-dispatch",
        })
        coverage = self.grammar.coverage()
        self.assertEqual(coverage["status"], "pass")
        self.assertEqual(coverage["family_count"], 10)
        self.assertGreaterEqual(coverage["rule_count"], 27)
        for terminal in coverage["terminal_realizations"].values():
            self.assertIn("native_emitter", terminal)
            self.assertIn("proof_generator", terminal)
            self.assertIn("benchmark_binding", terminal)

    def test_missing_rule_is_classified_as_grammar_failure_condition(self) -> None:
        payload = json.loads((ROOT / "vladder/grammars/deep-v2/grammar.json").read_text())
        payload["families"][0]["rules"] = [item for item in payload["families"][0]["rules"] if item["id"] != "scalar-to-word"]
        grammar = DeepGrammar(payload, "seeded-missing-rule")
        result = search_deep_grammar(self.contract, grammar, targets=("word-swar",))
        self.assertEqual(result.derivations, ())

    def test_word_proof_and_zero_trust_source_binding(self) -> None:
        derivation = self.derivations["word-swar"]
        with tempfile.TemporaryDirectory() as directory:
            candidate = emit_deep_candidate(self.contract, derivation, "rust", "deep_candidate", self.grammar)
            proof = prove_deep_candidate(self.contract, derivation, candidate, Path(directory), require_alive2_for_vector_mask=False)
            self.assertEqual(proof["status"], "PASS")
            broken_source = candidate.source.replace("i += 8;", "i += 16;")
            broken = replace(candidate, source=broken_source, source_sha256=hashlib.sha256(broken_source.encode()).hexdigest())
            broken_proof = prove_deep_candidate(self.contract, derivation, broken, Path(directory) / "broken", require_alive2_for_vector_mask=False)
            self.assertEqual(broken_proof["status"], "FAIL")
            self.assertEqual(broken_proof["obligations"][0]["id"], "native-source-binding")
            self.assertEqual(broken_proof["obligations"][0]["status"], "FAIL")

    @unittest.skipUnless(shutil.which("alive-tv"), "Alive2 is optional in generic CI and mandatory for strict promotion")
    def test_byte_accumulator_core_has_alive2_refinement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            proof = prove_vector_byte_accumulate_alive2(Path(directory))
        self.assertEqual(proof.status, "PASS")

    def test_native_candidates_compile_and_differentially_execute_in_all_languages(self) -> None:
        derivation = self.derivations["simd-mask-popcount"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tools = {
                "c": shutil.which("clang-20") or shutil.which("clang"),
                "cpp": shutil.which("clang++-20") or shutil.which("clang++"),
                "rust": shutil.which("rustc"),
                "zig": shutil.which("zig"),
                "julia": shutil.which("julia"),
            }
            for language in ("c", "cpp", "rust", "zig", "julia"):
                if not tools[language]:
                    continue
                candidate = emit_deep_candidate(self.contract, derivation, language, "deep_candidate", self.grammar)
                self.assertTrue(candidate.language_obligations)
                self.assertTrue(all(item.proof_method for item in candidate.language_obligations))
                build = compile_deep_harness(self.contract, candidate, root / language)
                self.assertEqual(build["status"], "pass", build.get("stderr"))
                completed = subprocess.run([str(build["binary"]), "candidate", "4096", "2"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                self.assertEqual(completed.returncode, 0, completed.stderr)
                payload = json.loads(completed.stdout.splitlines()[-1])
                self.assertIn("observable", payload)

    @unittest.skipUnless(shutil.which("zig") and shutil.which("julia") and (shutil.which("clang++-20") or shutil.which("clang++")), "new native emitter toolchains are optional in generic CI")
    def test_cpp_zig_and_julia_emit_every_terminal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for language in ("cpp", "zig", "julia"):
                for realization, derivation in self.derivations.items():
                    with self.subTest(language=language, realization=realization):
                        candidate = emit_deep_candidate(self.contract, derivation, language, "deep_candidate", self.grammar)
                        proof = prove_deep_candidate(
                            self.contract,
                            derivation,
                            candidate,
                            root / "proof" / language / realization,
                            require_alive2_for_vector_mask=False,
                        )
                        self.assertEqual(proof["status"], "PASS", proof["obligations"])
                        build = compile_deep_harness(self.contract, candidate, root / "build" / language / realization)
                        self.assertEqual(build["status"], "pass", build.get("stderr"))

    @unittest.skipUnless(shutil.which("alive-tv"), "expert vector proof audit requires Alive2")
    def test_expert_audit_closes_all_five_stages_without_benchmark(self) -> None:
        manifest = ROOT / "examples/deep_grammar/expert-audit.yaml"
        with tempfile.TemporaryDirectory() as directory:
            report = audit_expert_manifest(manifest, Path(directory), run_benchmarks=False)
            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["case_count"], 5)
            self.assertEqual(report["classifications"], {"proof_complete_measurement_not_run": 5})

    def test_source_classifier_fails_closed_on_unrelated_code(self) -> None:
        result = inspect_source_realization("pub fn owner() -> Vec<String> { Vec::new() }", "rust", "owner")
        self.assertFalse(result.representable)
        self.assertTrue(result.blockers)
        source = (ROOT / "examples/deep_grammar/rust_byte_kernels.rs").read_text()
        extracted = extract_named_source_region(source, "rust_word_count", "rust")
        self.assertIn("bytewise_equal", extracted)


if __name__ == "__main__":
    unittest.main()
