"""
V1-G: Tests for comparison_validation/divergences.py.

Covers:
  - DivergenceCategory predicates (is_blocking, requires_analyst_note)
  - DivergenceRecord lifecycle (create, acknowledge, waive, reclassify)
  - DivergenceAccumulator (add, buckets, filters, counts, serialization)
  - Deterministic ID assignment
"""

import os, sys
SRC = os.path.join(os.path.dirname(__file__), "..", "..", "src")
sys.path.insert(0, os.path.abspath(SRC))

import pytest

from scheduleiq.cpm.compare.divergences import (  # noqa: E402
    DivergenceAccumulator,
    DivergenceCategory,
    DivergenceRecord,
)


# ---------------------------------------------------------------------------
# DivergenceCategory predicates
# ---------------------------------------------------------------------------

class TestDivergenceCategoryPredicates:

    def test_material_is_blocking(self):
        assert DivergenceCategory.MATERIAL_ANALYTICAL_DIFFERENCE.is_blocking() is True

    def test_unknown_is_blocking(self):
        assert DivergenceCategory.UNKNOWN_DIFFERENCE.is_blocking() is True

    def test_expected_not_blocking(self):
        assert DivergenceCategory.EXPECTED_DIFFERENCE.is_blocking() is False

    def test_governed_not_blocking(self):
        assert DivergenceCategory.GOVERNED_DIFFERENCE.is_blocking() is False

    def test_p6_not_blocking(self):
        assert DivergenceCategory.P6_EMULATION_DIFFERENCE.is_blocking() is False

    def test_calendar_not_blocking(self):
        assert DivergenceCategory.CALENDAR_BEHAVIOR_DIFFERENCE.is_blocking() is False

    def test_lag_not_blocking(self):
        assert DivergenceCategory.LAG_BEHAVIOR_DIFFERENCE.is_blocking() is False

    def test_float_not_blocking(self):
        assert DivergenceCategory.FLOAT_METHOD_DIFFERENCE.is_blocking() is False

    def test_material_requires_note(self):
        assert DivergenceCategory.MATERIAL_ANALYTICAL_DIFFERENCE.requires_analyst_note() is True

    def test_unknown_requires_note(self):
        assert DivergenceCategory.UNKNOWN_DIFFERENCE.requires_analyst_note() is True

    def test_governed_requires_note(self):
        assert DivergenceCategory.GOVERNED_DIFFERENCE.requires_analyst_note() is True

    def test_expected_no_note_required(self):
        assert DivergenceCategory.EXPECTED_DIFFERENCE.requires_analyst_note() is False

    def test_all_categories_present(self):
        values = {c.value for c in DivergenceCategory}
        assert "EXPECTED_DIFFERENCE" in values
        assert "GOVERNED_DIFFERENCE" in values
        assert "MATERIAL_ANALYTICAL_DIFFERENCE" in values
        assert "P6_EMULATION_DIFFERENCE" in values
        assert "CALENDAR_BEHAVIOR_DIFFERENCE" in values
        assert "LAG_BEHAVIOR_DIFFERENCE" in values
        assert "FLOAT_METHOD_DIFFERENCE" in values
        assert "UNKNOWN_DIFFERENCE" in values


# ---------------------------------------------------------------------------
# DivergenceRecord lifecycle
# ---------------------------------------------------------------------------

class TestDivergenceRecord:

    def _make_record(self, category=DivergenceCategory.UNKNOWN_DIFFERENCE) -> DivergenceRecord:
        return DivergenceRecord(
            div_id="DIV-001",
            act_id="A100",
            field="total_float",
            mip39_value=5,
            reference_value=3,
            delta=2.0,
            category=category,
            explanation="TF differs by 2",
        )

    def test_initial_state(self):
        rec = self._make_record()
        assert rec.is_resolved is False
        assert rec.resolution == ""
        assert rec.analyst_note == ""

    def test_acknowledge_sets_resolved(self):
        rec = self._make_record()
        rec.acknowledge("Reviewed and confirmed")
        assert rec.is_resolved is True
        assert rec.resolution == "acknowledged"
        assert rec.analyst_note == "Reviewed and confirmed"

    def test_acknowledge_without_note(self):
        rec = self._make_record()
        rec.acknowledge()
        assert rec.is_resolved is True
        assert rec.analyst_note == ""

    def test_waive_sets_resolved(self):
        rec = self._make_record()
        rec.waive("Acceptable for V1 — within AACE RP tolerance")
        assert rec.is_resolved is True
        assert rec.resolution == "waived"
        assert "AACE" in rec.analyst_note

    def test_reclassify_changes_category(self):
        rec = self._make_record(DivergenceCategory.UNKNOWN_DIFFERENCE)
        rec.reclassify(DivergenceCategory.FLOAT_METHOD_DIFFERENCE, "TF=0 vs longest-path")
        assert rec.category == DivergenceCategory.FLOAT_METHOD_DIFFERENCE
        assert "longest-path" in rec.analyst_note

    def test_reclassify_without_note_preserves_note(self):
        rec = self._make_record()
        rec.analyst_note = "existing"
        rec.reclassify(DivergenceCategory.FLOAT_METHOD_DIFFERENCE)
        assert rec.analyst_note == "existing"

    def test_to_dict_keys(self):
        rec = self._make_record()
        d = rec.to_dict()
        for key in ("div_id", "act_id", "field", "mip39_value", "reference_value",
                    "delta", "category", "explanation", "analyst_note",
                    "is_resolved", "resolution"):
            assert key in d, f"Missing key: {key}"

    def test_to_dict_category_is_string(self):
        rec = self._make_record()
        d = rec.to_dict()
        assert isinstance(d["category"], str)

    def test_to_dict_date_serialization(self):
        from datetime import date
        rec = DivergenceRecord(
            div_id="DIV-002",
            act_id="A100",
            field="early_finish",
            mip39_value=date(2024, 3, 15),
            reference_value=date(2024, 3, 14),
            delta=1.0,
            category=DivergenceCategory.CALENDAR_BEHAVIOR_DIFFERENCE,
            explanation="1-day shift",
        )
        d = rec.to_dict()
        assert d["mip39_value"] == "2024-03-15"
        assert d["reference_value"] == "2024-03-14"

    def test_to_dict_none_act_id(self):
        rec = DivergenceRecord(
            div_id="DIV-003",
            act_id=None,
            field="project_finish",
            mip39_value=None,
            reference_value="2024-12-31",
            delta=None,
            category=DivergenceCategory.MATERIAL_ANALYTICAL_DIFFERENCE,
            explanation="Project finish missing",
        )
        d = rec.to_dict()
        assert d["act_id"] is None


# ---------------------------------------------------------------------------
# DivergenceAccumulator
# ---------------------------------------------------------------------------

class TestDivergenceAccumulator:

    def _acc(self) -> DivergenceAccumulator:
        return DivergenceAccumulator()

    def test_empty_initial_state(self):
        acc = self._acc()
        assert len(acc) == 0
        assert acc.all == []

    def test_add_returns_record(self):
        acc = self._acc()
        rec = acc.add(
            act_id="A100",
            field="total_float",
            mip39_value=5,
            reference_value=3,
            category=DivergenceCategory.FLOAT_METHOD_DIFFERENCE,
            explanation="TF diff",
        )
        assert isinstance(rec, DivergenceRecord)

    def test_sequential_ids(self):
        acc = self._acc()
        r1 = acc.add("A100", "total_float", 5, 3, DivergenceCategory.FLOAT_METHOD_DIFFERENCE, "x")
        r2 = acc.add("A110", "early_finish", 1, 2, DivergenceCategory.UNKNOWN_DIFFERENCE, "y")
        assert r1.div_id == "DIV-001"
        assert r2.div_id == "DIV-002"

    def test_ids_are_zero_padded(self):
        acc = self._acc()
        for i in range(9):
            acc.add("A100", "f", i, i + 1, DivergenceCategory.UNKNOWN_DIFFERENCE, "x")
        rec = acc.add("A100", "f", 9, 10, DivergenceCategory.UNKNOWN_DIFFERENCE, "x")
        assert rec.div_id == "DIV-010"

    def test_by_category_bucketing(self):
        acc = self._acc()
        acc.add("A100", "total_float", 5, 3, DivergenceCategory.FLOAT_METHOD_DIFFERENCE, "x")
        acc.add("A110", "is_valid", False, True, DivergenceCategory.MATERIAL_ANALYTICAL_DIFFERENCE, "y")
        assert len(acc.by_category(DivergenceCategory.FLOAT_METHOD_DIFFERENCE)) == 1
        assert len(acc.by_category(DivergenceCategory.MATERIAL_ANALYTICAL_DIFFERENCE)) == 1
        assert len(acc.by_category(DivergenceCategory.UNKNOWN_DIFFERENCE)) == 0

    def test_unresolved_filter(self):
        acc = self._acc()
        r1 = acc.add("A100", "total_float", 5, 3, DivergenceCategory.FLOAT_METHOD_DIFFERENCE, "x")
        r2 = acc.add("A110", "f", 1, 2, DivergenceCategory.UNKNOWN_DIFFERENCE, "y")
        r1.acknowledge()
        assert len(acc.unresolved()) == 1
        assert acc.unresolved()[0].div_id == r2.div_id

    def test_unresolved_blocking(self):
        acc = self._acc()
        acc.add("A100", "f", 5, 3, DivergenceCategory.FLOAT_METHOD_DIFFERENCE, "x")
        r2 = acc.add("A110", "f", 1, 2, DivergenceCategory.MATERIAL_ANALYTICAL_DIFFERENCE, "y")
        r3 = acc.add("A120", "f", 1, 2, DivergenceCategory.UNKNOWN_DIFFERENCE, "z")
        r3.acknowledge()
        blocking = acc.unresolved_blocking()
        assert len(blocking) == 1
        assert blocking[0].div_id == r2.div_id

    def test_material_shortcut(self):
        acc = self._acc()
        acc.add("A100", "f", 1, 2, DivergenceCategory.MATERIAL_ANALYTICAL_DIFFERENCE, "x")
        acc.add("A110", "f", 1, 2, DivergenceCategory.FLOAT_METHOD_DIFFERENCE, "y")
        assert len(acc.material()) == 1

    def test_unknown_shortcut(self):
        acc = self._acc()
        acc.add("A100", "f", 1, 2, DivergenceCategory.UNKNOWN_DIFFERENCE, "x")
        assert len(acc.unknown()) == 1

    def test_counts_by_category_all_keys_present(self):
        acc = self._acc()
        counts = acc.counts_by_category()
        for cat in DivergenceCategory:
            assert cat.value in counts

    def test_counts_by_category_values(self):
        acc = self._acc()
        acc.add("A100", "f", 1, 2, DivergenceCategory.FLOAT_METHOD_DIFFERENCE, "x")
        acc.add("A110", "f", 1, 2, DivergenceCategory.FLOAT_METHOD_DIFFERENCE, "y")
        counts = acc.counts_by_category()
        assert counts[DivergenceCategory.FLOAT_METHOD_DIFFERENCE.value] == 2
        assert counts[DivergenceCategory.UNKNOWN_DIFFERENCE.value] == 0

    def test_to_dict_list(self):
        acc = self._acc()
        acc.add("A100", "f", 1, 2, DivergenceCategory.FLOAT_METHOD_DIFFERENCE, "x")
        lst = acc.to_dict_list()
        assert len(lst) == 1
        assert isinstance(lst[0], dict)

    def test_insertion_order_preserved(self):
        acc = self._acc()
        for i in range(5):
            acc.add(f"A{i:03d}", "f", i, i + 1, DivergenceCategory.UNKNOWN_DIFFERENCE, "x")
        ids = [r.div_id for r in acc.all]
        assert ids == ["DIV-001", "DIV-002", "DIV-003", "DIV-004", "DIV-005"]

    def test_all_categories_bucketed_on_init(self):
        acc = self._acc()
        for cat in DivergenceCategory:
            assert acc.by_category(cat) == []
