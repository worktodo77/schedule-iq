"""Multi-file series analysis: ordering, same-project detection, metric
trending, and the series (TRD-*/EVM-*) checks computed across updates.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from ..compare.diff import ChangeSet, compare
from ..ingest.model import Calendar, PercentCompleteType, Schedule
from ..metrics.engine import (CheckDef, Finding, MetricResult,
                              ScheduleAssessment, evaluate, judge,
                              load_matrix)


@dataclass
class SeriesWarning:
    kind: str
    message: str


@dataclass
class SeriesAnalysis:
    schedules: list[Schedule]                       # ordered by data date
    assessments: list[ScheduleAssessment] = field(default_factory=list)
    changesets: list[ChangeSet] = field(default_factory=list)   # n-1 pairs
    series_results: list[MetricResult] = field(default_factory=list)
    warnings: list[SeriesWarning] = field(default_factory=list)

    @property
    def is_series(self) -> bool:
        return len(self.schedules) >= 2

    def metric_trend(self, check_id: str) -> list[Optional[float]]:
        out = []
        for a in self.assessments:
            r = a.result(check_id)
            out.append(r.value if r else None)
        return out

    @property
    def labels(self) -> list[str]:
        return [s.label() for s in self.schedules]


def _code_overlap(a: Schedule, b: Schedule) -> float:
    ca = {x.code for x in a.activities.values()}
    cb = {x.code for x in b.activities.values()}
    if not ca or not cb:
        return 0.0
    return len(ca & cb) / min(len(ca), len(cb))


def order_and_validate(schedules: list[Schedule]) -> tuple[list[Schedule], list[SeriesWarning]]:
    """Order by data date (auto-detect) and flag files that do not look like
    the same project (analyst confirms in the GUI before running)."""
    warnings: list[SeriesWarning] = []
    ordered = sorted(schedules, key=lambda s: (s.data_date or s.export_date
                                               or s.start_date))
    for i in range(1, len(ordered)):
        ov = _code_overlap(ordered[0], ordered[i])
        if ov < 0.5:
            warnings.append(SeriesWarning(
                "project-mismatch",
                f"{ordered[i].label()} shares only {ov:.0%} of activity IDs with "
                f"{ordered[0].label()} — confirm these are updates of the same "
                "project (otherwise run cross-project benchmarking instead)."))
        if ordered[i].data_date and ordered[i - 1].data_date \
                and ordered[i].data_date == ordered[i - 1].data_date:
            warnings.append(SeriesWarning(
                "duplicate-data-date",
                f"{ordered[i].label()} has the same data date as "
                f"{ordered[i - 1].label()}."))
    return ordered, warnings


def _cd(matrix, cid) -> CheckDef:
    for c in matrix:
        if c.id == cid:
            return c
    raise KeyError(cid)


def _working_hours_between(cal: Optional[Calendar],
                           start: datetime, end: datetime) -> float:
    """Working hours available on ``cal`` between two data dates (DUR-04
    branch 1).  Counts each workday at hours_per_day via Calendar.is_workday;
    without a calendar, assumes Mon-Fri at 8h.  Iteration is defensively
    capped at 5 years."""
    if start >= end:
        return 0.0
    hpd = cal.hours_per_day if cal and cal.hours_per_day else 8.0
    d, end_d = start.date(), end.date()
    cap = d + timedelta(days=5 * 365)
    total = 0.0
    while d < end_d and d < cap:
        if cal is not None:
            if cal.is_workday(d):
                total += hpd
        elif d.isoweekday() <= 5:
            total += hpd
        d += timedelta(days=1)
    return total


def analyze_series(schedules: list[Schedule],
                   overrides: dict[str, float] | None = None) -> SeriesAnalysis:
    matrix = load_matrix()
    ordered, warnings = order_and_validate(schedules)
    sa = SeriesAnalysis(schedules=ordered, warnings=warnings)
    sa.assessments = [evaluate(s, matrix, overrides) for s in ordered]
    if not sa.is_series:
        return sa
    sa.changesets = [compare(ordered[i], ordered[i + 1])
                     for i in range(len(ordered) - 1)]
    ov = overrides or {}

    def thr(cid):
        c = _cd(matrix, cid)
        return ov.get(cid, c.threshold), c

    # ---- TRD-01 float erosion ------------------------------------------
    t, cd = thr("TRD-01")
    per, finds = [], []
    for cs in sa.changesets:
        deltas = [d for d in cs.float_deltas.values()]
        if deltas:
            mean = sum(deltas) / len(deltas)
            per.append(mean)
            finds.append(Finding(f"{cs.earlier.label()} -> {cs.later.label()}", "",
                                 f"mean TF change {mean:+.1f}d; "
                                 f"min TF change {min(deltas):+.1f}d"))
    v = sum(per) / len(per) if per else 0.0
    sa.series_results.append(judge(cd, v, t, finds, None, None,
                                   f"Mean total-float movement {v:+.1f} working days "
                                   "per update (negative = erosion)."))

    # ---- TRD-02 critical path stability --------------------------------
    t, cd = thr("TRD-02")
    jacs, finds = [], []
    for cs in sa.changesets:
        j = cs.critical_path_jaccard
        if j is not None:
            jacs.append(j)
            gained = cs.critical_after - cs.critical_before
            lost = cs.critical_before - cs.critical_after
            finds.append(Finding(f"{cs.earlier.label()} -> {cs.later.label()}", "",
                                 f"overlap {j:.0%}; joined CP: "
                                 f"{', '.join(sorted(gained)) or 'none'}; left CP: "
                                 f"{', '.join(sorted(lost)) or 'none'}"))
    v = sum(jacs) / len(jacs) if jacs else 1.0
    sa.series_results.append(judge(cd, v, t, finds, None, None,
                                   f"Average critical-set overlap between updates "
                                   f"{v:.0%} (1.00 = perfectly stable)."))

    # ---- TRD-03 logic churn --------------------------------------------
    t, cd = thr("TRD-03")
    churns, finds = [], []
    for cs in sa.changesets:
        churns.append(cs.logic_churn_pct)
        cts = cs.summary_counts()
        finds.append(Finding(f"{cs.earlier.label()} -> {cs.later.label()}", "",
                             f"{cts['relationships added']} added, "
                             f"{cts['relationships deleted']} deleted, "
                             f"{cts['relationships modified']} modified "
                             f"({cs.logic_churn_pct:.1f}% churn)"))
    v = max(churns) if churns else 0.0
    sa.series_results.append(judge(cd, v, t, finds, None, None,
                                   f"Peak logic churn {v:.1f}% of network per update."))

    # ---- TRD-04 forecast slippage --------------------------------------
    t, cd = thr("TRD-04")
    rates, finds = [], []
    for cs in sa.changesets:
        e, l = cs.earlier, cs.later
        if e.finish_date and l.finish_date and e.data_date and l.data_date:
            dd_days = (l.data_date - e.data_date).days
            slip = (l.finish_date - e.finish_date).days
            rate = slip / dd_days if dd_days else 0.0
            rates.append(rate)
            finds.append(Finding(f"{e.label()} -> {l.label()}", "",
                                 f"finish moved {slip:+d} cal days over {dd_days} "
                                 f"days elapsed (rate {rate:+.2f})"))
    v = sum(rates) / len(rates) if rates else 0.0
    sa.series_results.append(judge(cd, v, t, finds, None, None,
                                   f"Average completion slip rate {v:+.2f} "
                                   "(days of slip per elapsed day; > 0 slipping, "
                                   "> 1 slipping faster than time passes)."))

    # ---- TRD-05 retroactive actual changes ------------------------------
    t, cd = thr("TRD-05")
    finds = []
    for cs in sa.changesets:
        for ch in cs.actual_date_changes:
            finds.append(Finding(ch.code, ch.name,
                                 f"{ch.field}: {ch.before} -> {ch.after} "
                                 f"({cs.earlier.label()} -> {cs.later.label()})"))
    v = float(len(finds))
    sa.series_results.append(judge(cd, v, t, finds, len(finds), None,
                                   f"{len(finds)} retroactive change(s) to previously "
                                   "reported actual dates."))

    # ---- TRD-06 duration changes ----------------------------------------
    t, cd = thr("TRD-06")
    finds = []
    for cs in sa.changesets:
        for ch in cs.duration_changes:
            finds.append(Finding(ch.code, ch.name,
                                 f"OD {ch.before} -> {ch.after}"
                                 + (f" [{ch.flag}]" if ch.flag else "")
                                 + f" ({cs.later.label()})"))
    v = float(len(finds))
    sa.series_results.append(judge(cd, v, t, finds, len(finds), None,
                                   f"{len(finds)} original-duration change(s) across "
                                   "the series."))

    # ---- TRD-07 scope churn ---------------------------------------------
    t, cd = thr("TRD-07")
    finds, total = [], 0
    for cs in sa.changesets:
        n = len(cs.added) + len(cs.deleted)
        total += n
        finds.append(Finding(f"{cs.earlier.label()} -> {cs.later.label()}", "",
                             f"{len(cs.added)} added "
                             f"({', '.join(a.code for a in cs.added[:8]) or '—'}); "
                             f"{len(cs.deleted)} deleted "
                             f"({', '.join(a.code for a in cs.deleted[:8]) or '—'})"))
    sa.series_results.append(judge(cd, float(total), t, finds, total, None,
                                   f"{total} activities added or deleted across "
                                   "the series."))

    # ---- TRD-08 plan date changes ---------------------------------------
    t, cd = thr("TRD-08")
    finds = []
    for cs in sa.changesets:
        for ch in cs.planned_date_changes:
            finds.append(Finding(ch.code, ch.name,
                                 f"{ch.field}: {ch.before} -> {ch.after} "
                                 f"({cs.later.label()})"))
    v = float(len(finds))
    sa.series_results.append(judge(cd, v, t, finds, len(finds), None,
                                   f"{len(finds)} planned-date change(s) without "
                                   "re-baseline across the series."))

    # ---- EVM-01 Hit Task % ----------------------------------------------
    t, cd = thr("EVM-01")
    hits, finds = [], []
    for cs in sa.changesets:
        e, l = cs.earlier, cs.later
        if not (e.data_date and l.data_date):
            continue
        base = {a.code: (a.baseline_finish or a.planned_finish)
                for a in e.activities.values() if not a.is_loe_or_summary}
        due = {c: bf for c, bf in base.items()
               if bf and e.data_date < bf <= l.data_date}
        if not due:
            continue
        l_by = {a.code: a for a in l.activities.values()}
        hit = sum(1 for c, bf in due.items()
                  if (a := l_by.get(c)) and a.actual_finish and a.actual_finish <= bf)
        pct = 100.0 * hit / len(due)
        hits.append(pct)
        finds.append(Finding(f"{e.label()} -> {l.label()}", "",
                             f"{hit}/{len(due)} baselined finishes hit ({pct:.0f}%)"))
    v = sum(hits) / len(hits) if hits else 0.0
    sa.series_results.append(judge(cd, v, t if hits else None, finds, None, None,
                                   f"Average Hit Task {v:.0f}% per period."
                                   if hits else "No period had baselined finishes."))

    # ---- EVM-02 CEI -------------------------------------------------------
    t, cd = thr("EVM-02")
    ceis, finds = [], []
    for cs in sa.changesets:
        e, l = cs.earlier, cs.later
        if not (e.data_date and l.data_date):
            continue
        fc = {a.code for a in e.activities.values()
              if not a.is_loe_or_summary and not a.completed
              and (a.early_finish or a.planned_finish)
              and e.data_date < (a.early_finish or a.planned_finish) <= l.data_date}
        if not fc:
            continue
        l_by = {a.code: a for a in l.activities.values()}
        did = sum(1 for c in fc
                  if (a := l_by.get(c)) and a.actual_finish
                  and a.actual_finish <= l.data_date)
        cei = did / len(fc)
        ceis.append(cei)
        finds.append(Finding(f"{e.label()} -> {l.label()}", "",
                             f"{did}/{len(fc)} forecast finishes achieved "
                             f"(CEI {cei:.2f})"))
    v = sum(ceis) / len(ceis) if ceis else 0.0
    sa.series_results.append(judge(cd, v, t if ceis else None, finds, None, None,
                                   f"Average CEI {v:.2f} per period."
                                   if ceis else "No period had forecast finishes."))

    # ---- SET-01 scheduling-settings drift --------------------------------
    t, cd = thr("SET-01")
    finds = []
    setting_fields = ["retained_logic", "progress_override",
                      "relationship_lag_calendar", "critical_float_threshold_hours",
                      "make_open_ends_critical", "use_expected_finish"]
    for cs in sa.changesets:
        es, ls = cs.earlier.settings, cs.later.settings
        for f in setting_fields:
            ev, lv = getattr(es, f), getattr(ls, f)
            if ev != lv:
                finds.append(Finding(f"{cs.earlier.label()} -> {cs.later.label()}", f,
                                     f"{f}: {ev} -> {lv}"))
    v = float(len(finds))
    sa.series_results.append(judge(cd, v, t, finds, len(finds), None,
                                   f"{len(finds)} scheduling-settings change(s) between "
                                   "updates."))

    # ---- CAL-04 calendar definition changes -------------------------------
    t, cd = thr("CAL-04")
    finds = []
    for cs in sa.changesets:
        for ch in cs.calendar_def_changes:
            finds.append(Finding(ch.code, ch.name,
                                 f"{ch.field}: {ch.before} -> {ch.after} "
                                 f"({cs.later.label()})"))
    v = float(len(finds))
    sa.series_results.append(judge(cd, v, t, finds, len(finds), None,
                                   f"{len(finds)} calendar definition change(s) across "
                                   "the series."))

    # ---- LOG-10 hollow-logic screen ----------------------------------------
    t, cd = thr("LOG-10")
    finds = []
    for cs in sa.changesets:
        later = cs.later
        has_pred = {r.succ_uid for r in later.relationships}
        has_succ = {r.pred_uid for r in later.relationships}
        for a in cs.added:
            cal = later.cal_for(a)
            hpd = cal.hours_per_day if cal and cal.hours_per_day else 8.0
            od_days = a.original_duration_hours / hpd if hpd else 0.0
            if od_days <= 1.0 and a.uid in has_pred and a.uid in has_succ:
                finds.append(Finding(a.code, a.name,
                                     f"OD {od_days:.1f}d, inserted with predecessor(s) "
                                     f"and successor(s) ({cs.later.label()})"))
    v = float(len(finds))
    sa.series_results.append(judge(cd, v, t, finds, len(finds), None,
                                   f"{len(finds)} newly added near-zero-duration "
                                   "activity(ies) inserted into existing logic chains."))

    # ---- DUR-04 remaining-duration compression without progress -----------
    # Branch 1 (all percent types): RD dropped by more than the working time
    # that passed between the data dates on the activity's own calendar —
    # physically impossible consumption, i.e. a silent re-estimate.
    # Branch 2 (Physical/Units percent only): RD fell faster than the
    # reported percent movement justifies.  Duration-% activities are
    # excluded from branch 2 because P6 derives their percent from RD/OD,
    # which would make the comparison self-referential.
    t, cd = thr("DUR-04")
    finds = []
    for cs in sa.changesets:
        e_by_code = {a.code: a for a in cs.earlier.activities.values()}
        dd_e, dd_l = cs.earlier.data_date, cs.later.data_date
        for la in cs.later.activities.values():
            if la.is_loe_or_summary or la.completed:
                continue
            ea = e_by_code.get(la.code)
            if ea is None:
                continue
            rd_e, rd_l = ea.remaining_duration_hours, la.remaining_duration_hours
            # branch 1: impossible RD consumption vs working time elapsed
            if dd_e and dd_l and dd_l > dd_e:
                avail = _working_hours_between(cs.later.cal_for(la), dd_e, dd_l)
                if (rd_e - rd_l) > avail + 8.0:
                    finds.append(Finding(la.code, la.name,
                                         f"branch 1 (impossible consumption): RD "
                                         f"{rd_e:.0f}h -> {rd_l:.0f}h "
                                         f"({rd_e - rd_l:.0f}h consumed) vs "
                                         f"{avail:.0f}h working time between data "
                                         f"dates ({cs.later.label()})"))
                    continue
            # branch 2: compression vs reported progress (Physical/Units only)
            if la.pct_type not in (PercentCompleteType.PHYSICAL,
                                   PercentCompleteType.UNITS):
                continue
            pct_e, pct_l = ea.pct_complete, la.pct_complete
            allowed = rd_e * (1 - max(0.0, pct_l - pct_e) / 100.0) - 4.0
            if rd_l < allowed:
                finds.append(Finding(la.code, la.name,
                                     f"branch 2 (compression vs reported progress): "
                                     f"RD {rd_e:.0f}h -> {rd_l:.0f}h, "
                                     f"pct {pct_e:.0f}% -> {pct_l:.0f}% "
                                     f"({cs.later.label()})"))
    v = float(len(finds))
    sa.series_results.append(judge(cd, v, t, finds, len(finds), None,
                                   f"{len(finds)} activity(ies) show remaining-duration "
                                   "compression not justified by working time elapsed "
                                   "or reported progress."))

    # ---- STR-03 WBS re-parenting churn --------------------------------------
    t, cd = thr("STR-03")
    finds = []
    for cs in sa.changesets:
        for ch in cs.wbs_changes:
            finds.append(Finding(ch.code, ch.name,
                                 f"{ch.before} -> {ch.after} ({cs.later.label()})"))
    v = float(len(finds))
    sa.series_results.append(judge(cd, v, t, finds, len(finds), None,
                                   f"{len(finds)} activity(ies) re-parented to a "
                                   "different WBS node across the series."))

    # ---- LI proprietary indices (LI-01..LI-10; additive, never sink) ----
    try:
        from ..analytics.li_wiring import li_series_results
        sa.series_results.extend(li_series_results(sa, matrix))
    except Exception as e:                        # pragma: no cover - defensive
        sa.warnings.append(SeriesWarning(
            "li-indices", f"LI proprietary indices skipped: {e}"))

    return sa
