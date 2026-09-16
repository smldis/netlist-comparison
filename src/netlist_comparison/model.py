from __future__ import annotations

from dataclasses import dataclass, field
import math
from urllib.parse import quote

from spice_canonical.canonical_netlist import Circuit, Device


@dataclass(frozen=True)
class InputScope:
    """Caller-supplied net-scoping knowledge; canonical extraction omits .GLOBAL."""

    global_nets: tuple[str, ...] = ("0",)
    globals_complete: bool = False


@dataclass(frozen=True)
class Options:
    """Experimental budgets and costs, not calibrated confidence settings."""

    matching_mode: str = "fixed"
    regional_work_limit: int = 50_000  # new incidence states/component certificates only
    growth_rounds: int = 64
    context_mode: str = "none"  # v1 reference; opt-in frozen structural context
    context_weight: float = 0.35
    max_objects: int = 20_000  # occurrences + expanded/opaque leaves per revision
    max_depth: int = 32
    candidate_top_k: int = 8  # feature classes, not individual device copies
    tile_size: int = 128
    max_pair_scores: int = 25_000_000
    max_component_nodes: int = 256
    max_component_edges: int = 4096
    max_alternative_checks: int = 16  # global extra-solver-call budget
    unmatched_cost: float = 0.3  # paid on EACH side
    type_penalty: float = 0.12
    ambiguity_tolerance: float = 1e-9

    def __post_init__(self):
        if self.matching_mode not in ("fixed", "anchor_growth", "partial_qap", "regional"):
            raise ValueError("matching_mode must be fixed, anchor_growth, partial_qap or regional")
        if self.matching_mode != "fixed" and self.context_mode != "none":
            raise ValueError("experimental matching uses its own context; leave context_mode=none")
        if self.context_mode not in ("none", "frozen_neighbors"):
            raise ValueError("context_mode must be none or frozen_neighbors")
        for name in ("regional_work_limit", "growth_rounds", "max_objects", "max_depth", "candidate_top_k", "tile_size",
                     "max_pair_scores", "max_component_nodes", "max_component_edges"):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if type(self.max_alternative_checks) is not int or self.max_alternative_checks < 0:
            raise ValueError("max_alternative_checks must be a nonnegative integer")
        for name in ("unmatched_cost", "type_penalty", "ambiguity_tolerance", "context_weight"):
            value = getattr(self, name)
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and nonnegative")


def location(parts: tuple[str, ...]) -> str:
    # Segment escaping prevents slash-bearing names from aliasing nested paths.
    return "/".join(quote(part, safe="") for part in parts)


@dataclass
class Leaf:
    path: str
    segments: tuple[str, ...]
    parent: str
    ancestors: tuple[str, ...]
    definition: str
    device: Device
    nets: dict[str, str]
    opaque: str | None = None


@dataclass
class View:
    selection: dict | None = None
    leaves: list[Leaf] = field(default_factory=list)
    occurrences: list[dict] = field(default_factory=list)
    definitions: dict[str, Circuit] = field(default_factory=dict)
    nets: dict[str, list[tuple[int, str]]] = field(default_factory=dict)
    unresolved: list[dict] = field(default_factory=list)
    diagnostics: list[dict] = field(default_factory=list)
    budget_exhausted: bool = False
