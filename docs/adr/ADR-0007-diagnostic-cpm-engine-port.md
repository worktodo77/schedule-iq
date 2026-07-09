# ADR-0007: Diagnostic CPM engine, ported from the LI MIP 3.9 tool

**Status:** accepted · **Date:** 2026-07-07 · **Amends:** ADR-0004

## Context
The v0.3+ analytical mission (issue-impact deltas, constraint-free
criticality, MIP 3.4 half-stepping, daily delay ledger, Monte Carlo) requires
recomputing schedule dates.  ADR-0004 (no CPM engine) was right for the v0.1
reporting mission and its core concern — a second source of truth
contradicting the schedule of record — remains valid.  Full analysis in
`docs/ANALYTICS_PROPOSAL.md` §0; plan of record also recorded in
expert-assist `PARKING_LOT.md` item B1.

## Decision
Amend ADR-0004, do not repeal it — and **port, do not build**:

1. The firm-owned MIP 3.9 tool's production CPM core (~4,400 SLOC: PDM
   forward/backward pass FS/SS/FF/SF with leads/lags, per-activity
   multi-calendar with exceptions, per-relationship lag-calendar resolution,
   actual-date-anchored statusing ("pinning", its ADR-019), AACE 49R-06
   longest-path tracing, network validation gate) is ported as
   `scheduleiq.cpm`, together with its ABCS destatusing package, its
   comparison-validation framework, its benchmark harness, and their test
   suites (~1,000 ported tests).  Port-and-validate: modules are byte-
   faithful except documented severances; provenance noted per module.
2. Gaps closed during the port: **LIM-028** (date constraints now scheduled
   — SNET/SNLT/FNET/FNLT/SO/FO/MS/MF/ALAP/XF, P6-compatible day-granularity
   semantics, all applications disclosed); **progress-override statusing
   mode** added alongside retained logic (net-new; the source is
   retained-logic only).  **LIM-045** (per-relationship lag calendars) was
   already resolved in the source scheduling pass; ScheduleIQ additionally
   maps the project's parsed `sched_calendar_on_relationship_lag`
   SCHEDOPTIONS value onto the engine's lag-calendar strategy.  **LIM-044**
   (calendar-day comparison tolerance) is carried, not fixed, and surfaces
   in the handshake tolerance configuration.
3. **Validation handshake** (the ADR-0004 risk converted into a check):
   before any engine-dependent feature runs, the engine re-schedules the
   file as imported — actual-date-anchored, honoring constraints and the
   project's scheduling options — and compares its computed dates/floats to
   the tool-of-record values stored in the file.  The match rate is reported
   (check **SET-02**); below the configured threshold (default 99%),
   engine-dependent features refuse to run and the mismatches are listed.
4. Presentation rule: tool-of-record dates remain the only dates reported as
   *the schedule*.  Engine output is always labeled a **diagnostic delta**
   ("removing X moves MS-100 by −12d"), never a competing schedule.
5. Wording discipline (from the source tool's ADR-006): results are a
   "P6-compatible analytical convention", never "exact P6 emulation".

## Consequences
- Engine-dependent backlog items (A2–A4, P5–P6, D9, N3, N4, M1–M4, C2)
  become buildable on a validated, firm-owned core.
- GOVERNANCE.md §7's "No CPM engine" disclosure is superseded by the
  handshake disclosure; DCMA-12's float-walk stays as the no-engine
  fallback and cross-check.
- The mirror of the source engine's own P6-equivalence validation (its
  MNFV/iiCON benchmark) cannot be re-run here — those XER inputs are
  case data and stay off-repo.  Its synthetic benchmark suites are ported
  and run in CI; re-validation against a real matter series is the principal's task
  L3 before first release.
