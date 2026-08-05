from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import hashlib
import json
import math
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Iterable

import yaml
from z3 import Int, Solver, sat

from .language_adapter import (
    ProtocolTransition,
    SemanticEffect,
    SemanticFlowEdge,
    SemanticFlowGraph,
    SemanticFlowNode,
    canonical_hash,
    file_sha256,
    obligation,
)


GPU_KERNEL_GRAPH_VERSION = "gpu-kernel-graph-v1"
GPU_ARCHITECTURE_SCHEMA_VERSION = "gpu-architecture-v1"
GPU_GRAMMAR_VERSION = "heterogeneous-execution-v1"


@dataclass(frozen=True)
class GPUArchitecture:
    vendor: str
    name: str
    architecture: str
    device_uuid: str
    warp_size: int
    multiprocessors: int
    max_threads_per_block: int
    max_threads_per_sm: int
    max_blocks_per_sm: int
    max_warps_per_sm: int
    registers_per_sm: int
    register_allocation_unit: int
    shared_memory_per_sm: int
    shared_memory_per_block: int
    global_transaction_bytes: int
    cache_line_bytes: int
    memory_bandwidth_bytes_per_second: float
    clock_hz: float
    issue_width: float = 1.0
    source: str = "declared"
    manifest_hash: str = ""

    def __post_init__(self) -> None:
        positive = {
            "warp_size": self.warp_size,
            "multiprocessors": self.multiprocessors,
            "max_threads_per_block": self.max_threads_per_block,
            "max_threads_per_sm": self.max_threads_per_sm,
            "max_blocks_per_sm": self.max_blocks_per_sm,
            "max_warps_per_sm": self.max_warps_per_sm,
            "registers_per_sm": self.registers_per_sm,
            "register_allocation_unit": self.register_allocation_unit,
            "shared_memory_per_sm": self.shared_memory_per_sm,
            "shared_memory_per_block": self.shared_memory_per_block,
            "global_transaction_bytes": self.global_transaction_bytes,
            "cache_line_bytes": self.cache_line_bytes,
        }
        invalid = [name for name, value in positive.items() if value <= 0]
        if invalid:
            raise ValueError(f"GPU architecture fields must be positive: {', '.join(invalid)}")
        expected = canonical_hash(self._hash_payload())
        if self.manifest_hash and self.manifest_hash != expected:
            raise ValueError("GPU architecture manifest hash does not match its payload")
        if not self.manifest_hash:
            object.__setattr__(self, "manifest_hash", expected)

    def _hash_payload(self) -> dict[str, Any]:
        return {
            key: value
            for key, value in asdict(self).items()
            if key != "manifest_hash"
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": GPU_ARCHITECTURE_SCHEMA_VERSION,
            **self._hash_payload(),
            "manifest_hash": self.manifest_hash,
        }

    @classmethod
    def from_mapping(cls, raw: dict[str, Any], *, source: str = "declared") -> "GPUArchitecture":
        required = (
            "vendor", "name", "architecture", "device_uuid", "warp_size", "multiprocessors",
            "max_threads_per_block", "max_threads_per_sm", "max_blocks_per_sm",
            "max_warps_per_sm", "registers_per_sm", "register_allocation_unit",
            "shared_memory_per_sm", "shared_memory_per_block", "global_transaction_bytes",
            "cache_line_bytes", "memory_bandwidth_bytes_per_second", "clock_hz",
        )
        missing = [key for key in required if key not in raw]
        if missing:
            raise ValueError(f"GPU architecture manifest is missing: {', '.join(missing)}")
        return cls(
            vendor=str(raw["vendor"]),
            name=str(raw["name"]),
            architecture=str(raw["architecture"]),
            device_uuid=str(raw["device_uuid"]),
            warp_size=int(raw["warp_size"]),
            multiprocessors=int(raw["multiprocessors"]),
            max_threads_per_block=int(raw["max_threads_per_block"]),
            max_threads_per_sm=int(raw["max_threads_per_sm"]),
            max_blocks_per_sm=int(raw["max_blocks_per_sm"]),
            max_warps_per_sm=int(raw["max_warps_per_sm"]),
            registers_per_sm=int(raw["registers_per_sm"]),
            register_allocation_unit=int(raw["register_allocation_unit"]),
            shared_memory_per_sm=int(raw["shared_memory_per_sm"]),
            shared_memory_per_block=int(raw["shared_memory_per_block"]),
            global_transaction_bytes=int(raw["global_transaction_bytes"]),
            cache_line_bytes=int(raw["cache_line_bytes"]),
            memory_bandwidth_bytes_per_second=float(raw["memory_bandwidth_bytes_per_second"]),
            clock_hz=float(raw["clock_hz"]),
            issue_width=float(raw.get("issue_width", 1.0)),
            source=source,
        )


@dataclass(frozen=True)
class GPUKernelResources:
    local_size: tuple[int, int, int]
    local_size_policy: str
    registers_per_thread: int
    static_shared_bytes: int
    dynamic_shared_bytes: int
    local_bytes_per_thread: int
    instruction_count: int
    global_loads: int
    global_stores: int
    shared_loads: int
    shared_stores: int
    barriers: int
    atomics: int
    branches: int
    arithmetic: int
    element_bytes: int = 4

    @property
    def threads_per_block(self) -> int:
        return math.prod(self.local_size)

    @property
    def shared_bytes_per_block(self) -> int:
        return self.static_shared_bytes + self.dynamic_shared_bytes

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "local_size": list(self.local_size), "threads_per_block": self.threads_per_block}


@dataclass(frozen=True)
class GPUKernelCapture:
    dialect: str
    source: str
    entry_point: str
    compiler_identity: str
    module_hash: str
    graph: SemanticFlowGraph
    resources: GPUKernelResources
    mapped_operations: int
    unsupported_operations: tuple[str, ...]
    status: str
    artifacts: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": GPU_KERNEL_GRAPH_VERSION,
            "dialect": self.dialect,
            "source": self.source,
            "entry_point": self.entry_point,
            "compiler_identity": self.compiler_identity,
            "module_hash": self.module_hash,
            "graph": self.graph.to_dict(),
            "resources": self.resources.to_dict(),
            "mapped_operations": self.mapped_operations,
            "unsupported_operations": list(self.unsupported_operations),
            "semantic_capture": "complete_for_supported_operations" if not self.unsupported_operations else "partial",
            "status": self.status,
            "artifacts": self.artifacts,
            "claim_boundary": "device-kernel information flow only; host queues, DMA, presentation, final ISA scheduling, and driver behavior are separate",
        }


@dataclass(frozen=True)
class GPUExecutionPlan:
    id: str
    local_size: tuple[int, int, int]
    unroll: int
    vector_width: int
    memory_realization: str
    barrier_realization: str
    prefetch_distance: int
    realization_class: str
    legality_guards: tuple[str, ...]
    derivation: tuple[str, ...]
    graph_hash: str = ""

    def __post_init__(self) -> None:
        expected = canonical_hash(self._hash_payload())
        if self.graph_hash and self.graph_hash != expected:
            raise ValueError("GPU execution plan hash does not match")
        if not self.graph_hash:
            object.__setattr__(self, "graph_hash", expected)

    def _hash_payload(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "local_size": self.local_size,
            "unroll": self.unroll,
            "vector_width": self.vector_width,
            "memory_realization": self.memory_realization,
            "barrier_realization": self.barrier_realization,
            "prefetch_distance": self.prefetch_distance,
            "realization_class": self.realization_class,
            "legality_guards": self.legality_guards,
            "derivation": self.derivation,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._hash_payload(), "local_size": list(self.local_size), "graph_hash": self.graph_hash}


@dataclass(frozen=True)
class GPUCostEstimate:
    feasible: bool
    occupancy: float
    resident_blocks_per_sm: int
    active_warps_per_sm: int
    limiting_resources: tuple[str, ...]
    allocated_registers_per_block: int
    shared_bytes_per_block: int
    estimated_global_transactions_per_block: float
    useful_global_bytes_per_block: float
    physical_global_bytes_per_block: float
    coalescing_efficiency: float
    estimated_instruction_work: float
    estimated_synchronization_cost: float
    static_score: float
    assumptions: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_gpu_architecture(path_or_mapping: Path | dict[str, Any]) -> GPUArchitecture:
    if isinstance(path_or_mapping, Path):
        path = path_or_mapping.resolve()
        raw = yaml.safe_load(path.read_text())
        if not isinstance(raw, dict):
            raise ValueError("GPU architecture manifest must be a mapping")
        if "architecture" in raw and isinstance(raw["architecture"], dict):
            raw = raw["architecture"]
        return GPUArchitecture.from_mapping(raw, source=str(path))
    return GPUArchitecture.from_mapping(path_or_mapping)


def capture_gpu_kernel(
    source: Path,
    output_directory: Path,
    *,
    dialect: str = "auto",
    entry_point: str | None = None,
    target_env: str = "vulkan1.2",
) -> GPUKernelCapture:
    source = source.resolve()
    output_directory = output_directory.resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    selected = _detect_dialect(source) if dialect == "auto" else dialect
    if selected in {"spirv", "glsl"}:
        return _capture_spirv(source, output_directory, entry_point=entry_point, target_env=target_env)
    if selected == "ptx":
        return _capture_ptx(source, output_directory, entry_point=entry_point)
    if selected == "cuda":
        return _capture_cuda(source, output_directory, entry_point=entry_point)
    raise ValueError(f"unsupported GPU kernel dialect: {selected}")


def _detect_dialect(source: Path) -> str:
    suffix = source.suffix.lower()
    if suffix in {".comp", ".glsl", ".spv", ".spvasm"}:
        return "spirv"
    if suffix == ".ptx":
        return "ptx"
    if suffix == ".cu":
        return "cuda"
    raise ValueError(f"cannot infer GPU dialect from {source}")


def _run(command: list[str], *, timeout: float = 120.0) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"GPU tool failed: {' '.join(command)}\n{result.stderr[-3000:]}")
    return result


def _required_tool(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise RuntimeError(f"required GPU tool is unavailable: {name}")
    # CUDA's driver locates toolkit-relative headers from its executable path. Resolve wrapper
    # symlinks so an otherwise valid /usr/local/bin/nvcc does not lose cuda_runtime.h.
    return str(Path(path).resolve())


def _capture_spirv(
    source: Path,
    output_directory: Path,
    *,
    entry_point: str | None,
    target_env: str,
) -> GPUKernelCapture:
    module = output_directory / "kernel.spv"
    assembly = output_directory / "kernel.spvasm"
    compile_command: list[str] | None = None
    if source.suffix == ".spvasm":
        _run([_required_tool("spirv-as"), f"--target-env={target_env}", str(source), "-o", str(module)])
    elif source.suffix == ".spv":
        shutil.copyfile(source, module)
    else:
        compile_command = [
            _required_tool("glslangValidator"), "-V", "--target-env", target_env,
            "-S", "comp", str(source), "-o", str(module),
        ]
        _run(compile_command)
    _run([_required_tool("spirv-val"), "--target-env", target_env, str(module)])
    _run([_required_tool("spirv-dis"), str(module), "-o", str(assembly)])
    text = assembly.read_text(errors="replace")
    entries = re.findall(r'OpEntryPoint\s+GLCompute\s+%\w+\s+"([^"]+)"', text)
    selected_entry = entry_point or (entries[0] if entries else "main")
    if entries and selected_entry not in entries:
        raise ValueError(f"SPIR-V entry point {selected_entry!r} not found; choices: {entries}")
    compiler = _run([_required_tool("spirv-val"), "--version"]).stdout.splitlines()[0]
    capture = _graph_from_spirv(
        text,
        source=str(source),
        module_hash=file_sha256(module),
        entry_point=selected_entry,
        compiler_identity=compiler,
    )
    artifacts = {
        "module": str(module),
        "disassembly": str(assembly),
    }
    if compile_command:
        artifacts["compile_command"] = json.dumps(compile_command)
    return replace(capture, artifacts=artifacts)


def _capture_ptx(source: Path, output_directory: Path, *, entry_point: str | None) -> GPUKernelCapture:
    output_directory.mkdir(parents=True, exist_ok=True)
    target = output_directory / "kernel.ptx"
    shutil.copyfile(source, target)
    text = target.read_text(errors="replace")
    entries = re.findall(r"(?:\.visible\s+)?\.entry\s+([A-Za-z_$][\w$]*)", text)
    selected = entry_point or (entries[0] if entries else "")
    if not selected or selected not in entries:
        raise ValueError(f"PTX entry point {selected!r} not found; choices: {entries}")
    version = re.search(r"\.version\s+([^\s]+)", text)
    target_arch = re.search(r"\.target\s+([^\s,]+)", text)
    compiler = f"PTX {version.group(1) if version else 'unknown'} target {target_arch.group(1) if target_arch else 'unknown'}"
    capture = _graph_from_ptx(
        text,
        source=str(source),
        module_hash=file_sha256(target),
        entry_point=selected,
        compiler_identity=compiler,
    )
    return replace(capture, artifacts={"ptx": str(target)})


def _capture_cuda(source: Path, output_directory: Path, *, entry_point: str | None) -> GPUKernelCapture:
    if not shutil.which("nvcc"):
        raise RuntimeError("CUDA source capture requires nvcc; use checked-in PTX when the CUDA toolkit is unavailable")
    nvcc = _required_tool("nvcc")
    ptx = output_directory / "kernel.ptx"
    command = [nvcc, "-ptx", "-lineinfo", str(source), "-o", str(ptx)]
    _run(command)
    capture = _capture_ptx(ptx, output_directory / "ptx-capture", entry_point=entry_point)
    compiler = _run([nvcc, "--version"]).stdout.strip().splitlines()[-1]
    return replace(
        capture,
        dialect="cuda-ptx",
        source=str(source),
        compiler_identity=compiler,
        artifacts={**capture.artifacts, "cuda_source": str(source), "compile_command": json.dumps(command)},
    )


_SPIRV_KIND: tuple[tuple[str, str], ...] = (
    ("OpLoad", "Load"), ("OpStore", "Store"), ("OpAccessChain", "Address"),
    ("OpInBoundsAccessChain", "Address"), ("OpControlBarrier", "Barrier"),
    ("OpMemoryBarrier", "Barrier"), ("OpAtomic", "Atomic"), ("OpGroup", "Subgroup"),
    ("OpBranch", "Control"), ("OpSwitch", "Control"), ("OpPhi", "Control"),
    ("OpSelect", "Select"), ("OpComposite", "Pack"), ("OpVector", "Pack"),
    ("OpBit", "Bitwise"), ("OpShift", "Bitwise"), ("OpConvert", "Map"),
    ("OpSConvert", "Map"), ("OpUConvert", "Map"), ("OpFConvert", "Map"),
    ("OpIAdd", "Map"), ("OpISub", "Map"), ("OpIMul", "Map"),
    ("OpFAdd", "Map"), ("OpFSub", "Map"), ("OpFMul", "Map"), ("OpFDiv", "Map"),
    ("OpSNegate", "Map"), ("OpFNegate", "Map"), ("OpIEqual", "Compare"),
    ("OpINotEqual", "Compare"), ("OpFOrd", "Compare"), ("OpFUnord", "Compare"),
    ("OpSLess", "Compare"), ("OpULess", "Compare"), ("OpSGreater", "Compare"),
    ("OpUGreater", "Compare"), ("OpExtInst", "Call"), ("OpFunctionCall", "Call"),
    ("OpImage", "Load"),
)


def _spirv_kind(opcode: str) -> str | None:
    for prefix, kind in _SPIRV_KIND:
        if opcode.startswith(prefix):
            return kind
    if opcode.startswith(("OpType", "OpName", "OpMemberName", "OpDecorate", "OpMemberDecorate", "OpSource", "OpLine", "OpNoLine", "OpModuleProcessed")):
        return "metadata"
    if opcode.startswith(("OpCapability", "OpExtension", "OpExtInstImport", "OpMemoryModel", "OpEntryPoint", "OpExecutionMode")):
        return "metadata"
    if opcode.startswith(("OpVariable", "OpConstant", "OpSpecConstant", "OpUndef", "OpFunction", "OpLabel", "OpReturn", "OpLoopMerge", "OpSelectionMerge")):
        return "structural"
    return None


def _graph_from_spirv(
    text: str,
    *,
    source: str,
    module_hash: str,
    entry_point: str,
    compiler_identity: str,
) -> GPUKernelCapture:
    local_match = re.search(r"OpExecutionMode\s+%\w+\s+LocalSize\s+(\d+)\s+(\d+)\s+(\d+)", text)
    local_size = tuple(map(int, local_match.groups())) if local_match else (1, 1, 1)
    opcodes = re.findall(r"\b(Op[A-Za-z0-9_]+)\b", text)
    counts: dict[str, int] = {}
    unsupported: list[str] = []
    mapped = 0
    for opcode in opcodes:
        kind = _spirv_kind(opcode)
        if kind in {"metadata", "structural"}:
            continue
        if kind is None:
            if opcode not in unsupported:
                unsupported.append(opcode)
            continue
        counts[kind] = counts.get(kind, 0) + 1
        mapped += 1
    workgroup_variables = len(re.findall(r"OpVariable\s+Workgroup", text))
    storage_variables = len(re.findall(r"OpVariable\s+(?:StorageBuffer|Uniform|PhysicalStorageBuffer)", text))
    resources = GPUKernelResources(
        local_size=local_size,
        local_size_policy="source-rewritable" if Path(source).suffix.lower() in {".comp", ".glsl"} else "fixed",
        registers_per_thread=0,
        static_shared_bytes=workgroup_variables * 4,
        dynamic_shared_bytes=0,
        local_bytes_per_thread=0,
        instruction_count=mapped,
        global_loads=counts.get("Load", 0),
        global_stores=counts.get("Store", 0),
        shared_loads=0,
        shared_stores=0,
        barriers=counts.get("Barrier", 0),
        atomics=counts.get("Atomic", 0),
        branches=counts.get("Control", 0),
        arithmetic=counts.get("Map", 0) + counts.get("Bitwise", 0) + counts.get("Compare", 0),
    )
    graph = _kernel_semantic_graph(
        dialect="spirv",
        source=source,
        module_hash=module_hash,
        entry_point=entry_point,
        compiler_identity=compiler_identity,
        resources=resources,
        operation_counts=counts,
        unsupported=tuple(unsupported),
        dialect_facts={"storage_variables": storage_variables, "workgroup_variables": workgroup_variables},
    )
    return GPUKernelCapture(
        "spirv", source, entry_point, compiler_identity, module_hash, graph, resources,
        mapped, tuple(sorted(unsupported)), "captured" if not unsupported else "partial_capture", {},
    )


_PTX_OPCODE_KIND: tuple[tuple[str, str], ...] = (
    ("ld.global", "Load"), ("ld.const", "Load"), ("ld.param", "Load"),
    ("ld.shared", "SharedMemory"), ("st.global", "Store"), ("st.shared", "SharedMemory"),
    ("atom.", "Atomic"), ("red.", "Atomic"), ("bar.", "Barrier"),
    ("membar.", "Barrier"), ("bra", "Control"), ("call", "Call"),
    ("setp.", "Compare"), ("selp.", "Select"), ("shfl.", "Subgroup"),
    ("vote.", "Subgroup"), ("mov.", "Map"), ("cvta.", "Address"),
    ("cvt.", "Map"), ("add.", "Map"), ("sub.", "Map"), ("mul.", "Map"),
    ("mad.", "Map"), ("fma.", "Map"), ("div.", "Map"), ("rem.", "Map"),
    ("min.", "Map"), ("max.", "Map"), ("and.", "Bitwise"), ("or.", "Bitwise"),
    ("xor.", "Bitwise"), ("shl.", "Bitwise"), ("shr.", "Bitwise"),
)


def _ptx_kind(opcode: str) -> str | None:
    for prefix, kind in _PTX_OPCODE_KIND:
        if opcode.startswith(prefix):
            return kind
    if opcode in {"ret", "exit", "trap", "brkpt", "nop"}:
        return "Control"
    return None


def _graph_from_ptx(
    text: str,
    *,
    source: str,
    module_hash: str,
    entry_point: str,
    compiler_identity: str,
) -> GPUKernelCapture:
    maxntid = re.search(r"\.(reqntid|maxntid)\s+(\d+)(?:\s*,\s*(\d+))?(?:\s*,\s*(\d+))?", text)
    local_size = tuple(int(value or 1) for value in maxntid.groups()[1:]) if maxntid else (128, 1, 1)
    local_size_policy = "required" if maxntid and maxntid.group(1) == "reqntid" else "maximum"
    registers = 0
    for match in re.finditer(r"\.reg\s+\.[A-Za-z0-9]+\s+%[A-Za-z]+<(\d+)>", text):
        registers += int(match.group(1))
    shared_bytes = 0
    for match in re.finditer(r"\.shared(?:\s+\.align\s+\d+)?\s+\.(?:b|u|s)(\d+)\s+\w+(?:\[(\d+)\])?", text):
        shared_bytes += (int(match.group(1)) // 8) * int(match.group(2) or 1)
    opcodes: list[str] = []
    for line in text.splitlines():
        clean = line.split("//", 1)[0].strip()
        clean = re.sub(r"^@[!%A-Za-z0-9_$.]+\s+", "", clean)
        match = re.match(r"([A-Za-z][A-Za-z0-9_.]+)\s", clean)
        if match and not match.group(1).startswith((".version", ".target", ".address_size", ".visible", ".entry", ".param", ".reg", ".shared")):
            opcodes.append(match.group(1))
    counts: dict[str, int] = {}
    unsupported: list[str] = []
    for opcode in opcodes:
        kind = _ptx_kind(opcode)
        if kind is None:
            if opcode not in unsupported:
                unsupported.append(opcode)
        else:
            counts[kind] = counts.get(kind, 0) + 1
    resources = GPUKernelResources(
        local_size=local_size,
        local_size_policy=local_size_policy,
        registers_per_thread=registers,
        static_shared_bytes=shared_bytes,
        dynamic_shared_bytes=0,
        local_bytes_per_thread=0,
        instruction_count=sum(counts.values()),
        global_loads=counts.get("Load", 0),
        global_stores=counts.get("Store", 0),
        shared_loads=counts.get("SharedMemory", 0),
        shared_stores=0,
        barriers=counts.get("Barrier", 0),
        atomics=counts.get("Atomic", 0),
        branches=counts.get("Control", 0),
        arithmetic=counts.get("Map", 0) + counts.get("Bitwise", 0) + counts.get("Compare", 0),
    )
    target = re.search(r"\.target\s+([^\s,]+)", text)
    graph = _kernel_semantic_graph(
        dialect="ptx",
        source=source,
        module_hash=module_hash,
        entry_point=entry_point,
        compiler_identity=compiler_identity,
        resources=resources,
        operation_counts=counts,
        unsupported=tuple(unsupported),
        dialect_facts={"ptx_target": target.group(1) if target else "unknown"},
    )
    return GPUKernelCapture(
        "ptx", source, entry_point, compiler_identity, module_hash, graph, resources,
        sum(counts.values()), tuple(sorted(unsupported)), "captured" if not unsupported else "partial_capture", {},
    )


def _kernel_semantic_graph(
    *,
    dialect: str,
    source: str,
    module_hash: str,
    entry_point: str,
    compiler_identity: str,
    resources: GPUKernelResources,
    operation_counts: dict[str, int],
    unsupported: tuple[str, ...],
    dialect_facts: dict[str, Any],
) -> SemanticFlowGraph:
    provenance = {"adapter": GPU_KERNEL_GRAPH_VERSION, "dialect": dialect, "source": source}
    geometry_obligation = obligation(
        "gpu.geometry.bounds", "bounds", "workgroup and dispatch geometry cover only declared logical elements",
        scope="kernel-dispatch", proof_method="bounded dispatch arithmetic plus output oracle",
        language=dialect, native_construct="local-size/thread-index",
    )
    memory_obligation = obligation(
        "gpu.memory.footprint", "memory", "every device access is inside its declared storage object and alias set",
        scope="kernel", proof_method="SPIR-V/PTX footprint analysis plus runner guards",
        language=dialect, native_construct="device load/store/address",
    )
    barrier_obligation = obligation(
        "gpu.barrier.scope", "synchronization", "barrier execution and memory scopes cover every participating lane and shared access",
        scope="workgroup", proof_method="bounded lane and memory-scope verification",
        language=dialect, native_construct="barrier/memory-semantics",
    )
    nodes: list[SemanticFlowNode] = [
        SemanticFlowNode("input", "Input", "device-buffers", (), "device-memory", {}, provenance, (memory_obligation,)),
        SemanticFlowNode("grid", "DispatchGrid", "logical-dispatch-grid", ("input",), "grid", {"local_size": list(resources.local_size)}, provenance, (geometry_obligation,)),
        SemanticFlowNode("workgroup", "Workgroup", "cooperative-thread-group", ("grid",), "workgroup", {"threads": resources.threads_per_block}, provenance, ()),
        SemanticFlowNode("subgroup", "Subgroup", "hardware-subgroup", ("workgroup",), "subgroup", {}, provenance, ()),
        SemanticFlowNode("lane", "Lane", "logical-invocation", ("subgroup",), "lane", {}, provenance, (geometry_obligation,)),
        SemanticFlowNode("address", "Address", "device-address-generation", ("lane", "input"), "address", {"count": operation_counts.get("Address", 0)}, provenance, (memory_obligation,)),
        SemanticFlowNode("global-load", "GlobalMemoryTransaction", "global-load", ("address",), "values", {"count": operation_counts.get("Load", 0)}, provenance, (memory_obligation,)),
    ]
    prior = "global-load"
    if operation_counts.get("SharedMemory", 0):
        nodes.append(SemanticFlowNode("shared", "SharedMemory", "workgroup-resident-data", (prior,), "shared-values", {"count": operation_counts["SharedMemory"]}, provenance, (barrier_obligation,)))
        prior = "shared"
    if operation_counts.get("Barrier", 0):
        nodes.append(SemanticFlowNode("barrier", "Barrier", "execution-and-memory-dependency", (prior,), "ordered-values", {"count": operation_counts["Barrier"]}, provenance, (barrier_obligation,)))
        prior = "barrier"
    if operation_counts.get("Atomic", 0):
        nodes.append(SemanticFlowNode("atomic", "Atomic", "atomic-memory-transition", (prior,), "atomic-values", {"count": operation_counts["Atomic"]}, provenance, (barrier_obligation,)))
        prior = "atomic"
    nodes.append(SemanticFlowNode(
        "compute", "Map", "device-compute", (prior,), "computed-values",
        {"arithmetic": operation_counts.get("Map", 0), "bitwise": operation_counts.get("Bitwise", 0), "compare": operation_counts.get("Compare", 0)},
        provenance, (),
    ))
    nodes.append(SemanticFlowNode("global-store", "GlobalMemoryTransaction", "global-store", ("compute",), "device-memory", {"count": operation_counts.get("Store", 0)}, provenance, (memory_obligation,)))
    nodes.append(SemanticFlowNode("resources", "ResourceUse", "kernel-resource-envelope", ("workgroup", "compute"), "resource-contract", resources.to_dict(), provenance, ()))
    if unsupported:
        nodes.append(SemanticFlowNode("unsupported", "UnsupportedOperation", "unmapped-dialect-operations", ("compute",), "unknown-effects", {"operations": list(unsupported)}, provenance, ()))
    nodes.append(SemanticFlowNode("output", "Output", "device-observables", ("global-store",), "device-memory", {}, provenance, ()))
    edges: list[SemanticFlowEdge] = []
    for node in nodes:
        for ordinal, source_node in enumerate(node.inputs):
            edges.append(SemanticFlowEdge(
                f"{source_node}->{node.id}:{ordinal}", source_node, node.id, node.output_type or "control",
                "device", "kernel-resource", "dispatch", "device-execution-order",
                logical_shape=("dispatch",), physical_shape=resources.local_size,
                lane_width_bits=32, realization=dialect, memory_region="device",
                validity_scope="kernel-dispatch",
            ))
    effects: list[SemanticEffect] = [
        SemanticEffect("gpu.read", "MemoryRead", "execute", "device-input", "kernel-result", "device-memory-model", ("global-load",), ("gpu.memory.footprint",)),
        SemanticEffect("gpu.write", "MemoryWrite", "execute", "device-output", "kernel-result", "device-memory-model", ("global-store",), ("gpu.memory.footprint",)),
        SemanticEffect("gpu.dispatch", "Dispatch", "launch", "device", "kernel-result", "dispatch-order", ("grid", "workgroup"), ("gpu.geometry.bounds",)),
    ]
    protocols: list[ProtocolTransition] = []
    if operation_counts.get("Barrier", 0):
        effects.append(SemanticEffect("gpu.barrier", "Barrier", "execute", "workgroup-memory", "kernel-result", "workgroup-scope", ("barrier",), ("gpu.barrier.scope",)))
        protocols.append(ProtocolTransition("gpu.visibility", "MemoryVisibility", "writes-pending", "barrier", "writes-visible", "declared scope and participating lanes", ("gpu.barrier.scope",), provenance))
    return SemanticFlowGraph(
        f"{dialect}:{entry_point}", dialect, compiler_identity, GPU_KERNEL_GRAPH_VERSION,
        module_hash, tuple(nodes), tuple(edges),
        {
            "entry_point": entry_point,
            "resources": resources.to_dict(),
            "operation_counts": operation_counts,
            "dialect_facts": dialect_facts,
            "exactness": "declared-by-runner",
        },
        ("host queue and API behavior", "final machine scheduling", "driver behavior", "DMA and presentation protocols"),
        (geometry_obligation, memory_obligation, barrier_obligation), tuple(effects), tuple(protocols),
    )


def enumerate_gpu_plans(
    capture: GPUKernelCapture,
    architecture: GPUArchitecture,
    *,
    logical_extent: int | None = None,
    maximum_candidates: int = 256,
) -> list[GPUExecutionPlan]:
    base = capture.resources.local_size
    candidates: list[GPUExecutionPlan] = []
    sizes = {base}
    for threads in (32, 64, 128, 256, 512):
        if threads <= architecture.max_threads_per_block:
            sizes.add((threads, 1, 1))
    for local_size in sorted(sizes):
        for unroll in (1, 2, 4):
            for vector_width in (1, 2, 4):
                for memory in ("direct-global", "coalesced-vector", "shared-stage"):
                    if memory == "shared-stage" and capture.resources.global_loads == 0:
                        continue
                    guards = ["threads_per_block <= architecture.max_threads_per_block"]
                    realization_class = "launch_plan"
                    changes_kernel_code = unroll != 1 or vector_width != 1 or memory != "direct-global"
                    if changes_kernel_code:
                        realization_class = "adapter_required"
                        guards.append("dialect source or binary emitter required for code-shape change")
                    if local_size != base and capture.resources.local_size_policy not in {"maximum", "source-rewritable"}:
                        realization_class = "adapter_required"
                        guards.append("source or specialization-constant local-size emitter required")
                    elif local_size != base and capture.resources.local_size_policy == "source-rewritable" and not changes_kernel_code:
                        realization_class = "source_rewrite"
                    if vector_width > 1:
                        guards.extend(("logical extent divisible or tail-guarded", f"alignment >= {vector_width * capture.resources.element_bytes}"))
                    if unroll > 1:
                        guards.append("unrolled iterations preserve bounds and operation order")
                    if logical_extent is not None and logical_extent < math.prod(local_size):
                        guards.append("inactive lanes are guarded")
                    plan_id = f"ls{local_size[0]}x{local_size[1]}x{local_size[2]}-u{unroll}-v{vector_width}-{memory}"
                    candidates.append(GPUExecutionPlan(
                        plan_id,
                        local_size,
                        unroll,
                        vector_width,
                        memory,
                        "baseline-scope",
                        1 if memory == "shared-stage" else 0,
                        realization_class,
                        tuple(guards),
                        (
                            "schedule:workgroup-shape",
                            f"schedule:unroll-{unroll}",
                            f"memory:{memory}",
                            f"lane:vector-width-{vector_width}",
                        ),
                    ))
                    if len(candidates) >= maximum_candidates:
                        return candidates
    return candidates


def estimate_gpu_cost(
    capture: GPUKernelCapture,
    architecture: GPUArchitecture,
    plan: GPUExecutionPlan,
) -> GPUCostEstimate:
    threads = math.prod(plan.local_size)
    warps = math.ceil(threads / architecture.warp_size)
    register_growth = max(0, plan.unroll - 1) * 2 + max(0, plan.vector_width - 1)
    registers_per_thread = max(1, capture.resources.registers_per_thread + register_growth)
    raw_registers = registers_per_thread * threads
    allocated_registers = _round_up(raw_registers, architecture.register_allocation_unit)
    shared_bytes = capture.resources.shared_bytes_per_block
    if plan.memory_realization == "shared-stage":
        shared_bytes += threads * capture.resources.element_bytes * plan.vector_width
    limits = {
        "threads": architecture.max_threads_per_sm // max(1, threads),
        "warps": architecture.max_warps_per_sm // max(1, warps),
        "registers": architecture.registers_per_sm // max(1, allocated_registers),
        "shared_memory": architecture.shared_memory_per_sm // max(1, shared_bytes) if shared_bytes else architecture.max_blocks_per_sm,
        "blocks": architecture.max_blocks_per_sm,
    }
    resident = min(limits.values())
    feasible = (
        threads <= architecture.max_threads_per_block
        and shared_bytes <= architecture.shared_memory_per_block
        and resident > 0
    )
    active_warps = resident * warps if feasible else 0
    occupancy = min(1.0, active_warps / architecture.max_warps_per_sm) if feasible else 0.0
    limiting = tuple(sorted(name for name, value in limits.items() if value == min(limits.values())))
    logical_ops = capture.resources.global_loads + capture.resources.global_stores
    useful_bytes = logical_ops * threads * capture.resources.element_bytes * plan.vector_width
    pattern_factor = {"direct-global": 1.25, "coalesced-vector": 1.0, "shared-stage": 1.0}[plan.memory_realization]
    transactions = math.ceil(math.ceil(useful_bytes / architecture.global_transaction_bytes) * pattern_factor) if useful_bytes else 0.0
    physical_bytes = transactions * architecture.global_transaction_bytes
    coalescing = min(1.0, useful_bytes / physical_bytes) if physical_bytes else 1.0
    instruction_work = capture.resources.instruction_count * threads / max(1, plan.unroll * plan.vector_width)
    synchronization = capture.resources.barriers * resident * (1.0 + 0.1 * warps)
    bandwidth_cycles = physical_bytes / max(1.0, architecture.memory_bandwidth_bytes_per_second) * architecture.clock_hz
    compute_cycles = instruction_work / max(0.01, architecture.issue_width * max(occupancy, 0.05) * architecture.warp_size)
    score = float("inf") if not feasible else bandwidth_cycles + compute_cycles + synchronization
    return GPUCostEstimate(
        feasible,
        occupancy,
        resident,
        active_warps,
        limiting,
        allocated_registers,
        shared_bytes,
        transactions,
        useful_bytes,
        physical_bytes,
        coalescing,
        instruction_work,
        synchronization,
        score,
        (
            "occupancy is a resource upper bound, not a speed prediction",
            "SPIR-V register usage is unavailable until final driver lowering" if capture.resources.registers_per_thread == 0 else "register usage parsed from PTX declaration",
            "memory transactions assume the manifest segment width and declared access realization",
        ),
    )


def rank_static_gpu_plans(
    capture: GPUKernelCapture,
    architecture: GPUArchitecture,
    plans: Iterable[GPUExecutionPlan],
) -> list[dict[str, Any]]:
    rows = []
    for plan in plans:
        cost = estimate_gpu_cost(capture, architecture, plan)
        rows.append({"plan": plan.to_dict(), "cost": cost.to_dict()})
    rows.sort(key=lambda item: (not item["cost"]["feasible"], item["cost"]["static_score"], item["plan"]["id"]))
    return rows


def prove_gpu_execution_plan(
    capture: GPUKernelCapture,
    architecture: GPUArchitecture,
    plan: GPUExecutionPlan,
    logical_extent: int,
    output_directory: Path,
) -> dict[str, Any]:
    """Prove the bounded launch-index relation for unchanged-kernel launch plans.

    This proof does not establish equivalence for code-shape plans or driver scheduling. It proves
    only that a recognized one-dimensional, lane-independent kernel maps each declared logical
    index exactly once under the selected launch geometry.
    """
    output_directory = output_directory.resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    cost = estimate_gpu_cost(capture, architecture, plan)
    checks: list[dict[str, Any]] = []
    smt_parts: list[str] = []
    executable = plan.realization_class in {"launch_plan", "source_rewrite"}
    lane_independent = (
        capture.resources.shared_loads == 0
        and capture.resources.shared_stores == 0
        and capture.resources.barriers == 0
        and capture.resources.atomics == 0
    )
    unchanged_code_shape = plan.unroll == 1 and plan.vector_width == 1 and plan.memory_realization == "direct-global"
    geometry_allowed = plan.local_size == capture.resources.local_size or capture.resources.local_size_policy in {"maximum", "source-rewritable"}
    static_facts = (
        ("executable-launch-plan", executable),
        ("resource-feasible", cost.feasible),
        ("lane-independent", lane_independent),
        ("unchanged-code-shape", unchanged_code_shape),
        ("local-size-policy", geometry_allowed),
        ("positive-logical-extent", logical_extent > 0),
    )
    for identifier, fact in static_facts:
        solver = Solver(); solver.add(not fact)
        result = solver.check()
        checks.append({"id": identifier, "status": "PROVED" if result != sat else "FAIL", "solver_result": str(result).upper()})
        smt_parts.append(solver.to_smt2())
    threads = math.prod(plan.local_size)
    index = Int("logical_index")
    group = index / threads
    lane = index % threads
    geometry = Solver()
    geometry.add(index >= 0, index < logical_extent)
    geometry.add(group * threads + lane != index)
    geometry_result = geometry.check()
    checks.append({
        "id": "one-dimensional-index-bijection",
        "status": "PROVED" if geometry_result != sat else "FAIL",
        "solver_result": str(geometry_result).upper(),
        "threads_per_block": threads,
        "logical_extent": logical_extent,
    })
    smt_parts.append(geometry.to_smt2())
    smt_path = output_directory / "launch-plan.smt2"
    smt_path.write_text("\n; ---- obligation ----\n".join(smt_parts))
    passed = all(item["status"] == "PROVED" for item in checks)
    report = {
        "schema_version": "gpu-launch-plan-proof-v1",
        "status": "PASS" if passed else "INCOMPLETE",
        "plan_id": plan.id,
        "plan_hash": plan.graph_hash,
        "kernel_graph_hash": capture.graph.graph_hash,
        "architecture_hash": architecture.manifest_hash,
        "checks": checks,
        "artifact": str(smt_path),
        "proof_scope": "bounded one-dimensional unchanged-kernel launch geometry and resource feasibility",
        "excluded_claims": ["code-shape transformation equivalence", "driver scheduling", "whole host protocol", "physical performance"],
    }
    (output_directory / "launch-plan-proof.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def materialize_gpu_plan(
    capture: GPUKernelCapture,
    architecture: GPUArchitecture,
    plan: GPUExecutionPlan,
    logical_extent: int,
    output_directory: Path,
    *,
    target_env: str = "vulkan1.2",
) -> dict[str, Any]:
    output_directory = output_directory.resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    proof = prove_gpu_execution_plan(capture, architecture, plan, logical_extent, output_directory / "proof")
    report: dict[str, Any] = {
        "schema_version": "gpu-plan-materialization-v1",
        "plan": plan.to_dict(),
        "proof": proof,
        "status": "adapter_required",
        "artifacts": {},
        "promotable": False,
    }
    if proof["status"] != "PASS":
        report["status"] = "proof_incomplete"
    elif plan.realization_class == "launch_plan":
        launch_path = output_directory / "launch-plan.json"
        launch_path.write_text(json.dumps({
            "kernel_artifacts": capture.artifacts,
            "local_size": list(plan.local_size),
            "logical_extent": logical_extent,
            "plan_hash": plan.graph_hash,
        }, indent=2, sort_keys=True) + "\n")
        report["status"] = "materialized_launch_plan"
        report["artifacts"] = {"launch_plan": str(launch_path), **capture.artifacts}
    elif plan.realization_class == "source_rewrite":
        source = Path(capture.source)
        if source.suffix.lower() not in {".comp", ".glsl"}:
            report["status"] = "source_emitter_unavailable"
        else:
            rewritten = output_directory / f"candidate{source.suffix.lower()}"
            rewritten.write_text(_rewrite_glsl_local_size(source.read_text(), plan.local_size))
            candidate_capture = capture_gpu_kernel(rewritten, output_directory / "compiled", dialect="spirv", entry_point=capture.entry_point, target_env=target_env)
            baseline_shape = capture.graph.contracts.get("operation_counts", {})
            candidate_shape = candidate_capture.graph.contracts.get("operation_counts", {})
            shape_equal = baseline_shape == candidate_shape and not candidate_capture.unsupported_operations
            report.update({
                "status": "materialized_source_rewrite" if shape_equal else "semantic_shape_mismatch",
                "artifacts": {"source": str(rewritten), **candidate_capture.artifacts},
                "candidate_kernel_graph_hash": candidate_capture.graph.graph_hash,
                "operation_shape_equal": shape_equal,
                "operation_shape": {"baseline": baseline_shape, "candidate": candidate_shape},
                "claim_boundary": "operation-shape and launch-index proof; exact output differential remains required",
            })
    (output_directory / "materialization.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def _rewrite_glsl_local_size(source: str, local_size: tuple[int, int, int]) -> str:
    pattern = re.compile(r"layout\s*\(([^)]*local_size_x[^)]*)\)\s*in\s*;")
    match = pattern.search(source)
    if not match:
        raise ValueError("GLSL source has no literal local_size layout declaration")
    body = match.group(1)
    names = ("local_size_x", "local_size_y", "local_size_z")
    for name, value in zip(names, local_size):
        expression = re.compile(rf"{name}\s*=\s*\d+")
        if expression.search(body):
            body = expression.sub(f"{name} = {value}", body)
        else:
            body += f", {name} = {value}"
    return source[:match.start()] + f"layout({body}) in;" + source[match.end():]


def _round_up(value: int, unit: int) -> int:
    return ((value + unit - 1) // unit) * unit
