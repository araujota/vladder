from __future__ import annotations

from typing import Any, Iterable, Mapping

from .dataflow_grammar import BoundedDataflowGrammar
from .dataflow_ir import BoundedDataflowContract
from .language_adapter import canonical_hash
from .lazy_search import LazyState


DATAFLOW_LAZY_VERSION = "bounded-dataflow-composition-search-v2"


class BoundedDataflowLazyGrammar:
    """Expose structural dataflow choices before concrete realization choices.

    The intermediate nodes are real search decisions. A useful SIMD terminal therefore marks
    its mask/compaction ancestor useful, while an exhausted structural family becomes a valid
    pruning negative rather than an opaque terminal label.
    """

    def __init__(
        self,
        contract: BoundedDataflowContract,
        grammar: BoundedDataflowGrammar,
    ) -> None:
        self.contract = contract
        self.grammar = grammar
        self.tree = _family_tree(contract.family)
        terminals = {
            value
            for children in self.tree.values()
            for value in children
            if value not in self.tree
        }
        expected = set(grammar.family_terminals(contract.family))
        if terminals != expected:
            raise ValueError(
                f"dataflow lazy tree mismatch for {contract.family}: "
                f"missing={sorted(expected - terminals)}, extra={sorted(terminals - expected)}"
            )

    def initial_states(self, root_context: Mapping[str, Any]) -> Iterable[LazyState]:
        return (self._state("root", (), {"family": self.contract.family, "op": "enter"}),)

    def expand(self, state: LazyState, root_context: Mapping[str, Any]) -> Iterable[LazyState]:
        node = str(state.semantic_state["node"])
        path = tuple(str(item) for item in state.semantic_state.get("path", ()))
        return tuple(
            self._state(
                child,
                (*path, child),
                {
                    "family": self.contract.family,
                    "family_version": DATAFLOW_LAZY_VERSION,
                    "op": "emit" if child not in self.tree else "select_structure",
                    "rule": _rule_name(node, child),
                    "primitives": [_rule_name(node, child)],
                    "parameters": {
                        "structural_choice": child,
                        **({"realization": child} if child not in self.tree else {}),
                    },
                    "realization": child if child not in self.tree else None,
                },
            )
            for child in self.tree.get(node, ())
        )

    def _state(
        self,
        node: str,
        path: tuple[str, ...],
        action: Mapping[str, Any],
    ) -> LazyState:
        terminal = node not in self.tree
        semantic = {
            "node": node,
            "path": list(path),
            "parameters": {"realization": node} if terminal else {},
            "remaining_dimensions": [] if terminal else ["realization"],
        }
        return LazyState(
            self.contract.family,
            "candidate" if terminal else "partial_candidate",
            semantic,
            {key: value for key, value in action.items() if value is not None},
            terminal=terminal,
            identity=canonical_hash({
                "version": DATAFLOW_LAZY_VERSION,
                "family": self.contract.family,
                "node": node,
                "path": path,
                "contract": self.contract.to_dict(),
            }),
        )


def _family_tree(family: str) -> dict[str, tuple[str, ...]]:
    return {
        "predicate-stable-compaction": {
            "root": ("scalar-two-pass", "fused-stable", "mask-and-scatter"),
            "mask-and-scatter": (
                "mask-prefix-stable",
                "guarded-avx2-compaction",
                "guarded-avx512-compress",
            ),
        },
        "fixed-width-codec": {
            "root": ("scalar-field-pack", "fused-pack"),
            "fused-pack": ("fused-word-pack", "coalesced-envelope-store"),
        },
        "stateful-delta-transducer": {
            "root": ("staged-delta", "transactional-update"),
            "transactional-update": ("transactional-delta", "mask-transactional-delta"),
        },
        "aos-fused-multi-reduction": {
            "root": (
                "repeated-projection-scans",
                "fused-aos-reductions",
                "blocked-aos-reductions",
            ),
        },
        "quantized-block-4x4": {
            "root": (
                "scalar-reference-block",
                "fused-4x4-block",
                "packed-lane-4x4-block",
            ),
        },
    }[family]


def _rule_name(parent: str, child: str) -> str:
    return f"{parent}-to-{child}"
