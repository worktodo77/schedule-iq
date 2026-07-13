# Changelog

Check-affecting changes are listed explicitly (GOVERNANCE.md §1) so an expert
can state which checks changed between versions used on a matter.

## Unreleased — Review wave 3 dispositions (independent adversarial review of Waves 3/4, 2026-07-13)

**Check-affecting for LI-05/LI-07/LI-09 on DEGRADED inputs only** (the fixed
paths previously produced fabricated readings; no computable-path number
moves).  Full disposition table in docs/rulings/LI-kernel-v2-2026-07-12.md.
The owed independent review wave ran (scope: Waves 3/4 + review-wave-2's
territory): scope C fully clean, FCBI byte-identity and 120-DAG oracle
equivalence independently confirmed, 494-call never-raises sweep, all
closed-form anchors re-derived.  1 MAJOR + 6 MINOR findings, all reproduced
before fixing:

- **RW3-F1 (MAJOR, BWI/RDI):** BWI no longer asserts a "projected break"
  against a fabricated demonstrated pace of 0.0 when the family completion
  basis is NOT EVALUATED — the break test is NOT EVALUATED with the reason
  disclosed (the ratio itself, on BWI's own anchor basis, is unaffected).
  A window whose completions were ALL quarantined reads an UNKNOWN
  demonstrated pace (None), never 0.0 — no phantom P50 drag, no accrual
  against a fabricated zero anchor; a series with required pace but no
  demonstrated evidence is NOT EVALUATED.  Quarantined demo completions
  are now disclosed on BwiResult.
- **RW3-F2 (kernel v2):** family-target resolution is CODE-ONLY (exact
  oracle mirror) — a UID/CODE collision can no longer bind the wrong
  activity; BWI's pinned anchor keeps UID-first (B2).
- **RW3-F3 (LI-06):** baseline_dilution_index type-hardens baseline_index
  (never raises on float/str/None/bool).
- **RW3-F4 (LI-07):** a fully-quarantined CDI board reads NOT EVALUATED
  naming the quarantine counts, not the benign "no near-critical work".
- **RW3-F5:** band_days validated (finite, >= 0) — invalid band leaves
  CDI/RDI/BWI NOT EVALUATED (was: negative band → RDI 0.0 full-credit with
  no reason); sensitivity-set members degrade to None points.
- **RW3-F6 (LI-04, disclosure-only):** PCI's disclosure no longer claims a
  governance quarantine it does not apply; path-level governance filtering
  is flagged OPEN for the principal.
- **RW3-F7 (LI-05, disclosure-only):** the later-endpoint demonstrated
  numerator (post-completion OD edits move demonstrated pace) is disclosed
  as a manipulation surface; the endpoint choice is flagged OPEN for the
  principal.

Suite: 304 passed, 1 skipped (8 new regressions).

## Unreleased — LI kernel v2 (Wave 3; rulings Q-B + design D1–D4, adjudicated 2026-07-12)

**Check-affecting / number-changing for LI-04 PCI, LI-05 RDI, LI-07 CDI,
LI-09 BWI** — every consumer of the v0.4 relative-float kernel moves to the
FCBI v0.5 family basis.  **LI-04 is additionally PROVISIONAL/UNGRADED**
(D4): its scored anchors were tuned to the abolished floor-0.1/top-10/
premium scale; `scorecard.yaml` carries the provisional block pending
recalibration against real series (LI-01 precedent).  LI-05/LI-09 stay
graded; pinned demo letters verified (demo held with LI-04 ungraded).
Recorded ruling docs/rulings/LI-kernel-v2-2026-07-12.md; approved design
docs/LI-kernel-v2-design-2026-07-12.md.

- **Family basis (D1):** nonnegative target-specific distance on the locked
  FCBI enumeration (proven convergence frontier, exact path cap →
  PROVISIONAL, propagated-governance quarantine, stable completion-milestone
  target), implemented as `_build_kernel_v2` — a mirror of the locked
  `_target_distance`, regression-locked against it as an oracle on a
  40-DAG corpus.  Abolishes the own-float fallback (K1: unresolved is
  quarantined + disclosed, never priced), the w > 1 negative-float premium
  (K2: d ≥ 0 ⇒ w ≤ 1), and the raw top-10 truncation (K5: PCI's 1/10
  Herfindahl floor is gone).
- **Severity beside (D2):** per-update N = max(0, −target margin) and ΔN⁺
  deepening reported beside PCI/CDI, never inside the weights (uniform
  deepening leaves PCI identical; the strip carries it).
- **CDI (D3):** dwell over live, resolved, ungoverned discrete activities
  with d ≤ band; milestone markers and post-completion accrual superseded
  out (dwell earned while live is retained); per-update quarantine counts
  disclosed.
- **RDI:** demonstrated-pace gate moves to the window's EARLIER endpoint
  (nonanticipative; fixes audit RDI-2's exporter dependence).  Honest
  degradation: an update whose entire live population is quarantined has
  required = None; an all-None series is NOT EVALUATED naming the
  quarantine (never a fabricated 0 days of debt).
- **BWI:** band membership by distance to the bow-wave milestone ITSELF
  (own UID-pinned target); B1 fixed horizon / B2 UID pinning / W1c-3 break
  test carried over unchanged.
- λ bounded to (0, FCBI_CONV_LAMBDA] family-wide (invalid λ → PCI/CDI NOT
  EVALUATED); Q-H sensitivity sets re-pointed.  Legacy v0.4 helpers stay
  byte-identical, RETIRED from the pipeline.  FCBI (LI-01), the shared
  enumerator, and the white paper untouched — all FCBI anchors pass
  unchanged.
- Review status: the independent adversarial review wave over Wave 3 (and
  review-wave-2's territory) is OWED — recorded in the ruling and the
  audit-matrix banner.

Suite: 296 passed, 1 skipped.

## Unreleased — LI kernel constant governance (ruling Q-H, adjudicated 2026-07-12)

**Additive — no canonical number changes.**  Recorded ruling
docs/rulings/LI-kernel-constants-2026-07-12.md (rubric C4: sensitivity
sets, not point claims).

- `kernel_lambda_sensitivity(sa, lams=(3,5,10))`: PCI + CDI top-decile per
  λ (the FCBI Q2 pattern); λ = 5 recorded as a professional convention.
- `kernel_band_sensitivity(sa, bands=(5,10,20))`: CDI / RDI / BWI per
  near-critical band; band = 10 recorded as a convention.
- KERNEL_PATHS_N = 10 recorded as a convention with the disclosed PCI
  Herfindahl floor (1/10) consequence; PCI's scored anchors are re-examined
  with the Wave-3 kernel, per the ruling.  MML's constants were recorded in
  the Wave-4b ruling.  2 new regressions.

Suite: 293 passed, 1 skipped.

## Unreleased — LI-10 MML Wave-4 revision (ruling Q-F, adjudicated 2026-07-12)

**Number-changing for LI-10 (informational — no Report Card weight, but the
per-trade contrast ratios and named clean/impacted periods move).**
Recorded ruling docs/rulings/LI-10-mml-v2-2026-07-12.md.

- **Basis segregation:** one basis per trade (resource units/hour only when
  every data-bearing window has resource movement, else activity-days/day
  throughout) — a resource window is never compared against an activity-day
  window (the prior per-window auto-selection produced dimensionally
  meaningless cross-basis "contrast" ratios; audit MML-1 probe: 0.4 from
  1.25 units/h ÷ 0.5 act-d/d).
- **Sustained clean mile:** best mean over 2 consecutive, valid, non-event
  windows within a 25% dispersion cap (recorded conventions) — a single
  spike window can no longer become the measured mile (anchor: [1.0, 1.05,
  5.0, 0.5] → clean 1.025, not 5.0); single-window degradation is a named
  reason.
- **Event overlay wired:** mapped delay events (sa.delay_events, D6 mapper
  output) now reach MML through the wiring and exclude overlapping windows
  from clean candidacy; ACTIVE/INACTIVE status disclosed (the parameter
  previously existed but was never supplied — dead code).
- **no_clean_mile carries named reasons** (tight spread / all windows
  evented / no sustained run) into the exhibit text; standing disclosures
  added.  4 new closed-form regressions.

Suite: 291 passed, 1 skipped.

## Unreleased — LI-06 BDI Wave-4 revision (ruling Q-G, adjudicated 2026-07-12)

**Check-affecting / number-changing for LI-06 (scored, weight 2).**
Recorded ruling docs/rulings/LI-06-bdi-v2-2026-07-12.md.

- **Fixed length basis:** every driving-path step weighs its ORIGINAL
  (planned) duration — progress alone can no longer move the dilution share
  (the prior remaining-else-original basis read an original 20d step at 4d
  remaining vs a 10d added step as 71.4% "post-baseline"; fixed basis:
  33.3% at every progress state).
- **LOE/summary steps zero-length** (the deferred family ruling extended to
  BDI); an all-LOE/milestone path reads NOT EVALUATED per the sentinel.
- **Explicit baseline_index / target_code parameters**, both choices named
  in new standing disclosures (confirm-for-work-product note when
  defaulted); out-of-range index degrades with a reason.
- Change-register detail-format coupling regression-locked.  4 new tests.

Suite: 287 passed, 1 skipped.

## Unreleased — Review wave 2 (reduced scope): RW2-1 fixed

**Check-affecting within the Unreleased Wave-1c train.**  The independent
wave-2 reviewer was terminated by an account spend limit; the wave ran
implementation-side against the same probe plan (disclosed as NOT
independent in the ruling record; an independent confirmation wave is owed).
The W1c-1..3 fixes and the Wave-2 IL/FRB rulings verified on-probe (incl.
the causing-edit adjacency case, the S(0)=0.5 KM boundary, IL4b
completed+negative same-window exclusion, overdue banding at n>=5, and the
wd_rem<=0 break edge).  One new finding, fixed:

- **RW2-1:** a branch with NO float evidence at all still leaked the
  spliced tail's min through the shared `rel_float_days` fallback (kernel
  rf 0.0 / weight 1.0 for a float-less feeder task).  A zero-float-evidence
  branch now contributes no RF evidence — its members fall to the own-float
  fallback / the documented omitted case, never a fabricated 0.0.
  Regression `test_rw2_1_*`.

Suite: 283 passed, 1 skipped.

## Unreleased — Wave 0-1c adversarial review, wave 1 (findings W1c-1..5 dispositioned)

**Check-affecting within the Unreleased Wave-1c train** (no released number
moves).  An independent adversarial review of `ec30292..372be49`
(reproduce-before-reporting) raised 3 MAJOR + 2 MINOR findings, all
reproduced and dispositioned (full table in
docs/rulings/LI-04-LI-07-kernel-loe-port-2026-07-12.md):

- **W1c-1:** kept-path margins now retain MILESTONE floats (min over unique
  non-summary members) — the ported code had silently stripped them,
  contradicting the ruled text and emptying the near-critical band on a
  deadline-constrained chain (rf +15 instead of −2 for the whole chain).
- **W1c-2:** an unfloated branch falls back to the shared `rel_float_days`
  (its own basis), never the spliced driving-path tail's min, which
  fabricated rf 0.0 / weight 1.0 for a genuinely floaty branch (rubric A1).
- **W1c-3:** BWI's projected-break test now compares a true REQUIRED pace
  (remaining volume / working days remaining to the fixed reference) against
  the demonstrated pace; under B1's constant denominator the old test lost
  sensitivity exactly as the milestone approached.
- **W1c-4/5:** over-broad "LOE feeder reads PCI 1.0" claim reworded
  (LOE-only BRANCHES cannot register as kernel paths); LI-07 wording now
  states milestone markers hold dwell (LOE/summary excluded).
- Review clean areas, with probe evidence: FCBI/paths byte-identity
  (82-entry corpus, 0 diff lines), never-raises (96 adversarial calls),
  Wave-3 scope locks, and every ported LHL/RDI/BWI ruling's arithmetic.
- 3 new regressions (`test_w1c1..3_*`).

Suite: 282 passed, 1 skipped.

## Unreleased — LI-08 IL + LI-03 FRB Wave-2 revisions (rulings adjudicated 2026-07-12)

**Check-affecting / number-changing for LI-08 and LI-03 (both scored,
weight 2).**  The open rulings from the lineage-A IL/FRB audit (imported at
docs/audit/IL_FRB_audit_2026-07-10.md) were adjudicated by the principal —
every recommended option adopted (recorded rulings
docs/rulings/LI-08-il-v2-2026-07-12.md and
docs/rulings/LI-03-frb-v2-2026-07-12.md).

- **IL1-A:** the emergence window is scanned — same-window mitigation reads
  latency 0 and the published 100-point anchor is reachable (previously the
  fastest responder read "did not act": 20 vs 85 for the identical edit a
  month later); adjacency-not-sequence disclosure added.
- **IL2-A:** KM right-censored headline median (unresolved chains censored
  at follow-up): 1-responded + 5-ignored moves 85 → 20 (with the follow-up
  bound as the value); a sole final-window emergence moves 20 → N/A (no
  latency information); no-events stays N/A.
- **IL4/IL5:** LOE/summary and completed-in-later-file activities excluded
  from the emergence set (a hammock-only chain no longer drives LI-08 to
  20); day figures follow the L9 data-date convention (withheld with a
  disclosure, never negative).  IL6 standing disclosures added.
- **FR2-A:** overdue forecasts (horizon ≤ 0) get their own scored bucket —
  bands no longer exclude exactly the record's worst forecasts;
  Σ bucket n == observations.
- **FR3-A:** the scored band requires n ≥ 5 resolved forecasts (the
  metric's own frb_apply_forward floor); below it LI-03 is NOT EVALUATED —
  thin-record series that scored 100 by construction become ungraded.
  FR4 standing disclosures added.
- 8 new regression tests (U2–U8) + 3 existing tests updated to the ruled
  conventions (bucket count 5; KM semantics; the Wave-0 FR1 anchor re-based
  to an n=5 closed-form fixture, width 10.0 wd through the wiring).

Suite: 279 passed, 1 skipped.

## Unreleased — LI kernel LOE exclusion PORTED (Wave 1c of the LI-02..LI-10 audit)

**Check-affecting / number-changing for LI-04 (PCI) and LI-07 (CDI) on any
series with near-critical LOE/summary activities, and for LI-05/LI-09 band
membership where a mixed-path LOE previously dragged a discrete activity's
RF into the band.**  LI-01 FCBI (locked) does not use this kernel and is
numerically untouched — its full anchor suite passes unchanged.  Port of
lineage-A rulings C1/C2 (v0.4.2) + the mixed-path neutralization (v0.4.3);
recorded ruling docs/rulings/LI-04-LI-07-kernel-loe-port-2026-07-12.md;
validation record imported at docs/audit/v0.4.2_validation_2026-07-09.md.

- **C1 — LOE/summary excluded at the shared kernel:** no RF entry, no
  weight, no CDI dwell, no band membership; `_build_kernel` drops paths
  with no discrete-work member (an LOE-only branch cannot register as
  a kernel path, and an all-milestone schedule degrades to None
  with a reason, never a spurious concentration).
- **Mixed-path neutralization:** each kept path's LI relative float is the
  min total float over its unique NON-SUMMARY members (`_li_path_rel_float`
  over the new additive `FloatPath.unique_uids` — LOE/summary out,
  milestones retained per review W1c-1), so an LOE no longer drives a
  member's RF; an unfloated branch falls back to the shared
  `rel_float_days`, never the spliced tail's min (review W1c-2).  The
  shared `float_paths()` / `iter_float_paths()` are byte-identical
  (regression-pinned alongside the neutralization).
- **C2 — CDI completed-retention documented** (§10.2, LI-07 row, standing
  disclosures); no behavioral change.
- NOT changed (Wave-3 kernel-cluster scope, scope-locked by test): the
  off-path own-total-float fallback for discrete activities, the
  negative-float w>1 premium, λ/band governance, the top-10 truncation
  disclosure, and PCI's kept-mixed-path Herfindahl weight residual.
- 5 new regression tests; pinned demo letters hold.

Suite: 272 passed, 1 skipped.

## Unreleased — LI-05 RDI / LI-09 BWI rulings PORTED (Wave 1b of the LI-02..LI-10 audit)

**Check-affecting / number-changing for LI-05 and LI-09 (both scored,
weight 2) on real data.**  The RDI/BWI rulings adjudicated by the principal
on the lineage-A branch (v0.4.2–v0.4.4, 2026-07-09) are ported as-ruled
(port ruling Q-A; recorded ruling
docs/rulings/LI-05-LI-09-rdi-bwi-port-2026-07-12.md; as-audited record
imported at docs/audit/RDI_BWI_CDI_audit_2026-07-08.md).

- **R2 — RDI accrues against the running P50** (median, sustainable)
  demonstrated pace, with the running max reported as the optimistic bound
  (the max-only anchor under-accrued).
- **R1 — planned-scope demonstrated basis affirmed + companion
  duration-overrun ratio** (Σ actual elapsed ÷ Σ planned of the window's
  completions) per window and per series, disclosed as an efficiency
  diagnostic and never an accrual input; missing actual starts degrade the
  ratio with a DATA QUALITY disclosure.  Anchor: five parallel on-pace
  completions → demonstrated 2.5, companion ratio 2.0 (the case where an
  elapsed basis would have manufactured phantom debt).
- **B1 — BWI fixed reference horizon** (constrained date, else baseline
  finish, else first-update forecast finish, constant across updates): a
  slipping milestone with unchanged work reads 1.0, no longer < 1
  ("relief") off the moving forecast denominator.
- **B2 — BWI target pinned by persistent UID** (located UID-then-code), so
  a re-coded/renamed milestone no longer silently drops later densities.
- **X1 — standing disclosures** on RdiResult/BwiResult (LOE exclusion,
  basis statements, data-quality notes).
- The Wave-0.5 NOT EVALUATED sentinel is retained (supersedes lineage-A's
  0.0 on the uncomputable branch).  The kernel C1/mixed-path items land
  separately (Wave 1c).  6 new regression tests; 1 Wave-0 test re-fixtured
  (B2 now survives the re-code it used).  Pinned demo letters hold.

Suite: 267 passed, 1 skipped.

## Unreleased — LI-02 LHL v0.4.5 rulings PORTED (Wave 1a of the LI-02..LI-10 audit)

**Check-affecting / number-changing for LI-02 (scored, weight 2).**  The 12
LHL rulings adjudicated by the principal on the unmerged lineage-A branch
(2026-07-10) are ported as-ruled onto this base (port ruling Q-A,
2026-07-12; recorded ruling docs/rulings/LI-02-lhl-port-2026-07-12.md;
as-audited record imported at docs/audit/LHL_audit_2026-07-09.md).

- Scoring: **L1** deaths-based 100 branch (was inverted — tested the
  censored fraction; a frozen network scored 70); **L10** ungradeable when
  the months basis is unavailable (was: could score 100 on maximal churn
  with missing data dates); offender count = relationship deaths.
- Metric: **L5+L7** calendar-day KM with midpoint death dating (replaces
  update-count × cadence-mean; first-window deletions are no longer
  0-duration events); **L2** longest-follow-up lower bound when the median
  is not reached + ratio suppression; **L4a** LOE/summary-attached ties
  excluded; **L4b** censor at completion (born-on-completed ties
  unobserved); **L9** missing/non-increasing data dates withhold the months
  basis (never a negative figure); **L8** on/off split = membership at ANY
  update while alive, incl. the completion-censor classification fix;
  **L3** code keying affirmed + disclosed; **L6** effective-exclusion
  reporting; **X1+X2** standing disclosures block (surfaced as LI-02
  findings by the wiring).
- Demo series: LI-02 member 70 → 100 ("at least 3.0 months", 1 death);
  series letter D holds.  21 ported regression tests (T1–T11 + the L8
  close-out) + 3 existing tests updated to the ruled conventions.

Suite: 261 passed, 1 skipped.

## Unreleased — LI-05/LI-06 NOT EVALUATED sentinels (defect-class batch, ruled)

**Check-affecting / number-changing at the Report Card surface.**  Ruled by
the principal (2026-07-12, Q-C of the LI-02..LI-10 audit triage; recorded
ruling docs/rulings/LI-05-LI-06-not-evaluated-2026-07-12.md).  Rubric A1:
undefined must be explicit, never a plausible-looking number.

- **LI-05 RDI:** a series where no update yields a usable required pace
  previously returned `rdi_days = 0.0` beside its reason and **scored 100
  ("no recovery debt") on a series the metric could not evaluate**.  Now
  `rdi_days = None` + `NOT EVALUATED …` reason; the member is ungraded.
  `RdiResult.rdi_days` is now Optional (None ⇒ NOT EVALUATED); the
  fewer-than-two-updates case is likewise None.
- **LI-06 BDI:** an all-milestone (zero-working-day-length) driving path
  previously returned `bdi_pct = 0.0` — the best-possible "fully
  baseline-original" reading — and scored 100.  Now `bdi_pct = None` +
  `NOT EVALUATED …` reason; ungraded.
- Accrual/attribution mathematics unchanged on every computable series
  (regression-guarded).  matrix.yaml LI-05/LI-06 formulas and §9.5/§10.1
  now state the convention.  7 new tests (`tests/test_li_sentinels.py`),
  metric layer + wired path.

Suite: 240 passed, 1 skipped.

## Unreleased — LI wiring defect batch (Wave 0 of the LI-02..LI-10 audit)

**Check-affecting for LI-03 (FRB) only, via the report/score surface.**  No
metric-layer formula changed; the fixes repair the wiring between correct
metric results and the exhibits/Report Card (audit:
docs/audit/LI-02-10_audit_matrix_2026-07-12.md, findings FR1/W1/W2; Wave 0
approved by the principal 2026-07-12).

- **FR1 — LI-03 scored off nonexistent fields.**  `li_wiring` read
  `b.bias`/`b.p10`/`b.p90` where `FRBBucket`'s fields are `bias_days`/
  `p10_days`/`p90_days`; every `getattr` returned its default, so the wired
  band width was a fabricated 0 and **LI-03 scored 100 on every series**
  while the findings text asserted zero bias / zero dispersion.  The wiring
  now reads the real fields: LI-03's value is the largest bucket's true
  P90−P10 width, so real series with forecast dispersion WILL move (that is
  the fix, not a side effect).  Regression pins width 8.0 wd end-to-end
  through `li_series_results` against a closed-form two-error anchor.
- **W1 — one None blanked all ten indices.**  Two wiring sites formatted
  Optional values raw (`PCI {val:.3f}` on a None per-update window; BWI
  `density {…:.2f}` on a None density row); either raised TypeError and the
  pipeline's blanket guard then silently dropped ALL LI-01..LI-10 rows (six
  scored members to N/A at once).  Optionals now render as an em dash, and
  `li_series_results` isolates each index behind its own guard — a failure
  degrades that one index to a reasoned placeholder row and the other nine
  still report.  Canonical series are numerically unchanged.
- **W2 — exhibits printed fabricated zeros (narrative only).**  Same
  wrong-field `getattr` class in three more blocks: LI-05 read
  `row.required`/`row.demonstrated` (real fields `required_pace`/
  `demonstrated_pace` — text always read "required 0.00 vs demonstrated
  nan"), LI-07 read `e.share` (real field `dwell_share` — every leaderboard
  entry read "dwell share 0.0%"), LI-10 read a nonexistent `row.basis`
  (always "?"; basis now reported from the clean/impacted windows, with a
  cross-basis pair labelled MIXED rather than papered over).  The wiring now
  uses direct attribute access throughout so a renamed field fails loudly —
  and is then contained per-index by the W1 isolation.
- 7 new wiring-path regression tests (`tests/test_li_wiring.py`) — all
  through `li_series_results`, not the metric layer, per the audit's
  non-circularity rule (the metric layer was never broken, which is exactly
  why metric-layer tests missed FR1).

Suite: 233 passed, 1 skipped.

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
