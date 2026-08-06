from __future__ import annotations

from dataclasses import dataclass
import json
import re
from pathlib import Path
from typing import Any, Iterable

from z3 import BoolVal, Solver, unsat


SPIRV_SEMANTIC_SCHEMA = "vladder-spirv-semantics-v2"


@dataclass(frozen=True)
class SpirvInstruction:
    ordinal: int
    result_id: str | None
    opcode: str
    operands: tuple[str, ...]
    source_line: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "ordinal": self.ordinal,
            "result_id": self.result_id,
            "opcode": self.opcode,
            "operands": list(self.operands),
            "source_line": self.source_line,
        }


_INSTRUCTION = re.compile(
    r"^\s*(?:(%[^\s=]+)\s*=\s*)?(Op[A-Za-z0-9_]+)\b(?:\s+(.*?))?\s*$"
)


def parse_spirv_instructions(text: str) -> tuple[SpirvInstruction, ...]:
    instructions: list[SpirvInstruction] = []
    for line_number, raw in enumerate(text.splitlines(), 1):
        line = raw.split(";", 1)[0].rstrip()
        match = _INSTRUCTION.match(line)
        if not match:
            continue
        result_id, opcode, operand_text = match.groups()
        operands = tuple(_tokenize(operand_text or ""))
        instructions.append(
            SpirvInstruction(len(instructions), result_id, opcode, operands, line_number)
        )
    return tuple(instructions)


def analyze_spirv_semantics(text: str) -> dict[str, Any]:
    instructions = parse_spirv_instructions(text)
    types = _type_table(instructions)
    constants = _constant_table(instructions)
    capabilities = sorted(
        instruction.operands[0]
        for instruction in instructions
        if instruction.opcode == "OpCapability" and instruction.operands
    )
    operations: list[dict[str, Any]] = []
    obligations: list[dict[str, Any]] = []
    family_counts: dict[str, int] = {}
    for instruction in instructions:
        descriptor = _operation_descriptor(instruction, types, constants, capabilities)
        if descriptor is None:
            continue
        operation_obligations = list(descriptor.pop("obligations"))
        descriptor["eligibility"] = (
            "exact_local_candidate"
            if all(item["status"] == "PASS" for item in operation_obligations)
            else "contract_gated_candidate"
            if all(item["status"] != "FAIL" for item in operation_obligations)
            else "invalid_module_operation"
        )
        descriptor["obligation_ids"] = [item["id"] for item in operation_obligations]
        operations.append(descriptor)
        family = str(descriptor["family"])
        family_counts[family] = family_counts.get(family, 0) + 1
        obligations.extend(operation_obligations)
    eligibility_counts: dict[str, int] = {}
    for item in operations:
        key = str(item["eligibility"])
        eligibility_counts[key] = eligibility_counts.get(key, 0) + 1
    return {
        "schema_version": SPIRV_SEMANTIC_SCHEMA,
        "instruction_count": len(instructions),
        "type_count": len(types),
        "capabilities": capabilities,
        "operation_families": dict(sorted(family_counts.items())),
        "operations": operations,
        "obligations": obligations,
        "eligibility": dict(sorted(eligibility_counts.items())),
        "unresolved_obligation_count": sum(
            item["status"] == "CONTRACT_REQUIRED" for item in obligations
        ),
        "proof_boundary": (
            "typed instruction semantics and validity domains; descriptor bindings, external image "
            "state, output equivalence, driver lowering, and physical performance remain separate"
        ),
    }


def write_spirv_semantic_evidence(text: str, output_directory: Path) -> dict[str, Any]:
    output_directory.mkdir(parents=True, exist_ok=True)
    report = analyze_spirv_semantics(text)
    solver = Solver()
    malformed = [item for item in report["obligations"] if item["status"] == "FAIL"]
    solver.add(BoolVal(bool(malformed)))
    result = solver.check()
    proof = {
        "status": "PASS" if result == unsat else "FAIL",
        "method": "Z3 structural semantic-schema consistency",
        "failed_obligations": malformed,
        "validity_domains": [
            item for item in report["obligations"] if item["status"] == "CONTRACT_REQUIRED"
        ],
        "claim_boundary": "schema consistency is not whole-kernel functional equivalence",
    }
    semantic_path = output_directory / "spirv-semantic-operations.json"
    proof_path = output_directory / "spirv-semantic-proof.json"
    smt_path = output_directory / "spirv-semantic-proof.smt2"
    semantic_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    proof_path.write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n")
    smt_path.write_text(solver.to_smt2())
    return {
        "report": report,
        "proof": proof,
        "artifacts": {
            "semantic_operations": str(semantic_path),
            "semantic_proof": str(proof_path),
            "semantic_smt2": str(smt_path),
        },
    }


def _tokenize(text: str) -> Iterable[str]:
    token = []
    quoted = False
    escaped = False
    for character in text:
        if escaped:
            token.append(character)
            escaped = False
        elif character == "\\" and quoted:
            token.append(character)
            escaped = True
        elif character == '"':
            token.append(character)
            quoted = not quoted
        elif character.isspace() and not quoted:
            if token:
                yield "".join(token)
                token = []
        else:
            token.append(character)
    if token:
        yield "".join(token)


def _type_table(instructions: tuple[SpirvInstruction, ...]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in instructions:
        if not item.result_id or not item.opcode.startswith("OpType"):
            continue
        descriptor: dict[str, Any] = {"opcode": item.opcode, "operands": list(item.operands)}
        if item.opcode == "OpTypeBool":
            descriptor.update({"kind": "bool"})
        elif item.opcode == "OpTypeInt" and len(item.operands) >= 2:
            descriptor.update(
                {"kind": "int", "width": int(item.operands[0]), "signed": item.operands[1] == "1"}
            )
        elif item.opcode == "OpTypeFloat" and item.operands:
            descriptor.update({"kind": "float", "width": int(item.operands[0])})
        elif item.opcode == "OpTypeVector" and len(item.operands) >= 2:
            descriptor.update(
                {"kind": "vector", "component_type": item.operands[0], "count": int(item.operands[1])}
            )
        elif item.opcode == "OpTypeMatrix" and len(item.operands) >= 2:
            descriptor.update(
                {"kind": "matrix", "column_type": item.operands[0], "columns": int(item.operands[1])}
            )
        elif item.opcode == "OpTypeImage":
            descriptor.update({"kind": "image", "sampled_type": item.operands[0] if item.operands else None})
        elif "CooperativeMatrix" in item.opcode:
            descriptor.update({"kind": "cooperative_matrix"})
        else:
            descriptor.setdefault("kind", item.opcode.removeprefix("OpType").lower())
        result[item.result_id] = descriptor
    return result


def _constant_table(instructions: tuple[SpirvInstruction, ...]) -> dict[str, str]:
    return {
        item.result_id: item.operands[-1]
        for item in instructions
        if item.result_id and item.opcode in {"OpConstant", "OpSpecConstant"} and item.operands
    }


def _operation_descriptor(
    instruction: SpirvInstruction,
    types: dict[str, dict[str, Any]],
    constants: dict[str, str],
    capabilities: list[str],
) -> dict[str, Any] | None:
    opcode = instruction.opcode
    family: str | None = None
    semantics = ""
    candidate_families: list[str] = []
    obligations: list[dict[str, Any]] = []
    if opcode in {
        "OpLogicalEqual", "OpLogicalNotEqual", "OpLogicalOr", "OpLogicalAnd",
        "OpLogicalNot", "OpCopyLogical",
    }:
        family = "logical"
        semantics = "component-wise boolean operation preserving scalar/vector boolean shape"
        candidate_families = ["predicate-hoist", "branch-select", "logical-canonicalization"]
    elif opcode in {"OpUDiv", "OpUMod"}:
        family = "unsigned-quotient-remainder"
        semantics = "component-wise unsigned integer quotient or remainder"
        candidate_families = ["invariant-divisor-strength-reduction", "quotient-remainder-fusion"]
        divisor = instruction.operands[-1] if instruction.operands else "unknown"
        constant = constants.get(divisor)
        known_nonzero = constant is not None and _integer_literal(constant) != 0
        obligations.append({
            "id": f"spirv.valid-divisor.{instruction.ordinal}",
            "kind": "validity-domain",
            "status": "PASS" if known_nonzero else "CONTRACT_REQUIRED",
            "statement": "the divisor is nonzero for every active scalar or vector component",
            "native_construct": opcode,
        })
    elif opcode == "OpDot":
        family = "vector-dot"
        semantics = "ordered vector component products followed by implementation-permitted floating reduction"
        candidate_families = ["vector-dot-fusion", "load-reuse"]
        obligations.append(_numeric_obligation(instruction, "dot contraction and IEEE rounding policy"))
    elif opcode in {
        "OpMatrixTimesVector", "OpVectorTimesMatrix", "OpMatrixTimesMatrix",
        "OpMatrixTimesScalar", "OpVectorTimesScalar", "OpOuterProduct",
    }:
        family = "matrix"
        semantics = "SPIR-V column-major logical matrix/vector algebra with declared component order"
        candidate_families = ["matrix-vector-fusion", "layout-aware-load-reuse"]
        obligations.append(_numeric_obligation(instruction, "matrix contraction and IEEE rounding policy"))
    elif opcode.startswith("OpImage") or opcode in {
        "OpSampledImage", "OpImageTexelPointer", "OpImageSparseTexelsResident",
    }:
        family = "image"
        semantics = "typed image access under externally bound descriptor, addressing, filtering, LOD, and format state"
        candidate_families = ["access-chain-simplification", "sample-reuse"]
        obligations.append({
            "id": f"spirv.image-contract.{instruction.ordinal}",
            "kind": "external-descriptor-contract",
            "status": "CONTRACT_REQUIRED",
            "statement": "descriptor identity, image format, coordinates, addressing, filtering, LOD, and bounds are declared",
            "native_construct": opcode,
        })
    elif "CooperativeMatrix" in opcode:
        family = "cooperative-matrix"
        semantics = "capability-gated cooperative matrix operation with declared scope, shape, layout, and component type"
        candidate_families = ["cooperative-matrix-realization", "simt-fallback"]
        capability_present = any("CooperativeMatrix" in value for value in capabilities)
        obligations.append({
            "id": f"spirv.cooperative-capability.{instruction.ordinal}",
            "kind": "capability",
            "status": "PASS" if capability_present else "FAIL",
            "statement": "the module declares the cooperative-matrix capability required by the opcode",
            "native_construct": opcode,
        })
        obligations.append(_numeric_obligation(instruction, "cooperative matrix accumulation and rounding policy"))
    if family is None:
        return None
    result_type = instruction.operands[0] if instruction.result_id and instruction.operands else None
    return {
        "ordinal": instruction.ordinal,
        "source_line": instruction.source_line,
        "result_id": instruction.result_id,
        "result_type": result_type,
        "result_type_descriptor": types.get(result_type or ""),
        "opcode": opcode,
        "operands": list(instruction.operands),
        "family": family,
        "semantics": semantics,
        "candidate_families": candidate_families,
        "obligations": obligations,
    }


def _numeric_obligation(instruction: SpirvInstruction, policy: str) -> dict[str, Any]:
    return {
        "id": f"spirv.numeric-policy.{instruction.ordinal}",
        "kind": "numeric-policy",
        "status": "CONTRACT_REQUIRED",
        "statement": policy,
        "native_construct": instruction.opcode,
    }


def _integer_literal(value: str) -> int:
    try:
        return int(value, 0)
    except ValueError:
        return 0
