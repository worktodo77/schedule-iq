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
- A **negative driver float never makes d negative** — the reference is the
  **rank-1 driving path** (the tool-of-record float walk) and the `max(0, ·)`
  clamp keeps d ≥ 0 for any off-path feeder more negative than the spine
  (treated as co-critical, d = 0; not the global minimum — see the REV-05
  reconciliation in the wave-2 review).  Margins are on a fixed reference-hours,
  discrete-members-only basis (REV-02/07).
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

**Enforcement scope (disclosed; strengthened in the wave-2 review below).**
Predicates (1), (2), (3), and (6) are computationally enforced from tool-of-record
data.  Governance (3) is traced through the network from **both** window
endpoints (so a non-target constraint or expected finish ADDED mid-window
quarantines what it governs), and predicate (5)'s **expected-finish** basis is
propagated the same way (not only checked on the activity itself).  Predicate
(4)'s *alternative terminal* is enforced for the *constrained* case (a
constrained alternative terminal governs its ancestors via propagation) and, for
the *unconstrained* case, is reflected implicitly in the tool-of-record float the
activity already carries (the binding successor governs its late dates);
*external/open-ended successor* detection and predicate (5)'s *resource-leveling*
basis await the CPM engine (ADR-0007) and are O7.6 documented captures.  An
incomplete population member whose float is not measurable at both endpoints is
counted as *unmeasurable* (not silently dropped), so eligible-burn coverage is
never mistaken for data completeness.

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
3. **Depth rule** — the raw top-10 cutoff is replaced by a lazy enumerator
   (`iter_float_paths`) that streams **EXACTLY** the reference `float_paths`
   sequence (same paths, same order) one at a time, with a **PROVEN** early-stop:
   the min reference float over discrete activities that can reach m and are not
   yet used lower-bounds every not-yet-enumerated path's margin, so once that
   frontier's weight (at the fixed, λ-invariant `FCBI_CONV_LAMBDA`, W3-02) falls
   below `FCBI_CONV_TOL` every omitted path is immaterial.  The bound needs **no
   monotonicity** of the native-rel order — that order is genuinely **non-monotone**
   (a later path can expose a lower-float branch that was hidden behind a
   since-consumed activity), and the frontier's soundness instead rests on being
   evaluated against `float_paths`'s **own** cumulative used set.  Because
   `kernel_weight(d, λ)` increases in λ, a frontier proven immaterial at
   `FCBI_CONV_LAMBDA` is immaterial at every λ ≤ it, so the weighting λ is capped
   at `FCBI_CONV_LAMBDA` (W4-05) to keep the resolved basis valid.  `FCBI_PATHS_MAX`
   caps a pathological wide near-critical fan **exactly** at the (MAX+1)-th path
   (then `depth_capped`, provisional; W4-07).  Activities on none of the enumerated
   paths are unresolved (O6), never own-float.  **Provenance:** the v0.5.4 best-first
   / priority-queue variant of this enumerator was **WITHDRAWN** in wave-4 — it
   cached feeders against a stale used set and only handled a rising rel, so it
   diverged from `float_paths` (wrong path splices → wrong distances, and a frontier
   read off a corrupted used set that dropped material-weight activities; W4-01/02).
   Correctness over performance (governed constraint): the enumerator is now the
   reference algorithm streamed, with the cost bounded by the sound frontier and the
   cap, not by weakening the enumeration (§ wave-4 disposition).
4. **Multiple targets** — v1 profiles a single target; summing across targets is
   prohibited without an explicit allocation rule (double-counting).  Standing
   disclosure.
5. **Engine-settings basis** — scheduling-option changes captured from
   `ScheduleSettings` feed the basis-change rule (retained logic / progress
   override, open-ends, expected finish, critical-float threshold, lag
   calendar).  Full per-run settings table is a documented capture.
6. **Constraint classification** — late-type constraints traced for governance
   (O6).  Record-network vs logic-only materiality is a **single** criterion,
   `|d_record − d_logic| ≥ λ` (the wave-2 reviewer showed the previously-stated
   "OR weight ratio ≥ 2" is mathematically identical, since the weight ratio is
   `2^(|Δd|/λ)`, so the OR was redundant); the absolute contribution delta
   `c·|w_record − w_logic|` is reported alongside the flag.  Full dual-pass
   reporting is a documented capture pending the CPM engine (ADR-0007).
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

## Wave-2 review — third reviewer (independent provider), loop closed

A second independent pass (different provider) raised seventeen findings against
the shipped branch.  Most were well-founded; all are dispositioned below.  Fixes
land in `analytics/li_indices.py` + `analytics/paths.py` + `analytics/li_wiring.py`
with regression tests; two are doc reconciliations and one is disputed.

| ID | Sev | Finding | Disposition |
|---|---|---|---|
| **REV-01** | BLOCKER | Default target resolution reused the BWI heuristic and could select a constrained *intermediate* milestone (or a task), not the terminal completion m. | **Fixed.** New `_resolve_fcbi_target` selects a **terminal** finish milestone (no path to another finish milestone), never a task, and flags `target_auto_resolved` so the analyst confirms m (O7.1). |
| **REV-02** | BLOCKER | Distance/ranking used each activity's *native* calendar days while burn used the 8h reference — driver could flip on mixed calendars. | **Fixed.** FCBI margins/distances now use a fixed-reference-hours, discrete-members-only path margin (`FloatPath.rel_float_hours`). Driver *identity* still follows the tool-of-record walk (ADR-0004), disclosed. |
| **REV-03** | BLOCKER | Basis-change windows still populated operational B/C/top burners and the wiring presented them as operational; the headline could revive a stale segment. | **Fixed.** Basis-change windows are excluded from the operational aggregate; the wiring reports them as basis-change (requirement-induced) and never revives a prior segment. |
| **REV-04** | BLOCKER | Governance used the earlier endpoint only; a constraint added mid-window, a downstream expected finish, and alternative terminals were not caught (over-inclusion). | **Fixed** (union of both endpoints + expected-finish propagation; unmeasurable float now counted). The over-broad "never over-includes" claim is corrected; unconstrained alternative-terminal governance is disclosed as tool-of-record-reflected. |
| **REV-05** | MAJOR | O1 prose ("global minimum" reference) contradicted the post-F2 implementation (rank-1 reference). | **Fixed (doc).** Rulings/proposal now state the rank-1 driving-path reference with the clamp. **Disputed:** the reviewer's alternative (quarantine a more-negative feeder) is rejected — clamping a super-critical feeder to d = 0 (co-critical) is simpler and defensible. |
| **REV-06** | MAJOR | Basis signature ignored constraint *type*, `constraint2`, `must_finish_by`, `baseline_finish`, `critical_definition`/`actual_dates`, and fired on a stale date when type was NONE. | **Fixed.** Requirement-basis signature compares constraint type + date (primary and secondary), project must-finish-by and baseline, and the added settings; stale dates under type NONE are ignored. |
| **REV-07** | MAJOR | LOE/summary nodes could set a path margin. | **Fixed.** `rel_float_hours` uses discrete members only. |
| **REV-08** | MAJOR | `FCBI_PATHS_N=50` was labelled "convergence" but is a hard cap. | **Fixed (v0.5.2).** Wave-2 relabelled a cap + surfaced `depth_capped`; the **principal then directed building the full adaptive convergence loop** (`_target_distance` enumerates 25→50→… until the max possible omitted weight < `FCBI_CONV_TOL`, ceiling `FCBI_PATHS_MAX`), so a cap-limited run is disclosed as provisional, not implied converged. |
| **REV-09** | MAJOR | The cross-window aggregate burner stored the first window's d/w against a summed contribution — arithmetically incoherent when printed. | **Fixed.** Aggregates now carry an **effective weight** (Σc·w / Σc) so consumption × weight == contribution; deterministic `(-contribution, -consumption, code)` ordering; basis-change windows excluded. |
| **REV-10** | MAJOR | Completion "moved" is endpoint-derived (null-vs-zero exporter-sensitive) and the list was capped at 15. | **Partially fixed.** The full completer list is now returned (counts were already complete). "moved" is documented as an endpoint-derived, exporter-sensitive supplement; prior float/weight remain the primary completion signal. |
| **REV-11** | MAJOR | Incomplete members with missing float were invisible, so coverage read 100% of *scored* burn. | **Fixed.** `unmeasurable_count` is reported per window; coverage is explicitly eligible-**burn** coverage. |
| **REV-12** | MAJOR | λ ≤ 0 / NaN / Inf raised or produced w > 1 / NaN. | **Fixed.** λ validated at the entry point (FCBI returns a reason; the shared kernel falls back to the default), never raises. |
| **REV-13** | MAJOR | A valid zero-movement window returned the "distance unresolved" failure reason. | **Fixed.** The result distinguishes basis-resolved-but-stable from unresolved; a stable window carries no failure reason. |
| **REV-14** | MINOR | An unresolved end distance was backfilled with the start distance. | **Fixed.** End/min timing members reuse the start weight only when the end is unresolved (no fabricated end distance); primary start-of-window scoring is unaffected. |
| **REV-15** | MINOR | Ineligible recovery was dropped with no quarantine subtotal. | **Fixed.** `recov_quarantine` mirrors the burn quarantine subtotal. |
| **REV-16** | MINOR | Matrix `unit: days` for a gross activity-day value. | **Fixed.** `unit: activity-days`. |
| **REV-17** | MINOR | Non-target zero-duration milestones counted as burners (undefined). | **Fixed (governed decision).** Non-target milestones are excluded from B/C as schedule markers and disclosed in `milestone_margin_changes`. |

Wave-2 regressions added; suite green: **186 passed, 1 skipped**.  The reviewer's
seven open-question recommendations are folded into the briefing
(`docs/LI-01-v0.5-briefing.md`), including its sharp observation that the O7.6
weight-ratio ≥ 2 criterion is mathematically identical to |Δd| ≥ λ (so the "OR"
was redundant — now stated as one criterion).

## Settled decisions — open questions Q1–Q7 (principal: Alex Bachowski, v0.5.2)

The seven open methodology questions were adjudicated by the principal. Recorded
here as binding; the briefing carries the same set.

| Q | Decision | Implementation |
|---|---|---|
| **Q1 headline** | The FCBI headline is the **(B, C) pair** — B is the cumulative curve, C annotated at each point; **W = B·C** is the derived single-number diagnostic. B is never reported alone. | Interpretation/wiring lead with B and C together and label W derived; ruling O2 unchanged. |
| **Q2 λ** | Keep **λ = 5** working days as the house default; state it as "≈5 reference working days of driver-relative path-margin separation"; **require a λ ∈ {3,5,10} sensitivity set** in contested/expert use; it is a professional convention, not a calibrated constant. | `fcbi_lambda_sensitivity(sa, target, lams=(3,5,10))` returns B (λ-invariant) plus C/W per λ. |
| **Q3 materiality** | **Single** criterion `|d_record − d_logic| ≥ λ` (the weight-ratio ≥ 2 form is identical); report the absolute contribution delta `c·|Δw|` alongside. Full dual-pass awaits the CPM engine. | Recorded (O7.6); dual-pass is a documented capture. |
| **Q4 headline curve** | Resolved with Q1 — **(B, C) pair**, W available. (Codex preferred cumulative W; the principal chose the O2-aligned pair.) | As Q1. |
| **Q5 N / ΔN⁺** | A **distinct severity strip** beside (B, C); never folded into the kernel or the headline. | Already so (`n_severity`, `n_deepening`). |
| **Q6 coverage** | Report a **full population-coverage block** beside eligible-burn coverage: candidate-population count, TF-evaluability, population-eligibility, and an exclusion-reason breakdown. | `candidate_pop`, `pop_tf_evaluable`, `pop_eligible`, `pop_exclusions`, and `tf_evaluability` / `population_eligibility` properties. |
| **Q7 multiple targets** | **Strict no-sum rule** now: never sum across targets; v2 shows separate target profiles + a shared-activity overlap disclosure; a combined scalar, if ever needed, uses **one-hot** allocation to a predeclared primary target, never fractional weights. | Recorded as the v2 roadmap rule (O7.4). |

Two review judgment calls were also confirmed by the principal: **keep the
distance clamp** (a feeder more critical than the tool-of-record rank-1 driver is
treated as co-critical d = 0, not quarantined — Codex's REV-05 alternative
rejected), and **build the adaptive convergence loop** rather than settle for the
cap-plus-flag (REV-08).

Suite after settlement: **191 passed, 1 skipped** (5 new decision regressions).

## Wave-3 review — third reviewer (GPT-5.6 Pro), loop closed (v0.5.3)

A third independent pass raised ten findings against the v0.5.2 head, most on the
new subsystems (adaptive convergence, population coverage, λ-sensitivity).  All
dispositioned; the one headline blocker did not reproduce on the real code.

| ID | Sev | Finding | Disposition |
|---|---|---|---|
| **W3-01** | BLOCKER | Claimed the convergence stopping bound is unsound because `float_paths` is not margin-monotone (a low-margin branch emitted only after a higher-margin parent). | **Disputed — not reproduced.**  On the actual `float_paths`, the reviewer's exact topology enumerates in monotone margin order and the low-margin branch (R→Q→X, margin 5) is resolved at rank 2, never omitted (the reviewer's throwaway harness diverged from the real greedy feeder search).  Guarded by `test_fcbi_w3_01_hidden_low_margin_branch_resolved`; a **monotonicity guard** now marks the run provisional if `float_paths` ever violates the assumption, so the bound is sound regardless. |
| **W3-02** | BLOCKER | λ was threaded into `_target_distance`'s convergence, so the resolved set and B changed with the weighting λ — B was not λ-invariant. | **Fixed.**  The distance basis is now **λ-INDEPENDENT**: convergence is judged at a fixed `FCBI_CONV_LAMBDA = 10`, not the weighting λ.  B, coverage, and the eligible population are identical at every λ; the sensitivity reports one invariant B.  Regression: `test_fcbi_w3_02_b_lambda_invariant`. |
| **W3-03** | BLOCKER | The headline paired cumulative B and W with the *latest window's* C and printed a false `W = B·C`. | **Fixed.**  A cumulative-proximity series `C^cum = W^cum / B^cum` is computed and used in the headline, so `W^cum = B^cum · C^cum` is exact; `LambdaPoint.cumulative_c` is likewise cumulative.  Regression: `test_fcbi_w3_03_cumulative_c_identity`. |
| **W3-04** | MAJOR | An explicit target bypassed all validation (a task or intermediate milestone was accepted). | **Fixed.**  Explicit targets are validated as terminal finish milestones exactly like auto-resolved ones; an invalid one returns NOT EVALUATED. |
| **W3-05** | MAJOR | Every convergence depth reruns `float_paths` from scratch; the ceiling probe (513 feeders) did not complete quickly. | **FIXED (v0.5.4).**  Replaced with a **lazy best-first generator** (`paths.iter_float_paths`) that computes each path once (no restart/re-scan) and a **PROVEN frontier bound** (the min reference float over unused activities that can reach m lower-bounds every not-yet-enumerated path — no monotonicity assumption).  Result: 100-fan 3.0 s → 0.06 s, 150-fan 10.2 s → 0.16 s, a far-off-critical 500-fan stops after ~1 path (0.005 s), the 513-fan completes (3.6 s) and is correctly capped provisional.  Distance maps verified identical to `float_paths` on 120 random networks + mixed calendars. |
| **W3-06** | MAJOR | The later endpoint's `depth_capped` was discarded (only the earlier used). | **Fixed.**  `win_capped = cap_e or cap_l`, propagated to the window and result. |
| **W3-07** | MAJOR | `fcbi_lambda_sensitivity` discarded per-λ reasons/provisional/coverage and returned failures as blank/zero points. | **Fixed.**  `LambdaPoint` carries `status`/`reason`/`depth_capped`; the set fails as a whole on a structural failure (invalid target) and per-point on an invalid λ; coverage/quarantine reported once. |
| **W3-08** | MAJOR | Candidate qualification tested only the earlier activity's type, so a task→LOE/milestone conversion still entered B. | **Fixed.**  A candidate must be a discrete task at BOTH endpoints; a type change is excluded from B/C and disclosed in `pop_exclusions`. |
| **W3-09** | MINOR | A network with exactly `FCBI_PATHS_MAX` paths was falsely marked `depth_capped`. | **Fixed.**  A one-path lookahead (`n+1`) distinguishes "exactly max" (exhausted) from "more exist." |
| **W3-10** | MINOR | Milestone margin change stored `abs(delta)`, losing erosion-vs-recovery. | **Fixed.**  New `MilestoneMarginChange` carries a `signed_delta_days`. |

Wave-3 regressions added; suite green: **199 passed, 1 skipped**.

**v0.5.4 follow-up (W3-05 closed) — later CORRECTED in v0.5.5:** the convergence
machinery was rebuilt on a lazy best-first generator with a frontier bound.  Wave-4
subsequently showed that generator was **not** equivalent to `float_paths` (see the
wave-4 disposition below); it was withdrawn and the enumerator re-based on the exact
reference sequence in v0.5.5.  The frontier bound is retained but its soundness is
now correctly grounded on `float_paths`'s own used set.  Remaining disclosure: the
generic `MetricResult.value` is the scalar B, with C always carried in the narrative
(Q1 mitigation, not a strict never-B-alone guarantee at the framework-value level).

## Wave-4 review — fourth reviewer (Codex GPT-5.6 Pro), loop closed (v0.5.5)

A fourth independent review targeted the v0.5.4 enumerator and its frontier.  Its
central claim — that `iter_float_paths` was **not** exactly equivalent to the
reference `float_paths` — **reproduced** against the real imported functions in one
process (the mandated "reproduce before modifying" step), overturning the v0.5.4
equivalence claim (the earlier 120-network check was insufficient; two concrete
counterexamples give divergent per-activity distances).  Both blockers are now
permanent regressions.  Governed constraint honoured: **correctness over
performance** — the enumerator was re-based on the reference algorithm rather than
kept as a faster-but-divergent oracle.

| ID | Severity | Finding | Disposition |
|----|----------|---------|-------------|
| **W4-01** | BLOCKER | The best-first iterator spliced a feeder onto the wrong tail (an all-8h FS-only net: iter path 3 `A04,A13,A14,A18,A20,T` vs reference `A04,A13,A14,T`), giving A18 a spurious `d=0` instead of `29.625`.  Root cause: lazy revalidation only re-pushed on a *rising* rel and fixed the tail at push time, but consuming an activity can make a feeder's rel *fall* and reroute its walk. | **Reproduced, then Fixed.**  `iter_float_paths` was rewritten to stream `float_paths`'s **exact** round structure (re-scan every found path, recompute every feeder under the current `used`, same `(rel, code)` selection and first-seen tie-break).  `d(A18)=29.625` restored.  Regression: `test_w4_01_counterexample_regression`; corpus `test_w4_03_iter_exactly_matches_float_paths_corpus`. |
| **W4-02** | BLOCKER | The frontier certificate could omit a material-weight activity: the iterator split `A01,A06,A08,A16,T` into two wrong paths, omitted A06/A08 (`d=None`), and the frontier — read off the **corrupted** used set — falsely declared convergence (`depth_capped=False`) while dropping weight 0.354. | **Reproduced, then Fixed.**  With the exact enumeration the frontier is evaluated on `float_paths`'s **own** cumulative used set (yielded per path); A06/A08 now resolve at `d=15` (weight 0.354).  Frontier soundness proven and property-tested (below).  Regression: `test_w4_02_counterexample_regression`. |
| **W4-03** | MAJOR | The equivalence test was **circular** — it built the "reference" distance map from the iterator itself, so it could never catch a divergence. | **Fixed.**  The test now builds the oracle **directly** from `float_paths`; adds a 500-DAG seeded corpus asserting byte-for-byte path-sequence identity and resolved-distance agreement, a 500-DAG frontier-soundness property (0 material omissions on uncapped runs), determinism, and both blocker counterexamples.  `test_w4_03_*`. |
| **W4-04** | MAJOR | The λ-sensitivity set re-enumerated float paths per λ (≈ `(len(lams)+1)·n_sched` enumerations); the `_walk` re-scan was also needlessly triangular. | **Fixed.**  `_prepare_fcbi_basis` computes the λ-independent distance/governance caches **once**; `_fcbi_from_basis` weights them per λ (a 2-schedule set now does **2** enumerations, verified by `test_w4_04_sensitivity_reuses_one_basis`).  The enumerator adds two provably-equivalent per-round optimisations (feeder memo by pred; attachment-activity dedup), cutting the wide-fan cost without changing any result.  (The reference re-scan's residual O(N²) on a pathological wide near-critical fan is accepted under the correctness-first mandate; such a fan is capped/provisional, and the common far-off case is milliseconds.) |
| **W4-05** | MAJOR | The weighting λ was unbounded above; a λ larger than the convergence reference `FCBI_CONV_LAMBDA` invalidates the frontier (an omitted path immaterial at λ=10 can be material at λ>10). | **Fixed.**  λ must be finite and in `(0, FCBI_CONV_LAMBDA]`; λ>10 (and non-finite/≤0) → NOT EVALUATED, or a failed sensitivity point (only that point).  `test_w4_05_lambda_range_enforced` covers −1, 0, NaN, Inf, 3, 5, 10, 10.000001, 20. |
| **W4-06** | MAJOR | An explicit target only had to be terminal in **some** update (`any`), and auto-resolution looked at a single schedule — a target could change basis across the series undetected. | **Fixed.**  A **stable target basis** is required: an explicit target must be a terminal finish milestone in **every** update (`all`); auto-resolution takes the **intersection** of per-update terminal-finish-milestone codes (latest-finishing preferred); an empty intersection or a target absent from an update → NOT EVALUATED (target-basis discontinuity).  `test_w4_06_*`. |
| **W4-07** | MINOR | The depth cap fired one path early/late relative to the intended boundary. | **Fixed.**  The cap fires **exactly** when a `(MAX+1)`-th path exists (generator one-path lookahead, checked before the exhaustion shortcut and before folding the extra path in): MAX−1 and MAX → not capped, MAX+1 and MAX+2 → capped.  `test_w4_07_exact_cap_boundary`. |

**Frontier soundness (now proven, W4-02).**  Every not-yet-enumerated path's unique
members are a subset of the still-unused activities, so a future path's branch margin
(a min of member floats) is ≥ the min reference float over reachable, discrete,
unused activities — the frontier value.  Hence every omitted path's distance ≥ the
frontier distance, and if the frontier weight (at `FCBI_CONV_LAMBDA`) is below
`FCBI_CONV_TOL` every omitted path is immaterial.  This holds **only** because the
used set is `float_paths`'s true trajectory; the v0.5.4 defect was precisely a
frontier read off a divergent enumeration's used set.  Because `2^(-d/λ)` increases
in λ, immateriality at `FCBI_CONV_LAMBDA` implies it for every λ ≤ that reference,
which is why the weighting λ is capped there (W4-05).

Wave-4 regressions added; suite green: **212 passed, 1 skipped**.

## Wave-5 review — fifth reviewer, core ACCEPTED; v0.5.6 hardening only

A fifth independent adversarial review exercised the v0.5.5 enumerator, frontier,
λ range, target-stability rule, prepared-basis refactor, and cap across ~35,000
adversarial networks (equivalence) and ~10,000 uncapped networks (frontier
soundness, 15,335 omitted activities checked).  **The core methodology is accepted
and is NOT reopened:** exact `float_paths` equivalence, frontier soundness,
λ ∈ (0, 10], stable-terminal-target enforcement, one-basis λ-sensitivity, and the
exact path cap all survived; the correctness-first performance tradeoff is accepted.

The wave produced only **pragmatic, non-methodology hardening** (v0.5.6).  None of
the below is a release blocker or a defect in the FCBI arithmetic — the numbers are
unchanged on every canonical series.

| Item | Class | Disposition |
|------|-------|-------------|
| **1 — Series-integrity guard** | Defensive software hardening | The `id()`-keyed distance cache assumed the canonical construction (each ChangeSet built from the same Schedule objects in `sa.schedules`).  Added `_validate_fcbi_series_integrity(sa, target_code)`, used by `_prepare_fcbi_basis`: it checks window count = schedules−1 and that each window joins `schedules[i] → schedules[i+1]` by project id, data date, target-code presence, forward date order, and `source_sha256` **when present on both**.  It does NOT require Python object identity — semantically identical clones pass and stay numerically identical; an ordinary cache miss is not a failure (the loop recomputes such endpoints).  A clearly inconsistent series is NOT EVALUATED with an audit reason.  This is a consistency guard, not a methodology gate. |
| **2 — Target UID continuity** | Nonblocking provenance disclosure | The target CODE is enforced stable + terminal in every update (W4-06), but its internal UID can legitimately move (re-import, migration, delete-and-recreate).  A moved UID no longer needs to be silent nor a rejection: the run continues, is flagged **PROVISIONAL**, and carries `target_uid_changed` / `target_uid_history` / `target_continuity_note` plus an interpretation warning to confirm the milestones denote the same contractual completion.  A UID change is explicitly NOT treated as proof the target changed — the numbers are identical to the stable-UID run. |
| **3 — λ input type hardening** | API robustness | `_invalid_lambda_reason` now rejects non-`Real` and `bool` inputs (bool subclasses int, so `True`/`False` would else pass as 1/0) BEFORE any arithmetic, and `run_li_indices` guards its legacy-kernel λ selection the same way (the v0.4 kernel is NOT bounded by 10 — any finite positive λ is valid there).  The public entry point never raises on any λ input type. |
| **4 — Corpus reproducibility** | Test quality | The randomized equivalence corpus now builds relationships in `sorted` order (stable across `PYTHONHASHSEED`), adds a 250-DAG **mixed-topology** corpus (FS/SS/FF/SF, ± lags, LOE nodes, parallel non-terminal finish milestones, None/negative float, shared merges, deep chains), and compares path count, code sequence, `rel_float_days`, `rel_float_hours`, the full resolved distance map, determinism, and absence of duplicate path signatures.  A subprocess test proves byte-identical output under different hash seeds.  The W4 blocker counterexamples are retained permanently. |
| **5 — Enumeration instrumentation** | Optional audit metadata | The exact enumerator is NOT replaced.  `_target_distance` gained an optional `stats` dict (default `None`) recording `paths_enumerated` / `convergence_stopped` / `depth_capped` / `stop_reason` — purely observational, no effect on the result, no new work-budget cap. |

v0.5.6 hardening added; suite green: **225 passed, 1 skipped**.  FCBI v0.5.6 is
non-number-changing provenance and API hardening only; the accepted v0.5.5
path-distance and frontier methodology is unchanged.
