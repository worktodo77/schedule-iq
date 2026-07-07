"""
V1-G: Tests for comparison_validation/policies.py.

Covers:
  - ComparisonPolicy enum values
  - ComparisonPolicyConfig predicates (is_blocking_category, requires_checkpoint,
    requires_resolution)
  - STRICT: blocks on MATERIAL and UNKNOWN; checkpoints for all non-expected
  - GOVERNED: blocks on MATERIAL only; checkpoints for UNKNOWN but not blocking
  - ADVISORY: never blocks; checkpoints for material/unknown/behavioral
  - EXPERIMENTAL: never blocks; no checkpoints
  - get_comparison_policy_config() returns correct config per policy
"""

import os, sys
SRC = os.path.join(os.path.dirname(__file__), "..", "..", "src")
sys.path.insert(0, os.path.abspath(SRC))

import pytest

from scheduleiq.cpm.compare.divergences import DivergenceCategory  # noqa: E402
from scheduleiq.cpm.compare.policies import (  # noqa: E402
    ComparisonPolicy,
    ComparisonPolicyConfig,
    get_comparison_policy_config,
)


class TestComparisonPolicyEnum:

    def test_all_four_values_present(self):
        values = {p.value for p in ComparisonPolicy}
        assert "STRICT" in values
        assert "GOVERNED" in values
        assert "ADVISORY" in values
        assert "EXPERIMENTAL" in values


class TestStrictPolicy:

    def setup_method(self):
        self.cfg = get_comparison_policy_config(ComparisonPolicy.STRICT)

    def test_blocks_on_material(self):
        assert self.cfg.is_blocking_category(DivergenceCategory.MATERIAL_ANALYTICAL_DIFFERENCE) is True

    def test_blocks_on_unknown(self):
        assert self.cfg.is_blocking_category(DivergenceCategory.UNKNOWN_DIFFERENCE) is True

    def test_does_not_block_on_expected(self):
        assert self.cfg.is_blocking_category(DivergenceCategory.EXPECTED_DIFFERENCE) is False

    def test_does_not_block_on_float_method(self):
        assert self.cfg.is_blocking_category(DivergenceCategory.FLOAT_METHOD_DIFFERENCE) is False

    def test_checkpoint_for_material(self):
        assert self.cfg.requires_checkpoint(DivergenceCategory.MATERIAL_ANALYTICAL_DIFFERENCE) is True

    def test_checkpoint_for_calendar(self):
        assert self.cfg.requires_checkpoint(DivergenceCategory.CALENDAR_BEHAVIOR_DIFFERENCE) is True

    def test_checkpoint_for_lag(self):
        assert self.cfg.requires_checkpoint(DivergenceCategory.LAG_BEHAVIOR_DIFFERENCE) is True

    def test_checkpoint_for_float(self):
        assert self.cfg.requires_checkpoint(DivergenceCategory.FLOAT_METHOD_DIFFERENCE) is True

    def test_no_checkpoint_for_expected(self):
        assert self.cfg.requires_checkpoint(DivergenceCategory.EXPECTED_DIFFERENCE) is False

    def test_requires_resolution_material(self):
        assert self.cfg.requires_resolution(DivergenceCategory.MATERIAL_ANALYTICAL_DIFFERENCE) is True

    def test_requires_resolution_unknown(self):
        assert self.cfg.requires_resolution(DivergenceCategory.UNKNOWN_DIFFERENCE) is True

    def test_does_not_require_resolution_float(self):
        assert self.cfg.requires_resolution(DivergenceCategory.FLOAT_METHOD_DIFFERENCE) is False


class TestGovernedPolicy:

    def setup_method(self):
        self.cfg = get_comparison_policy_config(ComparisonPolicy.GOVERNED)

    def test_blocks_on_material(self):
        assert self.cfg.is_blocking_category(DivergenceCategory.MATERIAL_ANALYTICAL_DIFFERENCE) is True

    def test_does_not_block_on_unknown(self):
        assert self.cfg.is_blocking_category(DivergenceCategory.UNKNOWN_DIFFERENCE) is False

    def test_does_not_block_on_float(self):
        assert self.cfg.is_blocking_category(DivergenceCategory.FLOAT_METHOD_DIFFERENCE) is False

    def test_checkpoint_for_unknown(self):
        assert self.cfg.requires_checkpoint(DivergenceCategory.UNKNOWN_DIFFERENCE) is True

    def test_checkpoint_for_calendar(self):
        assert self.cfg.requires_checkpoint(DivergenceCategory.CALENDAR_BEHAVIOR_DIFFERENCE) is True

    def test_no_checkpoint_for_p6(self):
        assert self.cfg.requires_checkpoint(DivergenceCategory.P6_EMULATION_DIFFERENCE) is False

    def test_requires_resolution_material(self):
        assert self.cfg.requires_resolution(DivergenceCategory.MATERIAL_ANALYTICAL_DIFFERENCE) is True

    def test_does_not_require_resolution_unknown(self):
        assert self.cfg.requires_resolution(DivergenceCategory.UNKNOWN_DIFFERENCE) is False


class TestAdvisoryPolicy:

    def setup_method(self):
        self.cfg = get_comparison_policy_config(ComparisonPolicy.ADVISORY)

    def test_never_blocks_any_category(self):
        for cat in DivergenceCategory:
            assert self.cfg.is_blocking_category(cat) is False

    def test_checkpoint_for_material(self):
        assert self.cfg.requires_checkpoint(DivergenceCategory.MATERIAL_ANALYTICAL_DIFFERENCE) is True

    def test_checkpoint_for_unknown(self):
        assert self.cfg.requires_checkpoint(DivergenceCategory.UNKNOWN_DIFFERENCE) is True

    def test_no_checkpoint_for_expected(self):
        assert self.cfg.requires_checkpoint(DivergenceCategory.EXPECTED_DIFFERENCE) is False

    def test_requires_resolution_none(self):
        for cat in DivergenceCategory:
            assert self.cfg.requires_resolution(cat) is False


class TestExperimentalPolicy:

    def setup_method(self):
        self.cfg = get_comparison_policy_config(ComparisonPolicy.EXPERIMENTAL)

    def test_never_blocks(self):
        for cat in DivergenceCategory:
            assert self.cfg.is_blocking_category(cat) is False

    def test_no_checkpoints(self):
        for cat in DivergenceCategory:
            assert self.cfg.requires_checkpoint(cat) is False

    def test_no_resolution_required(self):
        for cat in DivergenceCategory:
            assert self.cfg.requires_resolution(cat) is False


class TestGetComparisonPolicyConfig:

    def test_returns_correct_type(self):
        cfg = get_comparison_policy_config(ComparisonPolicy.STRICT)
        assert isinstance(cfg, ComparisonPolicyConfig)

    def test_all_policies_have_configs(self):
        for policy in ComparisonPolicy:
            cfg = get_comparison_policy_config(policy)
            assert cfg.policy == policy

    def test_config_is_frozen(self):
        cfg = get_comparison_policy_config(ComparisonPolicy.STRICT)
        with pytest.raises((AttributeError, TypeError)):
            cfg.description = "tampered"  # type: ignore
