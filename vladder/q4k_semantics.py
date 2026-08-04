from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
import struct
from typing import Any


QK_K = 256
K_SCALE_SIZE = 12
Q4K_BLOCK_BYTES = 144
Q8K_BLOCK_BYTES = 292
Q4KX8_BLOCK_BYTES = 1152

Q4K_NODE_KINDS = {
    "Q4KBlockAddress", "Q4KNativeRepackLoad", "Q4KScaleMetadataLoad", "Q4KScaleDecode",
    "Q4KMinDecode", "Q4KQuantValueLoad", "Q4KNibbleExtract", "Q4KSubBlockMap",
    "Q8KBlockAddress", "Q8KValueLoad", "Q8KScaleLoad", "Q8KBlockReuse", "IntegerDotPartial",
    "MinimumCorrection", "ScaleProduct", "FloatPartialAccumulate", "AccumulatorBank",
    "AccumulatorReduce", "InputBlockLoop", "OutputRowGroupLoop", "TokenTileLoop",
    "SiblingProjectionLoop", "ThreadPartition", "TailDispatch", "FloatOutputStore",
    "ProjectionResultTile", "ConsumerBoundary",
}


@dataclass(frozen=True)
class Q4KBlock:
    d_bits: int
    dmin_bits: int
    scales: bytes
    qs: bytes

    @property
    def d(self) -> float:
        return _half_from_bits(self.d_bits)

    @property
    def dmin(self) -> float:
        return _half_from_bits(self.dmin_bits)

    def to_bytes(self) -> bytes:
        return struct.pack("<HH", self.d_bits, self.dmin_bits) + self.scales + self.qs


@dataclass(frozen=True)
class Q8KBlock:
    d: float
    qs: tuple[int, ...]
    bsums: tuple[int, ...]

    def to_bytes(self) -> bytes:
        return struct.pack("<f", self.d) + struct.pack("<256b", *self.qs) + struct.pack("<16h", *self.bsums)


@dataclass(frozen=True)
class Q4KX8Block:
    d_bits: tuple[int, ...]
    dmin_bits: tuple[int, ...]
    scales: bytes
    qs: bytes

    def to_bytes(self) -> bytes:
        return struct.pack("<8H", *self.d_bits) + struct.pack("<8H", *self.dmin_bits) + self.scales + self.qs


@dataclass(frozen=True)
class Q4KGraphNode:
    id: str
    kind: str
    provenance_class: str
    provenance: str
    attrs: dict[str, Any]


@dataclass(frozen=True)
class Q4KGraphEdge:
    id: str
    src: str
    dst: str
    scalar_or_vector_type: str
    logical_shape: tuple[int, ...]
    packed_shape: tuple[int, ...]
    source_block_index: str
    destination_row_range: str
    byte_offset: str
    alignment: int
    alias_set: str
    lifetime: str
    register_residency_eligible: bool
    cache_reuse_expectation: int
    numerical_class: str
    exactness_obligation: str
    owning_projection: str
    owning_token_lane: str


@dataclass(frozen=True)
class Q4KKernelGraph:
    schema_version: str
    id: str
    graph_hash: str
    active_path_manifest_hash: str
    nodes: tuple[Q4KGraphNode, ...]
    edges: tuple[Q4KGraphEdge, ...]
    contract: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_q4k_block(raw: bytes) -> Q4KBlock:
    if len(raw) != Q4K_BLOCK_BYTES:
        raise ValueError(f"Q4_K block must be {Q4K_BLOCK_BYTES} bytes")
    d_bits, dmin_bits = struct.unpack_from("<HH", raw)
    return Q4KBlock(d_bits, dmin_bits, raw[4:16], raw[16:])


def parse_q8k_block(raw: bytes) -> Q8KBlock:
    if len(raw) != Q8K_BLOCK_BYTES:
        raise ValueError(f"Q8_K block must be {Q8K_BLOCK_BYTES} bytes")
    d = struct.unpack_from("<f", raw)[0]
    qs = struct.unpack_from("<256b", raw, 4)
    bsums = struct.unpack_from("<16h", raw, 260)
    return Q8KBlock(d, qs, bsums)


def decode_scale_min(scales: bytes, index: int) -> tuple[int, int]:
    if len(scales) != K_SCALE_SIZE or not 0 <= index < 8:
        raise ValueError("Q4_K scale decode requires 12 bytes and index in [0,7]")
    if index < 4:
        return scales[index] & 63, scales[index + 4] & 63
    scale = (scales[index + 4] & 15) | ((scales[index - 4] >> 6) << 4)
    minimum = (scales[index + 4] >> 4) | ((scales[index] >> 6) << 4)
    return scale, minimum


def pack_scale_min(scales: list[int] | tuple[int, ...], minima: list[int] | tuple[int, ...]) -> bytes:
    if len(scales) != 8 or len(minima) != 8 or any(not 0 <= value < 64 for value in (*scales, *minima)):
        raise ValueError("Q4_K scales and minima must contain eight 6-bit values")
    output = bytearray(12)
    for index in range(4):
        output[index] = (scales[index] & 63) | (((scales[index + 4] >> 4) & 3) << 6)
        output[index + 4] = (minima[index] & 63) | (((minima[index + 4] >> 4) & 3) << 6)
        output[index + 8] = (scales[index + 4] & 15) | ((minima[index + 4] & 15) << 4)
    return bytes(output)


def q4k_quant_values(block: Q4KBlock) -> tuple[int, ...]:
    values: list[int] = []
    for group in range(4):
        chunk = block.qs[group * 32:(group + 1) * 32]
        values.extend(value & 15 for value in chunk)
        values.extend(value >> 4 for value in chunk)
    return tuple(values)


def dequantize_q4k(block: Q4KBlock) -> tuple[float, ...]:
    output: list[float] = []
    values = q4k_quant_values(block)
    for subblock in range(8):
        scale, minimum = decode_scale_min(block.scales, subblock)
        d = block.d * scale
        m = block.dmin * minimum
        output.extend(d * value - m for value in values[subblock * 32:(subblock + 1) * 32])
    return tuple(output)


def q4k_q8k_reference_dot(weight: Q4KBlock, activation: Q8KBlock) -> float:
    scales_minima = [decode_scale_min(weight.scales, index) for index in range(8)]
    values = q4k_quant_values(weight)
    integer_dot = 0
    minimum_correction = 0
    for index in range(QK_K):
        scale = scales_minima[index // 32][0]
        integer_dot += scale * values[index] * activation.qs[index]
    for index in range(16):
        minimum_correction += activation.bsums[index] * scales_minima[index // 2][1]
    return weight.d * activation.d * integer_dot - weight.dmin * activation.d * minimum_correction


def repack_q4k_x8(blocks: tuple[Q4KBlock, ...], interleave: int = 8) -> Q4KX8Block:
    if len(blocks) != 8 or interleave not in {4, 8}:
        raise ValueError("native Q4_Kx8 repack requires eight blocks and interleave 4 or 8")
    quant_output = bytearray(1024)
    chunk_count = 128 // interleave
    destination = 0
    for chunk in range(chunk_count):
        offset = chunk * interleave
        for block in blocks:
            quant_output[destination:destination + interleave] = block.qs[offset:offset + interleave]
            destination += interleave
    scale_output = bytearray()
    decoded = [[decode_scale_min(block.scales, index) for index in range(8)] for block in blocks]
    for subblock in range(8):
        scale_output.extend(pack_scale_min(
            [decoded[row][subblock][0] for row in range(8)],
            [decoded[row][subblock][1] for row in range(8)],
        ))
    return Q4KX8Block(
        tuple(block.d_bits for block in blocks), tuple(block.dmin_bits for block in blocks),
        bytes(scale_output), bytes(quant_output),
    )


def inverse_repack_q4k_x8(block: Q4KX8Block, interleave: int = 8) -> tuple[Q4KBlock, ...]:
    if len(block.scales) != 96 or len(block.qs) != 1024 or interleave not in {4, 8}:
        raise ValueError("invalid Q4_Kx8 block")
    row_quants = [bytearray(128) for _ in range(8)]
    source = 0
    for chunk in range(128 // interleave):
        offset = chunk * interleave
        for row in range(8):
            row_quants[row][offset:offset + interleave] = block.qs[source:source + interleave]
            source += interleave
    row_scales = [[0] * 8 for _ in range(8)]
    row_minima = [[0] * 8 for _ in range(8)]
    for subblock in range(8):
        packed = block.scales[subblock * 12:(subblock + 1) * 12]
        for row in range(8):
            row_scales[row][subblock], row_minima[row][subblock] = decode_scale_min(packed, row)
    return tuple(
        Q4KBlock(block.d_bits[row], block.dmin_bits[row], pack_scale_min(row_scales[row], row_minima[row]), bytes(row_quants[row]))
        for row in range(8)
    )


def verify_repack_bijection(blocks: tuple[Q4KBlock, ...], interleave: int = 8) -> dict[str, Any]:
    repacked = repack_q4k_x8(blocks, interleave)
    restored = inverse_repack_q4k_x8(repacked, interleave)
    source = b"".join(block.to_bytes() for block in blocks)
    inverse = b"".join(block.to_bytes() for block in restored)
    return {
        "status": "proved" if source == inverse else "failed",
        "source_sha256": hashlib.sha256(source).hexdigest(),
        "repacked_sha256": hashlib.sha256(repacked.to_bytes()).hexdigest(),
        "inverse_sha256": hashlib.sha256(inverse).hexdigest(),
        "block_count": len(blocks),
        "metadata_value_count": len(blocks) * 16,
        "packed_value_bytes": len(blocks) * 128,
        "padding_bytes": 0,
        "deterministic": repacked == repack_q4k_x8(blocks, interleave),
    }


def build_q4k_kernel_graph(active_manifest: dict[str, Any], *, graph_id: str = "q4k-8x8-gemv") -> Q4KKernelGraph:
    manifest_hash = hashlib.sha256(json.dumps(active_manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    node_specs = [
        ("weight_address", "Q4KBlockAddress", "baseline_source_expression", "forward_mul_mat_one_chunk"),
        ("repack_load", "Q4KNativeRepackLoad", "baseline_intrinsic", "ggml_gemv_q4_K_8x8_q8_K"),
        ("metadata_load", "Q4KScaleMetadataLoad", "baseline_intrinsic", "_mm_loadu_si128"),
        ("scale_decode", "Q4KScaleDecode", "baseline_source_expression", "kmask1/kmask2/kmask3"),
        ("min_decode", "Q4KMinDecode", "baseline_source_expression", "mins_and_scales"),
        ("quant_load", "Q4KQuantValueLoad", "baseline_intrinsic", "_mm256_loadu_si256"),
        ("nibble_extract", "Q4KNibbleExtract", "baseline_intrinsic", "_mm256_and_si256/_mm256_srli_epi16"),
        ("subblock_map", "Q4KSubBlockMap", "baseline_source_expression", "sb loop"),
        ("activation_address", "Q8KBlockAddress", "baseline_source_expression", "a_ptr_start"),
        ("activation_load", "Q8KValueLoad", "baseline_intrinsic", "_mm_loadu_si128"),
        ("activation_scale", "Q8KScaleLoad", "baseline_intrinsic", "_mm256_set1_ps"),
        ("activation_reuse", "Q8KBlockReuse", "baseline_source_expression", "lane replication"),
        ("integer_dot", "IntegerDotPartial", "baseline_intrinsic", "_mm256_maddubs_epi16"),
        ("minimum_correction", "MinimumCorrection", "baseline_intrinsic", "_mm256_madd_epi16"),
        ("scale_product", "ScaleProduct", "baseline_intrinsic", "_mm256_mul_ps"),
        ("float_accumulate", "FloatPartialAccumulate", "baseline_intrinsic", "_mm256_fmadd_ps"),
        ("accumulator", "AccumulatorBank", "baseline_source_expression", "acc_row/acc_min_rows"),
        ("reduce", "AccumulatorReduce", "baseline_intrinsic", "_mm256_sub_ps"),
        ("input_loop", "InputBlockLoop", "baseline_source_expression", "for b in nb"),
        ("row_loop", "OutputRowGroupLoop", "baseline_source_expression", "for x in nc/8"),
        ("token_loop", "TokenTileLoop", "baseline_source_expression", "for y in nr"),
        ("sibling_loop", "SiblingProjectionLoop", "generated_grammar_rule", "independent baseline member"),
        ("thread_partition", "ThreadPartition", "baseline_source_expression", "dynamic chunk scheduler"),
        ("tail", "TailDispatch", "baseline_source_expression", "GEMM groups of four then GEMV"),
        ("store", "FloatOutputStore", "baseline_intrinsic", "_mm256_storeu_ps"),
        ("tile", "ProjectionResultTile", "baseline_source_expression", "eight output rows"),
        ("consumer", "ConsumerBoundary", "verified_synthetic_helper", "ProjectionComplexGraph boundary"),
    ]
    nodes = tuple(Q4KGraphNode(identifier, kind, provenance_class, provenance, {}) for identifier, kind, provenance_class, provenance in node_specs)
    edges: list[Q4KGraphEdge] = []
    for index, (source, target, value_type, numerical) in enumerate([
        ("weight_address", "repack_load", "ptr<block_q4_Kx8>", "address"),
        ("repack_load", "metadata_load", "u8x96", "bitvector"),
        ("metadata_load", "scale_decode", "u8x12", "bitvector"),
        ("metadata_load", "min_decode", "u8x12", "bitvector"),
        ("repack_load", "quant_load", "u8x32", "bitvector"),
        ("quant_load", "nibble_extract", "u4x64", "bitvector"),
        ("nibble_extract", "subblock_map", "u4x64", "integer"),
        ("activation_address", "activation_load", "i8x16", "integer"),
        ("activation_load", "activation_reuse", "i8x32", "integer"),
        ("activation_scale", "scale_product", "f32", "ieee754"),
        ("subblock_map", "integer_dot", "u8x32", "integer"),
        ("activation_reuse", "integer_dot", "i8x32", "integer"),
        ("min_decode", "minimum_correction", "u16x16", "integer"),
        ("integer_dot", "float_accumulate", "i32x8", "integer"),
        ("minimum_correction", "float_accumulate", "i32x8", "integer"),
        ("scale_product", "float_accumulate", "f32x8", "ieee754"),
        ("float_accumulate", "accumulator", "f32x8", "ieee754"),
        ("accumulator", "reduce", "f32x8", "ieee754"),
        ("reduce", "store", "f32x8", "ieee754"),
        ("store", "tile", "f32x8", "ieee754"),
        ("tile", "consumer", "f32x8", "ieee754"),
    ]):
        edges.append(Q4KGraphEdge(
            f"edge_{index}", source, target, value_type, (256,), (8, 256), "b", "rows[x:x+8]", "symbolic",
            32, "production-disjoint", "kernel", True, 8 if "activation" in source else 1, numerical,
            "E1 operation order" if numerical == "ieee754" else "exact bitvector", "declared_at_bind", "token_lane",
        ))
    _validate_graph(nodes, tuple(edges))
    payload = {"manifest": manifest_hash, "nodes": [asdict(item) for item in nodes], "edges": [asdict(item) for item in edges]}
    graph_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return Q4KKernelGraph(
        "vladder-q4k-kernel-graph-v7.0", graph_id, graph_hash, manifest_hash, nodes, tuple(edges),
        {"E1": "bitwise production equivalence", "E2": "declared absolute/relative/ULP tolerance; never exact"},
    )


def _validate_graph(nodes: tuple[Q4KGraphNode, ...], edges: tuple[Q4KGraphEdge, ...]) -> None:
    ids = {node.id for node in nodes}
    if len(ids) != len(nodes):
        raise ValueError("Q4KKernelGraph node ids must be unique")
    if {node.kind for node in nodes} != Q4K_NODE_KINDS:
        missing = Q4K_NODE_KINDS - {node.kind for node in nodes}
        raise ValueError("Q4KKernelGraph is missing node kinds: " + ", ".join(sorted(missing)))
    if any(node.provenance_class not in {"baseline_source_expression", "baseline_intrinsic", "baseline_assembly_region", "generated_grammar_rule", "verified_synthetic_helper"} for node in nodes):
        raise ValueError("invalid Q4KKernelGraph provenance class")
    if any(edge.src not in ids or edge.dst not in ids for edge in edges):
        raise ValueError("Q4KKernelGraph edge references an unknown node")


def _half_from_bits(bits: int) -> float:
    return struct.unpack("<e", struct.pack("<H", bits))[0]
