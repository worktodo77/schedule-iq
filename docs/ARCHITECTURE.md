# ScheduleIQ Architecture

## Purpose

ScheduleIQ replaces Deltek Acumen Fuse for Long International's schedule
intake, quality, health, trend, and change analysis: ingest one or many
Primavera P6 (.xer) or Microsoft Project (.mpp / MSPDI .xml) files, run a
documented, referenced battery of checks, and produce LI-house-style Word/PDF
reports plus detailed Excel workbooks with trend charts.

## Design principles

1. **The matrix is the product.**  Every check lives in
   `src/scheduleiq/metrics/matrix.yaml` with its formula, default threshold,
   severity, and literature reference.  The engine runs nothing undocumented
   and reports documented-but-unimplemented checks as NOT EVALUATED.  This is
   what makes results defensible in an expert-witness context: any figure in a
   report traces to a named check, a published standard, and a recorded
   threshold.
2. **One canonical model.**  All parsers normalize into
   `ingest/model.py` dataclasses; metrics, trend, comparison, and reporting
   never see format-specific structures.  Durations/floats are carried in
   hours (P6-native) and converted to days through each activity's own
   calendar — never a global 8h/day assumption.
3. **Read-only and reproducible.**  ScheduleIQ never modifies source files;
   it records their SHA-256 in every output and appends a structured audit
   line per run (`audit.py`), so every reported number is reproducible from
   hash-identified inputs plus a tool version.
4. **Lightweight core, optional heft.**  The core is pure Python + openpyxl +
   matplotlib.  The GUI (PySide6), native .mpp (MPXJ + JRE), and PDF
   conversion (Word) are optional extras; the packaged Windows installer
   bundles all of them so analysts get the full capability with zero setup.
5. **Word is the layout source of truth.**  The .docx (built on the firm's
   `LI_report_base.docx` template) is canonical; PDF is a conversion of it,
   never a parallel re-implementation of the house style (ADR-0005).

## Module map

```
src/scheduleiq/
├── ingest/                 # format -> canonical model
│   ├── model.py            #   Schedule/Activity/Relationship/Calendar/...
│   ├── xer.py              #   P6 XER (pure Python, incl. calendar blobs,
│   │                       #   SCHEDOPTIONS scheduling settings)
│   ├── msp_xml.py          #   MSPDI XML (pure Python)
│   └── mpp.py              #   .mpp via MPXJ -> MSPDI -> msp_xml (optional)
├── metrics/
│   ├── matrix.yaml         #   THE check inventory (rendered to docs/)
│   ├── engine.py           #   matrix loader, registry, evaluate(), scoring
│   └── checks/core.py      #   implementations keyed to matrix IDs
├── compare/diff.py         # version-to-version change register
├── trend/series.py         # ordering, same-project detection, series checks
├── report/
│   ├── excel.py            #   per-file workbook, trend workbook (+charts),
│   │                       #   benchmark workbook
│   ├── charts.py           #   matplotlib PNGs for the Word report
│   ├── docx_li.py          #   LI template-injection .docx writer
│   ├── report_builder.py   #   narrative + tables + figures -> report
│   └── pdf.py              #   docx -> pdf (Word, else LibreOffice)
├── runner.py               # end-to-end orchestration (CLI + GUI share it)
├── audit.py                # JSONL audit log (inputs hashed, params, outputs)
├── cli.py                  # scheduleiq analyze|matrix|gui
└── gui/app.py              # PySide6 desktop app
```

## Data flow

```
files (.xer/.xml/.mpp)
   └─ ingest.load_many() ──> [Schedule]                 (parse warnings kept)
        └─ trend.analyze_series()
             ├─ order_and_validate()     auto-order by data date; flag
             │                           files that don't look like the
             │                           same project (analyst confirms)
             ├─ metrics.evaluate() per file ──> ScheduleAssessment
             │     (matrix-driven; threshold overrides recorded)
             ├─ compare.compare() per consecutive pair ──> ChangeSet
             └─ series checks (TRD-*/EVM-*) from assessments + changesets
   └─ runner.run()
        ├─ report.excel      per-file workbooks, trend workbook, benchmark
        ├─ report.report_builder  LI .docx (+ charts.py figures)
        ├─ report.pdf        .docx -> .pdf
        └─ audit.append_audit
```

## Key mechanisms

### Check populations
DCMA-style checks operate on **incomplete tasks + milestones excluding
LOE/hammock/WBS-summary/MSP-summary rows**, matching DCMA/PASEG practice, so
numbers are comparable to Fuse and to other tools an opposing expert may run.
Each result carries numerator, denominator, the offender list (activity IDs +
detail), the threshold applied, and its provenance (standard default vs
analyst override).

### Health score
A weighted pass/fail triage aid over evaluated checks (critical checks weigh
2×, warnings score half credit).  It intentionally differs from Fuse's
record-based Schedule Index (which scores activities, not checks); both are
triage aids, not opinions.  See `docs/METHODOLOGY.md`.

### Trend and change
`compare.diff` matches activities on activity code (the identifier that
survives export), and classifies changes: added/deleted activities, logic
added/deleted/modified, original-duration edits (flagged when made to
in-progress/completed work), planned-date shifts, constraint/calendar/status
changes, float deltas, critical-set membership — and, most importantly for
forensic intake, **retroactive changes to previously reported actual dates**.
`trend.series` aggregates these into the series checks (float erosion,
critical-path stability, logic churn, forecast slippage, Hit Task %, CEI).

### Critical path caveat
ScheduleIQ deliberately contains **no CPM scheduling engine**: it analyzes
the values the scheduling tool computed, and the DCMA-12 continuity test is a
minimum-float-walk proxy with a documented instruction to confirm material
findings with a +600d perturbation in P6/MSP.  Recomputing CPM dates would
create a second source of truth that could disagree with the tool of record —
exactly what an expert must avoid (ADR-0004).

## Packaging

- **Source**: `pip install .[gui,mpp,pdf]` for developers.
- **Analysts**: PyInstaller one-folder Windows build with PySide6, MPXJ + a
  bundled JRE, and the LI template; produced by GitHub Actions on tag, zipped
  as `ScheduleIQ-<version>-windows.zip` (see `installer/` and
  `.github/workflows/build.yml`).  No admin rights needed (portable folder
  with a Start-menu shortcut script).
