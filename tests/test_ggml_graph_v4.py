import tempfile
import unittest
from pathlib import Path

from vladder.ggml_graph import normalize_ggml_dot


DOT = '''digraph G {
  "0x111" [ style = filled; fillcolor = white; shape = record; label="ffn_inp-0 (f32)|0 [4, 1] | <x>x+y"; ]
  "0x222" [ style = filled; fillcolor = white; shape = record; label="norm-0 (f32)|1 [4, 1] | <x>rms_norm(x)"; ]
  "0x333" [ style = filled; fillcolor = white; shape = record; label="ffn_norm-0 (f32)|2 [4, 1] | <x>x*y"; ]
  "0x444" [ style = filled; fillcolor = pink; shape = record; label="<x>weight (f32)|CONST 0 [4, 1]"; ]
  "0x111" -> "0x222" [ arrowhead = vee; style = solid; label = "src 0"; ]
  "0x222" -> "0x333" [ arrowhead = vee; style = solid; label = "src 0"; ]
  "0x444" -> "0x333" [ arrowhead = vee; style = solid; label = "src 1"; ]
}
'''


class GGMLGraphV4Tests(unittest.TestCase):
    def test_normalization_removes_pointer_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            left = Path(directory) / "left.dot"
            right = Path(directory) / "right.dot"
            left.write_text(DOT)
            right.write_text(DOT.replace("0x111", "0xaaa").replace("0x222", "0xbbb").replace("0x333", "0xccc").replace("0x444", "0xddd"))
            a = normalize_ggml_dot(left, {"model_sha256": "abc", "raw_dot_sha256": "left"})
            b = normalize_ggml_dot(right, {"model_sha256": "abc", "raw_dot_sha256": "right"})
            self.assertEqual(a.graph_hash, b.graph_hash)
            self.assertEqual(a.annotations["v3_add_rms_mul_regions"], 1)
            self.assertEqual(a.annotations["compute_node_count"], 3)
            self.assertEqual(a.annotations["leaf_count"], 1)


if __name__ == "__main__":
    unittest.main()
