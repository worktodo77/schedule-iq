# LI-01 FCBI — Recorded Rulings, v0.5.0 (governed methodology revision)

**Status:** accepted · **Date:** 2026-07-10 · **Supersedes:** FCBI v0.4.4 ·
**Process:** two-reviewer consensus (implementation-side review + independent
external peer review, converged 2026-07-10), methodology-owner approved.

This is a **number-changing revision** of check LI-01 (FCBI — Float Criticality
Burn Index).  Per GOVERNANCE.md §1 the full governance package moves together:
spec text (ANALYTICS_PROPOSAL.md §9.1) + check-matrix row (matrix.yaml LI-01) +
seeded fixtures + regression tests (tests/test_li_indices.py, probe set §P) +
this recorded ruling.  Implementation: `analytics/li_indices.py` (FCBI section,
self-contained; the v0.4 RF kernel is retained unchanged for PCI/CDI/RDI/BWI).

The audit-first "before" behavior (v0.4.4 on the §P probes) is preserved in the
change log of the white-paper briefing, [docs/LI-01-v0.5-briefing.md](../LI-01-v0.5-briefing.md).

---

## O1 — RF basis: nonnegative target-specific distance (keystone)

**Ruling.**  Replace the RF variable with a distance `d_i ≥ 0`: the minimum,
over enumerated float paths containing activity *i*, of *(that path's margin to
target m − the driving path's margin to m)*.  Consequences, all mandatory and
all implemented:

- Driving-path activities have **d = 0**.
- A **negative driver float never makes d negative** (the driving path is the
  global-minimum-margin reference, so every other path's margin ≥ it).
- The **own-total-float fallback is ABOLISHED**.  An activity on no enumerated
  path is *distance unresolved* and goes to the O6 quarantine — **never**
  assigned its absolute total float as a distance.
- Weight **w = 2^(−d/λ), λ = 5 working days, so w ∈ (0, 1] always**.  The w > 1
  "over-critical premium" is abolished (it was an artifact of the fallback
  basis).
- The v0.4.3 discrete-members-only path arithmetic carries over unchanged
  (`FloatPath.rel_float_days`, the branch-unique near-criticality).

**Verified (probe P1).**  X(TF 0→−3), Y(5→9), Z(10→8): X is the driver, d_X = 0,
w_X = 1.0 (was 1.516 under the end-weighted fallback premium); d_Z = 10 (start
of window), never negative; no weight exceeds 1.0.

## O2 — Primary outputs: B, C, optionally W (activity basis)

**Ruling.**

- **B** = Σ c_i — gross activity-float movement (burn side).  Never labelled
  "project float consumed" or "stock"; it contains replicated path float and is
  an activity-day aggregate.
- **C** = Σ(c_i·w_i) / Σ c_i — the burn-weighted mean proximity.  Never labelled
  a concentration statistic.  When B = 0, C is reported **NOT APPLICABLE** with
  a labelled reason, never 0.
- **W** = B·C may be reported as a derived diagnostic (equals the old weighted
  sum).  Docs state: (B, C) is an interpretive decomposition; it makes
  network-size dominance visible; it does **not** cure granularity or
  network-size dependence.
- Recovery side mirrors: **B⁻, C⁻**, identical conventions, tracked separately,
  never netted.
- **FCBI%** (the float-stock ratio, old Eq. 3) is **RETIRED**; the ratio and its
  sentinel are removed and the D = 0 regime disappears with it (see the FCBI%
  retirement record below).
- Scope language on every output: within-network trend instrument on a
  continuously maintained schedule; no cross-project or cross-granularity
  comparison; structural churn disclosed alongside.

**Verified (P1/P3/P5/P8).**  P1: B = 5, C = 0.7, W = 3.5.  P3: W = B·C on every
window.  P5: zero-burn window → C = NOT APPLICABLE.  P8: split changes B.

## O3 — Weight timing: supersession of min-RF

**Ruling.**  Primary convention for **both** burn and recovery is
**start-of-window, w(d_{i,u−1})**: nonanticipative, auditable from the opening
state, does not reprice earlier burn at eventual criticality.  Compute and
expose the **endpoint-timing sensitivity set** — start, end, min-endpoint —
labelled *exactly* "endpoint-timing sensitivity set," **never "band" or
"bounds":** the true within-window value is not bounded by these (distance can
dip below both endpoints mid-window).  See the min-RF supersession record below.

**Verified (P2/P4).**  P2: one window (start 2.5 / end 10 / min 10) vs two
windows (start 3.75 / end 7.5 / min 7.5).  P4: with opposite-direction burners
the min-endpoint aggregate strictly exceeds **both** endpoint aggregates — a
sensitivity set, not bounds.

## O4 — Noise: two tiers, only Tier 1 now

**Ruling.**  **Tier 1 (implemented):** a numerical tolerance tied to raw
source-field precision, applied **in hours before any hour→day conversion**;
covers storage precision, exporter rounding, float representation, and repeated
conversions only.  It is **not** an empirical noise filter.  **Tier 2 (NOT
implemented):** statistical noise treatment (deadbands, control limits,
persistence rules) is a separate calibration workstream gated on real
update-pair data.  No per-activity epsilon deadband — it is split/merge-
dependent (a 2 d loss contributes 1 whole, or 1 + 1 split, at eps = 1).

**Verified (P10).**  Sub-precision hour jitter (0.25 h < 0.5 h tolerance)
produces zero burn.

## O5 — Population: unchanged scope, new diagnostic

**Ruling.**  Retain the remaining-work population (incomplete at the later
update, discrete, weight-resolvable).  **Add the completion-omission
diagnostic** per window: count of activities completed in-window; their prior
positive and negative float; their prior weights; their share of the prior
live-work population — so a heavy-completion month cannot appear artificially
benign without disclosure.

**Verified (P11).**  An activity burning 15 d then completing in-window appears
in the omission diagnostic with prior float and weight, and **not** in B.

## O6 — Target governance: eligibility, quarantine, coverage

**Ruling.**  v1 scope: **one** selected terminal completion milestone m.  A
contribution enters the primary result only if the eligibility predicate holds:
(1) one selected terminal completion milestone; (2) a directed path to it;
(3) no non-target constraint or deadline governs its late dates — **including
propagated governance** (A→M→completion where an upstream activity carries no
constraint of its own but its late dates are governed by a constrained
intermediate milestone; a field-level check is insufficient — governance is
traced through the network from tool-of-record data); (4) no alternative
terminal or external successor governs it; (5) no resource leveling, expected
finish, or setting supplies an alternate late-date basis; (6) target and
scheduling basis unchanged within the window.  Ineligible or unresolved
contributions are **excluded and reported in a quarantine subtotal (never merely
flagged)**.  Report per window **eligible-burn coverage = eligible c /
(eligible c + quarantined c)**, NOT APPLICABLE when the denominator is zero.  No
acceptable-coverage threshold is invented.  ADR-0004 stays intact: if
tool-of-record output cannot establish governance, the contribution is
unresolved → quarantine.

**Enforcement scope (disclosed).**  Predicates (1), (2), (3), and (6) are
computationally enforced from tool-of-record data.  Predicate (4)'s *alternative
terminal* case is enforced implicitly — an activity whose only route leads to a
terminal other than m is on no enumerated path to m, so it is distance-unresolved
→ quarantine — while *external/open-ended successor* detection and predicate
(5)'s *resource-leveling* basis await the CPM engine (ADR-0007) and are O7.6
documented captures; the *expected-finish* half of (5) is enforced per activity.
This partial enforcement is conservative (it quarantines, never over-includes)
and is carried as a standing disclosure in the briefing.

**Verified (P7).**  A→M(constrained)→completion: A carries no constraint of its
own, yet predicate (3) routes A's burn to quarantine (governance traced through
M) and the coverage ratio reflects it.

## O7 — Specification expansion (all code-level)

Implemented (computationally, in `li_indices.py`) and/or documented as a
per-run capture, as noted:

1. **Target identity** — milestone id recorded per run (`FcbiResult.target_code`);
   a target-date change between updates triggers the basis-change rule (§O7.9).
2. **Path method** — exact MFP enumeration via the float-path module (§2.1);
   algorithm/source/version documented in ARCHITECTURE.md and the briefing.
3. **Depth rule** — the raw top-10 cutoff is replaced by a convergence
   enumeration (`FCBI_PATHS_N = 50`); activities on none of the enumerated paths
   are unresolved (O6), never own-float.
4. **Multiple targets** — v1 profiles a single target; summing across targets is
   prohibited without an explicit allocation rule (double-counting).  Standing
   disclosure.
5. **Engine-settings basis** — scheduling-option changes captured from
   `ScheduleSettings` feed the basis-change rule (retained logic / progress
   override, open-ends, expected finish, critical-float threshold, lag
   calendar).  Full per-run settings table is a documented capture.
6. **Constraint classification** — late-type constraints traced for governance
   (O6).  The record-network vs logic-only materiality rule (`d difference > λ`
   OR `weight ratio > 2`) is adopted and documented; full dual-pass reporting is
   a documented capture pending the CPM engine (ADR-0007).
7. **Calendar basis** — a fixed reference hours/day (`REFERENCE_HPD = 8.0`) with
   an exact conversion formula; calendar-definition changes feed the
   basis-change diagnostic.  This supersedes any "dominant calendar" language.
8. **Activity lineage** — re-code/split/merge/delete-recreate/scope-transfer:
   churn on eligible paths is disclosed alongside the index (scope note; change
   register).  Deeper lineage tracking is a documented capture.
9. **Basis-change segmentation** — target-date changes, rebaselines,
   scheduling-option changes, and calendar-definition changes mark the window a
   **BASIS-CHANGE WINDOW**: excluded from the continuous operational-burn trend,
   reported separately as requirement-induced margin change (real margin loss,
   not execution erosion), and the cumulative series segments/restarts after it.
10. **Time axis** — outputs carry actual data dates; burn rate B / (working days
    in window) is reported whenever window lengths differ; the cumulative series
    supports a date-based x-axis.

**Verified (P6/P9).**  P6: target date pulled 10 d earlier → basis-change window
fires, zero operational burn, requirement-induced margin change = 10 d reported
separately.  P9: unequal windows (21 d, ~90 d) carry burn-rate normalization.

---

## Supersession record — v0.4.2 min-RF ruling

- **Superseded rule (v0.4.2).**  Weight each activity's burn at the *minimum RF
  across the window's endpoints* (equivalently, the maximum weight), so that an
  activity crashing to critical mid-window is not under-counted.
- **New rule (O3).**  Weight at **start-of-window** as the primary convention;
  expose start/end/min-endpoint only as a labelled **sensitivity set**.
- **10→0 monotonic-cadence counterexample.**  A single activity whose distance
  falls monotonically 10 → 0 while consuming c = 10 scores, under the min-RF
  convention, **10.0 measured as one window** but **7.5 measured as two
  windows** (5 at min-weight 0.5 in the first half, 5 at min-weight 1.0 in the
  second).  A trend instrument whose value depends on how finely the analyst
  slices identical progress is not defensible (probe P2).
- **Hindsight-repricing objection.**  Min-RF reprices float burned early in the
  window at the criticality the activity *eventually* reached — it uses
  information not available at the time the float was burned, which an opposing
  expert correctly attacks as hindsight.
- **Note on the original motivation.**  The crash-to-critical concern that
  motivated min-RF was **partly an artifact of the abolished own-float
  fallback**: under the fallback an activity off all paths carried its absolute
  TF, so a late crash produced a large weight swing.  With the O1 driver-relative
  distance and quarantine of unresolved activities, that swing is far smaller,
  weakening the original case for min-RF.
- **Effect on regression anchors.**  All prior FCBI regression anchors are
  invalidated by the combined O1+O2+O3 change (basis, decomposition, and
  timing).  The X/Y/Z worked example is superseded; the new anchor is the P1
  probe and the briefing's new worked example.  The LI-01 Report Card scoring
  is marked **provisional/ungraded pending anchor recalibration** (scorecard.yaml
  `series_curve_overrides: LI-01`).

## Retirement record — FCBI% (old Eq. 3)

- **Retired.**  FCBI% = 100 × Σ c·w / Σ(TF⁺·w) — "share of the criticality-
  weighted float stock burned in the window" — together with its D = 0 sentinel
  (the reported value when the weighted float stock denominator was zero).
- **Reasons.**  (a) It implied a *stock* the index never had: the "float stock"
  denominator double-counted replicated path float and could be smaller than the
  numerator, producing values above 100% that were then rationalized as "erosion
  beyond available float."  (b) It invited cross-window and cross-project
  comparison the instrument does not support.  (c) The B/C decomposition (O2)
  supplies the interpretable view (gross size B, weighted proximity C) without a
  spurious ratio.
- **Replacement.**  None as a ratio.  Negative-float severity — the real signal
  the >100% readings were groping toward — is now carried explicitly beside B and
  C by **N = max(0, −F_m)** and **ΔN⁺** (O2/severity), never inside the kernel.
- **Removed surfaces.**  `FcbiWindow.fcbi_pct`, the `fcbi`/`fcbi_recovery`
  scalar fields, the >100% narrative in `li_wiring.py`, and the "normalized
  burn above 100%" language in the matrix row.

---

## Post-implementation review — second reviewer, loop closed

An independent second-reviewer pass (same protocol as the LHL v0.4.5 cycle) was
run against the shipped implementation and these rulings.  Five findings were
raised, reproduced, and dispositioned; the loop is **formally closed**.

| ID | Severity | Finding | Disposition |
|---|---|---|---|
| **F1** | BLOCKER | `_basis_change_reasons` fell back to the target's *forecast* (`early_finish`/`finish`) when it had no constraint date, so ordinary execution slippage on an unconstrained completion milestone falsely tripped a basis-change and restarted the cumulative — inverting O7.9's execution-erosion vs requirement-change distinction. | **Fixed.**  The target-date trigger now reads the **requirement basis only** (`constraint_date`, else `baseline_finish`); a moving forecast no longer fires.  Regression: `test_fcbi_forecast_slip_is_not_a_basis_change` (with a constraint-move control that still fires). |
| **F2** | MAJOR | `_target_distance` used the **global minimum** margin across all enumerated paths as the driver reference, so an off-driving-path feeder pushed negative by a non-target constraint became the reference and gave the true rank-1 driver d > 0, w < 1 — violating O1's mandatory "driving-path d = 0" and biasing C/W. | **Fixed.**  The reference is now the **rank-1 driving path** (`paths[0].rel_float_days`); the existing `max(0, …)` clamp keeps d ≥ 0 for a more-negative feeder.  Both O1 consequences now hold together.  Regression: `test_fcbi_offpath_negative_feeder_preserves_driver`. |
| **F3** | MINOR | The completion-omission diagnostic (O5) was gated on prior float being known, dropping a completer with unknown prior float from the count and list — the exact "benign heavy-completion month" O5 exists to prevent. | **Fixed.**  Completers are now **always** recorded and counted; prior float/weight fields are left `None` when unavailable.  Regression: `test_fcbi_completer_with_unknown_prior_still_disclosed`. |
| **F4** | NIT | The completion `moved` value skipped the Tier-1 hour tolerance (O4). | **Fixed.**  Tolerance now applied before the hour→day conversion in the completion path too. |
| **F5** | NIT/latent | `dist_cache`/`gov_cache` keyed by `id(schedule)` could `KeyError` on a malformed `ChangeSet` whose endpoints are not in `sa.schedules` (unreachable via `analyze_series`, but breaks the "never raises" contract). | **Fixed.**  Cache lookups now fall back to recomputation instead of raising. |

The reviewer independently reproduced P1, P7, the worked-example anchor, and the
driver-in-negative-float case, and verified O1–O7 semantics (distance
nonnegativity, B/C/W and recovery separation, start-of-window timing and the
sensitivity set, Tier-1 tolerance, remaining-work population, propagated
governance, coverage, and the fixed-reference conversion / burn-rate) with no
further defect.  Suite after fixes: **176 passed, 1 skipped** (3 new
post-review regression tests).
