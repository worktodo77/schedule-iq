"""
Ported from the LI MIP 3.9 tool (mip39.calendar_registry) per ADR-0007 — port-and-validate.
INFRA-019: Multi-Calendar Registry and Lag Calendar Strategy (V1-B.1).

CalendarRegistry stores multiple Calendar objects keyed by their XER clndr_id,
builds per-calendar workday tables on demand, and provides deterministic lookup
for the engine's per-activity calendar resolution.

LagCalendarStrategy governs which calendar is used for lag workday arithmetic
in a multi-calendar schedule. The strategy must be explicitly configured — no
hidden defaults (ADR-007).

Governance:
    - Every calendar registered with its raw clndr_data and parse status.
    - All workday tables built from the same date range for consistency.
    - Default calendar (project clndr_id from XER PROJECT record) tracked explicitly.
    - CalendarRegistry.summary() serialisable for provenance embedding.

Source authority: ADR-007 (normalization governance), ADR-012 (multi-calendar).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

from .calendar_ops import build_workday_table
from .models import Calendar


# ---------------------------------------------------------------------------
# Lag calendar strategy
# ---------------------------------------------------------------------------

class LagCalendarStrategy(enum.Enum):
    """
    Governs which calendar is used for lag workday arithmetic.

    In CPW-P6, lag is measured in workdays of the predecessor's calendar
    by default (CPW-P6 Manual, lag analysis section). This is the recommended
    default for forensic CPW-equivalent analysis (D-V1-005).

    Members:
        PREDECESSOR_CALENDAR   — lag measured in predecessor activity's calendar.
                                 CPW-aligned default. Documented in NormalizationDecision.
        SUCCESSOR_CALENDAR     — lag measured in successor activity's calendar.
        PROJECT_DEFAULT_CALENDAR — lag measured in the project's default calendar.
        CONTINUOUS_24H         — lag measured in a 7-day calendar (every day is
                                 a workday). Equivalent to calendar-day lag rather
                                 than workday lag.

    Every strategy selection must be logged as a NormalizationDecision so that
    analysts can verify the assumption in the analytical trail.
    """
    PREDECESSOR_CALENDAR = "predecessor_calendar"
    SUCCESSOR_CALENDAR = "successor_calendar"
    PROJECT_DEFAULT_CALENDAR = "project_default_calendar"
    CONTINUOUS_24H = "continuous_24h"

    @classmethod
    def from_str(cls, value: str) -> "LagCalendarStrategy":
        for member in cls:
            if member.value == value:
                return member
        valid = [m.value for m in cls]
        raise ValueError(
            f"Unknown LagCalendarStrategy {value!r}. Valid values: {valid}"
        )


# ---------------------------------------------------------------------------
# Calendar entry
# ---------------------------------------------------------------------------

@dataclass
class CalendarEntry:
    """
    One calendar in the registry, with raw source data and parse metadata.

    Fields:
        clndr_id       — Raw clndr_id from the XER CALENDAR record (key in registry).
        calendar       — Parsed Calendar object (work_days, hours_per_day, exception_dates).
        raw_clndr_data — Raw clndr_data string from XER, preserved verbatim (ADR-007).
        parse_status   — "PARSED": all recognized; "PARTIAL": some sections skipped;
                         "DEFERRED": format unrecognized, Mon-Fri default applied.
        parse_notes    — Human-readable explanation of parse outcome.
    """
    clndr_id: str
    calendar: Calendar
    raw_clndr_data: str = ""
    parse_status: str = "DEFERRED"  # PARSED | PARTIAL | DEFERRED
    parse_notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "clndr_id": self.clndr_id,
            "calendar_name": self.calendar.name,
            "work_days": sorted(self.calendar.work_days),
            "hours_per_day": self.calendar.hours_per_day,
            "exception_date_count": len(self.calendar.exception_dates),
            "exception_dates": sorted(
                d.isoformat() for d in self.calendar.exception_dates
            ),
            "raw_clndr_data_length": len(self.raw_clndr_data),
            "parse_status": self.parse_status,
            "parse_notes": self.parse_notes,
        }


# ---------------------------------------------------------------------------
# Calendar registry
# ---------------------------------------------------------------------------

class CalendarRegistry:
    """
    Registry of multiple Calendar objects, keyed by XER clndr_id.

    Stores CalendarEntry objects (calendar + raw data + parse metadata).
    Builds per-calendar workday tables lazily over a requested date range.
    Provides deterministic lookup for the engine's multi-calendar pass.

    Usage pattern:
        1. Importer registers each CALENDAR record via register().
        2. Importer sets the project default via set_default(clndr_id).
        3. Engine calls build_workday_tables(start, end) before analysis.
        4. Engine uses get_workday_table(clndr_id) for per-activity arithmetic.

    Governance:
        - No silent fallbacks: get() returns None for unknown clndr_ids.
          Callers must handle None explicitly and log the fallback decision.
        - register() raises ValueError on duplicate clndr_id to prevent
          silent overwrite of an already-registered calendar.
        - summary() is deterministic: calendars sorted by clndr_id.
    """

    def __init__(self) -> None:
        self._entries: dict[str, CalendarEntry] = {}
        self._workday_tables: dict[str, dict[date, int]] = {}
        self._default_clndr_id: Optional[str] = None
        self._table_range: Optional[tuple[date, date]] = None
        # Special 24h calendar for CONTINUOUS_24H lag strategy
        self._continuous_24h_calendar: Calendar = Calendar(
            name="continuous_24h",
            work_days={1, 2, 3, 4, 5, 6, 7},
            hours_per_day=24.0,
        )
        self._continuous_24h_table: Optional[dict[date, int]] = None

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, entry: CalendarEntry) -> None:
        """
        Register a CalendarEntry. Raises ValueError on duplicate clndr_id.

        Governance: no silent overwrite of already-registered calendars.
        """
        if entry.clndr_id in self._entries:
            raise ValueError(
                f"CalendarRegistry: clndr_id {entry.clndr_id!r} is already "
                f"registered as {self._entries[entry.clndr_id].calendar.name!r}. "
                "Duplicate registration is not permitted."
            )
        self._entries[entry.clndr_id] = entry

    def set_default(self, clndr_id: str) -> None:
        """
        Set the project-default calendar by clndr_id.

        The default is used when an activity has no calendar_id or when the
        lag strategy is PROJECT_DEFAULT_CALENDAR. The clndr_id need not be
        registered yet (it will be resolved at lookup time).
        """
        self._default_clndr_id = clndr_id

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get(self, clndr_id: str) -> Optional[Calendar]:
        """Return the Calendar for clndr_id, or None if not registered."""
        entry = self._entries.get(clndr_id)
        return entry.calendar if entry else None

    def get_entry(self, clndr_id: str) -> Optional[CalendarEntry]:
        """Return the full CalendarEntry for clndr_id, or None."""
        return self._entries.get(clndr_id)

    def get_default(self) -> Optional[Calendar]:
        """
        Return the project-default Calendar, or None if no default is set.
        Falls back to the first registered calendar if default clndr_id is
        unregistered (with deterministic ordering: lowest clndr_id string).
        """
        if self._default_clndr_id:
            cal = self.get(self._default_clndr_id)
            if cal is not None:
                return cal
        # Fallback: first registered calendar in sorted order
        if self._entries:
            first_id = sorted(self._entries.keys())[0]
            return self._entries[first_id].calendar
        return None

    def get_default_clndr_id(self) -> Optional[str]:
        """Return the configured default clndr_id, or None."""
        return self._default_clndr_id

    def get_continuous_24h_calendar(self) -> Calendar:
        """Return the synthetic 7-day continuous calendar for CONTINUOUS_24H lag."""
        return self._continuous_24h_calendar

    # ------------------------------------------------------------------
    # Workday tables
    # ------------------------------------------------------------------

    def _rebuild_all(self, lo: date, hi: date) -> None:
        """Rebuild ALL per-calendar tables + the continuous-24h table over
        [lo, hi] **atomically**: every table is built into temporaries first and
        only committed once they ALL succeed, so a mid-build failure (e.g. a
        calendar with no workdays in range — a disclosed hard error, never a
        silent single-calendar fallback) leaves the prior coverage intact
        (ADR-029 r2, Codex guardrail 1)."""
        new_tables: dict[str, dict[date, int]] = {}
        for clndr_id, entry in self._entries.items():
            new_tables[clndr_id] = build_workday_table(entry.calendar, lo, hi)
        new_24h = build_workday_table(self._continuous_24h_calendar, lo, hi)
        # Commit only after every build above succeeded.
        self._workday_tables = new_tables
        self._continuous_24h_table = new_24h
        self._table_range = (lo, hi)

    def build_workday_tables(self, start: date, end: date) -> None:
        """
        Build (replace) workday tables for all registered calendars over EXACTLY
        [start, end]. The same date range is used for all calendars so that
        cross-calendar date comparisons are coherent within the engine. Also
        builds the continuous-24h table for the CONTINUOUS_24H lag strategy.

        Prefer ``ensure_workday_tables()`` in new code — it is range-aware and
        idempotent. This explicit-range form is retained for callers/tests that
        intentionally (re)build over a specific range.
        """
        if start > end:
            raise ValueError(
                f"build_workday_tables: start {start} is after end {end}."
            )
        self._rebuild_all(start, end)

    def ensure_workday_tables(self, start: date, end: date) -> None:
        """
        Range-aware build (ADR-029 r2): guarantee the per-calendar tables cover
        [start, end]. Idempotent when already covered; otherwise (re)builds over
        the **superset** ``[min(existing_start, start), max(existing_end, end)]``
        so a later/wider analysis window never reuses a too-narrow earlier build.
        Atomic (see ``_rebuild_all``). This is the one call the shared window/run
        resource builder uses — engines should never depend on the bare boolean
        ``tables_built()`` as a coverage gate.
        """
        if start > end:
            raise ValueError(
                f"ensure_workday_tables: start {start} is after end {end}."
            )
        if self.tables_cover(start, end):
            return
        if self._table_range is not None:
            lo = min(self._table_range[0], start)
            hi = max(self._table_range[1], end)
        else:
            lo, hi = start, end
        self._rebuild_all(lo, hi)

    def tables_cover(self, start: date, end: date) -> bool:
        """True iff the built tables cover [start, end] — the range-aware gate
        engines must use instead of ``tables_built()`` (ADR-029 r2, Codex P1b)."""
        if self._table_range is None:
            return False
        return self._table_range[0] <= start and end <= self._table_range[1]

    @property
    def table_start(self) -> Optional[date]:
        """The start of the currently-built coverage range, or None."""
        return self._table_range[0] if self._table_range else None

    @property
    def table_end(self) -> Optional[date]:
        """The end of the currently-built coverage range, or None."""
        return self._table_range[1] if self._table_range else None

    def get_workday_table(self, clndr_id: str) -> Optional[dict[date, int]]:
        """
        Return the pre-built workday table for clndr_id.

        Returns None if clndr_id is not registered or tables have not been
        built yet. Callers must call build_workday_tables() first.
        """
        return self._workday_tables.get(clndr_id)

    def get_default_workday_table(self) -> Optional[dict[date, int]]:
        """Return the workday table for the project-default calendar."""
        if self._default_clndr_id and self._default_clndr_id in self._workday_tables:
            return self._workday_tables[self._default_clndr_id]
        if self._workday_tables:
            first_id = sorted(self._workday_tables.keys())[0]
            return self._workday_tables[first_id]
        return None

    def get_continuous_24h_table(self) -> Optional[dict[date, int]]:
        """Return the pre-built workday table for the continuous-24h calendar."""
        return self._continuous_24h_table

    # ------------------------------------------------------------------
    # Lag strategy resolution
    # ------------------------------------------------------------------

    def resolve_lag_resources(
        self,
        strategy: LagCalendarStrategy,
        pred_clndr_id: Optional[str],
        succ_clndr_id: Optional[str],
        fallback_calendar: Calendar,
        fallback_table: dict[date, int],
    ) -> tuple[Calendar, dict[date, int]]:
        """
        Return the (calendar, workday_table) to use for lag arithmetic.

        Resolves the lag calendar according to strategy. Falls back to
        fallback_calendar/fallback_table when the required calendar is
        unavailable. The fallback is the caller's responsibility to document
        as a NormalizationDecision.

        Args:
            strategy:          The configured LagCalendarStrategy.
            pred_clndr_id:     clndr_id of the predecessor activity (may be None).
            succ_clndr_id:     clndr_id of the successor activity (may be None).
            fallback_calendar: Calendar to use when the primary is unavailable.
            fallback_table:    Workday table to use when the primary is unavailable.

        Returns:
            (calendar, workday_table) — both non-None.
        """
        def _lookup(clndr_id: Optional[str]) -> Optional[tuple[Calendar, dict[date, int]]]:
            if clndr_id is None:
                return None
            cal = self.get(clndr_id)
            tbl = self.get_workday_table(clndr_id)
            if cal is not None and tbl is not None:
                return cal, tbl
            return None

        if strategy == LagCalendarStrategy.CONTINUOUS_24H:
            tbl = self.get_continuous_24h_table()
            if tbl is not None:
                return self._continuous_24h_calendar, tbl
            return fallback_calendar, fallback_table

        if strategy == LagCalendarStrategy.PREDECESSOR_CALENDAR:
            result = _lookup(pred_clndr_id)
            if result:
                return result

        elif strategy == LagCalendarStrategy.SUCCESSOR_CALENDAR:
            result = _lookup(succ_clndr_id)
            if result:
                return result

        elif strategy == LagCalendarStrategy.PROJECT_DEFAULT_CALENDAR:
            default_cal = self.get_default()
            if default_cal is not None:
                default_id = self._default_clndr_id
                if default_id:
                    default_tbl = self.get_workday_table(default_id)
                    if default_tbl is not None:
                        return default_cal, default_tbl
                # fallback: first registered table
                default_tbl = self.get_default_workday_table()
                if default_tbl is not None:
                    return default_cal, default_tbl

        return fallback_calendar, fallback_table

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def calendar_count(self) -> int:
        return len(self._entries)

    def calendar_ids(self) -> list[str]:
        """Sorted list of registered clndr_ids."""
        return sorted(self._entries.keys())

    def tables_built(self) -> bool:
        """True if any build has happened. **Derived predicate only** — do NOT
        use as a correctness gate (ADR-029 r2, Codex P1b): it does not prove the
        current window's range is covered. Use ``tables_cover(start, end)``."""
        return self._table_range is not None

    def summary(self) -> dict[str, Any]:
        """Serialisable summary for provenance embedding."""
        return {
            "calendar_count": len(self._entries),
            "default_clndr_id": self._default_clndr_id,
            "tables_built": self.tables_built(),
            "table_range": (
                [self._table_range[0].isoformat(), self._table_range[1].isoformat()]
                if self._table_range else None
            ),
            "calendars": [
                self._entries[cid].to_dict()
                for cid in sorted(self._entries.keys())
            ],
        }
