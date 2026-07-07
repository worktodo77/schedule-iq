"""Tests for the five provocative LI indices (backlog N16-N20;
ANALYTICS_PROPOSAL §11): SMI, DDI, ARR, PPS, RSA.

The published-weight arithmetic of each index is pinned on hand-built inputs via
the exported pure helpers (``_compute_smi``, ``_ddi_arithmetic``, ``_score_pps``,
``_classify_rsa_windows``, and hand-built certificate dicts for ARR/RSA), the
same convention ``test_robustness`` uses for ``compute_stability_stats``.  The
seeded three-update demo series (make_fixtures.py — TRD-05/LOG-10/SET-01/CAL-04/
DUR-04 already tripped) anchors the SMI decomposition and the guardrail text;
demo_hs1/demo_hs2 + a responsibility map anchor the ARR/RSA certificate path.
"""
import os
import subprocess
import sys
from datetime import datetime
from types import SimpleNamespace

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "src")
sys.path.insert(0, os.path.abspath(SRC))

from scheduleiq.ingest import load, load_many                              # noqa: E402
from scheduleiq.trend.series import analyze_series, SeriesAnalysis         # noqa: E402
from scheduleiq.ingest.model import Schedule                              # noqa: E402
from scheduleiq.metrics.engine import load_matrix, evaluate               # noqa: E402
from scheduleiq.scorecard import score_series                            # noqa: E402
from scheduleiq.analytics import li_provocative as lp                    # noqa: E402
from scheduleiq.analytics.li_provocative import (                        # noqa: E402
    schedule_manipulation_indicator, directed_date_index,
    attribution_robustness_ratio, pacing_plausibility, rebuttal_surface_area,
    run_li_provocative, _compute_smi, _ddi_arithmetic, _held_run, _score_pps,
    _pps_from_candidate, _classify_rsa_windows, _zscores,
    SMI_SIGNAL_WEIGHTS, PPS_CRITERIA_WEIGHTS, PPS_NEUTRAL, SENTENCE_CAP,
    NOT_COMPUTABLE)
from scheduleiq.analytics.li_wiring import li_provocative_results          # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
BASELINE = os.path.join(FIX, "demo_baseline.xer")
U1 = os.path.join(FIX, "demo_update1.xer")
U2 = os.path.join(FIX, "demo_update2.xer")
HS1 = os.path.join(FIX, "demo_hs1.xer")
HS2 = os.path.join(FIX, "demo_hs2.xer")

# HA* construction chain -> Contractor; procurement/equipment + owner change -> Owner
RM = {c: "Contractor" for c in
      ("HMS-START", "HA10", "HA20", "HA30", "HA40", "HA50", "HA60", "HA70",
       "HX10", "MS-HS")}
RM.update({"HB10": "Owner", "HB15": "Owner", "HB20": "Owner",
           "HC10": "Owner", "HC20": "Owner", "HD10": "Owner"})


@pytest.fixture(scope="session", autouse=True)
def fixtures():
    if not (os.path.exists(BASELINE) and os.path.exists(HS1)):
        subprocess.run([sys.executable, os.path.join(FIX, "make_fixtures.py")],
                       check=True)


@pytest.fixture(scope="session")
def series():
    return analyze_series(load_many([BASELINE, U1, U2]))


# ==========================================================================
# SMI — Schedule Manipulation Indicator (§11.1, N16)
# ==========================================================================
def test_smi_composite_closed_form():
    """Published weights: TRD-05 3, SET-01 3, LOG-10 2, DUR 2, CAL-04 1, STAT 1
    (Σ 12).  Signal = 0.30·presence + 0.50·severity + 0.20·timing, severity =
    100·min(1, count/5); timing dropped & renormalized (÷0.80) when no claim
    dates.  count 5 (saturated), no timing -> signal (30+50)/0.8 = 100."""
    assert sum(SMI_SIGNAL_WEIGHTS.values()) == 12.0
    # only TRD-05 saturated, no claim dates: SMI = 3*100/12 = 25
    r = _compute_smi({"TRD-05": 5}, {}, {}, claim_dates_available=False)
    assert r.smi == pytest.approx(25.0)
    # every signal saturated -> 100
    r2 = _compute_smi({k: 5 for k in SMI_SIGNAL_WEIGHTS}, {}, {}, False)
    assert r2.smi == pytest.approx(100.0)
    # a single TRD-05 finding: severity 20, signal (30 + 10)/0.8 = 50 -> 3*50/12
    r3 = _compute_smi({"TRD-05": 1}, {}, {}, False)
    assert r3.smi == pytest.approx(12.5)


def test_smi_timing_lowers_when_no_pre_claim_concentration():
    # with claim dates available, a signal whose edits do NOT precede a claim
    # scores timing 0: TRD-05 signal = 0.30*100 + 0.50*100 + 0.20*0 = 80
    r = _compute_smi({"TRD-05": 5}, {"TRD-05": False}, {}, claim_dates_available=True)
    assert r.smi == pytest.approx(20.0)               # 3*80/12
    assert r.timing_available is True
    # and 100 when it does precede a claim
    r2 = _compute_smi({"TRD-05": 5}, {"TRD-05": True}, {}, claim_dates_available=True)
    assert r2.smi == pytest.approx(25.0)              # 3*100/12


def test_smi_demo_series_decomposition_names_seeded_findings(series):
    smi = schedule_manipulation_indicator(series)
    assert smi.reason == ""
    by = {s.key: s for s in smi.signals}
    # the demo series trips all five seeded curation families
    assert by["TRD-05"].count >= 1 and by["TRD-05"].findings
    assert by["SET-01"].count >= 1 and by["SET-01"].findings
    assert by["LOG-10"].count >= 1 and by["LOG-10"].findings
    assert by["CAL-04"].count >= 1 and by["CAL-04"].findings
    assert by["DUR"].count >= 1 and by["DUR"].findings
    # the named seeded observations are cited in the decomposition
    blob = " ".join(f for s in smi.signals for f in s.findings)
    assert "A1010" in blob                             # retroactive actual change (TRD-05)
    assert "A1215" in blob                             # hollow-logic stub (LOG-10)
    assert "retained_logic" in blob                    # settings flip (SET-01)
    assert "A1070" in blob                             # DUR-04 compression
    # exact SMI from the published weighting: TRD 3*100 + SET 3*50 + LOG 2*50 +
    # DUR 2*50 + CAL 1*50 + STAT 1*75 = 775, /12
    assert smi.smi == pytest.approx(775.0 / 12.0)
    # self-consistent with the published formula
    num = sum(s.weight * s.score for s in smi.signals)
    den = sum(s.weight for s in smi.signals)
    assert smi.smi == pytest.approx(num / den)


def test_smi_guardrails_present_and_capped(series):
    smi = schedule_manipulation_indicator(series)
    d = smi.to_dict()
    text = repr(d).lower()
    # standing sentence cap present; innocent explanations per contributing signal
    assert SENTENCE_CAP in text
    for s in smi.signals:
        assert s.innocent_explanation
        assert ("verify" in s.innocent_explanation
                or "inquiry" in s.innocent_explanation)   # points to the record
    # no language stronger than "warrants explanation"
    assert "manipulation proven" not in text
    assert "intent" not in text                        # covers 'intentional' too
    # timing disclosed as omitted when no claim dates
    assert smi.timing_available is False
    assert "renormaliz" in smi.interpretation.lower()


def test_smi_short_series_reason():
    r = schedule_manipulation_indicator(SeriesAnalysis(schedules=[Schedule(project_id="E")]))
    assert r.reason and r.smi is None


# ==========================================================================
# DDI — Directed Date Index (§11.2, N17)
# ==========================================================================
def test_ddi_arithmetic_closed_form():
    # F = [0,10,20,30]: mean 15, pop std sqrt(125)=11.18034; z of the held span
    # [1,2,3] averages 0.447214; DDI = held_count(3) * 0.447214
    fundamentals = {"F1": [0.0, 10.0, 20.0, 30.0], "F2": [0.0, 10.0, 20.0, 30.0]}
    ddi, per_update, mean_held = _ddi_arithmetic(fundamentals, [1, 2, 3])
    assert mean_held == pytest.approx(0.4472136, abs=1e-6)
    assert ddi == pytest.approx(1.3416408, abs=1e-6)
    assert len(per_update) == 4


def test_zscores_zero_variance_is_zero_not_nan():
    assert _zscores([5.0, 5.0, 5.0]) == [0.0, 0.0, 0.0]
    assert _zscores([None, 5.0]) == [None, 0.0]


def test_held_run_trailing_streak():
    d = lambda m, day: datetime(2025, m, day, 17)
    finishes = [d(1, 1), d(2, 1), d(3, 1), d(3, 1), d(3, 2)]   # last 3 hold (±1d)
    assert _held_run(finishes, tol_days=1) == [2, 3, 4]
    # a date that never holds -> only the last update
    finishes2 = [d(1, 1), d(2, 1), d(3, 1)]
    assert _held_run(finishes2, tol_days=1) == [2]


def test_ddi_short_series_not_computable():
    sa = analyze_series(load_many([BASELINE, U1]))     # 2 updates < DDI_MIN_UPDATES
    r = directed_date_index(sa)
    assert r.ddi is None
    assert NOT_COMPUTABLE in r.reason and "short series" in r.reason


def test_ddi_demo_series_never_raises(series):
    r = directed_date_index(series)
    # computable or a clean NOT-COMPUTABLE reason; fundamentals always populated
    assert r.reason or r.ddi is not None
    assert set(r.fundamentals) and all(len(v) == len(series.schedules)
                                       for v in r.fundamentals.values())


# ==========================================================================
# ARR — Attribution Robustness Ratio (§11.3, N18)
# ==========================================================================
def _cert(overlay, variants):
    return {"overlay": overlay, "variants": variants}


def test_arr_hand_built_shares():
    cert = _cert(True, [
        {"computable": True, "per_party": {"Owner": 10, "Contractor": 10, "TBD": 0}},
        {"computable": True, "per_party": {"Owner": 30, "Contractor": 10, "TBD": 0}},
        {"computable": True, "per_party": {"Owner": 0, "Contractor": 20, "TBD": 0}},
    ])
    arr = attribution_robustness_ratio(cert)
    by = {p.party: p for p in arr.parties}
    # Owner shares [0.5, 0.75, 0.0] -> ARR 0/0.75 = 0
    assert by["Owner"].arr == pytest.approx(0.0)
    assert by["Owner"].min_share == pytest.approx(0.0)
    assert by["Owner"].max_share == pytest.approx(0.75)
    # Contractor shares [0.5, 0.25, 1.0] -> ARR 0.25/1.0 = 0.25
    assert by["Contractor"].arr == pytest.approx(0.25)
    assert arr.n_variants == 3
    # TBD is zero in every variant -> excluded with a note
    assert "TBD" in arr.excluded_parties
    assert "TBD" not in by


def test_arr_skips_zero_denominator_variant():
    cert = _cert(True, [
        {"computable": True, "per_party": {"Owner": 10, "Contractor": 10}},
        {"computable": True, "per_party": {"Owner": 0, "Contractor": 0}},   # skipped
        {"computable": False, "per_party": {"Owner": 99, "Contractor": 1}},  # skipped
    ])
    arr = attribution_robustness_ratio(cert)
    assert arr.n_variants == 1
    by = {p.party: p for p in arr.parties}
    assert by["Owner"].arr == pytest.approx(1.0)        # single variant -> min==max


def test_arr_not_computable_guards():
    assert NOT_COMPUTABLE in attribution_robustness_ratio(None).reason
    assert NOT_COMPUTABLE in attribution_robustness_ratio(
        _cert(False, [{"computable": True, "per_party": {"Owner": 5}}])).reason


def test_arr_on_demo_hs_certificate():
    pytest.importorskip("scheduleiq.cpm.bridge")
    from scheduleiq.analytics.robustness import run_robustness_certificate
    from scheduleiq.cpm.handshake import clear_handshake_cache
    clear_handshake_cache()
    cert = run_robustness_certificate([load(HS1)[0], load(HS2)[0]], responsibility=RM)
    assert cert.overlay is True
    arr = attribution_robustness_ratio(cert)
    assert arr.reason == ""
    assert arr.parties
    for p in arr.parties:
        assert 0.0 <= p.min_share <= p.max_share <= 1.0
        assert p.arr is None or 0.0 <= p.arr <= 1.0
    # object and dict forms agree
    arr_d = attribution_robustness_ratio(cert.to_dict())
    assert {p.party: p.arr for p in arr.parties} == \
        {p.party: p.arr for p in arr_d.parties}
    clear_handshake_cache()


# ==========================================================================
# PPS — Pacing Plausibility Score (§11.4, N19)
# ==========================================================================
def test_pps_weighted_score_with_neutral_rule():
    assert sum(PPS_CRITERIA_WEIGHTS.values()) == pytest.approx(1.0)
    crit = {"float_at_start": 100.0, "contemporaneous_awareness": None,
            "proportionality": 100.0, "reversibility": 0.0, "reacceleration": None}
    pps, neutral = _score_pps(crit)
    # 0.25*100 + 0.20*50 + 0.20*100 + 0.20*0 + 0.15*50 = 62.5
    assert pps == pytest.approx(62.5)
    assert set(neutral) == {"contemporaneous_awareness", "reacceleration"}
    # all-missing -> pure neutral, never zero
    all_none = {k: None for k in PPS_CRITERIA_WEIGHTS}
    assert _score_pps(all_none)[0] == pytest.approx(PPS_NEUTRAL)


def test_pps_from_candidate_designed_evidence():
    cand = SimpleNamespace(
        window_label="U1 -> U2", chain_codes=["A", "B"], float_at_start_days=10.0,
        contemporaneous_awareness=True, contemporaneous_events=["EOT notice"],
        reversibility="resources retained (100 -> 100 budget units) — consistent "
                      "with reversibility", reacceleration=None)
    # events available: float 100, awareness 100, proportionality 100,
    # reversibility 100, reacceleration neutral 50 -> 25+20+20+20+7.5 = 92.5
    inst = _pps_from_candidate(cand, events_available=True)
    assert inst.pps == pytest.approx(92.5)
    assert inst.neutral_criteria == ["reacceleration"]
    # no event list -> awareness also neutral -> 25+10+20+20+7.5 = 82.5
    inst2 = _pps_from_candidate(cand, events_available=False)
    assert inst2.pps == pytest.approx(82.5)
    assert "contemporaneous_awareness" in inst2.neutral_criteria


def test_pps_demo_series_scores_candidates(series):
    pps = pacing_plausibility(series)
    assert pps.reason == "" and pps.instances
    for inst in pps.instances:
        assert 0.0 <= inst.pps <= 100.0
        assert set(inst.criteria) == set(PPS_CRITERIA_WEIGHTS)
    # descending by score
    scores = [i.pps for i in pps.instances]
    assert scores == sorted(scores, reverse=True)


# ==========================================================================
# RSA — Rebuttal Surface Area (§11.5, N20)
# ==========================================================================
def test_rsa_classification_closed_form():
    windows = [
        {"window": "w1", "total_workdays": 10},   # data-fragile
        {"window": "w2", "total_workdays": 20},   # method-sensitive
        {"window": "w3", "total_workdays": 5},    # path-ambiguous
        {"window": "w4", "total_workdays": 15},   # robust
    ]
    res = _classify_rsa_windows(windows, {"w2"}, {"w1"}, {"w3"})
    assert res.total_delay_workdays == pytest.approx(50.0)
    assert res.contested_delay_workdays == pytest.approx(35.0)
    assert res.rsa_pct == pytest.approx(70.0)          # 35/50
    cls = {c.window_label: c.classification for c in res.components}
    assert cls == {"w1": "data-fragile", "w2": "method-sensitive",
                   "w3": "path-ambiguous", "w4": "robust"}
    assert res.class_totals["robust"] == pytest.approx(15.0)


def test_rsa_data_fragile_beats_method_sensitive():
    # a window that is both data-fragile and method-sensitive classifies as the
    # least defensible (data-fragile) by priority
    windows = [{"window": "w", "total_workdays": 8}]
    res = _classify_rsa_windows(windows, {"w"}, {"w"}, set())
    assert res.components[0].classification == "data-fragile"


def test_rsa_certificate_method_spread():
    cert = {"overlay": True, "variants": [
        {"is_primary": True, "computable": True,
         "windows": [{"window": "W1->W2", "total_workdays": 10},
                     {"window": "W2->W3", "total_workdays": 6}]},
        {"computable": True,
         "windows": [{"window": "W1->W2", "total_workdays": 10},
                     {"window": "W2->W3", "total_workdays": 0}]},
    ]}
    # W2->W3 total moves 0..6 (>2 wd) across variants -> method-sensitive;
    # W1->W2 is flat -> robust.  contested 6 / total 16 = 37.5%
    res = rebuttal_surface_area(cert, sa=None)
    assert res.rsa_pct == pytest.approx(37.5)
    cls = {c.window_label: c.classification for c in res.components}
    assert cls == {"W1->W2": "robust", "W2->W3": "method-sensitive"}


def test_rsa_not_computable_guards():
    assert NOT_COMPUTABLE in rebuttal_surface_area(None).reason
    assert NOT_COMPUTABLE in rebuttal_surface_area(
        {"overlay": False, "variants": []}).reason


def test_rsa_on_demo_hs_certificate():
    pytest.importorskip("scheduleiq.cpm.bridge")
    from scheduleiq.analytics.robustness import run_robustness_certificate
    from scheduleiq.cpm.handshake import clear_handshake_cache
    clear_handshake_cache()
    cert = run_robustness_certificate([load(HS1)[0], load(HS2)[0]], responsibility=RM)
    rsa = rebuttal_surface_area(cert)
    # single window (2 schedules): computable share, every component named
    assert rsa.reason == "" or NOT_COMPUTABLE in rsa.reason
    if rsa.reason == "":
        assert rsa.components and all(c.classification in lp.RSA_CLASSES
                                      for c in rsa.components)
        assert 0.0 <= rsa.rsa_pct <= 100.0
    clear_handshake_cache()


# ==========================================================================
# Privileged surface: standard card omits LI-11..15; internal card carries them
# ==========================================================================
def test_standard_card_has_no_provocative_indices(series):
    std = score_series(series, variant="standard")
    assert std.internal_indices == []
    # the provocative rows never leak into the standard series results
    ids = {r.check.id for r in series.series_results}
    assert not ({"LI-11", "LI-12", "LI-13", "LI-14", "LI-15"} & ids)


def test_internal_card_carries_provocative_indices_at_weight_zero(series):
    std = score_series(series, variant="standard")
    internal = score_series(series, variant="internal")
    # weight-0 today -> grade is IDENTICAL to the standard card
    assert internal.overall == pytest.approx(std.overall)
    assert internal.letter == std.letter
    got = {e["id"]: e for e in internal.internal_indices}
    assert set(got) == {"N16", "N17", "N18", "N19", "N20"}
    for e in got.values():
        assert e["weight"] == 0
        assert e["surface"] == "internal"
        assert e["check_id"] in {"LI-11", "LI-12", "LI-13", "LI-14", "LI-15"}
    # SMI (built, no certificate needed) carries its computed value + decomposition
    assert got["N16"]["value"] == pytest.approx(775.0 / 12.0)
    assert got["N16"]["decomposition"]["index"] == "SMI"


def test_provocative_metric_results_are_privileged_internal(series):
    matrix = load_matrix()
    results = li_provocative_results(series, matrix)
    assert {r.check.id for r in results} == {"LI-11", "LI-12", "LI-13", "LI-14", "LI-15"}
    for r in results:
        assert getattr(r, "privileged") is True
        assert getattr(r, "surface") == "internal"
        assert getattr(r, "decomposition") is not None


# ==========================================================================
# determinism + full-matrix regression
# ==========================================================================
def test_run_li_provocative_deterministic(series):
    a = run_li_provocative(series).to_dict()
    b = run_li_provocative(series).to_dict()
    assert a == b
    import json
    json.dumps(a, default=str)                         # JSON-serializable


def test_matrix_count_and_new_rows_are_series():
    matrix = load_matrix()
    assert len(matrix) == 79
    by = {c.id: c for c in matrix}
    for cid in ("LI-11", "LI-12", "LI-13", "LI-14", "LI-15"):
        assert by[cid].applies_to == "series"
        # the published weights are stated in the formula (governance)
        assert by[cid].formula


def test_series_checks_degrade_to_na_per_file():
    a = evaluate(load(BASELINE)[0])
    for cid in ("LI-11", "LI-12", "LI-13", "LI-14", "LI-15"):
        r = a.result(cid)
        assert r is not None and r.status == "N/A"     # series metric, per-file N/A


def test_run_li_provocative_clean_degradation_without_certificate(series):
    r = run_li_provocative(series)                      # no certificate
    assert r.smi.smi is not None                        # SMI needs no certificate
    assert NOT_COMPUTABLE in r.arr.reason               # ARR needs the N4 sweep
    assert NOT_COMPUTABLE in r.rsa.reason               # RSA needs the N4 sweep
    assert r.pps.reason == "" or r.pps.instances is not None
