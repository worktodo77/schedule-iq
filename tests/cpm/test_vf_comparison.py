"""
Tests for INFRA-016: Phase 7 Machine-Readable Comparison Artifacts.

Covers test categories:
  6. Warning comparison
  7. Float comparison
  8. Longest-path comparison
"""

import os, sys
SRC = os.path.join(os.path.dirname(__file__), "..", "..", "src")
sys.path.insert(0, os.path.abspath(SRC))

import pytest
from scheduleiq.cpm.benchmark.comparison import (  # noqa: E402
    ConventionDiff,
    DateDiff,
    FloatDiff,
    NormalizationDiff,
    PathDiff,
    WarningDiff,
    compare_date_results,
    compare_float_results,
    compare_paths,
    compare_warning_codes,
)


# ---------------------------------------------------------------------------
# Category 7: Float comparison — compare_float_results
# ---------------------------------------------------------------------------

class TestCompareFloatResults:
    def _make_expected(self, **kwargs) -> dict:
        defaults = {"total_float": 0, "free_float": 0}
        defaults.update(kwargs)
        return {"A": defaults}

    def _make_actual(self, **kwargs) -> dict:
        defaults = {"total_float": 0, "free_float": 0}
        defaults.update(kwargs)
        return {"A": defaults}

    def test_no_diff_when_equal(self):
        exp = {"A": {"total_float": 0, "free_float": 0}}
        act = {"A": {"total_float": 0, "free_float": 0}}
        assert compare_float_results(exp, act) == []

    def test_total_float_diff_detected(self):
        exp = {"A": {"total_float": 0, "free_float": 0}}
        act = {"A": {"total_float": 2, "free_float": 0}}
        diffs = compare_float_results(exp, act)
        assert len(diffs) == 1
        assert diffs[0].field == "total_float"
        assert diffs[0].expected == 0
        assert diffs[0].actual == 2
        assert diffs[0].delta == 2

    def test_free_float_diff_detected(self):
        exp = {"A": {"total_float": 0, "free_float": 0}}
        act = {"A": {"total_float": 0, "free_float": 3}}
        diffs = compare_float_results(exp, act)
        assert len(diffs) == 1
        assert diffs[0].field == "free_float"
        assert diffs[0].delta == 3

    def test_both_floats_diff_produces_two_diffs(self):
        exp = {"A": {"total_float": 0, "free_float": 0}}
        act = {"A": {"total_float": 5, "free_float": 2}}
        diffs = compare_float_results(exp, act)
        assert len(diffs) == 2

    def test_negative_delta(self):
        exp = {"A": {"total_float": 5, "free_float": 0}}
        act = {"A": {"total_float": 3, "free_float": 0}}
        diffs = compare_float_results(exp, act)
        assert diffs[0].delta == -2

    def test_multiple_activities_only_diverging_reported(self):
        exp = {
            "A": {"total_float": 0, "free_float": 0},
            "B": {"total_float": 3, "free_float": 3},
        }
        act = {
            "A": {"total_float": 0, "free_float": 0},
            "B": {"total_float": 0, "free_float": 0},  # B diverges
        }
        diffs = compare_float_results(exp, act)
        activity_ids = {d.activity_id for d in diffs}
        assert activity_ids == {"B"}

    def test_missing_activity_in_actual_skipped(self):
        exp = {
            "A": {"total_float": 0, "free_float": 0},
            "B": {"total_float": 0, "free_float": 0},
        }
        act = {"A": {"total_float": 0, "free_float": 0}}
        diffs = compare_float_results(exp, act)
        assert diffs == []

    def test_float_diff_to_dict(self):
        diff = FloatDiff(activity_id="A", field="total_float", expected=0, actual=3, delta=3)
        d = diff.to_dict()
        assert set(d.keys()) == {"activity_id", "field", "expected", "actual", "delta"}
        assert d["delta"] == 3


# ---------------------------------------------------------------------------
# Category 7: Date comparison — compare_date_results
# ---------------------------------------------------------------------------

class TestCompareDateResults:
    def test_no_diff_when_equal(self):
        exp = {"A": {
            "early_start": "2026-01-05", "early_finish": "2026-01-07",
            "late_start": "2026-01-05", "late_finish": "2026-01-07",
        }}
        act = {"A": {
            "early_start": "2026-01-05", "early_finish": "2026-01-07",
            "late_start": "2026-01-05", "late_finish": "2026-01-07",
        }}
        assert compare_date_results(exp, act) == []

    def test_early_start_diff_detected(self):
        exp = {"A": {
            "early_start": "2026-01-05", "early_finish": "2026-01-07",
            "late_start": "2026-01-05", "late_finish": "2026-01-07",
        }}
        act = {"A": {
            "early_start": "2026-01-06", "early_finish": "2026-01-07",
            "late_start": "2026-01-05", "late_finish": "2026-01-07",
        }}
        diffs = compare_date_results(exp, act)
        assert len(diffs) == 1
        assert diffs[0].field == "early_start"
        assert diffs[0].expected == "2026-01-05"
        assert diffs[0].actual == "2026-01-06"

    def test_all_four_date_fields_checked(self):
        exp = {"A": {
            "early_start": "2026-01-01", "early_finish": "2026-01-01",
            "late_start": "2026-01-01", "late_finish": "2026-01-01",
        }}
        act = {"A": {
            "early_start": "2026-01-02", "early_finish": "2026-01-03",
            "late_start": "2026-01-04", "late_finish": "2026-01-05",
        }}
        diffs = compare_date_results(exp, act)
        assert len(diffs) == 4

    def test_date_diff_to_dict(self):
        diff = DateDiff(activity_id="A", field="early_start",
                        expected="2026-01-05", actual="2026-01-06")
        d = diff.to_dict()
        assert set(d.keys()) == {"activity_id", "field", "expected", "actual"}


# ---------------------------------------------------------------------------
# Category 8: Longest-path comparison — compare_paths
# ---------------------------------------------------------------------------

class TestComparePaths:
    def test_matching_paths_no_missing_extra(self):
        diff = compare_paths(["A", "B", "C"], ["A", "B", "C"])
        assert diff.missing_from_actual == []
        assert diff.extra_in_actual == []
        assert not diff.order_differs

    def test_missing_from_actual(self):
        diff = compare_paths(["A", "B", "C"], ["A", "C"])
        assert diff.missing_from_actual == ["B"]
        assert diff.extra_in_actual == []

    def test_extra_in_actual(self):
        diff = compare_paths(["A", "B"], ["A", "B", "C"])
        assert diff.extra_in_actual == ["C"]
        assert diff.missing_from_actual == []

    def test_completely_different_paths(self):
        diff = compare_paths(["A", "B"], ["C", "D"])
        assert set(diff.missing_from_actual) == {"A", "B"}
        assert set(diff.extra_in_actual) == {"C", "D"}

    def test_same_set_different_order_detected(self):
        diff = compare_paths(["A", "B", "C"], ["C", "A", "B"])
        assert diff.order_differs is True
        assert diff.missing_from_actual == []
        assert diff.extra_in_actual == []

    def test_empty_paths(self):
        diff = compare_paths([], [])
        assert diff.missing_from_actual == []
        assert diff.extra_in_actual == []
        assert not diff.order_differs

    def test_expected_empty_actual_has_ids(self):
        diff = compare_paths([], ["A", "B"])
        assert diff.extra_in_actual == ["A", "B"]

    def test_path_diff_to_dict(self):
        diff = compare_paths(["A"], ["A"])
        d = diff.to_dict()
        assert set(d.keys()) == {
            "expected_ids", "actual_ids", "missing_from_actual",
            "extra_in_actual", "order_differs",
        }


# ---------------------------------------------------------------------------
# Category 6: Warning comparison — compare_warning_codes
# ---------------------------------------------------------------------------

class TestCompareWarningCodes:
    def test_matching_codes_no_missing_extra(self):
        diff = compare_warning_codes(["ENG-001", "ENG-002"], ["ENG-001", "ENG-002"])
        assert diff.missing == []
        assert diff.extra == []

    def test_missing_code_detected(self):
        diff = compare_warning_codes(["ENG-001"], [])
        assert "ENG-001" in diff.missing
        assert diff.extra == []

    def test_extra_code_detected(self):
        diff = compare_warning_codes([], ["ENG-001"])
        assert "ENG-001" in diff.extra
        assert diff.missing == []

    def test_partial_overlap(self):
        diff = compare_warning_codes(["A", "B"], ["B", "C"])
        assert diff.missing == ["A"]
        assert diff.extra == ["C"]

    def test_empty_expected_empty_actual(self):
        diff = compare_warning_codes([], [])
        assert diff.missing == []
        assert diff.extra == []

    def test_warning_diff_to_dict(self):
        diff = compare_warning_codes(["ENG-001"], [])
        d = diff.to_dict()
        assert set(d.keys()) == {"expected_codes", "actual_codes", "missing", "extra"}

    def test_returned_codes_sorted(self):
        diff = compare_warning_codes(["ENG-003", "ENG-001"], ["ENG-002"])
        assert diff.expected_codes == ["ENG-001", "ENG-003"]
        assert diff.actual_codes == ["ENG-002"]


# ---------------------------------------------------------------------------
# NormalizationDiff serialization
# ---------------------------------------------------------------------------

class TestNormalizationDiff:
    def test_to_dict_structure(self):
        diff = NormalizationDiff(
            expected_categories={"duration_normalization": 2},
            actual_categories={"duration_normalization": 3},
            changed_categories=["duration_normalization"],
        )
        d = diff.to_dict()
        assert set(d.keys()) == {
            "expected_categories", "actual_categories", "changed_categories"
        }

    def test_changed_categories_list(self):
        diff = NormalizationDiff(
            expected_categories={"A": 1},
            actual_categories={"A": 2},
            changed_categories=["A"],
        )
        assert diff.changed_categories == ["A"]


# ---------------------------------------------------------------------------
# ConventionDiff serialization
# ---------------------------------------------------------------------------

class TestConventionDiff:
    def test_to_dict_structure(self):
        diff = ConventionDiff(
            benchmark_id="BM-001",
            convention_a="inclusive_day",
            convention_b="p6_compatibility",
        )
        d = diff.to_dict()
        assert set(d.keys()) == {
            "benchmark_id", "convention_a", "convention_b",
            "date_diffs", "float_diffs", "path_changed", "duration_changed",
        }

    def test_default_no_diffs(self):
        diff = ConventionDiff(
            benchmark_id="BM-001",
            convention_a="inclusive_day",
            convention_b="p6_compatibility",
        )
        assert diff.date_diffs == []
        assert diff.float_diffs == []
        assert not diff.path_changed
        assert not diff.duration_changed

    def test_with_date_diffs(self):
        date_diff = DateDiff("A", "early_finish", "2026-01-13", "2026-01-12")
        conv_diff = ConventionDiff(
            benchmark_id="BM-001",
            convention_a="inclusive_day",
            convention_b="p6_compatibility",
            date_diffs=[date_diff],
        )
        d = conv_diff.to_dict()
        assert len(d["date_diffs"]) == 1
        assert d["date_diffs"][0]["activity_id"] == "A"
