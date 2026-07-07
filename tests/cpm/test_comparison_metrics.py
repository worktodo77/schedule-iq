"""
V1-G: Tests for comparison_validation/metrics.py.

Covers:
  - ComparisonMetrics field defaults
  - to_dict() serialization and rounding
  - activity_match_pct edge cases (zero total)
  - Critical path list fields
  - Divergence/checkpoint count fields
"""

import os, sys
SRC = os.path.join(os.path.dirname(__file__), "..", "..", "src")
sys.path.insert(0, os.path.abspath(SRC))

import pytest

from scheduleiq.cpm.compare.metrics import ComparisonMetrics  # noqa: E402


class TestComparisonMetricsDefaults:

    def test_all_numeric_defaults_zero(self):
        m = ComparisonMetrics()
        assert m.total_activities == 0
        assert m.mip39_only_activities == 0
        assert m.reference_only_activities == 0
        assert m.exact_match_activities == 0
        assert m.within_tolerance_activities == 0
        assert m.divergent_activities == 0
        assert m.activity_match_pct == 0.0
        assert m.total_float_variance_max == 0
        assert m.total_float_variance_mean == 0.0
        assert m.free_float_variance_max == 0
        assert m.divergence_count_total == 0
        assert m.unresolved_divergence_count == 0
        assert m.blocking_divergence_count == 0
        assert m.checkpoint_count == 0
        assert m.unresolved_checkpoint_count == 0

    def test_critical_path_agreement_default_false(self):
        m = ComparisonMetrics()
        assert m.critical_path_agreement is False

    def test_list_fields_empty(self):
        m = ComparisonMetrics()
        assert m.critical_path_mip39_only == []
        assert m.critical_path_ref_only == []

    def test_finish_date_variance_days_default_none(self):
        m = ComparisonMetrics()
        assert m.finish_date_variance_days is None

    def test_divergence_counts_default_empty(self):
        m = ComparisonMetrics()
        assert m.divergence_counts == {}


class TestComparisonMetricsToDict:

    def test_to_dict_has_all_keys(self):
        m = ComparisonMetrics()
        d = m.to_dict()
        expected_keys = [
            "total_activities", "mip39_only_activities", "reference_only_activities",
            "exact_match_activities", "within_tolerance_activities", "divergent_activities",
            "activity_match_pct", "critical_path_agreement", "critical_path_mip39_only",
            "critical_path_ref_only", "finish_date_variance_days", "total_float_variance_max",
            "total_float_variance_mean", "free_float_variance_max", "divergence_count_total",
            "divergence_counts", "unresolved_divergence_count", "blocking_divergence_count",
            "checkpoint_count", "unresolved_checkpoint_count",
        ]
        for k in expected_keys:
            assert k in d, f"Missing key: {k}"

    def test_activity_match_pct_rounded_to_2_decimals(self):
        m = ComparisonMetrics(activity_match_pct=99.9876543)
        d = m.to_dict()
        assert d["activity_match_pct"] == round(99.9876543, 2)

    def test_total_float_variance_mean_rounded_to_3_decimals(self):
        m = ComparisonMetrics(total_float_variance_mean=1.23456789)
        d = m.to_dict()
        assert d["total_float_variance_mean"] == round(1.23456789, 3)

    def test_finish_date_variance_none_serialized(self):
        m = ComparisonMetrics(finish_date_variance_days=None)
        d = m.to_dict()
        assert d["finish_date_variance_days"] is None

    def test_finish_date_variance_int_serialized(self):
        m = ComparisonMetrics(finish_date_variance_days=3)
        d = m.to_dict()
        assert d["finish_date_variance_days"] == 3

    def test_critical_path_lists_in_dict(self):
        m = ComparisonMetrics(
            critical_path_agreement=False,
            critical_path_mip39_only=["A100"],
            critical_path_ref_only=["A200"],
        )
        d = m.to_dict()
        assert d["critical_path_mip39_only"] == ["A100"]
        assert d["critical_path_ref_only"] == ["A200"]
        assert d["critical_path_agreement"] is False

    def test_divergence_counts_dict_serialized(self):
        m = ComparisonMetrics(divergence_counts={"FLOAT_METHOD_DIFFERENCE": 3})
        d = m.to_dict()
        assert d["divergence_counts"]["FLOAT_METHOD_DIFFERENCE"] == 3


class TestComparisonMetricsMath:

    def test_100_pct_match(self):
        m = ComparisonMetrics(
            total_activities=10,
            within_tolerance_activities=10,
            activity_match_pct=100.0,
        )
        assert m.activity_match_pct == 100.0

    def test_zero_total_activities_is_0_pct(self):
        m = ComparisonMetrics(total_activities=0, activity_match_pct=0.0)
        assert m.activity_match_pct == 0.0

    def test_partial_match(self):
        m = ComparisonMetrics(
            total_activities=4,
            within_tolerance_activities=3,
            activity_match_pct=75.0,
        )
        assert m.activity_match_pct == 75.0
