"""Tests for the methodology-robustness certificate (backlog N4,
ANALYTICS_PROPOSAL.md §8.4) — scheduleiq.analytics.robustness.

The sweep is driven by the D9 half-step pair demo_hs1.xer / demo_hs2.xer (both
files handshake at 100%; the designed decomposition is documented in
tests/test_halfstep.py and the fixture generator).  Numbers asserted here are
derived from that decomposition:

    E_n MS-HS 2025-05-29, H 2025-06-11, E_n1 2025-07-07
    retained logic:  progress +9, revision +18, total +27 wd
    progress override: progress +10, revision +22, total +32 wd (OOS on the
        overlaid half-step; both files still handshake at 100%)
    named revision movers: add activity HD10 = +8 ; add HB20->HA50 = +6

With the responsibility map RM below (HA* chain -> Contractor; HB*/HC*/HD10 ->
Owner), the mip34/retained allocation is:
    progress +9  -> HA40/HA30 (Contractor)                 => Contractor 9
    revision +18 -> HD10 +8 (Owner) + HA50 +6 (Contractor) +4 residual
                                                            => Owner 8, Contractor 6,
                                                               Unallocated 4
    per party: Contractor 15, Owner 8, Unallocated 4  (Σ = 27)
"""
import os
import subprocess
import sys

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "src")
sys.path.insert(0, os.path.abspath(SRC))

from scheduleiq.ingest import load                                       # noqa: E402
from scheduleiq.analytics.halfstep import run_halfstep                   # noqa: E402
from scheduleiq.analytics.robustness import (                            # noqa: E402
    RobustnessCertificate, VariantRow, band_verdict, compute_stability_stats,
    run_robustness_certificate, _boundary_sets,
    STABLE_RANGE_WD, MODERATE_RANGE_WD)
from scheduleiq.cpm.handshake import (HandshakeRefusal,                  # noqa: E402
                                      clear_handshake_cache)

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
HS1 = os.path.join(FIX, "demo_hs1.xer")
HS2 = os.path.join(FIX, "demo_hs2.xer")
CPM_DIV = os.path.join(FIX, "demo_cpm_divergent.xer")

# HA* construction chain -> Contractor; procurement/equipment + owner change -> Owner
RM = {c: "Contractor" for c in
      ("HMS-START", "HA10", "HA20", "HA30", "HA40", "HA50", "HA60", "HA70",
       "HX10", "MS-HS")}
RM.update({"HB10": "Owner", "HB15": "Owner", "HB20": "Owner",
           "HC10": "Owner", "HC20": "Owner", "HD10": "Owner"})


@pytest.fixture(scope="session", autouse=True)
def fixtures():
    if not (os.path.exists(HS1) and os.path.exists(HS2) and os.path.exists(CPM_DIV)):
        subprocess.run([sys.executable, os.path.join(FIX, "make_fixtures.py")],
                       check=True)


@pytest.fixture(autouse=True)
def _fresh_handshake_cache():
    clear_handshake_cache()
    yield
    clear_handshake_cache()


@pytest.fixture(scope="session")
def earlier():
    return load(HS1)[0]


@pytest.fixture(scope="session")
def later():
    return load(HS2)[0]


# ---------------------------------------------------------------- grid enumeration
def test_grid_enumeration_size_and_coordinates(earlier, later):
    cert = run_robustness_certificate([earlier, later])
    # 3 framings x 2 statusings x 1 boundary (collapsed) x 1 contested = 6
    assert len(cert.variants) == 6
    framings = {v.framing for v in cert.variants}
    assert framings == {"mip34_halfstep", "mip33_asis", "n3_daily"}
    assert {v.statusing for v in cert.variants} == {"retained_logic",
                                                    "progress_override"}
    assert all(v.boundary == "full" for v in cert.variants)
    assert all(v.contested == "with_revisions" for v in cert.variants)
    # every coordinate pair appears exactly once
    coords = {(v.framing, v.statusing) for v in cert.variants}
    assert len(coords) == 6
    # collapsed dimensions are disclosed
    assert any("boundary dimension COLLAPSED" in d for d in cert.disclosures)
    assert any("contested-revision dimension COLLAPSED" in d for d in cert.disclosures)


def test_contested_dimension_expands_halfstep_only(earlier, later):
    cert = run_robustness_certificate([earlier, later],
                                      contested_revisions=["add activity HD10"])
    # +1 without_contested per half-step statusing (2) = 8 variants
    assert len(cert.variants) == 8
    without = [v for v in cert.variants if v.contested == "without_contested"]
    assert len(without) == 2
    assert all(v.framing == "mip34_halfstep" for v in without)
    assert not any("contested-revision dimension COLLAPSED" in d
                   for d in cert.disclosures)


def test_boundary_sets_helper_three_schedules():
    class _S:
        def __init__(self, n):
            self._n = n

        def label(self):
            return self._n

    sets = _boundary_sets([_S("A"), _S("B"), _S("C")])
    assert sets == [("full", [(0, 1), (1, 2)]), ("drop:B", [(0, 2)])]


def test_include_daily_false_drops_daily(earlier, later):
    cert = run_robustness_certificate([earlier, later], include_daily=False)
    assert not any(v.framing == "n3_daily" for v in cert.variants)
    assert len(cert.variants) == 4
    assert any("daily framing DISABLED" in d for d in cert.disclosures)


def test_max_variants_truncation_disclosed(earlier, later):
    cert = run_robustness_certificate([earlier, later], max_variants=3)
    assert len(cert.variants) == 3
    assert cert.dimensions["truncated"] == 3
    assert any("capped at max_variants=3" in d for d in cert.disclosures)


# ------------------------------------------------------------- primary consistency
def test_primary_variant_equals_direct_halfstep(earlier, later):
    cert = run_robustness_certificate([earlier, later])   # no overlay -> totals
    primary = cert.primary()
    assert primary is not None
    assert primary.variant_id == \
        "mip34_halfstep|retained_logic|full|with_revisions"
    # the primary measured quantity reproduces a direct D9 run
    direct = run_halfstep(earlier, later)
    assert primary.total_workdays == direct.total_movement_workdays == 27
    # primary handshake summaries captured on the certificate header (100%)
    assert cert.handshake_primary_earlier["match_rate_pct"] == 100.0
    assert cert.handshake_primary_later["match_rate_pct"] == 100.0
    assert "finish milestone" in cert.target_resolved_how


# ------------------------------------------------------------- statusing dimension
def test_statusing_flip_changes_mode_and_numbers(earlier, later):
    cert = run_robustness_certificate([earlier, later])
    ret = cert.variant("mip34_halfstep|retained_logic|full|with_revisions")
    ovr = cert.variant("mip34_halfstep|progress_override|full|with_revisions")
    # the flip is verified through the bridge's own resolved mode
    assert ret.statusing_mode_resolved == "retained_logic"
    assert ovr.statusing_mode_resolved == "progress_override"
    # demo_hs2 carries an in-progress activity whose overlaid half-step is
    # out-of-sequence, so progress-override moves the number (27 -> 32) — a real
    # numeric difference, not just a recorded mode.
    assert ret.total_workdays == 27
    assert ovr.total_workdays == 32
    assert ovr.total_workdays != ret.total_workdays
    # the bridge disclosure is surfaced as evidence the flip took effect
    assert any(d.startswith("bridge: statusing mode: progress_override")
               for d in cert.disclosures)


# ------------------------------------------------------------- contested exclusion
def test_contested_exclusion_changes_revision_by_designed_minus_8(earlier, later):
    cert = run_robustness_certificate([earlier, later],
                                      contested_revisions=["add activity HD10"])
    with_rev = cert.variant(
        "mip34_halfstep|retained_logic|full|with_revisions")
    without = cert.variant(
        "mip34_halfstep|retained_logic|full|without_contested")
    # HD10's D9-attributed delta is +8; excluding it drops the total by exactly 8
    assert with_rev.total_workdays == 27
    assert without.total_workdays == 19
    assert with_rev.total_workdays - without.total_workdays == 8
    det = without.windows[0]["detail"]
    assert det["excluded_delta_workdays"] == 8
    assert "add activity HD10" in det["excluded_edits"]
    assert det["revision_effect_after_exclusion"] == 10   # 18 - 8


def test_contested_no_match_is_disclosed_no_adjustment(earlier, later):
    cert = run_robustness_certificate([earlier, later],
                                      contested_revisions=["add activity NOPE99"])
    with_rev = cert.variant("mip34_halfstep|retained_logic|full|with_revisions")
    without = cert.variant("mip34_halfstep|retained_logic|full|without_contested")
    assert with_rev.total_workdays == without.total_workdays == 27
    assert any("matched no named top-mover edit" in d for d in cert.disclosures)


# --------------------------------------------------------- responsibility overlay
def test_responsibility_allocated_path(earlier, later):
    cert = run_robustness_certificate([earlier, later], responsibility=RM)
    assert cert.overlay is True
    ret = cert.variant("mip34_halfstep|retained_logic|full|with_revisions")
    # progress 9 -> Contractor; revision HD10 +8 -> Owner, HA50 +6 -> Contractor,
    # residual +4 -> Unallocated.
    assert ret.per_party == {"Contractor": 15.0, "Owner": 8.0, "Unallocated": 4.0}
    assert round(sum(ret.per_party.values())) == 27
    # MIP 3.3 dumps the whole movement on the controlling activity's party
    mip33 = cert.variant("mip33_asis|retained_logic|full|with_revisions")
    assert mip33.per_party == {"Contractor": 27.0}
    # the sweep exposes the attribution's method-sensitivity as ranges
    contractor = cert.series("Contractor")
    owner = cert.series("Owner")
    assert contractor is not None and owner is not None
    assert owner.minimum == 0.0 and owner.maximum == 8.0


def test_no_overlay_path_is_totals_only(earlier, later):
    cert = run_robustness_certificate([earlier, later])
    assert cert.overlay is False
    assert all(v.per_party == {} for v in cert.variants)
    assert all(v.total_workdays is not None for v in cert.variants if v.computable)
    # a single TOTAL stability series
    assert [s.series for s in cert.stability] == ["TOTAL"]
    total = cert.series("TOTAL")
    assert total.minimum == 3.0 and total.maximum == 32.0   # daily 3 .. override 32


# --------------------------------------------------------- daily framing present
def test_daily_framing_computes_and_differs_from_halfstep(earlier, later):
    cert = run_robustness_certificate([earlier, later], responsibility=RM)
    daily = cert.variant("n3_daily|retained_logic|full|with_revisions")
    assert daily.computable is True
    # later-network framing nets revisions differently: a much smaller number
    assert daily.total_workdays == 3.0


# -------------------------------------------------- stability stats (hand-built)
def test_stability_stats_arithmetic_overlay():
    rows = [
        VariantRow("v1", "mip34_halfstep", "retained_logic", "full",
                   "with_revisions", per_party={"Owner": 10.0, "Contractor": 5.0}),
        VariantRow("v2", "mip33_asis", "retained_logic", "full",
                   "with_revisions", per_party={"Owner": 14.0, "Contractor": 5.0}),
        VariantRow("v3", "n3_daily", "retained_logic", "full",
                   "with_revisions", per_party={"Owner": 12.0}),  # Contractor -> 0
        VariantRow("vX", "mip34_halfstep", "progress_override", "full",
                   "with_revisions", computable=False, reason="skip"),
    ]
    stats = compute_stability_stats(rows)
    by = {s.series: s for s in stats}
    # not-computable v3? it IS computable; vX excluded.  Owner values 10,14,12
    owner = by["Owner"]
    assert owner.n_variants == 3
    assert owner.minimum == 10.0 and owner.maximum == 14.0
    assert owner.range == 4.0 and owner.median == 12.0
    assert owner.verdict == "MODERATE"          # range 4 <= 5 wd
    # Contractor: 5, 5, 0 (absent -> 0)
    contractor = by["Contractor"]
    assert contractor.values == [5.0, 5.0, 0.0]
    assert contractor.range == 5.0 and contractor.median == 5.0
    assert "Contractor-responsible delay ranges 0–5 wd" in contractor.sentence


def test_stability_stats_total_series_no_overlay():
    rows = [
        VariantRow("v1", "mip34_halfstep", "retained_logic", "full",
                   "with_revisions", total_workdays=30.0),
        VariantRow("v2", "mip33_asis", "retained_logic", "full",
                   "with_revisions", total_workdays=31.0),
        VariantRow("v3", "n3_daily", "retained_logic", "full",
                   "with_revisions", total_workdays=32.0),
    ]
    stats = compute_stability_stats(rows)
    assert len(stats) == 1
    tot = stats[0]
    assert tot.series == "TOTAL"
    assert tot.range == 2.0 and tot.verdict == "STABLE"   # range 2 <= 2 wd
    assert tot.sentence.startswith("Total target movement ranges 30–32 wd")


# ------------------------------------------------------- verdict banding
def test_verdict_banding_boundaries():
    # range at exactly the workday thresholds is inclusive (median 0 isolates
    # the workday arm from the percentage arm)
    assert band_verdict(STABLE_RANGE_WD, 0.0) == "STABLE"          # 2 wd
    assert band_verdict(STABLE_RANGE_WD + 0.001, 0.0) == "MODERATE"
    assert band_verdict(MODERATE_RANGE_WD, 0.0) == "MODERATE"      # 5 wd
    assert band_verdict(MODERATE_RANGE_WD + 0.001, 0.0) == "UNSTABLE"
    # percentage arm: 10 wd on median 100 = 10% -> STABLE; 25 -> MODERATE
    assert band_verdict(10.0, 100.0) == "STABLE"
    assert band_verdict(25.0, 100.0) == "MODERATE"
    assert band_verdict(26.0, 100.0) == "UNSTABLE"
    # zero median falls back to the workday arm only
    assert band_verdict(1.0, 0.0) == "STABLE"
    assert band_verdict(9.0, 0.0) == "UNSTABLE"


# ------------------------------------------------------- refusal + skip
def test_refusal_propagates_on_primary(earlier):
    div = load(CPM_DIV)[0]
    # primary window (hs1 -> divergent) refuses -> propagates under require
    with pytest.raises(HandshakeRefusal):
        run_robustness_certificate([earlier, div])


def test_skip_computes_and_degrades(earlier):
    div = load(CPM_DIV)[0]
    cert = run_robustness_certificate([earlier, div], handshake="skip")
    # never raises for variant-level failures; some variants degrade
    assert len(cert.variants) == 6
    assert cert.computable_variants >= 1
    assert cert.computable_variants < 6          # divergent network breaks some
    assert any(not v.computable and v.reason for v in cert.variants)


# ------------------------------------------------------- validation guards
def test_bad_handshake_mode_raises(earlier, later):
    with pytest.raises(ValueError):
        run_robustness_certificate([earlier, later], handshake="maybe")


def test_too_few_schedules_raises(earlier):
    with pytest.raises(ValueError):
        run_robustness_certificate([earlier])


# ------------------------------------------------------- determinism + shape
def test_determinism_identical_to_dict(earlier, later):
    clear_handshake_cache()
    a = run_robustness_certificate([earlier, later], responsibility=RM).to_dict()
    clear_handshake_cache()
    b = run_robustness_certificate([earlier, later], responsibility=RM).to_dict()
    assert a == b


def test_to_dict_shape_and_preliminary(earlier, later):
    import json
    cert = run_robustness_certificate([earlier, later], responsibility=RM)
    d = cert.to_dict()
    assert set(d) >= {"label", "target", "dimensions", "verdict_thresholds",
                      "variants", "stability", "sentences", "disclosures",
                      "allocation_note", "preliminary", "handshake",
                      "computable_variant_count", "total_variant_count"}
    assert "PRELIMINARY" in d["preliminary"]
    assert "reserved to the expert" in d["preliminary"]
    assert "OBSERVATIONAL" in d["allocation_note"]
    assert d["overlay"] is True
    assert isinstance(cert, RobustnessCertificate)
    # the §8.4-style sentence is present
    assert any("ranges" in s and "method variants" in s for s in d["sentences"])
    json.dumps(d)                    # must be JSON-serializable
