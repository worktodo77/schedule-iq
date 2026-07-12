"""Tests for the five bespoke LI-record metrics (backlog N7/N8/N11/N13/N15;
ANALYTICS_PROPOSAL.md §9.2 LHL, §9.3 FRB, §10.1 BDI, §10.3 IL, §10.5 MML).

Uses the existing three-update fixture series (tests/fixtures/make_fixtures.py
is not modified for this module) plus small synthetic/hand-built cases for the
statistical primitives that are cheapest to validate against a known answer
in isolation (Kaplan-Meier median, percentile-band interpolation, chain
grouping) rather than by reverse-engineering the fixture's exact numbers.
"""
import math
import os
import subprocess
import sys

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "src")
sys.path.insert(0, SRC)

from scheduleiq.ingest import load, load_many                          # noqa: E402
from scheduleiq.trend.series import analyze_series, SeriesAnalysis     # noqa: E402
from scheduleiq.ingest.model import Schedule                           # noqa: E402
from scheduleiq.analytics import li_record as lr                       # noqa: E402
from scheduleiq.analytics.li_record import (                           # noqa: E402
    kaplan_meier, logic_half_life, forecast_reliability_band,
    frb_apply_forward, baseline_dilution_index, intervention_latency,
    measured_mile_locator, run_li_record, _connected_components,
    _bucket_stats)

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
BASELINE = os.path.join(FIX, "demo_baseline.xer")
U1 = os.path.join(FIX, "demo_update1.xer")
U2 = os.path.join(FIX, "demo_update2.xer")


@pytest.fixture(scope="session", autouse=True)
def fixtures():
    if not os.path.exists(BASELINE):
        subprocess.run([sys.executable, os.path.join(FIX, "make_fixtures.py")],
                       check=True)


@pytest.fixture(scope="session")
def baseline():
    return load(BASELINE)[0]


@pytest.fixture(scope="session")
def series():
    return analyze_series(load_many([BASELINE, U1, U2]))


# ==========================================================================
# Synthetic / known-answer tests
# ==========================================================================
def test_kaplan_meier_known_median():
    # 4 uncensored lifespans 1,2,3,4: S(1)=0.75, S(2)=0.75*(2/3)=0.5 -> median 2
    km = kaplan_meier([(1.0, False), (2.0, False), (3.0, False), (4.0, False)])
    assert km.n == 4
    assert km.censored == 0
    assert km.median == 2.0
    assert km.median_reached is True


def test_kaplan_meier_all_censored_reports_follow_up_bound():
    # ruling L2 (v0.4.5, ported): with no events the median is "not reached"
    # and the reported value is the LONGEST OBSERVED FOLLOW-UP, not None — so
    # a frozen network can still carry a quantified lower bound.
    km = kaplan_meier([(1.0, True), (2.0, True), (3.0, True)])
    assert km.n == 3
    assert km.censored == 3
    assert km.median == 3.0
    assert km.median_reached is False


def test_kaplan_meier_median_not_reached_reports_longest_follow_up():
    # T2 / ruling L2 (v0.4.5, ported): 1 death at t=0 among 19 censored at
    # t=5 — S stays above 0.5 through the end of follow-up, so the median
    # provably exceeds the longest observed lifespan.  The prior fallback
    # reported the last EVENT time (0.0 — the degenerate "at least zero"
    # bound the audit found live on the demo card); the ruled bound is 5.0.
    lifespans = [(0.0, False)] + [(5.0, True)] * 19
    km = kaplan_meier(lifespans)
    assert km.median == 5.0
    assert km.median_reached is False


def test_kaplan_meier_empty():
    km = kaplan_meier([])
    assert km.n == 0 and km.median is None


def test_bucket_stats_known_percentiles():
    # linear-interpolated percentiles of 1..10: P10=1.9, median=5.5, P90=9.1
    n, bias, p10, p90 = _bucket_stats([float(x) for x in range(1, 11)])
    assert n == 10
    assert math.isclose(bias, 5.5)
    assert math.isclose(p10, 1.9)
    assert math.isclose(p90, 9.1)


def test_bucket_stats_empty():
    assert _bucket_stats([]) == (0, None, None, None)


def test_connected_components_two_disjoint_chains():
    edges = [("A", "B"), ("B", "C"), ("X", "Y")]
    nodes = {"A", "B", "C", "X", "Y", "Z"}
    comps = _connected_components(edges, nodes)
    comps_sorted = sorted((frozenset(c) for c in comps), key=lambda c: sorted(c))
    expected = sorted((frozenset(c) for c in
                       [{"A", "B", "C"}, {"X", "Y"}, {"Z"}]), key=lambda c: sorted(c))
    assert comps_sorted == expected


# ==========================================================================
# N7 — LHL
# ==========================================================================
def test_lhl_overall_sample_and_censoring_are_consistent(series):
    """The fixture bug this test originally documented (removed_rels naming
    "PR_SS" for a PR_FS relationship, so the intended deletion never fired)
    was FIXED in the wave-A audit: A1050->A1070 is now genuinely deleted in
    update2.  The series carries exactly one observed relationship death
    (both endpoints incomplete, so it survives the ported v0.4.5 population
    rulings); with all other instances censored the KM curve never crosses
    0.5, so the median is the flagged lower bound (median_reached=False) at
    the longest observed follow-up — the 91-day u1->u2 window, ~3.0 months
    (previously this read "0.0 months").  KM arithmetic itself is proven by
    the synthetic known-answer tests above.
    """
    lhl = logic_half_life(series)
    assert lhl.overall is not None, lhl.reason
    assert lhl.overall.n >= 1
    assert 0 <= lhl.overall.censored <= lhl.overall.n
    assert lhl.overall.censored == lhl.overall.n - 1  # exactly one death: A1050->A1070 deleted in update2
    assert lhl.overall.median_reached is False        # curve never crosses 0.5
    assert lhl.overall.median_days == pytest.approx(91.0)   # longest follow-up bound
    assert lhl.overall.median_months == pytest.approx(91.0 / 30.44)
    assert lhl.first_pair_excluded is True            # 3 schedules: exclusion applied


def test_lhl_on_off_split_or_reason(series):
    lhl = logic_half_life(series)
    # either both on/off variants were produced, or a reason explains why not
    assert (lhl.on_path is not None and lhl.off_path is not None) or lhl.reason


def test_lhl_exclude_first_pair_toggle_runs(series):
    a = logic_half_life(series, exclude_first_pair=True)
    b = logic_half_life(series, exclude_first_pair=False)
    assert a.exclude_first_pair is True
    assert b.exclude_first_pair is False


def test_lhl_degrades_gracefully_on_short_series():
    empty = Schedule(project_id="EMPTY")
    res = logic_half_life(SeriesAnalysis(schedules=[empty]))
    assert res.overall is None
    assert res.reason


# ==========================================================================
# LHL governance-quartet tests — ported v0.4.5 audit rulings
# (docs/rulings/LI-02-lhl-port-2026-07-12.md; as-audited record
# docs/audit/LHL_audit_2026-07-09.md, tests T1-T11)
# ==========================================================================
from datetime import datetime, timedelta                               # noqa: E402

from scheduleiq.ingest.model import (Activity, ActivityStatus,          # noqa: E402
                                     ActivityType, Relationship, RelType)
from scheduleiq.analytics.li_record import _build_instances             # noqa: E402


def _lhl_act(uid, code=None, tf=40.0, atype=ActivityType.TASK,
             status=ActivityStatus.NOT_STARTED, es=None, ef=None):
    return Activity(uid=uid, code=code or uid, name=code or uid, atype=atype,
                    status=status, total_float_hours=tf,
                    original_duration_hours=80.0, remaining_duration_hours=80.0,
                    early_start=es, early_finish=ef)


def _lhl_rel(p, s, rt=RelType.FS, lag=0.0):
    return Relationship(pred_uid=p, succ_uid=s, rtype=rt, lag_hours=lag)


def _lhl_sched(acts, rels, dd):
    s = Schedule(project_id="SYN", data_date=dd)
    s.activities = {a.uid: a for a in acts}
    s.relationships = list(rels)
    return s


def _dd(k):
    return datetime(2025, 1, 1, 8) if k == 0 else datetime(2025, 1, 1, 8) + timedelta(days=k)


def _li02_override():
    from scheduleiq.scorecard import load_spec
    return load_spec()["series_curve_overrides"]["LI-02"]


def _pair_series(n_ties, dies, dds):
    """len(dds) schedules over ``n_ties`` disjoint ties; the first ``dies``
    ties disappear at the LAST schedule."""
    acts = lambda: [_lhl_act(f"N{i}") for i in range(2 * n_ties)]
    all_rels = [_lhl_rel(f"N{2*i}", f"N{2*i+1}") for i in range(n_ties)]
    out = []
    for j, d in enumerate(dds):
        rels = all_rels[dies:] if j == len(dds) - 1 else all_rels
        out.append(_lhl_sched(acts(), rels, d))
    return SeriesAnalysis(schedules=out)


# ---- T1 (L1): scoring branches pinned ------------------------------------
def test_t1_li02_frozen_network_scores_100():
    from scheduleiq.scorecard import _li02_score
    # 20 ties, zero churn, 2 schedules 30d apart: median not reached, 0%
    # died -> 100 (previously the inverted branch tested the CENSORED
    # fraction and scored this 70).  Value = follow-up bound (~0.99 mo).
    sa = _pair_series(20, dies=0, dds=[_dd(0), _dd(30)])
    v, sc, offenders = _li02_score(sa, _li02_override())
    assert sc == 100.0
    assert offenders == 0
    assert v == pytest.approx(30.0 / 30.44)


def test_t1_li02_not_reached_with_real_churn_scores_70():
    from scheduleiq.scorecard import _li02_score
    # 3 of 20 die (15% >= 10%), median not reached -> 70-point placeholder.
    sa = _pair_series(20, dies=3, dds=[_dd(0), _dd(30)])
    v, sc, offenders = _li02_score(sa, _li02_override())
    assert sc == 70.0
    assert offenders == 3


def test_t1_li02_reached_short_median_scores_zero():
    from scheduleiq.scorecard import _li02_score
    # all 20 die in a 15-day window: median reached at the 7.5d midpoint
    # (~0.25 mo <= 1 mo) -> 0.
    sa = _pair_series(20, dies=20, dds=[_dd(0), _dd(15)])
    v, sc, offenders = _li02_score(sa, _li02_override())
    assert sc == 0.0
    assert offenders == 20
    assert v == pytest.approx(7.5 / 30.44)


# ---- T2 (L2): not-reached bound = longest follow-up (KM level is covered
# by test_kaplan_meier_median_not_reached_reports_longest_follow_up) -------
def test_t2_lhl_not_reached_reports_follow_up_not_event_time():
    # 1 early death among many survivors: the metric-level bound must be
    # the full follow-up (60d), not the death time.
    sa = _pair_series(10, dies=0, dds=[_dd(0), _dd(30), _dd(60)])
    # kill one tie in the FIRST window instead (present u0 only)
    sa.schedules[1].relationships = sa.schedules[1].relationships[1:]
    sa.schedules[2].relationships = sa.schedules[2].relationships[1:]
    lhl = logic_half_life(sa, exclude_first_pair=False)
    assert lhl.overall.median_reached is False
    assert lhl.overall.median_days == pytest.approx(60.0)


# ---- T3 (L3): code-keying retained, disclosed -----------------------------
def test_t3_recode_reads_as_death_plus_rebirth():
    """Ruling L3 (kept deliberately): signatures are keyed by activity CODE,
    so a UID-stable re-code reads as one logic death + one rebirth.  This is
    the CHOSEN convention — consistent with the code-keyed logic-churn diff
    (compare.diff / TRD-03) and robust to UID churn on re-export — not an
    accident; moving LHL to UID keying is a governance change that must be
    made jointly with TRD-03.  The consequence is disclosed on every result.
    """
    def mk(code_a, dd):
        acts = [_lhl_act("uidA", code_a), _lhl_act("uidB", "B"),
                _lhl_act("uidC", "C"), _lhl_act("uidD", "D")]
        return _lhl_sched(acts, [_lhl_rel("uidA", "uidB"), _lhl_rel("uidC", "uidD")], dd)
    sa = SeriesAnalysis(schedules=[mk("A100", _dd(0)), mk("A100R", _dd(30)),
                                   mk("A100R", _dd(60))])
    lhl = logic_half_life(sa, exclude_first_pair=False)
    assert lhl.overall.n == 3                      # (A100,B) dead + (A100R,B) + (C,D)
    assert lhl.overall.n - lhl.overall.censored == 1   # exactly one (spurious) death
    assert any("re-coded" in d for d in lhl.disclosures)


# ---- T4 (L4a/L4b): population rulings -------------------------------------
def test_t4_loe_attached_ties_excluded():
    def mk(dd):
        acts = [_lhl_act("A"), _lhl_act("B"), _lhl_act("L1", atype=ActivityType.LOE)]
        rels = [_lhl_rel("A", "B"), _lhl_rel("L1", "A"), _lhl_rel("A", "L1")]
        return _lhl_sched(acts, rels, dd)
    sa = SeriesAnalysis(schedules=[mk(_dd(0)), mk(_dd(30))])
    lhl = logic_half_life(sa)
    assert lhl.overall.n == 1                      # only the task-task tie observed


def test_t4_completed_ties_no_longer_inflate_survival():
    """Ruling L4b: previously, immortal completed-work ties inflated S(t) and
    flipped a reached ~1-month median (score 0) to not-reached (score 70).
    Now ties born on completed work are unobserved, so the two populations
    score identically."""
    from scheduleiq.scorecard import _li02_score
    live = [_lhl_rel(f"L{2*i}", f"L{2*i+1}") for i in range(6)]
    comp = [_lhl_rel(f"C{2*i}", f"C{2*i+1}") for i in range(6)]
    def mk(rels, dd):
        acts = [_lhl_act(f"L{i}") for i in range(12)] + \
               [_lhl_act(f"C{i}", status=ActivityStatus.COMPLETED) for i in range(12)]
        return _lhl_sched(acts, rels, dd)
    def series(extra):
        return SeriesAnalysis(schedules=[
            mk(live + extra, _dd(0)), mk(live + extra, _dd(30)),
            mk(live[:2] + extra, _dd(60))])
    base = logic_half_life(series([]), exclude_first_pair=False)
    with_comp = logic_half_life(series(comp), exclude_first_pair=False)
    assert with_comp.overall.n == base.overall.n == 6
    assert with_comp.overall.median_days == base.overall.median_days
    assert with_comp.overall.median_reached == base.overall.median_reached
    v1, s1, _ = _li02_score(series([]), _li02_override())
    v2, s2, _ = _li02_score(series(comp), _li02_override())
    assert s1 == s2


def test_t4_tie_censored_at_completion_mid_life():
    def mk(status, dd):
        acts = [_lhl_act("A", status=status), _lhl_act("B", status=status)]
        return _lhl_sched(acts, [_lhl_rel("A", "B")], dd)
    scheds = [mk(ActivityStatus.IN_PROGRESS, _dd(0)),
              mk(ActivityStatus.COMPLETED, _dd(30)),
              mk(ActivityStatus.COMPLETED, _dd(60))]
    insts = _build_instances(scheds)
    assert len(insts) == 1
    assert insts[0].censored is True
    assert insts[0].completed_at_idx == 1          # observation stops at completion


# ---- T5 (L5/L7): day basis + midpoint dating ------------------------------
def test_t5_day_basis_immune_to_irregular_cadence():
    """Rulings L5+L7: lifespans in calendar days between data dates, deaths
    at the disappearance-window midpoint.  Two ties die during the second
    window in both series; the reported median must be the actual midpoint
    day count — 21 + 92/2 = 67d irregular, 92 + 92/2 = 138d uniform — not an
    update count priced at the cadence mean (previously: 56.5d and 92d)."""
    for i1, i2, expect in ((21, 92, 67.0), (92, 92, 138.0)):
        sa = _pair_series(4, dies=2, dds=[_dd(0), _dd(i1), _dd(i1 + i2)])
        lhl = logic_half_life(sa, exclude_first_pair=False)
        assert lhl.overall.median_reached is True
        assert lhl.overall.median_days == pytest.approx(expect)
        assert lhl.overall.median_months == pytest.approx(expect / 30.44)


# ---- T6 (L6): exclusion mechanics honestly reported -----------------------
def test_t6_two_schedule_exclusion_not_applied_and_disclosed():
    sa = _pair_series(4, dies=1, dds=[_dd(0), _dd(30)])
    lhl = logic_half_life(sa, exclude_first_pair=True)
    assert lhl.exclude_first_pair is True          # the request
    assert lhl.first_pair_excluded is False        # what actually happened
    assert any("NOT APPLIED" in d for d in lhl.disclosures)
    assert lhl.overall.n - lhl.overall.censored == 1   # baseline-window death observed


def test_t6_three_schedule_exclusion_drops_baseline_cohort():
    # A->B dies in the BASELINE window; C->D and E->F survive throughout.
    def mk(rels, dd):
        acts = [_lhl_act(u) for u in "ABCDEF"]
        return _lhl_sched(acts, rels, dd)
    r_ab, r_cd, r_ef = _lhl_rel("A", "B"), _lhl_rel("C", "D"), _lhl_rel("E", "F")
    scheds = [mk([r_ab, r_cd, r_ef], _dd(0)), mk([r_cd, r_ef], _dd(30)),
              mk([r_cd, r_ef], _dd(60))]
    ex = logic_half_life(SeriesAnalysis(schedules=scheds), exclude_first_pair=True)
    assert ex.first_pair_excluded is True
    assert ex.overall.n == 2                       # baseline-window death unobserved
    assert ex.overall.censored == 2
    assert ex.overall.median_days == pytest.approx(30.0)  # clock starts at update 1
    inc = logic_half_life(SeriesAnalysis(schedules=scheds), exclude_first_pair=False)
    assert inc.overall.n == 3                      # death visible when included


# ---- T7 (L8): any-point-in-life split + silent-drop disclosure ------------
def _flip_sched(a_tf, x_tf, dd, extra=()):
    A = _lhl_act("A", tf=a_tf, es=dd, ef=dd + timedelta(days=10))
    B = _lhl_act("B", tf=a_tf, es=dd + timedelta(days=10), ef=dd + timedelta(days=20))
    C = _lhl_act("C", tf=0.0, es=dd + timedelta(days=20), ef=dd + timedelta(days=30))
    X = _lhl_act("X", tf=x_tf, es=dd, ef=dd + timedelta(days=20))
    D = _lhl_act("D", tf=400.0, es=dd, ef=dd + timedelta(days=5))
    E = _lhl_act("E", tf=400.0, es=dd + timedelta(days=5), ef=dd + timedelta(days=10))
    rels = [_lhl_rel("A", "B"), _lhl_rel("B", "C"), _lhl_rel("X", "C"),
            _lhl_rel("D", "E")] + list(extra)
    return _lhl_sched([A, B, C, X, D, E], rels, dd)


def test_t7_on_path_membership_at_any_point_in_life():
    """Ruling L8 ("ever became driving"): X->C is off the driving path at
    birth (u0: A->B->C drives) but becomes THE driving edge at u1/u2 — it
    must land in the on-path bucket.  D->E never drives: off-path."""
    scheds = [_flip_sched(0.0, 40.0, _dd(0)), _flip_sched(40.0, 0.0, _dd(30)),
              _flip_sched(40.0, 0.0, _dd(60))]
    lhl = logic_half_life(SeriesAnalysis(schedules=scheds), exclude_first_pair=False)
    assert lhl.on_path is not None and lhl.off_path is not None
    assert lhl.on_path.n == 3                      # (A,B), (B,C) and the joiner (X,C)
    assert lhl.off_path.n == 1                     # (D,E)
    assert lhl.on_off_ratio is None                # both unreached -> suppressed (L2)
    assert any("suppressed" in d for d in lhl.disclosures)
    assert any("ANY update" in d for d in lhl.disclosures)


def test_t7_completion_update_counts_for_split_classification():
    """v0.4.5 peer-review finding 1 (ported): a tie that becomes driving in
    the SAME update both its endpoints complete is alive (present) at that
    update, so under the ruled "any update while alive" convention it is
    ON-path — even though observation (censoring) stops there.  Pre-fix, the
    completion update was omitted from the classification range and the tie
    read off-path."""
    def mk(a_tf, x_tf, dd, xc_done):
        st = ActivityStatus.COMPLETED if xc_done else ActivityStatus.NOT_STARTED
        A = _lhl_act("A", tf=a_tf, es=dd, ef=dd + timedelta(days=10))
        B = _lhl_act("B", tf=a_tf, es=dd + timedelta(days=10), ef=dd + timedelta(days=20))
        C = _lhl_act("C", tf=0.0, status=st, es=dd + timedelta(days=20),
                     ef=dd + timedelta(days=30))
        X = _lhl_act("X", tf=x_tf, status=st, es=dd, ef=dd + timedelta(days=20))
        return _lhl_sched([A, B, C, X], [_lhl_rel("A", "B"), _lhl_rel("B", "C"),
                                         _lhl_rel("X", "C")], dd)
    # u0: A->B->C drives, X->C floaty/off.  u1: X and C complete AND X->C is
    # now the min-float (driving) edge.  u2: unchanged.
    scheds = [mk(0.0, 40.0, _dd(0), False), mk(40.0, 0.0, _dd(30), True),
              mk(40.0, 0.0, _dd(60), True)]
    insts = _build_instances(scheds)
    xc = next(i for i in insts if i.key == ("X", "C", "FS"))
    assert xc.censored is True and xc.completed_at_idx == 1
    assert xc.last_alive_idx == 1                  # present at the completion update
    lhl = logic_half_life(SeriesAnalysis(schedules=scheds), exclude_first_pair=False)
    assert lhl.on_path is not None and lhl.on_path.n == 3   # X->C lands ON-path
    assert (lhl.off_path.n if lhl.off_path else 0) == 0


def test_t7_split_drop_counted_and_disclosed():
    # A tie born and dead entirely inside an update whose driving path is
    # unresolvable (no activity dates) cannot be classified: it must be
    # counted in split_dropped and disclosed, not silently vanish.
    s0 = _flip_sched(0.0, 40.0, _dd(0))
    dateless = [_lhl_act(u, tf=0.0) for u in "ABCX"] + \
               [_lhl_act("D", tf=400.0), _lhl_act("E", tf=400.0),
                _lhl_act("N1"), _lhl_act("N2")]
    s1 = _lhl_sched(dateless, [_lhl_rel("A", "B"), _lhl_rel("B", "C"),
                               _lhl_rel("X", "C"), _lhl_rel("D", "E"),
                               _lhl_rel("N1", "N2")], _dd(30))
    s2 = _flip_sched(40.0, 0.0, _dd(60))           # N1->N2 gone: died at u1 only
    lhl = logic_half_life(SeriesAnalysis(schedules=[s0, s1, s2]),
                          exclude_first_pair=False)
    assert lhl.split_dropped == 1
    split_n = (lhl.on_path.n if lhl.on_path else 0) + \
              (lhl.off_path.n if lhl.off_path else 0)
    assert split_n + lhl.split_dropped == lhl.overall.n
    assert any("unclassifiable" in d for d in lhl.disclosures)


# ---- T8 (X1): standing disclosures ----------------------------------------
def test_t8_standing_disclosures_present(series):
    lhl = logic_half_life(series)
    text = "\n".join(lhl.disclosures)
    for needle in ("Signature", "CODE", "duplicate",        # signature definition + X2
                   "LOE", "both endpoints complete",        # population
                   "calendar days", "midpoint", "30.44",    # units basis
                   "censored"):                             # censoring stats
        assert needle in text, f"missing disclosure: {needle}"
    assert any("Baseline pair excluded" in d for d in lhl.disclosures)


def test_t8_wiring_narrative_rounds_and_carries_censoring(series):
    from scheduleiq.analytics.li_wiring import li_series_results
    from scheduleiq.metrics.engine import load_matrix
    r = next(x for x in li_series_results(series, load_matrix())
             if x.check.id == "LI-02")
    assert "censored" in r.narrative
    assert "months" in r.narrative
    # rounded presentation, not a repr'd float
    assert ".989487" not in r.narrative
    assert any(f.detail and "Signature" in f.detail for f in r.findings)


# ---- T9 (L9): data-date validation ----------------------------------------
def test_t9_out_of_order_dates_never_yield_negative_months():
    from scheduleiq.scorecard import _li02_score
    sa = _pair_series(4, dies=2, dds=[_dd(60), _dd(30), _dd(0)])
    lhl = logic_half_life(sa, exclude_first_pair=False)
    assert lhl.overall.median_months is None       # withheld, not negative
    assert any("MONTHS BASIS UNAVAILABLE" in d for d in lhl.disclosures)
    v, sc, _ = _li02_score(sa, _li02_override())
    assert sc is None                              # ungradeable, not 0-via-negative


def test_t9_same_day_and_missing_dates_are_ungradeable_not_silent():
    from scheduleiq.scorecard import _li02_score
    for dds in ([_dd(0), _dd(0), _dd(0)], [None, None, None]):
        sa = _pair_series(4, dies=2, dds=dds)
        lhl = logic_half_life(sa, exclude_first_pair=False)
        assert lhl.overall.median_months is None
        assert any("MONTHS BASIS UNAVAILABLE" in d for d in lhl.disclosures)
        v, sc, _ = _li02_score(sa, _li02_override())
        assert sc is None


def test_t9_missing_date_outside_used_cohort_still_grades():
    # baseline data date missing, but the default exclusion drops the
    # baseline from the cohort: the used schedules carry valid dates, so the
    # day basis stands (the sane partial degradation, pinned).
    sa = _pair_series(4, dies=1, dds=[None, _dd(30), _dd(60)])
    lhl = logic_half_life(sa, exclude_first_pair=True)
    assert lhl.first_pair_excluded is True
    assert lhl.overall.median_months is not None


# ---- T10 (L10): reached median with no usable dates is NEVER censoring-scored
def test_t10_reached_median_without_dates_is_ungradeable_not_100():
    """The audit's L1xL10 compound: 19/20 ties die (maximal churn); with no
    data dates the prior code skipped the reached curve, fell into the
    censoring branch, and the inverted test awarded 100.  Ruled: ungradeable
    (None), never any branch score."""
    from scheduleiq.scorecard import _li02_score
    sa = _pair_series(20, dies=19, dds=[None, None])
    lhl = logic_half_life(sa, exclude_first_pair=False)
    assert lhl.overall.median_reached is True      # reached in update units
    assert lhl.overall.median_months is None       # but no months basis
    v, sc, offenders = _li02_score(sa, _li02_override())
    assert sc is None and v is None
    assert offenders == 19
    # identical churn WITH dates scores at the bottom of the curve
    sa2 = _pair_series(20, dies=19, dds=[_dd(0), _dd(15)])
    v2, sc2, _ = _li02_score(sa2, _li02_override())
    assert sc2 == 0.0


# ---- T11 (X2): duplicate-tie lag-tuple semantics ---------------------------
def test_t11_duplicate_tie_deletion_reads_as_merged_modification():
    def mk(lags, dd):
        acts = [_lhl_act("A"), _lhl_act("B")]
        return _lhl_sched(acts, [_lhl_rel("A", "B", lag=x) for x in lags], dd)
    scheds = [mk([0.0, 16.0], _dd(0)), mk([0.0], _dd(30)), mk([0.0], _dd(60))]
    insts = _build_instances(scheds)
    assert len(insts) == 2
    died = [i for i in insts if not i.censored]
    assert len(died) == 1 and died[0].lag_state == (0.0, 16.0)
    survivor = [i for i in insts if i.censored][0]
    assert survivor.lag_state == (0.0,) and survivor.birth_idx == 1
    # and the collapse is disclosed on the metric result
    lhl = logic_half_life(SeriesAnalysis(schedules=scheds), exclude_first_pair=False)
    assert any("duplicate" in d for d in lhl.disclosures)


# ==========================================================================
# N8 — FRB
# ==========================================================================
def test_frb_has_at_least_one_populated_bucket(series):
    frb = forecast_reliability_band(series)
    assert any(b.n >= 1 for b in frb.buckets)
    assert len(frb.buckets) == 5          # incl. the overdue(<=0d) bucket (FR2)
    for obs in frb.observations:
        assert math.isfinite(obs.error_days)
        assert math.isfinite(obs.horizon_days)


def test_frb_bucket_stats_match_observations(series):
    frb = forecast_reliability_band(series)
    for b in frb.buckets:
        errs = [o.error_days for o in frb.observations if b.lo < o.horizon_days <= b.hi]
        assert b.n == len(errs)
        if b.n:
            assert b.bias_days is not None
            assert b.p10_days is not None and b.p90_days is not None


def test_frb_apply_forward_low_n_returns_reason(series):
    frb = forecast_reliability_band(series)
    # a horizon bucket with fewer than 5 observations must refuse to band
    lo, hi, reason = frb_apply_forward(frb, series.schedules[-1].data_date, None)
    assert lo is None and hi is None and reason


def test_frb_empty_series_never_raises():
    res = forecast_reliability_band(SeriesAnalysis(schedules=[Schedule(project_id="EMPTY")]))
    assert res.observations == []
    assert res.reason


# ==========================================================================
# N11 — BDI
# ==========================================================================
def test_bdi_in_valid_range(series):
    bdi = baseline_dilution_index(series)
    assert bdi.bdi_pct is not None
    assert 0.0 <= bdi.bdi_pct <= 100.0
    assert bdi.steps, "expected the latest driving path to have steps"


def test_bdi_classifies_a1210_if_on_latest_driving_path(series):
    """A1210 (Rework Foundations A1) is added fresh in the 2025-07-07 update
    as an alternate route into A1060.  If the driving-path walk (float-first,
    per analytics.paths) happens to select it, it must be classified
    post-baseline with first-appearance at the 2025-07-07 update; if the walk
    instead keeps the original A1040->A1060 edge, A1210 simply won't be on
    the path and this assertion is skipped rather than forced.
    """
    bdi = baseline_dilution_index(series)
    step = next((s for s in bdi.steps if s.code == "A1210"), None)
    if step is None:
        pytest.skip("A1210 is not on the latest driving path in this fixture run")
    assert not step.baseline_original
    el = next((e for e in bdi.decomposition if e.code == "A1210"), None)
    assert el is not None
    assert "2025-07-07" in el.first_appeared


def test_bdi_degrades_gracefully_on_single_schedule(baseline):
    res = baseline_dilution_index(SeriesAnalysis(schedules=[baseline]))
    assert res.reason


# ==========================================================================
# N13 — IL
# ==========================================================================
def test_il_finds_emergence_events(series):
    il = intervention_latency(series)
    assert il.events, "expected at least one negative-float emergence event " \
        "(fixture seeds negative float from update1)"
    resolved = [e for e in il.events if not e.unresolved]
    # KM headline (Wave-2 IL2-A): exactly one of median / follow-up bound is
    # populated whenever any event carries latency information
    assert (il.median_il_updates is not None) == il.median_reached
    if il.median_il_updates is None and il.events:
        assert il.follow_up_bound_updates is not None or all(
            e.unresolved and (e.censored_at_updates or 0) == 0 for e in il.events)
    assert il.unresolved_count == sum(1 for e in il.events if e.unresolved)
    assert il.unresolved_count + len(resolved) == len(il.events)
    for e in il.events:
        assert e.chain_codes
        if not e.unresolved:
            assert e.il_updates is not None and e.il_updates >= 0   # 0 = same-window (IL1-A)
            assert e.response_detail
        else:
            assert e.censored_at_updates is not None and e.censored_at_updates >= 0


def test_il_no_negative_float_never_raises():
    res = intervention_latency(SeriesAnalysis(schedules=[Schedule(project_id="EMPTY")]))
    assert res.events == []
    assert res.reason


# ==========================================================================
# N15 — MML
# ==========================================================================
def test_mml_per_wbs_rows_and_ratio_bounds(series):
    mml = measured_mile_locator(series)
    assert mml.wbs_results, "expected one row per top-level WBS node"
    saw_activity_day_fallback = False
    for wr in mml.wbs_results:
        for w in wr.windows:
            assert w.basis in ("resource", "activity-day fallback")
            if w.basis == "activity-day fallback":
                saw_activity_day_fallback = True
        if wr.ratio is not None:
            assert 0.0 <= wr.ratio <= 1.0
    # the fixture's resource data is sparse (only 4 of ~20 activities are
    # resourced), so most WBS nodes should fall back to activity-days.
    assert saw_activity_day_fallback


def test_mml_caption_is_preliminary(series):
    mml = measured_mile_locator(series)
    assert "preliminary" in mml.caption


def test_mml_degrades_gracefully_on_single_schedule(baseline):
    res = measured_mile_locator(SeriesAnalysis(schedules=[baseline]))
    assert res.reason


# ==========================================================================
# bundle
# ==========================================================================
def test_run_li_record_bundles_all_five(series):
    bundle = run_li_record(series)
    assert bundle.lhl is not None
    assert bundle.frb is not None
    assert bundle.bdi is not None
    assert bundle.il is not None
    assert bundle.mml is not None


def test_run_li_record_never_raises_on_empty_series():
    bundle = run_li_record(SeriesAnalysis(schedules=[]))
    assert bundle.lhl.reason
    assert bundle.frb.reason
    assert bundle.bdi.reason
    assert bundle.il.reason
    assert bundle.mml.reason


# ==========================================================================
# Wave 2 — IL (LI-08) + FRB (LI-03) rulings (docs/rulings/LI-08-il-v2 +
# LI-03-frb-v2, 2026-07-12; audit tests U2-U9)
# ==========================================================================
def _il_act(uid, tf_days, *, od=10, status=ActivityStatus.NOT_STARTED,
            atype=ActivityType.TASK):
    return Activity(uid=uid, code=uid, name=uid, atype=atype, status=status,
                    total_float_hours=None if tf_days is None else tf_days * 8.0,
                    original_duration_hours=od * 8.0,
                    remaining_duration_hours=od * 8.0)


def _il_sched(dd, acts, rels=()):
    s = Schedule(project_id="IL", data_date=dd)
    s.activities = {a.uid: a for a in acts}
    s.relationships = list(rels)
    return s


def _il_sa(scheds):
    from scheduleiq.compare.diff import compare
    css = [compare(scheds[i], scheds[i + 1]) for i in range(len(scheds) - 1)]
    return SeriesAnalysis(schedules=scheds, changesets=css)


def _li08_override():
    from scheduleiq.scorecard import load_spec
    return load_spec()["series_curve_overrides"]["LI-08"]


def test_u2_same_window_response_is_latency_zero_and_anchor_reachable():
    """IL1-A: a duration halved in the SAME window the float turns negative
    reads latency 0, and the published 100-point anchor fires (previously
    the event read unresolved and scored 20 — the fastest responder got the
    worst grade)."""
    from scheduleiq.scorecard import _li08_score
    s0 = _il_sched(_dd(0), [_il_act("X", 2.0, od=20), _il_act("Y", 20.0)],
                   [_lhl_rel("X", "Y")])
    s1 = _il_sched(_dd(30), [_il_act("X", -3.0, od=10), _il_act("Y", 20.0)],
                   [_lhl_rel("X", "Y")])
    s2 = _il_sched(_dd(60), [_il_act("X", -3.0, od=10), _il_act("Y", 20.0)],
                   [_lhl_rel("X", "Y")])
    sa = _il_sa([s0, s1, s2])
    il = intervention_latency(sa)
    ev = il.events[0]
    assert not ev.unresolved and ev.il_updates == 0
    assert il.median_reached and il.median_il_updates == 0.0
    v, sc, off = _li08_score(sa, _li08_override())
    assert sc == 100.0 and off == 0


def test_u3_ignored_chains_pull_the_score_to_did_not_act():
    """IL2-A: 1 chain responded in 1 update + 5 ignored -> KM median not
    reached (S(1)=5/6) -> 20 with the follow-up bound as the value
    (previously scored 85, identical to a perfect responder)."""
    from scheduleiq.scorecard import _li08_score
    def mk(dd, tfs, od0):
        acts = [_il_act(f"N{i}", tfs, od=(od0 if i == 0 else 20))
                for i in range(6)] + [_il_act("T", 20.0)]
        rels = [_lhl_rel(f"N{i}", "T") for i in range(6)]
        return _il_sched(dd, acts, rels)
    s0 = mk(_dd(0), 2.0, 20)
    s1 = mk(_dd(30), -4.0, 20)
    s2 = mk(_dd(60), -4.0, 10)          # N0 duration halved in window 2
    sa = _il_sa([s0, s1, s2])
    il = intervention_latency(sa)
    assert il.unresolved_count == 5
    assert not il.median_reached and il.median_il_updates is None
    assert il.follow_up_bound_updates == 1.0
    v, sc, off = _li08_score(sa, _li08_override())
    assert sc == 20.0 and off == 5 and v == 1.0


def test_u4_sole_final_window_emergence_is_na_not_20():
    """IL3 (subsumed by IL2-A): a 2-schedule series whose only emergence is
    in the final window has zero latency information — censored at 0 —
    and LI-08 is ungradeable, no longer 'did not act' (20)."""
    from scheduleiq.scorecard import _li08_score
    s0 = _il_sched(_dd(0), [_il_act("X", 2.0)], [])
    s1 = _il_sched(_dd(30), [_il_act("X", -3.0)], [])
    sa = _il_sa([s0, s1])
    il = intervention_latency(sa)
    assert il.events and il.events[0].censored_at_updates == 0
    v, sc, off = _li08_score(sa, _li08_override())
    assert sc is None and v is None
    assert off == 1                     # still disclosed as an offender count


def test_u5_loe_and_completed_excluded_from_emergence_population():
    """IL4a/IL4b: a hammock flipping negative is not an emergence chain; an
    activity completed in the later file is not a mitigable problem; a mixed
    chain keeps its discrete member only."""
    l0 = _il_act("L", 2.0, atype=ActivityType.LOE)
    l1 = _il_act("L", -1.0, atype=ActivityType.LOE)
    c0 = _il_act("C", 2.0)
    c1 = _il_act("C", -1.0, status=ActivityStatus.COMPLETED)
    x0, x1 = _il_act("X", 2.0), _il_act("X", -1.0)
    rels = [_lhl_rel("L", "X")]
    sa = _il_sa([_il_sched(_dd(0), [l0, c0, x0], rels),
                 _il_sched(_dd(30), [l1, c1, x1], rels),
                 _il_sched(_dd(60), [l1, c1, x1], rels)])
    il = intervention_latency(sa)
    assert len(il.events) == 1
    assert il.events[0].chain_codes == ["X"]        # L and C excluded


def test_u6_out_of_order_dates_withhold_day_figures_only():
    """IL5 (the L9 convention): reversed data dates never yield a negative
    il_days — day figures are withheld with a disclosure; the scored
    update-unit latency is unaffected."""
    s0 = _il_sched(_dd(60), [_il_act("X", 2.0, od=20)], [])
    s1 = _il_sched(_dd(30), [_il_act("X", -3.0, od=20)], [])
    s2 = _il_sched(_dd(0), [_il_act("X", -3.0, od=10)], [])
    sa = _il_sa([s0, s1, s2])
    il = intervention_latency(sa)
    ev = il.events[0]
    assert ev.il_updates == 1 and ev.il_days is None
    assert il.median_il_days is None
    assert any("DAY FIGURES WITHHELD" in d for d in il.disclosures)


def test_u7_overdue_forecasts_are_bucketed_and_counts_reconcile():
    """FR2: horizons -10/0/+10 all land in a bucket (the first two in
    overdue(<=0d)); sum of bucket n equals the observation count."""
    from datetime import timedelta as _td
    dd = _dd(0)
    def fa(uid, ef):
        a = _il_act(uid, 5.0)
        a.early_finish = ef
        return a
    def done(uid):
        a = _il_act(uid, 5.0, status=ActivityStatus.COMPLETED)
        a.remaining_duration_hours = 0.0
        a.actual_finish = dd + _td(days=30)
        return a
    s0 = _il_sched(dd, [fa("O1", dd - _td(days=10)), fa("O2", dd),
                        fa("O3", dd + _td(days=10))])
    s1 = _il_sched(dd + _td(days=60), [done("O1"), done("O2"), done("O3")])
    frb = forecast_reliability_band(_il_sa([s0, s1]))
    assert len(frb.observations) == 3
    assert sum(b.n for b in frb.buckets) == 3
    overdue = next(b for b in frb.buckets if b.label.startswith("overdue"))
    assert overdue.n == 2
    assert frb.disclosures and any("AUTOCORRELATED" in d for d in frb.disclosures)


def test_u8_thin_bucket_is_not_evaluated_through_the_wiring():
    """FR3: a largest bucket with n < 5 leaves LI-03 NOT EVALUATED (None)
    through li_series_results — a single resolved forecast can no longer
    certify a forecaster at 100."""
    from scheduleiq.analytics.li_wiring import li_series_results
    from scheduleiq.metrics.engine import load_matrix
    from datetime import timedelta as _td
    dd = _dd(0)
    f = _il_act("F1", 5.0)
    f.early_finish = dd + _td(days=10)
    d = _il_act("F1", 5.0, status=ActivityStatus.COMPLETED)
    d.remaining_duration_hours = 0.0
    d.actual_finish = dd + _td(days=10)
    sa = _il_sa([_il_sched(dd, [f]), _il_sched(dd + _td(days=40), [d])])
    r = next(x for x in li_series_results(sa, load_matrix())
             if x.check.id == "LI-03")
    assert r.value is None
    assert "NOT EVALUATED" in r.narrative and "< 5" in r.narrative


# ==========================================================================
# Wave 4a — BDI fixed-basis revision (docs/rulings/LI-06-bdi-v2-2026-07-12.md)
# ==========================================================================
def _bdi_act(uid, *, od=10, rem=None, tf=8.0, atype=ActivityType.TASK,
             status=ActivityStatus.NOT_STARTED, ef=None):
    return Activity(uid=uid, code=uid, name=uid, atype=atype, status=status,
                    total_float_hours=tf * 8.0,
                    original_duration_hours=od * 8.0,
                    remaining_duration_hours=(od if rem is None else rem) * 8.0,
                    early_finish=ef)


def _bdi_sched(dd, acts, rels):
    s = Schedule(project_id="BDI", data_date=dd)
    s.activities = {a.uid: a for a in acts}
    s.relationships = list(rels)
    return s


def test_bdi_progress_invariant_fixed_length_basis():
    """Q-G ruling: the dilution share must not move with mere progress.
    Original step X (od 20) + added step N (od 10): BDI = 10/30 = 33.3%
    whether X has 20 or 4 days remaining (previously 10/(4+10) = 71.4% after
    burn-down — execution alone inflated 'dilution')."""
    dd = datetime(2025, 1, 6, 8)
    fin = dd + timedelta(days=60)
    for rem in (20, 4):
        x0 = _bdi_act("X", od=20, tf=0.0, ef=fin)
        x1 = _bdi_act("X", od=20, rem=rem, tf=0.0, ef=fin,
                      status=(ActivityStatus.IN_PROGRESS if rem < 20
                              else ActivityStatus.NOT_STARTED))
        n1 = _bdi_act("N", od=10, tf=0.0, ef=fin)   # added PREDECESSOR of X
        t = _bdi_act("T", od=0, rem=0, tf=0.0, ef=fin,
                     atype=ActivityType.FINISH_MILESTONE)
        s0 = _bdi_sched(dd, [x0, t], [Relationship("X", "T")])
        s1 = _bdi_sched(dd + timedelta(days=30), [n1, x1, t],
                        [Relationship("N", "X"), Relationship("X", "T")])
        sa = SeriesAnalysis(schedules=[s0, s1])
        bdi = baseline_dilution_index(sa)
        assert {st.code for st in bdi.steps} == {"N", "X", "T"}
        # X keeps its baseline edge X->T (baseline-original); N is added:
        # BDI = 10 / (10 + 20) regardless of X's remaining duration
        assert bdi.bdi_pct == pytest.approx(100.0 * 10 / 30), f"rem={rem}"


def test_bdi_loe_step_contributes_zero_length():
    dd = datetime(2025, 1, 6, 8)
    fin = dd + timedelta(days=60)
    l = _bdi_act("L", od=40, tf=0.0, ef=fin, atype=ActivityType.LOE)
    x = _bdi_act("X", od=10, tf=0.0, ef=fin)
    t = _bdi_act("T", od=0, rem=0, tf=0.0, ef=fin,
                 atype=ActivityType.FINISH_MILESTONE)
    rels = [Relationship("L", "X"), Relationship("X", "T")]
    s0 = _bdi_sched(dd, [l, x, t], rels)
    s1 = _bdi_sched(dd + timedelta(days=30), [l, x, t], rels)
    bdi = baseline_dilution_index(SeriesAnalysis(schedules=[s0, s1]))
    lstep = next((st for st in bdi.steps if st.code == "L"), None)
    if lstep is None:
        pytest.skip("LOE not on the walked path in this run")
    assert lstep.length_days == 0.0
    assert bdi.bdi_pct == pytest.approx(0.0)          # all length is baseline X


def test_bdi_explicit_baseline_and_target_params_disclosed():
    dd = datetime(2025, 1, 6, 8)
    fin = dd + timedelta(days=60)
    mk = lambda d, acts, rels: _bdi_sched(d, acts, rels)
    x = _bdi_act("X", od=10, tf=0.0, ef=fin)
    n = _bdi_act("N", od=10, tf=0.0, ef=fin)
    t = _bdi_act("T", od=0, rem=0, tf=0.0, ef=fin,
                 atype=ActivityType.FINISH_MILESTONE)
    s0 = mk(dd, [x, t], [Relationship("X", "T")])
    s1 = mk(dd + timedelta(days=30), [x, n, t],
            [Relationship("X", "T"), Relationship("N", "T")])
    s2 = mk(dd + timedelta(days=60), [x, n, t],
            [Relationship("X", "T"), Relationship("N", "T")])
    sa = SeriesAnalysis(schedules=[s0, s1, s2])
    # explicit baseline = s1 (N already present there -> fully baseline-original)
    bdi = baseline_dilution_index(sa, baseline_index=1, target_code="T")
    assert bdi.bdi_pct == pytest.approx(0.0)
    assert any("baseline_index 1" in d for d in bdi.disclosures)
    assert any("analyst-selected" in d for d in bdi.disclosures)
    assert bdi.target_code == "T"
    # default baseline = s0 -> N is post-baseline
    bdi0 = baseline_dilution_index(sa)
    assert bdi0.bdi_pct is not None and bdi0.bdi_pct > 0.0
    # out-of-range baseline_index degrades with a reason, never raises
    bad = baseline_dilution_index(sa, baseline_index=2)
    assert bad.bdi_pct is None and bad.reason


def test_bdi5_logic_change_detail_format_coupling_lock():
    """BDI's first-appearance attribution parses lc.detail.split()[0] as the
    relationship type — lock the diff's detail format so a silent format
    change cannot break the attribution unnoticed."""
    dd = datetime(2025, 1, 6, 8)
    fin = dd + timedelta(days=60)
    a, b = _bdi_act("A", ef=fin), _bdi_act("B", ef=fin)
    s0 = _bdi_sched(dd, [a, b], [])
    s1 = _bdi_sched(dd + timedelta(days=30), [a, b], [Relationship("A", "B")])
    from scheduleiq.compare.diff import compare
    cs = compare(s0, s1)
    added = [lc for lc in cs.logic_changes if lc.kind == "added"]
    assert added and added[0].detail.split()[0] == "FS"


# ==========================================================================
# Wave 4b — MML basis segregation + sustained clean mile + event overlay
# (docs/rulings/LI-10-mml-v2-2026-07-12.md)
# ==========================================================================
from scheduleiq.ingest.model import ResourceAssignment, WbsNode         # noqa: E402


def _mml_sched(dd, acts, wbs):
    s = Schedule(project_id="MML", data_date=dd)
    s.activities = {a.uid: a for a in acts}
    s.wbs = {n.uid: n for n in wbs}
    return s


def _mml_wbs():
    return [WbsNode(uid="R", parent_uid=None, code="ROOT", name="root"),
            WbsNode(uid="W1", parent_uid="R", code="CIV", name="civil")]


def _mml_act(uid, *, od=10, done=False, af=None, au=0.0):
    a = Activity(uid=uid, code=uid, name=uid,
                 status=(ActivityStatus.COMPLETED if done
                         else ActivityStatus.NOT_STARTED),
                 total_float_hours=40.0, original_duration_hours=od * 8.0,
                 remaining_duration_hours=0.0 if done else od * 8.0,
                 actual_finish=af, wbs_uid="W1")
    if au:
        a.resources = [ResourceAssignment(activity_uid=uid, resource_uid="r1",
                                          actual_units=au)]
    return a


def test_mml_partial_resource_data_never_crosses_bases():
    """Q-F basis segregation: the audit's MML-1 probe — resource movement in
    window 1 only, a completion in window 2 — must NOT produce a
    resource-vs-activity-day 'contrast'.  The trade drops to a uniform
    activity-day basis for every window."""
    d0, d1, d2 = (datetime(2025, 1, 6, 8), datetime(2025, 2, 3, 8),
                  datetime(2025, 3, 3, 8))
    wbs = _mml_wbs()
    a0 = _mml_act("A", au=0.0)
    a1 = _mml_act("A", au=200.0)
    a2 = _mml_act("A", au=200.0)
    b0, b1 = _mml_act("B"), _mml_act("B")
    b2 = _mml_act("B", done=True, af=d2 - timedelta(days=3))
    sa = SeriesAnalysis(schedules=[
        _mml_sched(d0, [a0, b0], wbs), _mml_sched(d1, [a1, b1], wbs),
        _mml_sched(d2, [a2, b2], wbs)])
    mml = measured_mile_locator(sa)
    wr = mml.wbs_results[0]
    assert all(w.basis == "activity-day fallback" for w in wr.windows)
    assert wr.clean_window.basis == wr.impacted_window.basis
    assert any("never" in d and "compared" in d for d in mml.disclosures)


def test_mml_full_resource_trade_uses_resource_basis():
    d0, d1, d2 = (datetime(2025, 1, 6, 8), datetime(2025, 2, 3, 8),
                  datetime(2025, 3, 3, 8))
    wbs = _mml_wbs()
    sa = SeriesAnalysis(schedules=[
        _mml_sched(d0, [_mml_act("A", au=0.0)], wbs),
        _mml_sched(d1, [_mml_act("A", au=100.0)], wbs),
        _mml_sched(d2, [_mml_act("A", au=260.0)], wbs)])
    mml = measured_mile_locator(sa)
    wr = mml.wbs_results[0]
    assert all(w.basis == "resource" for w in wr.windows)
    assert wr.ratio is not None and 0.0 <= wr.ratio <= 1.0


def test_mml_spike_window_cannot_become_the_clean_mile():
    """Q-F sustained clean mile: productivities ~[1.0, 1.05, 5.0, 0.5] — the
    best qualifying 2-run is (1.0, 1.05), mean 1.025; the 5.0 spike fails
    every dispersion-capped run and must not set the clean basis."""
    dds = [datetime(2025, 1, 6, 8) + timedelta(days=14 * i) for i in range(5)]
    wbs = _mml_wbs()
    # per-window completions (planned days): 10, 10.5, 50, 5 over 10-wd windows
    specs = [("C1", 10, 1), ("C2", 10.5, 2), ("C3", 50, 3), ("C4", 5, 4)]
    def sched(k):
        acts = []
        for uid, od, win in specs:
            done = k >= win         # completed from schedule index win onward
            acts.append(_mml_act(uid, od=od, done=done,
                                 af=(dds[win] - timedelta(days=2) if done else None)))
        return _mml_sched(dds[k], acts, wbs)
    sa = SeriesAnalysis(schedules=[sched(k) for k in range(5)])
    mml = measured_mile_locator(sa)
    wr = mml.wbs_results[0]
    prods = [round(w.productivity, 3) for w in wr.windows]
    assert prods == [1.0, 1.05, 5.0, 0.5]
    assert wr.clean_productivity == pytest.approx(1.025)     # sustained run mean
    assert wr.clean_window.productivity == pytest.approx(1.05)
    assert wr.impacted_window.productivity == pytest.approx(0.5)
    assert wr.ratio == pytest.approx(0.5 / 1.025)
    assert not wr.no_clean_mile


def test_mml_event_overlay_excludes_windows_and_flows_from_series():
    """Q-F event wiring: delay events attached to the series (sa.delay_events)
    reach MML through the wiring; an evented window leaves clean-mile
    candidacy (here the spike window), and the overlay status is disclosed."""
    from scheduleiq.analytics.li_wiring import li_series_results
    from scheduleiq.metrics.engine import load_matrix
    dds = [datetime(2025, 1, 6, 8) + timedelta(days=14 * i) for i in range(5)]
    wbs = _mml_wbs()
    specs = [("C1", 10, 1), ("C2", 10.5, 2), ("C3", 50, 3), ("C4", 5, 4)]
    def sched(k):
        acts = [_mml_act(uid, od=od, done=k >= win,
                         af=(dds[win] - timedelta(days=2) if k >= win else None))
                for uid, od, win in specs]
        return _mml_sched(dds[k], acts, wbs)
    sa = SeriesAnalysis(schedules=[sched(k) for k in range(5)])
    events = [(dds[2] + timedelta(days=1), dds[3] - timedelta(days=1), "storm")]
    mml = measured_mile_locator(sa, events=events)
    wr = mml.wbs_results[0]
    assert wr.windows[2].excluded_by_event                    # the spike window
    assert wr.clean_productivity == pytest.approx(1.025)      # unchanged best run
    assert any("ACTIVE" in d for d in mml.disclosures)
    # and through the wiring via sa.delay_events
    sa.delay_events = events
    r = next(x for x in li_series_results(sa, load_matrix())
             if x.check.id == "LI-10")
    assert any("ACTIVE" in f.detail for f in r.findings)
