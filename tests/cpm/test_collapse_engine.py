"""Known-answer tests for the collapse / but-for extraction engine (Step 8).

Ported from the LI MIP 3.9 tool (tests/test_collapse_engine.py) per ADR-0007 —
port-and-validate (header/import rewrites only; the network fixtures and
hand-computed assertions are verbatim).

Networks are built directly from engine dataclasses (no XER) on a continuous
7-day calendar, so workdays == calendar days and finishes are exact. We assert
the *finish movement* (compensable days), which is convention-invariant.
"""

import os, sys
SRC = os.path.join(os.path.dirname(__file__), "..", "..", "src")
sys.path.insert(0, os.path.abspath(SRC))

from datetime import date

from scheduleiq.cpm.calendar_ops import build_workday_table
from scheduleiq.cpm.collapse import (
    CollapseInput,
    Delay,
    ExtractionMode,
    LagDelay,
    detect_out_of_sequence,
    run_collapse,
)
from scheduleiq.cpm.models import Activity, Calendar, Relationship

START = date(2023, 1, 2)
CAL = Calendar(name="continuous", work_days={1, 2, 3, 4, 5, 6, 7}, hours_per_day=8.0)


def _table():
    return build_workday_table(CAL, date(2023, 1, 1), date(2023, 6, 1))


def _input(activities, relationships, delays, party, mode=ExtractionMode.GLOBAL,
           lag_delays=None):
    return CollapseInput(
        activities=activities,
        relationships=relationships,
        project_start=START,
        workday_table=_table(),
        calendar=CAL,
        delays=delays,
        lag_delays=lag_delays or [],
        party=party,
        mode=mode,
    )


# ---------------------------------------------------------------------------
# Canonical: O(12, owner-delay 10) -> K(7, contractor-delay 5); W(2) parallel.
# As-built path O->K = 19 drives. Owner extraction saves 10; contractor saves 5.
# ---------------------------------------------------------------------------

def _canonical_network():
    acts = [
        Activity("O", original_duration=12),
        Activity("K", original_duration=7),
        Activity("W", original_duration=2),
    ]
    rels = [Relationship("O", "K", "FS", 0)]
    delays = [
        Delay("O", "OWNER", 10, "owner delay on O"),
        Delay("K", "CONTRACTOR", 5, "contractor delay on K"),
    ]
    return acts, rels, delays


def test_owner_extraction_saves_ten():
    acts, rels, delays = _canonical_network()
    res = run_collapse(_input(acts, rels, delays, "OWNER"))
    assert res.is_blocked is False
    assert res.oos_clean is True
    assert res.calibration_ok is True
    assert res.n_delays_processed == 1
    assert res.compensable_days == 10
    # Removing the owner delay pulls the finish 10 days earlier.
    assert (res.original_finish - res.collapsed_finish).days == 10
    dto = res.to_dict()
    assert dto["delay_quantity"] == "ECD"
    assert dto["ecd_workdays"] == 10
    assert dto["nnd_workdays"] is None
    assert dto["adjustments"]["status"] == "not_captured"
    # E4 interim floor (F-07/FU-2) — the uncomputed credit is disclosed as NOT
    # zero, and a non-END party carries no END reconciliation disclosure.
    assert dto["adjustments"]["is_zero"] is False
    assert "not" in dto["adjustments"]["disclosure"].lower()
    assert dto["end_basis"] == "party_extraction"
    assert dto["end_is_reconciled"] is False
    assert dto["end_disclosure"] is None  # ECD run, not END


def test_contractor_extraction_saves_five():
    acts, rels, delays = _canonical_network()
    res = run_collapse(_input(acts, rels, delays, "CONTRACTOR"))
    assert res.compensable_days == 5
    assert res.n_delays_processed == 1
    dto = res.to_dict()
    assert dto["delay_quantity"] == "NND"
    assert dto["nnd_workdays"] == 5
    assert dto["ecd_workdays"] is None


def test_end_extraction_discloses_party_extraction_basis():
    """E4 interim floor (F-07/FU-2): an EXCUSABLE extraction yields END, but END
    here is a party-extraction relabel — NOT a §3.9.I.3 net-excusable
    reconciliation — and the DTO discloses that explicitly so it can't be read as
    a settled END."""
    acts, rels, delays = _canonical_network()
    res = run_collapse(_input(acts, rels, delays, "EXCUSABLE"))
    dto = res.to_dict()
    assert dto["delay_quantity"] == "END"
    assert dto["end_workdays"] is not None
    assert dto["end_basis"] == "party_extraction"
    assert dto["end_is_reconciled"] is False
    assert dto["end_disclosure"] is not None
    assert "reconciliation" in dto["end_disclosure"].lower()


def test_acp_reconciliation_cross_foots_delays_on_path_both_modes():
    """E5/F-08 (CALC-021 / §3.9.K, Codex round 1): the ACP self-check sums the
    delays LOCATED ON the analogous critical path (collapsed CP transferred to the
    as-built logic) and cross-foots them against the as-built−collapsed delta — in
    BOTH global and stepped modes (not a stepped-only marginal telescope)."""
    acts, rels, delays = _canonical_network()
    # The owner delay (10 WD on O) sits on the collapsed CP; Σ ACP delays == delta.
    for mode in (ExtractionMode.GLOBAL, ExtractionMode.STEPPED):
        res = run_collapse(_input(acts, rels, delays, "OWNER", mode=mode))
        dto = res.to_dict()
        acp = dto["acp_reconciliation"]
        assert acp["mode"] == mode.value
        assert "O" in acp["acp"]
        assert acp["acp_delay_sum_wd"] == dto["compensable_days"]
        assert acp["reconciled"] is True
        assert acp["residual_wd"] == 0
        # Never the old stepped-only marginal field.
        assert "marginal_sum_wd" not in acp


def test_bypass_change_log_records_dropped_node_and_reconnect():
    """E7/F-23: a delay that fully removes an activity (0 duration) bypasses it —
    reconnecting predecessor to successor — and that structural edit is recorded in
    the §3.9.E.5 change-log (no un-tabulated mutation)."""
    acts = [
        Activity("P", original_duration=5),
        Activity("M", original_duration=10),  # a 10-day owner delay removes M fully
        Activity("S", original_duration=5),
    ]
    rels = [Relationship("P", "M", "FS", 0), Relationship("M", "S", "FS", 2)]
    delays = [Delay("M", "OWNER", 10, "owner delay removes M entirely")]
    res = run_collapse(_input(acts, rels, delays, "OWNER"))
    log = res.to_dict()["bypass_change_log"]
    entry = next((e for e in log if e["dropped_activity"] == "M"), None)
    assert entry is not None, log
    assert "§3.9.E.5" in entry["reason"]
    # M bypassed: P reconnects to S carrying the summed lag (0 + 2).
    assert any(
        r["pred_id"] == "P" and r["succ_id"] == "S"
        and r["rel_type"] == "FS" and r["lag"] == 2
        for r in entry["reconnects"]
    ), entry["reconnects"]
    # A run with no full removals records an empty change-log.
    a2, r2, d2 = _canonical_network()
    clean = run_collapse(_input(a2, r2, d2, "OWNER"))
    assert clean.to_dict()["bypass_change_log"] == []


def test_diagnostic_rows_and_cp_membership():
    acts, rels, delays = _canonical_network()
    res = run_collapse(_input(acts, rels, delays, "OWNER"))
    assert len(res.diagnostic) == 1
    row = res.diagnostic[0]
    assert row.activity_id == "O"
    assert row.original_duration == 12
    assert row.claim_days == 10
    assert row.effective_save_wd == 10
    assert row.capped is False
    assert row.on_pre_cp is True  # O is on the as-built critical path


# ---------------------------------------------------------------------------
# Off-critical-path delay: no finish movement, non-negative, capped.
# ---------------------------------------------------------------------------

def test_off_cp_delay_is_zero_and_capped_never_negative():
    acts = [
        Activity("O", original_duration=12),
        Activity("K", original_duration=7),
        Activity("W", original_duration=2),
    ]
    rels = [Relationship("O", "K", "FS", 0)]
    # Owner delay sits on W, which is far off the critical path (2 vs 19).
    delays = [Delay("W", "OWNER", 1, "off-cp owner delay")]
    res = run_collapse(_input(acts, rels, delays, "OWNER"))
    assert res.compensable_days == 0  # never negative (no "-2 CD" bug)
    assert res.diagnostic[0].effective_save_wd == 0
    assert res.diagnostic[0].capped is True


# ---------------------------------------------------------------------------
# Stepped extraction, latest-first (§3.9.H).
# A(5) -> B(5) -> C(5); owner delays on A(3) and C(3). As-built = 15.
# Latest-first removes C before A; each marginal = 3; cumulative 3 then 6.
# ---------------------------------------------------------------------------

def test_stepped_latest_first():
    acts = [
        Activity("A", original_duration=5),
        Activity("B", original_duration=5),
        Activity("C", original_duration=5),
    ]
    rels = [
        Relationship("A", "B", "FS", 0),
        Relationship("B", "C", "FS", 0),
    ]
    delays = [Delay("A", "OWNER", 3), Delay("C", "OWNER", 3)]
    res = run_collapse(_input(acts, rels, delays, "OWNER", ExtractionMode.STEPPED))
    assert res.n_delays_processed == 2
    assert [m.activity_id for m in res.per_delay_marginal] == ["C", "A"]  # latest first
    assert [m.marginal_days for m in res.per_delay_marginal] == [3, 3]
    assert [m.cumulative_days for m in res.per_delay_marginal] == [3, 6]
    assert res.compensable_days == 6


# ---------------------------------------------------------------------------
# Full-duration removal: the activity is bypassed (preds reconnect to succs),
# so it collapses EXACTLY (no residual 0-day-milestone off-by-one).
# A(5) -> B(5) -> C(5) = 15; remove B's full 5 -> A->C -> 10; save exactly 5.
# ---------------------------------------------------------------------------

def test_full_duration_removal_is_bypassed_exactly():
    acts = [
        Activity("A", original_duration=5),
        Activity("B", original_duration=5),
        Activity("C", original_duration=5),
    ]
    rels = [
        Relationship("A", "B", "FS", 0),
        Relationship("B", "C", "FS", 0),
    ]
    delays = [Delay("B", "OWNER", 5)]  # the WHOLE of B
    res = run_collapse(_input(acts, rels, delays, "OWNER"))
    assert res.compensable_days == 5  # exact — not 4 (milestone artifact)
    assert res.diagnostic[0].effective_save_wd == 5
    assert res.diagnostic[0].capped is False


def test_collapsed_dates_surfaced_for_schedule_overlay():
    """Phase I — the but-for collapse surfaces a per-activity collapsed span
    (early start/finish) for the schedule overlay. Activities that survive into
    the but-for network appear with ISO date spans (in both GLOBAL and STEPPED
    modes); an activity fully removed (bypassed) is ABSENT, so the overlay draws
    no misleading ghost where the delay no longer exists."""
    acts, rels, delays = _canonical_network()
    res = run_collapse(_input(acts, rels, delays, "OWNER"))
    cd = res.to_dict()["collapsed_dates"]
    assert set(cd) == {"O", "K", "W"}
    for span in cd.values():
        assert span["start"] and span["finish"]
        assert span["finish"] >= span["start"]   # ISO strings sort chronologically
    # STEPPED mode populates the spans from the final stepped network too.
    stepped = run_collapse(_input(acts, rels, delays, "OWNER", ExtractionMode.STEPPED))
    assert set(stepped.to_dict()["collapsed_dates"]) == {"O", "K", "W"}
    # A fully-removed (bypassed) activity is omitted from the overlay spans.
    bp_acts = [
        Activity("A", original_duration=5),
        Activity("B", original_duration=5),
        Activity("C", original_duration=5),
    ]
    bp_rels = [Relationship("A", "B", "FS", 0), Relationship("B", "C", "FS", 0)]
    bp = run_collapse(_input(bp_acts, bp_rels, [Delay("B", "OWNER", 5)], "OWNER"))
    bp_cd = bp.to_dict()["collapsed_dates"]
    assert "B" not in bp_cd            # bypassed -> no ghost
    assert {"A", "C"} <= set(bp_cd)


# ---------------------------------------------------------------------------
# Lag-delay: a delay embedded in a relationship lag is subtracted too.
# A(5) --FS lag 5--> B(5) = 15; an owner lag-delay of 5 removes the lag -> 10.
# ---------------------------------------------------------------------------

def test_lag_delay_subtraction():
    acts = [Activity("A", original_duration=5), Activity("B", original_duration=5)]
    rels = [Relationship("A", "B", "FS", 5)]  # 5-day lag (owner-caused hold)
    res = run_collapse(
        _input(
            acts, rels, [], "OWNER",
            lag_delays=[LagDelay("A", "B", "OWNER", 5, "FS")],
        )
    )
    assert res.n_delays_processed == 1
    assert res.compensable_days == 5  # removing the 5-day lag saves 5 workdays
    # The diagnostic carries a lag row labelled pred→succ.
    assert any("A" in d.activity_id and "B" in d.activity_id for d in res.diagnostic)


# ---------------------------------------------------------------------------
# Out-of-sequence precondition: collapse is blocked, not silently run.
# ---------------------------------------------------------------------------

def test_out_of_sequence_blocks_collapse():
    acts = [
        Activity(
            "P",
            original_duration=5,
            actual_start=date(2023, 1, 2),
            actual_finish=date(2023, 1, 9),
        ),
        # S actually started 1/5 — before P finished 1/9 — an FS OOS violation.
        Activity("S", original_duration=5, actual_start=date(2023, 1, 5)),
    ]
    rels = [Relationship("P", "S", "FS", 0)]
    conflicts = detect_out_of_sequence(acts, rels)
    assert len(conflicts) == 1
    assert conflicts[0]["succ_id"] == "S"

    res = run_collapse(_input(acts, rels, [Delay("S", "OWNER", 2)], "OWNER"))
    assert res.is_blocked is True
    assert res.oos_clean is False
    assert res.collapsed_finish is None
    assert res.compensable_days == 0
    assert res.anomalies  # explains the block


def test_out_of_sequence_proceeds_when_acknowledged():
    """A3/T2-oos-unblock: once the analyst ACKNOWLEDGES the OOS (Step 2), the
    collapse no longer hard-blocks — it proceeds and stamps the conflicts on the
    result as a disclosed anomaly. oos_clean stays False and the conflicts ride on
    the result so the deliverable shows exactly what was accepted."""
    acts = [
        Activity(
            "P",
            original_duration=5,
            actual_start=date(2023, 1, 2),
            actual_finish=date(2023, 1, 9),
        ),
        Activity("S", original_duration=5, actual_start=date(2023, 1, 5)),
    ]
    rels = [Relationship("P", "S", "FS", 0)]
    inp = _input(acts, rels, [Delay("S", "OWNER", 2)], "OWNER")
    inp.oos_acknowledged = True
    res = run_collapse(inp)
    assert res.is_blocked is False                  # acknowledged → proceeds
    assert res.oos_clean is False                   # but it is NOT clean
    assert len(res.oos_conflicts) == 1              # conflicts ride on the result
    assert res.oos_conflicts[0]["succ_id"] == "S"
    assert res.collapsed_finish is not None         # a real collapse was computed
    assert any("ACKNOWLEDGED out-of-sequence" in a for a in res.anomalies)  # stamp


def test_out_of_sequence_demoted_to_warning_on_rectified_basis():
    """ADR-027 §C — when the rectified ABCS is the basis, the OOS gate demotes to
    a safety-net: a conflict that SURVIVED rectification is a disclosed RESIDUAL
    warning, not a block, with NO analyst acknowledgement required (rectification
    is itself the resolution)."""
    acts = [
        Activity("P", original_duration=5, actual_start=date(2023, 1, 2), actual_finish=date(2023, 1, 9)),
        Activity("S", original_duration=5, actual_start=date(2023, 1, 5)),
    ]
    rels = [Relationship("P", "S", "FS", 0)]
    inp = _input(acts, rels, [Delay("S", "OWNER", 2)], "OWNER")
    inp.rectified_basis = True            # NOT acknowledged — rectified basis only
    res = run_collapse(inp)
    assert res.is_blocked is False                 # demoted → proceeds
    assert res.oos_clean is False                  # the residual is still disclosed
    assert len(res.oos_conflicts) == 1
    assert res.collapsed_finish is not None
    assert any("RESIDUAL out-of-sequence" in a for a in res.anomalies)
    assert not any("ACKNOWLEDGED" in a for a in res.anomalies)  # the rectified message, not A3


def test_rectified_basis_defaults_off_keeps_block():
    """Sanity: rectified_basis defaults False, so the existing hard block is
    byte-for-byte unchanged for every current caller."""
    acts = [
        Activity("P", original_duration=5, actual_start=date(2023, 1, 2), actual_finish=date(2023, 1, 9)),
        Activity("S", original_duration=5, actual_start=date(2023, 1, 5)),
    ]
    rels = [Relationship("P", "S", "FS", 0)]
    res = run_collapse(_input(acts, rels, [Delay("S", "OWNER", 2)], "OWNER"))
    assert res.is_blocked is True


# ---------------------------------------------------------------------------
# Calibration gate: an as-built finish the CPM can't reproduce is flagged.
# ---------------------------------------------------------------------------

def test_calibration_mismatch_is_flagged():
    acts = [Activity("O", original_duration=12), Activity("K", original_duration=7)]
    rels = [Relationship("O", "K", "FS", 0)]
    inp = _input(acts, rels, [Delay("O", "OWNER", 10)], "OWNER")
    # Claim an as-built finish far from what pure CPM produces.
    inp.as_built_finish = date(2024, 1, 1)
    res = run_collapse(inp)
    assert res.calibration_ok is False
    assert any("Calibration mismatch" in a for a in res.anomalies)
    # The collapse still computes a delta in the CPM model.
    assert res.collapsed_finish is not None


def test_multiple_delays_same_activity_sum():
    """C3(2/2): the register allows MULTIPLE delay entries per activity; the engine
    sums their claimed days into one per-activity claim, so two delays of 3 + 2 on
    activity A behave exactly like one delay of 5 (n_delays_processed still counts
    each entry)."""
    acts = [Activity("A", original_duration=10), Activity("B", original_duration=5)]
    rels = [Relationship("A", "B", "FS", 0)]
    res_two = run_collapse(
        _input(acts, rels, [Delay("A", "OWNER", 3), Delay("A", "OWNER", 2)], "OWNER")
    )
    res_one = run_collapse(
        _input(acts, rels, [Delay("A", "OWNER", 5)], "OWNER")
    )
    assert res_two.is_blocked is False
    assert res_two.compensable_days == res_one.compensable_days
    assert res_two.compensable_calendar_days == res_one.compensable_calendar_days
    assert res_two.n_delays_processed == 2 and res_one.n_delays_processed == 1


# ---------------------------------------------------------------------------
# A1 / F-03 — driving-override disclosed "analyst-driver" shadow
# ---------------------------------------------------------------------------

def _two_pred_network():
    # S has two predecessors; P1 (longer) drives it as-built. The analyst asserts
    # P2 drove S → the shadow drops P1->S so P2 binds (changes the as-built finish).
    acts = [
        Activity("P1", original_duration=10),
        Activity("P2", original_duration=4),
        Activity("S", original_duration=3),
    ]
    rels = [Relationship("P1", "S", "FS", 0), Relationship("P2", "S", "FS", 0)]
    delays = [Delay("P1", "OWNER", 5, "owner delay on P1")]
    return acts, rels, delays


def test_driving_override_empty_leaves_primary_intact():
    # No overrides -> no shadow, headline unchanged (the additive-shadow guard).
    acts, rels, delays = _canonical_network()
    res = run_collapse(_input(acts, rels, delays, "OWNER"))
    assert res.compensable_days == 10
    assert res.driving_overrides_applied == []
    assert res.to_dict()["driving_override_shadow"] is None


def test_driving_override_shadow_is_disclosed_sensitivity():
    acts, rels, delays = _two_pred_network()
    base = run_collapse(_input(acts, rels, delays, "OWNER"))          # no override
    inp = _input(acts, rels, delays, "OWNER")
    inp.driving_overrides = {"S": "P2"}                              # analyst: P2 drove S
    res = run_collapse(inp)
    # Primary headline is UNTOUCHED by the override (ungameable).
    assert res.compensable_days == base.compensable_days
    assert res.collapsed_finish == base.collapsed_finish
    assert res.calibration_ok == base.calibration_ok
    # The override applied: P1->S dropped, recorded as forensic data (E7-ready).
    applied = res.driving_overrides_applied
    assert len(applied) == 1 and applied[0]["applied"] is True
    assert applied[0]["succ_id"] == "S" and applied[0]["analyst_pred_id"] == "P2"
    assert {"pred_id": "P1", "rel_type": "FS", "lag": 0} in applied[0]["dropped_edges"]
    # Shadow is present + DISCLOSED: dropping a real driving edge changes the
    # substituted as-built, so it no longer reproduces the primary finish.
    shadow = res.to_dict()["driving_override_shadow"]
    assert shadow is not None and shadow["calibration_ok"] is False
    assert any("DISCLOSED SENSITIVITY" in a for a in res.shadow_anomalies)


def test_driving_override_invalid_pred_records_unapplied():
    acts, rels, delays = _two_pred_network()
    inp = _input(acts, rels, delays, "OWNER")
    inp.driving_overrides = {"S": "NOPE"}     # not a predecessor of S
    res = run_collapse(inp)
    assert res.driving_overrides_applied == [{
        "succ_id": "S", "analyst_pred_id": "NOPE", "dropped_edges": [], "applied": False,
        "reason": "analyst predecessor is not an existing predecessor of the successor",
    }]
    # No applied override -> no shadow.
    assert res.to_dict()["driving_override_shadow"] is None
    assert res.shadow_compensable_days == 0


def test_apply_driving_overrides_drops_competing_edges():
    from scheduleiq.cpm.collapse import _apply_driving_overrides
    rels = [
        Relationship("P1", "S", "FS", 0),
        Relationship("P2", "S", "FS", 2),
        Relationship("X", "Y", "FS", 0),   # unrelated, untouched
    ]
    subst, applied = _apply_driving_overrides(rels, {"S": "P2"})
    assert {(r.pred_id, r.succ_id) for r in subst} == {("P2", "S"), ("X", "Y")}
    assert applied[0]["dropped_edges"] == [{"pred_id": "P1", "rel_type": "FS", "lag": 0}]
