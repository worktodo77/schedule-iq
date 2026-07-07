"""Per-period start/finish compliance metrics (Fuse parity backlog F4;
docs/FUSE_PARITY.md "Baseline compliance group ... per-period start/finish
compliance variants planned (backlog)").

What this adds beyond DCMA-11/-14 and EVM-01
----------------------------------------------
DCMA-11 (missed tasks) and DCMA-14 (BEI) are *cumulative*, evaluated once per
file against everything due by that file's data date.  ``trend.series``'
EVM-01 "Hit Task %" is a *per-period FINISH* metric: of activities baselined
to finish within a window, the share whose actual finish landed on/before
that baseline finish (0-day tolerance only, one rate).

This module is a distinct, complementary cut: **per-period, tolerance-
banded, START-and-FINISH** compliance, plus a **START-side commitment-
reliability rate** that EVM-01 does not compute at all (EVM-01 only ever
looks at finishes).  Concretely, for each consecutive pair of schedules
(a "window"):

* **Start/finish compliance (0d and 7d tolerance, both reported)** — of
  activities that *actually* started (resp. finished) during the window,
  the share that did so on/before their planned/baseline start (resp.
  finish) plus the stated tolerance.  This is a population defined by
  *actual* occurrence in the window, unlike EVM-01's population (defined by
  when the activity was *baselined* to finish).
* **Commitment reliability (per-period Hit rate)** — of activities that were
  *planned* to start during the window (regardless of whether they actually
  did), the share that actually started at any point during the window.
  This measures whether the plan-to-start commitment was kept at all
  ("did work start when promised"), independent of whether the start was
  exactly on time — a question EVM-01 never asks, since EVM-01 is finish-
  only and cumulative-vs-baseline rather than commitment-vs-window.

Basis (documented convention)
------------------------------
Planned/baseline start and finish are read as ``baseline_start or
planned_start`` and ``baseline_finish or planned_finish`` respectively, off
the LATER schedule's activity record (the file as of the window's end) —
the same "baseline when present else planned/target" convention
``metrics.checks.core`` uses for DCMA-11/-13/-14 (see
``core.dcma11_missed_tasks``, ``core.dcma14_bei``).  Each window's basis mix
(how many activities used baseline vs. planned vs. had neither) is disclosed
via ``no_basis_start_count``/``no_basis_finish_count`` rather than being
silently absorbed into a denominator.  Days-late is calendar days (date
subtraction), consistent with ``TRD-04``/``DAT-04``'s convention elsewhere
in this codebase — not working days.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional

from ..ingest.model import Schedule

TOLERANCE_DAYS = (0, 7)

LABEL = ("PRELIMINARY — per-period start/finish compliance rates are "
        "diagnostic; entitlement (EOT/compensation) and causation for any "
        "late start or finish are reserved to the expert.")


# --------------------------------------------------------------------------
# result dataclasses
# --------------------------------------------------------------------------
@dataclass
class ComplianceOffender:
    code: str
    name: str
    basis_date: Optional[datetime]
    actual_date: Optional[datetime]
    days_late: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "basis_date": self.basis_date.isoformat() if self.basis_date else None,
            "actual_date": self.actual_date.isoformat() if self.actual_date else None,
            "days_late": self.days_late,
        }


@dataclass
class ComplianceWindow:
    earlier_label: str
    later_label: str
    basis: str = ""
    started_population: int = 0
    finished_population: int = 0
    start_compliance_pct_0d: Optional[float] = None
    start_compliance_pct_7d: Optional[float] = None
    finish_compliance_pct_0d: Optional[float] = None
    finish_compliance_pct_7d: Optional[float] = None
    planned_to_start_count: int = 0
    actually_started_count: int = 0
    commitment_reliability_pct: Optional[float] = None
    late_starts: list[ComplianceOffender] = field(default_factory=list)
    late_finishes: list[ComplianceOffender] = field(default_factory=list)
    no_basis_start_count: int = 0
    no_basis_finish_count: int = 0
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "earlier_label": self.earlier_label,
            "later_label": self.later_label,
            "basis": self.basis,
            "started_population": self.started_population,
            "finished_population": self.finished_population,
            "start_compliance_pct_0d": self.start_compliance_pct_0d,
            "start_compliance_pct_7d": self.start_compliance_pct_7d,
            "finish_compliance_pct_0d": self.finish_compliance_pct_0d,
            "finish_compliance_pct_7d": self.finish_compliance_pct_7d,
            "planned_to_start_count": self.planned_to_start_count,
            "actually_started_count": self.actually_started_count,
            "commitment_reliability_pct": self.commitment_reliability_pct,
            "late_starts": [o.to_dict() for o in self.late_starts],
            "late_finishes": [o.to_dict() for o in self.late_finishes],
            "no_basis_start_count": self.no_basis_start_count,
            "no_basis_finish_count": self.no_basis_finish_count,
            "reason": self.reason,
        }


@dataclass
class ComplianceAnalysis:
    windows: list[ComplianceWindow] = field(default_factory=list)
    trend: dict[str, list[Optional[float]]] = field(default_factory=dict)
    order: list[str] = field(default_factory=list)
    reason: str = ""
    label: str = LABEL

    def to_dict(self) -> dict[str, Any]:
        return {
            "windows": [w.to_dict() for w in self.windows],
            "trend": {k: list(v) for k, v in sorted(self.trend.items())},
            "order": list(self.order),
            "reason": self.reason,
            "label": self.label,
        }


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _basis_start(a) -> Optional[datetime]:
    return a.baseline_start or a.planned_start


def _basis_finish(a) -> Optional[datetime]:
    return a.baseline_finish or a.planned_finish


def _rate(hit: int, den: int) -> Optional[float]:
    return 100.0 * hit / den if den else None


# --------------------------------------------------------------------------
# main entry point
# --------------------------------------------------------------------------
def period_compliance(schedules: list[Schedule]) -> ComplianceAnalysis:
    ca = ComplianceAnalysis()
    if not schedules:
        ca.reason = "no schedules supplied"
        return ca
    order = sorted(schedules, key=lambda s: (s.data_date or s.export_date
                                              or s.start_date or datetime.min))
    ca.order = [s.label() for s in order]
    if len(order) < 2:
        ca.reason = "need at least two schedules to compute per-period compliance"
        return ca

    trend_keys = ["start_compliance_0d", "start_compliance_7d",
                 "finish_compliance_0d", "finish_compliance_7d",
                 "commitment_reliability"]
    ca.trend = {k: [] for k in trend_keys}

    for i in range(len(order) - 1):
        earlier, later = order[i], order[i + 1]
        w = ComplianceWindow(earlier_label=earlier.label(), later_label=later.label())
        if earlier.data_date is None or later.data_date is None:
            w.reason = "one or both schedules in this window lack a data date"
            ca.windows.append(w)
            for k in trend_keys:
                ca.trend[k].append(None)
            continue

        dd_e, dd_l = earlier.data_date, later.data_date
        later_acts = [a for a in later.real_activities]

        n_baseline = n_planned = n_missing = 0
        started_offenders_0d: list[ComplianceOffender] = []
        finished_offenders_0d: list[ComplianceOffender] = []
        started_on_time = {0: 0, 7: 0}
        started_with_basis = 0
        finished_on_time = {0: 0, 7: 0}
        finished_with_basis = 0
        no_basis_start = no_basis_finish = 0
        started_codes: set[str] = set()
        planned_start_codes: set[str] = set()

        for a in later_acts:
            bstart, bfinish = _basis_start(a), _basis_finish(a)
            if a.baseline_start or a.baseline_finish:
                n_baseline += 1
            elif a.planned_start or a.planned_finish:
                n_planned += 1
            else:
                n_missing += 1

            # -- started-in-window population -----------------------------
            if a.actual_start and dd_e < a.actual_start <= dd_l:
                started_codes.add(a.code)
                if bstart is None:
                    no_basis_start += 1
                else:
                    started_with_basis += 1
                    for tol in TOLERANCE_DAYS:
                        if a.actual_start <= bstart + timedelta(days=tol):
                            started_on_time[tol] += 1
                    if a.actual_start > bstart:
                        started_offenders_0d.append(ComplianceOffender(
                            code=a.code, name=a.name, basis_date=bstart,
                            actual_date=a.actual_start,
                            days_late=float((a.actual_start - bstart).days)))

            # -- finished-in-window population -----------------------------
            if a.actual_finish and dd_e < a.actual_finish <= dd_l:
                if bfinish is None:
                    no_basis_finish += 1
                else:
                    finished_with_basis += 1
                    for tol in TOLERANCE_DAYS:
                        if a.actual_finish <= bfinish + timedelta(days=tol):
                            finished_on_time[tol] += 1
                    if a.actual_finish > bfinish:
                        finished_offenders_0d.append(ComplianceOffender(
                            code=a.code, name=a.name, basis_date=bfinish,
                            actual_date=a.actual_finish,
                            days_late=float((a.actual_finish - bfinish).days)))

            # -- planned-to-start-in-window population (commitment) --------
            if bstart is not None and dd_e < bstart <= dd_l:
                planned_start_codes.add(a.code)

        finished_pop = sum(1 for a in later_acts
                           if a.actual_finish and dd_e < a.actual_finish <= dd_l)

        w.basis = (f"baseline {n_baseline}, planned {n_planned}, "
                  f"missing {n_missing} (of {len(later_acts)} activities)")
        w.started_population = len(started_codes)
        w.finished_population = finished_pop
        w.start_compliance_pct_0d = _rate(started_on_time[0], started_with_basis)
        w.start_compliance_pct_7d = _rate(started_on_time[7], started_with_basis)
        w.finish_compliance_pct_0d = _rate(finished_on_time[0], finished_with_basis)
        w.finish_compliance_pct_7d = _rate(finished_on_time[7], finished_with_basis)
        w.planned_to_start_count = len(planned_start_codes)
        w.actually_started_count = len(started_codes)
        w.commitment_reliability_pct = _rate(
            len(planned_start_codes & started_codes), len(planned_start_codes))
        w.late_starts = sorted(started_offenders_0d, key=lambda o: (-o.days_late, o.code))
        w.late_finishes = sorted(finished_offenders_0d, key=lambda o: (-o.days_late, o.code))
        w.no_basis_start_count = no_basis_start
        w.no_basis_finish_count = no_basis_finish

        ca.windows.append(w)
        ca.trend["start_compliance_0d"].append(w.start_compliance_pct_0d)
        ca.trend["start_compliance_7d"].append(w.start_compliance_pct_7d)
        ca.trend["finish_compliance_0d"].append(w.finish_compliance_pct_0d)
        ca.trend["finish_compliance_7d"].append(w.finish_compliance_pct_7d)
        ca.trend["commitment_reliability"].append(w.commitment_reliability_pct)

    return ca
