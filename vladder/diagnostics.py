from __future__ import annotations

from dataclasses import asdict, dataclass
import importlib.metadata
import json
import platform
import shutil
import subprocess
import sys
from typing import Any

from . import __version__
from .capabilities import load_registry
from .toolchain import compiler_version, cpu_model, discover_toolchain, tool_version


@dataclass(frozen=True)
class DependencyStatus:
    name: str
    required: bool
    available: bool
    path: str | None
    version: str | None


def _command_version(path: str | None, args: tuple[str, ...] = ("--version",)) -> str | None:
    if not path:
        return None
    result = subprocess.run([path, *args], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
    text = (result.stdout + result.stderr).strip()
    return text.splitlines()[0] if text else None


def doctor_report(strict: bool = False) -> dict[str, Any]:
    tc = discover_toolchain()
    z3_path = shutil.which("z3")
    dependencies = [
        DependencyStatus("clang", True, tc.compiler_kind == "clang", tc.compiler, compiler_version(tc.compiler)),
        DependencyStatus("llvm-mca", True, bool(tc.llvm_mca), tc.llvm_mca, tool_version(tc.llvm_mca)),
        DependencyStatus("z3", True, bool(z3_path), z3_path, _command_version(z3_path, ("-version",))),
        DependencyStatus("alive-tv", strict, bool(tc.alive_tv), tc.alive_tv, tool_version(tc.alive_tv)),
        DependencyStatus("cbmc", False, bool(tc.cbmc), tc.cbmc, tool_version(tc.cbmc)),
        DependencyStatus("perf", strict, bool(tc.perf), tc.perf, _command_version(tc.perf, ("--version",))),
        DependencyStatus("objdump", True, bool(tc.objdump), tc.objdump, _command_version(tc.objdump)),
        DependencyStatus("glslangValidator", False, bool(shutil.which("glslangValidator")), shutil.which("glslangValidator"), _command_version(shutil.which("glslangValidator"))),
        DependencyStatus("spirv-val", False, bool(shutil.which("spirv-val")), shutil.which("spirv-val"), _command_version(shutil.which("spirv-val"))),
        DependencyStatus("spirv-opt", False, bool(shutil.which("spirv-opt")), shutil.which("spirv-opt"), _command_version(shutil.which("spirv-opt"))),
        DependencyStatus("nvcc", False, bool(shutil.which("nvcc")), shutil.which("nvcc"), _command_version(shutil.which("nvcc"))),
    ]
    python_dependencies = []
    for distribution in ("PyYAML",):
        try:
            version = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            version = None
        python_dependencies.append(
            DependencyStatus(distribution, True, version is not None, None, version)
        )
    try:
        import z3  # type: ignore[import-not-found]

        z3_python_version = z3.get_version_string()
    except (ImportError, AttributeError):
        z3_python_version = None
    python_dependencies.append(
        DependencyStatus("z3-python", True, z3_python_version is not None, None, z3_python_version)
    )
    dependencies.extend(python_dependencies)
    missing = [item.name for item in dependencies if item.required and not item.available]
    registry = load_registry()
    return {
        "status": "pass" if not missing else "fail",
        "strict": strict,
        "vladder_version": __version__,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "cpu_model": cpu_model(),
        "grammar_version": registry.version,
        "grammar_sha256": registry.sha256,
        "dependencies": [asdict(item) for item in dependencies],
        "missing_required": missing,
    }


def doctor_json(strict: bool = False) -> str:
    return json.dumps(doctor_report(strict), indent=2, sort_keys=True)
