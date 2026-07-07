# Acumen Fuse Capability Parity

Where ScheduleIQ stands against Deltek Acumen Fuse, feature by feature.
Fuse facts per Deltek documentation and training material (see REFERENCES.md,
key FUSE).

| Fuse capability | ScheduleIQ status |
|---|---|
| Schedule Quality metric group (Missing Logic, Logic Density, Critical, Hard Constraints, Negative Float, Insufficient Detail, Lags, Leads, Merge Hotspot) | ✅ All nine implemented (DCMA-01/-05/-07, LOG-05/-06, FLT-01, DCMA-02/-03/-08); matrix rows name the Fuse equivalent |
| DCMA 14-Point Assessment group | ✅ All 14 (DCMA-12 as documented continuity proxy — Fuse's +600d simulation requires a CPM engine; see ADR-0004) |
| Advanced logic checks (open ends, dangling starts/finishes, SF, redundancy, links via summary/LOE) | ✅ DCMA-01, LOG-01/02/03/04/08/09 |
| Constraints / float / duration / dates / status groups | ✅ CON-*, FLT-*, DUR-*, DAT-*, plus P6-specific checks Fuse lacks (Expected Finish, suspend/resume, DD-vs-export currency) |
| Baseline compliance group (BEI, missed tasks, start/finish compliance) | ✅ DCMA-11/-14, EVM-01 Hit Task %, TRD-08 plan-date changes; per-period start/finish compliance variants planned (backlog) |
| Execution metrics (CPLI, BEI, CEI, Hit Task %) | ✅ DCMA-13/-14, EVM-01/-02 |
| Tripwire thresholds (unit and percentage), editable | ✅ Matrix defaults + per-run analyst profiles, provenance stamped; multi-band color scales are simplified to PASS/WARNING/FAIL + severity |
| Fuse Schedule Index (weighted scoring, record- and metric-based) | ✅ Check-weighted health score (metric-based analogue); documented difference in METHODOLOGY.md |
| Ribbon Analyzer (group-by field/WBS) | ◻ Backlog — engine keeps offender lists with WBS ids, so per-WBS ribbons are a straightforward aggregation |
| Phase Analyzer (time-phased slicing) | ◻ Backlog (series trending covers the time dimension across updates; intra-schedule phase slicing planned) |
| Forensics / schedule comparison (added/deleted, logic, durations, progress, constraints, calendars, float, critical membership) | ✅ compare/diff.py change register + Excel change sheets; plus retroactive-actuals detection Fuse surfaces less directly |
| Half-step (progress vs revisions) analysis | ◻ Backlog — requires a CPM engine or P6 round-trip (ADR-0004) |
| Benchmarking across projects | ✅ Benchmark mode (side-by-side workbook); no cloud database by design (confidentiality — GOVERNANCE.md §5) |
| Dashboards / publish to Word, Excel, PDF | ✅ LI-house-style Word + PDF, Excel workbooks with native charts (LI style beats Fuse's generic output for our purpose); interactive dashboard = the GUI results tree |
| Inputs: P6 XER | ✅ native |
| Inputs: P6 XML, MSP MPP/XML | ✅ .mpp via MPXJ (bundled in installer), MSPDI native; P6 XML backlog (ADR-0002) |
| Inputs: Asta, Phoenix, Open Plan, Safran, Excel | ◻ Not planned for v1 (MPXJ can read Asta/Phoenix — enable on demand) |
| Risk (Acumen Risk), 360 acceleration | ✖ Out of scope — different product tier; SRA-readiness checks (leads/lags/constraints/open ends) are covered |

Legend: ✅ shipped · ◻ backlog · ✖ out of scope.
