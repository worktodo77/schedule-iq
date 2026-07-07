# Governance

ScheduleIQ produces analysis that feeds expert work product.  These rules keep
it defensible.

## 1. Methodology control

- The Metric & Heuristic Matrix (`src/scheduleiq/metrics/matrix.yaml`,
  rendered to `docs/METRIC_MATRIX.md`) is the single authoritative statement
  of what the software checks, how, against which threshold, and on whose
  authority.  **Any change to a check's formula, threshold, population, or
  reference requires a pull request that updates the matrix, the
  implementation, and the tests together**, and a note in CHANGELOG.md.
- Default thresholds are the published standard values and are never edited
  casually; genuinely contested defaults get an ADR.
- Analyst threshold overrides are per-run, live in profile files, and are
  stamped on every output ("analyst override" vs "standard default").  The
  software never silently deviates from the published defaults.

## 2. Reproducibility and audit

- Every run appends a JSON line to `<output>/audit/audit_log.jsonl`:
  timestamp (UTC), operator, host, tool version, parameters, input files with
  SHA-256 hashes, outputs, and summary counts.
- Reports print the input hashes and the tool version; a third party with the
  same files and version must be able to reproduce every number.
- ScheduleIQ is read-only with respect to source schedules.

## 3. Interpretation discipline

- Outputs are **schedule-mechanics observations**, not opinions.  Report
  language (built into `report_builder.py`) expressly reserves causation,
  entitlement, concurrency, and quantum to the expert, and states that a
  flagged exception "is a matter for explanation and review, and is not,
  without more, evidence of impropriety."
- The health score is a triage aid (docs/METHODOLOGY.md); it must never be
  quoted as an opinion on schedule adequacy.
- DCMA-12 (critical path continuity) findings are a proxy; material findings
  are confirmed manually per the matrix note before they appear in expert
  work product.

## 4. Versioning and releases

- Semantic versioning.  The version is stamped in reports, workbooks, and the
  audit log.
- Releases are built only by CI from tagged commits; analysts install the
  signed release zip, never ad-hoc builds.  CHANGELOG.md records
  check-affecting changes so an expert can state which checks changed between
  versions used on a matter.

## 5. Data handling

- Case schedules never leave the analyst's machine: ScheduleIQ runs fully
  offline (no telemetry, no cloud benchmarking — deliberate difference from
  Fuse's Acumen Cloud).  Outputs inherit the matter's confidentiality and
  privilege handling.

## 6. Quality gates

- CI runs the full pytest suite (every check asserted against seeded-defect
  fixtures) on every push; releases require green tests.
- New checks require: matrix row with reference → implementation → seeded
  fixture defect → test.  A check without a citable reference does not ship.

## 7. Known limitations (disclose when relevant)

- Diagnostic CPM engine (ADR-0007, supersedes the ADR-0004 "no CPM engine"
  disclosure): a firm-owned CPM core is ported as `scheduleiq.cpm` and used only
  as a **diagnostic**.  The tool-of-record dates and float stored in the file
  remain the only values reported as *the schedule*; engine output is always a
  labelled diagnostic delta, never a competing schedule.  Before any
  engine-dependent feature runs, the engine re-schedules the file as imported
  (actual-date-anchored, honoring its date constraints and scheduling options)
  and its computed dates/floats are compared to the record — check **SET-02**
  (the validation handshake).  Below the configured threshold (default 99%),
  SET-02 gates: engine-dependent features refuse to run and the mismatches are
  listed.  DCMA-12's float-walk stays as the no-engine fallback and cross-check;
  multi-calendar float caveats are flagged by CP-01/CAL-02.
- Baseline-dependent checks (DCMA-11/13/14, Hit Task %) use the file's
  planned/baseline dates; if the XER lacks a linked baseline, the planned
  (target) dates stand in and the report says so via the matrix formula text.
- .mpp reading depends on MPXJ fidelity; when in doubt, request an MSPDI
  export and compare (the canonical model makes the two directly comparable).
- P6 XML (.xml P6 export) is not yet ingested (ADR-0002 tracks it).
