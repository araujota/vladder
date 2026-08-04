from pathlib import Path
import tempfile
import unittest

import yaml

from vladder.operator_analysis import analyze_operator
from vladder.operator_contract import ContractError, load_contract


class OperatorIRTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parent.parent
        cls.source = cls.root / "examples/operators/residual_rmsnorm_quant.c"
        cls.contract = cls.root / "examples/operators/contracts/residual_rmsnorm_quant.yaml"

    def test_contract_hash_is_stable(self):
        first = load_contract(self.contract)
        second = load_contract(self.contract)
        self.assertEqual(first.contract_hash, second.contract_hash)
        self.assertEqual(first.output_parameter_indices, (4, 5, 6))

    def test_missing_float_policy_is_rejected(self):
        data = yaml.safe_load(self.contract.read_text())
        del data["semantics"]["floating_point"]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.yaml"
            path.write_text(yaml.safe_dump(data))
            with self.assertRaises(ContractError):
                load_contract(path)

    def test_unguarded_specialization_is_rejected(self):
        data = yaml.safe_load(self.contract.read_text())
        data["specializations"]["dimension_256"].pop("enforcement")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.yaml"
            path.write_text(yaml.safe_dump(data))
            with self.assertRaises(ContractError):
                load_contract(path)

    def test_multi_output_operator_analysis(self):
        with tempfile.TemporaryDirectory() as tmp:
            contract, graph, summary = analyze_operator(self.source, self.contract, Path(tmp))
            self.assertEqual(contract.name, "residual_rmsnorm_quant")
            self.assertEqual({node.attrs.get("output") for node in graph.nodes if node.kind == "Emit"}, {"y", "q", "scale"})
            self.assertGreaterEqual(len(summary["fusion_regions"]), 1)
            self.assertTrue((Path(tmp) / "analysis/operator_graph.json").exists())
            self.assertTrue((Path(tmp) / "analysis/operator_slice.json").exists())

    def test_stateful_graph_has_state_scc(self):
        source = self.root / "examples/operators/decode_book_update.c"
        contract = self.root / "examples/operators/contracts/decode_book_update.yaml"
        with tempfile.TemporaryDirectory() as tmp:
            _, graph, summary = analyze_operator(source, contract, Path(tmp))
            self.assertTrue(any({"read_book", "write_book"}.issubset(component) for component in map(set, summary["stateful_sccs"])))
            self.assertEqual(len([node for node in graph.nodes if node.kind == "Emit"]), 4)


if __name__ == "__main__":
    unittest.main()
