from __future__ import annotations

import hashlib
from typing import Any


def interleave_sibling_blocks(payloads: list[bytes], block_bytes: int) -> tuple[bytes, dict[str, Any]]:
    if len(payloads) < 2:
        raise ValueError("sibling interleave requires at least two payloads")
    if block_bytes <= 0:
        raise ValueError("block_bytes must be positive")
    lengths = {len(payload) for payload in payloads}
    if len(lengths) != 1 or next(iter(lengths)) % block_bytes:
        raise ValueError("all sibling payloads must have equal whole-block lengths")
    blocks_per_sibling = next(iter(lengths)) // block_bytes
    chunks: list[bytes] = []
    forward: list[dict[str, int]] = []
    destination = 0
    for block in range(blocks_per_sibling):
        for sibling, payload in enumerate(payloads):
            chunks.append(payload[block * block_bytes:(block + 1) * block_bytes])
            forward.append({"sibling": sibling, "source_block": block, "destination_block": destination})
            destination += 1
    transformed = b"".join(chunks)
    manifest = {
        "schema_version": "vladder-layout-v5.0",
        "layout": "interleaved_sibling_blocks",
        "sibling_count": len(payloads),
        "block_bytes": block_bytes,
        "blocks_per_sibling": blocks_per_sibling,
        "source_sha256": [_sha(payload) for payload in payloads],
        "transformed_sha256": _sha(transformed),
        "forward_map": forward,
        "padding_bytes": 0,
    }
    return transformed, manifest


def inverse_sibling_interleave(transformed: bytes, manifest: dict[str, Any]) -> list[bytes]:
    block_bytes = int(manifest["block_bytes"])
    sibling_count = int(manifest["sibling_count"])
    blocks_per_sibling = int(manifest["blocks_per_sibling"])
    expected = block_bytes * sibling_count * blocks_per_sibling
    if len(transformed) != expected:
        raise ValueError("transformed layout length differs from manifest domain")
    outputs = [bytearray(block_bytes * blocks_per_sibling) for _ in range(sibling_count)]
    seen: set[tuple[int, int]] = set()
    seen_destinations: set[int] = set()
    for entry in manifest["forward_map"]:
        sibling = int(entry["sibling"])
        source = int(entry["source_block"])
        destination = int(entry["destination_block"])
        identity = (sibling, source)
        if (identity in seen or destination in seen_destinations or
                not (0 <= sibling < sibling_count and 0 <= source < blocks_per_sibling) or
                not (0 <= destination < sibling_count * blocks_per_sibling)):
            raise ValueError("layout map is not a bijection")
        seen.add(identity)
        seen_destinations.add(destination)
        outputs[sibling][source * block_bytes:(source + 1) * block_bytes] = transformed[destination * block_bytes:(destination + 1) * block_bytes]
    if len(seen) != sibling_count * blocks_per_sibling or len(seen_destinations) != sibling_count * blocks_per_sibling:
        raise ValueError("layout map does not cover every source block")
    return [bytes(output) for output in outputs]


def verify_layout_round_trip(payloads: list[bytes], transformed: bytes, manifest: dict[str, Any]) -> dict[str, Any]:
    restored = inverse_sibling_interleave(transformed, manifest)
    exact = restored == payloads
    return {
        "status": "proved" if exact else "failed",
        "method": "finite-block-bijection+byte-exact-inverse",
        "source_sha256": [_sha(payload) for payload in payloads],
        "transformed_sha256": _sha(transformed),
        "inverse_sha256": [_sha(payload) for payload in restored],
        "block_identity_count": len(manifest["forward_map"]),
        "unique_source_identities": len({(entry["sibling"], entry["source_block"]) for entry in manifest["forward_map"]}),
        "padding_bytes": int(manifest["padding_bytes"]),
    }


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()
