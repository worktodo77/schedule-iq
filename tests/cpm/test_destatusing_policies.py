"""
Tests for V1-D: Policy architecture (DestatusingPolicy, DSTpolicyConfig).

Covers:
  - All four policies have entries in POLICY_CONFIGS
  - is_blocking() and requires_checkpoint() behave per policy spec
  - STRICT_FORENSIC blocks at ANALYTICAL_RISK, checkpoints at WARNING
  - ADVISORY_ONLY never blocks
  - get_policy_config() returns correct config
"""

from __future__ import annotations

import os, sys
SRC = os.path.join(os.path.dirname(__file__), "..", "..", "src")
sys.path.insert(0, os.path.abspath(SRC))

import pytest

from scheduleiq.cpm.destatusing import (  # noqa: E402
    DestatusingPolicy,
    DSTpolicyConfig,
    POLICY_CONFIGS,
    get_policy_config,
)
from scheduleiq.cpm.severity import DiagnosticSeverity  # noqa: E402


class TestPolicyEnum:
    def test_all_four_policies_defined(self):
        values = {p.value for p in DestatusingPolicy}
        assert "strict_forensic" in values
        assert "advisory_only" in values
        assert "cpw_compatibility" in values
        assert "aggressive_normalization" in values

    def test_policy_configs_has_all_policies(self):
        for policy in DestatusingPolicy:
            assert policy in POLICY_CONFIGS


class TestStrictForensic:
    @pytest.fixture
    def config(self):
        return get_policy_config(DestatusingPolicy.STRICT_FORENSIC)

    def test_blocks_at_analytical_risk(self, config):
        assert config.is_blocking(DiagnosticSeverity.ANALYTICAL_RISK)

    def test_does_not_block_at_warning(self, config):
        assert not config.is_blocking(DiagnosticSeverity.WARNING)

    def test_checkpoints_at_warning(self, config):
        assert config.requires_checkpoint(DiagnosticSeverity.WARNING)

    def test_checkpoints_at_analytical_risk(self, config):
        assert config.requires_checkpoint(DiagnosticSeverity.ANALYTICAL_RISK)

    def test_does_not_checkpoint_at_advisory(self, config):
        assert not config.requires_checkpoint(DiagnosticSeverity.ADVISORY)

    def test_does_not_checkpoint_at_informational(self, config):
        assert not config.requires_checkpoint(DiagnosticSeverity.INFORMATIONAL)

    def test_requires_analyst_review_on_no_match(self, config):
        assert config.require_analyst_review_on_no_match is True

    def test_does_not_allow_pc_formula_interpretation(self, config):
        assert config.allow_pc_formula_interpretation is False


class TestAdvisoryOnly:
    @pytest.fixture
    def config(self):
        return get_policy_config(DestatusingPolicy.ADVISORY_ONLY)

    def test_never_blocks(self, config):
        for sev in DiagnosticSeverity:
            assert not config.is_blocking(sev)

    def test_checkpoints_at_analytical_risk(self, config):
        assert config.requires_checkpoint(DiagnosticSeverity.ANALYTICAL_RISK)

    def test_does_not_checkpoint_at_warning(self, config):
        assert not config.requires_checkpoint(DiagnosticSeverity.WARNING)

    def test_does_not_require_review_on_no_match(self, config):
        assert config.require_analyst_review_on_no_match is False

    def test_allows_pc_formula(self, config):
        assert config.allow_pc_formula_interpretation is True


class TestCPWCompatibility:
    @pytest.fixture
    def config(self):
        return get_policy_config(DestatusingPolicy.CPW_COMPATIBILITY)

    def test_blocks_at_analytical_risk(self, config):
        assert config.is_blocking(DiagnosticSeverity.ANALYTICAL_RISK)

    def test_checkpoints_at_warning(self, config):
        assert config.requires_checkpoint(DiagnosticSeverity.WARNING)

    def test_allows_pc_formula(self, config):
        assert config.allow_pc_formula_interpretation is True


class TestAggressiveNormalization:
    @pytest.fixture
    def config(self):
        return get_policy_config(DestatusingPolicy.AGGRESSIVE_NORMALIZATION)

    def test_never_blocks(self, config):
        for sev in DiagnosticSeverity:
            assert not config.is_blocking(sev)

    def test_does_not_require_review_on_no_match(self, config):
        assert config.require_analyst_review_on_no_match is False

    def test_allows_pc_formula(self, config):
        assert config.allow_pc_formula_interpretation is True


class TestDSTpolicyConfigFrozen:
    def test_frozen(self):
        config = get_policy_config(DestatusingPolicy.STRICT_FORENSIC)
        with pytest.raises((AttributeError, TypeError)):
            config.block_at = None  # type: ignore[misc]

    def test_description_is_non_empty(self):
        for policy in DestatusingPolicy:
            config = get_policy_config(policy)
            assert len(config.description) > 10

    def test_get_policy_config_correct_policy(self):
        for policy in DestatusingPolicy:
            config = get_policy_config(policy)
            assert config.policy == policy
