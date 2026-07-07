"""
Tests for Destatusing Rules A through F (CALC-005 through CALC-010).
Source: src/mip39/destatusing.py

Source authority: CPW-P6 Manual p. 40, Figure 1 ("Activity Destatus Procedure").
All fixtures are synthetic. No proprietary data.

Data dates used throughout unless overridden:
  new_dd = 2024-01-10 (Wednesday, workday 8 in Jan 2024)
  old_dd = 2024-01-17 (Wednesday, workday 13 in Jan 2024)
Workday table: 2024-01-01 (Mon) through 2024-01-31 (Wed), Mon-Fri 8h/day.
"""

import os, sys
SRC = os.path.join(os.path.dirname(__file__), "..", "..", "src")
sys.path.insert(0, os.path.abspath(SRC))

import json
import math
import pytest
from datetime import date
from pathlib import Path

from scheduleiq.cpm.models import Activity, Calendar  # noqa: E402
from scheduleiq.cpm.calendar_ops import build_workday_table  # noqa: E402
from scheduleiq.cpm.destatusing import (  # noqa: E402
    destatus_rule_a,
    destatus_rule_b,
    destatus_rule_c,
    destatus_rule_d,
    destatus_rule_e,
    destatus_rule_f,
)

FIXTURES = Path(__file__).parent / "fixtures"

# Shared test dates
NEW_DD = date(2024, 1, 10)  # Wednesday — workday 8
OLD_DD = date(2024, 1, 17)  # Wednesday — workday 13

# Shared workday table for rules that need it
_CAL = Calendar(name="Standard")
_TABLE = build_workday_table(_CAL, date(2024, 1, 1), date(2024, 1, 31))


def _load_fixture() -> dict:
    with open(FIXTURES / "destatusing_scenarios.json") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# CALC-005: Rule A — Do nothing
# ---------------------------------------------------------------------------

class TestRuleA:
    def test_basic_do_nothing(self):
        act = Activity(
            act_id="ACT-A",
            actual_start=date(2024, 1, 3),
            actual_finish=date(2024, 1, 5),
        )
        result = destatus_rule_a(act, NEW_DD, OLD_DD)
        assert result.actual_start == date(2024, 1, 3)
        assert result.actual_finish == date(2024, 1, 5)

    def test_returns_copy_not_same_object(self):
        act = Activity(
            act_id="ACT-A",
            actual_start=date(2024, 1, 3),
            actual_finish=date(2024, 1, 5),
        )
        result = destatus_rule_a(act, NEW_DD, OLD_DD)
        assert result is not act

    def test_fixture_match(self):
        fx = _load_fixture()["rule_a"]
        act = Activity(
            act_id=fx["act_id"],
            actual_start=date.fromisoformat(fx["actual_start"]),
            actual_finish=date.fromisoformat(fx["actual_finish"]),
        )
        result = destatus_rule_a(act, NEW_DD, OLD_DD)
        assert result.actual_start == date.fromisoformat(fx["expected"]["actual_start"])
        assert result.actual_finish == date.fromisoformat(fx["expected"]["actual_finish"])

    def test_missing_actual_start_raises(self):
        act = Activity(act_id="ACT-A", actual_finish=date(2024, 1, 5))
        with pytest.raises(ValueError, match="missing required field 'actual_start'"):
            destatus_rule_a(act, NEW_DD, OLD_DD)

    def test_missing_actual_finish_raises(self):
        act = Activity(act_id="ACT-A", actual_start=date(2024, 1, 3))
        with pytest.raises(ValueError, match="missing required field 'actual_finish'"):
            destatus_rule_a(act, NEW_DD, OLD_DD)

    def test_condition_not_met_raises(self):
        # AS is after new_dd — not a Rule A activity
        act = Activity(
            act_id="ACT-A",
            actual_start=date(2024, 1, 12),
            actual_finish=date(2024, 1, 15),
        )
        with pytest.raises(ValueError, match="condition not met"):
            destatus_rule_a(act, NEW_DD, OLD_DD)

    def test_as_on_new_dd_not_rule_a(self):
        # AS must be strictly before new_dd
        act = Activity(
            act_id="ACT-A",
            actual_start=NEW_DD,
            actual_finish=date(2024, 1, 5),
        )
        with pytest.raises(ValueError, match="condition not met"):
            destatus_rule_a(act, NEW_DD, OLD_DD)


# ---------------------------------------------------------------------------
# CALC-006: Rule B — Remove AS/AF, OD=AD, PC=0
# ---------------------------------------------------------------------------

class TestRuleB:
    def test_basic_reset(self):
        act = Activity(
            act_id="ACT-B",
            actual_start=date(2024, 1, 11),
            actual_finish=date(2024, 1, 15),
            actual_duration=3.0,
        )
        result = destatus_rule_b(act, NEW_DD, OLD_DD)
        assert result.actual_start is None
        assert result.actual_finish is None
        assert result.original_duration == 3.0
        assert result.percent_complete == 0.0

    def test_original_activity_not_mutated(self):
        act = Activity(
            act_id="ACT-B",
            actual_start=date(2024, 1, 11),
            actual_finish=date(2024, 1, 15),
            actual_duration=3.0,
        )
        destatus_rule_b(act, NEW_DD, OLD_DD)
        assert act.actual_start == date(2024, 1, 11)
        assert act.actual_finish == date(2024, 1, 15)

    def test_fixture_match(self):
        fx = _load_fixture()["rule_b"]
        act = Activity(
            act_id=fx["act_id"],
            actual_start=date.fromisoformat(fx["actual_start"]),
            actual_finish=date.fromisoformat(fx["actual_finish"]),
            actual_duration=fx["actual_duration"],
        )
        result = destatus_rule_b(act, NEW_DD, OLD_DD)
        assert result.actual_start is None
        assert result.actual_finish is None
        assert result.original_duration == fx["expected"]["original_duration"]
        assert result.percent_complete == fx["expected"]["percent_complete"]

    def test_missing_actual_duration_raises(self):
        act = Activity(
            act_id="ACT-B",
            actual_start=date(2024, 1, 11),
            actual_finish=date(2024, 1, 15),
        )
        with pytest.raises(ValueError, match="missing required field 'actual_duration'"):
            destatus_rule_b(act, NEW_DD, OLD_DD)

    def test_condition_not_met_raises(self):
        # AS before new_dd — not a Rule B activity
        act = Activity(
            act_id="ACT-B",
            actual_start=date(2024, 1, 5),
            actual_finish=date(2024, 1, 15),
            actual_duration=8.0,
        )
        with pytest.raises(ValueError, match="condition not met"):
            destatus_rule_b(act, NEW_DD, OLD_DD)

    def test_af_on_or_after_old_dd_not_rule_b(self):
        # AF must be strictly before old_dd
        act = Activity(
            act_id="ACT-B",
            actual_start=date(2024, 1, 11),
            actual_finish=OLD_DD,
            actual_duration=5.0,
        )
        with pytest.raises(ValueError, match="condition not met"):
            destatus_rule_b(act, NEW_DD, OLD_DD)


# ---------------------------------------------------------------------------
# CALC-007: Rule C — Do nothing (uses ES/EF, not AS/AF)
# ---------------------------------------------------------------------------

class TestRuleC:
    def test_basic_do_nothing(self):
        act = Activity(
            act_id="ACT-C",
            early_start=date(2024, 1, 22),
            early_finish=date(2024, 1, 26),
        )
        result = destatus_rule_c(act, NEW_DD, OLD_DD)
        assert result.early_start == date(2024, 1, 22)
        assert result.early_finish == date(2024, 1, 26)

    def test_returns_copy(self):
        act = Activity(
            act_id="ACT-C",
            early_start=date(2024, 1, 22),
            early_finish=date(2024, 1, 26),
        )
        result = destatus_rule_c(act, NEW_DD, OLD_DD)
        assert result is not act

    def test_fixture_match(self):
        fx = _load_fixture()["rule_c"]
        act = Activity(
            act_id=fx["act_id"],
            early_start=date.fromisoformat(fx["early_start"]),
            early_finish=date.fromisoformat(fx["early_finish"]),
        )
        result = destatus_rule_c(act, NEW_DD, OLD_DD)
        assert result.early_start == date.fromisoformat(fx["expected"]["early_start"])
        assert result.early_finish == date.fromisoformat(fx["expected"]["early_finish"])

    def test_missing_early_start_raises(self):
        act = Activity(act_id="ACT-C", early_finish=date(2024, 1, 26))
        with pytest.raises(ValueError, match="missing required field 'early_start'"):
            destatus_rule_c(act, NEW_DD, OLD_DD)

    def test_ef_not_after_old_dd_raises(self):
        # EF must be strictly after old_dd
        act = Activity(
            act_id="ACT-C",
            early_start=date(2024, 1, 22),
            early_finish=OLD_DD,
        )
        with pytest.raises(ValueError, match="condition not met"):
            destatus_rule_c(act, NEW_DD, OLD_DD)

    def test_uses_early_dates_not_actual(self):
        # Rule C checks ES/EF — actual dates should be irrelevant to the condition
        act = Activity(
            act_id="ACT-C",
            actual_start=date(2024, 1, 3),  # ignored for condition check
            actual_finish=date(2024, 1, 9),  # ignored for condition check
            early_start=date(2024, 1, 22),
            early_finish=date(2024, 1, 26),
        )
        result = destatus_rule_c(act, NEW_DD, OLD_DD)
        assert result.early_start == date(2024, 1, 22)


# ---------------------------------------------------------------------------
# CALC-008: Rule D — Remove AF, compute RD and PC (interpretation)
# ---------------------------------------------------------------------------

class TestRuleD:
    def test_basic_computation(self):
        # new_dd=Jan10(wd8), old_AF=Jan17(wd13). RD=5. WF-06: PC uses AD_before =
        # wd(AS 1/8 -> new_dd 1/10) = 2, NOT the supplied AD=3 -> PC = 2/7.
        act = Activity(
            act_id="ACT-D",
            actual_start=date(2024, 1, 8),
            actual_finish=date(2024, 1, 17),
            actual_duration=3.0,
        )
        result = destatus_rule_d(act, NEW_DD, OLD_DD, _TABLE, _CAL)
        assert result.actual_finish is None
        assert result.remaining_duration == 5.0
        assert math.isclose(result.percent_complete, 2.0 / 7.0)

    def test_fixture_match(self):
        fx = _load_fixture()["rule_d"]
        act = Activity(
            act_id=fx["act_id"],
            actual_start=date.fromisoformat(fx["actual_start"]),
            actual_finish=date.fromisoformat(fx["actual_finish"]),
            actual_duration=fx["actual_duration"],
        )
        result = destatus_rule_d(act, NEW_DD, OLD_DD, _TABLE, _CAL)
        assert result.actual_finish is None
        assert result.remaining_duration == fx["expected"]["remaining_duration"]
        assert math.isclose(
            result.percent_complete, fx["expected"]["percent_complete"]
        )

    def test_original_not_mutated(self):
        act = Activity(
            act_id="ACT-D",
            actual_start=date(2024, 1, 8),
            actual_finish=date(2024, 1, 17),
            actual_duration=3.0,
        )
        destatus_rule_d(act, NEW_DD, OLD_DD, _TABLE, _CAL)
        assert act.actual_finish == date(2024, 1, 17)

    def test_pc_between_0_and_1(self):
        act = Activity(
            act_id="ACT-D",
            actual_start=date(2024, 1, 8),
            actual_finish=date(2024, 1, 17),
            actual_duration=3.0,
        )
        result = destatus_rule_d(act, NEW_DD, OLD_DD, _TABLE, _CAL)
        assert 0.0 < result.percent_complete < 1.0

    def test_missing_actual_duration_raises(self):
        act = Activity(
            act_id="ACT-D",
            actual_start=date(2024, 1, 8),
            actual_finish=date(2024, 1, 17),
        )
        with pytest.raises(ValueError, match="missing required field 'actual_duration'"):
            destatus_rule_d(act, NEW_DD, OLD_DD, _TABLE, _CAL)

    def test_condition_not_met_as_after_new_dd_raises(self):
        # AS after new_dd — not Rule D
        act = Activity(
            act_id="ACT-D",
            actual_start=date(2024, 1, 12),
            actual_finish=date(2024, 1, 17),
            actual_duration=3.0,
        )
        with pytest.raises(ValueError, match="condition not met"):
            destatus_rule_d(act, NEW_DD, OLD_DD, _TABLE, _CAL)

    def test_condition_not_met_af_before_new_dd_raises(self):
        # AF before new_dd — not Rule D
        act = Activity(
            act_id="ACT-D",
            actual_start=date(2024, 1, 5),
            actual_finish=date(2024, 1, 8),
            actual_duration=2.0,
        )
        with pytest.raises(ValueError, match="condition not met"):
            destatus_rule_d(act, NEW_DD, OLD_DD, _TABLE, _CAL)

    def test_interpretation_note_in_docstring(self):
        # Confirm the interpretation note is documented in the function
        assert "implementation interpretation" in destatus_rule_d.__doc__
        assert "CALC-008" in destatus_rule_d.__doc__


# ---------------------------------------------------------------------------
# CALC-009: Rule E — Remove AS, OD=AD+RD, PC=0
# ---------------------------------------------------------------------------

class TestRuleE:
    def test_basic_reset(self):
        act = Activity(
            act_id="ACT-E",
            actual_start=date(2024, 1, 12),
            early_finish=date(2024, 1, 22),
            actual_duration=2.0,
            remaining_duration=6.0,
        )
        result = destatus_rule_e(act, NEW_DD, OLD_DD)
        assert result.actual_start is None
        assert result.original_duration == 8.0
        assert result.percent_complete == 0.0

    def test_fixture_match(self):
        fx = _load_fixture()["rule_e"]
        act = Activity(
            act_id=fx["act_id"],
            actual_start=date.fromisoformat(fx["actual_start"]),
            early_finish=date.fromisoformat(fx["early_finish"]),
            actual_duration=fx["actual_duration"],
            remaining_duration=fx["remaining_duration"],
        )
        result = destatus_rule_e(act, NEW_DD, OLD_DD)
        assert result.actual_start is None
        assert result.original_duration == fx["expected"]["original_duration"]
        assert result.percent_complete == fx["expected"]["percent_complete"]

    def test_original_not_mutated(self):
        act = Activity(
            act_id="ACT-E",
            actual_start=date(2024, 1, 12),
            early_finish=date(2024, 1, 22),
            actual_duration=2.0,
            remaining_duration=6.0,
        )
        destatus_rule_e(act, NEW_DD, OLD_DD)
        assert act.actual_start == date(2024, 1, 12)

    def test_missing_remaining_duration_raises(self):
        act = Activity(
            act_id="ACT-E",
            actual_start=date(2024, 1, 12),
            early_finish=date(2024, 1, 22),
            actual_duration=2.0,
        )
        with pytest.raises(ValueError, match="missing required field 'remaining_duration'"):
            destatus_rule_e(act, NEW_DD, OLD_DD)

    def test_as_before_new_dd_not_rule_e(self):
        # AS must be after new_dd for Rule E
        act = Activity(
            act_id="ACT-E",
            actual_start=date(2024, 1, 5),
            early_finish=date(2024, 1, 22),
            actual_duration=2.0,
            remaining_duration=6.0,
        )
        with pytest.raises(ValueError, match="condition not met"):
            destatus_rule_e(act, NEW_DD, OLD_DD)

    def test_as_after_old_dd_not_rule_e(self):
        # AS must be before old_dd for Rule E
        act = Activity(
            act_id="ACT-E",
            actual_start=date(2024, 1, 20),
            early_finish=date(2024, 1, 26),
            actual_duration=2.0,
            remaining_duration=4.0,
        )
        with pytest.raises(ValueError, match="condition not met"):
            destatus_rule_e(act, NEW_DD, OLD_DD)

    def test_ef_not_after_old_dd_not_rule_e(self):
        act = Activity(
            act_id="ACT-E",
            actual_start=date(2024, 1, 12),
            early_finish=OLD_DD,
            actual_duration=2.0,
            remaining_duration=4.0,
        )
        with pytest.raises(ValueError, match="condition not met"):
            destatus_rule_e(act, NEW_DD, OLD_DD)


# ---------------------------------------------------------------------------
# CALC-010: Rule F — Compute RD and PC from new_dd to old EF
# ---------------------------------------------------------------------------

class TestRuleF:
    def test_basic_computation(self):
        # new_dd=Jan10(wd8), old_EF=Jan24(wd18). RD=10. AD=5. PC=5/15=0.333...
        act = Activity(
            act_id="ACT-F",
            actual_start=date(2024, 1, 3),
            early_finish=date(2024, 1, 24),
            actual_duration=5.0,
        )
        result = destatus_rule_f(act, NEW_DD, OLD_DD, _TABLE, _CAL)
        assert result.remaining_duration == 10.0
        assert math.isclose(result.percent_complete, 5.0 / 15.0)

    def test_fixture_match(self):
        fx = _load_fixture()["rule_f"]
        act = Activity(
            act_id=fx["act_id"],
            actual_start=date.fromisoformat(fx["actual_start"]),
            early_finish=date.fromisoformat(fx["early_finish"]),
            actual_duration=fx["actual_duration"],
        )
        result = destatus_rule_f(act, NEW_DD, OLD_DD, _TABLE, _CAL)
        assert result.remaining_duration == fx["expected"]["remaining_duration"]
        assert math.isclose(
            result.percent_complete, fx["expected"]["percent_complete"]
        )

    def test_original_not_mutated(self):
        act = Activity(
            act_id="ACT-F",
            actual_start=date(2024, 1, 3),
            early_finish=date(2024, 1, 24),
            actual_duration=5.0,
        )
        original_rd = act.remaining_duration
        destatus_rule_f(act, NEW_DD, OLD_DD, _TABLE, _CAL)
        assert act.remaining_duration == original_rd

    def test_pc_between_0_and_1(self):
        act = Activity(
            act_id="ACT-F",
            actual_start=date(2024, 1, 3),
            early_finish=date(2024, 1, 24),
            actual_duration=5.0,
        )
        result = destatus_rule_f(act, NEW_DD, OLD_DD, _TABLE, _CAL)
        assert 0.0 < result.percent_complete < 1.0

    def test_condition_as_not_before_new_dd_raises(self):
        act = Activity(
            act_id="ACT-F",
            actual_start=date(2024, 1, 12),
            early_finish=date(2024, 1, 24),
            actual_duration=5.0,
        )
        with pytest.raises(ValueError, match="condition not met"):
            destatus_rule_f(act, NEW_DD, OLD_DD, _TABLE, _CAL)

    def test_condition_ef_not_after_old_dd_raises(self):
        act = Activity(
            act_id="ACT-F",
            actual_start=date(2024, 1, 3),
            early_finish=date(2024, 1, 15),
            actual_duration=5.0,
        )
        with pytest.raises(ValueError, match="condition not met"):
            destatus_rule_f(act, NEW_DD, OLD_DD, _TABLE, _CAL)

    def test_missing_early_finish_raises(self):
        act = Activity(
            act_id="ACT-F",
            actual_start=date(2024, 1, 3),
            actual_duration=5.0,
        )
        with pytest.raises(ValueError, match="missing required field 'early_finish'"):
            destatus_rule_f(act, NEW_DD, OLD_DD, _TABLE, _CAL)

    def test_interpretation_note_in_docstring(self):
        assert "implementation interpretation" in destatus_rule_f.__doc__


# ---------------------------------------------------------------------------
# Non-workday finish date handling (review fix — Rules D and F)
# ---------------------------------------------------------------------------
#
# Workday reference for Jan 2024 (Mon-Fri calendar):
#   Jan 10 (Wed) = wd8  <- NEW_DD
#   Jan 17 (Wed) = wd13 <- OLD_DD
#   Jan 19 (Fri) = wd15
#   Jan 20 (Sat) = non-workday  -> adjusted to Jan 19 (Fri, wd15) for finish dates
#   Jan 21 (Sun) = non-workday  -> adjusted to Jan 19 (Fri, wd15) for finish dates
#
# Rule D: RD = wd(adjusted_AF) - wd(new_dd) = 15 - 8 = 7; AD_before = wd(AS 1/8 ->
#   new_dd 1/10) = 2; PC = 2/9 (WF-06 — PC uses the pre-new_dd AD, not supplied AD=3)
# Rule F: RD = wd(adjusted_EF) - wd(new_dd) = 15 - 8 = 7; AD_before = wd(AS 1/3 ->
#   new_dd 1/10) = 5 (== supplied AD=5, so PC=5/12 is unchanged by WF-06)

class TestNonWorkdayFinishDates:
    """
    Verify that Rules D and F correctly apply the CALC-001 finish-date adjustment
    (retreat to previous workday) when Actual Finish or Early Finish falls on a
    non-workday. Source: CPW-P6 Manual pp. 41-42.
    """

    # --- Rule D: Saturday Actual Finish ---

    def test_rule_d_saturday_af_retreats_to_friday(self):
        # AF = Jan 20 (Sat) -> adjusted to Jan 19 (Fri, wd15). RD=7, AD_before=2, PC=2/9 (WF-06)
        act = Activity(
            act_id="ACT-D-SAT",
            actual_start=date(2024, 1, 8),
            actual_finish=date(2024, 1, 20),  # Saturday
            actual_duration=3.0,
        )
        result = destatus_rule_d(act, NEW_DD, OLD_DD, _TABLE, _CAL)
        assert result.actual_finish is None
        assert result.remaining_duration == 7.0
        assert math.isclose(result.percent_complete, 2.0 / 9.0)

    def test_rule_d_saturday_rd_equals_friday_adjustment(self):
        # Saturday AF and Friday AF (one day earlier) produce the same RD
        act_sat = Activity(
            act_id="ACT-D-SAT",
            actual_start=date(2024, 1, 8),
            actual_finish=date(2024, 1, 20),  # Saturday -> adjusts to Jan 19 (Fri)
            actual_duration=3.0,
        )
        act_fri = Activity(
            act_id="ACT-D-FRI",
            actual_start=date(2024, 1, 8),
            actual_finish=date(2024, 1, 19),  # Friday (the adjusted date directly)
            actual_duration=3.0,
        )
        result_sat = destatus_rule_d(act_sat, NEW_DD, OLD_DD, _TABLE, _CAL)
        result_fri = destatus_rule_d(act_fri, NEW_DD, OLD_DD, _TABLE, _CAL)
        assert result_sat.remaining_duration == result_fri.remaining_duration
        assert math.isclose(result_sat.percent_complete, result_fri.percent_complete)

    def test_rule_d_sunday_af_retreats_to_friday(self):
        # AF = Jan 21 (Sun) -> adjusted to Jan 19 (Fri, wd15). Same result as Saturday.
        act = Activity(
            act_id="ACT-D-SUN",
            actual_start=date(2024, 1, 8),
            actual_finish=date(2024, 1, 21),  # Sunday
            actual_duration=3.0,
        )
        result = destatus_rule_d(act, NEW_DD, OLD_DD, _TABLE, _CAL)
        assert result.actual_finish is None
        assert result.remaining_duration == 7.0
        assert math.isclose(result.percent_complete, 2.0 / 9.0)

    # --- Rule F: Saturday Early Finish ---

    def test_rule_f_saturday_ef_retreats_to_friday(self):
        # EF = Jan 20 (Sat) -> adjusted to Jan 19 (Fri, wd15). RD=7, AD=5, PC=5/12
        act = Activity(
            act_id="ACT-F-SAT",
            actual_start=date(2024, 1, 3),
            early_finish=date(2024, 1, 20),  # Saturday — after old_dd Jan 17
            actual_duration=5.0,
        )
        result = destatus_rule_f(act, NEW_DD, OLD_DD, _TABLE, _CAL)
        assert result.remaining_duration == 7.0
        assert math.isclose(result.percent_complete, 5.0 / 12.0)

    def test_rule_f_saturday_rd_equals_friday_adjustment(self):
        # Saturday EF and Friday EF produce the same RD
        act_sat = Activity(
            act_id="ACT-F-SAT",
            actual_start=date(2024, 1, 3),
            early_finish=date(2024, 1, 20),  # Saturday -> adjusts to Jan 19 (Fri)
            actual_duration=5.0,
        )
        act_fri = Activity(
            act_id="ACT-F-FRI",
            actual_start=date(2024, 1, 3),
            early_finish=date(2024, 1, 19),  # Friday (the adjusted date directly)
            actual_duration=5.0,
        )
        result_sat = destatus_rule_f(act_sat, NEW_DD, OLD_DD, _TABLE, _CAL)
        result_fri = destatus_rule_f(act_fri, NEW_DD, OLD_DD, _TABLE, _CAL)
        assert result_sat.remaining_duration == result_fri.remaining_duration
        assert math.isclose(result_sat.percent_complete, result_fri.percent_complete)

    def test_rule_f_sunday_ef_retreats_to_friday(self):
        # EF = Jan 21 (Sun) -> adjusted to Jan 19 (Fri, wd15). Same result as Saturday.
        act = Activity(
            act_id="ACT-F-SUN",
            actual_start=date(2024, 1, 3),
            early_finish=date(2024, 1, 21),  # Sunday — after old_dd Jan 17
            actual_duration=5.0,
        )
        result = destatus_rule_f(act, NEW_DD, OLD_DD, _TABLE, _CAL)
        assert result.remaining_duration == 7.0
        assert math.isclose(result.percent_complete, 5.0 / 12.0)


# ---------------------------------------------------------------------------
# Cross-rule immutability (paranoia check)
# ---------------------------------------------------------------------------

class TestActivityImmutability:
    """Confirm that no rule mutates the input Activity."""

    def _make_full_activity(self, act_id: str) -> Activity:
        return Activity(
            act_id=act_id,
            actual_start=date(2024, 1, 3),
            actual_finish=date(2024, 1, 5),
            early_start=date(2024, 1, 22),
            early_finish=date(2024, 1, 26),
            original_duration=10.0,
            actual_duration=3.0,
            remaining_duration=6.0,
            percent_complete=0.5,
        )

    def test_rule_a_no_mutation(self):
        act = Activity(
            act_id="X", actual_start=date(2024, 1, 3), actual_finish=date(2024, 1, 5)
        )
        before = (act.actual_start, act.actual_finish)
        destatus_rule_a(act, NEW_DD, OLD_DD)
        assert (act.actual_start, act.actual_finish) == before

    def test_rule_b_no_mutation(self):
        act = Activity(
            act_id="X",
            actual_start=date(2024, 1, 11),
            actual_finish=date(2024, 1, 15),
            actual_duration=3.0,
        )
        before = (act.actual_start, act.actual_finish, act.original_duration)
        destatus_rule_b(act, NEW_DD, OLD_DD)
        assert (act.actual_start, act.actual_finish, act.original_duration) == before

    def test_rule_c_no_mutation(self):
        act = Activity(
            act_id="X", early_start=date(2024, 1, 22), early_finish=date(2024, 1, 26)
        )
        before = (act.early_start, act.early_finish)
        destatus_rule_c(act, NEW_DD, OLD_DD)
        assert (act.early_start, act.early_finish) == before
