"""
INFRA-014: Phase 7 Validation Artifact Infrastructure.

Defines the provenance and artifact structures that wrap all validation
outputs. Every benchmark run, suite run, reproducibility check, and
regression analysis is wrapped in a ValidationArtifact so that the
full evidence chain is preserved.

Types:
  ValidationProvenance — engine version, benchmark version, convention, timestamp
  ValidationArtifact   — wrapper around any validation result with full provenance
  ArtifactRegistry     — in-memory artifact store for a validation session

Governance (ADR-009, ADR-010):
  - Every artifact has a unique, stable artifact_id.
  - Provenance is immutable after construction.
  - Artifact payloads are serialized dicts; no live engine objects.
  - Artifacts are created via factory classmethods, not direct construction.

Source: ADR-009 — Benchmark Governance; ADR-010 — Artifact Provenance.

Ported from the LI MIP 3.9 tool (mip39.validation_framework.artifacts) per ADR-0007 — port-and-validate.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from .benchmarks import BENCHMARK_FRAMEWORK_VERSION, ValidationSeverity
from ..context import ENGINE_VERSION
# mip39.xer is not ported; ScheduleIQ has its own ingest layer — substituting a local constant
# in place of mip39.xer.provenance.PARSER_VERSION.
PARSER_VERSION = "scheduleiq-ingest"


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------

@dataclass
class ValidationProvenance:
    """
    Immutable provenance record for a validation artifact.

    Fields:
        engine_version:            mip39 package version.
        benchmark_framework_version: Version of the benchmark framework.
        convention:                EFConvention value used in this run.
        parser_version:            XER parser version (from PARSER_VERSION constant).
        run_timestamp:             ISO 8601 UTC timestamp of the run.
    """
    engine_version: str
    benchmark_framework_version: str
    convention: str
    parser_version: str
    run_timestamp: str

    @classmethod
    def capture(cls, convention: str = "inclusive_day") -> "ValidationProvenance":
        """Create a provenance record from the current runtime state."""
        return cls(
            engine_version=ENGINE_VERSION,
            benchmark_framework_version=BENCHMARK_FRAMEWORK_VERSION,
            convention=convention,
            parser_version=PARSER_VERSION,
            run_timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "engine_version": self.engine_version,
            "benchmark_framework_version": self.benchmark_framework_version,
            "convention": self.convention,
            "parser_version": self.parser_version,
            "run_timestamp": self.run_timestamp,
        }


# ---------------------------------------------------------------------------
# Artifact
# ---------------------------------------------------------------------------

@dataclass
class ValidationArtifact:
    """
    Wrapper around a validation result with full provenance.

    An artifact is the permanent evidence record for one unit of validation
    work: a benchmark run, a suite run, a reproducibility check, or a
    regression analysis.

    Fields:
        artifact_id:    Unique identifier for this artifact (UUID4).
        artifact_type:  One of: "benchmark_run", "suite_run",
                        "reproducibility", "regression".
        provenance:     Immutable provenance captured at creation time.
        benchmark_id:   Benchmark that produced this artifact (or None for suites).
        suite_id:       Suite that produced this artifact (or None for single runs).
        passed:         Whether the validation passed.
        severity:       Maximum severity encountered.
        payload:        Serialized result dict (the full evidence record).
        created_at:     ISO 8601 UTC timestamp.
    """
    artifact_id: str
    artifact_type: str
    provenance: ValidationProvenance
    benchmark_id: Optional[str]
    suite_id: Optional[str]
    passed: bool
    severity: ValidationSeverity
    payload: dict[str, Any]
    created_at: str

    @classmethod
    def from_benchmark_run(
        cls,
        result: Any,   # BenchmarkRunResult
        provenance: Optional["ValidationProvenance"] = None,
    ) -> "ValidationArtifact":
        """Create an artifact from a BenchmarkRunResult."""
        prov = provenance or ValidationProvenance.capture(result.convention)
        return cls(
            artifact_id=str(uuid.uuid4()),
            artifact_type="benchmark_run",
            provenance=prov,
            benchmark_id=result.benchmark_id,
            suite_id=None,
            passed=result.passed,
            severity=result.severity,
            payload=result.to_dict(),
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    @classmethod
    def from_suite_run(
        cls,
        result: Any,   # SuiteRunResult
        provenance: Optional["ValidationProvenance"] = None,
    ) -> "ValidationArtifact":
        """Create an artifact from a SuiteRunResult."""
        prov = provenance or ValidationProvenance.capture()
        severity = (
            ValidationSeverity.INFORMATIONAL
            if result.passed
            else ValidationSeverity.ANALYTICAL
        )
        return cls(
            artifact_id=str(uuid.uuid4()),
            artifact_type="suite_run",
            provenance=prov,
            benchmark_id=None,
            suite_id=result.suite_id,
            passed=result.passed,
            severity=severity,
            payload=result.to_dict(),
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    @classmethod
    def from_reproducibility(
        cls,
        result: Any,   # ReproducibilityResult
        convention: str = "inclusive_day",
        provenance: Optional["ValidationProvenance"] = None,
    ) -> "ValidationArtifact":
        """Create an artifact from a ReproducibilityResult."""
        prov = provenance or ValidationProvenance.capture(convention)
        severity = (
            ValidationSeverity.INFORMATIONAL
            if result.passed
            else ValidationSeverity.CRITICAL
        )
        return cls(
            artifact_id=str(uuid.uuid4()),
            artifact_type="reproducibility",
            provenance=prov,
            benchmark_id=result.benchmark_id,
            suite_id=None,
            passed=result.passed,
            severity=severity,
            payload=result.to_dict(),
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    @classmethod
    def from_regression(
        cls,
        result: Any,   # RegressionResult
        convention: str = "inclusive_day",
        provenance: Optional["ValidationProvenance"] = None,
    ) -> "ValidationArtifact":
        """Create an artifact from a RegressionResult."""
        from .regression import ApprovalStatus
        prov = provenance or ValidationProvenance.capture(convention)
        passed = (
            not result.has_regression
            or result.approval_status == ApprovalStatus.APPROVED
        )
        return cls(
            artifact_id=str(uuid.uuid4()),
            artifact_type="regression",
            provenance=prov,
            benchmark_id=result.benchmark_id,
            suite_id=None,
            passed=passed,
            severity=result.max_severity,
            payload=result.to_dict(),
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "artifact_type": self.artifact_type,
            "provenance": self.provenance.to_dict(),
            "benchmark_id": self.benchmark_id,
            "suite_id": self.suite_id,
            "passed": self.passed,
            "severity": self.severity.value,
            "payload": self.payload,
            "created_at": self.created_at,
        }


# ---------------------------------------------------------------------------
# Artifact registry
# ---------------------------------------------------------------------------

class ArtifactRegistry:
    """
    In-memory artifact store for a single validation session.

    Records all artifacts created during a session so that the full evidence
    trail is available for review. Not persisted beyond the process lifetime;
    callers serialise the registry to_dict() for durable storage.

    Governance (ADR-010):
      - Each artifact is stored exactly once by artifact_id.
      - Records are immutable after storage (no update or delete).
      - list_by_type() returns artifacts in insertion order.
    """

    def __init__(self) -> None:
        self._store: dict[str, ValidationArtifact] = {}
        self._insertion_order: list[str] = []

    def record(self, artifact: ValidationArtifact) -> str:
        """
        Store an artifact. Returns the artifact_id.

        Raises:
            ValueError: If an artifact with the same artifact_id already exists.
        """
        if artifact.artifact_id in self._store:
            raise ValueError(
                f"ArtifactRegistry: artifact_id {artifact.artifact_id!r} already "
                "exists. Artifact IDs must be unique within a session."
            )
        self._store[artifact.artifact_id] = artifact
        self._insertion_order.append(artifact.artifact_id)
        return artifact.artifact_id

    def get(self, artifact_id: str) -> Optional[ValidationArtifact]:
        """Return the artifact with the given ID, or None if not found."""
        return self._store.get(artifact_id)

    def list_by_type(self, artifact_type: str) -> list[ValidationArtifact]:
        """Return all artifacts of the given type in insertion order."""
        return [
            self._store[aid]
            for aid in self._insertion_order
            if self._store[aid].artifact_type == artifact_type
        ]

    def all_artifacts(self) -> list[ValidationArtifact]:
        """Return all artifacts in insertion order."""
        return [self._store[aid] for aid in self._insertion_order]

    def summary(self) -> dict[str, Any]:
        """Return a summary dict with counts by type and pass/fail status."""
        total = len(self._store)
        passed = sum(1 for a in self._store.values() if a.passed)
        by_type: dict[str, int] = {}
        for a in self._store.values():
            by_type[a.artifact_type] = by_type.get(a.artifact_type, 0) + 1
        return {
            "total_artifacts": total,
            "passed": passed,
            "failed": total - passed,
            "by_type": by_type,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary(),
            "artifacts": [
                self._store[aid].to_dict() for aid in self._insertion_order
            ],
        }
