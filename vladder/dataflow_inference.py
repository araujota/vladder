from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any, Mapping

from .dataflow_audit import classify_cpp_dataflow
from .dataflow_ir import BoundedDataflowContract, DATAFLOW_FAMILIES


INFERENCE_VERSION = "bounded-dataflow-contract-inference-v2"


@dataclass(frozen=True)
class DataflowContractInference:
    family: str
    status: str
    inferred: Mapping[str, Any]
    evidence: tuple[str, ...]
    unresolved: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "inferred": dict(self.inferred),
            "evidence": list(self.evidence),
            "unresolved": list(self.unresolved),
        }

    def contract(self) -> BoundedDataflowContract | None:
        return BoundedDataflowContract.from_dict(dict(self.inferred)) if self.status == "complete" else None


def infer_bounded_dataflow_contracts(
    source: str,
    function: str,
    *,
    overrides: Mapping[str, Any] | None = None,
    compiler_report: Mapping[str, Any] | None = None,
) -> tuple[DataflowContractInference, ...]:
    """Infer only compiler/source-visible bounded dataflow facts.

    The recognizer is deliberately an admission aid, not an applicability proof. Missing extent,
    alias, failure, or ownership facts remain explicit and prevent executable enumeration.
    """
    overrides = dict(overrides or {})
    classified = classify_cpp_dataflow(source, function)
    detected = [str(item["family"]) for item in classified["families"]]
    if (
        re.search(r"\b(?:current|candidate|values?)\b", source)
        and re.search(r"\b(?:baseline|previous|old)\b", source)
        and re.search(r"\b(?:out|dst|output)[A-Za-z0-9_]*\s*\[", source)
        and re.search(r"\b(?:for|while)\s*\(", source)
    ):
        detected.append("predicate-stable-compaction")
        if re.search(r"\b(?:next|state|cache)[A-Za-z0-9_]*\s*\[", source):
            detected.append("stateful-delta-transducer")
    requested = overrides.get("family")
    if requested in DATAFLOW_FAMILIES and requested not in detected:
        detected.append(str(requested))
    results = []
    for family in sorted(set(detected)):
        values: dict[str, Any] = {"family": family}
        evidence: list[str] = []
        unresolved: list[str] = []

        extent = _fixed_extent(source)
        if extent is not None:
            values["max_elements"] = extent
            evidence.append(f"fixed or dominating maximum element bound: {extent}")
        elif family in {"fixed-width-codec", "quantized-block-4x4"}:
            values["max_elements"] = 16 if family == "quantized-block-4x4" else 1
            evidence.append("family shape fixes the bounded element count")
        elif _runtime_sized_borrowed_range(source, compiler_report):
            values["max_elements"] = None
            evidence.append("runtime-sized borrowed contiguous range with structural loop proof")
        else:
            unresolved.append("maximum element bound or runtime-sized borrowed range")

        bits = _element_bits(source)
        if bits is not None:
            values["element_bits"] = bits
            evidence.append(f"fixed-width element type: {bits} bits")

        if family == "predicate-stable-compaction":
            values["output_mode"] = _output_mode(source)
            values["stable"] = not any(token in source for token in ("unstable", "swap_remove", "partition("))
        if family in {"predicate-stable-compaction", "stateful-delta-transducer"}:
            no_growth = (
                _caller_owned_output(source)
                or _dominating_vector_capacity_guard(source)
                or _compiler_no_growth_closure(compiler_report)
            )
            values["no_growth"] = no_growth
            values["record_trivially_copyable"] = (
                _trivial_record_evidence(source) or _compiler_trivial_output(compiler_report)
            )
            values["noexcept"] = (
                _function_noexcept(source, function) or _compiler_nonthrowing_region(compiler_report)
            )
            if no_growth:
                evidence.append("caller-owned output or checked no-growth container capacity")
            else:
                unresolved.append("caller-owned or checked no-growth output")
            if values["record_trivially_copyable"]:
                evidence.append("primitive or explicitly trivially-copyable record")
            else:
                unresolved.append("trivially copyable and destructible output record")
            if values["noexcept"]:
                evidence.append("noexcept function boundary")
            else:
                unresolved.append("non-throwing bounded region")
            policy = _capacity_policy(source)
            if policy is None:
                unresolved.append("exact capacity failure behavior")
            else:
                values["capacity_policy"] = policy
                evidence.append(f"capacity failure policy: {policy}")

        if family in {"predicate-stable-compaction", "stateful-delta-transducer"}:
            aliasing = _aliasing(source)
            if aliasing is None and family == "predicate-stable-compaction" and no_growth:
                aliasing = "runtime-guarded-disjoint"
                evidence.append("generated overlap guard preserves the baseline-order fallback")
            if aliasing is None:
                unresolved.append("input/output alias relation")
            else:
                values["aliasing"] = aliasing
                evidence.append(f"declared alias relation: {aliasing}")

        if family == "fixed-width-codec":
            widths = _field_widths(source)
            if widths is None:
                unresolved.append("fixed codec field widths")
            else:
                values["field_widths"] = list(widths)
                evidence.append(f"fixed codec field widths: {widths}")
            byte_order = _byte_order(source)
            if byte_order is None:
                unresolved.append("wire byte order")
            else:
                values["byte_order"] = byte_order
                evidence.append(f"wire byte order: {byte_order}")

        for key, value in overrides.items():
            if key in BoundedDataflowContract.__dataclass_fields__:
                values[key] = value
                unresolved = [item for item in unresolved if not _override_resolves(item, key)]
                evidence.append(f"manifest override: {key}")

        try:
            if not unresolved:
                BoundedDataflowContract.from_dict(values)
        except ValueError as error:
            unresolved.append(str(error))
        results.append(DataflowContractInference(
            family,
            "complete" if not unresolved else "contract_blocked",
            values,
            tuple(evidence),
            tuple(dict.fromkeys(unresolved)),
        ))
    return tuple(results)


def _fixed_extent(source: str) -> int | None:
    candidates: list[int] = []
    for pattern in (
        r"std::span\s*<[^,>]+,\s*(\d+)\s*>",
        r"\[[ \t]*(\d+)[ \t]*\]",
        r"\b(?:n|count|size|length)\s*>\s*(\d+)\b",
        r"\b(?:n|count|size|length)\s*<=\s*(\d+)\b",
        r"VLADDER_MAX_ELEMENTS\s*\(\s*(\d+)\s*\)",
        r"vladder\s*:\s*max_elements\s*=\s*(\d+)",
    ):
        candidates.extend(int(item) for item in re.findall(pattern, source))
    valid = [item for item in candidates if 0 < item <= 4096]
    return min(valid) if valid else None


def _runtime_sized_borrowed_range(source: str, compiler_report: Mapping[str, Any] | None) -> bool:
    has_extent = bool(
        re.search(r"\b(?:n|count|size|length)\b", source)
        or re.search(r"\.size\s*\(\s*\)", source)
    )
    borrowed = bool(
        "std::span" in source
        or re.search(r"\bconst\s+[A-Za-z_:][A-Za-z0-9_:<> ]*\s*\*", source)
        or re.search(r"\b[A-Za-z_:][A-Za-z0-9_:<> ]*\s*\*\s*(?:const\s+)?[A-Za-z_]", source)
    )
    compiler_modeled = bool(
        compiler_report
        and compiler_report.get("typed_abi", {}).get("parameters_modeled")
    )
    return has_extent and borrowed and (compiler_modeled or bool(re.search(r"\b(?:for|while)\s*\(", source)))


def _element_bits(source: str) -> int | None:
    values = [int(item) for item in re.findall(r"(?:std::)?u?int(8|16|32|64)_t", source)]
    return max(values) if values else None


def _output_mode(source: str) -> str:
    index = bool(
        re.search(r"(?:out|dst|changed)[A-Za-z0-9_]*(?:index|indices)|out_indices", source, re.IGNORECASE)
        or re.search(r"\.(?:push_back|emplace_back)\s*\(\s*(?:static_cast<[^>]+>\s*\(\s*)?(?:i|index)\b", source)
    )
    value = bool(re.search(r"(?:out|dst|changed)[A-Za-z0-9_]*(?:value|values)|out_values", source, re.IGNORECASE))
    if index and value:
        return "index-value"
    return "index-only" if index else "value-only"


def _caller_owned_output(source: str) -> bool:
    return bool(
        re.search(r"std::span\s*<\s*(?!const\b)[^>]+>", source)
        or re.search(r"\b(?:out|dst|output)[A-Za-z0-9_]*\s*(?:\[|->|\[)", source)
        or re.search(r"\b(?:out|dst|output)[A-Za-z0-9_]*\s*\*\s*(?:__restrict|restrict)", source)
    )


def _dominating_vector_capacity_guard(source: str) -> bool:
    first_append = min((source.find(token) for token in (".push_back(", ".emplace_back(") if token in source), default=-1)
    if first_append < 0:
        return False
    capacity = source.find("capacity()")
    return 0 <= capacity < first_append and bool(re.search(r"(?:return|throw|fallback)", source[capacity:first_append]))


def _trivial_record_evidence(source: str) -> bool:
    return bool(
        re.search(r"(?:std::)?u?int(?:8|16|32|64)_t", source)
        or "std::byte" in source
        or "is_trivially_copyable" in source
        or "vladder: trivially_copyable" in source
    )


def _function_noexcept(source: str, function: str) -> bool:
    leaf = function.rsplit("::", 1)[-1]
    return bool(re.search(rf"\b{re.escape(leaf)}\s*\([^)]*\)\s*(?:const\s*)?noexcept\b", source, re.DOTALL))


def _capacity_policy(source: str) -> str | None:
    if "truncate" in source or "std::min" in source and "capacity" in source:
        return "truncate"
    first_append = min(
        (source.find(token) for token in (".push_back(", ".emplace_back(") if token in source),
        default=-1,
    )
    capacity_position = source.find("capacity()")
    if 0 <= capacity_position < first_append:
        preflight = source[capacity_position:first_append]
        if (
            re.search(r"(?:current|source|input|baseline)\s*\.\s*size\s*\(\s*\)", preflight)
            and re.search(r"\b(?:return|throw)\b", preflight)
        ):
            return "fail-input-extent-unchanged"
    if re.search(
        r"(?:capacity\s*\(\s*\)\s*-\s*[^;{}]*size\s*\(\s*\)|(?:out_|output_)?capacity)"
        r"[^;{}]*(?:input|current|source)?[^;{}]*size\s*\(\s*\)[^;{}]*(?:return|throw)",
        source,
        re.DOTALL,
    ):
        return "fail-input-extent-unchanged"
    guard = re.search(r"(?:capacity|out_capacity|output_capacity|\.size\(\))[^;{}]*(?:return|throw)", source, re.DOTALL)
    return "fail-unchanged" if guard else None


def _aliasing(source: str) -> str | None:
    if "vladder: aliasing=disjoint" in source:
        return "disjoint"
    pointer_count = len(re.findall(r"\b(?:__restrict|restrict)\b", source))
    return "disjoint" if pointer_count >= 2 else None


def _field_widths(source: str) -> tuple[int, ...] | None:
    explicit = re.search(r"vladder\s*:\s*field_widths\s*=\s*([0-9, ]+)", source)
    if explicit:
        result = tuple(int(item.strip()) for item in explicit.group(1).split(",") if item.strip())
        return result if result else None
    helpers = re.findall(r"(?:append|write|read|encode|decode)_u(8|16|32|64)", source)
    widths = tuple(int(item) for item in helpers[:3])
    return widths if len(widths) == 3 else None


def _byte_order(source: str) -> str | None:
    if any(token in source for token in ("little", "htole", "le16", "le32", "le64")):
        return "little"
    if any(token in source for token in ("big", "hton", "be16", "be32", "be64")):
        return "big"
    return None


def _override_resolves(obligation: str, key: str) -> bool:
    mapping = {
        "max_elements": "maximum element bound",
        "aliasing": "alias relation",
        "capacity_policy": "capacity failure behavior",
        "record_trivially_copyable": "trivially copyable",
        "no_growth": "no-growth output",
        "noexcept": "non-throwing",
        "field_widths": "field widths",
        "byte_order": "byte order",
    }
    return mapping.get(key, "") in obligation


def _compiler_no_growth_closure(report: Mapping[str, Any] | None) -> bool:
    return bool(report and any(
        item.get("container_closure", {}).get("mode") == "borrowed_no_growth"
        and item.get("container_closure", {}).get("guard_dominates_region")
        for item in report.get("subregions", ())
    ))


def _compiler_trivial_output(report: Mapping[str, Any] | None) -> bool:
    return bool(report and any(
        item.get("container_closure", {}).get("trivial_element")
        for item in report.get("subregions", ())
    ))


def _compiler_nonthrowing_region(report: Mapping[str, Any] | None) -> bool:
    if not report:
        return False
    return bool(
        report.get("compiled_effects", {}).get("local_effects")
        and not report.get("compiled_effects", {}).get("unwind_operations")
        and any(item.get("extractable_candidate") for item in report.get("subregions", ()))
    )
