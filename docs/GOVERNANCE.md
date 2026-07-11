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
- **Number-changing revisions of a proprietary index** (a change to its basis,
  outputs, or timing that alters the numbers a matter would quote) additionally
  require a **recorded ruling** in `docs/rulings/` carrying the approved rulings,
  any supersession/retirement records, and the audited before→after on a probe
  set — the full governance package (spec + matrix row + seeded fixtures +
  regression tests + recorded ruling) moves together.  Prior regression anchors
  invalidated by such a change are marked provisional/ungraded until
  recalibrated.  See `docs/rulings/LI-01-fcbi-v0.5.md` for the LI-01 v0.5
  precedent.

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

- No CPM engine: float/dates are analyzed as computed by the tool of record
  (ADR-0004); multi-calendar float caveats are flagged by CP-01/CAL-02.
- Baseline-dependent checks (DCMA-11/13/14, Hit Task %) use the file's
  planned/baseline dates; if the XER lacks a linked baseline, the planned
  (target) dates stand in and the report says so via the matrix formula text.
- .mpp reading depends on MPXJ fidelity; when in doubt, request an MSPDI
  export and compare (the canonical model makes the two directly comparable).
- P6 XML (.xml P6 export) is not yet ingested (ADR-0002 tracks it).
