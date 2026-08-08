"""Pure accounting for exact rooted prefix tries.

The production parser will provide Lean-native tactic units. This module does
not normalize, compare, or interpret those units.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Hashable, Iterable, Sequence


@dataclass(frozen=True)
class PrefixSummary:
    proposals: int
    independent_steps: int
    unique_nodes: int
    reusable_step_occurrences: int
    oracle_ratio: float


def summarize_prefixes(sequences: Iterable[Sequence[Hashable]]) -> PrefixSummary:
    root: dict[Hashable, dict] = {}
    proposals = independent_steps = unique_nodes = 0

    for sequence in sequences:
        proposals += 1
        independent_steps += len(sequence)
        node = root
        for unit in sequence:
            child = node.get(unit)
            if child is None:
                child = {}
                node[unit] = child
                unique_nodes += 1
            node = child

    reusable = independent_steps - unique_nodes
    ratio = independent_steps / unique_nodes if unique_nodes else 1.0
    return PrefixSummary(proposals, independent_steps, unique_nodes, reusable, ratio)

