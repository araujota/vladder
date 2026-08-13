from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def test_cpp_campaign_manifest_is_stratified_and_excludes_existing_roots(tmp_path: Path) -> None:
    compile_commands = tmp_path / "compile_commands.json"
    compile_commands.write_text("[]\n")
    sources = []
    regions = []
    for project in ("alpha", "beta"):
        for family in ("reduction", "stable_compaction"):
            for index in range(3):
                source = tmp_path / f"{project}-{family}-{index}.cpp"
                source.write_text("void f() {}\n")
                sources.append(source)
                regions.append({
                    "id": f"{project}-{family}-{index}",
                    "project": project,
                    "source": str(source),
                    "function": f"function_{index}",
                    "line": index + 1,
                    "compile_commands": str(compile_commands),
                    "command_index": 0,
                    "primary_family": family,
                })
    selection = tmp_path / "selection.json"
    selection.write_text(json.dumps({"regions": regions}))
    excluded = tmp_path / "excluded.json"
    excluded.write_text(json.dumps({"roots": [{
        "source": str(sources[0]), "function": "function_0", "line": 1,
    }]}))
    output = tmp_path / "manifest.json"

    completed = subprocess.run([
        sys.executable,
        str(Path(__file__).resolve().parents[1] / "scripts/build_cpp_search_manifest.py"),
        "--selection", str(selection),
        "--exclude-manifest", str(excluded),
        "--output", str(output),
        "--per-family", "2",
        "--cache-directory", str(tmp_path / "cache"),
    ], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    assert completed.returncode == 0, completed.stderr
    manifest = json.loads(output.read_text())
    keys = {(item["source"], item["function"]) for item in manifest["roots"]}
    assert (str(sources[0]), "function_0") not in keys
    assert all(item["source_line"] >= 1 for item in manifest["roots"])
    assert all(item["contract"]["max_selected_build_regions"] == 3 for item in manifest["roots"])
    assert manifest["artifact_retention"] == "decisive"
    assert len(manifest["full_artifact_identifiers"]) == 2
    counts: dict[tuple[str, str], int] = {}
    for item in manifest["roots"]:
        key = (item["project_id"], item["workload"]["source_family"])
        counts[key] = counts.get(key, 0) + 1
    assert set(counts.values()) == {2}
