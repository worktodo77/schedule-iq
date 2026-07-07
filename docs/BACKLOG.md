# ScheduleIQ Backlog — the to-do list of record

Single authoritative to-do list.  Status: **APPROVED** = green-lit by RJL for
build; **PARKED** = proposed, awaiting decision; **BLOCKED** = needs an
external action.  Sources: v0.1 build, ANALYTICS_PROPOSAL.md (§ refs),
FUSE_PARITY.md, and review decisions of 2026-07-06/07.

## 0. Logistics / blocked

| # | Item | Status | Notes |
|---|---|---|---|
| L1 | Migrate repo: push full history to worktodo77/schedule-iq | DONE (v0.3) | Imported at commit c0a64bf on main (2026-07-07); development history preserved on expert-assist branch `claude/acumen-fuse-replacement-ler9kq`; mirror synced until RJL confirms |
| L2 | Add `mip39-schedule-analysis-tool` to session scope | DONE (v0.3) | In session scope 2026-07-07; engine port complete |
| L3 | Validate against a real matter .xer series; review sample outputs | APPROVED | RJL, on return from vacation |
| L4 | First tagged release → CI Windows bundle; circulate installer to firm experts | APPROVED | After L3 sign-off |

## 1. Core engine (v0.3 centerpiece)

| # | Item | Status | Notes |
|---|---|---|---|
| E1 | Port MIP 3.9 CPM engine as `scheduleiq.cpm` (PORT-AND-VALIDATE per expert-assist parking-lot B1) | DONE (v0.3) | Core + destatusing + compare + benchmark ported with ~1,500 tests; PHASE7 suite 12/12 (MULTI_CALENDAR 3/7 matches source baseline — flagged); real-file validation = L3 |
| E2 | Close LIM-028: constraint scheduling in the ported engine | DONE (v0.3) | SNET/SNLT/FNET/FNLT/SO/FO/MS/MF/ALAP/XF with disclosure log; hard constraints yield disclosed negative float |
| E3 | Close LIM-045: per-relationship lag calendars | DONE (v0.3) | Source scheduling pass already resolved per-relationship lag resources; bridge maps parsed SCHEDOPTIONS setting → LagCalendarStrategy |
| E4 | Validation handshake + SET-02 check (tool-of-record vs engine match rate; features refuse below threshold) | DONE (v0.3) | run_handshake/require_valid_handshake; SET-02 (74-check matrix); LIM-044 carried (calendar-day tolerance, CALENDAR_AWARE default) |
| E5 | Retained-logic / progress-override statusing modes in engine | DONE (v0.3) | StatusingMode enum; PROGRESS_OVERRIDE net-new (source is retained-logic only); default bit-identical regression-guarded |

## 2. Milestone impact tracing (§1)

| # | Item | Status |
|---|---|---|
| A1 | Driving-path extraction + path fingerprint table (no engine) | DONE (v0.2 wave 1) |
| A2 | Issue-impact overlay: constraint-free delta, calendar-neutral float restatement, leads/lags deltas, expected-finish release | APPROVED |
| A3 | Milestone diagnostic waterfall (one-page exhibit, selectable target) | APPROVED |
| A4 | OOS retained-logic vs progress-override milestone delta | APPROVED |

## 3. Multi-path analytics (§2)

| # | Item | Status |
|---|---|---|
| P1 | Top-N float paths to selected target (composition, calendars, constraints) | DONE (v0.2 wave 1) |
| P2 | Path proximity profile (near-critical band distribution) | DONE (v0.2 wave 1) |
| P3 | True merge-point ranking (converging near-critical paths) | DONE (v0.2 wave 1) |
| P4 | Path stability across updates with progress-vs-revision attribution + path-timeline chart | DONE (v0.2 wave 1) |
| P5 | Constraint-free criticality (manufactured-criticality exposure) | APPROVED (needs E1) |
| P6 | As-built path reconstruction (ABCS core from ported engine) | APPROVED (needs E1) |

## 4. Delay-analysis accelerators (§3)

| # | Item | Status |
|---|---|---|
| D1 | Data-completeness scorecard + client RFI list generator | DONE (v0.2 wave 2) |
| D2 | As-planned vs as-built variance register | DONE (v0.2 wave 2) |
| D3 | Float consumption ledger + erosion-by-window chart | DONE (v0.2 wave 2) |
| D4 | Windows auto-segmentation (cadence + CP change points + revision events) | DONE (v0.2 wave 2) |
| D5 | Concurrency screening (co-slipping near-critical paths per window) | DONE (v0.2 wave 2) |
| D6 | Delay-event mapper (CSV events → activities → fragnet candidates) | DONE (v0.2 wave 2) |
| D7 | Responsibility overlay (Owner/Contractor/Neutral tagging; aggregation only) | DONE (v0.2 wave 2) |
| D8 | Evergreen-activity detector (percent-creep without RD/date movement) | DONE (v0.2 wave 2) |
| D9 | MIP 3.4 half-step engine: per-window progress-vs-revision bifurcation with named revision attribution; MIP 3.3 as-is tables | APPROVED (needs E1) |

## 5. New matrix checks (§3.3)

| # | Item | Status |
|---|---|---|
| C1 | SET-01 scheduling-settings drift between updates | DONE (v0.2 wave 1) |
| C2 | SET-02 engine match rate (see E4) | DONE (v0.3) |
| C3 | CAL-04 calendar-definition changes between updates | DONE (v0.2 wave 1) |
| C4 | CAL-05 quantified multi-calendar distortion at selected milestone | DONE (v0.2 wave 2) |
| C5 | LOG-10 hollow-logic screen (path-rerouting stub activities) | DONE (v0.2 wave 1) |
| C6 | DUR-04 remaining-duration compression without progress | DONE (v0.2 wave 1) |
| C7 | DAT-05 actual-duration anomalies (AF<AS, actuals before NTP) | DONE (v0.2 wave 1) |
| C8 | STR-03 WBS re-parenting churn | DONE (v0.2 wave 1) |
| C9 | REL-01 zombie relationships (refs to missing activities) | DONE (v0.2 wave 1) |
| C10 | FLT-03 float exceeding remaining project duration | DONE (v0.2 wave 1) |

## 6. Monte Carlo / SRA (§4)

| # | Item | Status |
|---|---|---|
| M1 | Distributions, correlation, risk-event register, Latin Hypercube on `scheduleiq.cpm` | APPROVED (needs E1) |
| M2 | Empirical calibration from the project's own update history (actual÷planned ratio distributions) | APPROVED |
| M3 | Outputs: S-curves, tornado, criticality/cruciality, merge-bias exhibit (LI style) | APPROVED |
| M4 | SRA-readiness gate (refuse/brand DIAGNOSTIC on failing schedules) | APPROVED |

## 7. Second-brainstorm items (§6) — per review of 2026-07-07

| # | Item | Status |
|---|---|---|
| S1 | §6.2 Statistical manipulation screens (Benford/round-number, distribution drift, progress physics) | DONE (v0.2 wave 2) |
| S2 | §6.3 Pacing + constructive-acceleration screens | DONE (v0.2d) |
| S3 | §6.4 Earned-schedule forecast credibility (ES(t), SPI(t), TSPI(t), IEAC(t)) | DONE (v0.2 wave 2) |
| S4 | §6.8 Narrative reconciliation vs XER record | DONE (v0.2d) |
| S5 | §6.1 Editing-session forensics (create/update user+date mining) | PARKED |
| S6 | §6.5 Push-button TIA workbench (MIP 3.6/3.7; collapsed as-built 3.8/3.9) | PARKED |
| S7 | §6.6 Damages/LD exposure overlay | PARKED |
| S8 | §6.7 Interactive HTML cockpit + graphics-generator demonstratives | PARKED |
| S9 | §6.9 Internal benchmark corpus | PARKED |
| S10 | §6.10 Research track (ML duration priors; gated LLM narratives) | PARKED |

## 8. Fuse-parity remainder (FUSE_PARITY.md)

| # | Item | Status |
|---|---|---|
| F1 | Ribbon analyzer (metrics grouped by WBS/field) | PARKED |
| F2 | Phase analyzer (time-phased slicing within one schedule) | PARKED |
| F3 | P6 XML (.xml) ingestion (ADR-0002 slot) | PARKED |
| F4 | Per-period start/finish compliance metrics (baseline-compliance variants) | PARKED |
| F5 | Asta/Phoenix ingestion via MPXJ (enable on demand) | PARKED |

## 9. Third-brainstorm items (§8 of ANALYTICS_PROPOSAL.md) — awaiting review

| # | Item | Status |
|---|---|---|
| N1 | §8.1 Weather & external-conditions overlay | PARKED (proposed 2026-07-07) |
| N2 | §8.2 As-built work-pattern reconstruction (de facto calendars, overtime/suspension detection) | PARKED (proposed) |
| N3 | §8.3 Daily-resolution delay ledger ("continuous windows") | APPROVED (RJL 2026-07-07; needs E1) |
| N4 | §8.4 Methodology-robustness certificate | APPROVED (RJL 2026-07-07; needs D9/N3) |
| N5 | §8.5 Reproducibility capsule & evidence sealing | DONE (v0.2 wave 2) |

## 10. Bespoke LI metrics (§9 of ANALYTICS_PROPOSAL.md) — awaiting review

| # | Item | Status |
|---|---|---|
| N6 | §9.1 FCBI — Float Criticality Burn Index (RJL concept) | DONE (v0.2b/c) |
| N7 | §9.2 LHL — Logic Half-Life | DONE (v0.2b/c) |
| N8 | §9.3 FRB — Forecast Reliability Band | DONE (v0.2b/c) |
| N9 | §9.4 PCI — Path Concentration Index | DONE (v0.2b/c) |
| N10 | §9.5 RDI — Recovery Debt Index | DONE (v0.2b/c) |

## 11. Bespoke LI metrics, second set (§10 of ANALYTICS_PROPOSAL.md) — awaiting review

| # | Item | Status |
|---|---|---|
| N11 | §10.1 BDI — Baseline Dilution Index | DONE (v0.2b/c) |
| N12 | §10.2 CDI — Criticality Dwell Index | DONE (v0.2b/c) |
| N13 | §10.3 IL — Intervention Latency | DONE (v0.2b/c) |
| N14 | §10.4 BWI — Bow-Wave Index | DONE (v0.2b/c) |
| N15 | §10.5 MML — Measured-Mile Locator | DONE (v0.2b/c) |

## 12. Bespoke LI metrics, third set (§11 of ANALYTICS_PROPOSAL.md) — awaiting review

| # | Item | Status |
|---|---|---|
| N16 | §11.1 SMI — Schedule Manipulation Indicator (composite curation signals; guarded framing) | PARKED (proposed 2026-07-07) |
| N17 | §11.2 DDI — Directed Date Index (dictated-completion signature) | PARKED (proposed) |
| N18 | §11.3 ARR — Attribution Robustness Ratio (case-strength across method variants) | PARKED (proposed; needs N4 sweep) |
| N19 | §11.4 PPS — Pacing Plausibility Score (scored pacing-defense credibility) | PARKED (proposed) |
| N20 | §11.5 RSA — Rebuttal Surface Area (share of conclusion on contested ground) | PARKED (proposed; needs N4) |

## 13. Report Card (docs/REPORT_CARD_DESIGN.md) — awaiting review

| # | Item | Status |
|---|---|---|
| RC1 | scorecard.yaml spec v1.0 (curves, weights, categories, gates, bands, normalizations) | DONE (v0.2d) |
| RC2 | Spec-driven scoring engine + score_trace.json | DONE (v0.2d) |
| RC3 | Per-schedule card outputs (report first page, exhibit, Excel, GUI) | DONE (v0.2d) |
| RC4 | Series report card (series categories, trajectory, gates) | DONE (v0.2d) |
| RC5 | Internal-variant card (provocative indices; privileged flag) | DONE (v0.2d) |
| RC6 | Open-source publication of spec + reference scorer (decision) | DONE (v0.2d) |

## Build order (approved scope)

1. **v0.2** (no engine): D1–D8, A1, P1–P4, C1/C3–C10, S1, S3, N5 — DONE
1b. **v0.2b** (no engine): bespoke LI metrics N6–N10 (FCBI, LHL, FRB, PCI, RDI)
1c. **v0.2c** (no engine): bespoke LI metrics N11–N15 (BDI, CDI, IL, BWI, MML)
1d. **v0.2d** (no engine): Report Card RC1–RC5 (+RC6 publication package prepared, publication itself on RJL go); S2 pacing/acceleration; S4 narrative reconciliation
2. **v0.3**: E1–E5, C2, A2–A4, P5–P6, S2 (needs path/engine outputs)
3. **v0.4**: D9 (MIP 3.4 half-step), windows outputs, N3 (daily delay ledger), S4
4. **v0.5**: M1–M4, N4 (robustness certificate — sweeps the D9/N3 machinery)
