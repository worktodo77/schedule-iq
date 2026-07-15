"""
Tests for the network validation framework (src/mip39/validation.py).

Coverage:
  - ValidationSeverity enum ordering
  - ValidationIssue construction and deterministic field sorting
  - ValidationResult aggregation, filtering, sorting, and summary
  - NetworkValidator — all individual checks
  - NetworkValidator.validate_all() — combined run
  - Topology checks (open-ended, multi-start, multi-finish)
  - Deterministic output verification (same input → same output)
  - Blocking issue classification
  - Edge cases: empty networks, single-activity networks, isolated nodes
"""

import os, sys
from datetime import date
SRC = os.path.join(os.path.dirname(__file__), "..", "..", "src")
sys.path.insert(0, os.path.abspath(SRC))

import pytest

from scheduleiq.cpm.models import Activity, Relationship  # noqa: E402
from scheduleiq.cpm.network import ActivityNetwork, topological_sort  # noqa: E402
from scheduleiq.cpm.validation import (  # noqa: E402
    ISSUE_CATALOG,
    NetworkValidator,
    ValidationIssue,
    ValidationResult,
    ValidationSeverity,
    _make_issue,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _act(act_id: str, od: float | None = 5) -> Activity:
    return Activity(act_id=act_id, original_duration=od)


def _rel(pred: str, succ: str, rel_type: str = "FS", lag: float = 0.0) -> Relationship:
    return Relationship(pred_id=pred, succ_id=succ, rel_type=rel_type, lag=lag)


def _invalid_rel(pred: str, succ: str, rel_type: str, lag: float = 0.0) -> Relationship:
    """Create a Relationship with an unsupported rel_type, bypassing __post_init__.

    Relationship.__post_init__ enforces {FS, SS, FF, SF} at construction time.
    To test NET-005 (which fires for types outside that set), we create a valid
    object first, then mutate rel_type. This simulates data that bypassed model
    construction (e.g., a future XER parser that uses a separate validation path).
    """
    r = Relationship(pred_id=pred, succ_id=succ, rel_type="FS", lag=lag)
    r.rel_type = rel_type
    return r


# ---------------------------------------------------------------------------
# ValidationSeverity
# ---------------------------------------------------------------------------

class TestValidationSeverity:
    def test_all_severities_exist(self):
        assert ValidationSeverity.INFO
        assert ValidationSeverity.WARNING
        assert ValidationSeverity.ERROR
        assert ValidationSeverity.CRITICAL

    def test_severity_values(self):
        assert ValidationSeverity.INFO.value == "INFO"
        assert ValidationSeverity.WARNING.value == "WARNING"
        assert ValidationSeverity.ERROR.value == "ERROR"
        assert ValidationSeverity.CRITICAL.value == "CRITICAL"

    def test_severity_ordering_critical_highest(self):
        assert ValidationSeverity.CRITICAL < ValidationSeverity.ERROR
        assert ValidationSeverity.ERROR < ValidationSeverity.WARNING
        assert ValidationSeverity.WARNING < ValidationSeverity.INFO

    def test_severity_not_equal(self):
        assert ValidationSeverity.CRITICAL != ValidationSeverity.ERROR


# ---------------------------------------------------------------------------
# ISSUE_CATALOG
# ---------------------------------------------------------------------------

class TestIssueCatalog:
    def test_all_expected_codes_present(self):
        expected = {
            "NET-001", "NET-002", "NET-003", "NET-004", "NET-005",
            "NET-006", "NET-007", "NET-008", "NET-009", "NET-010",
            "NET-011", "NET-012", "NET-013",
        }
        assert expected.issubset(set(ISSUE_CATALOG.keys()))

    def test_each_entry_has_source_reference(self):
        for code, entry in ISSUE_CATALOG.items():
            assert entry.source_reference, f"{code} missing source_reference"

    def test_each_entry_has_analyst_action(self):
        for code, entry in ISSUE_CATALOG.items():
            assert entry.analyst_action, f"{code} missing analyst_action"

    def test_blocking_codes_are_critical(self):
        for code, entry in ISSUE_CATALOG.items():
            if entry.blocking:
                assert entry.default_severity == ValidationSeverity.CRITICAL, (
                    f"{code} is blocking but not CRITICAL"
                )

    def test_net006_is_blocking(self):
        assert ISSUE_CATALOG["NET-006"].blocking is True

    def test_net007_is_blocking(self):
        assert ISSUE_CATALOG["NET-007"].blocking is True

    def test_net009_is_blocking(self):
        assert ISSUE_CATALOG["NET-009"].blocking is True

    def test_net013_is_blocking(self):
        assert ISSUE_CATALOG["NET-013"].blocking is True

    def test_net005_is_warning_not_blocking(self):
        assert ISSUE_CATALOG["NET-005"].default_severity == ValidationSeverity.WARNING
        assert ISSUE_CATALOG["NET-005"].blocking is False


# ---------------------------------------------------------------------------
# ValidationIssue
# ---------------------------------------------------------------------------

class TestValidationIssue:
    def test_activity_ids_sorted_on_construction(self):
        issue = ValidationIssue(
            issue_code="NET-001",
            severity=ValidationSeverity.WARNING,
            activity_ids=["C", "A", "B"],
        )
        assert issue.activity_ids == ["A", "B", "C"]

    def test_relationship_ids_sorted_on_construction(self):
        issue = ValidationIssue(
            issue_code="NET-005",
            severity=ValidationSeverity.WARNING,
            relationship_ids=[("Z", "Y", "FS"), ("A", "B", "SS")],
        )
        assert issue.relationship_ids == [("A", "B", "SS"), ("Z", "Y", "FS")]

    def test_to_dict_structure(self):
        issue = _make_issue("NET-007", activity_ids=["A"])
        d = issue.to_dict()
        assert d["issue_code"] == "NET-007"
        assert d["severity"] == "CRITICAL"
        assert d["activity_ids"] == ["A"]
        assert d["blocking"] is True
        assert "message" in d
        assert "source_reference" in d
        assert "analyst_action" in d

    def test_make_issue_uses_catalog_defaults(self):
        issue = _make_issue("NET-006", activity_ids=["A", "B"])
        assert issue.severity == ValidationSeverity.CRITICAL
        assert issue.blocking is True
        assert "SRC" in issue.source_reference

    def test_make_issue_severity_override(self):
        issue = _make_issue(
            "NET-003",
            severity_override=ValidationSeverity.ERROR,
        )
        assert issue.severity == ValidationSeverity.ERROR

    def test_make_issue_message_override(self):
        issue = _make_issue("NET-001", message="custom msg")
        assert issue.message == "custom msg"


# ---------------------------------------------------------------------------
# ValidationResult
# ---------------------------------------------------------------------------

class TestValidationResult:
    def test_empty_result_is_clean(self):
        result = ValidationResult()
        assert result.is_clean
        assert not result.has_blocking_issues
        assert not result.has_critical
        assert not result.has_errors
        assert not result.has_warnings

    def test_add_single_issue(self):
        result = ValidationResult()
        result.add(_make_issue("NET-007", activity_ids=["A"]))
        assert not result.is_clean
        assert result.has_critical
        assert result.has_blocking_issues
        assert len(result.issues) == 1

    def test_extend_adds_multiple(self):
        result = ValidationResult()
        result.extend([
            _make_issue("NET-003", activity_ids=["A", "B"]),
            _make_issue("NET-004", activity_ids=["C", "D"]),
        ])
        assert len(result.issues) == 2

    def test_sorting_critical_before_warning(self):
        result = ValidationResult()
        result.extend([
            _make_issue("NET-003"),   # WARNING
            _make_issue("NET-006"),   # CRITICAL
        ])
        assert result.issues[0].severity == ValidationSeverity.CRITICAL

    def test_sorting_by_issue_code_within_severity(self):
        result = ValidationResult()
        result.extend([
            _make_issue("NET-004"),   # WARNING
            _make_issue("NET-003"),   # WARNING
        ])
        assert result.issues[0].issue_code == "NET-003"
        assert result.issues[1].issue_code == "NET-004"

    def test_sorting_by_activity_id_within_code(self):
        result = ValidationResult()
        result.extend([
            _make_issue("NET-001", activity_ids=["Z"]),
            _make_issue("NET-001", activity_ids=["A"]),
        ])
        assert result.issues[0].activity_ids[0] == "A"
        assert result.issues[1].activity_ids[0] == "Z"

    def test_issues_by_severity(self):
        result = ValidationResult()
        result.extend([
            _make_issue("NET-006"),   # CRITICAL
            _make_issue("NET-003"),   # WARNING
            _make_issue("NET-011", activity_ids=["A"]),   # ERROR
        ])
        assert len(result.issues_by_severity(ValidationSeverity.CRITICAL)) == 1
        assert len(result.issues_by_severity(ValidationSeverity.WARNING)) == 1
        assert len(result.issues_by_severity(ValidationSeverity.ERROR)) == 1

    def test_issues_by_code(self):
        result = ValidationResult()
        result.extend([
            _make_issue("NET-001", activity_ids=["A"]),
            _make_issue("NET-001", activity_ids=["B"]),
            _make_issue("NET-003", activity_ids=["A", "B"]),
        ])
        net001 = result.issues_by_code("NET-001")
        assert len(net001) == 2

    def test_summary_counts(self):
        result = ValidationResult()
        result.extend([
            _make_issue("NET-006"),   # CRITICAL
            _make_issue("NET-003"),   # WARNING
            _make_issue("NET-004"),   # WARNING
        ])
        summary = result.summary()
        assert summary["CRITICAL"] == 1
        assert summary["WARNING"] == 2
        assert summary["ERROR"] == 0
        assert summary["INFO"] == 0

    def test_to_list_serializable(self):
        result = ValidationResult()
        result.add(_make_issue("NET-007", activity_ids=["A"]))
        lst = result.to_list()
        assert isinstance(lst, list)
        assert isinstance(lst[0], dict)
        assert lst[0]["issue_code"] == "NET-007"

    def test_deterministic_sorting_same_input(self):
        issues = [
            _make_issue("NET-001", activity_ids=["C"]),
            _make_issue("NET-006", activity_ids=["A", "B"]),
            _make_issue("NET-001", activity_ids=["A"]),
        ]
        r1 = ValidationResult(issues=list(issues))
        r2 = ValidationResult(issues=list(issues))
        assert [i.issue_code for i in r1.issues] == [i.issue_code for i in r2.issues]
        assert [i.activity_ids for i in r1.issues] == [i.activity_ids for i in r2.issues]


# ---------------------------------------------------------------------------
# NetworkValidator — check_duplicate_activity_ids
# ---------------------------------------------------------------------------

class TestCheckDuplicateActivityIds:
    def test_clean_no_duplicates(self):
        v = NetworkValidator([_act("A"), _act("B")], [])
        assert v.check_duplicate_activity_ids() == []

    def test_single_duplicate_detected(self):
        v = NetworkValidator([_act("A"), _act("A")], [])
        issues = v.check_duplicate_activity_ids()
        assert len(issues) == 1
        assert issues[0].issue_code == "NET-007"
        assert issues[0].severity == ValidationSeverity.CRITICAL
        assert issues[0].blocking is True
        assert "A" in issues[0].activity_ids

    def test_two_different_duplicates(self):
        v = NetworkValidator([_act("A"), _act("A"), _act("B"), _act("B")], [])
        issues = v.check_duplicate_activity_ids()
        codes = [i.activity_ids[0] for i in issues]
        assert "A" in codes
        assert "B" in codes

    def test_duplicate_reported_once_per_id(self):
        v = NetworkValidator([_act("X"), _act("X"), _act("X")], [])
        issues = v.check_duplicate_activity_ids()
        assert len(issues) == 1
        assert issues[0].activity_ids == ["X"]


# ---------------------------------------------------------------------------
# NetworkValidator — check_orphaned_relationships
# ---------------------------------------------------------------------------

class TestCheckOrphanedRelationships:
    def test_clean_no_orphans(self):
        v = NetworkValidator([_act("A"), _act("B")], [_rel("A", "B")])
        assert v.check_orphaned_relationships() == []

    def test_missing_predecessor(self):
        v = NetworkValidator([_act("B")], [_rel("X", "B")])
        issues = v.check_orphaned_relationships()
        assert any(i.issue_code == "NET-013" for i in issues)
        assert any("X" in i.activity_ids for i in issues)

    def test_missing_successor(self):
        v = NetworkValidator([_act("A")], [_rel("A", "Z")])
        issues = v.check_orphaned_relationships()
        assert any("Z" in i.activity_ids for i in issues)

    def test_both_missing(self):
        v = NetworkValidator([], [_rel("X", "Y")])
        issues = v.check_orphaned_relationships()
        missing_ids = {aid for i in issues for aid in i.activity_ids}
        assert "X" in missing_ids
        assert "Y" in missing_ids

    def test_sorted_deterministically(self):
        v = NetworkValidator([], [_rel("Z", "Y"), _rel("A", "B")])
        issues = v.check_orphaned_relationships()
        # Issues exist; first issue should be for "A" (alphabetically first missing)
        first_id = issues[0].activity_ids[0]
        assert first_id <= issues[-1].activity_ids[0] if len(issues) > 1 else True


# ---------------------------------------------------------------------------
# NetworkValidator — check_self_referential_relationships
# ---------------------------------------------------------------------------

class TestCheckSelfReferential:
    def test_clean_no_self_loop(self):
        v = NetworkValidator([_act("A"), _act("B")], [_rel("A", "B")])
        assert v.check_self_referential_relationships() == []

    def test_self_loop_detected(self):
        v = NetworkValidator([_act("A")], [_rel("A", "A")])
        issues = v.check_self_referential_relationships()
        assert len(issues) == 1
        assert issues[0].issue_code == "NET-009"
        assert issues[0].blocking is True
        assert "A" in issues[0].activity_ids

    def test_self_loop_reported_once_per_activity(self):
        v = NetworkValidator([_act("A")], [_rel("A", "A", "FS"), _rel("A", "A", "SS")])
        issues = v.check_self_referential_relationships()
        # One issue per activity with self-loop (not per relationship)
        assert len(issues) == 1

    def test_no_false_positive_for_normal_rel(self):
        v = NetworkValidator([_act("A"), _act("B")], [_rel("A", "B"), _rel("B", "A")])
        issues = v.check_self_referential_relationships()
        assert issues == []


# ---------------------------------------------------------------------------
# NetworkValidator — check_duplicate_relationships
# ---------------------------------------------------------------------------

class TestCheckDuplicateRelationships:
    def test_clean_no_duplicates(self):
        v = NetworkValidator([_act("A"), _act("B")], [_rel("A", "B", "FS", 0)])
        assert v.check_duplicate_relationships() == []

    def test_duplicate_same_type_detected(self):
        v = NetworkValidator(
            [_act("A"), _act("B")],
            [_rel("A", "B", "FS"), _rel("A", "B", "FS")],
        )
        issues = v.check_duplicate_relationships()
        assert len(issues) == 1
        assert issues[0].issue_code == "NET-008"
        assert issues[0].blocking is False

    def test_different_types_not_duplicate(self):
        v = NetworkValidator(
            [_act("A"), _act("B")],
            [_rel("A", "B", "FS"), _rel("A", "B", "SS")],
        )
        assert v.check_duplicate_relationships() == []

    def test_duplicate_with_different_lags_still_duplicate(self):
        v = NetworkValidator(
            [_act("A"), _act("B")],
            [_rel("A", "B", "FS", 0), _rel("A", "B", "FS", 2)],
        )
        issues = v.check_duplicate_relationships()
        assert len(issues) == 1


# ---------------------------------------------------------------------------
# NetworkValidator — check_missing_durations
# ---------------------------------------------------------------------------

class TestCheckMissingDurations:
    def test_clean_all_have_durations(self):
        v = NetworkValidator([_act("A", od=5), _act("B", od=0)], [])
        assert v.check_missing_durations() == []

    def test_missing_duration_detected(self):
        v = NetworkValidator([_act("A", od=None)], [])
        issues = v.check_missing_durations()
        assert len(issues) == 1
        assert issues[0].issue_code == "NET-012"
        assert issues[0].severity == ValidationSeverity.ERROR

    def test_multiple_missing_durations_all_reported(self):
        v = NetworkValidator([_act("A", od=None), _act("B", od=None)], [])
        issues = v.check_missing_durations()
        assert len(issues) == 2

    def test_zero_duration_not_flagged(self):
        v = NetworkValidator([_act("A", od=0)], [])
        assert v.check_missing_durations() == []


# ---------------------------------------------------------------------------
# NetworkValidator — check_negative_durations
# ---------------------------------------------------------------------------

class TestCheckNegativeDurations:
    def test_clean_positive_duration(self):
        v = NetworkValidator([_act("A", od=5)], [])
        assert v.check_negative_durations() == []

    def test_negative_duration_detected(self):
        v = NetworkValidator([_act("A", od=-1)], [])
        issues = v.check_negative_durations()
        assert len(issues) == 1
        assert issues[0].issue_code == "NET-011"
        assert issues[0].severity == ValidationSeverity.ERROR

    def test_zero_not_negative(self):
        v = NetworkValidator([_act("A", od=0)], [])
        assert v.check_negative_durations() == []

    def test_none_not_caught_by_negative_check(self):
        v = NetworkValidator([_act("A", od=None)], [])
        assert v.check_negative_durations() == []


# ---------------------------------------------------------------------------
# NetworkValidator — check_invalid_lags
# ---------------------------------------------------------------------------

class TestCheckInvalidLags:
    def test_clean_zero_lag(self):
        v = NetworkValidator([_act("A"), _act("B")], [_rel("A", "B", lag=0.0)])
        assert v.check_invalid_lags() == []

    def test_clean_positive_lag(self):
        v = NetworkValidator([_act("A"), _act("B")], [_rel("A", "B", lag=3.0)])
        assert v.check_invalid_lags() == []

    def test_clean_negative_lag(self):
        v = NetworkValidator([_act("A"), _act("B")], [_rel("A", "B", lag=-2.0)])
        assert v.check_invalid_lags() == []

    def test_nan_lag_detected(self):
        rel = Relationship(pred_id="A", succ_id="B", rel_type="FS", lag=float("nan"))
        v = NetworkValidator([_act("A"), _act("B")], [rel])
        issues = v.check_invalid_lags()
        assert len(issues) == 1
        assert issues[0].issue_code == "NET-010"

    def test_inf_lag_detected(self):
        rel = Relationship(pred_id="A", succ_id="B", rel_type="FS", lag=float("inf"))
        v = NetworkValidator([_act("A"), _act("B")], [rel])
        issues = v.check_invalid_lags()
        assert len(issues) == 1

    def test_negative_inf_lag_detected(self):
        rel = Relationship(pred_id="A", succ_id="B", rel_type="FS", lag=float("-inf"))
        v = NetworkValidator([_act("A"), _act("B")], [rel])
        issues = v.check_invalid_lags()
        assert len(issues) == 1


# ---------------------------------------------------------------------------
# NetworkValidator — check_unsupported_relationship_types
# ---------------------------------------------------------------------------

class TestCheckUnsupportedRelationshipTypes:
    def test_fs_and_ss_are_supported(self):
        v = NetworkValidator(
            [_act("A"), _act("B"), _act("C")],
            [_rel("A", "B", "FS"), _rel("A", "C", "SS")],
        )
        assert v.check_unsupported_relationship_types() == []

    def test_truly_invalid_type_flagged(self):
        v = NetworkValidator(
            [_act("A"), _act("B")],
            [_invalid_rel("A", "B", "XX")],
        )
        issues = v.check_unsupported_relationship_types()
        assert len(issues) == 1
        assert issues[0].issue_code == "NET-005"
        assert issues[0].severity == ValidationSeverity.WARNING
        assert issues[0].blocking is False

    def test_ff_not_flagged_as_unsupported(self):
        v = NetworkValidator(
            [_act("A"), _act("B")],
            [_rel("A", "B", "FF")],
        )
        assert v.check_unsupported_relationship_types() == []

    def test_sf_not_flagged_as_unsupported(self):
        v = NetworkValidator(
            [_act("A"), _act("B")],
            [_rel("A", "B", "SF")],
        )
        assert v.check_unsupported_relationship_types() == []

    def test_ff_and_sf_not_flagged(self):
        v = NetworkValidator(
            [_act("A"), _act("B"), _act("C")],
            [_rel("A", "B", "FF"), _rel("A", "C", "SF")],
        )
        assert v.check_unsupported_relationship_types() == []

    def test_invalid_type_with_valid_type_only_invalid_flagged(self):
        v = NetworkValidator(
            [_act("A"), _act("B"), _act("C")],
            [_rel("A", "B", "FS"), _invalid_rel("A", "C", "XX")],
        )
        issues = v.check_unsupported_relationship_types()
        assert len(issues) == 1
        assert ("A", "C", "XX") in issues[0].relationship_ids

    def test_unsupported_issue_has_source_reference(self):
        v = NetworkValidator([_act("A"), _act("B")], [_invalid_rel("A", "B", "XX")])
        issue = v.check_unsupported_relationship_types()[0]
        assert "24R-03" in issue.source_reference


# ---------------------------------------------------------------------------
# NetworkValidator — check_circular_logic
# ---------------------------------------------------------------------------

class TestCheckCircularLogic:
    def test_clean_acyclic(self):
        v = NetworkValidator(
            [_act("A"), _act("B"), _act("C")],
            [_rel("A", "B"), _rel("B", "C")],
        )
        assert v.check_circular_logic() == []

    def test_simple_cycle_detected(self):
        v = NetworkValidator(
            [_act("A"), _act("B")],
            [_rel("A", "B"), _rel("B", "A")],
        )
        issues = v.check_circular_logic()
        assert len(issues) == 1
        assert issues[0].issue_code == "NET-006"
        assert issues[0].severity == ValidationSeverity.CRITICAL
        assert issues[0].blocking is True
        assert "A" in issues[0].activity_ids
        assert "B" in issues[0].activity_ids

    def test_three_activity_cycle_detected(self):
        v = NetworkValidator(
            [_act("A"), _act("B"), _act("C")],
            [_rel("A", "B"), _rel("B", "C"), _rel("C", "A")],
        )
        issues = v.check_circular_logic()
        assert len(issues) == 1
        assert len(issues[0].activity_ids) == 3

    def test_partial_cycle_only_cyclic_activities_listed(self):
        # D→E→D is a cycle; A→B→C is clean
        v = NetworkValidator(
            [_act("A"), _act("B"), _act("C"), _act("D"), _act("E")],
            [_rel("A", "B"), _rel("B", "C"), _rel("D", "E"), _rel("E", "D")],
        )
        issues = v.check_circular_logic()
        assert len(issues) == 1
        assert set(issues[0].activity_ids) == {"D", "E"}

    def test_self_loop_excluded_from_cycle_check(self):
        # Self-loop is caught by NET-009; cycle check excludes it
        v = NetworkValidator([_act("A")], [_rel("A", "A")])
        issues = v.check_circular_logic()
        # A self-loop is not a cycle in the Kahn sense; A still has in-degree 0
        # after excluding the self-loop, so it processes normally
        assert issues == []

    def test_isolated_activity_not_cyclic(self):
        v = NetworkValidator([_act("A")], [])
        assert v.check_circular_logic() == []

    def test_cyclic_activities_sorted(self):
        v = NetworkValidator(
            [_act("Z"), _act("A"), _act("M")],
            [_rel("Z", "A"), _rel("A", "M"), _rel("M", "Z")],
        )
        issues = v.check_circular_logic()
        assert issues[0].activity_ids == sorted(["Z", "A", "M"])

    def test_parallel_typed_relationships_do_not_create_false_cycle(self):
        """A legal FF+SS pair is one reachability edge for cycle detection."""
        activities = [_act("A"), _act("B")]
        relationships = [_rel("A", "B", "FF"), _rel("A", "B", "SS")]
        assert NetworkValidator(activities, relationships).check_circular_logic() == []
        assert topological_sort(ActivityNetwork(activities, relationships)) == ["A", "B"]

    def test_exact_duplicate_rows_do_not_create_net006_and_still_warn_net008(self):
        activities = [_act("A"), _act("B")]
        relationships = [_rel("A", "B"), _rel("A", "B")]
        validator = NetworkValidator(activities, relationships)
        assert validator.check_circular_logic() == []
        codes = {issue.issue_code for issue in validator.validate_all().issues}
        assert "NET-008" in codes
        assert "NET-006" not in codes
        assert topological_sort(ActivityNetwork(activities, relationships)) == ["A", "B"]

    def test_cycle_with_parallel_rows_still_detected(self):
        activities = [_act("A"), _act("B")]
        relationships = [
            _rel("A", "B", "FF"),
            _rel("A", "B", "SS"),
            _rel("B", "A", "FS"),
        ]
        issues = NetworkValidator(activities, relationships).check_circular_logic()
        assert len(issues) == 1
        assert issues[0].issue_code == "NET-006"
        with pytest.raises(ValueError, match="[Cc]ycle"):
            topological_sort(ActivityNetwork(activities, relationships))

    def test_all_pinned_cycle_is_allowed(self):
        activities = [
            Activity("A", original_duration=1,
                     pinned_early_start=date(2025, 3, 3),
                     pinned_early_finish=date(2025, 3, 3)),
            Activity("B", original_duration=1,
                     pinned_early_start=date(2025, 3, 4),
                     pinned_early_finish=date(2025, 3, 4)),
        ]
        relationships = [_rel("A", "B"), _rel("B", "A")]
        assert NetworkValidator(activities, relationships).check_circular_logic() == []
        assert set(topological_sort(ActivityNetwork(activities, relationships))) == {"A", "B"}

    def test_partially_pinned_network_with_unpinned_cycle_still_blocks(self):
        """Pinning an unrelated successor must not hide a remaining open cycle."""
        activities = [
            _act("A"),
            _act("B"),
            Activity("C", original_duration=1,
                     pinned_early_start=date(2025, 3, 3),
                     pinned_early_finish=date(2025, 3, 3)),
        ]
        relationships = [_rel("A", "B"), _rel("B", "A"), _rel("A", "C")]
        issues = NetworkValidator(activities, relationships).check_circular_logic()
        assert len(issues) == 1
        assert set(issues[0].activity_ids) == {"A", "B"}
        with pytest.raises(ValueError, match="[Cc]ycle"):
            topological_sort(ActivityNetwork(activities, relationships))

    def test_validator_and_engine_topology_have_same_cycle_verdict(self):
        """The validator and scheduler must agree on the same effective graph."""
        cases = [
            ([_act("A"), _act("B")], [_rel("A", "B", "FF"), _rel("A", "B", "SS")]),
            ([_act("A"), _act("B")], [_rel("A", "B"), _rel("A", "B")]),
            ([_act("A"), _act("B"), _act("C")],
             [_rel("A", "B"), _rel("B", "C")]),
            ([_act("A"), _act("B")], [_rel("A", "B"), _rel("B", "A")]),
            ([_act("A"), _act("B")],
             [_rel("A", "B", "FF"), _rel("A", "B", "SS"), _rel("B", "A")]),
        ]
        for activities, relationships in cases:
            validator_clean = not NetworkValidator(
                activities, relationships
            ).check_circular_logic()
            try:
                topological_sort(ActivityNetwork(activities, relationships))
            except ValueError:
                scheduler_clean = False
            else:
                scheduler_clean = True
            assert validator_clean is scheduler_clean, (
                f"validator/topological_sort disagreement for {relationships!r}"
            )


# ---------------------------------------------------------------------------
# NetworkValidator — check_network_topology (multi-start / multi-finish)
# ---------------------------------------------------------------------------

class TestCheckNetworkTopology:
    def test_single_start_single_finish_clean(self):
        v = NetworkValidator(
            [_act("S"), _act("M"), _act("F")],
            [_rel("S", "M"), _rel("M", "F")],
        )
        assert v.check_network_topology() == []

    def test_multiple_start_nodes_detected(self):
        v = NetworkValidator(
            [_act("A"), _act("B"), _act("C")],
            [_rel("A", "C"), _rel("B", "C")],
        )
        issues = v.check_network_topology()
        codes = {i.issue_code for i in issues}
        assert "NET-003" in codes   # aggregate
        assert "NET-001" in codes   # per-activity

    def test_multiple_start_nodes_reports_all_start_activities(self):
        v = NetworkValidator(
            [_act("A"), _act("B"), _act("C")],
            [_rel("A", "C"), _rel("B", "C")],
        )
        issues = v.check_network_topology()
        net003 = [i for i in issues if i.issue_code == "NET-003"]
        assert len(net003) == 1
        assert "A" in net003[0].activity_ids
        assert "B" in net003[0].activity_ids

    def test_multiple_finish_nodes_detected(self):
        v = NetworkValidator(
            [_act("A"), _act("B"), _act("C")],
            [_rel("A", "B"), _rel("A", "C")],
        )
        issues = v.check_network_topology()
        codes = {i.issue_code for i in issues}
        assert "NET-004" in codes   # aggregate
        assert "NET-002" in codes   # per-activity

    def test_multiple_finish_nodes_reports_all_finish_activities(self):
        v = NetworkValidator(
            [_act("A"), _act("B"), _act("C")],
            [_rel("A", "B"), _rel("A", "C")],
        )
        issues = v.check_network_topology()
        net004 = [i for i in issues if i.issue_code == "NET-004"]
        assert len(net004) == 1
        assert "B" in net004[0].activity_ids
        assert "C" in net004[0].activity_ids

    def test_no_issue_for_single_start_node(self):
        v = NetworkValidator([_act("A"), _act("B")], [_rel("A", "B")])
        issues = v.check_network_topology()
        codes = {i.issue_code for i in issues}
        assert "NET-001" not in codes
        assert "NET-003" not in codes

    def test_no_issue_for_single_finish_node(self):
        v = NetworkValidator([_act("A"), _act("B")], [_rel("A", "B")])
        issues = v.check_network_topology()
        codes = {i.issue_code for i in issues}
        assert "NET-002" not in codes
        assert "NET-004" not in codes

    def test_isolated_activity_produces_both_start_and_finish_issues(self):
        # Two isolated activities → each is a start AND finish node (2+2 = multi start+finish)
        v = NetworkValidator([_act("A"), _act("B")], [])
        issues = v.check_network_topology()
        codes = {i.issue_code for i in issues}
        assert "NET-003" in codes
        assert "NET-004" in codes

    def test_net002_explains_float_distortion_risk(self):
        v = NetworkValidator(
            [_act("A"), _act("B"), _act("C")],
            [_rel("A", "B"), _rel("A", "C")],
        )
        issues = v.check_network_topology()
        net002_issues = [i for i in issues if i.issue_code == "NET-002"]
        assert all("TF=0" in i.message or "float" in i.message.lower()
                   for i in net002_issues)


# ---------------------------------------------------------------------------
# NetworkValidator — validate_all (combined)
# ---------------------------------------------------------------------------

class TestValidateAll:
    def test_clean_network_returns_no_issues(self):
        v = NetworkValidator(
            [_act("A"), _act("B"), _act("C")],
            [_rel("A", "B"), _rel("B", "C")],
        )
        result = v.validate_all()
        assert result.is_clean

    def test_all_issues_collected_from_multiple_failing_checks(self):
        # Duplicate ID + truly invalid relationship type + cycle
        v = NetworkValidator(
            [_act("A"), _act("A"), _act("B")],
            [_invalid_rel("A", "B", "XX"), _rel("B", "A")],
        )
        result = v.validate_all()
        codes = {i.issue_code for i in result.issues}
        assert "NET-007" in codes   # duplicate ID
        assert "NET-005" in codes   # unsupported type "XX"

    def test_blocking_issues_identified_in_combined_result(self):
        v = NetworkValidator([_act("A"), _act("A")], [])
        result = v.validate_all()
        assert result.has_blocking_issues

    def test_validate_all_deterministic_same_inputs(self):
        acts = [_act("C"), _act("A"), _act("B")]
        rels = [_rel("A", "B"), _rel("A", "C")]
        r1 = NetworkValidator(acts, rels).validate_all()
        r2 = NetworkValidator(acts, rels).validate_all()
        assert [i.issue_code for i in r1.issues] == [i.issue_code for i in r2.issues]
        assert [i.activity_ids for i in r1.issues] == [i.activity_ids for i in r2.issues]

    def test_validate_all_summary_reflects_all_issues(self):
        v = NetworkValidator(
            [_act("A"), _act("B"), _act("C"), _act("D")],
            [_rel("A", "B"), _rel("A", "C"), _rel("A", "D")],
        )
        result = v.validate_all()
        summary = result.summary()
        total = sum(summary.values())
        assert total == len(result.issues)

    def test_empty_network_is_clean(self):
        v = NetworkValidator([], [])
        result = v.validate_all()
        assert result.is_clean

    def test_single_activity_no_relationships_is_clean(self):
        # Single activity with no relationships is a degenerate but valid network
        v = NetworkValidator([_act("A")], [])
        result = v.validate_all()
        # Single start + single finish → no topology issues
        codes = {i.issue_code for i in result.issues}
        assert "NET-003" not in codes
        assert "NET-004" not in codes

    def test_negative_duration_reported_not_blocking(self):
        v = NetworkValidator([_act("A", od=-5)], [])
        result = v.validate_all()
        assert result.has_errors
        assert not result.has_blocking_issues


# ---------------------------------------------------------------------------
# Determinism verification
# ---------------------------------------------------------------------------

class TestDeterministicOrdering:
    def test_same_issues_different_construction_order_same_result(self):
        # Add issues in different orders; sorting must produce same final list
        r1 = ValidationResult()
        r1.extend([
            _make_issue("NET-004", activity_ids=["Z"]),
            _make_issue("NET-003", activity_ids=["A", "B"]),
            _make_issue("NET-006", activity_ids=["X", "Y"]),
        ])
        r2 = ValidationResult()
        r2.extend([
            _make_issue("NET-006", activity_ids=["X", "Y"]),
            _make_issue("NET-003", activity_ids=["A", "B"]),
            _make_issue("NET-004", activity_ids=["Z"]),
        ])
        assert [i.issue_code for i in r1.issues] == [i.issue_code for i in r2.issues]

    def test_validate_all_ordering_is_stable(self):
        # Run the same validation 3 times; ordering must be identical
        acts = [_act("B"), _act("A"), _act("C"), _act("D")]
        rels = [_rel("A", "C"), _rel("B", "C"), _rel("C", "D")]
        results = [NetworkValidator(acts, rels).validate_all() for _ in range(3)]
        for attr in ("issue_code", "activity_ids"):
            values = [[getattr(i, attr) for i in r.issues] for r in results]
            assert values[0] == values[1] == values[2]


# ---------------------------------------------------------------------------
# Severity classification
# ---------------------------------------------------------------------------

class TestSeverityClassification:
    def test_duplicate_id_is_critical(self):
        v = NetworkValidator([_act("A"), _act("A")], [])
        issues = v.check_duplicate_activity_ids()
        assert all(i.severity == ValidationSeverity.CRITICAL for i in issues)

    def test_cycle_is_critical(self):
        v = NetworkValidator([_act("A"), _act("B")], [_rel("A", "B"), _rel("B", "A")])
        issues = v.check_circular_logic()
        assert all(i.severity == ValidationSeverity.CRITICAL for i in issues)

    def test_self_loop_is_critical(self):
        v = NetworkValidator([_act("A")], [_rel("A", "A")])
        issues = v.check_self_referential_relationships()
        assert all(i.severity == ValidationSeverity.CRITICAL for i in issues)

    def test_orphaned_rel_is_critical(self):
        v = NetworkValidator([_act("A")], [_rel("A", "MISSING")])
        issues = v.check_orphaned_relationships()
        assert all(i.severity == ValidationSeverity.CRITICAL for i in issues)

    def test_negative_duration_is_error(self):
        v = NetworkValidator([_act("A", od=-1)], [])
        issues = v.check_negative_durations()
        assert all(i.severity == ValidationSeverity.ERROR for i in issues)

    def test_missing_duration_is_error(self):
        v = NetworkValidator([_act("A", od=None)], [])
        issues = v.check_missing_durations()
        assert all(i.severity == ValidationSeverity.ERROR for i in issues)

    def test_invalid_relationship_type_is_warning(self):
        v = NetworkValidator([_act("A"), _act("B")], [_invalid_rel("A", "B", "XX")])
        issues = v.check_unsupported_relationship_types()
        assert len(issues) == 1
        assert all(i.severity == ValidationSeverity.WARNING for i in issues)

    def test_multiple_start_nodes_is_warning(self):
        v = NetworkValidator(
            [_act("A"), _act("B"), _act("C")],
            [_rel("A", "C"), _rel("B", "C")],
        )
        issues = v.check_network_topology()
        assert all(i.severity == ValidationSeverity.WARNING for i in issues)
