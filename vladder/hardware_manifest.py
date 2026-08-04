from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import platform
import re
from typing import Any

from .toolchain import Toolchain, compiler_version, cpu_model, run


MATERIAL_FIELDS = (
    "cpu_model", "cpu_family_model_stepping", "online_cpus", "affinity",
    "thread_siblings", "numa_nodes", "l3_cache", "microcode", "governors",
    "kernel", "compiler", "memory",
)


@dataclass(frozen=True)
class HardwareManifest:
    schema_version: str
    target_name: str
    cpu: int
    data: dict[str, Any]
    manifest_hash: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def capture_manifest(target_name: str, cpu: int, tc: Toolchain) -> HardwareManifest:
    lscpu_result = run(["lscpu", "-J"], timeout=10)
    lscpu = json.loads(lscpu_result.stdout) if lscpu_result.returncode == 0 else {"lscpu": []}
    fields = {item["field"].rstrip(":"): item.get("data", "") for item in lscpu.get("lscpu", [])}
    cpu_root = Path(f"/sys/devices/system/cpu/cpu{cpu}")
    topology = cpu_root / "topology"
    governors = {}
    frequencies = {}
    for item in sorted(Path("/sys/devices/system/cpu").glob("cpu[0-9]*")):
        index = item.name[3:]
        governor = _read(item / "cpufreq/scaling_governor")
        current = _read(item / "cpufreq/scaling_cur_freq")
        if governor:
            governors[index] = governor
        if current:
            frequencies[index] = int(current)
    data = {
        "captured_unix_ns": __import__("time").time_ns(),
        "cpu_model": fields.get("Model name", cpu_model()),
        "cpu_family_model_stepping": [fields.get("CPU family"), fields.get("Model"), fields.get("Stepping")],
        "online_cpus": fields.get("On-line CPU(s) list"),
        "affinity": sorted(os.sched_getaffinity(0)),
        "selected_cpu": cpu,
        "thread_siblings": _read(topology / "thread_siblings_list"),
        "core_id": _read(topology / "core_id"),
        "package_id": _read(topology / "physical_package_id"),
        "die_id": _read(topology / "die_id"),
        "numa_nodes": fields.get("NUMA node(s)"),
        "numa_cpu_list": fields.get("NUMA node0 CPU(s)"),
        "l1d_cache": fields.get("L1d cache"),
        "l2_cache": fields.get("L2 cache"),
        "l3_cache": fields.get("L3 cache"),
        "governors": governors,
        "frequency_khz_snapshot": frequencies,
        "boost": _read(Path("/sys/devices/system/cpu/cpufreq/boost")) or fields.get("Frequency boost"),
        "microcode": _read(cpu_root / "microcode/version"),
        "kernel": platform.release(),
        "os": platform.platform(),
        "compiler": compiler_version(tc.compiler),
        "compiler_path": tc.compiler,
        "memory": _memory_configuration(),
        "temperature_millic": _temperatures(),
        "cmdline": _read(Path("/proc/cmdline")),
    }
    material = {key: data.get(key) for key in MATERIAL_FIELDS}
    digest = hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return HardwareManifest("vladder-target-v3.0", target_name, cpu, data, digest)


def write_manifest(path: Path, manifest: HardwareManifest) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest.to_dict(), indent=2, sort_keys=True) + "\n")


def compatibility_errors(manifests: list[HardwareManifest]) -> list[str]:
    if not manifests:
        return ["no hardware manifests supplied"]
    baseline = manifests[0]
    errors = []
    for other in manifests[1:]:
        for field in MATERIAL_FIELDS:
            if baseline.data.get(field) != other.data.get(field):
                errors.append(f"material field {field} differs between {baseline.manifest_hash[:12]} and {other.manifest_hash[:12]}")
        if baseline.cpu != other.cpu:
            errors.append(f"selected CPU differs: {baseline.cpu} vs {other.cpu}")
    return sorted(set(errors))


def stability_warnings(manifest: HardwareManifest) -> list[str]:
    warnings = []
    if manifest.cpu not in manifest.data.get("affinity", []):
        warnings.append("selected CPU is outside process affinity")
    if any(value != "performance" for value in manifest.data.get("governors", {}).values()):
        warnings.append("not all exposed CPUs use the performance governor")
    if str(manifest.data.get("boost", "")).lower() not in {"0", "disabled", "off", "false"}:
        warnings.append("frequency boost is enabled; cycle counts remain valid but thermal/frequency reproducibility needs scrutiny")
    siblings = str(manifest.data.get("thread_siblings", ""))
    if "," in siblings or "-" in siblings:
        warnings.append("selected CPU exposes an SMT sibling; isolation must be demonstrated")
    return warnings


def _read(path: Path) -> str:
    try:
        return path.read_text().strip()
    except OSError:
        return ""


def _memory_configuration() -> list[dict[str, Any]]:
    result = run(["dmidecode", "-t", "memory"], timeout=20)
    if result.returncode != 0:
        return [{"status": "unavailable"}]
    modules = []
    current: dict[str, Any] = {}
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if stripped == "Memory Device":
            if current.get("Size") and current["Size"] != "No Module Installed":
                modules.append(current)
            current = {}
        match = re.match(r"(Size|Type|Speed|Configured Memory Speed|Manufacturer|Part Number):\s*(.*)", stripped)
        if match:
            current[match.group(1)] = match.group(2).strip()
    if current.get("Size") and current["Size"] != "No Module Installed":
        modules.append(current)
    return modules or [{"status": "unavailable"}]


def _temperatures() -> dict[str, int]:
    values = {}
    for directory in sorted(Path("/sys/class/hwmon").glob("hwmon*")):
        name = _read(directory / "name") or directory.name
        for input_path in sorted(directory.glob("temp*_input")):
            raw = _read(input_path)
            if raw.isdigit():
                label = _read(input_path.with_name(input_path.name.replace("_input", "_label"))) or input_path.stem
                values[f"{name}:{label}"] = int(raw)
    return values
