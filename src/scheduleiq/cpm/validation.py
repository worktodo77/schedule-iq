"""
Ported from the LI MIP 3.9 tool (mip39.validation) per ADR-0007 — port-and-validate.
Network validation framework for the MIP 3.9 Schedule Analysis Tool.

Provides forensic-grade network integrity checks that run before any CPM
calculation. Every finding is structured, traceable, and accompanied by a
source reference and analyst action. Results are deterministic.

Design philosophy (ADR-005):
  Validation never silently ignores conditions. Analysts receive complete
  diagnostics. The same inputs always produce the same ValidationResult
  in the same order.

Sources:
  SRC-001 CPW-P6 Manual pp. 8-12   — normalization checks
  SRC-007 AACE 49R-06              — open-ended activity risks; CP distortion
  SRC-008 AACE 24R-03              — relationship types; network integrity
  ADR-005                          — forensic defensibility requirements
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .models import Activity, Relationship


# ---------------------------------------------------------------------------
# Severity
# ---------------------------------------------------------------------------

class ValidationSeverity(Enum):
    """
    Issue severity for forensic schedule validation.

    INFO:     Informational. No analytical impact. Documents a notable condition.
    WARNING:  May distort results. Analyst review recommended before relying on output.
    ERROR:    Will produce incorrect results if unresolved. Analysis may proceed
              with caution.
    CRITICAL: Blocking. Analysis must not proceed until resolved.
    """
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

    def _order(self) -> int:
        return {"INFO": 3, "WARNING": 2, "ERROR": 1, "CRITICAL": 0}[self.value]

    def __lt__(self, other: "ValidationSeverity") -> bool:
        return self._order() < other._order()


# ---------------------------------------------------------------------------
# Issue catalog
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _CatalogEntry:
    description: str
    default_severity: ValidationSeverity
    source_reference: str
    analyst_action: str
    blocking: bool


ISSUE_CATALOG: dict[str, _CatalogEntry] = {
    "NET-001": _CatalogEntry(
        description=(
            "Activity has no predecessor relationships (start node). "
            "A valid CPM network has a single designated start node. "
            "Multiple unrestricted start nodes indicate missing logic."
        ),
        default_severity=ValidationSeverity.WARNING,
        source_reference="AACE 49R-06 (SRC-007) §2; AACE 24R-03 (SRC-008)",
        analyst_action=(
            "Confirm this is the intended project start node. "
            "If multiple start nodes exist, add missing predecessor relationships "
            "or connect activities to a project start milestone."
        ),
        blocking=False,
    ),
    "NET-002": _CatalogEntry(
        description=(
            "Activity has no successor relationships (open-ended / finish node). "
            "Open-ended activities receive TF=0 from most scheduling software, "
            "making them appear critical when they are not. "
            "A valid network has a single designated finish node."
        ),
        default_severity=ValidationSeverity.WARNING,
        source_reference="AACE 49R-06 (SRC-007) §2; AACE 24R-03 (SRC-008)",
        analyst_action=(
            "Confirm this is the intended project finish node. "
            "If it is not the intended finish, add successor relationships. "
            "Open-ended activities distort float and critical path identification."
        ),
        blocking=False,
    ),
    "NET-003": _CatalogEntry(
        description=(
            "Network has multiple activities with no predecessors (multiple start nodes). "
            "Forensic CPM analysis requires a single start node for unambiguous "
            "critical path and float identification."
        ),
        default_severity=ValidationSeverity.WARNING,
        source_reference="AACE 49R-06 (SRC-007) §2; CPW-P6 Manual (SRC-001) p. 10",
        analyst_action=(
            "Add missing predecessor relationships to connect these activities to "
            "the project start milestone, or document why multiple starts are intentional."
        ),
        blocking=False,
    ),
    "NET-004": _CatalogEntry(
        description=(
            "Network has multiple activities with no successors (multiple finish nodes). "
            "Forensic CPM analysis requires a single finish node for unambiguous "
            "project completion date and delay quantification."
        ),
        default_severity=ValidationSeverity.WARNING,
        source_reference="AACE 49R-06 (SRC-007) §2; CPW-P6 Manual (SRC-001) p. 10",
        analyst_action=(
            "Add missing successor relationships to connect these activities to "
            "the project finish milestone, or document why multiple finish nodes are intentional."
        ),
        blocking=False,
    ),
    "NET-005": _CatalogEntry(
        description=(
            "Relationship type is not a supported PDM type. "
            "The Phase 3 CPM engine supports FS, SS, FF, and SF relationship types "
            "per AACE 24R-03 (SRC-008). Any other relationship type cannot be "
            "processed by the scheduler and will be skipped."
        ),
        default_severity=ValidationSeverity.WARNING,
        source_reference="AACE 24R-03 (SRC-008); ADR-005",
        analyst_action=(
            "Remove or convert the unsupported relationship type to a valid PDM type "
            "(FS, SS, FF, or SF). Relationships of unknown type are skipped by the engine. "
            "If this represents an intentional constraint, describe it in the analysis report."
        ),
        blocking=False,
    ),
    "NET-006": _CatalogEntry(
        description=(
            "Circular dependency detected in the activity network. "
            "CPM forward-pass scheduling requires an acyclic directed graph. "
            "A cycle means two or more activities each depend on the other, "
            "making scheduling impossible."
        ),
        default_severity=ValidationSeverity.CRITICAL,
        source_reference="CPW-P6 Manual (SRC-001) p. 10; AACE 24R-03 (SRC-008)",
        analyst_action=(
            "Remove the circular logic before proceeding. "
            "Identify the cycle among the listed activities and break it "
            "by removing or redirecting at least one relationship."
        ),
        blocking=True,
    ),
    "NET-007": _CatalogEntry(
        description=(
            "Duplicate activity ID. Activity IDs must be unique within a schedule. "
            "Duplicate IDs prevent unambiguous analysis and network construction."
        ),
        default_severity=ValidationSeverity.CRITICAL,
        source_reference="CPW-P6 Manual (SRC-001) p. 10",
        analyst_action=(
            "Remove or rename all duplicate activity IDs. "
            "Analysis cannot proceed with duplicate IDs."
        ),
        blocking=True,
    ),
    "NET-008": _CatalogEntry(
        description=(
            "Duplicate relationship. Two or more relationships connect the same "
            "predecessor and successor with the same relationship type. "
            "The duplicate with the more restrictive lag typically controls."
        ),
        default_severity=ValidationSeverity.WARNING,
        source_reference="CPW-P6 Manual (SRC-001) p. 10",
        analyst_action=(
            "Remove the redundant relationship to clarify schedule logic. "
            "Retain the relationship with the more restrictive lag if they differ."
        ),
        blocking=False,
    ),
    "NET-009": _CatalogEntry(
        description=(
            "Self-referential relationship. An activity references itself as "
            "its own predecessor or successor. This creates a trivial cycle "
            "that prevents topological ordering."
        ),
        default_severity=ValidationSeverity.CRITICAL,
        source_reference="CPW-P6 Manual (SRC-001) p. 10",
        analyst_action=(
            "Remove the self-referential relationship. "
            "A self-loop cannot be processed by the CPM scheduler."
        ),
        blocking=True,
    ),
    "NET-010": _CatalogEntry(
        description=(
            "Invalid lag value. Lag must be a finite numeric value. "
            "None, NaN, or infinite lag values cannot be processed "
            "by the workday arithmetic engine."
        ),
        default_severity=ValidationSeverity.ERROR,
        source_reference="CPW-P6 Manual (SRC-001) pp. 41-42; CALC-002",
        analyst_action=(
            "Replace the invalid lag with a valid finite numeric value. "
            "Use 0 if no lag is intended. "
            "Negative lags (leads) are permitted as finite values."
        ),
        blocking=False,
    ),
    "NET-011": _CatalogEntry(
        description=(
            "Activity has a negative original duration. "
            "Negative durations are not physically meaningful and will produce "
            "incorrect Early Finish dates."
        ),
        default_severity=ValidationSeverity.ERROR,
        source_reference="CPW-P6 Manual (SRC-001) p. 10",
        analyst_action=(
            "Correct the negative duration. "
            "Zero-duration milestones (original_duration=0) are permitted. "
            "A negative value indicates a data entry error."
        ),
        blocking=False,
    ),
    "NET-012": _CatalogEntry(
        description=(
            "Activity is missing its original duration (original_duration=None). "
            "The forward-pass scheduler requires a duration for every activity."
        ),
        default_severity=ValidationSeverity.ERROR,
        source_reference="CPW-P6 Manual (SRC-001) p. 10",
        analyst_action=(
            "Assign an original duration before scheduling. "
            "Activities without durations cannot be scheduled."
        ),
        blocking=False,
    ),
    "NET-013": _CatalogEntry(
        description=(
            "Orphaned relationship. The relationship references an activity ID "
            "that does not exist in the network. The network cannot be "
            "constructed until this is resolved."
        ),
        default_severity=ValidationSeverity.CRITICAL,
        source_reference="CPW-P6 Manual (SRC-001) p. 10",
        analyst_action=(
            "Remove the orphaned relationship or add the missing activity. "
            "All relationship pred_id and succ_id values must exist in the "
            "activity list."
        ),
        blocking=True,
    ),
}


# ---------------------------------------------------------------------------
# ValidationIssue
# ---------------------------------------------------------------------------

@dataclass
class ValidationIssue:
    """
    A single validation finding.

    activity_ids and relationship_ids are sorted on construction for
    deterministic output.
    """
    issue_code: str
    severity: ValidationSeverity
    activity_ids: list[str] = field(default_factory=list)
    relationship_ids: list[tuple[str, str, str]] = field(default_factory=list)
    message: str = ""
    source_reference: str = ""
    analyst_action: str = ""
    blocking: bool = False

    def __post_init__(self) -> None:
        self.activity_ids = sorted(self.activity_ids)
        self.relationship_ids = sorted(self.relationship_ids)

    def to_dict(self) -> dict:
        return {
            "issue_code": self.issue_code,
            "severity": self.severity.value,
            "activity_ids": list(self.activity_ids),
            "relationship_ids": [list(r) for r in self.relationship_ids],
            "message": self.message,
            "source_reference": self.source_reference,
            "analyst_action": self.analyst_action,
            "blocking": self.blocking,
        }


def _make_issue(
    code: str,
    activity_ids: Optional[list[str]] = None,
    relationship_ids: Optional[list[tuple[str, str, str]]] = None,
    message: Optional[str] = None,
    severity_override: Optional[ValidationSeverity] = None,
) -> ValidationIssue:
    entry = ISSUE_CATALOG[code]
    return ValidationIssue(
        issue_code=code,
        severity=severity_override if severity_override is not None else entry.default_severity,
        activity_ids=list(activity_ids or []),
        relationship_ids=list(relationship_ids or []),
        message=message if message is not None else entry.description,
        source_reference=entry.source_reference,
        analyst_action=entry.analyst_action,
        blocking=entry.blocking,
    )


# ---------------------------------------------------------------------------
# ValidationResult
# ---------------------------------------------------------------------------

_SEV_ORDER = {
    ValidationSeverity.CRITICAL: 0,
    ValidationSeverity.ERROR: 1,
    ValidationSeverity.WARNING: 2,
    ValidationSeverity.INFO: 3,
}


@dataclass
class ValidationResult:
    """
    Aggregated output of a network validation pass.

    Issues are sorted: CRITICAL first, then by issue_code, then by first
    activity_id. This ordering is deterministic for the same input.
    """
    issues: list[ValidationIssue] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._sort()

    def _sort(self) -> None:
        self.issues.sort(
            key=lambda i: (
                _SEV_ORDER[i.severity],
                i.issue_code,
                i.activity_ids[0] if i.activity_ids else "",
            )
        )

    # --- Aggregate properties ---

    @property
    def has_blocking_issues(self) -> bool:
        return any(i.blocking for i in self.issues)

    @property
    def has_critical(self) -> bool:
        return any(i.severity == ValidationSeverity.CRITICAL for i in self.issues)

    @property
    def has_errors(self) -> bool:
        return any(i.severity == ValidationSeverity.ERROR for i in self.issues)

    @property
    def has_warnings(self) -> bool:
        return any(i.severity == ValidationSeverity.WARNING for i in self.issues)

    @property
    def is_clean(self) -> bool:
        return len(self.issues) == 0

    # --- Filtering ---

    def issues_by_severity(self, severity: ValidationSeverity) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == severity]

    def issues_by_code(self, code: str) -> list[ValidationIssue]:
        return [i for i in self.issues if i.issue_code == code]

    # --- Summary ---

    def summary(self) -> dict[str, int]:
        counts: dict[str, int] = {s.value: 0 for s in ValidationSeverity}
        for issue in self.issues:
            counts[issue.severity.value] += 1
        return counts

    # --- Mutation (re-sorts after each call) ---

    def add(self, issue: ValidationIssue) -> None:
        self.issues.append(issue)
        self._sort()

    def extend(self, issues: list[ValidationIssue]) -> None:
        self.issues.extend(issues)
        self._sort()

    def to_list(self) -> list[dict]:
        return [i.to_dict() for i in self.issues]


# ---------------------------------------------------------------------------
# NetworkValidator
# ---------------------------------------------------------------------------

class NetworkValidator:
    """
    Forensic-grade network integrity validator.

    Operates on raw lists of Activity and Relationship objects — not on a
    constructed ActivityNetwork. This allows reporting ALL issues before any
    one of them causes construction to fail.

    All checks are deterministic: the same inputs always produce the same
    ValidationResult in the same order.

    validate_all() runs every check and combines the results. Individual check
    methods can be called in isolation for targeted diagnostics.

    Sources:
        SRC-001 CPW-P6 Manual pp. 8-12
        SRC-007 AACE 49R-06
        SRC-008 AACE 24R-03
        ADR-005 (forensic defensibility)
    """

    def __init__(
        self,
        activities: list[Activity],
        relationships: list[Relationship],
    ) -> None:
        self._activities = list(activities)
        self._relationships = list(relationships)

        # Build ID lookup structures (handle duplicates gracefully)
        self._act_id_counts: dict[str, int] = {}
        for a in activities:
            self._act_id_counts[a.act_id] = self._act_id_counts.get(a.act_id, 0) + 1
        self._all_act_ids: set[str] = set(self._act_id_counts)

    # ------------------------------------------------------------------
    # Primary entry point
    # ------------------------------------------------------------------

    def validate_all(self) -> ValidationResult:
        """
        Run all checks in a fixed order. All issues are collected before
        returning — early failures do not prevent later checks from running.
        """
        result = ValidationResult()
        # Structural integrity first (blocking issues)
        result.extend(self.check_duplicate_activity_ids())
        result.extend(self.check_orphaned_relationships())
        result.extend(self.check_self_referential_relationships())
        result.extend(self.check_duplicate_relationships())
        # Data quality
        result.extend(self.check_missing_durations())
        result.extend(self.check_negative_durations())
        result.extend(self.check_invalid_lags())
        # Relationship type support
        result.extend(self.check_unsupported_relationship_types())
        # Network topology
        result.extend(self.check_circular_logic())
        result.extend(self.check_network_topology())
        return result

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    def check_duplicate_activity_ids(self) -> list[ValidationIssue]:
        """NET-007: activities sharing an ID."""
        return [
            _make_issue(
                "NET-007",
                activity_ids=[aid],
                message=(
                    f"Duplicate activity ID {aid!r} appears "
                    f"{count} times in the activity list."
                ),
            )
            for aid, count in sorted(self._act_id_counts.items())
            if count > 1
        ]

    def check_orphaned_relationships(self) -> list[ValidationIssue]:
        """NET-013: relationships referencing unknown activity IDs."""
        issues: list[ValidationIssue] = []
        seen: set[tuple[str, str, str]] = set()
        for rel in sorted(self._relationships, key=lambda r: (r.pred_id, r.succ_id, r.rel_type)):
            for missing_id in sorted({rel.pred_id, rel.succ_id} - self._all_act_ids):
                key = (missing_id, rel.pred_id, rel.succ_id)
                if key not in seen:
                    seen.add(key)
                    issues.append(_make_issue(
                        "NET-013",
                        activity_ids=[missing_id],
                        relationship_ids=[(rel.pred_id, rel.succ_id, rel.rel_type)],
                        message=(
                            f"Relationship {rel.pred_id!r} → {rel.succ_id!r} "
                            f"({rel.rel_type}) references unknown activity {missing_id!r}."
                        ),
                    ))
        return issues

    def check_self_referential_relationships(self) -> list[ValidationIssue]:
        """NET-009: pred_id == succ_id."""
        seen: set[str] = set()
        issues: list[ValidationIssue] = []
        for rel in sorted(self._relationships, key=lambda r: (r.pred_id, r.rel_type)):
            if rel.pred_id == rel.succ_id and rel.pred_id not in seen:
                seen.add(rel.pred_id)
                issues.append(_make_issue(
                    "NET-009",
                    activity_ids=[rel.pred_id],
                    relationship_ids=[(rel.pred_id, rel.succ_id, rel.rel_type)],
                    message=(
                        f"Activity {rel.pred_id!r} has a self-referential "
                        f"{rel.rel_type} relationship."
                    ),
                ))
        return issues

    def check_duplicate_relationships(self) -> list[ValidationIssue]:
        """NET-008: identical (pred_id, succ_id, rel_type) tuples."""
        counts: dict[tuple[str, str, str], int] = {}
        for rel in self._relationships:
            key = (rel.pred_id, rel.succ_id, rel.rel_type)
            counts[key] = counts.get(key, 0) + 1
        return [
            _make_issue(
                "NET-008",
                activity_ids=sorted({pred, succ}),
                relationship_ids=[(pred, succ, rtype)],
                message=(
                    f"Relationship {pred!r} → {succ!r} ({rtype}) "
                    f"appears {n} times."
                ),
            )
            for (pred, succ, rtype), n in sorted(counts.items())
            if n > 1
        ]

    def check_missing_durations(self) -> list[ValidationIssue]:
        """NET-012: original_duration is None."""
        return [
            _make_issue(
                "NET-012",
                activity_ids=[a.act_id],
                message=f"Activity {a.act_id!r} has original_duration=None.",
            )
            for a in sorted(self._activities, key=lambda x: x.act_id)
            if a.original_duration is None
        ]

    def check_negative_durations(self) -> list[ValidationIssue]:
        """NET-011: original_duration < 0."""
        return [
            _make_issue(
                "NET-011",
                activity_ids=[a.act_id],
                message=(
                    f"Activity {a.act_id!r} has negative "
                    f"original_duration={a.original_duration}."
                ),
            )
            for a in sorted(self._activities, key=lambda x: x.act_id)
            if a.original_duration is not None and a.original_duration < 0
        ]

    def check_invalid_lags(self) -> list[ValidationIssue]:
        """NET-010: lag is None, NaN, or infinite."""
        issues: list[ValidationIssue] = []
        for rel in sorted(self._relationships, key=lambda r: (r.pred_id, r.succ_id, r.rel_type)):
            lag = rel.lag
            if lag is None or (isinstance(lag, float) and (math.isnan(lag) or math.isinf(lag))):
                issues.append(_make_issue(
                    "NET-010",
                    activity_ids=sorted([rel.pred_id, rel.succ_id]),
                    relationship_ids=[(rel.pred_id, rel.succ_id, rel.rel_type)],
                    message=(
                        f"Relationship {rel.pred_id!r} → {rel.succ_id!r} "
                        f"({rel.rel_type}) has invalid lag={lag!r}."
                    ),
                ))
        return issues

    _SUPPORTED_RELATIONSHIP_TYPES: frozenset[str] = frozenset({"FS", "SS", "FF", "SF"})

    def check_unsupported_relationship_types(self) -> list[ValidationIssue]:
        """NET-005: relationship type not in the supported set {FS, SS, FF, SF}."""
        issues: list[ValidationIssue] = []
        for rel in sorted(self._relationships, key=lambda r: (r.rel_type, r.pred_id, r.succ_id)):
            if rel.rel_type not in self._SUPPORTED_RELATIONSHIP_TYPES:
                issues.append(_make_issue(
                    "NET-005",
                    activity_ids=sorted([rel.pred_id, rel.succ_id]),
                    relationship_ids=[(rel.pred_id, rel.succ_id, rel.rel_type)],
                    message=(
                        f"Relationship {rel.pred_id!r} → {rel.succ_id!r} "
                        f"uses unsupported type {rel.rel_type!r}. "
                        "Supported types are FS, SS, FF, SF (AACE 24R-03). "
                        "This relationship will be skipped by the scheduler."
                    ),
                ))
        return issues

    def check_circular_logic(self) -> list[ValidationIssue]:
        """
        NET-006: cycle detection using Kahn's algorithm.

        Runs on the set of unique, known activity IDs. Self-loops are excluded
        (detected separately as NET-009).

        V2-A actual-date-anchored CPM (ADR-019, brief §4.3): edges pointing INTO
        a fully-pinned (completed) activity are dropped before cycle detection,
        consistent with topological_sort(). A fully-pinned activity ignores
        predecessor logic, so its incoming relationships are not real
        dependencies. This lets cycles composed ENTIRELY of completed activities
        pass validation (P6 tolerates as-built logic loops). GUARD: a cycle that
        still survives — i.e. contains an activity that is NOT fully pinned —
        still raises NET-006 and blocks. Unpinned schedules are unchanged
        (no activity is fully pinned, so no edges are dropped).
        """
        valid_ids = self._all_act_ids
        fully_pinned_ids = {
            a.act_id for a in self._activities
            if a.act_id in valid_ids
            and getattr(a, "pinned_early_start", None) is not None
            and getattr(a, "pinned_early_finish", None) is not None
        }
        in_degree: dict[str, int] = {aid: 0 for aid in valid_ids}
        succs: dict[str, list[str]] = {aid: [] for aid in valid_ids}

        for rel in self._relationships:
            if (rel.pred_id in valid_ids and rel.succ_id in valid_ids
                    and rel.pred_id != rel.succ_id
                    and rel.succ_id not in fully_pinned_ids):
                in_degree[rel.succ_id] += 1
                succs[rel.pred_id].append(rel.succ_id)

        queue: deque[str] = deque(
            sorted(aid for aid, deg in in_degree.items() if deg == 0)
        )
        visited: set[str] = set()
        while queue:
            aid = queue.popleft()
            visited.add(aid)
            # ``in_degree`` is incremented once per relationship row above.
            # Decrement once per row as well: multiple PDM relationship types
            # between one endpoint pair are legal constraints, and must not
            # strand the successor as a false cycle.  This also keeps the
            # validator's multigraph bookkeeping identical to topological_sort.
            for succ in sorted(succs.get(aid, [])):
                in_degree[succ] -= 1
                if in_degree[succ] == 0:
                    queue.append(succ)

        cyclic_ids = sorted(aid for aid in valid_ids if aid not in visited)
        if not cyclic_ids:
            return []
        return [_make_issue(
            "NET-006",
            activity_ids=cyclic_ids,
            message=(
                f"Circular dependency detected among {len(cyclic_ids)} activities: "
                f"{cyclic_ids}."
            ),
        )]

    def check_network_topology(self) -> list[ValidationIssue]:
        """
        NET-001, NET-002, NET-003, NET-004: start-node and finish-node analysis.

        A valid network has exactly one start node (no predecessors) and one
        finish node (no successors). Reports:
          NET-003 aggregate + NET-001 per-activity when >1 start nodes.
          NET-004 aggregate + NET-002 per-activity when >1 finish nodes.

        A single start node or a single finish node generates no issues.
        """
        valid_ids = self._all_act_ids
        has_predecessor: set[str] = set()
        has_successor: set[str] = set()
        for rel in self._relationships:
            if rel.pred_id in valid_ids and rel.succ_id in valid_ids:
                has_predecessor.add(rel.succ_id)
                has_successor.add(rel.pred_id)

        start_nodes = sorted(valid_ids - has_predecessor)
        finish_nodes = sorted(valid_ids - has_successor)
        issues: list[ValidationIssue] = []

        if len(start_nodes) > 1:
            issues.append(_make_issue(
                "NET-003",
                activity_ids=start_nodes,
                message=(
                    f"Network has {len(start_nodes)} start nodes "
                    f"(activities with no predecessors): {start_nodes}."
                ),
            ))
            for aid in start_nodes:
                issues.append(_make_issue(
                    "NET-001",
                    activity_ids=[aid],
                    message=(
                        f"Activity {aid!r} has no predecessor relationships "
                        f"(one of {len(start_nodes)} start nodes)."
                    ),
                ))

        if len(finish_nodes) > 1:
            issues.append(_make_issue(
                "NET-004",
                activity_ids=finish_nodes,
                message=(
                    f"Network has {len(finish_nodes)} finish nodes "
                    f"(activities with no successors): {finish_nodes}."
                ),
            ))
            for aid in finish_nodes:
                issues.append(_make_issue(
                    "NET-002",
                    activity_ids=[aid],
                    message=(
                        f"Activity {aid!r} has no successor relationships "
                        f"(open-ended; one of {len(finish_nodes)} finish nodes). "
                        "Open-ended activities receive TF=0, distorting float "
                        "and critical path identification."
                    ),
                ))

        return issues
