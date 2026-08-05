from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any

import yaml

from .cuda_runtime import probe_cuda_device
from .device_protocol import enumerate_dma_routes
from .language_adapter import canonical_hash, file_sha256


DEVICE_TOPOLOGY_SCHEMA_VERSION = "vladder-device-topology-v1"
VULKAN_CAPABILITY_SCHEMA_VERSION = "vladder-vulkan-capability-v1"


def _read(path: Path, fallback: str = "") -> str:
    try:
        return path.read_text().strip()
    except (FileNotFoundError, PermissionError, OSError):
        return fallback


def _link_capacity(speed_text: str, width_text: str) -> float:
    try:
        width = max(0, int(width_text or 0))
    except ValueError:
        width = 0
    match = re.search(r"([0-9.]+)\s*GT/s", speed_text)
    transfers = float(match.group(1)) * 1e9 if match else 0.0
    efficiency = 128.0 / 130.0 if transfers >= 8e9 else 8.0 / 10.0
    return transfers * width * efficiency / 8.0


def _link_bandwidth(path: Path) -> tuple[float, dict[str, Any]]:
    current_speed = _read(path / "current_link_speed", "0")
    current_width = _read(path / "current_link_width", "0")
    max_speed = _read(path / "max_link_speed", current_speed)
    max_width = _read(path / "max_link_width", current_width)
    current = _link_capacity(current_speed, current_width)
    maximum = _link_capacity(max_speed, max_width)
    return maximum or current, {
        "current_speed": current_speed,
        "current_width": max(0, int(current_width or 0)),
        "current_bandwidth_bytes_per_second": current,
        "max_speed": max_speed,
        "max_width": max(0, int(max_width or 0)),
        "max_bandwidth_bytes_per_second": maximum,
        "capacity_basis": "maximum negotiated capability; current link may be power-managed while idle",
    }


def _cache_root() -> Path:
    root = Path(os.environ.get("VLADDER_CACHE_DIR", Path.home() / ".cache" / "vladder")) / "vulkan"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _stable_capability_payload(value: Any) -> Any:
    """Remove probe-location and transient link-state fields from identity hashes."""
    if isinstance(value, dict):
        return {
            key: _stable_capability_payload(item)
            for key, item in value.items()
            if key not in {"runner", "capability_hash", "observation_hash", "topology_hash"}
            and not key.startswith("current_")
        }
    if isinstance(value, list):
        return [_stable_capability_payload(item) for item in value]
    return value


def _ensure_vulkan_probe() -> Path:
    source = Path(__file__).resolve().parent / "native" / "vulkan_probe.cpp"
    compiler = os.environ.get("CXX") or shutil.which("c++") or shutil.which("g++")
    if not source.is_file():
        raise RuntimeError(f"bundled Vulkan probe source is missing: {source}")
    if not compiler:
        raise RuntimeError("a C++ compiler is required for the Vulkan capability probe")
    identity_text = subprocess.run(
        [compiler, "--version"], check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
    ).stdout
    identity = hashlib.sha256(
        (file_sha256(source) + "\n" + str(Path(compiler).resolve()) + "\n" + identity_text).encode("utf-8")
    ).hexdigest()[:20]
    directory = _cache_root() / f"probe-{identity}"
    binary = directory / "vladder-vulkan-probe"
    if binary.is_file() and os.access(binary, os.X_OK):
        return binary
    directory.mkdir(parents=True, exist_ok=True)
    command = [compiler, "-std=c++17", "-O2", str(source), "-lvulkan", "-o", str(binary)]
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise RuntimeError(f"Vulkan probe build failed: {' '.join(command)}\n{result.stderr[-4000:]}")
    (directory / "build.json").write_text(json.dumps({
        "source": str(source), "source_hash": file_sha256(source), "compiler": compiler,
        "compiler_identity": identity_text.strip(), "command": command,
    }, indent=2, sort_keys=True) + "\n")
    return binary


def probe_vulkan_capabilities(output_path: Path | None = None) -> dict[str, Any]:
    runner = _ensure_vulkan_probe()
    result = subprocess.run(
        [str(runner)], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30.0
    )
    if result.returncode:
        raise RuntimeError(f"Vulkan capability probe failed: {result.stderr[-4000:]}")
    report = json.loads(result.stdout)
    if report.get("schema_version") != VULKAN_CAPABILITY_SCHEMA_VERSION:
        raise ValueError("Vulkan probe returned an unsupported schema")
    report["runner"] = str(runner)
    report["claim_boundary"] = (
        "physical-device and queue-family capabilities; surface support, command execution, "
        "driver scheduling, and presentation completion require workload-bound runtime evidence"
    )
    report["capability_hash"] = canonical_hash(_stable_capability_payload(report))
    if output_path is not None:
        output_path = output_path.resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def probe_drm_presentation(output_path: Path | None = None) -> dict[str, Any]:
    connectors = []
    for status_path in sorted(Path("/sys/class/drm").glob("card*-*/status")):
        connector = status_path.parent
        card_name = connector.name.split("-", 1)[0]
        card_device = Path("/sys/class/drm") / card_name / "device"
        edid_path = connector / "edid"
        edid = edid_path.read_bytes() if edid_path.is_file() else b""
        connectors.append({
            "id": connector.name,
            "card": card_name,
            "status": _read(status_path, "unknown"),
            "enabled": _read(connector / "enabled", "unknown"),
            "dpms": _read(connector / "dpms", "unknown"),
            "modes": [line for line in _read(connector / "modes").splitlines() if line],
            "edid_sha256": hashlib.sha256(edid).hexdigest() if edid else None,
            "pci_bdf": Path(os.path.realpath(card_device)).name if card_device.exists() else None,
        })
    connected = [item["id"] for item in connectors if item["status"] == "connected"]
    report = {
        "schema_version": "vladder-drm-presentation-capability-v1",
        "status": "PASS" if connected else "NO_CONNECTED_CONNECTOR",
        "connectors": connectors,
        "connected_connectors": connected,
        "claim_boundary": (
            "DRM connector identity and advertised modes only; swapchain acquisition, page-flip, "
            "vblank, compositor, and scanout timestamps require an active display runner"
        ),
    }
    report["capability_hash"] = canonical_hash(_stable_capability_payload(report))
    if output_path is not None:
        output_path = output_path.resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def _iommu_group(path: Path) -> str | None:
    target = path / "iommu_group"
    if not target.exists():
        return None
    try:
        return Path(os.path.realpath(target)).name
    except OSError:
        return None


def _pci_path(path: Path) -> list[str]:
    resolved = Path(os.path.realpath(path))
    return [part for part in resolved.parts if re.fullmatch(r"[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-7]", part)]


def _rdma_bdfs() -> set[str]:
    results: set[str] = set()
    root = Path("/sys/class/infiniband")
    if not root.is_dir():
        return results
    for device in root.iterdir():
        target = device / "device"
        if target.exists():
            results.add(Path(os.path.realpath(target)).name)
    return results


def _network_interfaces() -> list[dict[str, Any]]:
    rdma = _rdma_bdfs()
    results = []
    for interface in sorted(Path("/sys/class/net").iterdir() if Path("/sys/class/net").is_dir() else []):
        device_link = interface / "device"
        if not device_link.exists():
            continue
        device_path = Path(os.path.realpath(device_link))
        bdf = device_path.name
        if not re.fullmatch(r"[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-7]", bdf):
            continue
        speed_mbps_text = _read(interface / "speed", "0")
        try:
            network_bandwidth = max(0.0, float(speed_mbps_text)) * 1e6 / 8.0
        except ValueError:
            network_bandwidth = 0.0
        pcie_bandwidth, link = _link_bandwidth(device_path)
        capabilities = ["network_endpoint"]
        if bdf in rdma:
            capabilities.extend(("rdma", "peer_dma_import"))
        results.append({
            "interface": interface.name,
            "bdf": bdf,
            "type": "nic",
            "driver": Path(os.path.realpath(device_path / "driver")).name if (device_path / "driver").exists() else None,
            "vendor_id": _read(device_path / "vendor"),
            "device_id": _read(device_path / "device"),
            "numa_node": int(_read(device_path / "numa_node", "-1")),
            "iommu_group": _iommu_group(device_path),
            "pci_path": _pci_path(device_path),
            "network_bandwidth_bytes_per_second": network_bandwidth,
            "pcie_bandwidth_bytes_per_second": pcie_bandwidth,
            "pcie_link": link,
            "capabilities": capabilities,
        })
    return results


def probe_device_topology(
    output_path: Path | None = None,
    *,
    cuda_device: int = 0,
    transfer_bytes: int = 1 << 20,
) -> dict[str, Any]:
    cuda = probe_cuda_device(cuda_device)
    vulkan = probe_vulkan_capabilities()
    presentation = probe_drm_presentation()
    bdf = f"{int(cuda['pci_domain_id']):04x}:{int(cuda['pci_bus_id']):02x}:{int(cuda['pci_device_id']):02x}.0"
    gpu_path = Path("/sys/bus/pci/devices") / bdf
    gpu_bandwidth, gpu_link = _link_bandwidth(gpu_path)
    gpu_capabilities = ["cuda", "peer_dma_export"] if int(cuda.get("gpu_direct_rdma_supported", 0)) else ["cuda"]
    cuda_uuid = str(cuda["device_uuid"]).removeprefix("GPU-").lower()
    matching_vulkan = next(
        (item for item in vulkan.get("devices", []) if str(item.get("device_uuid", "")).lower() == cuda_uuid),
        None,
    )
    gpu = {
        "id": "gpu0",
        "type": "gpu",
        "name": cuda["name"],
        "uuid": cuda["device_uuid"],
        "bdf": bdf,
        "numa_node": int(_read(gpu_path / "numa_node", "-1")),
        "iommu_group": _iommu_group(gpu_path),
        "pci_path": _pci_path(gpu_path),
        "pcie_bandwidth_bytes_per_second": gpu_bandwidth,
        "pcie_link": gpu_link,
        "gpu_direct_rdma_supported": bool(cuda.get("gpu_direct_rdma_supported", 0)),
        "gpu_direct_rdma_flush_writes_options": cuda.get("gpu_direct_rdma_flush_writes_options"),
        "gpu_direct_rdma_writes_ordering": cuda.get("gpu_direct_rdma_writes_ordering"),
        "capabilities": gpu_capabilities,
        "vulkan_binding": {
            "matched": matching_vulkan is not None,
            "device_uuid": matching_vulkan.get("device_uuid") if matching_vulkan else None,
            "device_index": matching_vulkan.get("index") if matching_vulkan else None,
            "timeline_semaphore": matching_vulkan.get("timeline_semaphore") if matching_vulkan else None,
            "synchronization2": matching_vulkan.get("synchronization2") if matching_vulkan else None,
            "queue_families": matching_vulkan.get("queue_families", []) if matching_vulkan else [],
        },
    }
    interfaces = _network_interfaces()
    devices: list[dict[str, Any]] = [gpu, {
        "id": "host0",
        "type": "host-memory",
        "capabilities": ["host_staging", "peer_dma_import", "peer_dma_export"],
    }]
    links: list[dict[str, Any]] = [{
        "from": "gpu0",
        "to": "host0",
        "kind": "pcie-host-staging",
        "direct": False,
        "bidirectional": True,
        "bandwidth_bytes_per_second": gpu_bandwidth,
        "latency_ns": 2000,
        "evidence": gpu_link,
    }]
    for ordinal, interface in enumerate(interfaces):
        identifier = f"nic{ordinal}"
        devices.append({"id": identifier, **interface})
        staged_bandwidth = min(
            value for value in (
                float(interface["pcie_bandwidth_bytes_per_second"]),
                float(interface["network_bandwidth_bytes_per_second"]),
            ) if value > 0
        ) if any(float(interface[key]) > 0 for key in (
            "pcie_bandwidth_bytes_per_second", "network_bandwidth_bytes_per_second"
        )) else 0.0
        links.append({
            "from": "host0",
            "to": identifier,
            "kind": "host-to-nic",
            "direct": False,
            "bidirectional": True,
            "bandwidth_bytes_per_second": staged_bandwidth,
            "latency_ns": 2000,
            "evidence": interface["pcie_link"],
        })
        direct_capable = "peer_dma_export" in gpu_capabilities and "peer_dma_import" in interface["capabilities"]
        if direct_capable:
            links.append({
                "from": "gpu0",
                "to": identifier,
                "kind": "gpudirect-rdma-pcie",
                "direct": True,
                "bidirectional": True,
                "bandwidth_bytes_per_second": min(gpu_bandwidth, float(interface["pcie_bandwidth_bytes_per_second"])),
                "latency_ns": 1000,
                "common_pci_ancestry": sorted(set(gpu["pci_path"]) & set(interface["pci_path"])),
            })
    route_sets: dict[str, list[dict[str, Any]]] = {}
    for device in devices:
        if device.get("type") != "nic":
            continue
        raw = {
            "devices": devices,
            "links": links,
            "transfer": {"source": "gpu0", "destination": device["id"], "bytes": transfer_bytes},
        }
        route_sets[str(device["id"])] = enumerate_dma_routes(raw)
    report = {
        "schema_version": DEVICE_TOPOLOGY_SCHEMA_VERSION,
        "status": "PASS",
        "devices": devices,
        "links": links,
        "routes": route_sets,
        "direct_gpudirect_targets": [
            device["id"] for device in devices
            if device.get("type") == "nic" and "peer_dma_import" in device.get("capabilities", [])
            and "peer_dma_export" in gpu_capabilities
        ],
        "vulkan": vulkan,
        "presentation": presentation,
        "claim_boundary": (
            "sysfs/CUDA/Vulkan capability and route evidence; NIC firmware, registration success, "
            "IOMMU policy, queue execution, page flips, scanout, and transfer completion require runtime proof"
        ),
    }
    report["observation_hash"] = canonical_hash(report)
    report["topology_hash"] = canonical_hash(_stable_capability_payload(report))
    if output_path is not None:
        output_path = output_path.resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def emit_dma_protocol_template(
    topology: dict[str, Any],
    destination: str,
    output_path: Path,
    *,
    transfer_bytes: int = 1 << 20,
) -> dict[str, Any]:
    routes = topology.get("routes", {}).get(destination, [])
    if not routes:
        raise ValueError(f"no topology route to {destination}")
    route = routes[0]
    direct = bool(route["direct"])
    manifest = {
        "kind": "dma",
        "name": f"gpu0-to-{destination}",
        "topology_hash": topology["topology_hash"],
        "devices": topology["devices"],
        "links": topology["links"],
        "transfer": {
            "source": "gpu0",
            "destination": destination,
            "route": route["route"],
            "bytes": transfer_bytes,
            "direct": direct,
            "memory_registered": False,
            "registration_api": None,
            "producer_complete_before_dma": False,
            "producer_sync": None,
            "dma_complete_before_publish": False,
            "completion_signal": None,
            "publication_order": None,
            "consumer_complete_before_reuse": False,
            "reuse_guard": None,
            "fallback": "host_staging" if direct else "copy_to_host_then_send",
        },
    }
    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(yaml.safe_dump(manifest, sort_keys=False))
    return manifest


def emit_vulkan_queue_protocol_template(topology: dict[str, Any], output_path: Path) -> dict[str, Any]:
    gpu = next((item for item in topology.get("devices", []) if item.get("type") == "gpu"), None)
    if not gpu:
        raise ValueError("topology contains no GPU")
    binding = gpu.get("vulkan_binding", {})
    if not binding.get("matched"):
        raise ValueError("CUDA target has no matching Vulkan device UUID")
    families = binding.get("queue_families", [])
    family = next((item for item in families if "compute" in item.get("flags", [])), None)
    if not family:
        raise ValueError("matching Vulkan device has no compute-capable queue family")
    family_index = int(family["index"])
    manifest = {
        "kind": "queue",
        "name": "live-bound-compute-producer-consumer",
        "requires_synchronization2": True,
        "device_binding": {
            "topology_hash": topology["topology_hash"],
            "device_uuid": binding["device_uuid"],
            "timeline_semaphore": binding["timeline_semaphore"],
            "synchronization2": binding["synchronization2"],
            "queue_families": families,
        },
        "resources": [{"id": "output", "owner": str(family_index)}],
        "operations": [
            {
                "id": "produce", "queue": f"family-{family_index}-queue-0",
                "queue_family": str(family_index), "queue_family_index": family_index, "queue_index": 0,
                "required_capabilities": ["compute"],
                "accesses": [{"resource": "output", "mode": "write", "stage": "compute"}],
                "signals": [{"semaphore": "produce_done", "value": 1}],
            },
            {
                "id": "consume", "queue": f"family-{family_index}-queue-0",
                "queue_family": str(family_index), "queue_family_index": family_index, "queue_index": 0,
                "required_capabilities": ["compute"],
                "accesses": [{"resource": "output", "mode": "read", "stage": "compute"}],
            },
        ],
        "barriers": [{
            "src": "produce", "dst": "consume", "resource": "output",
            "src_stage": "compute", "dst_stage": "compute",
            "src_access": "shader_write", "dst_access": "shader_read",
        }],
    }
    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(yaml.safe_dump(manifest, sort_keys=False))
    return manifest


def emit_presentation_protocol_template(topology: dict[str, Any], output_path: Path) -> dict[str, Any]:
    presentation = topology.get("presentation", {})
    connectors = presentation.get("connectors", [])
    connector = next((item for item in connectors if item.get("status") == "connected"), None)
    if connector is None:
        connector = connectors[0] if connectors else {
            "id": "unavailable", "status": "unavailable", "pci_bdf": None, "modes": [],
        }
    manifest = {
        "kind": "presentation",
        "name": "live-bound-swapchain-page-flip-scanout",
        "images": ["image0"],
        "present_mode": "fifo",
        "deadline_policy": "next_vblank",
        "connector_binding": {
            "capability_hash": presentation.get("capability_hash"),
            "connector": connector.get("id"),
            "status": connector.get("status"),
            "pci_bdf": connector.get("pci_bdf"),
            "modes": connector.get("modes", []),
        },
        "events": [
            {"type": "acquire", "image": "image0"},
            {"type": "render_complete", "image": "image0"},
            {"type": "present", "image": "image0"},
            {"type": "scanout", "image": "image0"},
            {"type": "release", "image": "image0"},
        ],
    }
    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(yaml.safe_dump(manifest, sort_keys=False))
    return manifest
