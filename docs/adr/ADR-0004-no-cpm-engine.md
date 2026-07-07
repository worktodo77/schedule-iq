# ADR-0004: No embedded CPM scheduling engine

**Status:** accepted · **Date:** 2026-07-06

## Context
Some Fuse capabilities (the +600d critical path test, half-step analysis)
require recomputing schedule dates.  A reimplemented CPM engine will never
match P6/MSP exactly (calendars, lag calendars, retained-logic subtleties,
leveling), creating a second source of truth.

## Decision
ScheduleIQ analyzes the dates and floats computed by the scheduling tool of
record and does not reschedule.  DCMA-12 is implemented as a minimum-float
continuity walk with an explicit instruction to confirm material findings by
perturbation inside P6/MSP.  Half-step analysis stays out of scope until a
P6 round-trip workflow exists.

## Consequences
- No risk of the tool contradicting the schedule of record — essential for
  expert work.
- A small set of Fuse parity items remain manual (documented in
  FUSE_PARITY.md).
