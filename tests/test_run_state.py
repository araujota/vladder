from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from vladder.run_state import ContentAddressedRun


class RunStateTests(unittest.TestCase):
    def test_resume_requires_matching_artifact_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run = ContentAddressedRun(root, {"contract": "abc", "grammar": "def", "target": "ghi"})
            run.initialize()
            artifact = run.directory / "graph.json"
            artifact.write_text("{}\n")
            run.complete_step("analyze", [artifact])
            self.assertTrue(run.step_is_valid("analyze"))
            artifact.write_text("changed\n")
            self.assertFalse(run.step_is_valid("analyze"))


if __name__ == "__main__":
    unittest.main()
