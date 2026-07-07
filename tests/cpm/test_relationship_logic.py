"""
Tests for CALC-004: Retained Logic Driving Relationship.
Source: src/mip39/relationship_logic.py

All fixtures are synthetic. No proprietary data.

Test predecessor (shared across most tests):
  pred_es = Jan 8, 2024 (Mon, wd6)
  pred_ef = Jan 12, 2024 (Fri, wd10)
  OD = 5 workdays

Test successor (for driving tests):
  succ_es = Jan 15, 2024 (Mon, wd11)
  succ_ef = Jan 19, 2024 (Fri, wd15)
  OD = 5 workdays
"""

import os, sys
SRC = os.path.join(os.path.dirname(__file__), "..", "..", "src")
sys.path.insert(0, os.path.abspath(SRC))

import json
import pytest
from datetime import date
from pathlib import Path

from scheduleiq.cpm.models import Activity, Relationship, Calendar  # noqa: E402
from scheduleiq.cpm.calendar_ops import build_workday_table  # noqa: E402
from scheduleiq.cpm.relationship_logic import (  # noqa: E402
    compute_relationship_constraint,
    is_driving_relationship,
    find_driving_relationship,
)

FIXTURES = Path(__file__).parent / "fixtures"

# ---------------------------------------------------------------------------
# Shared test state
# ---------------------------------------------------------------------------

_CAL = Calendar(name="Standard")
_TABLE = build_workday_table(_CAL, date(2024, 1, 1), date(2024, 1, 31))

_PRED_ES = date(2024, 1, 8)   # Mon wd6
_PRED_EF = date(2024, 1, 12)  # Fri wd10
_SUCC_ES = date(2024, 1, 15)  # Mon wd11
_SUCC_EF = date(2024, 1, 19)  # Fri wd15


def _make_pred(act_id: str = "A1000",
               es: date = _PRED_ES,
               ef: date = _PRED_EF) -> Activity:
    return Activity(act_id=act_id, early_start=es, early_finish=ef)


def _make_succ(act_id: str = "A2000",
               es: date = _SUCC_ES,
               ef: date = _SUCC_EF) -> Activity:
    return Activity(act_id=act_id, early_start=es, early_finish=ef)


def _make_rel(pred_id: str = "A1000",
              succ_id: str = "A2000",
              rel_type: str = "FS",
              lag: float = 0.0) -> Relationship:
    return Relationship(pred_id=pred_id, succ_id=succ_id, rel_type=rel_type, lag=lag)


# ---------------------------------------------------------------------------
# CALC-004: compute_relationship_constraint — constraint type and date
# ---------------------------------------------------------------------------

class TestComputeRelationshipConstraintType:
    def test_fs_returns_es_constraint(self):
        ct, _ = compute_relationship_constraint(
            "FS", _PRED_ES, _PRED_EF, 0, _TABLE, _CAL
        )
        assert ct == "ES"

    def test_ss_returns_es_constraint(self):
        ct, _ = compute_relationship_constraint(
            "SS", _PRED_ES, _PRED_EF, 0, _TABLE, _CAL
        )
        assert ct == "ES"

    def test_ff_returns_ef_constraint(self):
        ct, _ = compute_relationship_constraint(
            "FF", _PRED_ES, _PRED_EF, 0, _TABLE, _CAL
        )
        assert ct == "EF"

    def test_sf_returns_ef_constraint(self):
        ct, _ = compute_relationship_constraint(
            "SF", _PRED_ES, _PRED_EF, 0, _TABLE, _CAL
        )
        assert ct == "EF"

    def test_invalid_rel_type_raises(self):
        with pytest.raises(ValueError, match="invalid rel_type"):
            compute_relationship_constraint(
                "XY", _PRED_ES, _PRED_EF, 0, _TABLE, _CAL
            )

    def test_empty_rel_type_raises(self):
        with pytest.raises(ValueError, match="invalid rel_type"):
            compute_relationship_constraint(
                "", _PRED_ES, _PRED_EF, 0, _TABLE, _CAL
            )


class TestComputeRelationshipConstraintFS:
    def test_fs_lag_zero_constrained_es_equals_pred_ef(self):
        # FS lag=0: constrained_es = pred_ef = Jan 12 (wd10)
        _, cd = compute_relationship_constraint("FS", _PRED_ES, _PRED_EF, 0, _TABLE, _CAL)
        assert cd == date(2024, 1, 12)

    def test_fs_lag_one_crosses_weekend(self):
        # FS lag=1: pred_ef Jan 12 (wd10) + 1 = wd11 = Jan 15 (Mon, crosses weekend)
        _, cd = compute_relationship_constraint("FS", _PRED_ES, _PRED_EF, 1, _TABLE, _CAL)
        assert cd == date(2024, 1, 15)

    def test_fs_lag_two(self):
        # FS lag=2: pred_ef Jan 12 (wd10) + 2 = wd12 = Jan 16
        _, cd = compute_relationship_constraint("FS", _PRED_ES, _PRED_EF, 2, _TABLE, _CAL)
        assert cd == date(2024, 1, 16)

    def test_fs_negative_lag_lead(self):
        # FS lag=-1 (lead): pred_ef Jan 12 (wd10) - 1 = wd9 = Jan 11
        _, cd = compute_relationship_constraint("FS", _PRED_ES, _PRED_EF, -1, _TABLE, _CAL)
        assert cd == date(2024, 1, 11)

    def test_fs_uses_pred_ef_not_pred_es(self):
        # FS must anchor on pred_ef; verify by comparing result with pred_ef anchor vs pred_es anchor
        _, cd_fs = compute_relationship_constraint("FS", _PRED_ES, _PRED_EF, 0, _TABLE, _CAL)
        assert cd_fs == _PRED_EF  # anchored on pred_ef


class TestComputeRelationshipConstraintSS:
    def test_ss_lag_zero_constrained_es_equals_pred_es(self):
        # SS lag=0: constrained_es = pred_es = Jan 8 (wd6)
        _, cd = compute_relationship_constraint("SS", _PRED_ES, _PRED_EF, 0, _TABLE, _CAL)
        assert cd == date(2024, 1, 8)

    def test_ss_lag_two(self):
        # SS lag=2: pred_es Jan 8 (wd6) + 2 = wd8 = Jan 10
        _, cd = compute_relationship_constraint("SS", _PRED_ES, _PRED_EF, 2, _TABLE, _CAL)
        assert cd == date(2024, 1, 10)

    def test_ss_uses_pred_es_not_pred_ef(self):
        # SS must anchor on pred_es; pred_es ≠ pred_ef so results differ
        _, cd_ss = compute_relationship_constraint("SS", _PRED_ES, _PRED_EF, 0, _TABLE, _CAL)
        assert cd_ss == _PRED_ES  # anchored on pred_es
        assert cd_ss != _PRED_EF


class TestComputeRelationshipConstraintFF:
    def test_ff_lag_zero_constrained_ef_equals_pred_ef(self):
        # FF lag=0: constrained_ef = pred_ef = Jan 12 (wd10)
        _, cd = compute_relationship_constraint("FF", _PRED_ES, _PRED_EF, 0, _TABLE, _CAL)
        assert cd == date(2024, 1, 12)

    def test_ff_lag_two(self):
        # FF lag=2: pred_ef Jan 12 (wd10) + 2 = wd12 = Jan 16
        _, cd = compute_relationship_constraint("FF", _PRED_ES, _PRED_EF, 2, _TABLE, _CAL)
        assert cd == date(2024, 1, 16)

    def test_ff_lag_three(self):
        # FF lag=3: pred_ef Jan 12 (wd10) + 3 = wd13 = Jan 17
        _, cd = compute_relationship_constraint("FF", _PRED_ES, _PRED_EF, 3, _TABLE, _CAL)
        assert cd == date(2024, 1, 17)


class TestComputeRelationshipConstraintSF:
    def test_sf_lag_zero_constrained_ef_equals_pred_es(self):
        # SF lag=0: constrained_ef = pred_es = Jan 8 (wd6)
        _, cd = compute_relationship_constraint("SF", _PRED_ES, _PRED_EF, 0, _TABLE, _CAL)
        assert cd == date(2024, 1, 8)

    def test_sf_lag_five(self):
        # SF lag=5: pred_es Jan 8 (wd6) + 5 = wd11 = Jan 15
        _, cd = compute_relationship_constraint("SF", _PRED_ES, _PRED_EF, 5, _TABLE, _CAL)
        assert cd == date(2024, 1, 15)

    def test_sf_lag_seven(self):
        # SF lag=7: pred_es Jan 8 (wd6) + 7 = wd13 = Jan 17
        _, cd = compute_relationship_constraint("SF", _PRED_ES, _PRED_EF, 7, _TABLE, _CAL)
        assert cd == date(2024, 1, 17)


class TestComputeRelationshipConstraintNonWorkday:
    def test_fs_saturday_pred_ef_retreats_before_lag(self):
        # pred_ef = Sat Jan 6 (non-workday, finish-type) → retreats to Jan 5 (wd5)
        # FS lag=1: wd5 + 1 = wd6 = Jan 8
        _, cd = compute_relationship_constraint(
            "FS", date(2024, 1, 1), date(2024, 1, 6), 1, _TABLE, _CAL
        )
        assert cd == date(2024, 1, 8)

    def test_ss_saturday_pred_es_advances_before_lag(self):
        # pred_es = Sat Jan 6 (non-workday, start-type) → advances to Jan 8 (wd6)
        # SS lag=1: wd6 + 1 = wd7 = Jan 9
        _, cd = compute_relationship_constraint(
            "SS", date(2024, 1, 6), date(2024, 1, 12), 1, _TABLE, _CAL
        )
        assert cd == date(2024, 1, 9)


# ---------------------------------------------------------------------------
# CALC-004: compute_relationship_constraint — fixture-driven
# ---------------------------------------------------------------------------

class TestComputeRelationshipConstraintFixtures:
    def setup_method(self):
        with open(FIXTURES / "relationship_scenarios.json") as f:
            self.fixture = json.load(f)
        start = date.fromisoformat(self.fixture["table_start"])
        end = date.fromisoformat(self.fixture["table_end"])
        self.table = build_workday_table(Calendar(name="Standard"), start, end)
        self.cal = Calendar(name="Standard")

    def test_all_constraint_scenarios(self):
        for scenario in self.fixture["relationship_constraint_scenarios"]:
            pred_es = date.fromisoformat(scenario["pred_es"])
            pred_ef = date.fromisoformat(scenario["pred_ef"])
            rel_type = scenario["rel_type"]
            lag = scenario["lag_workdays"]
            expected_ct = scenario["expected_constraint_type"]
            expected_cd = date.fromisoformat(scenario["expected_constrained_date"])

            ct, cd = compute_relationship_constraint(
                rel_type, pred_es, pred_ef, lag, self.table, self.cal
            )
            assert ct == expected_ct, (
                f"Failed constraint type for '{scenario['_note']}': "
                f"expected {expected_ct!r}, got {ct!r}"
            )
            assert cd == expected_cd, (
                f"Failed constrained date for '{scenario['_note']}': "
                f"expected {expected_cd}, got {cd}"
            )


# ---------------------------------------------------------------------------
# CALC-004: is_driving_relationship
# ---------------------------------------------------------------------------

class TestIsDrivingRelationship:
    def test_fs_lag_one_is_driving(self):
        # FS lag=1: constrained_es = Jan 15 == succ_es (Jan 15) → driving
        assert is_driving_relationship(
            "FS", _PRED_ES, _PRED_EF, _SUCC_ES, _SUCC_EF, 1, _TABLE, _CAL
        )

    def test_fs_lag_zero_not_driving_when_succ_later(self):
        # FS lag=0: constrained_es = Jan 12 ≠ succ_es (Jan 15) → not driving
        assert not is_driving_relationship(
            "FS", _PRED_ES, _PRED_EF, _SUCC_ES, _SUCC_EF, 0, _TABLE, _CAL
        )

    def test_ss_lag_five_is_driving(self):
        # SS lag=5: constrained_es = Jan 8 + 5 = Jan 15 == succ_es → driving
        assert is_driving_relationship(
            "SS", _PRED_ES, _PRED_EF, _SUCC_ES, _SUCC_EF, 5, _TABLE, _CAL
        )

    def test_ss_lag_zero_not_driving(self):
        # SS lag=0: constrained_es = Jan 8 ≠ succ_es (Jan 15) → not driving
        assert not is_driving_relationship(
            "SS", _PRED_ES, _PRED_EF, _SUCC_ES, _SUCC_EF, 0, _TABLE, _CAL
        )

    def test_ff_driving_when_constrained_ef_matches(self):
        # FF lag=3: constrained_ef = Jan 17; succ_ef=Jan 17 → driving
        succ_ef_jan17 = date(2024, 1, 17)
        assert is_driving_relationship(
            "FF", _PRED_ES, _PRED_EF, _SUCC_ES, succ_ef_jan17, 3, _TABLE, _CAL
        )

    def test_ff_not_driving_when_constrained_ef_earlier(self):
        # FF lag=0: constrained_ef = Jan 12 ≠ succ_ef (Jan 19) → not driving
        assert not is_driving_relationship(
            "FF", _PRED_ES, _PRED_EF, _SUCC_ES, _SUCC_EF, 0, _TABLE, _CAL
        )

    def test_sf_driving_when_constrained_ef_matches(self):
        # SF lag=7: constrained_ef = Jan 8 + 7 = Jan 17; succ_ef=Jan 17 → driving
        succ_ef_jan17 = date(2024, 1, 17)
        assert is_driving_relationship(
            "SF", _PRED_ES, _PRED_EF, _SUCC_ES, succ_ef_jan17, 7, _TABLE, _CAL
        )

    def test_sf_not_driving_when_constrained_ef_different(self):
        # SF lag=0: constrained_ef = Jan 8 ≠ succ_ef (Jan 19) → not driving
        assert not is_driving_relationship(
            "SF", _PRED_ES, _PRED_EF, _SUCC_ES, _SUCC_EF, 0, _TABLE, _CAL
        )

    def test_fs_and_ss_both_can_be_driving_independently(self):
        # FS lag=1 is driving for succ_es=Jan 15; SS lag=5 also for succ_es=Jan 15
        assert is_driving_relationship("FS", _PRED_ES, _PRED_EF, _SUCC_ES, _SUCC_EF, 1, _TABLE, _CAL)
        assert is_driving_relationship("SS", _PRED_ES, _PRED_EF, _SUCC_ES, _SUCC_EF, 5, _TABLE, _CAL)


# ---------------------------------------------------------------------------
# CALC-004: is_driving_relationship — fixture-driven
# ---------------------------------------------------------------------------

class TestIsDrivingRelationshipFixtures:
    def setup_method(self):
        with open(FIXTURES / "relationship_scenarios.json") as f:
            self.fixture = json.load(f)
        start = date.fromisoformat(self.fixture["table_start"])
        end = date.fromisoformat(self.fixture["table_end"])
        self.table = build_workday_table(Calendar(name="Standard"), start, end)
        self.cal = Calendar(name="Standard")

    def test_all_driving_scenarios(self):
        for scenario in self.fixture["driving_relationship_scenarios"]:
            pred_es = date.fromisoformat(scenario["pred_es"])
            pred_ef = date.fromisoformat(scenario["pred_ef"])
            rel_type = scenario["rel_type"]
            lag = scenario["lag_workdays"]
            succ_es = date.fromisoformat(scenario["succ_es"])
            succ_ef = date.fromisoformat(scenario["succ_ef"])
            expected = scenario["expected_driving"]

            result = is_driving_relationship(
                rel_type, pred_es, pred_ef, succ_es, succ_ef, lag, self.table, self.cal
            )
            assert result == expected, (
                f"Failed for '{scenario['_note']}': "
                f"expected driving={expected}, got {result}"
            )


# ---------------------------------------------------------------------------
# CALC-004: find_driving_relationship
# ---------------------------------------------------------------------------

class TestFindDrivingRelationship:
    """
    Network setup:
      pred_a: ES=Jan 1,  EF=Jan 12 — FS lag=1 → constrained_es = Jan 15 (DRIVING)
      pred_b: ES=Jan 8,  EF=Jan 10 — FS lag=0 → constrained_es = Jan 10 (not driving)
      pred_c: ES=Jan 8,  EF=Jan 12 — SS lag=5 → constrained_es = Jan 15 (CO-DRIVING)
      succ: ES=Jan 15, EF=Jan 19
    """

    def setup_method(self):
        self.pred_a = Activity(
            act_id="A1000",
            early_start=date(2024, 1, 1),
            early_finish=date(2024, 1, 12),
        )
        self.pred_b = Activity(
            act_id="A1010",
            early_start=date(2024, 1, 8),
            early_finish=date(2024, 1, 10),
        )
        self.pred_c = Activity(
            act_id="A1020",
            early_start=date(2024, 1, 8),
            early_finish=date(2024, 1, 12),
        )
        # rel_a: FS lag=1 → constrained_es = Jan 12 + 1 = Jan 15 (driving)
        self.rel_a = Relationship("A1000", "A2000", "FS", 1.0)
        # rel_b: FS lag=0 → constrained_es = Jan 10 (not driving, Jan 10 < Jan 15)
        self.rel_b = Relationship("A1010", "A2000", "FS", 0.0)
        # rel_c: SS lag=5 → constrained_es = Jan 8 + 5 = Jan 15 (co-driving)
        self.rel_c = Relationship("A1020", "A2000", "SS", 5.0)

    def test_single_driving_predecessor(self):
        preds = [(self.pred_a, self.rel_a)]
        driving = find_driving_relationship(preds, _SUCC_ES, _SUCC_EF, _TABLE, _CAL)
        assert len(driving) == 1
        assert driving[0][0].act_id == "A1000"

    def test_non_driving_predecessor_excluded(self):
        preds = [(self.pred_b, self.rel_b)]
        driving = find_driving_relationship(preds, _SUCC_ES, _SUCC_EF, _TABLE, _CAL)
        assert driving == []

    def test_driving_identified_among_multiple_predecessors(self):
        preds = [
            (self.pred_a, self.rel_a),
            (self.pred_b, self.rel_b),
        ]
        driving = find_driving_relationship(preds, _SUCC_ES, _SUCC_EF, _TABLE, _CAL)
        assert len(driving) == 1
        assert driving[0][0].act_id == "A1000"

    def test_co_driving_predecessors_both_returned(self):
        # pred_a (FS lag=1) and pred_c (SS lag=5) both constrain Jan 15 → co-driving
        preds = [
            (self.pred_a, self.rel_a),
            (self.pred_b, self.rel_b),
            (self.pred_c, self.rel_c),
        ]
        driving = find_driving_relationship(preds, _SUCC_ES, _SUCC_EF, _TABLE, _CAL)
        assert len(driving) == 2
        driving_ids = {p.act_id for p, _ in driving}
        assert "A1000" in driving_ids
        assert "A1020" in driving_ids
        assert "A1010" not in driving_ids

    def test_empty_predecessors_returns_empty(self):
        driving = find_driving_relationship([], _SUCC_ES, _SUCC_EF, _TABLE, _CAL)
        assert driving == []

    def test_predecessor_missing_early_start_raises(self):
        bad_pred = Activity(act_id="X", early_start=None, early_finish=date(2024, 1, 12))
        rel = Relationship("X", "A2000", "FS", 1.0)
        with pytest.raises(ValueError, match="early_start=None"):
            find_driving_relationship([(bad_pred, rel)], _SUCC_ES, _SUCC_EF, _TABLE, _CAL)

    def test_predecessor_missing_early_finish_raises(self):
        bad_pred = Activity(act_id="X", early_start=date(2024, 1, 8), early_finish=None)
        rel = Relationship("X", "A2000", "FS", 1.0)
        with pytest.raises(ValueError, match="early_finish=None"):
            find_driving_relationship([(bad_pred, rel)], _SUCC_ES, _SUCC_EF, _TABLE, _CAL)

    def test_returns_original_activity_and_relationship_objects(self):
        # Verify the returned tuples are the same objects passed in
        preds = [(self.pred_a, self.rel_a)]
        driving = find_driving_relationship(preds, _SUCC_ES, _SUCC_EF, _TABLE, _CAL)
        assert driving[0][0] is self.pred_a
        assert driving[0][1] is self.rel_a

    def test_ff_driving_predecessor(self):
        # FF lag=3: constrained_ef = Jan 12 + 3 = Jan 17
        pred = Activity(act_id="B1000", early_start=_PRED_ES, early_finish=_PRED_EF)
        rel = Relationship("B1000", "A2000", "FF", 3.0)
        succ_ef_jan17 = date(2024, 1, 17)
        driving = find_driving_relationship(
            [(pred, rel)], _SUCC_ES, succ_ef_jan17, _TABLE, _CAL
        )
        assert len(driving) == 1
        assert driving[0][0].act_id == "B1000"
