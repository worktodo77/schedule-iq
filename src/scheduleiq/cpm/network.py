"""
Ported from the LI MIP 3.9 tool (mip39.network) per ADR-0007 — port-and-validate.
Activity network container and topological ordering for the Phase 2 forward-pass
skeleton.

Provides:
  ActivityNetwork — lightweight container for activities and relationships with
                    validation and predecessor/successor lookups.
  topological_sort — Kahn's algorithm, raises ValueError on cycle.

Phase 2 scope (ADR-002):
  - Simplified container only; no persistence layer, no XER import.
  - Relationship type validation delegates to Relationship.__post_init__.
  - All activity/relationship data is synthetic for Phase 2.

This module is infrastructure; it does not correspond to a single CPW Manual
calculation ID. See INFRA-001 in the calculation registry.
"""

from __future__ import annotations

from collections import deque

from .models import Activity, Relationship


# ---------------------------------------------------------------------------
# Activity network container
# ---------------------------------------------------------------------------

class ActivityNetwork:
    """
    Lightweight container for a set of activities and their relationships.

    Validates on construction:
      - No duplicate activity IDs.
      - Every relationship predecessor ID exists in the activity set.
      - Every relationship successor ID exists in the activity set.

    Builds predecessor and successor lookup dicts for O(1) access during
    scheduling and analysis.

    Assumptions:
      - Relationship type validity is enforced by Relationship.__post_init__.
      - Duration validation is deferred to the forward-pass scheduler.
      - No persistence layer; in-memory only (Phase 2).

    Limitations:
      - No support for date constraints, resource calendars, or project-level
        settings beyond what is passed explicitly to the forward-pass function.
    """

    def __init__(
        self,
        activities: list[Activity],
        relationships: list[Relationship],
    ) -> None:
        """
        Construct and validate the network.

        Args:
            activities:    List of Activity objects. No duplicate act_id values.
            relationships: List of Relationship objects. All pred_id and succ_id
                           values must exist in activities.

        Raises:
            ValueError: If any activity ID is duplicated, or if any relationship
                        references an unknown activity ID.
        """
        self._activities: dict[str, Activity] = {}
        for act in activities:
            if act.act_id in self._activities:
                raise ValueError(
                    f"ActivityNetwork: duplicate activity ID {act.act_id!r}. "
                    "Each activity must have a unique ID."
                )
            self._activities[act.act_id] = act

        for rel in relationships:
            if rel.pred_id not in self._activities:
                raise ValueError(
                    f"ActivityNetwork: relationship predecessor {rel.pred_id!r} "
                    f"(→ {rel.succ_id!r}) not found in the activity set."
                )
            if rel.succ_id not in self._activities:
                raise ValueError(
                    f"ActivityNetwork: relationship successor {rel.succ_id!r} "
                    f"(from {rel.pred_id!r}) not found in the activity set."
                )

        self._relationships: list[Relationship] = list(relationships)

        # Build predecessor / successor lookups
        self._predecessors: dict[str, list[Relationship]] = {
            act_id: [] for act_id in self._activities
        }
        self._successors: dict[str, list[Relationship]] = {
            act_id: [] for act_id in self._activities
        }
        for rel in self._relationships:
            self._predecessors[rel.succ_id].append(rel)
            self._successors[rel.pred_id].append(rel)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def activities(self) -> dict[str, Activity]:
        """Activity ID → Activity mapping (read-only view)."""
        return self._activities

    @property
    def relationships(self) -> list[Relationship]:
        """All relationships in the network."""
        return self._relationships

    @property
    def predecessors(self) -> dict[str, list[Relationship]]:
        """
        Successor ID → list of incoming Relationship objects.

        Each entry contains the relationships for which the key activity is
        the successor. Used by the forward-pass scheduler to find constraints.
        """
        return self._predecessors

    @property
    def successors(self) -> dict[str, list[Relationship]]:
        """
        Predecessor ID → list of outgoing Relationship objects.

        Each entry contains the relationships for which the key activity is
        the predecessor. Used by topological sort to propagate ordering.
        """
        return self._successors

    def __len__(self) -> int:
        return len(self._activities)

    def __repr__(self) -> str:
        return (
            f"ActivityNetwork("
            f"{len(self._activities)} activities, "
            f"{len(self._relationships)} relationships)"
        )


# ---------------------------------------------------------------------------
# Topological ordering
# ---------------------------------------------------------------------------

def _is_fully_pinned(activity: Activity) -> bool:
    """
    Return True when an activity is fully pinned (completed) for V2-A
    actual-date-anchored CPM (ADR-019, brief §4.3).

    A fully-pinned activity has BOTH pinned_early_start and pinned_early_finish
    set. Its forward-pass result is fixed at its actual dates and ignores all
    predecessor logic, so its INCOMING relationships are not real scheduling
    dependencies — they may be dropped for topological ordering.
    """
    return (
        getattr(activity, "pinned_early_start", None) is not None
        and getattr(activity, "pinned_early_finish", None) is not None
    )


def topological_sort(network: ActivityNetwork) -> list[str]:
    """
    Return activity IDs in topological (predecessor-before-successor) order.

    Uses Kahn's algorithm (BFS-based in-degree reduction). Newly unblocked
    activities are added in sorted ID order to produce a deterministic result
    for a given network.

    Isolated activities (no predecessors, no successors) are included in the
    result. Networks with multiple start or finish activities are handled
    correctly.

    V2-A actual-date-anchored CPM (ADR-019, brief §4.3): edges pointing INTO a
    fully-pinned (completed) activity are dropped before ordering, because a
    fully-pinned activity ignores predecessor logic — its incoming relationships
    are not data dependencies. This resolves cycles composed ENTIRELY of
    completed activities into a DAG (the OV-001-F1 / W4 case), exactly as P6
    tolerates as-built logic loops. GUARD: if a residual cycle remains after
    dropping those edges — i.e. the cycle contains at least one activity that is
    NOT fully pinned — NET-006 still fires (ValueError), because that is a
    genuine, un-progressed network defect, not an as-built artifact. Unpinned
    schedules behave exactly as before (no edges are dropped).

    Assumptions:
      - Relationship types do not affect ordering (all types impose a
        predecessor-before-successor constraint on scheduling sequence).
      - Determinism is achieved by sorting newly freed activity IDs at each step.

    Limitations:
      - Does not distinguish critical vs non-critical paths.
      - Cycle identification reports all activities involved, not the exact path.

    Args:
        network: A validated ActivityNetwork.

    Returns:
        List of activity IDs in valid topological order.

    Raises:
        ValueError: If the network contains a cycle that is not fully covered by
                    pinned activities. The error message identifies the activity
                    IDs involved.
    """
    activities = network.activities

    # V2-A: relationships whose successor is fully pinned are non-binding for
    # ordering. Dropping them lets all-completed cycles resolve to a DAG while
    # leaving unpinned networks unchanged.
    effective_rels = [
        rel for rel in network.relationships
        if not _is_fully_pinned(activities[rel.succ_id])
    ]

    in_degree: dict[str, int] = {act_id: 0 for act_id in activities}
    successors: dict[str, list[str]] = {act_id: [] for act_id in activities}
    for rel in effective_rels:
        in_degree[rel.succ_id] += 1
        successors[rel.pred_id].append(rel.succ_id)

    # Initialise queue with all zero-in-degree activities, sorted for determinism
    queue: deque[str] = deque(
        sorted(act_id for act_id, deg in in_degree.items() if deg == 0)
    )
    result: list[str] = []

    while queue:
        act_id = queue.popleft()
        result.append(act_id)

        # Reduce in-degree for each successor; collect newly freed nodes
        newly_free: list[str] = []
        for succ_id in successors.get(act_id, []):
            in_degree[succ_id] -= 1
            if in_degree[succ_id] == 0:
                newly_free.append(succ_id)

        # Add newly freed nodes in sorted order for determinism
        for freed_id in sorted(newly_free):
            queue.append(freed_id)

    if len(result) != len(activities):
        cyclic = sorted(
            act_id for act_id, deg in in_degree.items() if deg > 0
        )
        raise ValueError(
            f"Cycle detected in activity network. "
            f"Activities involved in cycle: {cyclic}. "
            "The forward-pass scheduler requires an acyclic network."
        )

    return result
