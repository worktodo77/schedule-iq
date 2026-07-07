# ADR-0003: Matrix-driven check engine

**Status:** accepted · **Date:** 2026-07-06

## Context
The check inventory is the product's professional core; it must be reviewable
by non-programmers (experts), citable in reports, and impossible to drift
from the implementation silently.

## Decision
A YAML matrix (id, category, description, formula, unit, default threshold,
direction, severity, references, Fuse equivalent, applicability) is loaded at
runtime; implementations register against matrix IDs.  The engine runs only
matrix rows and reports unimplemented rows as NOT EVALUATED.  Thresholds are
overridable per run via profiles, with provenance recorded on every result.

## Consequences
- Adding a check = matrix row + registered function + fixture defect + test.
- The rendered matrix doubles as the methodology exhibit for expert reports.
- A stale matrix is impossible: it is the runtime configuration, not
  documentation about it.
