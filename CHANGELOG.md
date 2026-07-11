# Changelog

Check-affecting changes are listed explicitly (GOVERNANCE.md §1) so an expert
can state which checks changed between versions used on a matter.

## Unreleased — LI-01 FCBI v0.5.6 (wave-5 peer-review; provenance/API/test hardening)

**NOT number-changing.**  A fifth independent adversarial review accepted the
v0.5.5 core (exact `float_paths` equivalence, frontier soundness, λ ∈ (0, 10],
stable-terminal-target enforcement, one-basis λ-sensitivity, exact cap, and the
correctness-first performance tradeoff).  v0.5.6 is pragmatic hardening only — no
change to the FCBI path-distance/frontier methodology or to any canonical number.

- **Series-integrity guard (Item 1, defensive):** `_validate_fcbi_series_integrity`
  (used by `_prepare_fcbi_basis`) checks the change-set sequence is structurally
  consistent with `sa.schedules` — window count, per-window project id / data date /
  target presence / forward date order, and `source_sha256` when present on both.
  It does NOT require object identity (semantically identical clones pass and stay
  numerically identical); a clearly inconsistent series is NOT EVALUATED with an
  audit reason.  Canonical workflow behaviour is unchanged.
- **Target UID continuity (Item 2, provenance):** a target whose CODE stays stable
  and terminal but whose internal UID moves across updates (re-import, migration,
  delete-and-recreate) is still evaluated, now flagged PROVISIONAL with
  `target_uid_changed` / `target_uid_history` / `target_continuity_note` and an
  interpretation warning.  A moved UID is NOT treated as a changed target — the
  numbers match the stable-UID run.
- **λ input type hardening (Item 3, API):** `_invalid_lambda_reason` rejects
  non-real and `bool` λ before any arithmetic; `run_li_indices` guards its
  legacy-kernel λ selection the same way.  The public entry point never raises on
  any λ input type (None, str, bool, complex, containers, non-finite).
- **Corpus reproducibility (Item 4, tests):** the randomized equivalence corpus
  builds relationships in sorted order (stable across `PYTHONHASHSEED`), adds a
  250-DAG mixed-topology corpus (all four relationship types, ± lags, LOE, parallel
  finish milestones, None/negative float, shared merges, deep chains) comparing
  path count / sequence / `rel_float_days` / `rel_float_hours` / distance map /
  determinism / no-duplicate-signatures, and a subprocess hash-seed reproducibility
  check.  W4 counterexamples retained.
- **Enumeration instrumentation (Item 5, optional):** `_target_distance` gained an
  optional `stats` dict recording `paths_enumerated` / `convergence_stopped` /
  `depth_capped` / `stop_reason` — observational only, no result change, no new
  work-budget cap; the exact enumerator is untouched.
- The v0.4 RF kernel (PCI/CDI/RDI/BWI) and all canonical FCBI anchors are unchanged.
- Wave-6 review returned **GO** (lock at v0.5.6); its two optional test-only
  tightenings were applied — full-tuple equality in the instrumentation test and a
  mixed non-real λ-sensitivity point test — no code or methodology change.

Suite: 226 passed, 1 skipped.

## Unreleased — LI-01 FCBI v0.5.5 (wave-4 peer-review; enumerator correctness)

**Check-affecting for the topologies where the withdrawn v0.5.4 enumerator
diverged** (path splices differed from the reference `float_paths`, changing some
per-activity distances and, through the frontier, which activities were resolved).
A fourth independent review (Codex GPT-5.6 Pro) found the v0.5.4 best-first
generator was **not** exactly equivalent to `float_paths`; both counterexamples
reproduced against the real code.  Correctness was prioritised over performance
(governed constraint): the enumerator is now the reference algorithm streamed.

- **`paths.iter_float_paths` re-based (W4-01):** the priority-queue variant is
  **withdrawn** (it cached feeders against a stale used set and only handled a
  rising rel; a consumed activity can make a feeder's rel *fall* and reroute its
  walk, and the native-rel order is genuinely non-monotone).  It now streams
  `float_paths`'s **exact** round structure — same paths, same order, verified
  byte-for-byte on a 500-DAG seeded corpus — with two provably-equivalent per-round
  optimisations (feeder memo; attachment-activity dedup).  `float_paths` unchanged.
- **Frontier soundness corrected (W4-02):** the early-stop bound is now evaluated on
  `float_paths`'s **own** cumulative used set (yielded per path), so it can no longer
  omit a material-weight activity; proven sound and property-tested (0 material
  omissions across 500 uncapped DAGs).
- **λ bounded (W4-05):** the FCBI weighting λ must be in `(0, FCBI_CONV_LAMBDA]`
  (=10); λ>10 → NOT EVALUATED (a larger λ would make frontier-omitted paths
  material and invalidate the basis).  The v0.4 kernel (PCI/CDI/RDI/BWI) is
  untouched.
- **Stable target basis (W4-06):** an explicit target must be a terminal finish
  milestone in **every** update (`all`, not `any`); auto-resolution intersects the
  per-update terminal-milestone codes; a target-basis discontinuity → NOT EVALUATED.
- **Exact depth cap (W4-07):** `depth_capped` fires exactly at the (MAX+1)-th path.
- **λ-sensitivity reuses one basis (W4-04):** `_prepare_fcbi_basis` /
  `_fcbi_from_basis` compute the λ-independent distance/governance caches once and
  reuse them across λ (2 enumerations for a 2-schedule set, not 8).
- **Non-circular equivalence test (W4-03):** the oracle is built directly from
  `float_paths`; both blocker counterexamples are permanent regressions.
- All prior FCBI anchors (P1 B=5/C=0.7/W=3.5; worked example B=7/coverage=0.7/N=4;
  λ-sensitivity C=0.315/0.5/0.707) are unchanged.

Suite: 212 passed, 1 skipped.

## Unreleased — LI-01 FCBI v0.5.4 (best-first enumerator; W3-05 closed) — SUPERSEDED by v0.5.5

- **`paths.iter_float_paths`** — a lazy, best-first generator intended to be
  equivalent to `float_paths` (identical paths, same order) but computed one at a
  time with a priority queue and lazy revalidation.  **Wave-4 (v0.5.5) found this
  variant was NOT exactly equivalent** (stale-used-set caching + rise-only
  revalidation) and withdrew it; see the v0.5.5 entry above.  `float_paths` itself
  was unchanged then and remains so (PCI/CDI still use it).
- **`_target_distance` rebuilt** on the generator with a frontier early-stop; the
  bound's soundness was later (v0.5.5) re-grounded on `float_paths`'s own used set.
- **Performance:** near-critical fan ×100 3.0 s → 0.06 s, ×150 10.2 s → 0.16 s
  (these figures were for the withdrawn variant; the v0.5.5 reference enumerator is
  slower on a pathological wide near-critical fan, which is capped/provisional).
  The claim "distance maps verified identical to `float_paths` across 120 random
  networks" proved **insufficient** — a 1000-network / 500-DAG test later found the
  divergence.

Suite: 202 passed, 1 skipped.

## Unreleased — LI-01 FCBI v0.5.3 (wave-3 peer-review hardening)

Third independent peer review (GPT-5.6 Pro) raised 10 findings on the v0.5.2
head, mostly on the new subsystems; dispositions in the rulings wave-3 table.

- **λ-invariant distance basis (W3-02, blocker):** convergence is now judged at a
  fixed `FCBI_CONV_LAMBDA = 10`, not the weighting λ, so B, coverage, and the
  eligible population are identical at every λ (the sensitivity set reports one
  invariant B).
- **Cumulative proximity (W3-03, blocker):** `cumulative_proximity` C^cum =
  W^cum/B^cum so the headline identity `W = B·C` is exact (the old code printed a
  false equality using the latest-window C).
- **W3-01 (blocker) disputed — not reproduced:** on the real `float_paths` the
  reviewer's topology enumerates in monotone margin order and the low-margin
  branch is resolved, never omitted; a monotonicity guard now marks the run
  provisional if the assumption is ever violated.
- **Explicit-target validation (W3-04):** an explicit target is validated as a
  terminal finish milestone (task/intermediate → NOT EVALUATED).
- **Depth-cap propagation (W3-06):** both endpoints' `depth_capped` count; a
  one-path lookahead stops an exactly-at-ceiling network being falsely capped
  (W3-09).
- **Sensitivity status (W3-07):** per-λ status/reason/provisional retained; the
  set fails whole on a structural error, per-point on an invalid λ.
- **Endpoint type change (W3-08):** a task→LOE/milestone conversion is excluded
  from B and disclosed; **signed** milestone margin change (W3-10).
- Follow-up (documented): a proven convergence bound + incremental enumerator
  (W3-05 performance) targeted for v0.5.4.

Suite: 199 passed, 1 skipped.

## Unreleased — LI-01 FCBI v0.5.2 (settled open questions)

The seven open methodology questions were adjudicated by the principal; recorded
in `docs/rulings/LI-01-fcbi-v0.5.md` (settled-decisions table).  Code-affecting:

- **Headline (Q1/Q4):** the FCBI headline is the **(B, C) pair** — B is the
  cumulative curve, C annotated; W = B·C is the derived single-number diagnostic,
  never B alone.
- **λ sensitivity (Q2):** new `fcbi_lambda_sensitivity(sa, target, lams=(3,5,10))`
  reports C/W across λ (B is λ-invariant), so a near-critical-burn conclusion is
  shown robust to the half-weight constant.
- **Population coverage (Q6):** a full block beside eligible-burn coverage —
  `candidate_pop`, `pop_tf_evaluable`, `pop_eligible`, `pop_exclusions`, and the
  `tf_evaluability` / `population_eligibility` fractions — so burn coverage is
  never read as data completeness.
- **Target mandate (Q1/O7.1):** an auto-resolved target flags the run PROVISIONAL
  (m must be analyst-confirmed for work product).
- **Adaptive convergence (Q6/REV-08):** `_target_distance` now enumerates
  25→50→… until the max possible omitted weight < `FCBI_CONV_TOL` (ceiling
  `FCBI_PATHS_MAX`), replacing the hard cap; a ceiling hit sets `depth_capped`
  (provisional).
- **Materiality (Q3):** the single criterion `|d_record − d_logic| ≥ λ` (the
  weight-ratio form was redundant).
- Confirmed: keep the distance clamp (REV-05); no-sum across targets (Q7).

Suite: 191 passed, 1 skipped.

## Unreleased — LI-01 FCBI v0.5.1 (wave-2 peer-review hardening)

Independent second peer review (different provider) of the v0.5.0 branch raised
17 findings; dispositions recorded in `docs/rulings/LI-01-fcbi-v0.5.md` (wave-2
table).  Check-affecting corrections:

- **Target (REV-01):** default resolution now selects a **terminal** finish
  milestone (never a constrained intermediate or a task) and flags
  `target_auto_resolved`; the analyst should still select m explicitly.
- **Calendar basis (REV-02/07):** FCBI distances use a fixed-reference-hours,
  discrete-members-only path margin (`FloatPath.rel_float_hours`) — a driver is
  no longer repriced by native calendar length, and a level-of-effort node can
  no longer set a path margin.
- **Basis-change isolation (REV-03):** basis-change windows are excluded from the
  operational aggregate and headline; the wiring labels them requirement-induced.
- **Governance (REV-04/06):** governance is unioned across both window endpoints
  (catches a constraint/expected-finish added mid-window) with expected-finish
  propagation; the basis-change signature now covers constraint type, secondary
  constraint, must-finish-by, rebaseline, and more settings, and ignores a stale
  date under constraint type NONE.
- **Decomposition (REV-09):** cross-window aggregate burners carry an effective
  weight so (consumption × weight == contribution); deterministic ordering.
- **Robustness (REV-11/12/13/15/17):** λ validated (never raises); unmeasurable
  float counted; a stable window no longer reports a false "unresolved" reason;
  quarantined-recovery subtotal added; non-target milestones excluded from B/C
  and disclosed separately.
- Matrix `unit: activity-days` (REV-16); `depth_capped` disclosed (REV-08).

Suite: 186 passed, 1 skipped (wave-2 regressions added).

## Unreleased — LI-01 FCBI methodology v0.5.0 (governed revision)

**Check-affecting, number-changing.**  LI-01 (FCBI — Float Criticality Burn
Index) revised under two-reviewer consensus (converged 2026-07-10); rulings
O1–O7 recorded in `docs/rulings/LI-01-fcbi-v0.5.md`, spec rewritten in
`docs/ANALYTICS_PROPOSAL.md` §9.1, matrix row updated.  Prior FCBI numbers on a
matter do not carry over — the basis, outputs, and timing all changed.

- **Distance basis (O1).**  RF replaced by a nonnegative target-specific
  distance `d_i = min over enumerated paths of (path margin − driving margin)`;
  driver d=0, never negative; own-total-float fallback abolished (unresolved →
  quarantine); weight `w = 2^(−d/λ) ∈ (0,1]` (the w>1 over-critical premium is
  gone).
- **Outputs (O2).**  Primary outputs are now **B** (gross activity-day burn) and
  **C** (burn-weighted mean proximity, NOT APPLICABLE when B=0), optional
  **W = B·C**; recovery mirror **B⁻/C⁻** tracked separately.  **FCBI% retired**
  (ratio and its D=0 sentinel removed).  Negative-float severity moved beside B
  and C as **N = max(0,−F_m)** and **ΔN⁺**, never inside the kernel.
- **Timing (O3).**  Start-of-window weighting is primary; an **endpoint-timing
  sensitivity set** (start/end/min-endpoint) supersedes the v0.4.2 min-RF ruling
  (supersession recorded).
- **Noise (O4).**  Tier-1 numerical tolerance in hours before hour→day
  conversion; no statistical deadband (Tier 2 deferred).
- **Population/governance (O5/O6).**  Remaining-work population retained, plus a
  completion-omission diagnostic; target eligibility predicate with **propagated
  governance** traced through the network, a **quarantine subtotal**, and
  **eligible-burn coverage**.
- **Segmentation/scale (O7).**  Basis-change windows (target-date/rebaseline/
  settings/calendar) segmented out of the operational trend as requirement-
  induced margin change; burn-rate normalization; fixed reference hours/day.
- **Report Card.**  LI-01 scoring marked **provisional/ungraded** pending anchor
  recalibration (the definition change invalidates the prior [0,20,60] anchors);
  reported informationally with its B/C decomposition, coverage, and severity.
- **Tests.**  Probe set §P (P1–P11) added as seeded in-memory regression
  fixtures; the v0.4 X/Y/Z exact test superseded.  The v0.4 RF kernel is
  untouched, so PCI/CDI/RDI/BWI (LI-04/07/05/09) are unchanged.

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
