"""Tests for the Monte Carlo / SRA core (backlog M1 / M2 / M4) —
scheduleiq.analytics.montecarlo.

Fixtures (all built by tests/fixtures/make_fixtures.py; the demo_* .xer files
follow the engine-of-record pattern, so demo_cpm / demo_impact / demo_hs1 /
demo_hs2 handshake at 100% and demo_cpm_divergent lands below the 99% SET-02
threshold).  Known content used for the M4-gate assertions (verified against the
fixture generator):

  * demo_impact.xer — one lead (IA40->IA50, -16h), one hard constraint
    (MANDATORY_FINISH on IB20), and two open ends (IE10, IE20 — no successor):
    DIAGNOSTIC_ONLY.
  * demo_hs1.xer    — clean of leads/hard-constraints but HX10 is an open end:
    DIAGNOSTIC_ONLY (open_ends=1).
  * demo_hs2.xer    — no leads, no hard constraints, no open ends: READY.  Its
    deterministic controlling chain to MS-HS is
    HB20 -> HA50 -> HA60 -> HD10 -> HA70 -> MS-HS (each total-float 0), with
    MS-HS engine finish 2025-07-07.  All duration-sensitivity tests are designed
    against that chain.
  * demo_cpm_divergent.xer — engine cannot reproduce the record: REFUSED.
"""
import os
import subprocess
import sys
from datetime import datetime

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "src")
sys.path.insert(0, os.path.abspath(SRC))

from scheduleiq.ingest import load                                          # noqa: E402
from scheduleiq.ingest.model import (Activity, ActivityStatus, ActivityType,  # noqa: E402
                                     Calendar, Schedule)
from scheduleiq.cpm.handshake import HandshakeRefusal, clear_handshake_cache  # noqa: E402
from scheduleiq.analytics.montecarlo import (                               # noqa: E402
    SimulationResult, SraReadiness, UncertaintySpec, TemplateRule, ThreePointRow,
    ThreePointDist, RiskEvent, EmpiricalCalibration, run_simulation,
    sra_readiness, calibrate_from_series, load_three_point_csv,
    _latin_hypercube, _resolve_varying)
from scheduleiq.cpm.bridge import build_engine_inputs                        # noqa: E402
import random                                                                # noqa: E402
import statistics                                                            # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
IMPACT = os.path.join(FIX, "demo_impact.xer")
HS1 = os.path.join(FIX, "demo_hs1.xer")
HS2 = os.path.join(FIX, "demo_hs2.xer")
CPM = os.path.join(FIX, "demo_cpm.xer")
CPM_DIV = os.path.join(FIX, "demo_cpm_divergent.xer")
TP_CSV = os.path.join(FIX, "mc_threepoint_sample.csv")


@pytest.fixture(scope="session", autouse=True)
def fixtures():
    if not (os.path.exists(HS2) and os.path.exists(IMPACT)):
        subprocess.run([sys.executable, os.path.join(FIX, "make_fixtures.py")],
                       check=True)


@pytest.fixture(scope="session")
def hs2():
    return load(HS2)[0]


def _sim(sched, spec, **kw):
    kw.setdefault("iterations", 300)
    kw.setdefault("seed", 42)
    return run_simulation(sched, spec=spec, **kw)


# ======================================================================== M4 gate
def test_m4_gate_impact_diagnostic_only_with_all_three_screens():
    r = sra_readiness(load(IMPACT)[0])
    assert r.verdict == "DIAGNOSTIC_ONLY"
    assert r.leads == 1                        # IA40->IA50 lead (-16h)
    assert r.hard_constraints == 1             # MANDATORY_FINISH on IB20
    assert r.open_ends == 2 and r.open_end_codes == ["IE10", "IE20"]
    assert r.handshake_passed is True
    # every tripped screen is named in the branding line
    b = r.branding()
    assert b.startswith("DIAGNOSTIC ONLY — SRA-readiness screens failed:")
    assert "1 lead" in b and "1 hard constraint" in b and "2 open end" in b


def test_m4_gate_hs1_open_end_only():
    r = sra_readiness(load(HS1)[0])
    assert r.verdict == "DIAGNOSTIC_ONLY"
    assert r.leads == 0 and r.hard_constraints == 0
    assert r.open_ends == 1 and r.open_end_codes == ["HX10"]


def test_m4_gate_hs2_is_ready(hs2):
    r = sra_readiness(hs2)
    assert r.verdict == "READY"
    assert (r.leads, r.hard_constraints, r.open_ends) == (0, 0, 0)
    assert r.handshake_passed is True
    assert r.branding() is None


def test_m4_gate_divergent_refused():
    r = sra_readiness(load(CPM_DIV)[0])
    assert r.verdict == "REFUSED"
    assert r.handshake_passed is False


def test_refused_raises_and_skip_escape_hatch():
    div = load(CPM_DIV)[0]
    spec = UncertaintySpec(templates=[TemplateRule(match="", low_pct=-10, high_pct=10)])
    with pytest.raises(HandshakeRefusal):
        run_simulation(div, spec=spec, iterations=50, seed=1)
    # skip runs anyway (disclosed) — the divergent file's network is still valid
    r = run_simulation(div, spec=spec, iterations=50, seed=1, handshake="skip")
    assert r.iterations == 50
    assert any("skip" in d.lower() and "bypass" in d.lower() for d in r.disclosures)


def test_bad_handshake_mode_raises(hs2):
    with pytest.raises(ValueError):
        run_simulation(hs2, spec=UncertaintySpec(), iterations=10, seed=1,
                       handshake="maybe")


def test_seed_is_required(hs2):
    with pytest.raises(TypeError):
        run_simulation(hs2, spec=UncertaintySpec(), iterations=10)   # no seed


# ================================================================ determinism
def test_determinism_same_seed_identical(hs2):
    spec = UncertaintySpec(templates=[TemplateRule(match="", low_pct=-20, high_pct=20)])
    clear_handshake_cache()
    a = run_simulation(hs2, spec=spec, iterations=200, seed=42).to_dict()
    clear_handshake_cache()
    b = run_simulation(hs2, spec=spec, iterations=200, seed=42).to_dict()
    assert a == b


def test_different_seed_differs(hs2):
    spec = UncertaintySpec(templates=[TemplateRule(match="", low_pct=-20, high_pct=20)])
    a = run_simulation(hs2, spec=spec, iterations=200, seed=42)
    b = run_simulation(hs2, spec=spec, iterations=200, seed=43)
    assert a.target_offsets != b.target_offsets   # almost surely


# ============================================================ correctness anchors
def test_degenerate_spec_every_iteration_equals_deterministic(hs2):
    # zero-width distributions, no risks, rho=0 -> every EF == deterministic EF
    deg = UncertaintySpec(templates=[TemplateRule(match="", low_pct=0, high_pct=0,
                                                  mode_pct=0)])
    r = run_simulation(hs2, spec=deg, iterations=250, seed=5)
    assert set(r.target_offsets) == {r.deterministic_offset}
    assert r.percentiles["P50"]["offset"] == r.deterministic_offset
    assert r.merge_bias["merge_bias_workdays"] == 0.0


def test_one_sided_widening_of_controlling_activity(hs2):
    # HA50 (OD 12, on the controlling chain): pessimistic-only triangular in
    # [12, 24] -> can only grow -> P80 >= deterministic, HA50 tops the tornado,
    # and its criticality index is 100% (it stays on the path in every iteration).
    spec = UncertaintySpec(three_point=[ThreePointRow("HA50", 12, 12, 24, "triangular")])
    r = run_simulation(hs2, spec=spec, iterations=400, seed=7)
    assert r.percentiles["P80"]["offset"] >= r.deterministic_offset
    assert r.percentiles["P90"]["offset"] >= r.deterministic_offset
    assert r.tornado[0]["code"] == "HA50"
    assert r.tornado[0]["criticality_index_pct"] == 100.0
    # only HA50 varies -> it is the sole tornado bar
    assert len(r.tornado) == 1


def test_off_path_widening_leaves_target_unchanged(hs2):
    # HC10 sits on chain R with total float 35 wd; widening it by at most +6 wd
    # (< its float) never reaches MS-HS -> every percentile equals deterministic.
    spec = UncertaintySpec(three_point=[ThreePointRow("HC10", 6, 6, 12, "triangular")])
    r = run_simulation(hs2, spec=spec, iterations=400, seed=9)
    assert set(r.target_offsets) == {r.deterministic_offset}
    for key in ("P10", "P50", "P80", "P90"):
        assert r.percentiles[key]["offset"] == r.deterministic_offset


def test_risk_event_probability_one_shifts_p50_by_impact(hs2):
    # probability 1, fixed +3 wd impact on the controlling HA50 -> P50 shifts by
    # exactly +3; probability 0 -> no shift.
    base = run_simulation(hs2, spec=UncertaintySpec(), iterations=80, seed=3)
    fired = run_simulation(hs2, spec=UncertaintySpec(), iterations=80, seed=3,
                           risk_events=[RiskEvent("R1", 1.0, ThreePointDist(3, 3, 3),
                                                  "HA50")])
    never = run_simulation(hs2, spec=UncertaintySpec(), iterations=80, seed=3,
                           risk_events=[RiskEvent("R0", 0.0, ThreePointDist(3, 3, 3),
                                                  "HA50")])
    assert fired.percentiles["P50"]["offset"] - base.deterministic_offset == 3
    assert never.percentiles["P50"]["offset"] - base.deterministic_offset == 0


def test_correlation_widens_the_distribution(hs2):
    # identical symmetric bands on all activities: rho=1 (all move together)
    # widens the completion distribution vs rho=0 (independent) — merge-bias
    # mechanics.  Assert the variance ordering.
    spec = UncertaintySpec(templates=[TemplateRule(match="", dist="triangular",
                                                   low_pct=-30, high_pct=30)])
    c1 = run_simulation(hs2, spec=spec, iterations=400, seed=11, correlation=1.0)
    c0 = run_simulation(hs2, spec=spec, iterations=400, seed=11, correlation=0.0)
    assert statistics.pvariance(c1.target_offsets) > statistics.pvariance(c0.target_offsets)


# ====================================================== tiers / provenance / LHS
def test_tier_precedence_and_provenance(hs2):
    # HA50 carries BOTH a three-point row and a template match -> three_point wins;
    # HA60 matches only the template; empirical is the default for the rest.
    emp = EmpiricalCalibration(n=3, ratios=[0.9, 1.0, 1.1], mean=1.0, p10=0.9,
                               p50=1.0, p90=1.1, method="bootstrap")
    # template scoped to HA60 only, so the empirical default reaches the rest.
    spec = UncertaintySpec(
        templates=[TemplateRule(match="HA60", low_pct=-10, high_pct=10)],
        three_point=[ThreePointRow("HA50", 10, 12, 20)],
        empirical=emp)
    r = run_simulation(hs2, spec=spec, iterations=50, seed=1)
    tiers = {p["code"]: p["tier"] for p in r.input_provenance}
    assert tiers["HA50"] == "three_point"    # explicit row beats template + empirical
    assert tiers["HA60"] == "template"       # template beats empirical
    assert tiers["HA70"] == "empirical"      # empirical is the default for the rest
    # provenance records the parameters, not just the tier
    ha50 = next(p for p in r.input_provenance if p["code"] == "HA50")
    assert ha50["params"]["pessimistic_days"] == 20


def test_three_point_csv_loader():
    rows = load_three_point_csv(TP_CSV)
    by_code = {r.code: r for r in rows}
    assert set(by_code) == {"HA50", "HA60", "HB20", "HC10"}
    assert by_code["HA50"].optimistic_days == 10 and by_code["HA50"].pessimistic_days == 20
    assert by_code["HA60"].dist == "pert"
    assert by_code["HC10"].dist == "uniform"


def test_empirical_calibration_harvests_known_ratios():
    # in-memory series (pattern from test_asbuilt.py) with designed actual÷planned
    # ratios: planned OD 10 wd each; A finishes 15 wd (1.5), B 10 wd (1.0),
    # C 20 wd (2.0) -> sorted [1.0, 1.5, 2.0], median 1.5.
    def dt(y, m, d):
        return datetime(y, m, d, 8, 0)

    def act(uid, AS, AF):
        return Activity(uid=uid, code=uid, atype=ActivityType.TASK,
                        status=ActivityStatus.COMPLETED, calendar_uid="C",
                        original_duration_hours=80.0, actual_start=AS, actual_finish=AF)

    s = Schedule()
    s.data_date = dt(2025, 1, 6)
    s.calendars["C"] = Calendar(uid="C", name="5d", hours_per_day=8.0, is_default=True)
    s.activities["A"] = act("A", dt(2025, 1, 6), dt(2025, 1, 24))   # 15 wd
    s.activities["B"] = act("B", dt(2025, 1, 6), dt(2025, 1, 17))   # 10 wd
    s.activities["C"] = act("C", dt(2025, 1, 6), dt(2025, 1, 31))   # 20 wd
    emp = calibrate_from_series([s])
    assert emp.n == 3
    assert emp.ratios == [1.0, 1.5, 2.0]
    assert emp.p50 == 1.5
    assert emp.method == "bootstrap"       # n < 20
    assert any("no linked baseline" in d for d in emp.disclosures)


def test_lhs_stratification_covers_every_stratum():
    # 100 iterations, one uniform dimension -> exactly one sample in each of the
    # 100 equal strata [k/100, (k+1)/100).
    rng = random.Random(5)
    matrix = _latin_hypercube(100, 1, rng)
    vals = sorted(row[0] for row in matrix)
    buckets = [int(v * 100) for v in vals]
    assert buckets == list(range(100))       # every stratum hit exactly once
    assert all(0.0 <= v < 1.0 for v in vals)


# ============================================================ serialization / branding
def test_to_dict_shape_and_preliminary(hs2):
    spec = UncertaintySpec(templates=[TemplateRule(match="", low_pct=-20, high_pct=20)])
    d = run_simulation(hs2, spec=spec, iterations=100, seed=42).to_dict()
    assert set(d) >= {"iterations", "seed", "correlation", "target", "readiness",
                      "branding", "percentiles", "target_sample", "criticality_index",
                      "cruciality", "tornado", "merge_bias", "input_provenance",
                      "risk_events", "disclosures", "preliminary", "presentation_rule"}
    assert "PRELIMINARY" in d["preliminary"]
    assert "reserved to the expert" in d["preliminary"]
    assert set(d["percentiles"]) >= {"P10", "P50", "P80", "P90"}


def test_branding_stamped_when_diagnostic_only_and_absent_when_ready(hs2):
    spec = UncertaintySpec(templates=[TemplateRule(match="", low_pct=-10, high_pct=10)])
    # demo_impact is DIAGNOSTIC_ONLY -> branding stamped on the result dict
    diag = run_simulation(load(IMPACT)[0], spec=spec, iterations=60, seed=1)
    assert diag.branding is not None
    assert diag.to_dict()["branding"].startswith("DIAGNOSTIC ONLY")
    assert any("DIAGNOSTIC ONLY" in x for x in diag.disclosures)
    # demo_hs2 is READY -> no branding
    ready = run_simulation(hs2, spec=spec, iterations=60, seed=1)
    assert ready.branding is None
    assert ready.to_dict()["branding"] is None


def test_iteration_cap_is_disclosed(hs2):
    r = run_simulation(hs2, spec=UncertaintySpec(), iterations=6000, seed=1)
    assert r.iterations == 5000
    assert any("capped at 5000" in d for d in r.disclosures)
