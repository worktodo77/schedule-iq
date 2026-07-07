"""
Ported from the LI MIP 3.9 tool (mip39.models) per ADR-0007 — port-and-validate.
Data model skeleton for the MIP 3.9 Schedule Analysis Tool.

Defines the core dataclasses used across Phase 2 calculations:
  Activity    — a schedule activity with actual/early dates and progress fields
  Relationship — a predecessor/successor link between activities
  Calendar    — a workday calendar with configurable work days, hours/day,
                and non-work exception dates (V1-B.1 multi-calendar support)

V1-B.1 additions (backward-compatible):
  Activity.calendar_id — optional assigned calendar ID from XER (clndr_id)
  Calendar.exception_dates — frozenset of non-work exception dates (e.g. holidays)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class Activity:
    """
    A single schedule activity.

    Date fields use Python date objects. None means the field is not set
    (e.g., a not-yet-started activity has no Actual Start).

    Fields follow P6/CPW naming conventions:
      act_id       — unique activity identifier
      actual_start — Actual Start (AS)
      actual_finish — Actual Finish (AF)
      early_start  — Early Start (ES), CPM-calculated
      early_finish — Early Finish (EF), CPM-calculated
      original_duration — Original Duration in workdays (OD)
      actual_duration   — Actual Duration in workdays (AD)
      remaining_duration — Remaining Duration in workdays (RD)
      percent_complete  — Percent Complete as a float in [0.0, 1.0]
      calendar_id  — XER clndr_id of the activity's assigned calendar (V1-B.1).
                     None for activities created without calendar binding.
      constraint_type — Optional constraint classification string; values map to
                        ConstraintType enum names (e.g. "mandatory_start",
                        "start_on"). Stored as str to avoid circular imports.
      constraint_date — Optional date associated with constraint_type.
      pinned_early_start  — V2-A actual-date-anchored CPM (ADR-019). When set,
                        the forward pass fixes Early Start at this date and
                        ignores predecessor-derived constraints. A pinned date
                        means "this activity is fixed here because it actually
                        occurred here; do not compute it from predecessor logic."
                        None (default) → unpinned, fully backward-compatible.
      pinned_early_finish — V2-A actual-date-anchored CPM (ADR-019). When set
                        together with pinned_early_start, the activity is treated
                        as completed: Early Finish is fixed here and predecessor
                        logic is ignored. When pinned_early_start is set but this
                        is None, the activity is in-progress: ES is pinned and EF
                        is computed forward from remaining duration. None (default).
    """

    act_id: str
    actual_start: Optional[date] = None
    actual_finish: Optional[date] = None
    early_start: Optional[date] = None
    early_finish: Optional[date] = None
    original_duration: Optional[float] = None
    actual_duration: Optional[float] = None
    remaining_duration: Optional[float] = None
    percent_complete: Optional[float] = None
    calendar_id: Optional[str] = None  # V1-B.1: assigned calendar from XER
    constraint_type: Optional[str] = None
    constraint_date: Optional[date] = None
    # V2-A: actual-date-anchored CPM ("pinning"; ADR-019). Both None by default.
    pinned_early_start: Optional[date] = None
    pinned_early_finish: Optional[date] = None


@dataclass
class Relationship:
    """
    A predecessor/successor relationship between two activities.

    Fields:
      pred_id  — activity ID of the predecessor
      succ_id  — activity ID of the successor
      rel_type — relationship type: "FS", "SS", "FF", or "SF"
      lag      — lag in workdays (may be negative for lead)
    """

    pred_id: str
    succ_id: str
    rel_type: str  # "FS" | "SS" | "FF" | "SF"
    lag: float = 0.0

    def __post_init__(self) -> None:
        valid_types = {"FS", "SS", "FF", "SF"}
        if self.rel_type not in valid_types:
            raise ValueError(
                f"Relationship rel_type must be one of {valid_types}; "
                f"got {self.rel_type!r} for {self.pred_id!r} -> {self.succ_id!r}"
            )


@dataclass
class Calendar:
    """
    Workday calendar with configurable work week and non-work exception dates.

    V1-B.1 extends the original Mon-Fri-only model to support:
      - Configurable work week (any set of ISO weekday numbers)
      - Named non-work exception dates (holidays, project-specific shutdowns)
    Backward-compatible: exception_dates defaults to empty frozenset.

    Fields:
      name            — human-readable calendar name
      work_days       — set of ISO weekday numbers that are workdays
                        (1=Monday … 7=Sunday; default {1,2,3,4,5})
      hours_per_day   — working hours per workday (default 8)
      exception_dates — frozenset of specific non-work dates regardless of weekday.
                        Holidays, project shutdowns, etc. (V1-B.1).
    """

    name: str
    work_days: set[int] = field(default_factory=lambda: {1, 2, 3, 4, 5})
    hours_per_day: float = 8.0
    exception_dates: frozenset = field(default_factory=frozenset)  # frozenset[date]

    def __post_init__(self) -> None:
        valid_iso = set(range(1, 8))
        if not self.work_days:
            raise ValueError("Calendar must have at least one work day.")
        invalid = self.work_days - valid_iso
        if invalid:
            raise ValueError(
                f"work_days contains invalid ISO weekday numbers: {invalid}. "
                "Use 1=Monday through 7=Sunday."
            )
        if self.hours_per_day <= 0:
            raise ValueError(
                f"hours_per_day must be positive; got {self.hours_per_day}."
            )

    def is_workday(self, d: date) -> bool:
        """Return True if d is a workday: correct weekday AND not a named exception."""
        if d in self.exception_dates:
            return False
        return d.isoweekday() in self.work_days
