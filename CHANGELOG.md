# Changelog

## 0.5.0 — 2026-07-14

- Ported the governed FCBI v0.5 methodology: target-specific nonnegative
  distance, B/C/W decomposition, quarantine and coverage, basis-change
  segmentation, endpoint-timing sensitivity, and fixed-reference-hour margins.
- Added the exact lazy float-path enumerator and mixed-calendar frontier
  regression; reconciled target/activity identity to the UID-first R-ID rule.
- Retired FCBI% and the old weighted-RF/own-float fallback; LI-01 is
  provisional/ungraded pending recalibration of its new gross-burn anchors.
  The recorded scorecard re-pin therefore holds: demo file grades remain
  C+/C/D and the demo series remains D.

## 0.4.7 — 2026-07-14

Check-affecting: **R-ID provocative extension**. The LI-12 DDI target, the
LI-14 §6.3 pacing screen, and the N4 responsibility allocation feeding LI-13
ARR / LI-15 RSA now carry persistent activity identity UID-first across update
re-codes; analyst-facing codes remain display labels with legacy UID-less
fallback only. The existing provocative arithmetic and privileged/weight-0
surfaces are unchanged.

- Added UID-stable re-code regression coverage for DDI, pacing/PPS, half-step
  progress overlay, and N4 party allocation.
- Matrix LI-12..LI-15 rows now state the UID-first identity contract.

Check-affecting changes are listed explicitly (GOVERNANCE.md §1) so an expert
can state which checks changed between versions used on a matter.

## 0.4.6 — 2026-07-14

Check-affecting: **R-ID family identity implementation** from
docs/plans/li_family_rulings_2026-07-14.md. The shared change register and the
portable BDI/IL/MML/FRB lookups now match activities and relationship endpoints
by persistent UID first; codes remain display labels. Code fallback is limited
to an unambiguous legacy row with no UID. A pure UID-stable re-code is not a
change; a different present UID is a true replacement (added/deleted).

- Added UID/re-code regression coverage for the shared register and all four
  affected LI metrics.
- The matrix-lineage-only LOE, basis, kernel, and other parallel-branch changes
  are intentionally not duplicated on this branch.

Check-affecting changes are listed explicitly (GOVERNANCE.md §1) so an expert
can state which checks changed between versions used on a matter.

## 0.4.5 — 2026-07-09

Check-affecting: **four LHL (LI-02) defect fixes** from the LHL audit
(docs/audit/LHL_audit_2026-07-09.md), ruled by the methodology owner; each ships
with the governance quartet.  LI-02 is a scored member — the demo series LI-02
moves (see below); the pinned demo letter grades (C+/C/D per file, D for the
series) held.  One audit item (L5, LOE population) is deferred pending a
second-opinion methodology review and is NOT included here.

- **L1 — scoring branch inversion.** `_li02_score` awarded full marks when the
  median was not reached only if `censored_frac < 10%` (i.e. >90% of logic had
  died) — the inverse of the spec ("< 10% *died* = too stable to estimate a
  half-life = 100").  Now branches on the DIED fraction; the config key
  `censored_pass_threshold` is renamed `died_pass_threshold`.  The demo series
  (27/28 censored, median not reached) now scores LI-02 = **100**, not 70.
- **L2 — death timing off-by-one.** A relationship death is now dated to the
  first update in which the tie is absent/modified (event time = last-present +
  1); a tie that survived one update interval no longer registers as dying at
  age 0.  Censoring times are unchanged.  Understated half-lives corrected.
- **L3 — signatures keyed by UID, not code.** Relationship identity is keyed by
  `(pred_uid, succ_uid, type)` (matching `Relationship.key()`), so re-coding an
  activity is no longer a spurious death; a type change still is.  The on/off
  driving-path edge set was moved to UIDs in lockstep (else the whole cohort
  would collapse to off-path).  Mirrors the BWI-B2 fix.
- **L4 — on/off ratio guard.** `on_off_ratio` is published only when BOTH cohort
  medians were genuinely reached (`on_off_ratio_reached`), with a disclosure
  when suppressed — a ratio of two not-reached lower bounds is not a bound.
- **L6 — standing disclosures.** `LHLResult` now carries methodology disclosures
  (UID identity, mean-interval months conversion, death-timing, birth-time
  on/off classification, first-pair exclusion, censoring %, and that LOE ties
  are currently included pending the L5 ruling).
- 5 new regression tests (scoring died-fraction, death timing, re-code vs type
  change, ratio suppression, disclosures).  Full suite: 2087 passed, 2 skipped.
- Governance quartet: matrix LI-02 row + scorecard.yaml (key rename) + impl
  (scorecard.py, li_record.py) + tests; public_spec/scorecard.yaml regenerated.
- **DEFERRED (not implemented):** L5 (exclude LOE/summary ties from the LHL
  population) — spec-consistent as-is per §9.2; routed for a methodology
  second opinion before ruling.

## 0.4.4 — 2026-07-09

**R1 resolution (LI-05, RDI): planned-scope basis affirmed; companion
duration-overrun ratio added.**  Ruled by the methodology owner on the
recommendation of one independent reviewer and the concurrence (with
modifications) of a second.  The RDI accrual mathematics are UNCHANGED — no
scored number moves; the release adds a disclosed diagnostic output and
resolves the spec ambiguity.

- **Demonstrated pace** is affirmed as planned near-critical scope actually
  retired (completions, at original duration) per calendar working-day — the
  only basis commensurable with required pace.  The earlier "actual elapsed"
  direction was reconsidered and reversed on dimensional grounds: an
  elapsed-time denominator is concurrency-non-additive (five parallel
  on-pace activities would read as phantom recovery debt) and an elapsed-time
  numerator rewards overruns.  §9.5 reworded; the reversal is recorded in the
  audit doc.
- **Companion duration-overrun ratio** (Σ actual elapsed working days ÷
  Σ planned duration of the same completions) added to `RdiResult` per window
  (`RdiRow.overrun_ratio`) and for the series (`RdiResult.overrun_ratio`),
  with a standing disclosure that it is an efficiency diagnostic and never an
  accrual input.  Completions lacking an actual start are omitted from the
  ratio and surfaced as a DATA QUALITY disclosure.
- 2 new regression tests: the five-parallel concurrency case (demonstrated
  pace 2.5 with companion ratio 2.0 — the case where an elapsed basis would
  have manufactured debt) and a 3-window overrun case (zero-completion windows
  depress the P50 anchor; window ratio 3.0; missing-actual-start degrades to
  None + disclosure, never a guess).

## 0.4.3 — 2026-07-09

Check-affecting: **three bespoke-metric methodology rulings** from the
RDI/BWI/CDI audit's deferred set (docs/audit/RDI_BWI_CDI_audit_2026-07-08.md),
ruled by the methodology owner.  Each ships with the full governance quartet
(matrix row + implementation + seeded fixture + tests).  Scored members LI-05
(RDI) and LI-09 (BWI) move on real data; the pinned demo letter grades
(C+/C/D per file, D for the series) held, so the scorecard suite stays green.

- **B1 — BWI fixed reference horizon (LI-09).** BWI now normalizes near-critical
  density against a FIXED denominator — working days from the first update's
  data date to the target's constrained (promised) date, else baseline finish,
  else first-update forecast finish — held constant across updates.  A slipping
  milestone with unchanged work now reads BWI = 1.0 (the old moving-forecast
  denominator mis-read a slip as relief).  Demo BWI: [1.0, 0.833, 0.661].
- **R2 — RDI accrues against P50, not max (LI-05).** Debt accrues when required
  pace exceeds the running P50 (median, sustainable) demonstrated pace; the
  running max is retained as the reported optimistic bound.  The old max-only
  anchor under-accrued.  Demo RDI: 161.1 working days.
- **Mixed-path LOE neutralization (kernel: LI-01/04/05/07/09).** The LI kernel
  now computes each kept path's relative float over its DISCRETE members only,
  so an LOE that is the lowest-float member of a mixed path no longer drives the
  discrete members' RF.  Layered on top of `float_paths()`, which is UNCHANGED —
  a purely additive `unique_uids` field was exposed on `FloatPath` and the LI
  kernel reads it; no tool-of-record driving-path result shifts.  This supersedes
  the v0.4.2 disclosed residual (the prior residual-lock test is replaced by a
  neutralization test).
- 3 new/updated regression tests (BWI fixed-horizon slip, RDI P50-vs-max accrual,
  kernel LOE neutralization).  Full suite: 2080 passed, 2 skipped.
- R1 (RDI demonstrated-pace basis) remained open at 0.4.3 and was resolved in
  0.4.4 (see below): the earlier "actual elapsed" direction was reconsidered on
  dimensional grounds and the planned-scope basis affirmed, with the overrun
  signal shipped as a companion disclosure ratio.

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
stays open (a pre-existing L3 task).  The demo-series FCBI figures shift (e.g.
cumulative burn) and so does LI-01's weighted contribution to the Report Card;
the scorecard tests do not pin absolute FCBI values or absolute numeric grades
(they combine trace self-consistency checks with fixture letter-grade
expectations — C+/C/D per file, D for the series), and those pinned letters
held stable across the change, so the suite stays green.

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

## 0.4.2 — 2026-07-08

Correctness / consistency / governance update per the RDI/BWI/CDI audit
(docs/audit/RDI_BWI_CDI_audit_2026-07-08.md).  Approved rulings C1, C2, B2, X1
implemented; B1, R1, R2 remain open methodology decisions and are NOT included.

Check-affecting: **LOE/summary exclusion across the LI criticality kernel.**
LOE, WBS-summary, hammock, and other summary activities are not discrete work
and no longer contribute to the proprietary indices that measure criticality,
float consumption, recovery, or criticality-time.

- **C1 — LOE exclusion.** Enforced at the shared kernel (`relative_float_map`
  drops summary activities from the RF/weight map; `_build_kernel` drops float
  paths with no discrete-work member).  FCBI additionally carries an explicit
  LOE guard on burn/recovery/denominator; CDI inherits the kernel exclusion.
  PCI no longer counts LOE-only / bare-milestone paths (a single-threaded
  schedule with an LOE feeder now reads 1.0, not 0.5).  FCBI/PCI/CDI numbers
  shift on any series containing near-critical LOE; the pinned demo letter
  grades (C+/C/D) held.  RDI and BWI already excluded LOE (unchanged).
- **C2 — CDI documentation.** No behavioral change: §10.2, the LI-07 matrix
  row, and a new CDI disclosure state that completed activities are retained
  because CDI measures retrospective criticality-time.
- **B2 — BWI target robustness.** The target milestone is pinned by persistent
  UID (resolved from the first update) and located by UID-then-code in each
  later update, so it survives re-coding/renaming.  BWI mathematics unchanged.
- **X1 — data-quality disclosures.** RDI, BWI, and CDI now carry standing
  disclosures (LOE exclusion, dependence on remaining durations / project
  finish / target finish) and emit a DATA-QUALITY note when those inputs are
  absent; numerical behavior preserved.
- Full shared-kernel family audit (metric-by-metric) in the audit doc's
  resolution note: MML already excluded LOE; DDI already guards it;
  BDI/IL/LHL/FRB do not consume the kernel/RF map (BDI/IL flagged for a future
  LOE ruling, not implemented here).
- 7 new regression tests (kernel/CDI/FCBI/PCI LOE exclusion, BWI rename
  survival, disclosures).  Suite: 2069 passed, 2 skipped.
- NOT changed: BWI/RDI mathematics, kernel equations, RF calculations, the
  deferred B1 (fixed BWI denominator), R1 (actual-vs-planned demonstrated
  pace), R2 (P50 comparator).

**Validation follow-up (no code / no number change).**  Independent peer review
of the v0.4.2 validation added two regression locks and a disclosure, closing
the remaining review items:

- **All-milestone graceful lock** (`test_pci_all_milestone_schedule_graceful`):
  a schedule with no discrete executable work drops every kernel path and PCI
  degrades to `None` (never a spurious concentration figure) without raising.
- **PCI mixed-path residual lock** (`test_pci_mixed_path_loe_residual_is_intentional`):
  pins the *deferred* behavior that a kept mixed path (real work + LOE) still
  takes its relative float from the shared `float_paths()`, so an LOE that is the
  lowest-float member still drives that path's relative float and the discrete
  member's RF.  The lock fails if the residual is ever removed inside
  `float_paths()`, flagging it as an actioned methodology decision rather than a
  regression.
- **§9.4 disclosure** records the residual as an intentional deferred item and
  that any full LOE neutralization inside mixed paths must be an LI-specific
  kernel/path calculation, never a change to the shared `float_paths()` (which
  feeds tool-of-record driving-path analytics outside the LI indices).
- Validation report filed at `docs/audit/v0.4.2_validation_2026-07-09.md`.
