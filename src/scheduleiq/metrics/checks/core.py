"""Check implementations, registered against matrix IDs.

Population conventions (per DCMA 14-point practice and PASEG):
- "incomplete activities" = tasks + milestones not Completed, excluding
  LOE / WBS-summary / hammock / MSP-summary rows.
- Relationship checks count relationships whose successor (and predecessor,
  when present in file) belong to the assessed population.
- Day conversions use each activity's own calendar (never a global 8h/day).

Each function returns a MetricResult with the offender list so reports can
drill from metric -> activity IDs (the analyst's first question is always
"which ones?").
"""
from __future__ import annotations

from ...ingest.model import (Activity, ActivityType, ConstraintType, RelType,
                             Schedule)
from ..engine import CheckDef, Finding, MetricResult, judge, register


def _fx(acts) -> list[Finding]:
    return [Finding(a.code, a.name) for a in acts]


def _hpd(sched: Schedule, a: Activity) -> float:
    cal = sched.cal_for(a)
    return cal.hours_per_day if cal and cal.hours_per_day else 8.0


def _incomplete(sched: Schedule) -> list[Activity]:
    return [a for a in sched.real_activities if not a.completed]


def _pct(n: float, d: float) -> float:
    return 100.0 * n / d if d else 0.0


def _rel_endpoints(sched: Schedule):
    """Relationships with both endpoints resolvable to real activities."""
    acts = sched.activities
    for r in sched.relationships:
        p, s = acts.get(r.pred_uid), acts.get(r.succ_uid)
        if p is not None and s is not None and not p.is_loe_or_summary \
                and not s.is_loe_or_summary:
            yield r, p, s


# ===========================================================================
# DCMA 14-Point
# ===========================================================================
@register("DCMA-01")
def dcma01_logic(sched: Schedule, cd: CheckDef, thr):
    pop = _incomplete(sched)
    have_pred = {r.succ_uid for r in sched.relationships}
    have_succ = {r.pred_uid for r in sched.relationships}
    missing = [a for a in pop if a.uid not in have_pred or a.uid not in have_succ]
    finds = []
    for a in missing:
        side = []
        if a.uid not in have_pred:
            side.append("no predecessor")
        if a.uid not in have_succ:
            side.append("no successor")
        finds.append(Finding(a.code, a.name, ", ".join(side)))
    v = _pct(len(missing), len(pop))
    return judge(cd, v, thr, finds, len(missing), len(pop),
                 f"{len(missing)} of {len(pop)} incomplete activities are missing a "
                 f"predecessor and/or successor ({v:.1f}%).")


@register("DCMA-02")
def dcma02_leads(sched: Schedule, cd: CheckDef, thr):
    rels = list(_rel_endpoints(sched))
    pop = [(r, p, s) for r, p, s in rels if not s.completed]
    leads = [(r, p, s) for r, p, s in pop if r.lag_hours < 0]
    finds = [Finding(f"{p.code} -> {s.code}", f"{p.name} -> {s.name}",
                     f"{r.rtype.value} lag {r.lag_hours:.0f}h")
             for r, p, s in leads]
    v = _pct(len(leads), len(pop))
    return judge(cd, v, thr, finds, len(leads), len(pop),
                 f"{len(leads)} of {len(pop)} relationships carry a lead "
                 f"(negative lag) ({v:.1f}%).")


@register("DCMA-03")
def dcma03_lags(sched: Schedule, cd: CheckDef, thr):
    pop = [(r, p, s) for r, p, s in _rel_endpoints(sched) if not s.completed]
    lags = [(r, p, s) for r, p, s in pop if r.lag_hours > 0]
    finds = [Finding(f"{p.code} -> {s.code}", f"{p.name} -> {s.name}",
                     f"{r.rtype.value} lag +{r.lag_hours:.0f}h")
             for r, p, s in lags]
    v = _pct(len(lags), len(pop))
    return judge(cd, v, thr, finds, len(lags), len(pop),
                 f"{len(lags)} of {len(pop)} relationships carry positive lag ({v:.1f}%).")


@register("DCMA-04")
def dcma04_fs(sched: Schedule, cd: CheckDef, thr):
    pop = [(r, p, s) for r, p, s in _rel_endpoints(sched) if not s.completed]
    fs = [x for x in pop if x[0].rtype == RelType.FS]
    non = [x for x in pop if x[0].rtype != RelType.FS]
    finds = [Finding(f"{p.code} -> {s.code}", f"{p.name} -> {s.name}", r.rtype.value)
             for r, p, s in non]
    v = _pct(len(fs), len(pop))
    return judge(cd, v, thr, finds, len(fs), len(pop),
                 f"{v:.1f}% of relationships are Finish-to-Start.")


@register("DCMA-05")
def dcma05_hard_constraints(sched: Schedule, cd: CheckDef, thr):
    """DCMA hard = anything preventing rightward movement: Must/Mandatory
    Start/Finish, Start On, Finish On, Start/Finish No Later Than
    (DCMA-EA PAM 200.1 §4, check 5)."""
    pop = _incomplete(sched)
    hard = [a for a in pop if a.constraint.is_late_type or a.constraint2.is_late_type]
    finds = [Finding(a.code, a.name,
                     (a.constraint if a.constraint.is_late_type else a.constraint2).value)
             for a in hard]
    v = _pct(len(hard), len(pop))
    return judge(cd, v, thr, finds, len(hard), len(pop),
                 f"{len(hard)} of {len(pop)} incomplete activities carry hard "
                 f"constraints ({v:.1f}%).")


@register("DCMA-06")
def dcma06_high_float(sched: Schedule, cd: CheckDef, thr):
    pop = [a for a in _incomplete(sched) if a.total_float_hours is not None]
    high = [a for a in pop
            if a.total_float_hours / _hpd(sched, a) > 44]
    finds = [Finding(a.code, a.name,
                     f"TF {a.total_float_hours / _hpd(sched, a):.0f}d") for a in high]
    v = _pct(len(high), len(pop))
    return judge(cd, v, thr, finds, len(high), len(pop),
                 f"{len(high)} of {len(pop)} incomplete activities have total float "
                 f"> 44 working days ({v:.1f}%).")


@register("DCMA-07")
def dcma07_negative_float(sched: Schedule, cd: CheckDef, thr):
    pop = [a for a in _incomplete(sched) if a.total_float_hours is not None]
    neg = [a for a in pop if a.total_float_hours < 0]
    finds = [Finding(a.code, a.name,
                     f"TF {a.total_float_hours / _hpd(sched, a):.1f}d") for a in neg]
    v = _pct(len(neg), len(pop))
    return judge(cd, v, thr, finds, len(neg), len(pop),
                 f"{len(neg)} incomplete activities show negative total float ({v:.1f}%).")


@register("DCMA-08")
def dcma08_high_duration(sched: Schedule, cd: CheckDef, thr):
    """DCMA check 8 uses BASELINE (original) duration, not remaining
    (DCMA-EA PAM 200.1 §4)."""
    pop = [a for a in _incomplete(sched)
           if a.atype == ActivityType.TASK]
    high = [a for a in pop if a.original_duration_hours / _hpd(sched, a) > 44]
    finds = [Finding(a.code, a.name,
                     f"OD {a.original_duration_hours / _hpd(sched, a):.0f}d")
             for a in high]
    v = _pct(len(high), len(pop))
    return judge(cd, v, thr, finds, len(high), len(pop),
                 f"{len(high)} of {len(pop)} incomplete tasks have original duration "
                 f"> 44 working days ({v:.1f}%).")


@register("DCMA-09")
def dcma09_invalid_dates(sched: Schedule, cd: CheckDef, thr):
    dd = sched.data_date
    finds = []
    if dd:
        for a in sched.real_activities:
            if a.actual_start and a.actual_start > dd:
                finds.append(Finding(a.code, a.name,
                                     f"actual start {a.actual_start:%Y-%m-%d} after data date"))
            if a.actual_finish and a.actual_finish > dd:
                finds.append(Finding(a.code, a.name,
                                     f"actual finish {a.actual_finish:%Y-%m-%d} after data date"))
            if not a.completed:
                fs = a.early_start if not a.actual_start else None
                ff = a.early_finish
                if fs and fs < dd:
                    finds.append(Finding(a.code, a.name,
                                         f"forecast start {fs:%Y-%m-%d} before data date"))
                if ff and ff < dd:
                    finds.append(Finding(a.code, a.name,
                                         f"forecast finish {ff:%Y-%m-%d} before data date"))
    v = float(len(finds))
    return judge(cd, v, thr, finds, len(finds), None,
                 f"{len(finds)} invalid date conditions relative to the data date.")


@register("DCMA-10")
def dcma10_resources(sched: Schedule, cd: CheckDef, thr):
    pop = [a for a in _incomplete(sched)
           if a.atype == ActivityType.TASK and a.original_duration_hours > 0]
    bare = [a for a in pop if not a.resources and a.budget_cost == 0]
    finds = _fx(bare)
    v = _pct(len(bare), len(pop))
    return judge(cd, v, thr, finds, len(bare), len(pop),
                 f"{len(bare)} of {len(pop)} incomplete tasks carry neither resources "
                 f"nor cost ({v:.1f}%).")


@register("DCMA-11")
def dcma11_missed_tasks(sched: Schedule, cd: CheckDef, thr):
    dd = sched.data_date
    base = {a.uid: (a.baseline_finish or a.planned_finish)
            for a in sched.real_activities}
    pop = [a for a in sched.real_activities
           if dd and base.get(a.uid) and base[a.uid] <= dd]
    missed = []
    for a in pop:
        bf = base[a.uid]
        af = a.actual_finish or a.early_finish
        if af and bf and af > bf:
            missed.append(a)
    finds = [Finding(a.code, a.name,
                     f"baseline finish {base[a.uid]:%Y-%m-%d}, "
                     f"finish {(a.actual_finish or a.early_finish):%Y-%m-%d}")
             for a in missed]
    v = _pct(len(missed), len(pop))
    return judge(cd, v, thr, finds, len(missed), len(pop),
                 f"{len(missed)} of {len(pop)} activities due by the data date "
                 f"finished (or forecast) late against baseline ({v:.1f}%).")


def longest_float_path(sched: Schedule) -> list[Activity]:
    """Activities on the apparent critical path: minimum-float set, walked for
    continuity from the data date to project finish."""
    pop = [a for a in _incomplete(sched) if a.total_float_hours is not None]
    if not pop:
        return []
    min_tf = min(a.total_float_hours for a in pop)
    crit = [a for a in pop if a.total_float_hours <= min_tf + 0.01]
    return sorted(crit, key=lambda a: (a.early_start or a.planned_start
                                       or sched.data_date or a.uid))


@register("DCMA-12")
def dcma12_critical_path_test(sched: Schedule, cd: CheckDef, thr):
    crit = longest_float_path(sched)
    if not crit:
        return MetricResult(check=cd, status="N/A",
                            narrative="No incomplete activities with float data.")
    crit_ids = {a.uid for a in crit}
    finish = max(crit, key=lambda a: a.early_finish or a.planned_finish
                 or sched.data_date)
    breaks = []
    for a in crit:
        if a.uid == finish.uid:
            continue
        succs = [r for r in sched.successors_of(a.uid)]
        if succs and not any(r.succ_uid in crit_ids for r in succs):
            breaks.append(a)
        if not succs:
            breaks.append(a)
    finds = [Finding(a.code, a.name, "no on-path successor") for a in breaks]
    v = float(len(breaks))
    n = (f"Longest/critical path traced through {len(crit)} activities; "
         f"{len(breaks)} continuity break(s) detected.")
    return judge(cd, v, thr, finds, len(breaks), len(crit), n)


@register("DCMA-13")
def dcma13_cpli(sched: Schedule, cd: CheckDef, thr):
    dd, bf = sched.data_date, sched.must_finish_by or sched.baseline_finish
    ff = sched.finish_date
    if not (dd and bf and ff):
        return MetricResult(check=cd, status="N/A",
                            narrative="Requires data date, baseline/contract finish, "
                                      "and forecast finish.")
    cpl = (ff - dd).days
    tf = (bf - ff).days
    if cpl <= 0:
        return MetricResult(check=cd, status="N/A",
                            narrative="Critical path length is zero (project complete?).")
    v = (cpl + tf) / cpl
    return judge(cd, v, thr, [], None, None,
                 f"CPLI = (CP length {cpl}d + total float {tf}d) / {cpl}d = {v:.2f}.")


@register("DCMA-14")
def dcma14_bei(sched: Schedule, cd: CheckDef, thr):
    dd = sched.data_date
    if not dd:
        return MetricResult(check=cd, status="N/A", narrative="No data date.")
    base = {a.uid: (a.baseline_finish or a.planned_finish)
            for a in sched.real_activities}
    planned = [a for a in sched.real_activities
               if base.get(a.uid) and base[a.uid] <= dd]
    # PAM 200.1: tasks MISSING baseline dates count in the denominator so
    # sparse baselining is penalized, not rewarded
    no_base = [a for a in sched.real_activities if not base.get(a.uid)]
    den = len(planned) + len(no_base)
    done = [a for a in sched.real_activities if a.completed]
    if not den:
        return MetricResult(check=cd, status="N/A",
                            narrative="No activities baselined to finish by the data date.")
    v = len(done) / den
    late = [a for a in planned if not a.completed]
    finds = [Finding(a.code, a.name, "baselined to finish by DD, not complete")
             for a in late]
    finds += [Finding(a.code, a.name, "missing baseline dates (counted in denominator)")
              for a in no_base]
    return judge(cd, v, thr, finds, len(done), den,
                 f"BEI = {len(done)} completed / ({len(planned)} baselined to complete "
                 f"+ {len(no_base)} missing baseline dates) = {v:.2f}.")


# ===========================================================================
# Logic quality beyond DCMA
# ===========================================================================
@register("LOG-01")
def log01_dangling_starts(sched: Schedule, cd: CheckDef, thr):
    """Start not driven: only FF predecessors (start can float freely)."""
    pop = _incomplete(sched)
    have_pred = {}
    for r, p, s in _rel_endpoints(sched):
        have_pred.setdefault(s.uid, set()).add(r.rtype)
    bad = [a for a in pop
           if have_pred.get(a.uid) and have_pred[a.uid] <= {RelType.FF}]
    v = float(len(bad))
    return judge(cd, v, thr, _fx(bad), len(bad), len(pop),
                 f"{len(bad)} activities have only FF predecessors (dangling start).")


@register("LOG-02")
def log02_dangling_finishes(sched: Schedule, cd: CheckDef, thr):
    """Finish drives nothing: has successors but only via SS."""
    pop = _incomplete(sched)
    succ_types: dict[str, set] = {}
    for r, p, s in _rel_endpoints(sched):
        succ_types.setdefault(p.uid, set()).add(r.rtype)
    bad = [a for a in pop
           if succ_types.get(a.uid) and succ_types[a.uid] <= {RelType.SS}]
    v = float(len(bad))
    return judge(cd, v, thr, _fx(bad), len(bad), len(pop),
                 f"{len(bad)} activities have only SS successors (dangling finish).")


@register("LOG-03")
def log03_sf(sched: Schedule, cd: CheckDef, thr):
    pop = list(_rel_endpoints(sched))
    sf = [(r, p, s) for r, p, s in pop if r.rtype == RelType.SF]
    finds = [Finding(f"{p.code} -> {s.code}", f"{p.name} -> {s.name}", "SF")
             for r, p, s in sf]
    v = float(len(sf))
    return judge(cd, v, thr, finds, len(sf), len(pop),
                 f"{len(sf)} Start-to-Finish relationship(s).")


@register("LOG-04")
def log04_redundant(sched: Schedule, cd: CheckDef, thr):
    seen: dict[tuple, int] = {}
    dup = []
    for r, p, s in _rel_endpoints(sched):
        k = (r.pred_uid, r.succ_uid)
        seen[k] = seen.get(k, 0) + 1
        if seen[k] == 2:
            dup.append((p, s))
    finds = [Finding(f"{p.code} -> {s.code}", f"{p.name} -> {s.name}",
                     "multiple parallel relationships") for p, s in dup]
    v = float(len(dup))
    return judge(cd, v, thr, finds, len(dup), None,
                 f"{len(dup)} activity pair(s) linked by more than one relationship.")


@register("LOG-05")
def log05_density(sched: Schedule, cd: CheckDef, thr):
    pop = sched.real_activities
    rels = list(_rel_endpoints(sched))
    v = len(rels) / len(pop) if pop else 0.0
    return judge(cd, v, thr, [], len(rels), len(pop),
                 f"{len(rels)} relationships over {len(pop)} activities "
                 f"= {v:.2f} per activity.")


@register("LOG-06")
def log06_merge_hotspot(sched: Schedule, cd: CheckDef, thr):
    preds: dict[str, int] = {}
    for r, p, s in _rel_endpoints(sched):
        preds[s.uid] = preds.get(s.uid, 0) + 1
    hot = [(sched.activities[uid], n) for uid, n in preds.items() if n >= 10]
    finds = [Finding(a.code, a.name, f"{n} predecessors") for a, n in hot]
    v = float(len(hot))
    return judge(cd, v, thr, finds, len(hot), None,
                 f"{len(hot)} merge hotspot(s) (>= 10 predecessors).")


@register("LOG-07")
def log07_oos(sched: Schedule, cd: CheckDef, thr):
    """Out-of-sequence progress: successor started before a FS predecessor
    finished (or before SS predecessor started)."""
    finds = []
    for r, p, s in _rel_endpoints(sched):
        if not s.actual_start:
            continue
        if r.rtype == RelType.FS:
            pf = p.actual_finish
            if (not p.completed) or (pf and s.actual_start < pf):
                finds.append(Finding(f"{p.code} -> {s.code}", f"{p.name} -> {s.name}",
                                     "successor started before FS predecessor finished"))
        elif r.rtype == RelType.SS and not p.actual_start:
            finds.append(Finding(f"{p.code} -> {s.code}", f"{p.name} -> {s.name}",
                                 "successor started before SS predecessor started"))
    v = float(len(finds))
    return judge(cd, v, thr, finds, len(finds), None,
                 f"{len(finds)} relationship(s) progressed out of sequence.")


@register("LOG-08")
def log08_loe_logic(sched: Schedule, cd: CheckDef, thr):
    loe = {a.uid for a in sched.activities.values() if a.is_loe_or_summary}
    acts = sched.activities
    bad = [r for r in sched.relationships
           if (r.pred_uid in loe or r.succ_uid in loe)]
    finds = []
    for r in bad:
        p, s = acts.get(r.pred_uid), acts.get(r.succ_uid)
        if p and s:
            finds.append(Finding(f"{p.code} -> {s.code}", f"{p.name} -> {s.name}",
                                 "logic through LOE/summary activity"))
    v = float(len(finds))
    return judge(cd, v, thr, finds, len(finds), None,
                 f"{len(finds)} relationship(s) run through LOE/summary activities.")


@register("LOG-09")
def log09_transitive_redundancy(sched: Schedule, cd: CheckDef, thr):
    """A->C redundant when another FS path A->...->C exists (bounded BFS)."""
    fs_succ: dict[str, list[str]] = {}
    for r, p, s in _rel_endpoints(sched):
        if r.rtype == RelType.FS and r.lag_hours == 0:
            fs_succ.setdefault(p.uid, []).append(s.uid)
    finds = []
    for r, p, s in _rel_endpoints(sched):
        if r.rtype != RelType.FS:
            continue
        frontier = [u for u in fs_succ.get(p.uid, []) if u != s.uid]
        seen = set(frontier)
        for _ in range(25):
            nxt = []
            for u in frontier:
                for v in fs_succ.get(u, []):
                    if v == s.uid:
                        finds.append(Finding(f"{p.code} -> {s.code}",
                                             f"{p.name} -> {s.name}",
                                             "implied by an existing FS path"))
                        nxt = []
                        frontier = []
                        break
                    if v not in seen:
                        seen.add(v)
                        nxt.append(v)
                else:
                    continue
                break
            if not nxt:
                break
            frontier = nxt
    v = float(len(finds))
    return judge(cd, v, thr, finds, len(finds), None,
                 f"{len(finds)} relationship(s) duplicated by transitive FS paths.")


@register("REL-01")
def rel01_zombie_relationships(sched: Schedule, cd: CheckDef, thr):
    """Relationships whose predecessor or successor task ID does not resolve
    to an activity in this schedule — export corruption or a partial delete
    that left dangling logic rows behind (RPW Schedule Analyzer practice)."""
    acts = sched.activities
    finds = []
    for r in sched.relationships:
        missing = []
        if r.pred_uid not in acts:
            missing.append(f"predecessor {r.pred_uid}")
        if r.succ_uid not in acts:
            missing.append(f"successor {r.succ_uid}")
        if missing:
            finds.append(Finding(f"{r.pred_uid} -> {r.succ_uid}", "",
                                 f"missing {', '.join(missing)} ({r.rtype.value})"))
    v = float(len(finds))
    return judge(cd, v, thr, finds, len(finds), None,
                 f"{len(finds)} relationship(s) reference an activity absent from "
                 "the schedule.")


# ===========================================================================
# Constraints / float
# ===========================================================================
@register("CON-01")
def con01_soft_constraints(sched: Schedule, cd: CheckDef, thr):
    pop = _incomplete(sched)
    soft = [a for a in pop
            if (a.constraint != ConstraintType.NONE and not a.constraint.is_late_type)
            or (a.constraint2 != ConstraintType.NONE and not a.constraint2.is_late_type)]
    finds = [Finding(a.code, a.name,
                     (a.constraint if a.constraint != ConstraintType.NONE
                      else a.constraint2).value) for a in soft]
    v = _pct(len(soft), len(pop))
    return judge(cd, v, thr, finds, len(soft), len(pop),
                 f"{len(soft)} of {len(pop)} incomplete activities carry soft "
                 f"(one-way) constraints ({v:.1f}%).")


@register("CON-02")
def con02_expected_finish(sched: Schedule, cd: CheckDef, thr):
    pop = _incomplete(sched)
    ef = [a for a in pop if a.constraint == ConstraintType.EXPECTED_FINISH
          or a.expected_finish]
    v = float(len(ef))
    return judge(cd, v, thr, _fx(ef), len(ef), len(pop),
                 f"{len(ef)} activities carry Expected Finish constraints.")


@register("CON-03")
def con03_alap(sched: Schedule, cd: CheckDef, thr):
    pop = _incomplete(sched)
    alap = [a for a in pop if ConstraintType.AS_LATE_AS_POSSIBLE in
            (a.constraint, a.constraint2)]
    v = float(len(alap))
    return judge(cd, v, thr, _fx(alap), len(alap), len(pop),
                 f"{len(alap)} activities are As-Late-As-Possible.")


@register("FLT-01")
def flt01_critical_pct(sched: Schedule, cd: CheckDef, thr):
    pop = [a for a in _incomplete(sched) if a.total_float_hours is not None]
    crit = [a for a in pop if a.total_float_hours <= 0]
    v = _pct(len(crit), len(pop))
    return judge(cd, v, thr, _fx(crit), len(crit), len(pop),
                 f"{len(crit)} of {len(pop)} incomplete activities are critical "
                 f"(TF <= 0) ({v:.1f}%).")


@register("FLT-02")
def flt02_near_critical_pct(sched: Schedule, cd: CheckDef, thr):
    pop = [a for a in _incomplete(sched) if a.total_float_hours is not None]
    near = [a for a in pop
            if 0 < a.total_float_hours / _hpd(sched, a) <= 5]
    v = _pct(len(near), len(pop))
    return judge(cd, v, thr, _fx(near), len(near), len(pop),
                 f"{len(near)} of {len(pop)} incomplete activities are near-critical "
                 f"(0 < TF <= 5d) ({v:.1f}%).")


@register("FLT-03")
def flt03_float_exceeds_remaining(sched: Schedule, cd: CheckDef, thr):
    """Total float cannot legitimately exceed the runway left to the forecast
    finish; when it does the calendar or a constraint is producing an
    artifact rather than genuine flexibility (RPW; GAO BP7).

    Working-day-equivalent remaining duration is approximated as
    (finish_date - data_date) calendar days * 5/7 + a 2-working-day buffer
    (for holidays/rounding); it does not model the project's actual holiday
    calendar, so it is deliberately conservative (a small buffer before
    flagging) rather than exact."""
    dd, ff = sched.data_date, sched.finish_date
    if not dd or not ff:
        return MetricResult(check=cd, status="N/A",
                            narrative="Requires data date and forecast finish date.")
    cal_days = (ff - dd).days
    remaining_wd = max(0.0, cal_days * 5.0 / 7.0) + 2.0
    pop = [a for a in _incomplete(sched) if a.total_float_hours is not None]
    bad = []
    for a in pop:
        tf_days = a.total_float_hours / _hpd(sched, a)
        if tf_days > remaining_wd:
            bad.append((a, tf_days))
    finds = [Finding(a.code, a.name,
                     f"TF {tf_days:.0f}wd > {remaining_wd:.0f}wd remaining")
             for a, tf_days in bad]
    v = float(len(bad))
    return judge(cd, v, thr, finds, len(bad), len(pop),
                 f"{len(bad)} of {len(pop)} incomplete activities carry total float "
                 f"exceeding the ~{remaining_wd:.0f} working-day-equivalent runway "
                 f"remaining to the forecast finish ({cal_days} calendar days from "
                 "the data date).")


# ===========================================================================
# Durations / estimates
# ===========================================================================
@register("DUR-01")
def dur01_zero_duration_tasks(sched: Schedule, cd: CheckDef, thr):
    pop = [a for a in _incomplete(sched) if a.atype == ActivityType.TASK]
    zero = [a for a in pop if a.original_duration_hours == 0]
    v = float(len(zero))
    return judge(cd, v, thr, _fx(zero), len(zero), len(pop),
                 f"{len(zero)} zero-duration activities are not coded as milestones.")


@register("DUR-02")
def dur02_round_durations(sched: Schedule, cd: CheckDef, thr):
    pop = [a for a in _incomplete(sched)
           if a.atype == ActivityType.TASK and a.original_duration_hours > 0]
    round5 = [a for a in pop
              if (a.original_duration_hours / _hpd(sched, a)) % 5 == 0]
    v = _pct(len(round5), len(pop))
    return judge(cd, v, thr, [], len(round5), len(pop),
                 f"{v:.1f}% of task durations are multiples of 5 days "
                 "(possible templated estimating).")


@register("DUR-03")
def dur03_od_rd_mismatch(sched: Schedule, cd: CheckDef, thr):
    pop = [a for a in _incomplete(sched)
           if a.not_started and a.atype == ActivityType.TASK]
    bad = [a for a in pop
           if abs(a.remaining_duration_hours - a.original_duration_hours) > 0.01]
    finds = [Finding(a.code, a.name,
                     f"OD {a.original_duration_hours:.0f}h vs RD "
                     f"{a.remaining_duration_hours:.0f}h") for a in bad]
    v = float(len(bad))
    return judge(cd, v, thr, finds, len(bad), len(pop),
                 f"{len(bad)} not-started activities have remaining duration differing "
                 "from original duration.")


# ===========================================================================
# Status/date integrity
# ===========================================================================
@register("DAT-01")
def dat01_progress_no_actual(sched: Schedule, cd: CheckDef, thr):
    finds = []
    for a in sched.real_activities:
        if a.in_progress and not a.actual_start:
            finds.append(Finding(a.code, a.name, "in progress without actual start"))
        if a.completed and not a.actual_finish:
            finds.append(Finding(a.code, a.name, "completed without actual finish"))
        if a.completed and not a.actual_start:
            finds.append(Finding(a.code, a.name, "completed without actual start"))
    v = float(len(finds))
    return judge(cd, v, thr, finds, len(finds), None,
                 f"{len(finds)} status/actual-date inconsistencies.")


@register("DAT-02")
def dat02_actual_no_progress(sched: Schedule, cd: CheckDef, thr):
    bad = [a for a in sched.real_activities
           if a.not_started and (a.actual_start or a.actual_finish)]
    v = float(len(bad))
    return judge(cd, v, thr, _fx(bad), len(bad), None,
                 f"{len(bad)} not-started activities carry actual dates.")


@register("DAT-03")
def dat03_suspend(sched: Schedule, cd: CheckDef, thr):
    pop = sched.real_activities
    sus = [a for a in pop if a.suspend_date or a.resume_date]
    v = float(len(sus))
    return judge(cd, v, thr, _fx(sus), len(sus), None,
                 f"{len(sus)} activities use suspend/resume dates.")


@register("DAT-04")
def dat04_dd_alignment(sched: Schedule, cd: CheckDef, thr):
    dd, exp = sched.data_date, sched.export_date
    if not dd or not exp:
        return MetricResult(check=cd, status="N/A",
                            narrative="Data date or export date unavailable.")
    v = abs((exp - dd).days)
    return judge(cd, float(v), thr, [], None, None,
                 f"Export made {v} day(s) after the data date "
                 f"(DD {dd:%Y-%m-%d}, exported {exp:%Y-%m-%d}).")


@register("DAT-05")
def dat05_actual_duration_anomalies(sched: Schedule, cd: CheckDef, thr):
    """As-built corruption screens (AACE29R §2.3): actual finish before
    actual start, actuals earlier than the project start date, and completed
    tasks of positive duration whose actual span collapses to zero."""
    start = sched.start_date
    finds = []
    for a in sched.real_activities:
        if a.actual_start and a.actual_finish and a.actual_finish < a.actual_start:
            finds.append(Finding(a.code, a.name,
                                 f"actual finish {a.actual_finish:%Y-%m-%d} before "
                                 f"actual start {a.actual_start:%Y-%m-%d}"))
        if start:
            if a.actual_start and a.actual_start < start:
                finds.append(Finding(a.code, a.name,
                                     f"actual start {a.actual_start:%Y-%m-%d} before "
                                     f"project start {start:%Y-%m-%d}"))
            if a.actual_finish and a.actual_finish < start:
                finds.append(Finding(a.code, a.name,
                                     f"actual finish {a.actual_finish:%Y-%m-%d} before "
                                     f"project start {start:%Y-%m-%d}"))
        if a.completed and a.atype == ActivityType.TASK \
                and a.original_duration_hours > 0 \
                and a.actual_start and a.actual_finish \
                and a.actual_start == a.actual_finish:
            finds.append(Finding(a.code, a.name,
                                 "completed with positive original duration but "
                                 "zero as-built span (actual start == actual finish)"))
    v = float(len(finds))
    return judge(cd, v, thr, finds, len(finds), None,
                 f"{len(finds)} actual-duration anomal{'y' if len(finds) == 1 else 'ies'} "
                 "detected.")


# ===========================================================================
# Calendars
# ===========================================================================
def _cals_in_use(sched: Schedule):
    used = {}
    for a in sched.real_activities:
        c = sched.cal_for(a)
        if c:
            used.setdefault(c.uid, [c, 0])
            used[c.uid][1] += 1
    return used


@register("CAL-01")
def cal01_count(sched: Schedule, cd: CheckDef, thr):
    used = _cals_in_use(sched)
    finds = [Finding(c.name or uid, "",
                     f"{n} activities, {c.hours_per_day:g}h/day, "
                     f"{c.workdays_per_week}d/week")
             for uid, (c, n) in used.items()]
    v = float(len(used))
    return judge(cd, v, thr, finds, len(used), None,
                 f"{len(used)} calendar(s) in use.")


@register("CAL-02")
def cal02_nonstandard_hours(sched: Schedule, cd: CheckDef, thr):
    used = _cals_in_use(sched)
    odd = [(c, n) for c, n in used.values() if c.hours_per_day not in (8.0,)]
    finds = [Finding(c.name or c.uid, "",
                     f"{c.hours_per_day:g}h/day on {n} activities") for c, n in odd]
    v = float(sum(n for _, n in odd))
    return judge(cd, v, thr, finds, len(odd), None,
                 f"{len(odd)} calendar(s) with non-8-hour days cover "
                 f"{sum(n for _, n in odd)} activities (day-unit distortion risk).")


@register("CAL-03")
def cal03_no_holidays(sched: Schedule, cd: CheckDef, thr):
    used = _cals_in_use(sched)
    bare = [(c, n) for c, n in used.values()
            if c.workdays_per_week <= 5 and not c.exceptions_nonwork]
    finds = [Finding(c.name or c.uid, "", f"no holiday exceptions ({n} activities)")
             for c, n in bare]
    v = float(len(bare))
    return judge(cd, v, thr, finds, len(bare), None,
                 f"{len(bare)} working calendar(s) define no holidays.")


@register("CAL-05")
def cal05_multi_calendar_float_distortion(sched: Schedule, cd: CheckDef, thr):
    """Quantified multi-calendar float distortion at the driving path
    (backlog C4/CAL-05).  For each activity on the driving path (reused,
    never recomputed, from analytics.paths.driving_path — ADR-0004), total
    float is restated in days via the activity's OWN calendar hours/day and,
    separately, via the project's DOMINANT calendar hours/day (the calendar
    covering the most real activities).  The two day-figures diverge whenever
    a driving-path activity sits on a non-dominant-hours calendar, because
    'days' of float is not a calendar-neutral unit (RPW).  Reports the max
    absolute divergence along the path; a driving-path chart date can look
    solid on one calendar's 'days' and be materially different when restated
    on the calendar the rest of the schedule uses.  Lazy-imports
    analytics.paths and returns N/A on any failure (including an
    unresolvable driving path) so this check can never sink a run."""
    try:
        from ...analytics.paths import driving_path
        dp = driving_path(sched)
        if not dp.steps:
            return MetricResult(check=cd, status="N/A",
                                narrative=dp.reason or "No driving path could be resolved.")
        cal_counts: dict[str, list] = {}
        for a in sched.real_activities:
            c = sched.cal_for(a)
            if c:
                cal_counts.setdefault(c.uid, [c, 0])
                cal_counts[c.uid][1] += 1
        if not cal_counts:
            return MetricResult(check=cd, status="N/A",
                                narrative="No calendars resolved for activities.")
        dominant = max(cal_counts.values(), key=lambda t: t[1])[0]
        dom_hpd = dominant.hours_per_day if dominant.hours_per_day else 8.0
        finds = []
        max_div = 0.0
        for step in dp.steps:
            a = step.activity
            if a.total_float_hours is None:
                continue
            own_cal = sched.cal_for(a)
            own_hpd = own_cal.hours_per_day if own_cal and own_cal.hours_per_day else 8.0
            own_days = a.total_float_hours / own_hpd
            dom_days = a.total_float_hours / dom_hpd
            div = abs(own_days - dom_days)
            max_div = max(max_div, div)
            if div > 0.5:
                finds.append(Finding(
                    a.code, a.name,
                    f"TF {a.total_float_hours:.0f}h = {own_days:.1f}d on own "
                    f"calendar ({own_hpd:g}h/day) vs {dom_days:.1f}d on the "
                    f"project's dominant calendar "
                    f"({dominant.name or dominant.uid}, {dom_hpd:g}h/day) — "
                    f"divergence {div:.1f}d"))
        v = max_div
        return judge(cd, v, thr, finds, len(finds), len(dp.steps),
                     f"Max float divergence along the driving path from "
                     f"multi-calendar distortion is {v:.1f}d (own-calendar vs "
                     f"the project's dominant calendar "
                     f"{dominant.name or dominant.uid} at {dom_hpd:g}h/day); "
                     f"{len(finds)} step(s) exceed 0.5d.")
    except Exception as e:
        return MetricResult(check=cd, status="N/A",
                            narrative=f"Driving-path analytics unavailable: {e}")


# ===========================================================================
# Resources
# ===========================================================================
@register("RES-01")
def res01_milestone_resources(sched: Schedule, cd: CheckDef, thr):
    ms = [a for a in sched.real_activities if a.is_milestone and a.resources]
    v = float(len(ms))
    return judge(cd, v, thr, _fx(ms), len(ms), None,
                 f"{len(ms)} milestone(s) carry resource assignments.")


@register("RES-02")
def res02_completed_remaining(sched: Schedule, cd: CheckDef, thr):
    bad = [a for a in sched.real_activities
           if a.completed and (a.remaining_duration_hours > 0
                               or a.remaining_cost > 0
                               or any(r.remaining_units > 0 for r in a.resources))]
    v = float(len(bad))
    return judge(cd, v, thr, _fx(bad), len(bad), None,
                 f"{len(bad)} completed activities retain remaining duration/units/cost.")


# ===========================================================================
# Structure / critical path
# ===========================================================================
@register("CP-01")
def cp01_multiple_cals_on_cp(sched: Schedule, cd: CheckDef, thr):
    crit = [a for a in _incomplete(sched)
            if a.total_float_hours is not None and a.total_float_hours <= 0]
    cals = {}
    for a in crit:
        c = sched.cal_for(a)
        if c:
            cals.setdefault(c.uid, [c, 0])
            cals[c.uid][1] += 1
    v = float(len(cals))
    finds = [Finding(c.name or c.uid, "", f"{n} critical activities")
             for c, n in cals.values()]
    return judge(cd, v, thr, finds, len(cals), None,
                 f"{len(cals)} calendar(s) on the critical path "
                 "(mixed calendars distort float).")


@register("STR-01")
def str01_size(sched: Schedule, cd: CheckDef, thr):
    v = float(len(sched.real_activities))
    return judge(cd, v, thr, [], None, None,
                 f"{len(sched.real_activities)} task/milestone activities "
                 f"({len(sched.activities)} rows incl. LOE/summary), "
                 f"{len(sched.relationships)} relationships, "
                 f"{len(sched.wbs)} WBS nodes.")


@register("STR-02")
def str02_milestones(sched: Schedule, cd: CheckDef, thr):
    starts = [a for a in sched.real_activities
              if a.atype == ActivityType.START_MILESTONE]
    fins = [a for a in sched.real_activities
            if a.atype == ActivityType.FINISH_MILESTONE]
    v = float(len(starts) + len(fins))
    return judge(cd, v, thr, [], None, None,
                 f"{len(starts)} start milestone(s), {len(fins)} finish milestone(s).")


@register("PRG-01")
def prg01_progress(sched: Schedule, cd: CheckDef, thr):
    pop = sched.real_activities
    done = [a for a in pop if a.completed]
    prog = [a for a in pop if a.in_progress]
    v = _pct(len(done), len(pop))
    return judge(cd, v, thr, [], len(done), len(pop),
                 f"{len(done)} completed ({v:.1f}%), {len(prog)} in progress, "
                 f"{len(pop) - len(done) - len(prog)} not started.")
