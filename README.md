# ScheduleIQ

Schedule quality, health, trend, and change analysis for Primavera P6 (.xer)
and Microsoft Project (.mpp / MSPDI .xml) — Long International's replacement
for Deltek Acumen Fuse, built for schedule intake ahead of delay analysis.

## What it does

- **Ingests one or many schedule files** (drag-and-drop GUI or CLI); multiple
  files are auto-ordered by data date and validated as updates of the same
  project (or run side-by-side in benchmark mode).
- **Runs a documented battery of 54 checks** — the full DCMA 14-Point
  Assessment plus logic, constraint, float, duration, status/date-integrity,
  calendar, resource, structure, and forensic-intake checks — every one
  defined in the [Metric & Heuristic Matrix](docs/METRIC_MATRIX.md) with its
  formula, default threshold, severity, and literature reference (DCMA, GAO,
  NASA, NDIA PASEG, AACE 29R-03/78R-13, SCL Protocol, Fuse parity, P6
  forensic practice).
- **Trend analysis across updates**: health-score and metric trends, float
  erosion, critical-path stability, logic churn, forecast slippage, Hit Task
  %, CEI.
- **Version-to-version change register**: activities added/deleted, logic
  added/deleted/modified, duration edits, constraint/calendar/status changes,
  and retroactive changes to previously reported actual dates.
- **Outputs**: Long International house-style Word report (and PDF via Word),
  a detailed Excel workbook per file, and a trend workbook with native Excel
  charts; every run appends a hash-stamped audit log line.

## Quick start (source)

```bash
pip install .[gui]            # add [mpp] for native .mpp, [pdf] for Word PDF
scheduleiq gui                                    # desktop app
scheduleiq analyze u1.xer u2.xer u3.xer -o out/   # CLI
scheduleiq matrix                                 # print the check matrix
```

Analysts: install the Windows build from the Releases page instead — it
bundles everything including native .mpp support (see
[docs/INSTALL.md](docs/INSTALL.md)).

## Documentation

| Doc | Contents |
|---|---|
| [docs/METRIC_MATRIX.md](docs/METRIC_MATRIX.md) | Every check, formula, threshold, reference (generated from `matrix.yaml`) |
| [docs/REFERENCES.md](docs/REFERENCES.md) | Full citations for the standards behind the matrix |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Design, module map, data flow |
| [docs/GOVERNANCE.md](docs/GOVERNANCE.md) | Methodology control, audit, versioning, limitations |
| [docs/METHODOLOGY.md](docs/METHODOLOGY.md) | Populations, health score, baseline semantics |
| [docs/FUSE_PARITY.md](docs/FUSE_PARITY.md) | Feature-by-feature status vs Acumen Fuse |
| [docs/adr/](docs/adr/) | Architecture decision records |

## Development

```bash
pip install -e .[gui,dev]
python tests/fixtures/make_fixtures.py     # regenerate seeded-defect fixtures
pytest                                     # 22 tests, all checks asserted
python scripts/render_matrix.py            # re-render METRIC_MATRIX.md
```

Governance rule: a check changes only when the matrix row, implementation,
and tests change together — see [docs/GOVERNANCE.md](docs/GOVERNANCE.md).

*Proprietary — Long International internal use.*
