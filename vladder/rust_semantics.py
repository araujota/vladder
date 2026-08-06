from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import re
from typing import Any

from .language_adapter import SemanticFlowEdge, SemanticFlowGraph, SemanticFlowNode, obligation


RUST_SUPPORT_VERSION = "bounded-rust-regions-v2"


@dataclass(frozen=True)
class RustParameter:
    name: str
    type: str
    ownership: str


@dataclass(frozen=True)
class RustFunction:
    requested_name: str
    source_name: str
    qualified_name: str
    signature: str
    parameters: tuple[RustParameter, ...]
    return_type: str
    body: str
    source: str
    start_offset: int
    end_offset: int
    function_sha256: str


@dataclass(frozen=True)
class RustEffectSummary:
    safe: bool
    monomorphic: bool
    allocation_free: bool
    panic_free_under_contract: bool
    custom_drop_free: bool
    concurrency_free: bool
    ffi_free: bool
    modeled_calls: tuple[str, ...]
    unresolved_calls: tuple[str, ...]
    blockers: tuple[dict[str, str], ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RustKernelModel:
    family: str
    operation: str
    slice_parameter: str
    needle_parameter: str | None
    accumulator_type: str
    result_type: str
    exactness: str
    panic_policy: str
    overflow_policy: str
    source_form: str
    mir_operations: tuple[str, ...]
    mir_confirmed: bool
    proof_bound: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MirFunction:
    name: str
    signature: str
    body: str
    operations: tuple[str, ...]
    basic_blocks: int
    assertions: tuple[str, ...]
    calls: tuple[str, ...]
    sha256: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def extract_rust_function(text: str, requested_name: str) -> RustFunction:
    source_name = requested_name.rsplit("::", 1)[-1]
    pattern = re.compile(
        rf"(?m)^[ \t]*(?:(?:pub(?:\([^\n)]*\))?|const|async|unsafe|extern\s+\"[^\"]+\")\s+)*"
        rf"fn\s+{re.escape(source_name)}\b"
    )
    matches = list(pattern.finditer(text))
    if not matches:
        raise ValueError(f"Rust function definition not found: {requested_name}")
    if len(matches) > 1:
        raise ValueError(f"multiple Rust definitions named {source_name}; provide one source file per concrete definition")
    start = matches[0].start()
    signature_open = text.find("(", matches[0].end())
    signature_close = _match_delimiter(text, signature_open, "(", ")")
    body_open = _find_body_open(text, signature_close + 1)
    body_close = _match_delimiter(text, body_open, "{", "}")
    signature = text[start:body_open].strip()
    params_text = text[signature_open + 1 : signature_close]
    parameters = tuple(_parse_parameter(value) for value in _split_top_level(params_text, ",") if value.strip())
    between = text[signature_close + 1 : body_open]
    return_match = re.search(r"->\s*(.+?)\s*(?:where\b.*)?$", between.strip(), re.S)
    return_type = return_match.group(1).strip() if return_match else "()"
    source = text[start : body_close + 1]
    qualified = requested_name if "::" in requested_name else source_name
    return RustFunction(
        requested_name,
        source_name,
        qualified,
        signature,
        parameters,
        return_type,
        text[body_open + 1 : body_close],
        source,
        start,
        body_close + 1,
        hashlib.sha256(source.encode()).hexdigest(),
    )


def classify_rust_effects(function: RustFunction) -> RustEffectSummary:
    source = function.source
    blockers: list[dict[str, str]] = []
    if re.search(r"\bunsafe\b", function.signature) or re.search(r"\bunsafe\s*\{", function.body):
        blockers.append(_blocker("unsafe-contract", "unsafe Rust occurs in the selected function", "document and prove the unsafe preconditions or isolate a safe caller region"))
    if re.search(r"\basync\b", function.signature) or re.search(r"\b(?:await|yield)\b", function.body):
        blockers.append(_blocker("async-runtime", "async/coroutine state occurs in the selected function", "async state-machine and executor protocol adapter"))
    allocation_patterns = r"\b(?:Vec|Box|String|Rc|Arc)::|\b(?:vec|format)!\s*\(|\.(?:push|reserve|collect|to_vec|to_string)\s*\("
    if re.search(allocation_patterns, source):
        blockers.append(_blocker("allocation-ownership", "allocation or owning collection mutation occurs", "bounded allocator, capacity, drop, and ownership contract"))
    if re.search(r"\b(?:extern|asm!)\b", source):
        blockers.append(_blocker("ffi-or-assembly", "FFI or inline assembly occurs", "explicit ABI and external-effect adapter"))
    if re.search(r"\b(?:Atomic\w*|Mutex|RwLock|channel|spawn)\b", source):
        blockers.append(_blocker("concurrency", "synchronization or concurrent state occurs", "Rust memory-order and runtime protocol adapter"))
    if "<" in function.signature.split("(", 1)[0] or re.search(r"\bwhere\b", function.signature):
        blockers.append(_blocker("generic-instance", "the selected source definition is generic", "select and capture one monomorphized MIR/LLVM instance"))
    if re.search(r"\b(?:panic|unreachable|todo|unimplemented)!\s*\(", source):
        blockers.append(_blocker("explicit-panic", "an explicit panic-like macro occurs", "model panic payload, unwind strategy, and Drop observables"))

    calls = _source_calls(function.body)
    modeled = {"iter", "fold", "filter", "count", "len", "wrapping_add", "wrapping_mul"}
    unresolved = sorted(call for call in calls if call not in modeled)
    for call in unresolved:
        blockers.append(_blocker("unmodeled-call", f"call is outside the R1 semantic envelope: {call}", "inline a pure helper or declare a compositional call contract"))
    primitive_boundary = all(_r1_type(parameter.type) for parameter in function.parameters) and _r1_type(function.return_type)
    if not primitive_boundary:
        blockers.append(_blocker("type-boundary", "parameter or result type is outside scalars, arrays, and borrowed slices", "language adapter for the concrete ownership and layout boundary"))
    return RustEffectSummary(
        safe=not any(item["kind"] == "unsafe-contract" for item in blockers),
        monomorphic=not any(item["kind"] == "generic-instance" for item in blockers),
        allocation_free=not any(item["kind"] == "allocation-ownership" for item in blockers),
        panic_free_under_contract=not any(item["kind"] == "explicit-panic" for item in blockers),
        custom_drop_free=primitive_boundary,
        concurrency_free=not any(item["kind"] == "concurrency" for item in blockers),
        ffi_free=not any(item["kind"] == "ffi-or-assembly" for item in blockers),
        modeled_calls=tuple(sorted(calls & modeled)),
        unresolved_calls=tuple(unresolved),
        blockers=tuple(blockers),
    )


def parse_mir_functions(text: str) -> tuple[MirFunction, ...]:
    # MIR function names can themselves contain braces, for example
    # `foo::{closure#0}`. Match the terminal body brace instead of treating the
    # first brace on the line as the function body.
    starts = list(re.finditer(r"(?m)^fn\s+(.+?)\s+\{\s*$", text))
    functions: list[MirFunction] = []
    for match in starts:
        body_open = match.end() - 1
        try:
            body_close = _match_delimiter(text, body_open, "{", "}")
        except ValueError:
            continue
        signature = text[match.start() : body_open].strip()
        name = signature[3:].split("(", 1)[0].strip()
        body = text[body_open + 1 : body_close]
        operations = tuple(sorted(set(re.findall(
            r"\b(Len|Lt|Le|Gt|Ge|Eq|Ne|Add|Sub|Mul|BitAnd|BitOr|Shr|Shl|CheckedAdd|CheckedSub|CheckedMul|Offset|PtrToPtr|IntToInt)\b",
            body,
        ))))
        assertions = tuple(line.strip() for line in body.splitlines() if line.strip().startswith("assert("))
        calls = tuple(sorted(set(
            call.strip() for call in re.findall(r"(?m)^\s*_[0-9]+\s*=\s*([^=\n]+?)\([^\n]*\)\s*->", body)
            if "assert" not in call
        )))
        functions.append(MirFunction(
            name,
            signature,
            body,
            operations,
            len(re.findall(r"(?m)^\s*bb\d+:\s*\{", body)),
            assertions,
            calls,
            hashlib.sha256((signature + "{" + body + "}").encode()).hexdigest(),
        ))
    return tuple(functions)


def select_mir_function(functions: tuple[MirFunction, ...], requested_name: str) -> MirFunction:
    normalized = requested_name.replace("::", "::")
    direct = [item for item in functions if item.name == normalized]
    if len(direct) == 1:
        return direct[0]
    suffix = requested_name.rsplit("::", 1)[-1]
    matches = [
        item for item in functions
        if item.name == suffix or item.name.endswith(f"::{suffix}")
    ]
    if len(matches) != 1:
        names = [item.name for item in matches[:8]]
        raise ValueError(f"MIR function selection for {requested_name!r} is ambiguous or absent: {names}")
    return matches[0]


def infer_rust_kernel_model(
    function: RustFunction,
    mir: MirFunction,
    all_mir: tuple[MirFunction, ...],
    *,
    overflow_checks: bool,
    proof_bound: int,
) -> RustKernelModel | None:
    compact = re.sub(r"\s+", "", function.body)
    slice_params = [parameter for parameter in function.parameters if parameter.type in {"&[u8]", "&mut [u8]"}]
    scalar_u8 = [parameter for parameter in function.parameters if parameter.type == "u8"]
    if len(slice_params) == 1 and len(scalar_u8) == 1 and function.return_type == "usize":
        fold_shape = ".iter().fold(0," in compact and "==" in function.body and "asusize" in compact
        while_shape = bool(re.search(r"while\s+\w+\s*<\s*\w+\.len\s*\(\s*\)", function.body)) and "==" in function.body
        closure = [item for item in all_mir if item.name.startswith(mir.name + "::{closure#")]
        fold_mir = any("Eq" in item.operations and "Add" in item.operations for item in closure)
        loop_mir = "Eq" in mir.operations and ("Add" in mir.operations or "CheckedAdd" in mir.operations)
        if (fold_shape and fold_mir) or (while_shape and loop_mir):
            return RustKernelModel(
                "ordered_reduction",
                "count_equal_u8",
                slice_params[0].name,
                scalar_u8[0].name,
                "usize",
                "usize",
                "E1",
                "no panic for valid borrowed slice; candidate must preserve any captured assert behavior",
                "checked" if overflow_checks else "wrapping-machine-usize",
                "iterator_fold" if fold_shape else "index_while",
                tuple(sorted(set(mir.operations) | {operation for item in closure for operation in item.operations})),
                True,
                proof_bound,
            )
    return None


def build_semantic_flow_graph(
    function: RustFunction,
    model: RustKernelModel,
    mir: MirFunction,
    compiler_identity: str,
) -> SemanticFlowGraph:
    def rust_obligation(identifier: str, category: str, statement: str, construct: str) -> tuple[Any, ...]:
        return (obligation(
            identifier,
            category,
            statement,
            proof_method="mir-z3-native",
            language="rust",
            native_construct=construct,
        ),)

    nodes = (
        SemanticFlowNode("input.slice", "Input", "borrowed sequence", (), "slice<u8>", {"parameter": model.slice_parameter}, {"source": function.source_name, "mir": mir.name}, rust_obligation("rust.borrow.call", "ownership", "borrow remains valid for the call", "shared-reference")),
        SemanticFlowNode("input.needle", "Input", "scalar value", (), "u8", {"parameter": model.needle_parameter}, {"source": function.source_name, "mir": mir.name}, ()),
        SemanticFlowNode("borrow.slice", "Borrow", "shared borrow", ("input.slice",), "borrowed<u8>", {}, {"mir_operations": ["Len", "Load"]}, rust_obligation("rust.borrow.shared", "ownership", "no mutation through the shared borrow", "shared-reference")),
        SemanticFlowNode("load.byte", "Load", "stream element load", ("borrow.slice",), "u8", {"traversal": "ordered"}, {"mir_operations": list(model.mir_operations)}, rust_obligation("rust.load.bounds", "bounds", "index or iterator remains in bounds", "slice-index")),
        SemanticFlowNode("compare.eq", "Compare", "equal", ("load.byte", "input.needle"), "bool", {}, {"mir_operation": "Eq"}, ()),
        SemanticFlowNode("map.indicator", "Map", "bool to usize", ("compare.eq",), "usize", {"false": 0, "true": 1}, {"mir_operation": "IntToInt"}, ()),
        SemanticFlowNode("reduce.count", "Reduce", "ordered sum", ("map.indicator",), "usize", {"algebra": "sum", "overflow": model.overflow_policy}, {"mir_operations": ["Add", "CheckedAdd"]}, rust_obligation("rust.reduce.overflow", "numeric", "panic and overflow contract is preserved", "usize-add")),
        SemanticFlowNode("control.loop", "Control", "sequence traversal", ("borrow.slice", "reduce.count"), None, {"source_form": model.source_form}, {"basic_blocks": mir.basic_blocks}, rust_obligation("rust.loop.coverage", "bounds", "every element is visited exactly once", model.source_form)),
        SemanticFlowNode("output.count", "Output", "return reduction", ("reduce.count",), "usize", {}, {"return_type": function.return_type}, ()),
    )
    edge_pairs = (
        ("input.slice", "borrow.slice", "slice<u8>", "borrowed", "slice", "call", "sequenced"),
        ("borrow.slice", "load.byte", "u8", "borrowed", "slice", "iteration", "ordered"),
        ("load.byte", "compare.eq", "u8", "value", "local", "expression", "ordered"),
        ("input.needle", "compare.eq", "u8", "value", "local", "call", "ordered"),
        ("compare.eq", "map.indicator", "bool", "value", "local", "expression", "ordered"),
        ("map.indicator", "reduce.count", "usize", "value", "accumulator", "iteration", "ordered"),
        ("reduce.count", "control.loop", "usize", "state", "accumulator", "loop", "loop-carried"),
        ("borrow.slice", "control.loop", "slice<u8>", "borrowed", "slice", "loop", "ordered"),
        ("reduce.count", "output.count", "usize", "value", "return", "call", "ordered"),
    )
    edges = tuple(
        SemanticFlowEdge(f"edge.{index}", source, destination, value_type, ownership, alias, lifetime, ordering)
        for index, (source, destination, value_type, ownership, alias, lifetime, ordering) in enumerate(edge_pairs)
    )
    return SemanticFlowGraph(
        name=function.qualified_name,
        source_language="rust",
        compiler_identity=compiler_identity,
        semantic_ir="rust-mir",
        function_identity=function.function_sha256,
        nodes=nodes,
        edges=edges,
        contracts={
            "family": model.family,
            "operation": model.operation,
            "exactness": model.exactness,
            "panic_policy": model.panic_policy,
            "overflow_policy": model.overflow_policy,
            "proof_bound": model.proof_bound,
        },
        excluded_claims=(
            "arbitrary Rust equivalence",
            "unsafe contract proof",
            "custom Drop equivalence",
            "async or concurrency protocol equivalence",
            "FFI or external runtime equivalence",
        ),
    )


def _blocker(kind: str, reason: str, required: str) -> dict[str, str]:
    return {"kind": kind, "reason": reason, "required_adapter": required}


def _source_calls(body: str) -> set[str]:
    calls = set(re.findall(r"\.([A-Za-z_]\w*)\s*\(", body))
    calls.update(re.findall(r"(?<![.!:])\b([A-Za-z_]\w*)\s*\(", body))
    return calls - {"if", "while", "for", "match", "loop", "return", "Some", "None", "Ok", "Err"}


def _r1_type(value: str) -> bool:
    normalized = re.sub(r"\s+", " ", value.strip())
    if normalized in {"()", "bool", "u8", "u16", "u32", "u64", "u128", "usize", "i8", "i16", "i32", "i64", "i128", "isize", "f32", "f64"}:
        return True
    return bool(re.fullmatch(r"&(?:mut\s+)?\[(?:u8|u16|u32|u64|usize|i8|i16|i32|i64|isize|f32|f64)\]", normalized))


def _parse_parameter(value: str) -> RustParameter:
    stripped = value.strip()
    receiver = re.fullmatch(r"(?:(?:&(?:'\w+\s+)?(?:mut\s+)?)|(?:mut\s+)?)self", stripped)
    if receiver:
        ownership = "borrowed_mut" if "mut" in stripped else "borrowed" if stripped.startswith("&") else "owned_self"
        return RustParameter("self", stripped, ownership)
    name_type = _split_first_top_level(stripped, ":")
    if name_type is None:
        raise ValueError(f"unsupported Rust receiver or parameter: {stripped}")
    name, type_name = (item.strip() for item in name_type)
    if name in {"self", "&self", "&mut self"}:
        raise ValueError("R1 requires a standalone function; method receivers use a state adapter")
    ownership = "borrowed_mut" if type_name.startswith("&mut ") else "borrowed" if type_name.startswith("&") else "value"
    return RustParameter(name, type_name, ownership)


def _split_top_level(text: str, delimiter: str) -> list[str]:
    values: list[str] = []
    start = 0
    stack: list[str] = []
    pairs = {"(": ")", "[": "]", "{": "}", "<": ">"}
    in_string: str | None = None
    escaped = False
    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == in_string:
                in_string = None
            continue
        if char in {'"', "'"}:
            in_string = char
        elif char in pairs:
            stack.append(pairs[char])
        elif stack and char == stack[-1]:
            stack.pop()
        elif char == delimiter and not stack:
            values.append(text[start:index])
            start = index + 1
    values.append(text[start:])
    return values


def _split_first_top_level(text: str, delimiter: str) -> tuple[str, str] | None:
    values = _split_top_level(text, delimiter)
    if len(values) < 2:
        return None
    return values[0], delimiter.join(values[1:])


def _find_body_open(text: str, start: int) -> int:
    stack: list[str] = []
    in_string: str | None = None
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == in_string:
                in_string = None
            continue
        if char in {'"', "'"}:
            in_string = char
        elif char in "([<":
            stack.append({"(": ")", "[": "]", "<": ">"}[char])
        elif stack and char == stack[-1]:
            stack.pop()
        elif char == "{" and not stack:
            return index
    raise ValueError("Rust function body not found")


def _match_delimiter(text: str, start: int, opening: str, closing: str) -> int:
    if start < 0 or start >= len(text) or text[start] != opening:
        raise ValueError(f"expected {opening!r} at offset {start}")
    depth = 0
    in_string: str | None = None
    escaped = False
    line_comment = False
    block_comment = 0
    index = start
    while index < len(text):
        char = text[index]
        next_char = text[index + 1] if index + 1 < len(text) else ""
        if line_comment:
            if char == "\n":
                line_comment = False
        elif block_comment:
            if char == "/" and next_char == "*":
                block_comment += 1
                index += 1
            elif char == "*" and next_char == "/":
                block_comment -= 1
                index += 1
        elif in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == in_string:
                in_string = None
        elif char == "/" and next_char == "/":
            line_comment = True
            index += 1
        elif char == "/" and next_char == "*":
            block_comment = 1
            index += 1
        elif char in {'"', "'"}:
            in_string = char
        elif char == opening:
            depth += 1
        elif char == closing:
            depth -= 1
            if depth == 0:
                return index
        index += 1
    raise ValueError(f"unterminated {opening}{closing} region")
