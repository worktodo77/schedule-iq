# ADR-0006: Fully offline; no telemetry or cloud benchmarking

**Status:** accepted · **Date:** 2026-07-06

## Context
Fuse offers cloud benchmarking (anonymized score upload).  LI handles
privileged, confidential dispute material.

## Decision
ScheduleIQ makes no network calls of any kind.  Cross-project benchmarking is
local (benchmark mode over files the analyst selects).  Audit logs stay in
the run's output folder.

## Consequences
- Zero data-handling risk from the tool itself; simpler security review.
- No global benchmark statistics — accepted; the firm can build an internal
  benchmark corpus from its own matters if desired.
