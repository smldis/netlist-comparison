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
    operator_time_limit: float = 60.0
    operator_memory_mib: int = 3072
    operator_parameters: bool = True
    operator_max_leaves: int = 64
    operator_max_nets: int = 64
    operator_max_counterparts: int = 16
    operator_retained_paths: int = 100
    operator_presentation_paths: int = 100
    operator_max_cards: int = 12
    operator_query_seconds: float = 10.0
    regional_work_limit: int = 50_000  # new incidence states/component certificates only
    omission_work_limit: int = 0  # opt-in full-map exchange scores; 0 disables
    swap_work_limit: int = 0  # opt-in full-map paired-swap scores; 0 disables
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
    black_box_missing: bool = False
    component_presentation: str = "existing"

    def __post_init__(self):
        if not isinstance(self.operator_time_limit, (int, float)) or not math.isfinite(self.operator_time_limit) or self.operator_time_limit <= 0:
            raise ValueError('operator_time_limit must be finite and positive')
        if type(self.operator_memory_mib) is not int or self.operator_memory_mib < 64:
            raise ValueError('operator_memory_mib must be an integer at least 64')
        for name in ('operator_max_leaves', 'operator_max_nets', 'operator_max_counterparts',
                     'operator_retained_paths', 'operator_presentation_paths', 'operator_max_cards'):
            if type(getattr(self, name)) is not int or getattr(self, name) <= 0:
                raise ValueError(f'{name} must be a positive integer')
        if self.operator_presentation_paths > self.operator_retained_paths:
            raise ValueError('operator_presentation_paths cannot exceed operator_retained_paths')
        if type(self.operator_query_seconds) not in (int, float) or not math.isfinite(self.operator_query_seconds) or self.operator_query_seconds <= 0:
            raise ValueError('operator_query_seconds must be finite and positive')
        if type(self.operator_parameters) is not bool:
            raise ValueError('operator_parameters must be boolean')
        if type(self.omission_work_limit) is not int or self.omission_work_limit < 0:
            raise ValueError("omission_work_limit must be a nonnegative integer")
        if self.omission_work_limit and self.matching_mode != "regional":
            raise ValueError("omission_work_limit requires matching_mode regional")
        if type(self.swap_work_limit) is not int or self.swap_work_limit < 0:
            raise ValueError("swap_work_limit must be a nonnegative integer")
        if self.swap_work_limit and self.matching_mode != "regional":
            raise ValueError("swap_work_limit requires matching_mode regional")
        if self.component_presentation not in ("existing", "minimum_raw"):
            raise ValueError("component_presentation must be existing or minimum_raw")
        if self.component_presentation != "existing" and self.matching_mode != "regional":
            raise ValueError("component_presentation minimum_raw requires matching_mode regional")
        if type(self.black_box_missing) is not bool:
            raise ValueError("black_box_missing must be a boolean")
        if self.matching_mode not in ("fixed", "anchor_growth", "partial_qap", "regional", "operator_scoped"):
            raise ValueError("matching_mode must be fixed, anchor_growth, partial_qap, regional or operator_scoped")
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
    black_box: dict | None = None


@dataclass
class View:
    selection: dict | None = None
    leaves: list[Leaf] = field(default_factory=list)
    occurrences: list[dict] = field(default_factory=list)
    definitions: dict[str, Circuit] = field(default_factory=dict)
    declared_subcircuits: set[str] = field(default_factory=set)
    nets: dict[str, list[tuple[int, str]]] = field(default_factory=dict)
    unresolved: list[dict] = field(default_factory=list)
    diagnostics: list[dict] = field(default_factory=list)
    budget_exhausted: bool = False
