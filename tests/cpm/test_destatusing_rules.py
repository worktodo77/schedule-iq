"""
Tests for V1-D: Rule classification (determine_rule) and DestatusingRule enum.

Covers:
  - All six rules (A-F) assigned correctly based on activity date state
  - NO_MATCH and NOT_IN_SCOPE edge cases
  - RuleAssignment fields populated correctly
  - Boundary conditions (dates exactly on new_dd / old_dd)
"""

from __future__ import annotations

import os, sys
SRC = os.path.join(os.path.dirname(__file__), "..", "..", "src")
sys.path.insert(0, os.path.abspath(SRC))

from datetime import date

import pytest

from scheduleiq.cpm.destatusing import (  # noqa: E402
    DestatusingRule,
    RuleAssignment,
    determine_rule,
)
from scheduleiq.cpm.models import Activity, Calendar  # noqa: E402


# ---------------------------------------------------------------------------
# Test calendar and date fixtures
# ---------------------------------------------------------------------------

MON = date(2024, 1, 1)   # Monday
TUE = date(2024, 1, 2)
WED = date(2024, 1, 3)
THU = date(2024, 1, 4)
FRI = date(2024, 1, 5)
MON2 = date(2024, 1, 8)
TUE2 = date(2024, 1, 9)

NEW_DD = WED   # data date moved back to
OLD_DD = FRI   # original data date


def _act(**kwargs) -> Activity:
    defaults = dict(
        act_id="ACT-001",
        original_duration=5,
        actual_duration=None,
        remaining_duration=None,
        percent_complete=0.0,
        early_start=None,
        early_finish=None,
        actual_start=None,
        actual_finish=None,
        calendar_id=None,
        constraint_type=None,
        constraint_date=None,
    )
    defaults.update(kwargs)
    return Activity(**defaults)


# ---------------------------------------------------------------------------
# Rule A: Activity completed before or on new_dd
# AS < new_dd AND AF < new_dd
# ---------------------------------------------------------------------------

class TestDetermineRuleA:
    def test_complete_before_new_dd(self):
        act = _act(actual_start=MON, actual_finish=TUE)
        r = determine_rule(act, NEW_DD, OLD_DD)
        assert r.rule == DestatusingRule.A
        assert r.act_id == "ACT-001"
        assert r.is_applicable()

    def test_af_equals_new_dd_minus_one(self):
        act = _act(actual_start=MON, actual_finish=TUE)
        r = determine_rule(act, WED, OLD_DD)
        assert r.rule == DestatusingRule.A

    def test_rule_a_assignment_fields(self):
        act = _act(actual_start=MON, actual_finish=TUE)
        r = determine_rule(act, NEW_DD, OLD_DD)
        assert r.act_id == act.act_id
        assert isinstance(r.reason, str)
        assert len(r.reason) > 0

    def test_both_dates_on_new_dd_is_not_rule_a(self):
        # AS == new_dd means not strictly before new_dd — Rule E or NO_MATCH
        act = _act(actual_start=NEW_DD, actual_finish=THU)
        r = determine_rule(act, NEW_DD, OLD_DD)
        assert r.rule != DestatusingRule.A


# ---------------------------------------------------------------------------
# Rule B: Activity completed within analysis window
# AS < new_dd AND new_dd <= AF < old_dd
# ---------------------------------------------------------------------------

class TestDetermineRuleB:
    def test_af_in_window(self):
        # Rule B: AS and AF both in window (new_dd < AS < old_dd AND new_dd < AF < old_dd)
        # THU is between WED (new_dd) and FRI (old_dd)
        act = _act(actual_start=THU, actual_finish=THU, actual_duration=1)
        r = determine_rule(act, NEW_DD, OLD_DD)
        assert r.rule == DestatusingRule.B

    def test_af_equals_new_dd_is_not_b(self):
        # AS=Mon < new_dd=Wed and AF=Mon < new_dd=Wed → Rule A (not B)
        act = _act(actual_start=MON, actual_finish=NEW_DD)
        r = determine_rule(act, NEW_DD, OLD_DD)
        # AF == new_dd: both <= new_dd → Rule A (AF not > new_dd so not Rule B)
        assert r.rule != DestatusingRule.B

    def test_af_equals_old_dd_minus_one_is_b(self):
        # AS=Thu (>new_dd), AF=Thu (<old_dd) → Rule B
        act = _act(actual_start=THU, actual_finish=THU, actual_duration=1)
        r = determine_rule(act, NEW_DD, OLD_DD)
        assert r.rule == DestatusingRule.B


# ---------------------------------------------------------------------------
# Rule C: Activity not yet started, future/planned
# No actuals; ES >= old_dd
# ---------------------------------------------------------------------------

class TestDetermineRuleC:
    def test_future_activity(self):
        # Rule C: no actuals, ES and EF both after old_dd (strictly)
        act = _act(early_start=MON2, early_finish=TUE2)
        r = determine_rule(act, NEW_DD, OLD_DD)
        assert r.rule == DestatusingRule.C

    def test_early_start_exactly_old_dd_is_not_c(self):
        # Rule C requires ES > old_dd strictly; exactly equal → NOT_IN_SCOPE
        act = _act(early_start=OLD_DD, early_finish=MON2)
        r = determine_rule(act, NEW_DD, OLD_DD)
        assert r.rule != DestatusingRule.C

    def test_no_actuals_no_early_dates_is_not_in_scope(self):
        act = _act()
        r = determine_rule(act, NEW_DD, OLD_DD)
        assert r.rule == DestatusingRule.NOT_IN_SCOPE


# ---------------------------------------------------------------------------
# Rule D: In-progress activity — AF after old_dd, AS before new_dd
# AS < new_dd AND AF >= old_dd
# ---------------------------------------------------------------------------

class TestDetermineRuleD:
    def test_spanning_old_dd(self):
        act = _act(
            actual_start=MON,
            actual_finish=MON2,
            actual_duration=5,
        )
        r = determine_rule(act, NEW_DD, OLD_DD)
        assert r.rule == DestatusingRule.D

    def test_af_exactly_old_dd_is_d(self):
        act = _act(actual_start=MON, actual_finish=OLD_DD, actual_duration=4)
        r = determine_rule(act, NEW_DD, OLD_DD)
        assert r.rule == DestatusingRule.D


# ---------------------------------------------------------------------------
# Rule E: Activity started within analysis window, not yet finished
# new_dd <= AS < old_dd, no AF
# ---------------------------------------------------------------------------

class TestDetermineRuleE:
    def test_started_in_window(self):
        # Rule E: AS in window (new_dd < AS < old_dd), no AF, EF after old_dd
        # THU (Jan 4) > WED (new_dd), < FRI (old_dd); EF=Mon2 (Jan 8) > FRI
        act = _act(
            actual_start=THU,
            remaining_duration=5,
            early_finish=MON2,
            actual_duration=1,
        )
        r = determine_rule(act, NEW_DD, OLD_DD)
        assert r.rule == DestatusingRule.E

    def test_as_exactly_new_dd_is_not_e(self):
        # AS == new_dd: Rule E requires AS > new_dd strictly → not Rule E
        act = _act(
            actual_start=NEW_DD,
            remaining_duration=3,
            early_finish=MON2,
        )
        r = determine_rule(act, NEW_DD, OLD_DD)
        assert r.rule != DestatusingRule.E


# ---------------------------------------------------------------------------
# Rule F: In-progress activity spanning new_dd
# AS < new_dd AND no AF (still running), EF after old_dd
# ---------------------------------------------------------------------------

class TestDetermineRuleF:
    def test_in_progress_spanning_new_dd(self):
        act = _act(
            actual_start=MON,
            remaining_duration=5,
            early_finish=MON2,
            actual_duration=3,
        )
        r = determine_rule(act, NEW_DD, OLD_DD)
        assert r.rule == DestatusingRule.F


# ---------------------------------------------------------------------------
# NO_MATCH and NOT_IN_SCOPE
# ---------------------------------------------------------------------------

class TestNoMatchNotInScope:
    def test_not_in_scope_rule_is_correct(self):
        act = _act()
        r = determine_rule(act, NEW_DD, OLD_DD)
        assert r.rule == DestatusingRule.NOT_IN_SCOPE

    def test_rule_assignment_has_reason_for_no_match(self):
        # Construct an anomalous activity that can't be classified
        # AF exists but AS does not — anomalous
        act = _act(actual_finish=THU)
        r = determine_rule(act, NEW_DD, OLD_DD)
        assert r.rule == DestatusingRule.NO_MATCH
        assert len(r.reason) > 0

    def test_no_match_rule_is_correct(self):
        act = _act(actual_finish=THU)
        r = determine_rule(act, NEW_DD, OLD_DD)
        assert r.rule == DestatusingRule.NO_MATCH


# ---------------------------------------------------------------------------
# RuleAssignment dataclass
# ---------------------------------------------------------------------------

class TestRuleAssignment:
    def test_frozen(self):
        act = _act(actual_start=MON, actual_finish=TUE)
        r = determine_rule(act, NEW_DD, OLD_DD)
        with pytest.raises((AttributeError, TypeError)):
            r.rule = DestatusingRule.B  # type: ignore[misc]

    def test_to_dict_shape(self):
        act = _act(actual_start=MON, actual_finish=TUE)
        r = determine_rule(act, NEW_DD, OLD_DD)
        d = r.to_dict()
        assert "act_id" in d
        assert "rule" in d
        assert "reason" in d

    def test_determinism(self):
        act = _act(actual_start=MON, actual_finish=TUE)
        r1 = determine_rule(act, NEW_DD, OLD_DD)
        r2 = determine_rule(act, NEW_DD, OLD_DD)
        assert r1.rule == r2.rule
        assert r1.reason == r2.reason
