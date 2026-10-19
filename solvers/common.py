"""Shared solver result types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from engine.core import Action, GameState


@dataclass(frozen=True, slots=True)
class SolverResult:
    """A solver outcome and the metrics required by the project report."""

    found: bool
    moves: tuple[Action, ...]
    states: tuple[GameState, ...]
    search_time: float
    peak_memory: int
    expanded_nodes: int
    solution_length: int
    path_cost: float | None

    def __post_init__(self) -> None:
        if self.search_time < 0:
            raise ValueError("search_time must be non-negative")
        if self.peak_memory < 0:
            raise ValueError("peak_memory must be non-negative")
        if self.expanded_nodes < 0:
            raise ValueError("expanded_nodes must be non-negative")
        if self.solution_length < 0:
            raise ValueError("solution_length must be non-negative")

        if self.found:
            if self.solution_length != len(self.moves):
                raise ValueError("solution_length must match the number of moves")
            if len(self.states) != len(self.moves) + 1:
                raise ValueError("a solved path must include its initial and final states")
            if self.path_cost is None:
                raise ValueError("a solved path must report its path cost")
        elif self.moves or self.states or self.solution_length or self.path_cost is not None:
            raise ValueError("an unsolved result cannot contain a solution path")

    @property
    def peak_memory_bytes(self) -> int:
        """Return the measured peak memory in bytes."""

        return self.peak_memory

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly metrics and solution summary."""

        return {
            "found": self.found,
            "moves": [move.value for move in self.moves],
            "search_time": self.search_time,
            "peak_memory": self.peak_memory,
            "expanded_nodes": self.expanded_nodes,
            "solution_length": self.solution_length,
            "path_cost": self.path_cost,
        }
