"""The ADR-0007 validation handshake (E4): engine output vs schedule of record.

Before any engine-dependent feature runs, the ported CPM engine re-schedules the
file exactly as imported — actual-date-anchored ("pinning", ADR-019), honoring
its P6 date constraints (LIM-028) and the project's scheduling options
(lag-calendar strategy + retained-logic / progress-override statusing) — and its
computed dates and floats are compared, field by field, to the tool-of-record
values stored IN the file.  The match rate is check **SET-02**; below the
configured threshold (default 99%), engine-dependent features refuse to run and
the mismatches are listed.

Presentation discipline (ADR-0007 §4): the tool-of-record dates remain the only
dates reported as *the schedule*.  The engine output is a diagnostic delta, never
a competing schedule; this module never writes back to the record.

Tolerance (LIM-044, CARRIED not fixed): the comparison tolerance is
**calendar-day based**, not workday based — a Friday finish and the following
Monday finish are one CPM day apart but three calendar days apart, so the
default ``TOLERANCE_CALENDAR_AWARE`` policy allows date fields to differ by up to
1 calendar day and float fields by up to 1 workday.  The TolerancePolicy is an
explicit, named choice exposed on every ``run_handshake`` call and recorded on
the result (no hidden tolerance — ADR-005).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Optional

from ..ingest.model import Schedule
from .bridge import build_engine_inputs
from .compare import (ReferenceSchedule, ReferenceScheduledActivity,
                     TOLERANCE_CALENDAR_AWARE, TolerancePolicy, compare_schedules)
from .compare.policies import ComparisonPolicy
from .conventions import EFConvention
from .engine import run_analysis


_MISMATCH_CAP = 200


class HandshakeRefusal(Exception):
    """Raised by ``require_valid_handshake`` when the engine-vs-record match rate
    is below the configured threshold — the refusal gate for engine-dependent
    features (ADR-0007 §3)."""


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class HandshakeResult:
    match_rate_pct: float
    threshold_pct: float
    passed: bool
    total_activities: int
    within_tolerance: int
    exact_match: int
    divergent: int
    mismatches: list[dict[str, Any]]
    convention: str
    lag_strategy: str
    statusing_mode: str
    tolerance_policy: str
    disclosures: list[str] = field(default_factory=list)
    constraint_applications: int = 0
    engine_is_valid: bool = True
    blocking_issues: list[str] = field(default_factory=list)
    mismatch_truncated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "match_rate_pct": round(self.match_rate_pct, 2),
            "threshold_pct": self.threshold_pct,
            "passed": self.passed,
            "total_activities": self.total_activities,
            "within_tolerance": self.within_tolerance,
            "exact_match": self.exact_match,
            "divergent": self.divergent,
            "convention": self.convention,
            "lag_strategy": self.lag_strategy,
            "statusing_mode": self.statusing_mode,
            "tolerance_policy": self.tolerance_policy,
            "constraint_applications": self.constraint_applications,
            "engine_is_valid": self.engine_is_valid,
            "blocking_issues": list(self.blocking_issues),
            "mismatch_truncated": self.mismatch_truncated,
            "mismatches": list(self.mismatches),
            "disclosures": list(self.disclosures),
        }


# ---------------------------------------------------------------------------
# build_reference — the schedule of record as a comparison ReferenceSchedule
# ---------------------------------------------------------------------------

def _round_half_away(x: float) -> int:
    """Round half away from zero to the nearest integer (P6/CPW convention)."""
    if x >= 0:
        return int(math.floor(x + 0.5))
    return int(math.ceil(x - 0.5))


def _hpd(sched: Schedule, act) -> float:
    cal = sched.cal_for(act)
    return cal.hours_per_day if (cal and cal.hours_per_day) else 8.0


def build_reference(sched: Schedule) -> ReferenceSchedule:
    """Build a ReferenceSchedule from the file's stored tool-of-record values.

    Per real activity, the stored early/late dates, total/free float (hours ->
    workdays via the activity calendar hours/day, rounded half away from zero),
    criticality, and floored original duration are carried through. Completed
    activities are remapped for the engine's status semantics: their actual
    start/finish dates become the reference early start/finish (ADR-019 pins
    completed work to those dates), while P6 late fields are omitted because
    they are status artifacts. ``None`` reference fields are skipped by the
    comparison framework, so a file that does not store (say) late dates simply
    does not have them compared.
    """
    ref = ReferenceSchedule(
        schedule_id=f"record::{sched.project_id or sched.project_name or 'schedule'}",
        description="Schedule of record (stored tool-of-record CPM values).",
        source="schedule of record (XER)",
        tool=sched.source_tool or "unknown",
        lag_strategy_assumed=(sched.settings.relationship_lag_calendar or "unknown"),
        calendar_convention="p6_compatibility",
    )
    thr_hr = sched.settings.critical_float_threshold_hours
    missing_completed_actuals: list[str] = []
    for a in sched.real_activities:
        if a.completed and (a.actual_start is None or a.actual_finish is None):
            # Do not let a malformed completed row fall through to the
            # duration-only comparison.  Leaving it out of the reference
            # population is honest; run_handshake surfaces the count below.
            missing_completed_actuals.append(a.code or a.uid)
            continue
        hpd = _hpd(sched, a)
        tf = (_round_half_away(a.total_float_hours / hpd)
             if a.total_float_hours is not None else None)
        ff = (_round_half_away(a.free_float_hours / hpd)
             if a.free_float_hours is not None else None)
        if a.is_critical_flag is not None:
            crit: Optional[bool] = a.is_critical_flag
        elif a.total_float_hours is not None and thr_hr is not None:
            crit = a.total_float_hours <= thr_hr
        else:
            crit = None
        od = 0 if a.is_milestone else int(math.floor(a.original_duration_hours / hpd + 1e-9))
        # P6 exports use the data date as a placeholder in the stored early
        # fields for completed activities.  The engine deliberately pins
        # completed work to actual dates (ADR-019), so remap the reference to
        # those actuals.  Late fields remain unset because P6's completed-status
        # late dates are not a comparable forecast; the actual dates provide a
        # falsifiable pinning check instead of a duration-only pass.
        if a.completed:
            early_start = a.actual_start.date() if a.actual_start else None
            early_finish = a.actual_finish.date() if a.actual_finish else None
            late_start = late_finish = None
        else:
            early_start = a.early_start.date() if a.early_start else None
            early_finish = a.early_finish.date() if a.early_finish else None
            late_start = a.late_start.date() if a.late_start else None
            late_finish = a.late_finish.date() if a.late_finish else None

        ref.add_activity(ReferenceScheduledActivity(
            act_id=a.uid,
            early_start=early_start,
            early_finish=early_finish,
            late_start=late_start,
            late_finish=late_finish,
            total_float=tf,
            free_float=ff,
            is_critical=crit,
            original_duration=od,
            notes=a.code,
        ))
    if missing_completed_actuals:
        ref.notes = (
            "SET-02 excluded "
            f"{len(missing_completed_actuals)} completed activit"
            f"{'y' if len(missing_completed_actuals) == 1 else 'ies'} "
            "from the comparison population because actual start/finish "
            "dates were incomplete."
        )
    return ref


# ---------------------------------------------------------------------------
# run_handshake — the engine run + comparison, cached
# ---------------------------------------------------------------------------

# Module-level cache so SET-02 (and future engine-dependent features) do not
# re-run the engine per check.  Keyed by (file identity, threshold, tolerance,
# convention).
_HANDSHAKE_CACHE: dict[tuple, HandshakeResult] = {}


def _cache_key(sched: Schedule, threshold_pct: float,
               tolerance: TolerancePolicy, convention: EFConvention) -> tuple:
    ident = sched.source_sha256 or f"id:{id(sched)}"
    return (ident, threshold_pct, tolerance.name, convention.value)


def run_handshake(
    sched: Schedule,
    threshold_pct: float = 99.0,
    tolerance: TolerancePolicy = TOLERANCE_CALENDAR_AWARE,
    convention: EFConvention = EFConvention.P6_COMPATIBILITY,
) -> HandshakeResult:
    """Re-schedule ``sched`` with the ported engine and compare to the record.

    Returns a serializable ``HandshakeResult``.  When the network fails the
    engine's ``NetworkValidator`` (blocking issues -> ``is_valid=False``), the
    handshake is a FAIL with ``match_rate_pct=0.0`` and the blocking issues
    listed.  Result objects are cached per (file, threshold, tolerance,
    convention)."""
    key = _cache_key(sched, threshold_pct, tolerance, convention)
    cached = _HANDSHAKE_CACHE.get(key)
    if cached is not None:
        return cached

    inputs = build_engine_inputs(sched, convention=convention)
    constraint_log: list = []
    result = run_analysis(
        activities=inputs.activities,
        relationships=inputs.relationships,
        project_start=inputs.project_start,
        workday_table=inputs.workday_table,
        calendar=inputs.calendar,
        convention=convention,
        calendar_registry=inputs.calendar_registry,
        lag_strategy=inputs.lag_strategy,
        constraints=inputs.constraints or None,
        statusing_mode=inputs.statusing_mode,
        constraint_log_out=constraint_log,
    )

    reference = build_reference(sched)
    if reference.notes:
        inputs.disclosures.append(reference.notes)

    if not result.is_valid:
        blocking = [f"{i.issue_code}: {i.message}"
                   for i in result.validation.issues if i.blocking]
        hs = HandshakeResult(
            match_rate_pct=0.0,
            threshold_pct=threshold_pct,
            passed=False,
            total_activities=len(inputs.activities),
            within_tolerance=0,
            exact_match=0,
            divergent=len(inputs.activities),
            mismatches=[],
            convention=convention.value,
            lag_strategy=inputs.lag_strategy.value,
            statusing_mode=inputs.statusing_mode.value,
            tolerance_policy=tolerance.name,
            disclosures=inputs.disclosures,
            constraint_applications=len(constraint_log),
            engine_is_valid=False,
            blocking_issues=blocking,
        )
        _HANDSHAKE_CACHE[key] = hs
        return hs

    comparison = compare_schedules(
        analysis_result=result,
        reference=reference,
        policy=ComparisonPolicy.ADVISORY,   # never block here; SET-02 is the gate
        tolerance_policy=tolerance,
        calendar_registry=inputs.calendar_registry,
        context="ADR-0007 validation handshake (SET-02)",
    )
    metrics = comparison.metrics

    # Per-field mismatches, engine value vs record value, named by code.
    mismatches: list[dict[str, Any]] = []
    truncated = False
    for ac in comparison.activity_comparisons:
        if not ac.has_divergences:
            continue
        code = inputs.code_by_uid.get(ac.act_id, ac.act_id)
        for fc in ac.field_comparisons:
            if fc.skipped or fc.is_within_tolerance:
                continue
            if len(mismatches) >= _MISMATCH_CAP:
                truncated = True
                break
            mismatches.append({
                "act_id": ac.act_id,
                "code": code,
                "field": fc.field,
                "engine": _ser(fc.mip39_value),
                "record": _ser(fc.reference_value),
                "delta": fc.delta,
            })
        if truncated:
            break

    match_rate = metrics.activity_match_pct
    hs = HandshakeResult(
        match_rate_pct=match_rate,
        threshold_pct=threshold_pct,
        passed=match_rate >= threshold_pct,
        total_activities=metrics.total_activities,
        within_tolerance=metrics.within_tolerance_activities,
        exact_match=metrics.exact_match_activities,
        divergent=metrics.divergent_activities,
        mismatches=mismatches,
        convention=convention.value,
        lag_strategy=inputs.lag_strategy.value,
        statusing_mode=inputs.statusing_mode.value,
        tolerance_policy=tolerance.name,
        disclosures=inputs.disclosures,
        constraint_applications=len(constraint_log),
        engine_is_valid=True,
        blocking_issues=[],
        mismatch_truncated=truncated,
    )
    _HANDSHAKE_CACHE[key] = hs
    return hs


def _ser(v: Any) -> Any:
    """Serialize a date to isoformat, leave everything else as-is."""
    iso = getattr(v, "isoformat", None)
    if callable(iso) and not isinstance(v, (int, float, bool)):
        return iso()
    return v


def require_valid_handshake(
    sched: Schedule,
    threshold_pct: float = 99.0,
    tolerance: TolerancePolicy = TOLERANCE_CALENDAR_AWARE,
    convention: EFConvention = EFConvention.P6_COMPATIBILITY,
) -> HandshakeResult:
    """Run the handshake and raise ``HandshakeRefusal`` when below threshold.

    Engine-dependent features call this as their gate: a passing result is
    returned; a failing one raises with the match rate, threshold, and (when the
    network was invalid) the blocking validation issues."""
    hs = run_handshake(sched, threshold_pct=threshold_pct,
                      tolerance=tolerance, convention=convention)
    if not hs.passed:
        if not hs.engine_is_valid:
            detail = ("engine network validation failed (" +
                     "; ".join(hs.blocking_issues[:5]) + ")")
        else:
            detail = (f"match rate {hs.match_rate_pct:.1f}% is below the "
                     f"{hs.threshold_pct:.0f}% threshold "
                     f"({hs.divergent} of {hs.total_activities} activities diverge)")
        raise HandshakeRefusal(
            "ADR-0007 validation handshake refused: " + detail +
            ". Engine-dependent features will not run against this file; the "
            "tool-of-record dates remain the schedule.")
    return hs


def clear_handshake_cache() -> None:
    """Clear the module-level handshake cache (test/tooling helper)."""
    _HANDSHAKE_CACHE.clear()
