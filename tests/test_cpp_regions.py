from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from vladder import CPP_SUPPORT_VERSION, CppAuditRequest, CppRegionRequest, VelocityLadder
from vladder.cpp_regions import (
    inspect_cpp_matrix,
    inspect_cpp_region,
    isolate_cpp_region,
    load_compilation_command,
    optimize_cpp_region,
)
from vladder.cpp_semantics import analyze_ir_effects
from vladder.toolchain import discover_toolchain


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "examples" / "cpp_regions"
SUPPORTED = ("supported_pointer.cpp", "supported_span.cpp", "supported_vector.cpp", "supported_method.cpp", "supported_template.cpp")
ADAPTERS = {
    "adapter_external.cpp": "external-call-adapter",
    "adapter_atomic.cpp": "memory-order-adapter",
    "adapter_overload.cpp": "overload-selection-adapter",
}


def write_database(root: Path, files: tuple[str, ...] | None = None) -> Path:
    tc = discover_toolchain()
    selected = files or tuple(path.name for path in FIXTURES.glob("*.cpp"))
    entries = []
    for name in selected:
        source = (FIXTURES / name).resolve()
        entries.append({
            "directory": str(ROOT),
            "file": str(source),
            "arguments": [tc.compiler, "-std=c++20", "-Wall", "-Wextra", "-c", str(source), "-o", str(root / f"{source.stem}.o")],
        })
    path = root / "compile_commands.json"
    path.write_text(json.dumps(entries, indent=2) + "\n")
    return path


class CppRegionTests(unittest.TestCase):
    def test_transitive_nonlocal_helper_effects_are_not_lost(self):
        module = """
@state = global i32 0
define void @target(ptr %p) #0 {
entry:
  call void @helper(ptr %p)
  ret void
}
define void @helper(ptr %p) #0 {
entry:
  store i32 1, ptr @state
  ret void
}
attributes #0 = { nounwind nofree nosync }
"""
        effects = analyze_ir_effects(module, "target")
        self.assertFalse(effects["local_effects"])
        self.assertIn("helper", effects["external_calls"])

    def test_supported_matrix_emits_proved_adapter_and_regenerated_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = write_database(root)
            for name in SUPPORTED:
                with self.subTest(name=name):
                    out = root / name
                    report = inspect_cpp_region(FIXTURES / name, "transform", database, out)
                    self.assertEqual(report["status"], "supported")
                    self.assertEqual(report["support_version"], CPP_SUPPORT_VERSION)
                    self.assertEqual(report["proof_classification"], "kernel_isolated_adapter_proved")
                    self.assertEqual(report["verification"]["adapter"]["status"], "PROVED")
                    self.assertEqual(report["verification"]["regenerated_compile"]["status"], "pass")
                    self.assertTrue(Path(report["production_ir"]["normalized_ir"]).read_text().startswith("define "))
                    self.assertTrue(Path(report["artifacts"]["regenerated_cpp"]).exists())
                    self.assertTrue(Path(report["artifacts"]["provenance"]).exists())
                    self.assertTrue(report["kernel_support"]["supported"])

    def test_cpp_semantics_fail_closed_with_named_adapters(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = write_database(root)
            for name, expected in ADAPTERS.items():
                with self.subTest(name=name):
                    report = inspect_cpp_region(FIXTURES / name, "transform", database, root / name)
                    self.assertEqual(report["status"], "adapter_required")
                    self.assertIn(expected, [item["kind"] for item in report["adapters"]])
                    self.assertNotEqual(report["proof_classification"], "kernel_isolated_adapter_proved")
                    self.assertNotIn("regenerated_cpp", report["artifacts"])

    def test_effect_aware_regions_accept_broader_typed_boundaries(self):
        cases = {
            "accepted_byte_parser.cpp": ("parse_word", "whole_function_local_ir"),
            "accepted_inferred_nounwind.cpp": ("byte_checksum", "whole_function_local_ir"),
            "accepted_struct_view.cpp": ("weighted_total", "whole_function_local_ir"),
            "accepted_status_result.cpp": ("first_byte", "whole_function_local_ir"),
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = write_database(root, tuple(cases))
            for name, (function, tier) in cases.items():
                with self.subTest(name=name):
                    report = inspect_cpp_region(FIXTURES / name, function, database, root / name)
                    self.assertEqual(report["status"], "supported")
                    self.assertTrue(report["accepted"])
                    self.assertFalse(report["transformation_ready"])
                    self.assertEqual(report["support_tier"], tier)
                    self.assertTrue(report["typed_abi"]["modeled"])
                    self.assertTrue(report["compiled_effects"]["local_effects"])
                    self.assertNotIn("external-call-adapter", [item["kind"] for item in report["adapters"]])
                    self.assertNotIn("ownership-lifetime-adapter", [item["kind"] for item in report["adapters"]])
                    self.assertNotIn("exception-adapter", [item["kind"] for item in report["adapters"]])
                    if report["subregions"]:
                        self.assertNotIn("source-lowering-adapter", [item["kind"] for item in report["adapters"]])
                        self.assertTrue(report["closure"]["capabilities"]["candidate_generation"]["ready"])
                    else:
                        self.assertIn("source-lowering-adapter", [item["kind"] for item in report["adapters"]])
                    self.assertNotIn("regenerated_cpp", report["artifacts"])
                    self.assertEqual(len(report["information_flow"]["graph_sha256"]), 64)
                    self.assertEqual(report["information_flow"]["schema_version"], "semantic-flow-v2")
                    self.assertTrue(report["information_flow"]["effects"])
                    self.assertTrue(all("category" in item for item in report["information_flow"]["obligations"]))
                    self.assertTrue(Path(report["artifacts"]["information_flow"]).exists())
                    if name == "accepted_byte_parser.cpp":
                        self.assertEqual(report["helper_closure"]["disposition"]["read_be32"], "inlined_or_folded")

    def test_owning_and_throwing_wrappers_expose_only_local_subregions(self):
        cases = {
            "accepted_owning_subregion.cpp": ("copy_words", "ownership-lifetime-adapter"),
            "adapter_ownership.cpp": ("transform", "ownership-lifetime-adapter"),
            "adapter_exception.cpp": ("transform", "exception-adapter"),
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = write_database(root, tuple(cases))
            for name, (function, expected_adapter) in cases.items():
                with self.subTest(name=name):
                    report = inspect_cpp_region(FIXTURES / name, function, database, root / name)
                    self.assertEqual(report["status"], "supported")
                    self.assertEqual(report["support_tier"], "extractable_subregions")
                    self.assertFalse(report["transformation_ready"])
                    self.assertIn(expected_adapter, [item["kind"] for item in report["adapters"]])
                    self.assertTrue(any(item["extractable_candidate"] for item in report["subregions"]))

    def test_object_method_is_a_bounded_state_transition_not_a_local_equivalence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = write_database(root, ("accepted_state_transition.cpp",))
            first = inspect_cpp_region(
                FIXTURES / "accepted_state_transition.cpp", "add", database, root / "ambiguous"
            )
            symbol = first["candidate_symbols"][0]["symbol"]
            report = inspect_cpp_region(
                FIXTURES / "accepted_state_transition.cpp", "add", database, root / "selected", symbol=symbol
            )
            self.assertEqual(report["status"], "supported")
            self.assertEqual(report["support_tier"], "bounded_state_transition")
            self.assertFalse(report["transformation_ready"])
            self.assertIn("object-state-adapter", [item["kind"] for item in report["adapters"]])
            self.assertIn("declare and prove an explicit object-state projection and invariant", report["proof_envelope"]["required_before_source_rewrite"])

    def test_local_function_becomes_a_proved_identity_unit_but_has_no_invented_transform(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = write_database(root, ("accepted_byte_parser.cpp",))
            isolation = VelocityLadder().cpp_region(CppRegionRequest(
                FIXTURES / "accepted_byte_parser.cpp", "parse_word", database, root / "isolate", action="isolate"
            ))
            self.assertEqual(isolation.return_code, 0)
            self.assertEqual(isolation.report["operation_status"], "isolated")
            self.assertTrue(isolation.report["closure"]["capabilities"]["local_proof"]["actual"])
            self.assertFalse(isolation.report["closure"]["capabilities"]["candidate_generation"]["actual"])
            code, report = optimize_cpp_region(
                FIXTURES / "accepted_byte_parser.cpp", "parse_word", database, root / "out"
            )
            self.assertEqual(code, 2)
            self.assertEqual(report["status"], "no_admitted_transform")
            self.assertFalse((root / "out" / "kernel-optimization").exists())

    def test_owning_wrapper_isolates_and_synthesizes_a_local_loop_without_applying_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = write_database(root, ("accepted_owning_subregion.cpp",))
            code, report = isolate_cpp_region(
                FIXTURES / "accepted_owning_subregion.cpp", "copy_words", database, root / "isolate"
            )
            self.assertEqual(code, 0)
            closure = report["closure"]
            self.assertEqual(closure["disposition"], "local_regions_only")
            self.assertTrue(closure["capabilities"]["isolation"]["actual"])
            self.assertEqual(closure["capabilities"]["candidate_generation"]["count"], 2)
            self.assertFalse(closure["capabilities"]["benchmark"]["actual"])
            self.assertFalse(closure["source_changes_performed"])
            for candidate in closure["candidates"]:
                self.assertEqual(candidate["proof"]["status"], "SOURCE_CONTRACT_PROVED")
                self.assertEqual(candidate["proof"]["physical_candidate_alive2"]["status"], "NOT_RUN")
                self.assertEqual(candidate["repository_syntax"]["status"], "pass")
                self.assertEqual(candidate["benchmark"]["status"], "ADAPTER_REQUIRED")
                self.assertFalse(candidate["application_performed"])

    def test_local_return_loop_uses_whole_function_cfg_closure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = write_database(root, ("adapter_escaping_loop.cpp",))
            report = inspect_cpp_region(
                FIXTURES / "adapter_escaping_loop.cpp", "first_positive", database, root / "inspect"
            )
            self.assertTrue(report["closure"]["regions"][0]["eligible"])
            self.assertEqual(report["closure"]["regions"][0]["isolation_mode"], "whole_function_cfg")
            self.assertEqual(report["region_closure"]["classes"]["multi_exit"], "closed_as_tagged_cfg")
            self.assertEqual(report["region_closure_proof"]["status"], "PASS")
            self.assertFalse(report["closure"]["global_workflow_blocked"])

            code, isolated = isolate_cpp_region(
                FIXTURES / "adapter_escaping_loop.cpp", "first_positive", database, root / "isolate"
            )
            self.assertEqual(code, 0)
            cfg_candidates = [item for item in isolated["closure"]["candidates"] if "cfg-unroll" in item["id"]]
            self.assertEqual(len(cfg_candidates), 2)
            self.assertTrue(all(item["proof"]["status"] == "SOURCE_CONTRACT_PROVED" for item in cfg_candidates))

    def test_aggregate_helper_and_no_growth_ownership_close_as_typed_channels(self):
        cases = {
            "accepted_byte_parser.cpp": "parse_word",
            "accepted_no_growth_vector.cpp": "collect_changed",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = write_database(root, tuple(cases))
            parser = inspect_cpp_region(
                FIXTURES / "accepted_byte_parser.cpp", cases["accepted_byte_parser.cpp"], database, root / "parser"
            )
            self.assertEqual(
                [(item["name"], item["type"]) for item in parser["region_closure"]["aggregate_fields"]],
                [("ok", "bool"), ("value", "std::uint32_t")],
            )
            self.assertEqual(parser["region_closure"]["classes"]["helper_summary"], "closed_inlined_or_call_preserving")
            self.assertTrue(any(item["mode"] == "inlined_into_selected_ir" for item in parser["region_closure"]["helper_summaries"]))
            self.assertEqual(parser["region_closure_proof"]["status"], "PASS")

            no_growth = inspect_cpp_region(
                FIXTURES / "accepted_no_growth_vector.cpp", cases["accepted_no_growth_vector.cpp"], database, root / "no-growth"
            )
            region = no_growth["subregions"][0]
            self.assertEqual(region["closure_mode"], "no_growth_container")
            self.assertTrue(region["extractable_candidate"])
            self.assertEqual(no_growth["region_closure"]["classes"]["ownership"], "closed_no_growth_projection")
            statuses = {item["id"]: item["status"] for item in no_growth["region_closure_proof"]["obligations"]}
            self.assertEqual(statuses["no-growth-capacity"], "PASS")
            self.assertIn("ownership-lifetime-adapter", [item["kind"] for item in no_growth["adapters"]])

    def test_definition_visible_helper_summary_allows_call_preserving_loop_closure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = write_database(root, ("accepted_local_helper_loop.cpp",))
            report = inspect_cpp_region(
                FIXTURES / "accepted_local_helper_loop.cpp", "mix_total", database, root / "inspect"
            )
            self.assertEqual(report["status"], "supported")
            self.assertTrue(report["subregions"][0]["helper_summary_closure"]["closed"])
            self.assertNotIn("external_call", report["subregions"][0]["hard_hazards"])
            self.assertEqual(report["region_closure"]["classes"]["helper_summary"], "closed_inlined_or_call_preserving")
            self.assertTrue(any(item["mode"] == "exact_call_preserving" for item in report["region_closure"]["helper_summaries"]))
            binding = next(item for item in report["region_closure_proof"]["obligations"] if item["id"].startswith("helper-binding"))
            self.assertEqual(binding["status"], "PASS")

    def test_capacity_check_after_writes_does_not_close_ownership(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = write_database(root, ("adapter_late_capacity_guard.cpp",))
            report = inspect_cpp_region(
                FIXTURES / "adapter_late_capacity_guard.cpp", "collect_unchecked", database, root / "inspect"
            )
            region = report["subregions"][0]
            self.assertEqual(region["container_closure"]["mode"], "unclosed")
            self.assertFalse(region["container_closure"]["guard_dominates_region"])
            self.assertIn("capacity_mutation", region["hard_hazards"])
            self.assertEqual(report["region_closure"]["classes"]["ownership"], "requires_adapter")

    def test_nontrivial_elements_do_not_enter_no_growth_projection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = write_database(root, ("adapter_nontrivial_no_growth.cpp",))
            report = inspect_cpp_region(
                FIXTURES / "adapter_nontrivial_no_growth.cpp", "copy_names", database, root / "inspect"
            )
            region = report["subregions"][0]
            self.assertTrue(region["container_closure"]["guard_dominates_region"])
            self.assertFalse(region["container_closure"]["trivial_element"])
            self.assertEqual(region["container_closure"]["mode"], "unclosed")
            self.assertIn("capacity_mutation", region["hard_hazards"])

    def test_large_aggregate_result_binds_sret_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = write_database(root, ("accepted_large_result.cpp",))
            report = inspect_cpp_region(
                FIXTURES / "accepted_large_result.cpp", "widen_result", database, root / "inspect"
            )
            self.assertTrue(report["typed_abi"]["lowered_sret"])
            self.assertEqual(
                [item["name"] for item in report["region_closure"]["aggregate_fields"]],
                ["first", "second", "third", "fourth"],
            )
            self.assertTrue(all(item["channel"] == "sret-memory" for item in report["region_closure"]["aggregate_fields"]))
            self.assertEqual(report["region_closure_proof"]["status"], "PASS")

    def test_external_protocol_scope_does_not_hide_other_vladder_workflows(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = write_database(root, ("adapter_protocol.cpp",))
            report = inspect_cpp_region(
                FIXTURES / "adapter_protocol.cpp", "send_packet", database, root / "inspect"
            )
            closure = report["closure"]
            self.assertEqual(closure["disposition"], "external_protocol_only")
            self.assertFalse(closure["global_workflow_blocked"])
            external = next(
                item for item in closure["protocol_scopes"] if item["category"] == "external_api_or_callback"
            )
            self.assertTrue(external["categorical_for_generic_ingestion"])
            self.assertIn("independently isolated local regions", external["does_not_block"])
            self.assertTrue(any(effect["kind"] == "ExternalCall" for effect in report["information_flow"]["effects"]))

    def test_callback_loop_is_not_misclassified_as_a_closed_local_capsule(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = write_database(root, ("adapter_callback_loop.cpp",))
            report = inspect_cpp_region(
                FIXTURES / "adapter_callback_loop.cpp", "visit_values", database, root / "inspect"
            )
            region = report["closure"]["regions"][0]
            self.assertFalse(region["eligible"])
            self.assertIn("external_call", region["blockers"])
            detail = next(item for item in region["blocker_details"] if item["kind"] == "external_call")
            self.assertFalse(detail["whole_function_blocked"])
            self.assertIn("other independently closed subregions", detail["permitted_continuation"])

    def test_overload_can_be_selected_by_mangled_symbol(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = write_database(root, ("adapter_overload.cpp",))
            first = inspect_cpp_region(FIXTURES / "adapter_overload.cpp", "transform", database, root / "ambiguous")
            pointer_symbol = next(item["symbol"] for item in first["candidate_symbols"] if "PfPKf" in item["symbol"])
            selected = inspect_cpp_region(
                FIXTURES / "adapter_overload.cpp", "transform", database, root / "selected", symbol=pointer_symbol
            )
            self.assertEqual(selected["status"], "supported")
            self.assertEqual(selected["selection"]["symbol"], pointer_symbol)
            self.assertEqual(selected["abi_class"], "pointer-view")

    def test_ambiguous_compile_commands_require_an_index(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = write_database(root, ("supported_span.cpp",))
            entries = json.loads(database.read_text())
            duplicate = dict(entries[0])
            duplicate["arguments"] = [*duplicate["arguments"][:-2], "-DSECOND_CONFIGURATION=1", *duplicate["arguments"][-2:]]
            database.write_text(json.dumps([entries[0], duplicate]))
            report = inspect_cpp_region(FIXTURES / "supported_span.cpp", "transform", database, root / "ambiguous")
            self.assertEqual(report["adapters"][0]["kind"], "compile-command-selection-adapter")
            selected = load_compilation_command(FIXTURES / "supported_span.cpp", database, command_index=1)
            self.assertIn("-DSECOND_CONFIGURATION=1", selected.semantic_arguments)

    def test_regenerated_span_executes_with_original_results(self):
        tc = discover_toolchain()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = write_database(root, ("supported_span.cpp",))
            report = inspect_cpp_region(FIXTURES / "supported_span.cpp", "transform", database, root / "out")
            generated = Path(report["artifacts"]["regenerated_cpp"])
            driver = root / "driver.cpp"
            driver.write_text(
                "#include <bit>\n#include <cstdint>\n#include <cstdio>\n#include <span>\n"
                "void transform(std::span<float>, std::span<const float>) noexcept;\n"
                "int main(){ float src[8]={-2,-1,0,1,2,3,4,5}; float dst[8]={}; "
                "transform(dst,src); std::uint64_t h=1469598103934665603ull; "
                "for(float x:dst){h^=std::bit_cast<std::uint32_t>(x);h*=1099511628211ull;} "
                "std::printf(\"%llu\\n\",(unsigned long long)h);}\n"
            )
            outputs = []
            for index, source in enumerate((FIXTURES / "supported_span.cpp", generated)):
                binary = root / f"run-{index}"
                compiled = subprocess.run(
                    [tc.compiler, "-std=c++20", "-O3", str(source), str(driver), "-o", str(binary)],
                    text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                )
                self.assertEqual(compiled.returncode, 0, compiled.stderr)
                outputs.append(subprocess.check_output([str(binary)], text=True).strip())
            self.assertEqual(outputs[0], outputs[1])

    def test_library_api_isolates_cpp(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = write_database(root, ("supported_pointer.cpp",))
            request = CppRegionRequest(
                FIXTURES / "supported_pointer.cpp", "transform", database, root / "api", action="isolate"
            )
            result = VelocityLadder().cpp_region(request)
            self.assertEqual(result.return_code, 0)
            self.assertEqual(result.report["status"], "supported")

    def test_cpp_audit_manifest_aggregates_without_optimization(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = write_database(root, ("accepted_byte_parser.cpp", "adapter_protocol.cpp"))
            manifest = root / "audit.yaml"
            manifest.write_text(
                "compile_commands: " + str(database) + "\nregions:\n"
                "  - id: parser\n    source: " + str(FIXTURES / "accepted_byte_parser.cpp") + "\n    function: parse_word\n"
                "  - id: protocol\n    source: " + str(FIXTURES / "adapter_protocol.cpp") + "\n    function: send_packet\n"
            )
            report = inspect_cpp_matrix(manifest, root / "audit")
            self.assertEqual(report["region_count"], 2)
            self.assertEqual(report["accepted_count"], 1)
            self.assertEqual(report["transformation_ready_count"], 0)
            self.assertFalse(report["optimization_performed"])
            self.assertFalse(report["source_changes_performed"])
            self.assertFalse(report["isolation_materialized"])
            request = CppAuditRequest(manifest, root / "api-audit")
            api = VelocityLadder().cpp_audit(request)
            self.assertEqual(api.return_code, 0)
            self.assertEqual(api.report["region_count"], 2)

    def test_cpp_audit_can_materialize_proof_units_without_source_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = write_database(root, ("accepted_byte_parser.cpp", "accepted_owning_subregion.cpp"))
            manifest = root / "audit.yaml"
            manifest.write_text(
                "compile_commands: " + str(database) + "\nregions:\n"
                "  - id: parser\n    source: " + str(FIXTURES / "accepted_byte_parser.cpp") + "\n    function: parse_word\n"
                "  - id: owning\n    source: " + str(FIXTURES / "accepted_owning_subregion.cpp") + "\n    function: copy_words\n"
            )
            report = inspect_cpp_matrix(manifest, root / "audit", materialize_isolation=True)
            self.assertTrue(report["isolation_materialized"])
            self.assertFalse(report["source_changes_performed"])
            capabilities = report["closure_capabilities"]["actual_capabilities"]
            self.assertEqual(capabilities["isolation"], 2)
            self.assertEqual(capabilities["local_proof"], 2)
            self.assertEqual(capabilities["candidate_generation"], 1)


if __name__ == "__main__":
    unittest.main()
