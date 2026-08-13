from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys


def test_object_symbol_discovery_adds_nonoverlapping_cpp_roots(tmp_path: Path) -> None:
    compiler = shutil.which("clang++-20") or shutil.which("clang++")
    if not compiler:
        return
    source = tmp_path / "sample.cpp"
    source.write_text("""
    int existing(int value) { return value + 1; }
    int encode_packet(int value) { return value ^ 0x55; }
    int count_values(const int* values, int n) {
        int result = 0;
        for (int i = 0; i < n; ++i) result += values[i] != 0;
        return result;
    }
    """)
    object_path = tmp_path / "sample.o"
    completed = subprocess.run(
        [compiler, "-std=c++20", "-O2", "-c", str(source), "-o", str(object_path)],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    assert completed.returncode == 0, completed.stderr
    database = tmp_path / "compile_commands.json"
    database.write_text(json.dumps([{
        "directory": str(tmp_path),
        "file": str(source),
        "arguments": [compiler, "-std=c++20", "-O2", "-c", str(source), "-o", str(object_path)],
    }]))
    base = tmp_path / "base.json"
    base.write_text(json.dumps({
        "schema_version": "vladder-executable-search-manifest-v1",
        "roots": [{
            "id": "existing", "project_id": "fixture", "source": str(source),
            "function": "existing", "compile_commands": str(database), "command_index": 0,
        }],
    }))
    output = tmp_path / "discovered.json"
    command = [
        sys.executable,
        str(Path(__file__).resolve().parents[1] / "scripts/discover_cpp_object_roots.py"),
        "--manifest", str(base), "--output", str(output),
        "--cache-directory", str(tmp_path / "cache"), "--per-family", "8",
    ]
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    assert result.returncode == 0, result.stderr
    manifest = json.loads(output.read_text())
    names = {root["function"] for root in manifest["roots"]}
    assert "existing" not in names
    assert {"encode_packet", "count_values"} <= names
    assert all(root["symbol"] for root in manifest["roots"])
    assert manifest["artifact_retention"] == "decisive"
