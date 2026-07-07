"""Tests for the MIP 3.4 half-step engine (backlog D9) —
scheduleiq.analytics.halfstep.

demo_hs1.xer / demo_hs2.xer are an engine-consistent update pair (both files'
stored tool-of-record dates are produced by the ported engine, so BOTH
handshake at 100%).  Every asserted number below was extracted from a manual
engine run on the pair and sanity-checked against the designed mechanism; the
full mechanism map is in the fixture generator's header comment
(tests/fixtures/make_fixtures.py, "MIP 3.4 half-step fixture pair") and
restated inline per assertion.

The designed decomposition (single 5-day calendar; workdays of the target
MS-HS's own calendar):

    E_n  MS-HS EF 2025-05-29   (hs1 as imported, DD 2025-04-07)
    H    MS-HS EF 2025-06-11   (hs1 network + hs2 progress, DD 2025-05-05)
    E_n1 MS-HS EF 2025-07-07   (hs2 as imported)

    progress_effect  = +9  wd  (HA30 finished 5 wd late; HA40 started late,
                                RD 4 still open at the hs2 data date)
    revision_effect  = +18 wd
    total_movement   = +27 wd  == 9 + 18 (identity, exact by construction)

Per-class revision attribution (each class re-applied ALONE on the half-step):
    logic_added        +6  (new tie HB20->HA50: envelope waits for equipment)
    logic_deleted       0  (old HB20->HA70 tie was not binding in H)
    duration_changed   +4  (HA50 OD 8 -> 12 wd on the controlling chain)
    constraint_changed +3  (SNET 2025-05-26 added on HA60)
    new_activities     +8  (HD10 inserted HA60 -> HD10 -> HA70)
    deleted_activities  0  (HX10 descoped; off-path)
    sum = +21; interaction residual = 18 - 21 = -3 (the SNET is absorbed when
    the other revisions push HA60 past its date — designed interaction).
"""
import os
import subprocess
import sys

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "src")
sys.path.insert(0, SRC)

from scheduleiq.ingest import load                                        # noqa: E402
from scheduleiq.analytics.halfstep import (HalfStepResult, run_halfstep,  # noqa: E402
                                           run_halfstep_series)
from scheduleiq.cpm.handshake import HandshakeRefusal, clear_handshake_cache  # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
HS1 = os.path.join(FIX, "demo_hs1.xer")
HS2 = os.path.join(FIX, "demo_hs2.xer")
CPM_DIV = os.path.join(FIX, "demo_cpm_divergent.xer")


@pytest.fixture(scope="session", autouse=True)
def fixtures():
    if not (os.path.exists(HS1) and os.path.exists(HS2)):
        subprocess.run([sys.executable, os.path.join(FIX, "make_fixtures.py")],
                       check=True)


@pytest.fixture(scope="session")
def earlier():
    return load(HS1)[0]


@pytest.fixture(scope="session")
def later():
    return load(HS2)[0]


@pytest.fixture(scope="session")
def hs(earlier, later):
    return run_halfstep(earlier, later)


# ---------------------------------------------------------------- handshake gate
def test_both_files_handshake_at_100(hs):
    assert hs.handshake_mode == "require"
    assert hs.handshake_earlier["match_rate_pct"] == 100.0
    assert hs.handshake_later["match_rate_pct"] == 100.0
    assert hs.handshake_earlier["passed"] and hs.handshake_later["passed"]


def test_handshake_refusal_propagates_on_divergent(earlier):
    # divergent file in either slot refuses the pair (both files are gated)
    div = load(CPM_DIV)[0]
    with pytest.raises(HandshakeRefusal):
        run_halfstep(earlier, div)
    with pytest.raises(HandshakeRefusal):
        run_halfstep(div, earlier)


def test_handshake_skip_runs_with_disclosure(earlier, later):
    r = run_halfstep(earlier, later, handshake="skip")
    assert any("skip" in d.lower() and "bypass" in d.lower() for d in r.disclosures)
    # skip still computes the same decomposition on valid files
    assert r.progress_effect_workdays == 9
    assert r.revision_effect_workdays == 18
    assert r.total_movement_workdays == 27


def test_bad_handshake_mode_raises(earlier, later):
    with pytest.raises(ValueError):
        run_halfstep(earlier, later, handshake="maybe")


# ------------------------------------------------------------- target resolution
def test_target_resolves_to_finish_milestone_in_both(hs):
    assert hs.target_code == "MS-HS"
    assert "finish milestone" in hs.resolved_how
    assert hs.target_in_earlier is True
    assert hs.target_calendar == "HS Standard 5-Day"


# ----------------------------------------------------------------- decomposition
def test_engine_dates_of_the_three_runs(hs):
    # E_n (hs1 as imported), H (half-step), E_n1 (hs2 as imported)
    assert hs.en_target_ef.isoformat() == "2025-05-29"
    assert hs.h_target_ef.isoformat() == "2025-06-11"
    assert hs.en1_target_ef.isoformat() == "2025-07-07"


def test_exact_progress_and_revision_effects(hs):
    # HA30 finished 5 wd late + HA40 late start/RD 4 at the new DD -> +9 wd of
    # pure performance slip; the revisions add a further +18 wd.
    assert hs.progress_effect_workdays == 9
    assert hs.revision_effect_workdays == 18
    assert hs.total_movement_workdays == 27


def test_decomposition_identity_exact(hs):
    # exact by construction (three engine dates on one target workday table);
    # asserted in code too — this test re-checks it from the result fields.
    assert hs.identity_holds is True
    assert (hs.progress_effect_workdays + hs.revision_effect_workdays
            == hs.total_movement_workdays)
    assert (hs.progress_effect_calendar_days + hs.revision_effect_calendar_days
            == hs.total_movement_calendar_days)


def test_record_movement_carried_beside_engine_numbers(hs):
    # the fixture's record dates ARE engine-produced (engine-of-record
    # pattern), so record movement equals the engine total here — but it is
    # carried as a separate field, never merged (presentation rule).
    assert hs.record_movement_calendar_days == 39
    assert hs.record_movement_workdays == 27


def test_data_dates_and_labels(hs):
    assert hs.earlier_data_date.isoformat() == "2025-04-07"
    assert hs.later_data_date.isoformat() == "2025-05-05"
    assert "2025-04-07" in hs.earlier_label
    assert "2025-05-05" in hs.later_label


# ------------------------------------------------------- per-class attribution
def test_designed_logic_add_class_is_nonzero(hs):
    ca = hs.attribution("logic_added")
    assert ca.computable and ca.n_edits == 1
    assert ca.delta_workdays == 6            # HB20->HA50 reroute binds HA50
    assert ca.target_finish_engine.isoformat() == "2025-06-19"


def test_designed_od_change_class_is_nonzero(hs):
    ca = hs.attribution("duration_changed")
    assert ca.computable and ca.n_edits == 1
    assert ca.delta_workdays == 4            # HA50 OD 8 -> 12 on the chain


def test_constraint_and_new_activity_classes(hs):
    assert hs.attribution("constraint_changed").delta_workdays == 3   # SNET HA60
    assert hs.attribution("new_activities").delta_workdays == 8      # HD10 insert


def test_zero_delta_classes_are_reported_not_dropped(hs):
    # honest zeros: the deleted tie was not binding; HX10 was off-path
    assert hs.attribution("logic_deleted").delta_workdays == 0
    assert hs.attribution("deleted_activities").delta_workdays == 0
    # untouched classes present with 0 edits (deterministic full table)
    assert hs.attribution("lag_type_changed").n_edits == 0
    assert hs.attribution("calendar_changed").n_edits == 0


def test_residual_reported_present_and_finite_not_forced_zero(hs):
    # sum(classes) = 6+0+4+3+8+0 = 21; revision_effect = 18; the SNET's +3 is
    # absorbed by interaction in the full network -> residual -3.  The
    # requirement is that the residual is PRESENT and finite — asserting the
    # designed value documents the interaction; it must never be forced to 0.
    assert hs.attribution_sum_workdays == 21
    assert hs.residual_workdays is not None
    assert isinstance(hs.residual_workdays, int)
    assert hs.residual_workdays == -3
    assert "never forced to zero" in hs.attribution_block()["residual_note"]


def test_named_top_movers_include_the_designed_edits(hs):
    # top movers are computed for the two largest classes: new_activities (+8)
    # and logic_added (+6) — the designed edits are named.
    added = hs.attribution("logic_added")
    newact = hs.attribution("new_activities")
    assert [m["edit"] for m in added.top_movers] == ["add HB20->HA50"]
    assert added.top_movers[0]["delta_workdays"] == 6
    assert [m["edit"] for m in newact.top_movers] == ["add activity HD10"]
    assert newact.top_movers[0]["delta_workdays"] == 8
    # non-top-2 classes carry no mover reruns (cap discipline)
    assert hs.attribution("duration_changed").top_movers == []


# ----------------------------------------- new / deleted activity handling
def test_new_and_deleted_activity_disclosures(hs):
    # HD10 (new in later) is NOT overlaid onto the half-step; HX10 (deleted in
    # later) keeps its earlier unprogressed state — both disclosed by name.
    assert any("HD10" in d and "NOT overlaid" in d for d in hs.disclosures)
    assert any("HX10" in d and "unprogressed" in d for d in hs.disclosures)


def test_new_activity_absent_from_half_step_run(hs):
    # the half-step target EF (2025-06-11) predates the HD10 insertion effect;
    # HD10 first appears in the new_activities class run (+8 wd).
    assert hs.h_target_ef.isoformat() == "2025-06-11"
    assert hs.attribution("new_activities").target_finish_engine.isoformat() \
        == "2025-06-23"


# ------------------------------------------------------- progress contributors
def test_progress_contributors_rank_the_designed_slips(hs):
    codes = [r["code"] for r in hs.progress_contributors]
    # HA40 (RD 10 -> 4, |change| 6) outranks HA30 (RD 5 -> 0, |change| 5);
    # both sit on the half-step's controlling path.
    assert codes[:2] == ["HA40", "HA30"]
    ha40 = hs.progress_contributors[0]
    assert ha40["rd_change_workdays"] == -6.0
    assert ha40["later_status"] == "In Progress"
    # the heuristic is disclosed
    assert any("HEURISTIC" in d for d in hs.disclosures)


def test_progress_contributors_exclude_pure_od_revisions(hs):
    # HA50 is on the controlling path and its RD changed 8 -> 12 wd, but it is
    # not started in EITHER update — that is the OD revision, not progress.
    assert "HA50" not in {r["code"] for r in hs.progress_contributors}


# --------------------------------------------------------------- MIP 3.3 row
def test_mip33_row_fields(hs):
    row = hs.mip33_row
    assert row["method"].startswith("MIP 3.3")
    assert row["target_code"] == "MS-HS"
    assert row["record_finish_movement_calendar_days"] == 39
    assert row["engine_finish_movement_calendar_days"] == 39
    assert 0.0 < row["critical_path_jaccard"] < 1.0
    counts = row["change_counts"]
    assert counts["activities added"] == 1        # HD10
    assert counts["activities deleted"] == 1      # HX10
    assert counts["relationships added"] == 3     # HB20->HA50 + HD10's two ties
    assert counts["relationships deleted"] == 2   # HB20->HA70, HA10->HX10
    assert counts["duration changes"] == 1        # HA50 OD
    assert counts["constraint changes"] == 1      # SNET on HA60


# ------------------------------------------------------------------ series API
def test_series_runs_pairs_and_degrades_on_refusal(earlier, later):
    div = load(CPM_DIV)[0]
    results = run_halfstep_series([earlier, later, div])
    assert len(results) == 2
    good, stub = results
    # pair 1 computes normally
    assert good.refused is False
    assert good.total_movement_workdays == 27
    # pair 2 (later, divergent) is a refusal STUB, not an exception
    assert stub.refused is True
    assert "handshake refused" in stub.refusal
    assert stub.earlier_label and stub.later_label
    assert stub.decomposition_blocking == "" and stub.en_target_ef is None
    assert any("stub" in d for d in stub.disclosures)


# -------------------------------------------------------------------- determinism
def test_deterministic_to_dict(earlier, later):
    clear_handshake_cache()
    a = run_halfstep(earlier, later).to_dict()
    clear_handshake_cache()
    b = run_halfstep(earlier, later).to_dict()
    assert a == b


# ----------------------------------------------------------------- serialization
def test_to_dict_shape_and_preliminary_label(hs):
    d = hs.to_dict()
    assert set(d) >= {"pair", "refused", "handshake", "decomposition",
                      "revision_attribution", "progress_contributors",
                      "mip33_row", "disclosures", "preliminary"}
    assert "PRELIMINARY" in d["preliminary"]
    assert "reserved to the expert" in d["preliminary"]
    assert d["decomposition"]["identity"] == \
        "total_movement == progress_effect + revision_effect"
    assert isinstance(hs, HalfStepResult)
