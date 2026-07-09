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
- N3 daily-resolution delay ledger: day-by-day rescheduling between update
  pairs on linearly interpolated remaining durations, per-day critical-path
  delta with controlling activity, exact telescoping identity (sum of daily
  deltas equals the endpoint movement, asserted), reconciliation against
  as-imported runs and record dates, event annotation (D6) and observational
  responsibility subtotals (D7); handshake-gated.
- N4 methodology-robustness certificate: variant grid over framing
  (MIP 3.4 half-step / MIP 3.3 as-is / N3 daily), statusing (retained vs
  override), window boundaries (±1 update), and contested-revision
  exclusion; observational per-party allocation with disclosed heuristics;
  stability stats + STABLE/MODERATE/UNSTABLE banding and the §8.4
  stability sentence per party; memoized engine reuse across variants.
- M1/M2/M4 Monte Carlo (SRA) core: triangular/PERT/uniform via inverse-CDF
  (stdlib-pure beta-PERT), Latin Hypercube sampling, systemic correlation
  (rank-blend, disclosed approximation), Bernoulli risk events; three input
  tiers with per-activity provenance — templates, 3-point CSV, and
  empirical calibration from the project's own actual÷planned ratio history
  (bootstrap or fitted lognormal); percentiles vs deterministic and record
  dates, TF≤0 criticality index, Spearman cruciality/tornado, merge-bias
  gap; SRA-readiness gate (leads/hard-constraints/open-ends screens →
  READY / DIAGNOSTIC ONLY branding / REFUSED via the SET-02 handshake).
- M3 + forensic outputs: LI-style S-curve and tornado figures, SRA workbook
  (gate verdict, percentiles, criticality/cruciality, provenance, sample);
  half-step bridge figure with per-class attribution inset (hatched
  residual), daily-ledger cumulative curve, robustness range plot;
  forensic workbook (half-step, attribution, MIP 3.3, ledger,
  responsibility subtotals, certificate, disclosures); all wired into the
  run and the Word report with per-block refusal messages.  Suite: 1839
  tests + 1 skip.

## 0.4.0 — 2026-07-07

The principal's approval of 2026-07-07 ("build all items awaiting my call") green-lit
N16-N20, RC6 publication, and all PARKED items.  Check-affecting change:
matrix expanded to 79 checks (LI-11..LI-15, privileged/internal surfaces).

- N16-N20 (LI-11..15): SMI Schedule Manipulation Indicator (published
  12-point weighting over the seeded curation signals, innocent-explanation
  text per signal, language capped at "warrants explanation"), DDI Directed
  Date Index, ARR Attribution Robustness Ratio (per-party min/max share
  across the N4 sweep), PPS Pacing Plausibility Score (neutral-on-missing
  evidence), RSA Rebuttal Surface Area.  All privileged/internal by default:
  RC5 internal card + internal workbook only; never on standard surfaces.
- S6 TIA workbench: event→fragnet auto-build (MIP 3.6/3.7) with stepped
  cumulative insertion (marginals telescope exactly), collapsed as-built
  (MIP 3.8/3.9) via the ported MIP 3.9 collapse engine (GLOBAL/STEPPED,
  calibration gate and OOS block carried faithfully — no auto-acknowledge).
- S7 damages overlay: LD-rate and time-cost exposure lines with the
  arithmetic always shown, optional exposure axis/sheets on every impact,
  forensic, and SRA surface; None-config outputs byte-identical.
- RC6: publication package built and verified (Apache-2.0, stamped spec
  SHA-256, reference scorer validated against a sample, internal variant
  stripped from the public copy).  Public push remains a human step.
- N1 weather overlay: offline GHCN-Daily reader (ADR-0006 — no network),
  calendar-realism test (embedded downtime vs 10-year weather norm),
  per-window abnormal-weather exceedance with weather-sensitive slippage
  overlay, exhibit rows presented both ways (better-than-norm windows
  listed); thresholds analyst-overridable.
- N2 work-pattern reconstruction: de facto calendars per trade/WBS
  (planned-vs-observed divergence), weekend/overtime detection, dormancy
  on near-critical spans, work-intensity heatmap data.
- S5 editing-session forensics: XER create/update user+date capture (new
  optional ingest fields), session clustering (30-min/day fallback), bulk-
  before-claim / unusual-user / logic-with-actuals flags, driving-path edit
  share, editing-timeline exhibit rows; innocent explanations + language
  cap; degrades cleanly on sanitized exports.  New demo_edit fixture pair.
- F3 P6 XML (PMXML) native ingestion with .xml root-sniff dispatch (MSPDI
  unchanged), version-agnostic namespace handling, full-fidelity mapping
  (constraint slots, schedule options incl. lag calendar, calendars with
  exceptions); F5 Asta/Phoenix routed through the MPXJ bridge (conditional).
- F1 ribbon analyzer (per-WBS/group offender densities + severity-weighted
  group scores), F2 phase analyzer (time-phased problem clustering),
  F4 per-period start/finish compliance (0d/7d tolerances, commitment
  reliability, named late offenders; distinct from cumulative Hit Task %).
- S8 interactive HTML cockpit: one self-contained file (no external
  requests; ADR-0006), time-scaled driving/near-critical network with
  zoom/pan, update slider with churn annotations, findings click-through;
  ~64 KB on the demo series.
- Test hardening: xlsx byte-identity comparisons exclude the openpyxl
  docProps timestamp member (flake fix).
- S9 internal benchmark corpus: local append-only JSONL of anonymized
  per-project outcomes (blocklist-asserted before write), percentile
  context lines with small-n refusal; S10 offline duration priors:
  empirical quantiles + lognormal MLE with KS statistic + Kaplan-Meier
  right-censoring adjustment, exposed only as Monte Carlo empirical-tier
  inputs and internal diagnostics behind the governance wall (provenance
  threads into simulation disclosures; LLM narratives expressly out of
  scope).

## 0.4.1 — 2026-07-08

Check-affecting: **FCBI (LI-01) definition change** per the peer-reviewed audit
(docs/audit/FCBI_audit_2026-07-08.md; confirmed by Codex).  FCBI values move on
any series with completed near-critical activities and/or float that changed
criticality within a window — the LI-01 anchor recalibration against real files
stays open (a pre-existing L3 task); the demo-series Report Card grades shift
accordingly (scorecard tests assert internal consistency, not absolute grades,
so remain green).

- **Completed activities excluded** from both FCBI+ (burn) and FCBI− (recovery):
  the index now measures float consumed by *in-flight* work only.  Removes the
  exporter-dependent phantom burn (a completed activity whose tool-of-record
  float was written 0 rather than null no longer scores its whole prior float
  as burn).  Aligns FCBI with RDI/BWI; CDI intentionally still counts completed
  activities as retrospective criticality dwell (documented).
- **Weight timing** now samples RF as **min(RF at u-1, RF at u)** across the
  window, so burn that itself drove a chain critical is weighted at that
  criticality rather than at its floaty start.
- **Normalized FCBI%** returns a labelled "stock exhausted — interpret absolute
  FCBI+" reason instead of a bare None when the weighted live float stock ≤ 0.
- Every FCBI result now carries standing methodology **disclosures** (completed
  exclusion, min-RF timing, top-10 RF provenance, windowing non-additivity).
- matrix.yaml LI-01 wording + §9.1 conventions updated; 7 new governance tests
  (completed-invariance, min-RF timing, RF basis fallback, windowing
  non-additivity, sentinel, cross-index, disclosures).  Suite: 2069 passed.
