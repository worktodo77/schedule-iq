# Changelog

Check-affecting changes are listed explicitly (GOVERNANCE.md §1) so an expert
can state which checks changed between versions used on a matter.

## 0.1.0 — 2026-07-06

Initial release.

- Canonical schedule model; parsers for P6 .xer (native), MSPDI .xml
  (native), and .mpp (via MPXJ, optional/bundled in installer).
- Metric & Heuristic Matrix v1: 54 checks — DCMA 14-Point (all 14), logic &
  network quality (9), constraints (3), float (2), duration & estimating (3),
  status & date integrity (4), calendars (3), resources & cost (2), structure
  & critical path (4), trend & change series checks (10, incl. Hit Task % and
  CEI).  Default thresholds per published standards.
- Trend analysis across updates; version-to-version change register with
  retroactive actual-date detection.
- Outputs: LI house-style Word report, PDF via Word/LibreOffice conversion,
  per-file Excel workbooks, trend workbook with native charts, benchmark
  workbook; JSONL audit log with SHA-256 input hashes.
- PySide6 desktop GUI (drag-and-drop, auto-ordering with same-project
  detection, threshold profile editor, results drill-down) and CLI.
- CI: tests + tagged Windows PyInstaller release build.

## 0.2.0 — 2026-07-07

- Matrix expanded to 73 checks: 8 forensic checks (SET-01, CAL-04, LOG-10,
  DUR-04 two-branch, STR-03, DAT-05, REL-01, FLT-03), CAL-05, and the ten
  LI proprietary indices (LI-01..LI-10: FCBI, LHL, FRB, PCI, RDI, BDI, CDI,
  IL, BWI, MML).
- Path analytics: driving-path extraction (float-first), top-N float paths,
  proximity profile, merge ranking, path stability with progress-vs-revision
  attribution.
- Intake accelerator pack (D1-D8): scorecard + RFI generator, variance
  register, float ledger, windows auto-segmentation, concurrency screen,
  delay-event mapper, responsibility overlay, evergreen detector.
- Statistical screens (Benford/round-number/KS drift/progress physics),
  earned schedule (ES(t), SPI(t), TSPI(t), IEAC(t)).
- Pacing and constructive-acceleration screens; narrative reconciliation
  (CONSISTENT/DISCREPANT/RECORD-REWRITTEN/UNMATCHED).
- LI Schedule Report Card (spec LI-RC v1.0, scorecard.yaml): per-file and
  series cards with categories, integrity gates, top-factors decomposition,
  score_trace.json, report first page + workbook; public-spec package
  prepared (unpublished).
- Reproducibility capsule (hash manifest + rerun script) on every run.
- Fixture correction: seeded logic deletion now fires (was silently
  mistyped); DUR-04 evergreen and driving-path defects found in audit and
  fixed.  162-test suite.

## 0.3.0 — 2026-07-07

The engine release (ADR-0007; amends ADR-0004).  Check-affecting change:
matrix expanded to 74 checks (SET-02 added).

- `scheduleiq.cpm`: the LI MIP 3.9 tool's production CPM core ported
  (port-and-validate, ~1,500 ported tests carried): PDM forward/backward
  pass (FS/SS/FF/SF, leads/lags), per-activity multi-calendar with
  exceptions, per-relationship lag-calendar resolution, actual-date-anchored
  statusing (pinning), AACE 49R-06 longest-path tracing, network validation
  gate, ABCS destatusing (six CPW rules + auto-drive + actual-lag analysis),
  comparison-validation framework, and benchmark harness (PHASE7 12/12;
  MULTI_CALENDAR 3/7 in both source and port — pre-existing source baseline,
  flagged for review).
- Date-constraint scheduling added (closes source LIM-028):
  SNET/SNLT/FNET/FNLT/SO/FO/MS/MF/ALAP/XF, P6-compatible analytical
  convention at day granularity; every application disclosed; hard
  constraints yield disclosed negative float.
- Progress Override statusing mode added alongside Retained Logic (net-new;
  the source engine is retained-logic only).
- Ingest→engine bridge honoring the file's own scheduling options,
  including SCHEDOPTIONS `sched_calendar_on_relationship_lag` →
  lag-calendar strategy (source LIM-045 companion).
- **SET-02 (new check)**: the ADR-0007 validation handshake — the engine
  re-schedules the file as imported and the match rate against the
  tool-of-record dates/floats is reported (threshold 99%, severity info;
  refusal gate for engine-dependent features).  LIM-044 carried: tolerance
  is calendar-day based (TOLERANCE_CALENDAR_AWARE default).
- New fixtures demo_cpm.xer (handshake 100.0%) and demo_cpm_divergent.xer
  (exactly 75.0%, three seeded +5wd shifts).  Suite: 1683 tests + 1 skip.
- Tool-of-record dates remain the only dates reported as the schedule;
  engine output is always a labelled diagnostic delta (GOVERNANCE §7).
- Engine-dependent analytics (A2-A4, P5, P6): issue-impact overlay with
  per-constraint waterfall attribution and float-absorbed accounting;
  retained-logic vs progress-override milestone delta; constraint-free
  criticality (manufactured/masked sets); as-built path reconstruction with
  actual-lag traceability and contradicted-logic evidence; milestone
  diagnostic waterfall one-pager + impact workbook + as-built figure, wired
  into the run (handshake-gated; refusal reported, never an error) and the
  Word report.  All engine numbers labelled diagnostic deltas (ADR-0007).
- D9 MIP 3.4 half-step engine: per-update-pair bifurcation of milestone
  movement into progress vs revision effects (identity exact by
  construction), NAMED revision attribution from the change register
  (per-class re-application with an honestly reported interaction residual,
  top movers per class), progress contributors, MIP 3.3 as-is row;
  handshake-gated; new engine-consistent fixture pair demo_hs1/demo_hs2.
