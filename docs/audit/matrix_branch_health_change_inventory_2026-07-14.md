# Matrix-branch health + change inventory — 2026-07-14

## Scope and lineage

This report is an inventory, not a soundness review.  The comparison baseline
is the approved v0.4.6 lineage at `e99f2010d71b0560dfefe7b1d9ff8a4e22aa8c14`.
The matrix branch was checked out in a clean detached worktree at
`269730b800b50da2e021e89040e734266aa7c488` (`RW3-F6/F7 rulings executed`).
Their merge-base is `c0a64bf1830d64854becdf79acf40940726664e3`; this is a
substantial fork, so this inventory limits itself to the requested LI/kernel
surfaces rather than treating unrelated fork deletions as methodology deltas.

## 1. Matrix-branch test health

### Full-suite command

Command, run from the clean matrix worktree:

```text
py -m pytest -q
```

Result: **the suite did not collect**.  Exact pytest failure summary:

```text
=================================== ERRORS ====================================
__________________ ERROR collecting tests/test_scorecard.py ___________________
ImportError while importing test module 'C:\Users\Alex\schedule-iq-matrix-rid\tests\test_scorecard.py'.
...
tests\test_scorecard.py:22: in <module>
    from scheduleiq.scorecard import (
src\scheduleiq\scorecard.py:37: in <module>
    import yaml
E   ModuleNotFoundError: No module named 'yaml'
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!
1 error in 0.92s
```

Therefore the honest full-suite count in this runtime is **0 passed, 0
skipped, 0 failed tests, 1 collection error**; no assertion-level full-suite
verdict is available.  The branch declares historical suite counts in its
record (for example `docs/rulings/LI-kernel-v2-2026-07-12.md:121,152-156`),
but those records are not a substitute for this reproduction.

### Supplemental non-scorecard run

To measure the remainder without the collection blocker, I ran:

```text
py -m pytest -q --ignore=tests/test_scorecard.py -rs
```

Result: **259 passed, 17 failed, 1 skipped** (`3.60s`).  The skip is verbatim:

```text
SKIPPED [1] tests\test_li_record.py:601: A1210 is not on the latest driving path in this fixture run
```

All 17 failures are import/environment failures rather than assertion
failures:

| Tests | Exact blocking exception |
|---|---|
| `tests/test_intake.py::test_series_report_includes_intake_review`; `::test_runner_writes_intake_review_xlsx`; `tests/test_paths.py::test_series_report_includes_paths`; `tests/test_scheduleiq.py::test_outputs`; `tests/test_scheduleiq.py::test_audit_log`; `tests/test_stats_es_capsule.py::test_capsule_built_by_runner` | `ModuleNotFoundError: No module named 'matplotlib'` |
| `tests/test_li_record.py::test_t1_li02_frozen_network_scores_100`; `::test_t1_li02_not_reached_with_real_churn_scores_70`; `::test_t1_li02_reached_short_median_scores_zero`; `::test_t4_completed_ties_no_longer_inflate_survival`; `::test_t9_out_of_order_dates_never_yield_negative_months`; `::test_t9_same_day_and_missing_dates_are_ungradeable_not_silent`; `::test_t10_reached_median_without_dates_is_ungradeable_not_100`; `::test_u2_same_window_response_is_latency_zero_and_anchor_reachable`; `::test_u3_ignored_chains_pull_the_score_to_did_not_act`; `::test_u4_sole_final_window_emergence_is_na_not_20` | `ModuleNotFoundError: No module named 'yaml'` |
| `tests/test_scheduleiq.py::test_cli_end_to_end` | `AssertionError` whose subprocess stderr ends with `ModuleNotFoundError: No module named 'matplotlib'` |

No dependency installation or code change was made to either lineage; the
environment has `pytest` but lacks the declared `pyyaml` and `matplotlib`
packages.

## 2. Public API/signature inventory vs v0.4.6

| Surface | v0.4.6 baseline (`e99f2010`) | Matrix tip (`269730b`) |
|---|---|---|
| `run_li_indices` | `run_li_indices(sa, lam=5, band_days=10, bwi_target=None)` (`src/scheduleiq/analytics/li_indices.py:961-992`) | Adds `fcbi_target=None`; builds one family `_KernelV2` per schedule and passes it to PCI/CDI/RDI/BWI (`src/scheduleiq/analytics/li_indices.py:2466-2528`). |
| FCBI entry/basis | FCBI is an internal consumer of a shared `_Kernel`, with `FcbiWindow.fcbi`, `fcbi_recovery`, and `fcbi_pct` (`.../li_indices.py:216-247,423-520`). | `_fcbi(sa, lam, target, tier1_tol_hours)` and `_prepare_fcbi_basis` expose target selection, target-governance/quarantine, basis segmentation, and a λ-independent prepared basis; the result exposes B/C/W, coverage, severity, omissions, cap, target, and UID-continuity fields (`.../li_indices.py:273-452,987-1057`). |
| Sensitivity helpers | None. | New `fcbi_lambda_sensitivity` (`.../li_indices.py:1367-1427`), `kernel_lambda_sensitivity` and `kernel_band_sensitivity` (`.../li_indices.py:2401-2463`). |
| Path engine | `FloatPath` has native `rel_float_days` plus `unique_uids`; only eager `float_paths` (`.../paths.py:71-84,386-447`). | Adds fixed-reference `rel_float_hours` and lazy `iter_float_paths`, which streams the exact reference sequence and supports the convergence frontier/cap (`.../paths.py:71-92,396-399,469-495`). |
| BDI | `baseline_dilution_index(series_analysis)` (`src/scheduleiq/analytics/li_record.py:498-509`). | Adds `baseline_index=0` and `target_code=None`; original-duration basis and LOE-zero-length rules are explicit (`.../li_record.py:622-649`). |
| MML | Existing `events` parameter, but no sustained-run/basis result fields (`.../li_record.py:773-863`). | Adds `MML_RUN_K`, spread conventions, `clean_windows`, `clean_productivity`, `no_clean_mile_reasons`, and event-exclusion fields; `run_li_record` passes `sa.delay_events` through (`.../li_record.py:1011-1052,1112-1137,1285-1307`; `analytics/li_wiring.py:70`). |
| Scorecard LI-04 | Scored with the v0.4 PCI curve. | `provisional: true`, ungraded pending recalibration after the basis change (`src/scheduleiq/scorecard.yaml:478-493`). |

## 3. Behavioral inventory — FCBI v0.5 and v0.5.6

### FCBI v0.5 governed revision (number-changing relative to e99)

- **Basis and weight:** replaces shared RF with nonnegative target-specific
  distance `d` to one selected terminal completion milestone; `w=2^(-d/λ)` is
  always in `(0,1]`; own-total-float fallback and the negative-float `w>1`
  premium are abolished (`src/scheduleiq/analytics/li_indices.py:550-555,561-680`; recorded ruling `docs/rulings/LI-01-fcbi-v0.5.md:14-37`).
- **Headline outputs:** replaces scalar `fcbi`/`fcbi_recovery`/`fcbi_pct` with
  gross burn `B`, proximity `C`, derived `W=B*C`, separate recovery B-/C-/W-,
  and explicit negative-float severity N/dN+ (`.../li_indices.py:324-368`; `docs/rulings/LI-01-fcbi-v0.5.md:45-79`).
- **Timing/population:** weights primary burn at the window start and exposes
  start/end/min-endpoint as a sensitivity set; completed-in-window work is
  disclosed as omission rather than silently making a month benign (`.../li_indices.py:324-384`; ruling `.../LI-01-fcbi-v0.5.md:84-119`).
- **Target governance:** selected terminal target, propagated non-target
  governance, unresolved/ineligible quarantine and eligible-burn coverage are
  first-class outputs; target/basis/settings/calendar changes segment the
  operational cumulative series (`.../li_indices.py:360-418,1007-1052`).
- **Enumeration/calendar:** fixed reference 8 h/day, discrete-member margins,
  exact streamed `float_paths`, λ-invariant frontier, and an exact 512-path cap
  replace the old top-10/shared-RF assumptions (`.../li_indices.py:45-66,561-680`; `.../paths.py:80-92,469-495`).

### FCBI v0.5.6 hardening (not number-changing)

The branch records v0.5.6 as provenance/API/test hardening only: no canonical
number moves (`docs/rulings/LI-01-fcbi-v0.5.md:415-439`).  The five changes are:

1. Series-integrity guard for changeset/schedule alignment; inconsistent series
   becomes NOT EVALUATED (`.../li_indices.py:916-967`).
2. Stable target code with moved target UID disclosed as PROVISIONAL via
   `target_uid_changed`, history, and note, not rejected (`.../li_indices.py:432-443,969-978`).
3. Non-real/bool/non-finite/out-of-range λ inputs are rejected without raising;
   legacy v0.4 λ remains unbounded above (`.../li_indices.py:867-894,1039-1052`).
4. Deterministic mixed-topology/hash-seed corpus expands equivalence and
   frontier testing (`docs/rulings/LI-01-fcbi-v0.5.md:429-435`).
5. Optional `_target_distance(..., stats=None)` instrumentation records path
   count/convergence/cap/stop reason without affecting results (`.../li_indices.py:561-570,600-606`).

## 4. Behavioral inventory — kernel v2 and Wave-4 rulings

### Q-B and D1–D4

The accepted kernel-v2 ruling is explicitly number-changing for LI-04 PCI,
LI-05 RDI, LI-07 CDI, and LI-09 BWI (`docs/rulings/LI-kernel-v2-2026-07-12.md:1-10`).

- **Q-B:** build a new governed LI kernel rather than extend the v0.4 basis
  (`.../LI-kernel-v2-2026-07-12.md:3-10`).
- **D1:** reuse the locked FCBI v0.5 nonnegative target-distance basis,
  convergence frontier, cap, governance quarantine, and stable target for the
  family; BWI uses its UID-pinned anchor (`.../LI-kernel-v2-2026-07-12.md:14-29`; implementation `.../li_indices.py:2260-2382`).
- **D2:** move negative-float severity beside, never inside, PCI/CDI as N and
  dN+ (`.../LI-kernel-v2-2026-07-12.md:30-35`; result fields `.../li_indices.py:455-490`).
- **D3:** CDI accrues dwell while an activity is live, retains earned history
  after completion, then stops; milestone markers no longer receive dwell
  allocation (`.../LI-kernel-v2-2026-07-12.md:36-43`).
- **D4:** LI-04 PCI is provisional/ungraded until real-series anchors are
  recalibrated; LI-05/LI-09 stay graded and LI-07 remains unscored
  (`.../LI-kernel-v2-2026-07-12.md:44-50`; `scorecard.yaml:478-493`).

The direct before→after number/basis changes are recorded as:

- **PCI:** ≤10 shared-RF paths/floor 0.1 → all enumerated discrete-work paths
  on target-relative weights; uniform deepening leaves PCI unchanged while N/
  dN+ carries severity; cap/target/λ failures are NOT EVALUATED
  (`.../LI-kernel-v2-2026-07-12.md:79-84`).
- **CDI:** own-float fallback/milestones/completed post-completion accrual →
  live, resolved, ungoverned discrete work, with unresolved/governed counts
  disclosed and accrue-while-live history (`.../LI-kernel-v2-2026-07-12.md:79-84`; matrix row `src/scheduleiq/metrics/matrix.yaml:992-1004`).
- **RDI:** old RF-band/fallback and later-endpoint completion gate → resolved,
  ungoverned target-distance band, earlier-endpoint demonstration, quarantine-
  honest NOT EVALUATED sentinel (`.../LI-kernel-v2-2026-07-12.md:79-84`; matrix row `.../matrix.yaml:966-978`).
- **BWI:** RF-to-completion basis → distance to its own UID-pinned bow-wave
  milestone, unresolved/governed exclusion, fixed horizon and required-pace
  break test (`.../LI-kernel-v2-2026-07-12.md:79-84`; matrix row `.../matrix.yaml:1018-1030`).

### Q-F, Q-G, Q-H

- **Q-F / MML full package:** one basis per trade (resource units/hour only if
  every data-bearing window has resources, else activity-days), sustained best
  two-window clean run within 25% spread, delay-event overlay, and named
  no-clean-mile reasons (`docs/rulings/LI-10-mml-v2-2026-07-12.md:9-43`; implementation `.../li_record.py:1011-1016,1118-1137,1183-1269`).
- **Q-G / BDI fixed basis + LOE out:** original planned duration for every step,
  LOE/summary zero length, explicit baseline/target parameters and disclosed
  defaults; the recorded probe moves 71.4% to 33.3% and makes it progress-
  invariant (`docs/rulings/LI-06-bdi-v2-2026-07-12.md:9-35,37-50`; implementation `.../li_record.py:622-649`).
- **Q-H / sensitivity sets:** λ and band defaults are professional conventions,
  not calibrated constants; expose PCI/CDI λ={3,5,10} and CDI/RDI/BWI band={5,
  10,20} sets, plus recorded MML constants (`docs/rulings/LI-kernel-constants-2026-07-12.md:8-35`; implementation `.../li_indices.py:2401-2463`).

## 5. Review-wave rulings (RW-*)

These are the branch's later dispositions, recorded without a soundness
judgment:

- **RW2-1:** zero float evidence on a branch returns no RF evidence; do not
  fabricate RF=0/weight=1 through the spliced tail (`docs/rulings/LI-04-LI-07-kernel-loe-port-2026-07-12.md:102-106`).
- **RW3-F1:** BWI projected-break and RDI demonstrated-pace paths require usable
  evidence; quarantine/NOT EVALUATED replaces fabricated zero readings
  (`docs/rulings/LI-kernel-v2-2026-07-12.md:137-140`).
- **RW3-F2:** family kernel target resolution is CODE-only to mirror FCBI; only
  BWI's pinned anchor is UID-first then code (`.../LI-kernel-v2-2026-07-12.md:140`; `.../li_indices.py:2304-2316`).
- **RW3-F3:** BDI validates `baseline_index` type before range checking and
  degrades rather than raising (`.../LI-kernel-v2-2026-07-12.md:141`; `.../li_record.py:655-665`).
- **RW3-F4:** a fully quarantined CDI board is NOT EVALUATED with quarantine
  counts/reason, not the benign empty-board message (`.../LI-kernel-v2-2026-07-12.md:142`).
- **RW3-F5:** invalid negative/NaN/non-real band values make CDI/RDI/BWI and
  sensitivity points NOT EVALUATED instead of fabricated clean values
  (`.../LI-kernel-v2-2026-07-12.md:143`; `.../li_indices.py:2445-2463`).
- **RW3-F6:** PCI keeps all paths and discloses that governance is beside the
  concentration measure; this disposition is disclosure-only and does not move
  numbers (`.../LI-kernel-v2-2026-07-12.md:144`).
- **RW3-F7:** demonstrated-pace planned duration is read at the earlier window
  endpoint in both pace and overrun, so post-completion OD edits no longer move
  LI-05/LI-09 (`.../LI-kernel-v2-2026-07-12.md:145`; matrix row `.../matrix.yaml:966-970`).

## Cutover boundary

This document records what is present at matrix tip and how it differs from
`e99f2010`; it does not recommend adoption, re-score anchors, or port code.
The approved lineage's R-ID portability report remains separate:
`docs/audit/R_ID_matrix_portability_2026-07-14.md`.
