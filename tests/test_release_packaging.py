from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml

from scripts.release_preflight import preflight, project_version, runtime_version
from scripts.render_homebrew_formula import pypi_sdist, render
from scripts.audit_release import audit_artifact


ROOT = Path(__file__).resolve().parent.parent


class ReleasePackagingTests(unittest.TestCase):
    def test_artifact_audit_is_independent_of_generated_build_tree(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "minimal.whl"
            import zipfile
            with zipfile.ZipFile(artifact, "w") as archive:
                for path in (
                    "vladder/grammars/vladder-v1/capabilities.json",
                    "vladder/grammars/lifetime-v1/grammar.json",
                    "vladder/skills/vladder/SKILL.md",
                    "vladder/skills/vladder/references/lifetime.md",
                ):
                    archive.writestr(path, "fixture")
            (root / "build" / "temporary").mkdir(parents=True)
            self.assertEqual(audit_artifact(artifact)["status"], "pass")

    def test_release_identity_and_unbuilt_preflight(self):
        version = project_version(ROOT)
        self.assertEqual(version, runtime_version(ROOT))
        with tempfile.TemporaryDirectory() as directory:
            result = preflight(ROOT, "example/vladder", f"v{version}", Path(directory))
        self.assertEqual(result["status"], "pass")
        checks = {item["name"]: item for item in result["checks"]}
        self.assertEqual(checks["artifacts"]["status"], "pending")
        self.assertIn(checks["git"]["status"], {"pass", "pending"})

    def test_formula_render_is_exact_and_ruby_valid(self):
        source_bytes = b"release source distribution"
        source_digest = hashlib.sha256(source_bytes).hexdigest()
        metadata = {
            "urls": [
                {
                    "packagetype": "sdist",
                    "url": "https://files.pythonhosted.org/example.tar.gz",
                    "digests": {"sha256": "a" * 64},
                }
            ]
        }
        resource = pypi_sdist("example", "1", metadata)
        template = (ROOT / "packaging" / "homebrew" / "vladder.rb.in").read_text()
        formula = render(
            template,
            "example/vladder",
            "1.0.0rc4",
            "https://github.com/example/vladder/releases/download/v1.0.0rc4/vladder-1.0.0rc4.tar.gz",
            source_digest,
            {"PyYAML": resource, "z3-solver": {"url": "https://example.invalid/z3.tar.gz", "sha256": "b" * 64}},
        )
        self.assertNotIn("@REPOSITORY@", formula)
        self.assertIn(source_digest, formula)
        self.assertIn('depends_on "cmake" => :build', formula)
        self.assertIn('depends_on "llvm@20"', formula)
        with tempfile.TemporaryDirectory() as directory:
            formula_path = Path(directory) / "vladder.rb"
            formula_path.write_text(formula)
            completed = subprocess.run(["ruby", "-c", str(formula_path)], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_github_workflows_parse_and_use_oidc(self):
        workflows = ROOT / ".github" / "workflows"
        for path in sorted(workflows.glob("*.yml")):
            with self.subTest(workflow=path.name):
                self.assertIsInstance(yaml.safe_load(path.read_text()), dict)
        release = (workflows / "release.yml").read_text()
        test_publish = (workflows / "test-publish.yml").read_text()
        self.assertIn("id-token: write", release)
        self.assertIn("pypa/gh-action-pypi-publish@release/v1", release)
        self.assertIn("id-token: write", test_publish)
        self.assertNotIn("PYPI_API_TOKEN", release + test_publish)
        self.assertIn("vladder lifetime evaluate-corpus", release)
        self.assertIn("vladder lifetime evaluate-corpus", (workflows / "ci.yml").read_text())


if __name__ == "__main__":
    unittest.main()
