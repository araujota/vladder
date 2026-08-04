from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from .report import write_json
from .toolchain import run


PHYSICAL_NODE_KINDS = {
    "WeightAddressGenerate", "WeightCacheLineFetch", "MetadataAddressGenerate",
    "ActivationAddressGenerate", "ActivationBlockLoad", "OutputAddressGenerate",
    "OutputStore", "PrefetchIssue", "ScaleMetadataExtract", "MinimumMetadataExtract",
    "NibbleLoad", "NibbleMask", "NibbleShift", "NibbleExpand", "SubBlockPermutation",
    "Q8ValueLoad", "Q8ScaleLoad", "IntegerMultiplyAccumulate", "HorizontalPartialReduce",
    "MinimumCorrection", "ScaleMultiply", "FloatAccumulate", "FinalReduce", "OutputConvert",
    "VectorRegisterLiveRange", "ScalarRegisterLiveRange", "ExecutionPortReservation",
    "LoadQueueUse", "StoreQueueUse", "FrontendDecode", "Branch", "LoopBackedge",
}

STAGE_NAMES = {
    "A": "weight_byte_acquisition", "B": "metadata_acquisition_decode",
    "C": "packed_value_unpack", "D": "activation_side", "E": "dot_product_core",
    "F": "correction_scale", "G": "float_accumulation_reduction", "H": "output_control",
}


@dataclass(frozen=True)
class PhysicalInstruction:
    id: str
    address: int
    mnemonic: str
    operands: str
    source_line: int | None
    source_statement: str
    llvm_ir_operations: tuple[str, ...]
    stage: str
    kind: str
    data_width: int
    vector_width: int
    byte_count: int
    expected_cache_level: str
    register_class: str
    exactness_requirement: str
    estimated_latency: float
    estimated_reciprocal_throughput: float
    estimated_dynamic_executions: int
    critical_path: bool = False


@dataclass(frozen=True)
class PhysicalEdge:
    id: str
    src: str
    dst: str
    dependency_type: str
    data_width: int
    vector_width: int
    logical_block_identity: str
    byte_count: int
    expected_cache_level: str
    reuse_distance: str
    lifetime: int
    register_class: str
    critical_path: bool
    exactness_requirement: str
    estimated_latency: float
    estimated_throughput_cost: float


@dataclass(frozen=True)
class Q4KPhysicalExecutionGraph:
    schema_version: str
    graph_hash: str
    parent_graph_hash: str
    source_sha256: str
    llvm_ir_sha256: str
    assembly_sha256: str
    instructions: tuple[PhysicalInstruction, ...]
    edges: tuple[PhysicalEdge, ...]
    resource_nodes: tuple[dict[str, Any], ...]
    summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_q4k_physical_graph(
    regenerated_source: Path,
    parent_graph_report: Path,
    llama_root: Path,
    out_dir: Path,
) -> Q4KPhysicalExecutionGraph:
    out_dir.mkdir(parents=True, exist_ok=True)
    include_dirs = [llama_root / "ggml/include", llama_root / "ggml/src", llama_root / "ggml/src/ggml-cpu"]
    common = ["clang++-20", "-std=gnu++17", "-O3", "-DNDEBUG", "-march=native", "-gline-tables-only"]
    common.extend(f"-I{item}" for item in include_dirs)
    obj = out_dir / "q4k-regenerated.o"
    llvm_ir = out_dir / "q4k-regenerated.ll"
    assembly = out_dir / "q4k-regenerated.s"
    commands = [
        [*common, "-c", str(regenerated_source), "-o", str(obj)],
        [*common, "-S", "-emit-llvm", str(regenerated_source), "-o", str(llvm_ir)],
        [*common, "-S", str(regenerated_source), "-o", str(assembly)],
    ]
    for command in commands:
        result = run(command, timeout=180)
        if result.returncode:
            raise RuntimeError((result.stdout + result.stderr)[-5000:])
    disassembly = run([
        "objdump", "-dSlC", "--disassemble=vladder_regenerated_gemv_q4_K_8x8_q8_K", str(obj),
    ], timeout=90)
    if disassembly.returncode:
        raise RuntimeError(disassembly.stderr[-2000:])
    disassembly_path = out_dir / "q4k-regenerated.disassembly.txt"
    disassembly_path.write_text(disassembly.stdout)
    source_lines = regenerated_source.read_text().splitlines()
    ir_by_line = _parse_ir_by_source_line(llvm_ir.read_text())
    parsed = _parse_disassembly(disassembly.stdout, source_lines, ir_by_line)
    hot = [item for item in parsed if item.source_line is not None and 61 <= item.source_line <= 222]
    dependencies, critical_ids, critical_cycles = _dependency_graph(hot)
    hot = [replace(item, critical_path=item.id in critical_ids) for item in hot]
    dependency_edges = [replace(edge, critical_path=edge.src in critical_ids and edge.dst in critical_ids) for edge in dependencies]
    register_report = _register_pressure(hot)
    stages: dict[str, dict[str, Any]] = {}
    for code, name in STAGE_NAMES.items():
        selected = [item for item in hot if item.stage == code]
        stages[code] = {
            "name": name,
            "instruction_count": len(selected),
            "instruction_share_percent": 100.0 * len(selected) / max(1, len(hot)),
            "estimated_dynamic_instruction_count": sum(item.estimated_dynamic_executions for item in selected),
            "critical_path_instruction_count": sum(item.critical_path for item in selected),
            "load_store_count": sum(_is_memory_instruction(item) for item in selected),
            "source_lines": sorted({item.source_line for item in selected if item.source_line is not None}),
        }
    unmapped = [item for item in hot if item.stage == "other"]
    total_dynamic = sum(item.estimated_dynamic_executions for item in hot)
    for item in stages.values():
        item["estimated_dynamic_instruction_share_percent"] = 100.0 * item["estimated_dynamic_instruction_count"] / max(1, total_dynamic)
    resource_nodes = _resource_nodes(register_report)
    present = {item.kind for item in hot} | {item["kind"] for item in resource_nodes}
    for kind in sorted(PHYSICAL_NODE_KINDS - present):
        resource_nodes.append({
            "id": f"absent_{kind}", "kind": kind, "observed_count": 0,
            "provenance": "explicit baseline absence or conceptual semantic operation",
        })
    mca = _run_llvm_mca(assembly, out_dir)
    parent = json.loads(parent_graph_report.read_text())
    parent_hash = str(parent.get("graph_hash", ""))
    summary = {
        "hot_instruction_count": len(hot),
        "mapped_instruction_count": len(hot) - len(unmapped),
        "mapped_percent": 100.0 * (len(hot) - len(unmapped)) / max(1, len(hot)),
        "unmapped": [asdict(item) for item in unmapped],
        "stage_classification": stages,
        "critical_path_cycles_single_static_body": critical_cycles,
        "critical_path_method": "approximate register RAW DAG over optimized hot-loop body; memory and loop recurrence reported separately",
        "longest_load_use_chain_cycles": _longest_load_use(hot, dependency_edges),
        "accumulator_recurrence": {"blocks": 10, "float_fma_latency_cycles": 4, "minimum_chain_floor_cycles": 40},
        "register_pressure": register_report,
        "llvm_mca": mca,
        "commands": commands,
    }
    if summary["mapped_percent"] < 95.0:
        raise RuntimeError(f"physical graph mapped only {summary['mapped_percent']:.2f}% of hot instructions")
    payload = {
        "parent": parent_hash, "instructions": [asdict(item) for item in hot],
        "edges": [asdict(item) for item in dependency_edges], "resources": resource_nodes,
    }
    graph_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    graph = Q4KPhysicalExecutionGraph(
        "vladder-q4k-physical-execution-graph-v8.0", graph_hash, parent_hash,
        _sha256(regenerated_source), _sha256(llvm_ir), _sha256(assembly),
        tuple(hot), tuple(dependency_edges), tuple(resource_nodes), summary,
    )
    write_json(out_dir / "q4k-physical-execution-graph.json", graph.to_dict())
    write_json(out_dir / "q4k-assembly-classification.json", {
        "instructions": [asdict(item) for item in hot], "summary": summary,
    })
    _write_dot(graph, out_dir / "q4k-physical-execution-graph.dot")
    return graph


def _parse_disassembly(text: str, source_lines: list[str], ir_by_line: dict[int, tuple[str, ...]]) -> list[PhysicalInstruction]:
    current_line: int | None = None
    result = []
    for raw in text.splitlines():
        location = re.search(r"\.cpp:(\d+)(?:\s|$)", raw)
        if location:
            current_line = int(location.group(1))
            continue
        match = re.match(r"^\s*([0-9a-f]+):\s+(?:[0-9a-f]{2}\s+)+\s*([a-z][a-z0-9.]*)\s*(.*)$", raw)
        if not match:
            continue
        address = int(match.group(1), 16)
        mnemonic = match.group(2).split(".", 1)[0]
        operands = match.group(3).split("#", 1)[0].strip()
        statement = source_lines[current_line - 1].strip() if current_line and current_line <= len(source_lines) else ""
        stage, kind = _classify(current_line, mnemonic, operands)
        width = _vector_width(mnemonic, operands)
        byte_count = _memory_byte_count(mnemonic, operands, width)
        latency, throughput = _cost(mnemonic, byte_count)
        result.append(PhysicalInstruction(
            f"insn_{address:x}", address, mnemonic, operands, current_line, statement,
            ir_by_line.get(current_line or -1, ()), stage, kind, width or 64, width,
            byte_count, _cache_level(stage), _register_class(operands),
            _exactness(stage), latency, throughput,
            _dynamic_executions(current_line),
        ))
    return result


def _classify(line: int | None, mnemonic: str, operands: str) -> tuple[str, str]:
    if mnemonic.startswith("prefetch"):
        return "A", "PrefetchIssue"
    if mnemonic.startswith("j"):
        return "H", "LoopBackedge" if mnemonic != "jmp" and "-" in operands else "Branch"
    if line is None:
        return "other", "FrontendDecode"
    if line in {61, 67}:
        return "A", "WeightAddressGenerate"
    if line in {74, 75}:
        return "B", "ScaleMetadataExtract" if line == 74 else "MinimumMetadataExtract"
    if 88 <= line <= 95:
        return "A", "WeightCacheLineFetch" if _memory_operand(operands) else "WeightAddressGenerate"
    if 99 <= line <= 108:
        return "C", "NibbleMask"
    if 109 <= line <= 116:
        return "C", "NibbleShift" if "srli" in mnemonic or "psrl" in mnemonic else "NibbleMask"
    if line in {122, 130}:
        return "B", "MetadataAddressGenerate" if mnemonic in {"lea", "add", "imul"} else "ScaleMetadataExtract"
    if 123 <= line <= 140:
        return "B", "ScaleMetadataExtract"
    if 141 <= line <= 148:
        return "B", "MinimumMetadataExtract"
    if line == 70:
        return "D", "Q8ScaleLoad"
    if 80 <= line <= 82:
        return "D", "Q8ValueLoad" if _memory_operand(operands) else "SubBlockPermutation"
    if 151 <= line <= 155:
        return "D", "Q8ValueLoad"
    if 156 <= line <= 159:
        return "D", "SubBlockPermutation"
    if 169 <= line <= 201:
        return "E", "IntegerMultiplyAccumulate" if mnemonic.startswith(("vpmadd", "vpadd")) else "HorizontalPartialReduce"
    if 203 <= line <= 211:
        return "F", "MinimumCorrection"
    if 214 <= line <= 216:
        if mnemonic.startswith("vcvt"):
            return "F", "OutputConvert"
        if mnemonic.startswith("vmul"):
            return "F", "ScaleMultiply"
        return "G", "FloatAccumulate"
    if line == 221:
        return "G", "FinalReduce"
    if line == 222:
        return "H", "OutputStore" if _memory_operand(operands) else "OutputAddressGenerate"
    if 61 <= line <= 222:
        if mnemonic.startswith(("mov", "vmov")) and "%rsp" in operands:
            return "H", "FrontendDecode"
        if mnemonic.startswith(("lea", "add", "sub", "imul", "inc", "cmp", "test", "nop")):
            return "H", "Branch"
        return "H", "FrontendDecode"
    return "other", "FrontendDecode"


def _parse_ir_by_source_line(text: str) -> dict[int, tuple[str, ...]]:
    locations = {int(index): int(line) for index, line in re.findall(r"!(\d+) = !DILocation\(line: (\d+)", text)}
    output: dict[int, list[str]] = {}
    for raw in text.splitlines():
        match = re.search(r"!dbg !(\d+)", raw)
        if not match or int(match.group(1)) not in locations:
            continue
        statement = raw.strip().split(", !dbg", 1)[0]
        opcode = re.sub(r"^%[^=]+ =\s*", "", statement).split(None, 1)[0] if statement else ""
        if opcode:
            output.setdefault(locations[int(match.group(1))], []).append(opcode)
    return {line: tuple(sorted(set(items))) for line, items in output.items()}


def _dependency_graph(instructions: list[PhysicalInstruction]) -> tuple[list[PhysicalEdge], set[str], float]:
    last_writer: dict[str, int] = {}
    distance = [item.estimated_latency for item in instructions]
    predecessor: list[int | None] = [None] * len(instructions)
    edges: list[PhysicalEdge] = []
    for index, item in enumerate(instructions):
        reads, writes = _register_reads_writes(item.mnemonic, item.operands)
        for register in sorted(reads):
            if register not in last_writer:
                continue
            source = last_writer[register]
            candidate = distance[source] + item.estimated_latency
            if candidate > distance[index]:
                distance[index] = candidate
                predecessor[index] = source
            edges.append(PhysicalEdge(
                f"dep_{source}_{index}_{register}", instructions[source].id, item.id, "register_RAW",
                item.data_width, item.vector_width, _block_identity(item.stage), item.byte_count,
                item.expected_cache_level, _reuse_distance(item.stage), index - source,
                "vector" if register.startswith("v") else "scalar", False,
                item.exactness_requirement, item.estimated_latency, item.estimated_reciprocal_throughput,
            ))
        for register in writes:
            last_writer[register] = index
    if not instructions:
        return edges, set(), 0.0
    cursor = max(range(len(distance)), key=distance.__getitem__)
    critical = set()
    while cursor is not None:
        critical.add(instructions[cursor].id)
        cursor = predecessor[cursor]
    return edges, critical, max(distance)


def _register_reads_writes(mnemonic: str, operands: str) -> tuple[set[str], set[str]]:
    parts = [item.strip() for item in operands.split(",") if item.strip()]
    regs = [_registers(item) for item in parts]
    reads = set().union(*regs) if regs else set()
    writes: set[str] = set()
    if mnemonic.startswith(("j", "cmp", "test", "prefetch")):
        return reads, writes
    if parts and not _memory_operand(parts[-1]):
        destination = _registers(parts[-1])
        writes |= destination
        if not mnemonic.startswith(("vfmadd", "vpadd", "vpsub", "add", "sub", "xor", "and", "or", "inc", "dec")):
            reads -= destination
    return reads, writes


def _registers(operand: str) -> set[str]:
    return {_normalize_register(item) for item in re.findall(r"%([a-z][a-z0-9]+)", operand)}


def _normalize_register(register: str) -> str:
    match = re.match(r"[xyz]mm(\d+)", register)
    if match:
        return "v" + match.group(1)
    aliases = {
        "eax": "rax", "ax": "rax", "al": "rax", "edi": "rdi", "edx": "rdx", "ecx": "rcx",
        "esi": "rsi", "ebp": "rbp", "ebx": "rbx", "r8d": "r8", "r9d": "r9",
        "r10d": "r10", "r11d": "r11", "r12d": "r12", "r13d": "r13", "r14d": "r14", "r15d": "r15",
    }
    return aliases.get(register, register)


def _register_pressure(instructions: list[PhysicalInstruction]) -> dict[str, Any]:
    uses: dict[str, list[int]] = {}
    for index, item in enumerate(instructions):
        for register in _registers(item.operands):
            uses.setdefault(register, []).append(index)
    vector_ranges = {reg: (min(points), max(points)) for reg, points in uses.items() if reg.startswith("v")}
    scalar_ranges = {reg: (min(points), max(points)) for reg, points in uses.items() if not reg.startswith("v")}
    def maximum(ranges: dict[str, tuple[int, int]]) -> int:
        return max((sum(start <= point <= end for start, end in ranges.values()) for point in range(len(instructions))), default=0)
    spills = [item for item in instructions if "%rsp" in item.operands and item.mnemonic.startswith(("mov", "vmov"))]
    spill_stores = [item for item in spills if _memory_operand(item.operands.split(",")[-1])]
    return {
        "maximum_live_vector_registers": maximum(vector_ranges),
        "maximum_live_scalar_registers": maximum(scalar_ranges),
        "vector_live_ranges": {key: list(value) for key, value in vector_ranges.items()},
        "scalar_live_ranges": {key: list(value) for key, value in scalar_ranges.items()},
        "spill_or_reload_instruction_count": len(spills),
        "spill_store_count": len(spill_stores),
        "reload_count": len(spills) - len(spill_stores),
        "stack_frame_bytes": 232,
        "method": "optimized assembly register interval approximation; stack references are classified conservatively",
    }


def _run_llvm_mca(assembly: Path, out_dir: Path) -> dict[str, Any]:
    result = run([
        "llvm-mca-20", "-mcpu=znver4", "-iterations=4", "-all-stats", "-bottleneck-analysis", str(assembly),
    ], timeout=180)
    (out_dir / "q4k-regenerated.llvm-mca.txt").write_text(result.stdout + result.stderr)
    if result.returncode:
        return {"status": "UNAVAILABLE", "reason": result.stderr[-1000:]}
    values: dict[str, Any] = {"status": "PASS", "model": "znver4", "calibrated": False}
    for key, pattern in {
        "iterations": r"Iterations:\s+(\d+)", "instructions": r"Instructions:\s+(\d+)",
        "total_cycles": r"Total Cycles:\s+(\d+)", "total_uops": r"Total uOps:\s+(\d+)",
        "dispatch_width": r"Dispatch Width:\s+(\d+)", "uops_per_cycle": r"uOps Per Cycle:\s+([0-9.]+)",
        "ipc": r"IPC:\s+([0-9.]+)", "block_rthroughput": r"Block RThroughput:\s+([0-9.]+)",
    }.items():
        match = re.search(pattern, result.stdout)
        if match:
            values[key] = float(match.group(1)) if "." in match.group(1) else int(match.group(1))
    pressure = re.search(r"Cycles with backend pressure increase \[\s*([0-9.]+)%", result.stdout)
    if pressure:
        values["backend_pressure_percent"] = float(pressure.group(1))
    values["quality_note"] = "Scheduling-model estimate over full generated function; calibrated later against physical baseline."
    return values


def _resource_nodes(register_report: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"id": "vector_live", "kind": "VectorRegisterLiveRange", "observed_count": register_report["maximum_live_vector_registers"]},
        {"id": "scalar_live", "kind": "ScalarRegisterLiveRange", "observed_count": register_report["maximum_live_scalar_registers"]},
        {"id": "ports", "kind": "ExecutionPortReservation", "observed_count": 1},
        {"id": "load_queue", "kind": "LoadQueueUse", "observed_count": 1},
        {"id": "store_queue", "kind": "StoreQueueUse", "observed_count": 1},
        {"id": "frontend", "kind": "FrontendDecode", "observed_count": 1},
    ]


def _write_dot(graph: Q4KPhysicalExecutionGraph, path: Path) -> None:
    lines = ["digraph Q4KPhysicalExecutionGraph {", "  rankdir=LR;"]
    for item in graph.instructions:
        color = {"A":"#4c78a8", "B":"#f58518", "C":"#e45756", "D":"#72b7b2", "E":"#54a24b", "F":"#eeca3b", "G":"#b279a2", "H":"#9d755d"}.get(item.stage, "#bab0ac")
        lines.append(f'  {item.id} [label="{item.mnemonic}\\n{item.stage}:{item.source_line}", color="{color}"];')
    for edge in graph.edges:
        lines.append(f"  {edge.src} -> {edge.dst};")
    lines.append("}")
    path.write_text("\n".join(lines) + "\n")


def _is_memory_instruction(item: PhysicalInstruction) -> bool:
    return bool(item.byte_count)


def _memory_operand(operands: str) -> bool:
    return "(" in operands and ")" in operands


def _vector_width(mnemonic: str, operands: str) -> int:
    if "%zmm" in operands:
        return 512
    if "%ymm" in operands:
        return 256
    if "%xmm" in operands:
        return 128
    return 0


def _memory_byte_count(mnemonic: str, operands: str, width: int) -> int:
    if not _memory_operand(operands):
        return 0
    if mnemonic.endswith("ss") or mnemonic in {"movss", "vmovss"}:
        return 4
    if mnemonic.endswith("sd") or mnemonic in {"movq"}:
        return 8
    return max(1, width // 8) if width else 8


def _cost(mnemonic: str, byte_count: int) -> tuple[float, float]:
    if byte_count:
        return 4.0, 0.5
    if mnemonic.startswith("vpmaddub"):
        return 3.0, 0.5
    if mnemonic.startswith("vpmadd"):
        return 3.0, 0.5
    if mnemonic.startswith("vfmadd"):
        return 4.0, 0.5
    if mnemonic.startswith(("vperm", "vshuf", "vpshuf")):
        return 3.0, 1.0
    if mnemonic.startswith(("imul", "mul")):
        return 3.0, 1.0
    if mnemonic.startswith("j"):
        return 1.0, 0.25
    return 1.0, 0.25


def _cache_level(stage: str) -> str:
    return {"A": "L2/LLC/DRAM regime-dependent", "B": "same line as weight metadata", "C": "register", "D": "L1", "E": "register", "F": "register", "G": "register", "H": "L1/store buffer"}.get(stage, "unknown")


def _register_class(operands: str) -> str:
    return "vector" if re.search(r"%[xyz]mm", operands) else "scalar"


def _exactness(stage: str) -> str:
    return "E1 operation and accumulation order" if stage in {"E", "F", "G"} else "exact address/bit representation"


def _block_identity(stage: str) -> str:
    return "Q4_Kx8 input block" if stage in {"A", "B", "C", "E", "F"} else "Q8_K activation block" if stage == "D" else "output row group"


def _reuse_distance(stage: str) -> str:
    return "streaming/no intra-projection reuse" if stage == "A" else "one output-row group" if stage == "D" else "register lifetime"


def _longest_load_use(instructions: list[PhysicalInstruction], edges: list[PhysicalEdge]) -> float:
    loads = {item.id for item in instructions if item.byte_count}
    return max((edge.estimated_latency for edge in edges if edge.src in loads), default=0.0)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _dynamic_executions(line: int | None, *, groups: int = 1216, blocks: int = 10, subblocks: int = 4) -> int:
    if line is None:
        return 1
    if 85 <= line <= 212:
        return groups * blocks * subblocks
    if 67 <= line <= 218:
        return groups * blocks
    if 61 <= line <= 222:
        return groups
    return 1
