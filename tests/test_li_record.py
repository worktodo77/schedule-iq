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


def test_kaplan_meier_all_censored_has_no_median():
    km = kaplan_meier([(1.0, True), (2.0, True), (3.0, True)])
    assert km.n == 3
    assert km.censored == 3
    assert km.median is None


def test_kaplan_meier_median_not_reached_falls_back_to_last_event():
    # 1 death among 20 far-outlived censored items: S never drops to <=0.5,
    # so the fallback reports the (only) event time as a lower bound.
    lifespans = [(0.0, False)] + [(5.0, True)] * 19
    km = kaplan_meier(lifespans)
    assert km.median == 0.0
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
    update2.  The series therefore carries exactly one observed relationship
    death; with 27 of 28 instances censored the KM curve never crosses 0.5,
    so the median is the flagged conservative lower bound
    (median_reached=False).  KM arithmetic itself is proven by the synthetic
    known-answer tests above.
    """
    lhl = logic_half_life(series)
    assert lhl.overall is not None, lhl.reason
    assert lhl.overall.n >= 1
    assert 0 <= lhl.overall.censored <= lhl.overall.n
    assert lhl.overall.censored == lhl.overall.n - 1  # exactly one death: A1050->A1070 deleted in update2
    assert lhl.overall.median_updates is not None     # conservative lower bound reported
    assert lhl.overall.median_reached is False        # 27/28 censored: curve never crosses 0.5


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


# -- v0.4.5 LHL audit fixes (L1-L4, L6) --------------------------------------
from datetime import datetime as _dt                                    # noqa: E402
from scheduleiq.ingest.model import (Activity as _Act, Relationship as _Rel,  # noqa: E402
    Calendar as _Cal, ActivityType as _AT, ActivityStatus as _ST, RelType as _RT)

_LCAL = _Cal(uid="1", name="5d", hours_per_day=8.0, is_default=True)


def _lact(uid, code):
    return _Act(uid=uid, code=code, name=code, atype=_AT.TASK, status=_ST.NOT_STARTED,
                calendar_uid="1", original_duration_hours=80.0,
                remaining_duration_hours=80.0, total_float_hours=0.0,
                early_start=_dt(2025, 1, 1), early_finish=_dt(2025, 3, 1),
                planned_start=_dt(2025, 1, 1), planned_finish=_dt(2025, 3, 1))


def _lsched(acts, rels, dd):
    s = Schedule(project_id="P", data_date=dd)
    s.calendars = {"1": _LCAL}
    for uid, code in acts:
        s.activities[uid] = _lact(uid, code)
    s.relationships = [_Rel(pred_uid=p, succ_uid=q, rtype=t, lag_hours=0.0)
                       for p, q, t in rels]
    return s


def test_li02_not_reached_scores_on_died_fraction(monkeypatch):
    """L1: when the KM median is not reached, full marks require FEW ties to
    have DIED (too stable to estimate a half-life).  The prior code tested the
    CENSORED fraction, inverting the branch so stable networks scored 70."""
    from types import SimpleNamespace
    from scheduleiq import scorecard as scm
    override = {"points": [[1, 0], [6, 70], [12, 100]],
                "died_pass_threshold": 0.10, "not_reached_partial_score": 70.0}

    def fake(censored, n):
        ov = lr.LHLVariant(median_updates=3.0, median_months=3.0,
                           median_reached=False, n=n, censored=censored)
        monkeypatch.setattr(lr, "run_li_record",
                            lambda sa: SimpleNamespace(lhl=lr.LHLResult(overall=ov)))
    fake(27, 28)      # 1/28 died = 3.6% < 10%  -> stable -> 100
    assert scm._li02_score(None, override)[1] == 100.0
    fake(20, 28)      # 8/28 died = 28.6% >= 10% -> churned -> 70
    assert scm._li02_score(None, override)[1] == 70.0


def test_lhl_death_recorded_at_first_absent_update():
    """L2: a tie present in one update then deleted has lifespan 1 (death dated
    to the first-absent update), not 0."""
    u0 = _lsched([("a", "A"), ("b", "B"), ("c", "C"), ("d", "D")],
                 [("a", "b", _RT.FS), ("c", "d", _RT.FS)], _dt(2025, 1, 1))
    u1 = _lsched([("a", "A"), ("b", "B"), ("c", "C"), ("d", "D")],
                 [], _dt(2025, 2, 1))                 # every tie deleted at update 1
    lhl = logic_half_life(SeriesAnalysis(schedules=[u0, u1]), exclude_first_pair=False)
    assert lhl.overall.median_updates == pytest.approx(1.0)   # not 0.0 (the bug)
    assert lhl.overall.median_reached is True


def test_lhl_recode_is_not_a_death_but_type_change_is():
    """L3: identity is keyed by UID — re-coding an activity is not a logic death;
    a relationship-type change is."""
    r0 = _lsched([("a", "A"), ("b", "B")], [("a", "b", _RT.FS)], _dt(2025, 1, 1))
    r1 = _lsched([("a", "A-RENAMED"), ("b", "B")], [("a", "b", _RT.FS)], _dt(2025, 2, 1))
    insts = lr._build_instances([r0, r1])
    assert len(insts) == 1 and insts[0].censored is True      # survived the re-code

    t0 = _lsched([("a", "A"), ("b", "B")], [("a", "b", _RT.FS)], _dt(2025, 1, 1))
    t1 = _lsched([("a", "A"), ("b", "B")], [("a", "b", _RT.SS)], _dt(2025, 2, 1))
    tinsts = lr._build_instances([t0, t1])
    assert any(not i.censored for i in tinsts)                # the FS tie died


def test_lhl_on_off_ratio_suppressed_when_median_not_reached(series):
    """L4: the on/off ratio is published only when BOTH cohort medians are
    genuinely reached; otherwise it is suppressed and a disclosure carried."""
    lhl = logic_half_life(series)
    if lhl.on_path and lhl.off_path and not (
            lhl.on_path.median_reached and lhl.off_path.median_reached):
        assert lhl.on_off_ratio is None
        assert lhl.on_off_ratio_reached is False
        assert any("suppressed" in d for d in lhl.disclosures)
    # invariant: a published ratio implies both medians were reached
    assert (lhl.on_off_ratio is None) or lhl.on_off_ratio_reached


def test_lhl_carries_standing_disclosures(series):
    """L6: LHL outputs carry standing methodology disclosures."""
    lhl = logic_half_life(series)
    assert lhl.disclosures
    assert any("UID" in d for d in lhl.disclosures)            # identity basis
    assert any("mean" in d.lower() for d in lhl.disclosures)   # months conversion
    assert any("LOE" in d for d in lhl.disclosures)            # LOE inclusion (pending L5)


# ==========================================================================
# N8 — FRB
# ==========================================================================
def test_frb_has_at_least_one_populated_bucket(series):
    frb = forecast_reliability_band(series)
    assert any(b.n >= 1 for b in frb.buckets)
    assert len(frb.buckets) == 4
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
    assert (il.median_il_updates is not None) == bool(resolved)
    assert il.unresolved_count == sum(1 for e in il.events if e.unresolved)
    assert il.unresolved_count + len(resolved) == len(il.events)
    for e in il.events:
        assert e.chain_codes
        if not e.unresolved:
            assert e.il_updates is not None and e.il_updates >= 1
            assert e.response_detail


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
