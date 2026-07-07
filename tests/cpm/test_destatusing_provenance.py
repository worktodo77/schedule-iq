"""
Tests for V1-D: Transformation provenance (TransformationRecord, TransformationLog).

Covers:
  - TransformationLog generates sequential TX-NNN IDs
  - make_removal_record, make_set_record, make_compute_record populate fields correctly
  - for_activity() and requiring_review() filtering
  - No silent transformations — every rule leaves at least one record
  - TransformationRecord is frozen (immutable)
"""

from __future__ import annotations

import os, sys
SRC = os.path.join(os.path.dirname(__file__), "..", "..", "src")
sys.path.insert(0, os.path.abspath(SRC))

from datetime import date

import pytest

from scheduleiq.cpm.destatusing import (  # noqa: E402
    TransformationLog,
    TransformationRecord,
    make_removal_record,
    make_set_record,
    make_compute_record,
)


class TestTransformationLogIDs:
    def test_sequential_ids(self):
        log = TransformationLog()
        make_set_record(log, "A1", "RULE_B", "CALC-006", "original_duration",
                        source_value=5, target_value=3,
                        reversible=True, analyst_review_required=False,
                        analytical_implication="test")
        make_set_record(log, "A2", "RULE_B", "CALC-006", "percent_complete",
                        source_value=0.5, target_value=0.0,
                        reversible=True, analyst_review_required=False,
                        analytical_implication="test")
        ids = [r.transformation_id for r in log.all]
        assert ids[0] == "TX-001"
        assert ids[1] == "TX-002"

    def test_fresh_log_empty(self):
        log = TransformationLog()
        assert len(log.all) == 0

    def test_len(self):
        log = TransformationLog()
        make_removal_record(log, "A1", "RULE_B", "CALC-006", "actual_start",
                            source_value=date(2024, 1, 1),
                            analyst_review_required=False,
                            analytical_implication="test")
        assert len(log) == 1


class TestMakeRemovalRecord:
    def test_type_is_remove(self):
        log = TransformationLog()
        make_removal_record(log, "A1", "RULE_B", "CALC-006", "actual_start",
                            source_value=date(2024, 1, 1),
                            analyst_review_required=False,
                            analytical_implication="test")
        r = log.all[0]
        assert r.transformation_type == "REMOVE"

    def test_target_value_is_none(self):
        log = TransformationLog()
        make_removal_record(log, "A1", "RULE_B", "CALC-006", "actual_start",
                            source_value=date(2024, 1, 1),
                            analyst_review_required=False,
                            analytical_implication="test")
        assert log.all[0].target_value is None

    def test_fields_populated(self):
        log = TransformationLog()
        src = date(2024, 1, 5)
        make_removal_record(log, "A1", "RULE_D", "CALC-008", "actual_finish",
                            source_value=src,
                            analyst_review_required=True,
                            analytical_implication="Finish removed.")
        r = log.all[0]
        assert r.act_id == "A1"
        assert r.rule == "RULE_D"
        assert r.governing_calc == "CALC-008"
        assert r.field_name == "actual_finish"
        assert r.source_value == src
        assert r.analyst_review_required is True
        assert "Finish removed" in r.analytical_implication


class TestMakeSetRecord:
    def test_type_is_set(self):
        log = TransformationLog()
        make_set_record(log, "A1", "RULE_B", "CALC-006", "original_duration",
                        source_value=5, target_value=3,
                        reversible=True, analyst_review_required=False,
                        analytical_implication="OD set.")
        assert log.all[0].transformation_type == "SET"

    def test_source_and_target_set(self):
        log = TransformationLog()
        make_set_record(log, "A1", "RULE_B", "CALC-006", "percent_complete",
                        source_value=0.75, target_value=0.0,
                        reversible=True, analyst_review_required=False,
                        analytical_implication="PC reset.")
        r = log.all[0]
        assert r.source_value == 0.75
        assert r.target_value == 0.0

    def test_reversible_field(self):
        log = TransformationLog()
        make_set_record(log, "A1", "RULE_B", "CALC-006", "original_duration",
                        source_value=5, target_value=3,
                        reversible=False, analyst_review_required=False,
                        analytical_implication="test")
        assert log.all[0].reversible is False


class TestMakeComputeRecord:
    def test_type_is_compute(self):
        log = TransformationLog()
        make_compute_record(log, "A1", "RULE_D", "CALC-008", "remaining_duration",
                            source_value=3, target_value=5,
                            analyst_review_required=False,
                            analytical_implication="RD computed.")
        assert log.all[0].transformation_type == "COMPUTE"

    def test_analyst_review_required_propagated(self):
        log = TransformationLog()
        make_compute_record(log, "A1", "RULE_D", "CALC-008", "percent_complete",
                            source_value=0.6, target_value=0.5,
                            analyst_review_required=True,
                            analytical_implication="PC formula.")
        assert log.all[0].analyst_review_required is True


class TestTransformationLogFiltering:
    def setup_method(self):
        self.log = TransformationLog()
        make_removal_record(self.log, "A1", "RULE_B", "CALC-006", "actual_start",
                            source_value=date(2024, 1, 1),
                            analyst_review_required=False,
                            analytical_implication="test")
        make_compute_record(self.log, "A2", "RULE_D", "CALC-008", "percent_complete",
                            source_value=0.6, target_value=0.5,
                            analyst_review_required=True,
                            analytical_implication="PC formula.")
        make_set_record(self.log, "A1", "RULE_B", "CALC-006", "original_duration",
                        source_value=5, target_value=3,
                        reversible=True, analyst_review_required=False,
                        analytical_implication="OD set.")

    def test_for_activity_filters_by_act_id(self):
        a1_records = self.log.for_activity("A1")
        assert len(a1_records) == 2
        assert all(r.act_id == "A1" for r in a1_records)

    def test_requiring_review_filters_correctly(self):
        review_records = self.log.requiring_review()
        assert len(review_records) == 1
        assert review_records[0].act_id == "A2"

    def test_all_returns_all_records(self):
        assert len(self.log.all) == 3


class TestTransformationRecordImmutability:
    def test_frozen(self):
        log = TransformationLog()
        make_set_record(log, "A1", "RULE_B", "CALC-006", "original_duration",
                        source_value=5, target_value=3,
                        reversible=True, analyst_review_required=False,
                        analytical_implication="test")
        r = log.all[0]
        with pytest.raises((AttributeError, TypeError)):
            r.field_name = "something_else"  # type: ignore[misc]

    def test_to_dict_has_required_keys(self):
        log = TransformationLog()
        make_set_record(log, "A1", "RULE_B", "CALC-006", "original_duration",
                        source_value=5, target_value=3,
                        reversible=True, analyst_review_required=False,
                        analytical_implication="test")
        d = log.all[0].to_dict()
        for key in ("transformation_id", "act_id", "rule", "governing_calc",
                    "field_name", "source_value", "target_value",
                    "transformation_type", "reversible", "analyst_review_required",
                    "analytical_implication"):
            assert key in d
