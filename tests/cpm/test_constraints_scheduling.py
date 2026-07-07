"""
Tests for date-constraint scheduling (LIM-028), added to the ported CPM engine.

Every constraint type's forward and backward effect is asserted against
hand-computed dates on a synthetic Mon-Fri network. The expected values in the
comments are derived by hand from the day-granularity P6 scheduling reference
behavior (a documented approximation — a P6-compatible analytical convention,
NOT exact P6 emulation; ADR-006).

Workday reference (Mon-Fri; wd1 = 2026-01-05 for the DEFAULT engine table, but
these tests build a table with ~5 weeks of pre-start HEADROOM so that hard
constraints and negative-float late dates that legitimately fall before the
project start stay inside the table, exactly as production window tables carry
14d-before headroom):

  W1 = 2026-01-05 (Mon)  W2 = 2026-01-06  W3 = 2026-01-07  W4 = 2026-01-08
  W5 = 2026-01-09 (Fri)  W6 = 2026-01-12 (Mon)  W7 = 2026-01-13  W8 = 2026-01-14
  W9 = 2026-01-15        W10 = 2026-01-16 (Fri)

All fixtures are synthetic. No proprietary schedule data.
"""

import os, sys
SRC = os.path.join(os.path.dirname(__file__), "..", "..", "src")
sys.path.insert(0, os.path.abspath(SRC))

import pytest
from datetime import date

from scheduleiq.cpm.models import Activity, Calendar, Relationship  # noqa: E402
from scheduleiq.cpm.calendar_ops import build_workday_table  # noqa: E402
from scheduleiq.cpm.engine import run_analysis  # noqa: E402
from scheduleiq.cpm.constraints import (  # noqa: E402
    ConstraintType,
    SchedulingConstraint,
    ConstraintApplication,
    StatusingMode,
)


_CAL = Calendar(name="Standard")
# ~5 weeks of pre-start headroom (matches production window tables) so that
# hard-constraint / negative-float late dates before project start stay in range.
_TABLE = build_workday_table(_CAL, date(2025, 12, 1), date(2026, 6, 30))
_START = date(2026, 1, 5)   # Monday

W1  = date(2026, 1, 5)
W2  = date(2026, 1, 6)
W3  = date(2026, 1, 7)
W4  = date(2026, 1, 8)
W5  = date(2026, 1, 9)
W6  = date(2026, 1, 12)
W7  = date(2026, 1, 13)
W8  = date(2026, 1, 14)
W9  = date(2026, 1, 15)
W10 = date(2026, 1, 16)
SAT = date(2026, 1, 10)   # Saturday — non-workday, between W5 (Fri) and W6 (Mon)


def _act(act_id, od):
    return Activity(act_id=act_id, original_duration=float(od))


def _rel(pred, succ, rel_type="FS", lag=0):
    return Relationship(pred_id=pred, succ_id=succ, rel_type=rel_type, lag=lag)


def _run(acts, rels, cons=None, mode=StatusingMode.RETAINED_LOGIC, log=None):
    return run_analysis(
        acts, rels, _START, _TABLE, _CAL,
        constraints=cons, statusing_mode=mode, constraint_log_out=log,
    )


def _sc(act_id, ctype, cdate=None):
    return SchedulingConstraint(act_id, ctype, cdate)


# ===========================================================================
# START_ON_OR_AFTER (SNET) — forward floor; no backward effect.
# ===========================================================================

class TestSNET:
    def test_forward_floor_pushes_es(self):
        # A(3), logic ES=W1. SNET W6 -> ES=W6, EF=W6+2wd=W8.
        log = []
        r = _run([_act("A", 3)], [], [_sc("A", ConstraintType.START_ON_OR_AFTER, W6)], log=log)
        sa = r.scheduled["A"]
        assert sa.early_start == W6
        assert sa.early_finish == W8
        assert log[0].violated is False

    def test_no_backward_clamp_ls_follows_es(self):
        # A(2), SNET W3 -> ES=W3,EF=W4. No backward clamp; LS=W3,LF=W4,TF=0.
        r = _run([_act("A", 2)], [], [_sc("A", ConstraintType.START_ON_OR_AFTER, W3)])
        sa = r.scheduled["A"]
        assert (sa.early_start, sa.early_finish) == (W3, W4)
        assert (sa.late_start, sa.late_finish) == (W3, W4)
        assert sa.total_float == 0

    def test_no_effect_when_logic_already_later(self):
        # A(2) after P(5): P.EF=W5, FS same-workday -> logic A.ES=W5 (>= cdate W3).
        # SNET W3 therefore has no forward effect.
        log = []
        r = _run(
            [_act("P", 5), _act("A", 2)], [_rel("P", "A")],
            [_sc("A", ConstraintType.START_ON_OR_AFTER, W3)], log=log,
        )
        assert r.scheduled["A"].early_start == W5
        assert "no forward effect" in log[0].effect


# ===========================================================================
# FINISH_ON_OR_AFTER (FNET) — forward floor on EF; ES retreats by span.
# ===========================================================================

class TestFNET:
    def test_forward_pushes_ef_and_retreats_es(self):
        # A(2), logic EF=W2. FNET W5 -> EF=W5, ES=W5-1wd=W4.
        r = _run([_act("A", 2)], [], [_sc("A", ConstraintType.FINISH_ON_OR_AFTER, W5)])
        sa = r.scheduled["A"]
        assert sa.early_finish == W5
        assert sa.early_start == W4


# ===========================================================================
# START_ON (SO) and FINISH_ON (FO) — forward floor + backward ceiling.
# ===========================================================================

class TestStartOnFinishOn:
    def test_start_on_forward_and_backward(self):
        # A(2) SO W3: forward ES=max(W1,W3)=W3,EF=W4; backward LS=min(logic LS,W3).
        log = []
        r = _run([_act("A", 2)], [], [_sc("A", ConstraintType.START_ON, W3)], log=log)
        sa = r.scheduled["A"]
        assert (sa.early_start, sa.early_finish) == (W3, W4)
        assert (sa.late_start, sa.late_finish) == (W3, W4)
        # both passes disclosed
        assert "SO:" in log[0].effect and "(late)" in log[0].effect

    def test_finish_on_forward(self):
        # A(2) FO W5: EF=W5, ES=W4.
        r = _run([_act("A", 2)], [], [_sc("A", ConstraintType.FINISH_ON, W5)])
        sa = r.scheduled["A"]
        assert (sa.early_start, sa.early_finish) == (W4, W5)


# ===========================================================================
# MANDATORY_START / MANDATORY_FINISH — hard; pin both passes; violation flag.
# ===========================================================================

class TestMandatory:
    def test_mandatory_start_pins_both_passes(self):
        # A(3) MS W6 (no preds): ES=W6,EF=W8; LS=W6,LF=W8; TF=0; not violated.
        log = []
        r = _run([_act("A", 3)], [], [_sc("A", ConstraintType.MANDATORY_START, W6)], log=log)
        sa = r.scheduled["A"]
        assert (sa.early_start, sa.early_finish) == (W6, W8)
        assert (sa.late_start, sa.late_finish) == (W6, W8)
        assert log[0].violated is False

    def test_mandatory_start_violation_flag_and_days(self):
        # P(5)->A(2): P.EF=W5, FS same-workday -> logic A.ES=W5. MS A W1 overrides
        # -> ES=W1. logic ES (W5) is 4 workdays later than cdate (W1) ->
        # violated, violation_days=4.
        log = []
        r = _run(
            [_act("P", 5), _act("A", 2)], [_rel("P", "A")],
            [_sc("A", ConstraintType.MANDATORY_START, W1)], log=log,
        )
        assert r.scheduled["A"].early_start == W1
        assert r.scheduled["A"].early_finish == W2
        assert log[0].violated is True
        assert log[0].violation_days == 4

    def test_mandatory_finish_violation_flag_and_days(self):
        # P(5)->A(2): P.EF=W5, FS same-workday -> logic A.ES=W5, logic A.EF=W6.
        # MF A W3 overrides -> EF=W3, ES=W2. logic EF (W6) is 3 workdays later
        # than W3 -> violated, violation_days=3.
        log = []
        r = _run(
            [_act("P", 5), _act("A", 2)], [_rel("P", "A")],
            [_sc("A", ConstraintType.MANDATORY_FINISH, W3)], log=log,
        )
        sa = r.scheduled["A"]
        assert (sa.early_start, sa.early_finish) == (W2, W3)
        assert log[0].violated is True
        assert log[0].violation_days == 3


# ===========================================================================
# START_ON_OR_BEFORE (SNLT) / FINISH_ON_OR_BEFORE (FNLT) — backward ceiling.
# ===========================================================================

class TestSNLTFNLT:
    def test_snlt_no_effect_when_logic_already_earlier(self):
        # A(2) alone SNLT W3: logic LS=W1 (<= W3) -> no late effect.
        log = []
        r = _run([_act("A", 2)], [], [_sc("A", ConstraintType.START_ON_OR_BEFORE, W3)], log=log)
        sa = r.scheduled["A"]
        assert (sa.late_start, sa.late_finish) == (W1, W2)
        assert "no late effect" in log[0].effect

    def test_snlt_pulls_late_start_in_reducing_float(self):
        # Diamond: S(1)->A(2)->F(1); S(1)->B(5)->F(1). A has TF=3 unconstrained.
        # SNLT A W2 -> A.LS=W2, LF=W3, TF drops to 1.
        acts = [_act("S", 1), _act("A", 2), _act("B", 5), _act("F", 1)]
        rels = [_rel("S", "A"), _rel("A", "F"), _rel("S", "B"), _rel("B", "F")]
        base = _run(acts, rels)
        assert base.scheduled["A"].total_float == 3
        acts2 = [_act("S", 1), _act("A", 2), _act("B", 5), _act("F", 1)]
        r = _run(acts2, rels, [_sc("A", ConstraintType.START_ON_OR_BEFORE, W2)])
        sa = r.scheduled["A"]
        assert (sa.late_start, sa.late_finish) == (W2, W3)
        assert sa.total_float == 1

    def test_fnlt_earlier_than_logic_ef_creates_negative_float(self):
        # P(3)->A(2): logic A ES=W3,EF=W4. FNLT W3 -> LF=W3, LS=W2. EF(W4) is
        # later than LF(W3) -> TF = -1 (negative float; P6-faithful, disclosed).
        log = []
        r = _run(
            [_act("P", 3), _act("A", 2)], [_rel("P", "A")],
            [_sc("A", ConstraintType.FINISH_ON_OR_BEFORE, W3)], log=log,
        )
        sa = r.scheduled["A"]
        assert (sa.early_start, sa.early_finish) == (W3, W4)
        assert (sa.late_start, sa.late_finish) == (W2, W3)
        assert sa.total_float == -1


# ===========================================================================
# EXPECTED_FINISH (XF) — recalculate remaining duration to finish on cdate.
# ===========================================================================

class TestExpectedFinish:
    def test_xf_recalculates_remaining_duration(self):
        # A(10) alone, logic ES=W1. XF W5 -> EF:=W5 (effective span 4 workdays),
        # ES stays W1. LS=W1, LF=W5, TF=0.
        log = []
        r = _run([_act("A", 10)], [], [_sc("A", ConstraintType.EXPECTED_FINISH, W5)], log=log)
        sa = r.scheduled["A"]
        assert sa.early_start == W1
        assert sa.early_finish == W5
        assert (sa.late_start, sa.late_finish) == (W1, W5)
        assert sa.total_float == 0
        assert log[0].violated is False

    def test_xf_violation_when_cdate_before_es(self):
        # P(5)->A(10): P.EF=W5, FS same-workday -> logic A.ES=W5. XF W3 precedes
        # ES -> violated, EF held at ES (zero remaining) = W5.
        # violation_days = wd(W5)-wd(W3) = 2.
        log = []
        r = _run(
            [_act("P", 5), _act("A", 10)], [_rel("P", "A")],
            [_sc("A", ConstraintType.EXPECTED_FINISH, W3)], log=log,
        )
        sa = r.scheduled["A"]
        assert sa.early_start == W5
        assert sa.early_finish == W5
        assert log[0].violated is True
        assert log[0].violation_days == 2


# ===========================================================================
# AS_LATE_AS_POSSIBLE (ALAP) — schedule as late as own late dates allow.
# ===========================================================================

class TestALAP:
    def test_alap_consumes_free_float(self):
        # Diamond: S(1)->A(1)->F(1); S(1)->B(4)->F(1). A unconstrained ES=W1 with
        # free float. ALAP moves A to its late dates: ES:=LS=W4, EF:=LF=W4; TF=0.
        acts = [_act("S", 1), _act("A", 1), _act("B", 4), _act("F", 1)]
        rels = [_rel("S", "A"), _rel("S", "B"), _rel("A", "F"), _rel("B", "F")]
        base = _run(acts, rels)
        assert base.scheduled["A"].early_start == W1   # unconstrained: as early
        assert base.scheduled["A"].total_float > 0
        acts2 = [_act("S", 1), _act("A", 1), _act("B", 4), _act("F", 1)]
        log = []
        r = _run(acts2, rels, [_sc("A", ConstraintType.AS_LATE_AS_POSSIBLE, None)], log=log)
        sa = r.scheduled["A"]
        assert sa.early_start == W4          # scheduled as late as possible
        assert sa.early_finish == W4
        assert sa.total_float == 0
        assert "ALAP" in log[0].effect
        assert r.is_valid

    def test_alap_cdate_none_is_allowed(self):
        # Sanity: ALAP is the only type permitted to carry cdate=None.
        con = SchedulingConstraint("A", ConstraintType.AS_LATE_AS_POSSIBLE, None)
        assert con.cdate is None

    def test_non_alap_none_cdate_rejected(self):
        with pytest.raises(ValueError, match="AS_LATE_AS_POSSIBLE"):
            SchedulingConstraint("A", ConstraintType.START_ON_OR_AFTER, None)


# ===========================================================================
# Non-workday snapping.
# ===========================================================================

class TestSnapping:
    def test_snet_saturday_snaps_forward_to_monday(self):
        # SNET on Saturday 2026-01-10 (non-workday) snaps FORWARD to Monday W6.
        log = []
        r = _run([_act("A", 1)], [], [_sc("A", ConstraintType.START_ON_OR_AFTER, SAT)], log=log)
        assert r.scheduled["A"].early_start == W6
        assert log[0].cdate == W6                 # record carries the snapped date
        assert "snapped" in log[0].effect

    def test_fnlt_saturday_snaps_back_to_friday(self):
        # FNLT on Saturday 2026-01-10 (finish-type) snaps BACK to Friday W5.
        log = []
        r = _run([_act("A", 1)], [], [_sc("A", ConstraintType.FINISH_ON_OR_BEFORE, SAT)], log=log)
        assert log[0].cdate == W5
        assert "snapped" in log[0].effect


# ===========================================================================
# Pinned (actualized) activities ignore their constraints (P6 behavior).
# ===========================================================================

class TestPinnedIgnoresConstraint:
    def test_completed_activity_ignores_mandatory_start(self):
        # A pinned (completed) W6..W8. MS W1 would move an unpinned activity, but
        # actual dates outrank constraints -> A stays W6..W8; recorded "ignored".
        a = Activity(act_id="A", original_duration=3.0,
                     pinned_early_start=W6, pinned_early_finish=W8)
        log = []
        r = _run([a], [], [_sc("A", ConstraintType.MANDATORY_START, W1)], log=log)
        sa = r.scheduled["A"]
        assert (sa.early_start, sa.early_finish) == (W6, W8)
        assert log[0].violated is False
        assert "ignored (actualized)" in log[0].effect

    def test_in_progress_activity_ignores_constraint(self):
        # In-progress A (pinned ES=W6, RD=4 -> EF=W9). SNET W1 ignored.
        a = Activity(act_id="A", original_duration=10.0, remaining_duration=4.0,
                     pinned_early_start=W6)
        log = []
        r = _run([a], [], [_sc("A", ConstraintType.START_ON_OR_AFTER, W1)], log=log)
        assert r.scheduled["A"].early_start == W6
        assert r.scheduled["A"].early_finish == W9
        assert "ignored (actualized)" in log[0].effect


# ===========================================================================
# Disclosure log (constraint_log_out) + longest-path robustness + determinism.
# ===========================================================================

class TestConstraintLog:
    def test_constraint_log_out_contents(self):
        # Two constraints on two activities: log preserves input order and fields.
        acts = [_act("A", 2), _act("B", 2)]
        cons = [
            _sc("A", ConstraintType.START_ON_OR_AFTER, W3),
            _sc("B", ConstraintType.MANDATORY_START, W6),
        ]
        log = []
        r = _run(acts, [], cons, log=log)
        assert len(log) == 2
        assert all(isinstance(a, ConstraintApplication) for a in log)
        assert log[0].act_id == "A" and log[0].ctype == ConstraintType.START_ON_OR_AFTER
        assert log[1].act_id == "B" and log[1].ctype == ConstraintType.MANDATORY_START
        # to_dict is serializable and carries the P6 mnemonic
        d = log[0].to_dict()
        assert d["mnemonic"] == "SNET"
        assert d["cdate"] == W3.isoformat()

    def test_unknown_activity_recorded_not_applied(self):
        log = []
        _run([_act("A", 1)], [], [_sc("GHOST", ConstraintType.START_ON_OR_AFTER, W3)], log=log)
        assert len(log) == 1
        assert "NOT APPLIED" in log[0].effect

    def test_con_sched_warning_emitted(self):
        r = _run([_act("A", 3)], [], [_sc("A", ConstraintType.START_ON_OR_AFTER, W6)])
        codes = [w["code"] for w in r.warnings.to_list()]
        assert "CON-SCHED" in codes

    def test_constraint_controlled_source_does_not_crash_longest_path(self):
        # An activity whose ES is controlled by a constraint (not a predecessor)
        # becomes a longest-path source; the tracer must not crash.
        acts = [_act("A", 2), _act("B", 2)]
        rels = [_rel("A", "B")]
        cons = [_sc("A", ConstraintType.START_ON_OR_AFTER, W6)]
        r = _run(acts, rels, cons)
        assert r.is_valid
        assert r.critical_path is not None
        # disclosure assumption appended
        assert any("Date constraints were applied" in a for a in r.critical_path.cp_assumptions)

    def test_determinism_same_input_same_output_twice(self):
        acts1 = [_act("A", 3), _act("B", 2)]
        acts2 = [_act("A", 3), _act("B", 2)]
        rels = [_rel("A", "B")]
        cons1 = [_sc("A", ConstraintType.START_ON_OR_AFTER, W6)]
        cons2 = [_sc("A", ConstraintType.START_ON_OR_AFTER, W6)]
        log1, log2 = [], []
        r1 = _run(acts1, rels, cons1, log=log1)
        r2 = _run(acts2, rels, cons2, log=log2)
        assert r1.to_dict()["scheduled"] == r2.to_dict()["scheduled"]
        assert [a.to_dict() for a in log1] == [a.to_dict() for a in log2]
