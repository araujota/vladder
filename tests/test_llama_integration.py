import tempfile
import unittest
from pathlib import Path

from vladder.llama_integration import _extract_completion, _sha256


class LlamaIntegrationTests(unittest.TestCase):
    def test_sha256_streams_model_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.gguf"
            path.write_bytes(b"vladder")
            self.assertEqual(
                _sha256(path),
                "74d6c60a84e1863f201e5680ac48d503fed9b9fa3e2b7a7ae0bbce55111811ce",
            )

    def test_extract_completion_ignores_timing_prefixes(self):
        log = (
            "0.01.000 I generate: n_ctx = 32\n"
            "0.01.010 Paris is the capital.\n"
            "0.01.020 I common_perf_print: eval time = 1 ms\n"
        )
        self.assertEqual(_extract_completion(log), "Paris is the capital.")


if __name__ == "__main__":
    unittest.main()
