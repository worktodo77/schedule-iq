"""
INFRA-015: Phase 7 Reproducibility Verification.

Implements deterministic reproducibility checks for the CPM engine.
Repeated analysis runs on identical inputs must produce byte-for-byte
identical serialized outputs. Any deviation indicates a non-determinism
defect that must be resolved before production or forensic use.

Types:
  ReproducibilityResult — result of an n-run repeatability check

Class:
  ReproducibilityChecker — runs a benchmark n times and compares hashes

Governance (ADR-009):
  - Reproducibility is verified by SHA-256 hashing of the serialized
    BenchmarkRunResult.to_dict() with sorted keys.
  - All n run hashes must be identical for the check to pass.
  - Any discrepancy is recorded with the differing hash values.
  - timestamp fields are excluded from the hash because they legitimately
    differ between runs (analysis_id and analysis_timestamp in AnalysisContext).

Source: ADR-005 §7 (determinism requirement); ADR-009 — Benchmark Governance.

Ported from the LI MIP 3.9 tool (mip39.validation_framework.reproducibility) per ADR-0007 — port-and-validate.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


# ---------------------------------------------------------------------------
# Result structure
# ---------------------------------------------------------------------------

@dataclass
class ReproducibilityResult:
    """
    Result of an n-run reproducibility check for a single benchmark.

    Fields:
        benchmark_id:   Benchmark that was checked.
        n_runs:         Number of times the benchmark was executed.
        passed:         True when all n run hashes are identical.
        run_hashes:     SHA-256 hash of each run's serialized result.
        discrepancies:  Human-readable descriptions of any hash differences.
        run_timestamp:  ISO 8601 UTC timestamp of the check.
    """
    benchmark_id: str
    n_runs: int
    passed: bool
    run_hashes: list[str]
    discrepancies: list[str] = field(default_factory=list)
    run_timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "benchmark_id": self.benchmark_id,
            "n_runs": self.n_runs,
            "passed": self.passed,
            "run_hashes": list(self.run_hashes),
            "discrepancies": list(self.discrepancies),
            "run_timestamp": self.run_timestamp,
        }


# ---------------------------------------------------------------------------
# Checker
# ---------------------------------------------------------------------------

# Fields that legitimately differ between runs and must be excluded from hashing.
# analysis_id: random UUID per run
# analysis_timestamp: current UTC time per run
# run_timestamp: captured by the harness per run
_EXCLUDED_TOP_KEYS = frozenset({
    "run_timestamp",
})

_EXCLUDED_CONTEXT_KEYS = frozenset({
    "analysis_id",
    "analysis_timestamp",
})


class ReproducibilityChecker:
    """
    Verifies that repeated engine runs on identical inputs produce identical outputs.

    Usage:
        checker = ReproducibilityChecker()
        result = checker.check(benchmark_definition, harness, n_runs=5)

    The checker runs the benchmark n times via the provided harness,
    hashes each result after stripping legitimately-varying fields,
    and checks that all hashes match.
    """

    def check(
        self,
        benchmark: Any,           # BenchmarkDefinition
        harness: Any,             # ValidationHarness
        n_runs: int = 3,
    ) -> ReproducibilityResult:
        """
        Run the benchmark n_runs times and verify all results are identical.

        Args:
            benchmark: BenchmarkDefinition to execute.
            harness:   ValidationHarness to use for execution.
            n_runs:    Number of times to run the benchmark (minimum 2).

        Returns:
            ReproducibilityResult with pass/fail status and any discrepancies.

        Raises:
            ValueError: If n_runs < 2.
        """
        if n_runs < 2:
            raise ValueError(
                f"ReproducibilityChecker: n_runs must be >= 2; got {n_runs}."
            )

        run_hashes: list[str] = []
        for _ in range(n_runs):
            result = harness.run_benchmark(benchmark)
            run_hashes.append(self._hash_result(result))

        reference_hash = run_hashes[0]
        discrepancies: list[str] = []
        for i, h in enumerate(run_hashes[1:], start=2):
            if h != reference_hash:
                discrepancies.append(
                    f"Run {i} hash {h[:12]}... differs from run 1 hash "
                    f"{reference_hash[:12]}... — non-determinism detected."
                )

        return ReproducibilityResult(
            benchmark_id=benchmark.metadata.benchmark_id,
            n_runs=n_runs,
            passed=len(discrepancies) == 0,
            run_hashes=run_hashes,
            discrepancies=discrepancies,
        )

    @staticmethod
    def _hash_result(result: Any) -> str:
        """
        Compute a stable SHA-256 hash of a BenchmarkRunResult.

        Legitimately varying fields (analysis_id, analysis_timestamp,
        run_timestamp) are stripped before hashing to avoid false positives.

        Returns: Hex-encoded SHA-256 digest.
        """
        payload = result.to_dict()

        # Strip top-level varying fields
        for key in _EXCLUDED_TOP_KEYS:
            payload.pop(key, None)

        # Strip context fields that vary per run
        actual = payload.get("actual_output", {})
        ctx = actual.get("context", {})
        for key in _EXCLUDED_CONTEXT_KEYS:
            ctx.pop(key, None)

        serialized = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
