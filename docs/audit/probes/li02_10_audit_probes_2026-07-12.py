"""AUDIT-FIRST probe set for LI-02..LI-10 (no repo changes).

Hand-built in-memory series with closed-form expectations, run against the
FCBI-v0.5.6 base (ec30292).  Each probe prints CURRENT behavior next to the
hand-computed expectation / the rubric item it tests.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))

from datetime import datetime, timedelta

from scheduleiq.ingest.model import (Activity, ActivityStatus, ActivityType,
                                     Calendar, ConstraintType, Relationship,
                                     RelType, ResourceAssignment, Schedule,
                                     WbsNode)
from scheduleiq.compare.diff import compare
from scheduleiq.trend.series import SeriesAnalysis
from scheduleiq.analytics.li_indices import (run_li_indices, kernel_weight,
                                             relative_float_map, _build_kernel,
                                             DEFAULT_LAMBDA)
from scheduleiq.analytics.li_record import (run_li_record, logic_half_life,
                                            forecast_reliability_band,
                                            intervention_latency,
                                            baseline_dilution_index,
                                            measured_mile_locator, kaplan_meier)
from scheduleiq.analytics.li_wiring import li_series_results
from scheduleiq.scorecard import _li02_score, _li08_score
from scheduleiq.analytics.paths import float_paths

H = 8.0
FIN = datetime(2025, 6, 30, 17)


def A(uid, code, tf, *, atype=ActivityType.TASK, status=ActivityStatus.NOT_STARTED,
      od=10, rem=10, ef=FIN, af=None, aslate=None, wbs=None, res=None,
      constraint=ConstraintType.NONE, cdate=None, pf=None):
    a = Activity(uid=uid, code=code, atype=atype, status=status,
                 total_float_hours=None if tf is None else tf * H,
                 original_duration_hours=od * H, remaining_duration_hours=rem * H,
                 early_start=(ef - timedelta(days=od)) if ef else None,
                 early_finish=ef, actual_finish=af, actual_start=aslate,
                 wbs_uid=wbs, constraint=constraint, constraint_date=cdate,
                 planned_finish=pf)
    if res:
        a.resources = res
    return a


def M(uid, code, tf=0.0, ef=FIN, constraint=ConstraintType.NONE, cdate=None):
    return A(uid, code, tf, atype=ActivityType.FINISH_MILESTONE, od=0, rem=0,
             ef=ef, constraint=constraint, cdate=cdate)


def S(dd, acts, rels, finish=None, wbs=None):
    sc = Schedule(project_id="P", data_date=dd,
                  activities={a.uid: a for a in acts})
    sc.relationships = list(rels)
    sc.finish_date = finish
    if wbs:
        sc.wbs = {n.uid: n for n in wbs}
    return sc


def SA(scheds):
    css = [compare(scheds[i], scheds[i + 1]) for i in range(len(scheds) - 1)]
    return SeriesAnalysis(schedules=scheds, changesets=css)


def hdr(t):
    print("\n" + "=" * 78 + f"\n{t}\n" + "=" * 78)


# =========================================================================
# K — Shared v0.4 kernel probes (feeds LI-04 PCI, LI-05 RDI, LI-07 CDI,
#     LI-09 BWI)
# =========================================================================
hdr("K1 (A1): own-total-float fallback still live in relative_float_map")
# X->T driving (TF 0); ORPHAN has no relationships at all -> on no path.
rels = [Relationship("X", "T")]
s = S(datetime(2025, 1, 6, 8),
      [A("X", "X", 0.0), M("T", "T", 0.0), A("ORPH", "ORPH", 4.0)], rels)
paths = float_paths(s, n=10)
rf = relative_float_map(s, paths)
print("paths:", [p.codes for p in paths])
print(f"RF map: {rf}")
print(f"EXPECT under FCBI O1 discipline: ORPH unresolved/quarantined; "
      f"ACTUAL: ORPH RF = {rf.get('ORPH')} (own TF fallback -> weight "
      f"{kernel_weight(rf['ORPH'], 5.0):.3f} enters CDI/RDI/BWI populations)")

hdr("K2 (A1): negative float -> kernel weight > 1 (over-critical premium)")
print(f"kernel_weight(-3, 5) = {kernel_weight(-3.0, 5.0):.4f}  (>1)")
print(f"kernel_weight(-10, 5) = {kernel_weight(-10.0, 5.0):.4f}  (=4)")

hdr("K3 (A3): LOE can set a v0.4 path margin (rel_float_days) and enters RF map")
# Driving: X(0)->T.  Feeder: LOE(-2)->X : LOE is the branch-unique member.
rels = [Relationship("X", "T"), Relationship("L", "X")]
s = S(datetime(2025, 1, 6, 8),
      [A("X", "X", 0.0), M("T", "T", 0.0),
       A("L", "L", -2.0, atype=ActivityType.LOE)], rels)
k = _build_kernel(s, 5.0)
print("paths:", [(p.rank, p.codes, p.rel_float_days) for p in k.paths])
print("RF map:", k.rf)
print("EXPECT under FCBI A3: LOE never sets a margin (rel_float_hours basis is "
      "discrete-only).  ACTUAL v0.4 rel_float_days of the LOE feeder path and "
      "the LOE's own RF entry:", k.rf.get("L"))

# =========================================================================
# LI-02 LHL
# =========================================================================
hdr("LHL-1 (L1 inversion): frozen network (0 deaths) scores 70, not 100")
rels = [Relationship("A", "B")]
scheds = [S(datetime(2025, 1, 6, 8) + timedelta(days=30 * i),
            [A("A", "A", 5.0), A("B", "B", 5.0), M("T", "T")], rels)
          for i in range(4)]
sa = SA(scheds)
val, score, off = _li02_score(sa, {"points": [[1, 0], [6, 70], [12, 100]],
                                   "censored_pass_threshold": 0.10,
                                   "not_reached_partial_score": 70.0})
lhl = logic_half_life(sa)
print(f"0 deaths / all censored: censored={lhl.overall.censored}/{lhl.overall.n}, "
      f"median_reached={lhl.overall.median_reached}")
print(f"published rationale: 100 when <10% DIED.  ACTUAL score = {score} "
      f"(inverted: tests CENSORED fraction)")

hdr("LHL-2 (L10): maximal churn + missing data dates -> score 100")
# 4 schedules, no data dates; 19/20 rels die AFTER the excluded baseline pair.
r0 = [Relationship(f"A{i}", "B") for i in range(20)]
acts = [A(f"A{i}", f"A{i}", 5.0) for i in range(20)] + [A("B", "B", 5.0)]
s0 = S(None, acts, r0)
s1 = S(None, acts, r0)
s2 = S(None, acts, r0[:1])          # 19 of 20 die in the scored cohort
s3 = S(None, acts, r0[:1])
sa = SA([s0, s1, s2, s3])
val, score, off = _li02_score(sa, {"points": [[1, 0], [6, 70], [12, 100]],
                                   "censored_pass_threshold": 0.10,
                                   "not_reached_partial_score": 70.0})
lhl = logic_half_life(sa, exclude_first_pair=False)
print(f"19/20 relationships die, data dates missing: median_updates="
      f"{lhl.overall.median_updates}, months={lhl.overall.median_months}")
print(f"EXPECT: ungradeable (no months basis).  ACTUAL score = {score} "
      f"(100 via the L1-inverted censoring branch)")

hdr("LHL-3 (L2/L7): first-window deletion -> '0.0 months' median")
dd = datetime(2025, 1, 6, 8)
rels_e = [Relationship("A", "B"), Relationship("C", "B")]
rels_l = [Relationship("A", "B")]                     # C->B dies in window 1
s0 = S(dd, [A("A", "A", 5.0), A("C", "C", 5.0), A("B", "B", 5.0)], rels_e)
s1 = S(dd + timedelta(days=30), [A("A", "A", 5.0), A("C", "C", 5.0),
                                 A("B", "B", 5.0)], rels_l)
sa = SA([s0, s1])
lhl = logic_half_life(sa)         # 2 scheds -> exclusion cannot apply (L6)
print(f"median_updates={lhl.overall.median_updates}, "
      f"months={lhl.overall.median_months}, reached={lhl.overall.median_reached}")
print(f"exclude_first_pair reported as: {lhl.exclude_first_pair} "
      f"(L6: with 2 schedules the exclusion silently cannot apply)")
print("EXPECT: death dated in (0,1] window, lower bound = longest follow-up. "
      "ACTUAL: lifespan = last_alive - birth = 0 -> median 0.0 'months'")

hdr("LHL-4 (L5): irregular cadence x global mean interval distorts months")
# deaths at update index 1 for cohort born at 0; intervals 7d then 105d.
dd0 = datetime(2025, 1, 6, 8)
r_all = [Relationship("A", "B"), Relationship("C", "D")]
acts4 = [A(x, x, 5.0) for x in "ABCD"]
s0 = S(dd0, acts4, r_all)
s1 = S(dd0 + timedelta(days=7), acts4, r_all[:1])      # C->D dies in 7-day window
s2 = S(dd0 + timedelta(days=112), acts4, [])           # A->B dies in 105-day window
sa = SA([s0, s1, s2])
lhl = logic_half_life(sa, exclude_first_pair=False)
print(f"mean interval = {lhl.mean_update_interval_days} d (7 and 105 averaged)")
print(f"median_updates={lhl.overall.median_updates} -> months="
      f"{lhl.overall.median_months and round(lhl.overall.median_months, 2)}")
print("EXPECT: per-instance calendar-day lifespans.  ACTUAL: update-count KM "
      "x 56d mean -> one number for two very different real durations")

hdr("LHL-5 (L9): out-of-order data dates -> negative months, silently")
s0 = S(datetime(2025, 3, 6, 8), acts4, r_all)
s1 = S(datetime(2025, 2, 6, 8), acts4, r_all)
s2 = S(datetime(2025, 1, 6, 8), acts4, r_all[:1])   # C->D dies at t=1
sa = SA([s0, s1, s2])
lhl = logic_half_life(sa, exclude_first_pair=False)
print(f"months = {lhl.overall.median_months}, reason = {lhl.reason!r}")

hdr("LHL-6 (L4): completed-work ties inflate survival (immortal logic)")
# 6 ties on completed work never die; 2 live ties die fast.
dd = datetime(2025, 1, 6, 8)
comp = [A(f"C{i}", f"C{i}", None, status=ActivityStatus.COMPLETED,
          af=dd - timedelta(days=10), rem=0) for i in range(6)]
live = [A("L1", "L1", 5.0), A("L2", "L2", 5.0), A("B", "B", 5.0)]
r_comp = [Relationship(f"C{i}", f"C{(i + 1) % 6}") for i in range(6)]
r_live = [Relationship("L1", "B"), Relationship("L2", "B")]
s0 = S(dd, comp + live, r_comp + r_live)
s1 = S(dd + timedelta(days=30), comp + live, r_comp + r_live[:1])
s2 = S(dd + timedelta(days=60), comp + live, r_comp)
sa = SA([s0, s1, s2])
lhl = logic_half_life(sa, exclude_first_pair=False)
print(f"n={lhl.overall.n}, censored={lhl.overall.censored}, "
      f"median_updates={lhl.overall.median_updates}, "
      f"reached={lhl.overall.median_reached}, months={lhl.overall.median_months}")
print("EXPECT (lineage-A ruling L4b): completed-work ties censored/unobserved; "
      "the 2 live ties die at t=1 -> median reached.  ACTUAL: 6 immortal "
      "completed ties keep S(t) > 0.5 -> 'not reached'")

# =========================================================================
# LI-03 FRB
# =========================================================================
hdr("FRB-1 (FR1): wiring reads b.bias/b.p10/b.p90 -> LI-03 always width 0")
dd = datetime(2025, 1, 6, 8)
# 6 activities forecast ~20d out; actuals from 7wd early to 43wd late.
offsets = [-7, -2, 3, 11, 22, 43]
acts_e, acts_l = [], []
for i, off in enumerate(offsets):
    f = dd + timedelta(days=20)
    act_fin = f + timedelta(days=int(off * 7 / 5))   # approx wd->cal
    acts_e.append(A(f"F{i}", f"F{i}", 5.0, ef=f))
    acts_l.append(A(f"F{i}", f"F{i}", 5.0, ef=None, af=act_fin,
                    status=ActivityStatus.COMPLETED, rem=0))
tmile = M("T", "T", ef=dd + timedelta(days=300))
frb_rels = [Relationship(f"F{i}", "T") for i in range(6)]
s0 = S(dd, acts_e + [tmile], frb_rels)
s1 = S(dd + timedelta(days=100), acts_l + [tmile], frb_rels)
sa = SA([s0, s1])
frb = forecast_reliability_band(sa)
for b in frb.buckets:
    if b.n:
        print(f"metric layer bucket {b.label}: n={b.n} bias={b.bias_days:+.1f} "
              f"P10={b.p10_days:+.1f} P90={b.p90_days:+.1f} "
              f"width={b.p90_days - b.p10_days:.1f} wd")
from scheduleiq.metrics.engine import load_matrix
matrix = load_matrix()
res = {r.check.id: r for r in li_series_results(sa, matrix) if r}
li03 = res.get("LI-03")
print(f"WIRED LI-03 value (band width) = {li03.value}  narrative: "
      f"{li03.narrative[:80]}")
print(f"findings text: {[f.detail for f in li03.findings][:2]}")

hdr("FRB-2 (FR2): overdue forecasts (horizon <= 0) fall out of every bucket")
acts_e = [A("O1", "O1", 5.0, ef=dd - timedelta(days=10)),
          A("O2", "O2", 5.0, ef=dd),
          A("O3", "O3", 5.0, ef=dd + timedelta(days=10))]
acts_l = [A(u, u, 5.0, ef=None, af=dd + timedelta(days=30), rem=0,
            status=ActivityStatus.COMPLETED) for u in ("O1", "O2", "O3")]
sa = SA([S(dd, acts_e, []), S(dd + timedelta(days=60), acts_l, [])])
frb = forecast_reliability_band(sa)
print(f"observations={len(frb.observations)}, "
      f"sum of bucket n = {sum(b.n for b in frb.buckets)}")

# =========================================================================
# LI-04 PCI
# =========================================================================
hdr("PCI-1 (K3): an LOE feeder path halves PCI on a single-threaded schedule")
rels = [Relationship("X", "T"), Relationship("L", "X")]
s_loe = S(dd, [A("X", "X", 0.0), M("T", "T", 0.0),
               A("L", "L", 0.0, atype=ActivityType.LOE)], rels)
sa = SA([s_loe, s_loe])
pci = run_li_indices(sa).pci
print(f"single real chain + LOE feeder: PCI per update = {pci.per_update}")
print("EXPECT (lineage-A C1 ruling): 1.0 single-threaded.  ACTUAL: 0.5 "
      "(the LOE-only path counts as a second path)")

hdr("PCI-2 (K2): negative-float driver inflates its share (w>1)")
rels = [Relationship("X", "T"), Relationship("Y", "T")]
mk = lambda tfx: S(dd, [A("X", "X", tfx), A("Y", "Y", 5.0), M("T", "T", 0.0)], rels)
for tfx in (0.0, -10.0):
    k = _build_kernel(mk(tfx), 5.0)
    ws = [kernel_weight(p.rel_float_days, 5.0) for p in k.paths]
    tot = sum(ws)
    pci_v = sum((w / tot) ** 2 for w in ws)
    print(f"driver TF {tfx:+.0f}: path weights {[round(w, 3) for w in ws]} "
          f"-> PCI {pci_v:.3f}")
print("A deepening-negative driver reads as RISING concentration purely "
      "through the w>1 premium (basis artifact, not structure)")

hdr("PCI-3 (C4): PCI is a strong function of the un-governed lambda")
rels = [Relationship(f"P{i}", "T") for i in range(5)]
s5 = S(dd, [A(f"P{i}", f"P{i}", float(2 * i)) for i in range(5)] +
       [M("T", "T", 0.0)], rels)
for lam in (1.0, 5.0, 50.0):
    sa5 = SA([s5, s5])
    v = run_li_indices(sa5, lam=lam).pci.per_update[0]
    print(f"lambda={lam:>5}: PCI = {v:.3f}")
print("Report Card grades PCI on fixed anchors [0.15,0.35] while lambda is a "
      "free parameter with no sensitivity set and no FCBI-style bound")

# =========================================================================
# LI-05 RDI
# =========================================================================
hdr("RDI-1 (A1): unusable series -> rdi_days = 0.0 (best score), not N/A")
s0 = S(None, [A("X", "X", 0.0), M("T", "T")], [Relationship("X", "T")])
s1 = S(None, [A("X", "X", 0.0), M("T", "T")], [Relationship("X", "T")])
sa = SA([s0, s1])
rdi = run_li_indices(sa).rdi
print(f"reason = {rdi.reason!r}")
print(f"rdi_days = {rdi.rdi_days} -> wired LI-05 value 0.0 -> piecewise "
      f"score 100 despite 'not computable'")

hdr("RDI-2 (R1): overrun invisible — demonstrated pace uses planned duration")
dd = datetime(2025, 1, 6, 8)
fin = datetime(2025, 12, 31, 17)
# A completes in window 1 (planned 10d, actually took ~40 cal days).
a_e = A("A", "A", 2.0, od=10, rem=10, ef=dd + timedelta(days=12))
a_l = A("A", "A", None, od=10, rem=0, status=ActivityStatus.COMPLETED,
        af=dd + timedelta(days=40), aslate=dd)
b_e = A("B", "B", 2.0, od=10, rem=10, ef=fin)
b_l = A("B", "B", 2.0, od=10, rem=10, ef=fin)
s0 = S(dd, [a_e, b_e, M("T", "T", ef=fin)], [], finish=fin)
s1 = S(dd + timedelta(days=42), [a_l, b_l, M("T", "T", ef=fin)], [], finish=fin)
sa = SA([s0, s1])
rdi = run_li_indices(sa).rdi
for r in rdi.rows:
    print(f"  {r.label}: required={r.required_pace} demonstrated="
          f"{r.demonstrated_pace} accrual={r.accrual_days:.1f}")
print("A 4x overrun contributes its full PLANNED 10d to demonstrated pace "
      "(lineage-A R1 ruling: AFFIRMED planned-scope basis + companion overrun "
      "ratio DISCLOSED — the companion ratio does not exist here)")

hdr("RDI-3 (R2/R3): accrual vs running MAX includes own window (mixed sampling)")
print("code: max_demo updated with window i's demonstrated BEFORE accrual of "
      "window i is computed; comparator is the running MAX (lineage-A v0.4.3 "
      "ruled P50 with max as disclosed bound)")

# =========================================================================
# LI-06 BDI
# =========================================================================
hdr("BDI-1 (A1): all-milestone driving path -> BDI = 0.0% ('fully baseline')")
mm1, mm2 = M("M1", "M1", 0.0, ef=dd + timedelta(days=5)), M("M2", "M2", 0.0)
s0 = S(dd, [mm1, mm2], [Relationship("M1", "M2")])
s1 = S(dd + timedelta(days=30), [mm1, mm2], [Relationship("M1", "M2")])
sa = SA([s0, s1])
bdi = baseline_dilution_index(sa)
print(f"bdi_pct = {bdi.bdi_pct}, reason = {bdi.reason!r}")
print("EXPECT: NOT APPLICABLE (zero-length basis).  ACTUAL: 0.0% == the "
      "'perfect fidelity' reading; scored 100 via [[0,100],...] curve")

hdr("BDI-2 (A3): step length = remaining-else-original mixes bases with progress")
x_e = A("X", "X", 0.0, od=20, rem=20)
x_l = A("X", "X", 0.0, od=20, rem=4, status=ActivityStatus.IN_PROGRESS)
n_l = A("N", "N", 0.0, od=10, rem=10)          # added post-baseline
s0 = S(dd, [x_e, M("T", "T")], [Relationship("X", "T")])
s1 = S(dd + timedelta(days=30), [x_l, n_l, M("T", "T")],
       [Relationship("X", "T"), Relationship("N", "T")])
sa = SA([s0, s1])
bdi = baseline_dilution_index(sa)
print(f"bdi_pct = {bdi.bdi_pct and round(bdi.bdi_pct, 1)}%  steps: "
      f"{[(st.code, st.baseline_original, st.length_days) for st in bdi.steps]}")
print("Post-baseline share rises as ORIGINAL work burns down (remaining 4d vs "
      "added 10d = 71%), though the added scope never changed — progress alone "
      "moves a 'dilution' number (A4: execution vs revision conflated)")

# =========================================================================
# LI-07 CDI
# =========================================================================
hdr("CDI-1 (C1): LOE + milestone + off-path fallback populate the leaderboard")
rels = [Relationship("X", "T")]
s = S(dd, [A("X", "X", 0.0), M("T", "T", 0.0),
           A("L", "L", 0.0, atype=ActivityType.LOE),
           A("ORPH", "ORPH", 4.0)], rels)
sa = SA([s, s])
cdi = run_li_indices(sa).cdi
print("leaderboard:", [(e.code, round(e.dwell_share, 3)) for e in cdi.leaderboard])
print("EXPECT: real work only (X; T is the marker, L is LOE, ORPH is on no "
      "path).  ACTUAL: all four earn dwell (LOE via kernel, ORPH via own-TF "
      "fallback, T as a zero-duration marker)")

hdr("CDI-2 (K2): negative-float premium skews dwell shares")
rels = [Relationship("X", "T"), Relationship("Y", "T")]
s = S(dd, [A("X", "X", -10.0), A("Y", "Y", 0.0), M("T", "T", 0.0)], rels)
sa = SA([s, s])
cdi = run_li_indices(sa).cdi
print("leaderboard:", [(e.code, round(e.dwell_share, 3)) for e in cdi.leaderboard])
print(f"X at TF -10 carries w = {kernel_weight(-10, 5.0):.1f} vs Y at 1.0 -> "
      "dwell allocation driven by the premium, not by time spent critical")

# =========================================================================
# LI-08 IL
# =========================================================================
hdr("IL-1 (IL1): same-window mitigation scores WORSE than doing nothing for a month")
dd = datetime(2025, 1, 6, 8)


def mkil(respond_same_window):
    x0 = A("X", "X", 2.0, od=20, rem=20)
    x1 = A("X", "X", -3.0, od=(10 if respond_same_window else 20),
           rem=(10 if respond_same_window else 20))
    x2 = A("X", "X", -3.0, od=10, rem=10)
    y = A("Y", "Y", 20.0)
    s0 = S(dd, [x0, y, M("T", "T")], [Relationship("X", "T")])
    s1 = S(dd + timedelta(days=30), [x1, y, M("T", "T")], [Relationship("X", "T")])
    s2 = S(dd + timedelta(days=60), [x2, y, M("T", "T")], [Relationship("X", "T")])
    return SA([s0, s1, s2])


for same in (True, False):
    sa = mkil(same)
    il = intervention_latency(sa)
    val, score, off = _li08_score(sa, {"points": [[0, 100], [2, 70], [6, 0]],
                                       "unresolved_only_score": 20.0})
    ev = il.events[0]
    print(f"duration halved in {'SAME window as' if same else 'window AFTER'} "
          f"emergence: unresolved={ev.unresolved}, il_updates={ev.il_updates}, "
          f"score={score}")
print("published anchor '0 updates -> 100' is unreachable (min latency 1); "
      "fastest responder reads 'did not act' (20)")

hdr("IL-2 (IL2): 1 responded + 5 ignored chains == perfect responder score")


def mk_multi():
    e_acts = [A(f"N{i}", f"N{i}", 2.0, od=20, rem=20) for i in range(6)] + \
             [M("T", "T")]
    l_acts = [A(f"N{i}", f"N{i}", -4.0, od=20, rem=20) for i in range(6)] + \
             [M("T", "T")]
    l2_acts = [A("N0", "N0", -4.0, od=10, rem=10)] + \
              [A(f"N{i}", f"N{i}", -4.0, od=20, rem=20) for i in range(1, 6)] + \
              [M("T", "T")]
    rels = [Relationship(f"N{i}", "T") for i in range(6)]
    return SA([S(dd, e_acts, rels), S(dd + timedelta(days=30), l_acts, rels),
               S(dd + timedelta(days=60), l2_acts, rels)])


sa = mk_multi()
il = intervention_latency(sa)
val, score, off = _li08_score(sa, {"points": [[0, 100], [2, 70], [6, 0]],
                                   "unresolved_only_score": 20.0})
print(f"events={len(il.events)}, unresolved={il.unresolved_count}, "
      f"median={il.median_il_updates}, score={score}")

hdr("IL-3 (IL3): sole emergence in the final window -> 20 ('did not act')")
x0 = A("X", "X", 2.0)
x1 = A("X", "X", -3.0)
sa = SA([S(dd, [x0, M("T", "T")], [Relationship("X", "T")]),
         S(dd + timedelta(days=30), [x1, M("T", "T")], [Relationship("X", "T")])])
val, score, off = _li08_score(sa, {"points": [[0, 100], [2, 70], [6, 0]],
                                   "unresolved_only_score": 20.0})
print(f"score = {score} though no later update exists in which to respond")

hdr("IL-4 (IL4): a hammock-only chain drives LI-08 to 20")
l0 = A("L", "L", 2.0, atype=ActivityType.LOE)
l1 = A("L", "L", -1.0, atype=ActivityType.LOE)
ok = A("K", "K", 10.0)
sa = SA([S(dd, [l0, ok, M("T", "T")], []),
         S(dd + timedelta(days=30), [l1, ok, M("T", "T")], []),
         S(dd + timedelta(days=60), [l1, ok, M("T", "T")], [])])
il = intervention_latency(sa)
val, score, off = _li08_score(sa, {"points": [[0, 100], [2, 70], [6, 0]],
                                   "unresolved_only_score": 20.0})
print(f"events={[(e.chain_codes, e.unresolved) for e in il.events]}, "
      f"score={score}")

# =========================================================================
# LI-09 BWI
# =========================================================================
hdr("BWI-1 (B1): a slipping milestone reads as bow-wave RELIEF")
w = A("W", "W", 2.0, od=10, rem=10, ef=datetime(2025, 5, 30, 17))
t0 = M("MS", "MS", 0.0, ef=datetime(2025, 6, 1, 17))
t1 = M("MS", "MS", 0.0, ef=datetime(2025, 9, 1, 17))
s0 = S(datetime(2025, 1, 6, 8), [w, t0], [Relationship("W", "MS")])
w1 = A("W", "W", 2.0, od=10, rem=10, ef=datetime(2025, 8, 30, 17))
s1 = S(datetime(2025, 2, 6, 8), [w1, t1], [Relationship("W", "MS")])
sa = SA([s0, s1])
bwi = run_li_indices(sa).bwi
print("rows:", [(r.label, r.density and round(r.density, 4),
                 r.bwi and round(r.bwi, 3)) for r in bwi.rows])
print("work unchanged, date 3 months WORSE -> EXPECT >= 1.0 under a fixed "
      "horizon (lineage-A B1 ruling).  ACTUAL < 1.0 (moving-forecast "
      "denominator reads the slip as relief)")

hdr("BWI-2 (B2/B4): re-coded target milestone silently drops later densities")
t0 = M("MS", "MS", 0.0, ef=datetime(2025, 6, 1, 17))
t1 = M("MS", "MS-NEW", 0.0, ef=datetime(2025, 6, 1, 17))   # re-coded, same UID
s0 = S(datetime(2025, 1, 6, 8), [w, t0], [Relationship("W", "MS")])
s1 = S(datetime(2025, 2, 6, 8), [w, t1], [Relationship("W", "MS")])
sa = SA([s0, s1])
bwi = run_li_indices(sa).bwi
print("rows:", [(r.label, r.density, r.bwi) for r in bwi.rows],
      "| reason:", bwi.reason or "-")

# =========================================================================
# LI-10 MML
# =========================================================================
hdr("MML-1 (A2): ratio can compare a resource window against an activity-day window")
root = WbsNode(uid="R", parent_uid=None, code="ROOT", name="root")
civ = WbsNode(uid="W1", parent_uid="R", code="CIV", name="civil")
dd0, dd1, dd2 = (datetime(2025, 1, 6, 8), datetime(2025, 2, 3, 8),
                 datetime(2025, 3, 3, 8))


def act_with_res(uid, au, wbs="W1", **kw):
    return A(uid, uid, 5.0, wbs=wbs,
             res=[ResourceAssignment(activity_uid=uid, resource_uid="r1",
                                     actual_units=au)], **kw)


# window 1: resource actuals move (basis=resource); window 2: no resource
# movement but one completion (basis=activity-day fallback).
a0 = act_with_res("A", 0.0)
a1 = act_with_res("A", 200.0)
a2 = act_with_res("A", 200.0)
b0 = A("B", "B", 5.0, wbs="W1", od=10, rem=10)
b1 = A("B", "B", 5.0, wbs="W1", od=10, rem=10)
b2 = A("B", "B", None, wbs="W1", od=10, rem=0, status=ActivityStatus.COMPLETED,
       af=dd2 - timedelta(days=3))
s0 = S(dd0, [a0, b0], [], wbs=[root, civ])
s1 = S(dd1, [a1, b1], [], wbs=[root, civ])
s2 = S(dd2, [a2, b2], [], wbs=[root, civ])
sa = SA([s0, s1, s2])
mml = measured_mile_locator(sa)
for wr in mml.wbs_results:
    for wrow in wr.windows:
        print(f"  {wrow.window_label}: basis={wrow.basis} "
              f"productivity={wrow.productivity and round(wrow.productivity, 3)}")
    print(f"  clean={wr.clean_window and wr.clean_window.basis} "
          f"impacted={wr.impacted_window and wr.impacted_window.basis} "
          f"ratio={wr.ratio and round(wr.ratio, 4)}")
print("ratio divides units/hour by activity-days/day — dimensionally "
      "incommensurable; the 'contrast' is a units artifact")

# =========================================================================
# W1 — wiring blast radius
# =========================================================================
hdr("W1: a None PCI window (or None BWI density) blanks ALL TEN LI indices")
s_nopaths = S(dd, [A("X", "X", None), M("T", "T", None)], [])
s_paths = S(dd + timedelta(days=30), [A("X", "X", 0.0), M("T", "T", 0.0)],
            [Relationship("X", "T")])
sa = SA([s_nopaths, s_paths])
try:
    out = li_series_results(sa, matrix)
    print(f"li_series_results returned {len(out)} results")
except Exception as e:
    print(f"li_series_results RAISED {type(e).__name__}: {e}")
    print("-> trend/series.py catches this blanket-style and skips ALL LI "
      "indices (six scored members silently drop to N/A)")

hdr("W2 (FR1-class): RDI/CDI/MML findings text reads wrong field names")
sa = mk_multi()   # reuse; has RDI rows
r = {x.check.id: x for x in li_series_results(sa, matrix) if x}
if "LI-05" in r and r["LI-05"].findings:
    print("LI-05 finding detail:", r["LI-05"].findings[0].detail)
s = S(dd, [A("X", "X", 0.0), M("T", "T", 0.0)], [Relationship("X", "T")])
sa2 = SA([s, s])
r2 = {x.check.id: x for x in li_series_results(sa2, matrix) if x}
if "LI-07" in r2 and r2["LI-07"].findings:
    print("LI-07 finding detail:", r2["LI-07"].findings[0].detail)
print("(RdiRow fields are required_pace/demonstrated_pace; CdiEntry field is "
      "dwell_share — the wiring getattr defaults mask them)")

print("\nDONE")
