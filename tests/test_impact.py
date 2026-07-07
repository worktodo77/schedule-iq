"""Tests for the issue-impact overlay (A2), the OOS statusing delta (A4), and
constraint-free criticality (P5) — scheduleiq.analytics.impact.

demo_impact.xer is an engine-consistent fixture (its stored tool-of-record dates
are produced by the ported engine, so it handshakes at 100%).  Its network is
engineered so every impact scenario has a NONZERO, mechanism-explained delta;
the mechanism map for each asserted number is in the fixture generator's header
comment (tests/fixtures/make_fixtures.py) and restated inline below.

Every expected value here was extracted from a manual engine run on the fixture
and sanity-checked for plausibility (see the per-assertion comments).
"""
import os
import subprocess
import sys

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "src")
sys.path.insert(0, SRC)

from scheduleiq.ingest import load                                       # noqa: E402
from scheduleiq.analytics.impact import (ImpactAnalysis, run_impact_analysis)  # noqa: E402
from scheduleiq.cpm.handshake import HandshakeRefusal, clear_handshake_cache   # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
IMPACT = os.path.join(FIX, "demo_impact.xer")
CPM_DIV = os.path.join(FIX, "demo_cpm_divergent.xer")
BASELINE = os.path.join(FIX, "demo_baseline.xer")


@pytest.fixture(scope="session", autouse=True)
def fixtures():
    if not os.path.exists(IMPACT):
        subprocess.run([sys.executable, os.path.join(FIX, "make_fixtures.py")],
                       check=True)


@pytest.fixture(scope="session")
def sched():
    return load(IMPACT)[0]


@pytest.fixture(scope="session")
def ia(sched):
    return run_impact_analysis(sched)


# ------------------------------------------------------------ target resolution
def test_target_auto_resolves_to_finish_milestone(ia):
    # MS-IMP is the sole finish milestone and the latest-finishing activity.
    assert ia.target_code == "MS-IMP"
    assert ia.target_uid == "3200"
    assert "finish milestone" in ia.resolved_how


def test_target_explicit_by_code_and_uid(sched):
    by_code = run_impact_analysis(sched, target="MS-IMP")
    by_uid = run_impact_analysis(sched, target="3200")
    assert by_code.target_uid == "3200" and "by code" in by_code.resolved_how
    assert by_uid.target_code == "MS-IMP" and "by uid" in by_uid.resolved_how


# ---------------------------------------------------------------- handshake gate
def test_handshake_require_passes_on_clean_fixture(ia):
    assert ia.handshake["match_rate_pct"] == 100.0
    assert ia.handshake["passed"] is True
    assert ia.handshake["constraint_applications"] == 4      # MF + SNET + XF + SNLT


def test_handshake_refusal_propagates_on_divergent():
    with pytest.raises(HandshakeRefusal):
        run_impact_analysis(load(CPM_DIV)[0])


def test_handshake_skip_runs_with_disclosure(sched):
    ia = run_impact_analysis(sched, handshake="skip")
    assert any("skip" in d.lower() and "bypass" in d.lower() for d in ia.disclosures)
    # skip still computes the same deltas on a valid file
    assert ia.delta("constraints_released_all").delta_workdays == 39


def test_bad_handshake_mode_raises(sched):
    with pytest.raises(ValueError):
        run_impact_analysis(sched, handshake="maybe")


# --------------------------------------------------------------- baseline record
def test_baseline_carries_both_engine_and_record_dates(ia):
    # presentation rule: engine dates are diagnostic; record dates are the schedule
    assert ia.baseline_engine_ef.isoformat() == "2025-05-28"
    assert ia.baseline_engine_tf_workdays == 23
    assert ia.baseline_record_ef is not None
    assert ia.baseline_record_ef.date().isoformat() == "2025-05-28"


# ------------------------------------------------- scenario 1: constraints_released
def test_constraints_released_all_moves_target_later(ia):
    # The MANDATORY FINISH on IB20 pins chain B far below its true logic length;
    # releasing all constraints lets chain B spring back PAST chain A, so MS-IMP
    # moves +39 workdays later (2025-05-28 -> 2025-07-22).
    d = ia.delta("constraints_released_all")
    assert d.computable is True
    assert d.delta_workdays == 39
    assert d.target_finish_engine.isoformat() == "2025-07-22"


def test_float_absorbed_lists_the_snet_activity(ia):
    # The SNET holds IC15 beyond its logic date; releasing constraints returns its
    # total float 30 -> 56 workdays, i.e. 26 workdays were absorbed by the SNET.
    absorbed = {r["code"]: r for r in
                ia.delta("constraints_released_all").details["float_absorbed_workdays"]}
    assert "IC15" in absorbed
    assert absorbed["IC15"]["float_absorbed_workdays"] == 26
    assert absorbed["IC15"]["tf_constrained_workdays"] == 30
    assert absorbed["IC15"]["tf_unconstrained_workdays"] == 56


# --------------------------------------------- scenario: per-constraint attribution
def test_constraint_attribution_isolates_the_mandatory_finish(ia):
    table = {d.scenario: d.delta_workdays for d in ia.constraint_attribution}
    # only the mandatory finish moves the target; the others are ~0 -> deltas differ
    assert table["constraint_released:IB20/mandatory_finish"] == 39
    assert table["constraint_released:IC15/start_on_or_after"] == 0
    assert table["constraint_released:IC20/expected_finish"] == 0
    assert table["constraint_released:ID10/start_on_or_before"] == 0
    assert len(set(table.values())) >= 2                     # per-constraint deltas differ


# --------------------------------------------------------- scenario: leads_zeroed
def test_leads_zeroed_delta_and_lead_hours(ia):
    # The -16h lead on IA40->IA50 (chain A, controlling) compresses the path by
    # 2 workdays; zeroing it pushes MS-IMP +2 workdays later.
    d = ia.delta("leads_zeroed")
    assert d.delta_workdays == 2
    assert d.details["lead_hours_on_controlling_path"] == 16.0


# ------------------------------------------------------- scenario: lags_visibility
def test_lags_visibility_reports_path_lag_no_rerun(ia):
    # The +80h lag on IA50->IA60 is invisible scope on the controlling path;
    # path working duration is 408h (5+8+10+8+8+10 wd across two calendars).
    d = ia.delta("lags_visibility")
    assert d.delta_workdays is None                          # no engine rerun
    assert d.details["positive_lag_hours_on_controlling_path"] == 80.0
    assert d.details["path_working_hours"] == 408.0
    assert d.details["lag_share_pct_of_path"] == pytest.approx(19.61, abs=0.05)


# ------------------------------------------------------ scenario: OOS delta (A4)
def test_oos_override_delta_and_dropped_relationships(ia):
    # IA40 (steel) started 2025-04-02 before its in-progress predecessor IA30
    # (foundations) finished — genuine OOS.  Progress override drops the retained
    # tie, so chain A (controlling) proceeds at the data date and MS-IMP moves
    # -7 workdays earlier.  Three ties are dropped in total.
    d = ia.delta("oos_statusing_delta")
    assert d.delta_workdays == -7
    assert d.details["baseline_statusing_mode"] == "retained_logic"
    assert d.details["override_dropped_relationships"] == 3
    assert ["IA30", "IA40"] in d.details["dropped_pairs"]    # the genuine OOS pair


# --------------------------------------------- scenario: expected_finish_released
def test_expected_finish_released(ia):
    d = ia.delta("expected_finish_released")
    assert d.details["expected_finish_count"] == 1
    assert d.delta_workdays == 0                             # XF is off the controlling path


# ------------------------------------------------ P5: constraint-free criticality
def test_p5_manufactured_and_masked_criticality(ia):
    blk = ia.constraint_free_criticality
    # ID10's SNLT is unmeetable -> negative float WITH the constraint only.
    assert "ID10" in blk["manufactured_critical"]
    # the mandatory finish masks MS-IMP's own criticality (float 23 -> 0).
    assert "MS-IMP" in blk["masked_critical"]
    assert blk["target_total_float_workdays"] == {"with_constraints": 23, "without": 0}
    codes = {r["code"] for r in blk["flip_table"]}
    assert {"ID10", "MS-IMP"} <= codes


# --------------------------------------------- calendar-neutral restatement
def test_calendar_restatement_flags_the_7day_activity(ia):
    blk = ia.calendar_restatement
    codes = {r["code"] for r in blk["diverging_activities"]}
    assert "IA50" in codes                                   # the 7-day / 10h activity
    ia50 = next(r for r in blk["diverging_activities"] if r["code"] == "IA50")
    assert ia50["own_hours_per_day"] == 10.0
    assert ia50["divergence_days"] == pytest.approx(8.25, abs=0.01)


# ----------------------------------------------------------------- open ends
def test_open_ends_are_exactly_the_designed_set(ia):
    codes = {a["code"] for a in ia.open_ends["activities"]}
    assert codes == {"IE10", "IE20"}                         # no forward path to MS-IMP
    assert ia.open_ends["count"] == 2


# --------------------------------------------- per-scenario degradation (invalid net)
def test_scenarios_degrade_not_raise_on_invalid_network():
    # demo_baseline.xer fails engine validation (circular logic); with skip the
    # module must record every scenario as not-computable rather than raising.
    ia = run_impact_analysis(load(BASELINE)[0], handshake="skip")
    assert ia.baseline_computable is False
    assert ia.deltas                                         # scenarios still listed
    assert all(d.computable is False for d in ia.deltas)
    assert all(d.blocking for d in ia.deltas)


# -------------------------------------------------------------------- determinism
def test_deterministic_to_dict(sched):
    clear_handshake_cache()
    a = run_impact_analysis(sched).to_dict()
    clear_handshake_cache()
    b = run_impact_analysis(sched).to_dict()
    assert a == b


# ----------------------------------------------------------------- serialization
def test_to_dict_shape_and_deferred_note(ia):
    d = ia.to_dict()
    assert set(d) >= {"target", "baseline", "handshake", "waterfall",
                      "constraint_attribution", "constraint_free_criticality",
                      "calendar_restatement", "open_ends", "disclosures",
                      "deferred", "presentation_rule"}
    assert any("D9" in note for note in d["deferred"])       # half-step deferral
    assert isinstance(ia, ImpactAnalysis)
