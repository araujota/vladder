from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from vladder import CPP_SUPPORT_VERSION, CppRegionRequest, VelocityLadder
from vladder.cpp_regions import inspect_cpp_region, load_compilation_command
from vladder.toolchain import discover_toolchain


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "examples" / "cpp_regions"
SUPPORTED = ("supported_pointer.cpp", "supported_span.cpp", "supported_vector.cpp", "supported_method.cpp", "supported_template.cpp")
ADAPTERS = {
    "adapter_ownership.cpp": "ownership-lifetime-adapter",
    "adapter_exception.cpp": "exception-adapter",
    "adapter_external.cpp": "external-call-adapter",
    "adapter_atomic.cpp": "memory-order-adapter",
    "adapter_overload.cpp": "overload-selection-adapter",
}


def write_database(root: Path, files: tuple[str, ...] | None = None) -> Path:
    tc = discover_toolchain()
    selected = files or tuple(path.name for path in FIXTURES.glob("*.cpp"))
    entries = []
    for name in selected:
        source = (FIXTURES / name).resolve()
        entries.append({
            "directory": str(ROOT),
            "file": str(source),
            "arguments": [tc.compiler, "-std=c++20", "-Wall", "-Wextra", "-c", str(source), "-o", str(root / f"{source.stem}.o")],
        })
    path = root / "compile_commands.json"
    path.write_text(json.dumps(entries, indent=2) + "\n")
    return path


class CppRegionTests(unittest.TestCase):
    def test_supported_matrix_emits_proved_adapter_and_regenerated_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = write_database(root)
            for name in SUPPORTED:
                with self.subTest(name=name):
                    out = root / name
                    report = inspect_cpp_region(FIXTURES / name, "transform", database, out)
                    self.assertEqual(report["status"], "supported")
                    self.assertEqual(report["support_version"], CPP_SUPPORT_VERSION)
                    self.assertEqual(report["proof_classification"], "kernel_isolated_adapter_proved")
                    self.assertEqual(report["verification"]["adapter"]["status"], "PROVED")
                    self.assertEqual(report["verification"]["regenerated_compile"]["status"], "pass")
                    self.assertTrue(Path(report["production_ir"]["normalized_ir"]).read_text().startswith("define "))
                    self.assertTrue(Path(report["artifacts"]["regenerated_cpp"]).exists())
                    self.assertTrue(Path(report["artifacts"]["provenance"]).exists())
                    self.assertTrue(report["kernel_support"]["supported"])

    def test_cpp_semantics_fail_closed_with_named_adapters(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = write_database(root)
            for name, expected in ADAPTERS.items():
                with self.subTest(name=name):
                    report = inspect_cpp_region(FIXTURES / name, "transform", database, root / name)
                    self.assertEqual(report["status"], "adapter_required")
                    self.assertIn(expected, [item["kind"] for item in report["adapters"]])
                    self.assertNotEqual(report["proof_classification"], "kernel_isolated_adapter_proved")
                    self.assertNotIn("regenerated_cpp", report["artifacts"])

    def test_overload_can_be_selected_by_mangled_symbol(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = write_database(root, ("adapter_overload.cpp",))
            first = inspect_cpp_region(FIXTURES / "adapter_overload.cpp", "transform", database, root / "ambiguous")
            pointer_symbol = next(item["symbol"] for item in first["candidate_symbols"] if "PfPKf" in item["symbol"])
            selected = inspect_cpp_region(
                FIXTURES / "adapter_overload.cpp", "transform", database, root / "selected", symbol=pointer_symbol
            )
            self.assertEqual(selected["status"], "supported")
            self.assertEqual(selected["selection"]["symbol"], pointer_symbol)
            self.assertEqual(selected["abi_class"], "pointer-view")

    def test_ambiguous_compile_commands_require_an_index(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = write_database(root, ("supported_span.cpp",))
            entries = json.loads(database.read_text())
            duplicate = dict(entries[0])
            duplicate["arguments"] = [*duplicate["arguments"][:-2], "-DSECOND_CONFIGURATION=1", *duplicate["arguments"][-2:]]
            database.write_text(json.dumps([entries[0], duplicate]))
            report = inspect_cpp_region(FIXTURES / "supported_span.cpp", "transform", database, root / "ambiguous")
            self.assertEqual(report["adapters"][0]["kind"], "compile-command-selection-adapter")
            selected = load_compilation_command(FIXTURES / "supported_span.cpp", database, command_index=1)
            self.assertIn("-DSECOND_CONFIGURATION=1", selected.semantic_arguments)

    def test_regenerated_span_executes_with_original_results(self):
        tc = discover_toolchain()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = write_database(root, ("supported_span.cpp",))
            report = inspect_cpp_region(FIXTURES / "supported_span.cpp", "transform", database, root / "out")
            generated = Path(report["artifacts"]["regenerated_cpp"])
            driver = root / "driver.cpp"
            driver.write_text(
                "#include <bit>\n#include <cstdint>\n#include <cstdio>\n#include <span>\n"
                "void transform(std::span<float>, std::span<const float>) noexcept;\n"
                "int main(){ float src[8]={-2,-1,0,1,2,3,4,5}; float dst[8]={}; "
                "transform(dst,src); std::uint64_t h=1469598103934665603ull; "
                "for(float x:dst){h^=std::bit_cast<std::uint32_t>(x);h*=1099511628211ull;} "
                "std::printf(\"%llu\\n\",(unsigned long long)h);}\n"
            )
            outputs = []
            for index, source in enumerate((FIXTURES / "supported_span.cpp", generated)):
                binary = root / f"run-{index}"
                compiled = subprocess.run(
                    [tc.compiler, "-std=c++20", "-O3", str(source), str(driver), "-o", str(binary)],
                    text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                )
                self.assertEqual(compiled.returncode, 0, compiled.stderr)
                outputs.append(subprocess.check_output([str(binary)], text=True).strip())
            self.assertEqual(outputs[0], outputs[1])

    def test_library_api_isolates_cpp(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = write_database(root, ("supported_pointer.cpp",))
            request = CppRegionRequest(
                FIXTURES / "supported_pointer.cpp", "transform", database, root / "api", action="isolate"
            )
            result = VelocityLadder().cpp_region(request)
            self.assertEqual(result.return_code, 0)
            self.assertEqual(result.report["status"], "supported")


if __name__ == "__main__":
    unittest.main()
