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
