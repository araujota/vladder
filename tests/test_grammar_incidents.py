from __future__ import annotations

import unittest
from pathlib import Path
import json
import tempfile
import yaml

from vladder.artifact_identity import bounded_artifact_name
from vladder.gpu_ir import _graph_from_spirv
from vladder.spirv_semantics import analyze_spirv_semantics, parse_spirv_instructions
from vladder.resource_protocol import protocol_template, verify_resource_protocol
from vladder.structured_dataflow import classify_structured_dataflow
from vladder.cpp_semantics import analyze_ir_effects


class ArtifactIdentityTests(unittest.TestCase):
    def test_long_identity_is_bounded_stable_and_collision_resistant(self) -> None:
        identity = "_ZN" + "VeryLongTemplateSpecialization" * 40
        first = bounded_artifact_name("summary-join", identity, ".smt2")
        second = bounded_artifact_name("summary-join", identity, ".smt2")
        different = bounded_artifact_name("summary-join", identity + "x", ".smt2")
        self.assertEqual(first, second)
        self.assertNotEqual(first, different)
        self.assertLessEqual(len(first.encode()), 180)


class SpirvSemanticTests(unittest.TestCase):
    MODULE = r'''
               OpCapability Shader
               OpCapability CooperativeMatrixKHR
               OpMemoryModel Logical GLSL450
               OpEntryPoint GLCompute %main "main"
               OpName %named "OpacityMap"
       %bool = OpTypeBool
        %u32 = OpTypeInt 32 0
        %f32 = OpTypeFloat 32
         %v4 = OpTypeVector %f32 4
         %m4 = OpTypeMatrix %v4 4
       %zero = OpConstant %u32 0
        %one = OpConstant %u32 1
          %a = OpLogicalNot %bool %b
          %c = OpLogicalAnd %bool %a %b
          %q = OpUDiv %u32 %x %one
          %r = OpUMod %u32 %x %d
        %dot = OpDot %f32 %left %right
         %mv = OpMatrixTimesVector %v4 %matrix %vector
       %coop = OpCooperativeMatrixMulAddKHR %m4 %ma %mb %mc
       %main = OpFunction %void None %fn
               OpReturn
               OpFunctionEnd
    '''

    def test_instruction_parser_does_not_treat_debug_names_as_opcodes(self) -> None:
        opcodes = [item.opcode for item in parse_spirv_instructions(self.MODULE)]
        self.assertNotIn("OpacityMap", opcodes)
        self.assertIn("OpLogicalNot", opcodes)

    def test_incident_operations_have_typed_semantics_and_validity_domains(self) -> None:
        report = analyze_spirv_semantics(self.MODULE)
        self.assertEqual(
            set(report["operation_families"]),
            {"cooperative-matrix", "logical", "matrix", "unsigned-quotient-remainder", "vector-dot"},
        )
        divisor = [
            item for item in report["obligations"] if item["kind"] == "validity-domain"
        ]
        self.assertEqual([item["status"] for item in divisor], ["PASS", "CONTRACT_REQUIRED"])

    def test_gpu_capture_maps_incident_operations(self) -> None:
        capture = _graph_from_spirv(
            self.MODULE,
            source="fixture.spvasm",
            module_hash="fixture",
            entry_point="main",
            compiler_identity="fixture",
        )
        self.assertEqual(capture.status, "captured")
        self.assertFalse(capture.unsupported_operations)
        facts = capture.graph.contracts["dialect_facts"]
        self.assertGreater(facts["typed_operation_count"], 0)
        self.assertTrue(facts["semantic_obligations"])


class CppIncidentClosureTests(unittest.TestCase):
    def test_recursive_effect_summary_terminates_without_becoming_external_io(self) -> None:
        module = r'''
define i32 @left(i32 %n) #0 {
entry:
  %stop = icmp eq i32 %n, 0
  br i1 %stop, label %done, label %next
next:
  %m = sub i32 %n, 1
  %v = call i32 @right(i32 %m)
  ret i32 %v
done:
  ret i32 0
}
define i32 @right(i32 %n) #0 {
entry:
  %v = call i32 @left(i32 %n)
  ret i32 %v
}
attributes #0 = { nounwind nofree nosync memory(none) }
'''
        effects = analyze_ir_effects(module, "left")
        self.assertFalse(effects["external_calls"])
        self.assertIn("right", effects["internal_call_summaries"])


class ResourceProtocolTests(unittest.TestCase):
    def test_standard_templates_are_finite_and_proved(self) -> None:
        for kind in ("publication", "queue", "socket", "device"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                manifest = root / "protocol.yaml"
                manifest.write_text(yaml.safe_dump(protocol_template(kind), sort_keys=False))
                report = verify_resource_protocol(manifest, root / "proof")
                self.assertEqual(report["status"], "PASS")

    def test_non_atomic_publication_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = protocol_template("publication")
            payload["transitions"][0]["atomic"] = False
            manifest = root / "protocol.yaml"
            manifest.write_text(yaml.safe_dump(payload, sort_keys=False))
            report = verify_resource_protocol(manifest, root / "proof")
            self.assertEqual(report["status"], "FAIL")
            failed = {item["id"] for item in report["obligations"] if item["status"] == "FAIL"}
            self.assertIn("protocol.publication-atomic", failed)


class StructuredDataflowTests(unittest.TestCase):
    def test_structured_owner_is_recognized_but_not_falsely_executable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "cpp-information-flow.json"
            artifact.write_text(json.dumps({
                "name": "apply_changes",
                "nodes": [
                    {"kind": "Call", "operation": "call", "attributes": {"callee": "stable_partition"}},
                    {"kind": "Call", "operation": "call", "attributes": {"callee": "emplace_back"}},
                ],
                "contracts": {"object_state": True},
            }))
            (root / "compiled-effects.json").write_text(json.dumps({
                "instruction_counts": {"branches": 4, "loads": 8, "stores": 4},
                "allocation_calls": ["allocate"], "external_calls": ["driver"],
            }))
            report = classify_structured_dataflow(artifact)
            ids = {item["id"] for item in report["archetypes"]}
            self.assertIn("stable-partition-prefix-scatter", ids)
            self.assertIn("realization-lifetime", ids)
            self.assertEqual(report["candidate_generation_eligibility"], "agent_realization_required")


if __name__ == "__main__":
    unittest.main()
