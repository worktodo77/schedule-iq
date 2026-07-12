> **PROVENANCE (port record, 2026-07-12).**  Authored on the unmerged lineage-A
> branch (`claude/lhl-implementation-audit-xom1ah` lineage) against the v0.4.x
> state there; imported VERBATIM as the as-audited record and rationale for the
> RDI/BWI/CDI rulings ported to this base under
> [docs/rulings/LI-05-LI-09-rdi-bwi-port-2026-07-12.md](../rulings/LI-05-LI-09-rdi-bwi-port-2026-07-12.md)
> (principal ruling Q-A: port as-ruled; the kernel C1/mixed-path items are the
> Wave-1c package).  Code line numbers, commit hashes, and suite counts cited
> inside refer to that branch; every audited pre-ruling behavior was
> independently reproduced on this base (docs/audit/LI-02-10_audit_matrix_2026-07-12.md).

# RDI / BWI / CDI (LI-05 / LI-09 / LI-07) implementation audit

**Date:** 2026-07-08 · **Auditor:** Claude (lead) · Batch audit of the three
indices that share FCBI's criticality kernel / RF machinery, applying the
reusable template from the FCBI audit (docs/audit/FCBI_audit_2026-07-08.md).

> **PARTIALLY RESOLVED in v0.4.2 (2026-07-08).** The methodology owner approved
> **C1, C2, B2, X1**; all implemented with the governance quartet.
>
> **RESOLVED in v0.4.3 (2026-07-09).** The methodology owner ruled on the
> deferred items:
> - **B1 — BWI fixed reference horizon: ADOPTED (option A).** BWI normalizes
>   against a fixed horizon (constrained/promised date, else baseline finish,
>   else first-update forecast finish), held constant across updates, so a
>   slipping milestone no longer dilutes the bow wave.  A slip with unchanged
>   work now reads BWI = 1.0.  Scored (LI-09); pinned demo letter grades held.
> - **R2 — RDI accrual anchor: ADOPTED (P50).** Debt accrues against the running
>   P50 (median) demonstrated pace, with the running max retained as the reported
>   optimistic bound.  Scored (LI-05); pinned demo letter grades held.
> - **Mixed-path LOE residual: NEUTRALIZED.** The LI kernel now computes each
>   kept path's relative float over its discrete members only, so an LOE on a
>   mixed path no longer drives a discrete activity's RF.  Implemented as an
>   LI-specific layer on top of `float_paths()` (which is unchanged; the kernel
>   reads only its additive `unique_uids`).
> - **R1 — RDI demonstrated-pace basis: RESOLVED in v0.4.4 (2026-07-09) —
>   planned-scope basis AFFIRMED, with a companion overrun disclosure.**  The
>   earlier "actual elapsed" direction was reconsidered and reversed on
>   dimensional grounds (independent reviewer recommendation; second reviewer
>   concurred with modifications): an elapsed-time denominator is
>   concurrency-non-additive — parallel on-pace work would read as phantom
>   debt — and an elapsed-time numerator rewards overruns.  Demonstrated pace
>   remains planned near-critical scope actually retired per calendar
>   working-day (the only basis commensurable with required pace; "actually"
>   attaches to the completion dates).  The audit's legitimate concern — the
>   overrun signal must be visible — ships as the companion duration-overrun
>   ratio (Σ actual elapsed ÷ Σ planned of the same completions), per window
>   and per series, disclosed as a diagnostic and never an accrual input.
>   RDI accrual mathematics unchanged; §9.5 reworded.
>
> **Shared-kernel family audit (Part 2 of the ruling) — metric by metric:**
> | LI | Metric | Kernel/RF-map consumer? | LOE status in v0.4.2 |
> |---|---|---|---|
> | LI-01 | FCBI | yes (RF/weight) | **MODIFIED** — kernel exclusion + explicit burn/recovery/denominator guard |
> | LI-04 | PCI | yes (path set) | **MODIFIED** — `_build_kernel` drops paths with no discrete-work member |
> | LI-07 | CDI | yes (RF map) | **MODIFIED** — inherits kernel exclusion; retrospective-completed documented |
> | LI-05 | RDI | reads `k.rf` after its own guard | already excluded LOE (unchanged); disclosures added |
> | LI-09 | BWI | reads `k.rf` after its own guard | already excluded LOE (unchanged); UID target + disclosures added |
> | LI-10 | MML | no (resource productivity) | already excluded LOE at its own loop |
> | N17 DDI | provocative | consumes RDI/BWI/FCBI + own loop | already guards LOE (`is_loe_or_summary`) |
> | LI-06 | BDI | **no** (uses `driving_path`, tool-of-record) | immune from the kernel issue* |
> | LI-08 | IL | **no** (reads raw `total_float`) | immune from the kernel issue* |
> | LI-02 | LHL | no (relationship survival) | immune |
> | LI-03 | FRB | no (forecast error) | immune |
> | N16/18/19/20 | SMI/ARR/PPS/RSA | consume check findings / certificate / pacing | inherit fixed outputs |
>
> *Future consideration (flagged, NOT implemented per the ruling): BDI counts
> LOE steps that appear on the tool-of-record driving path, and IL would count
> an LOE turning negative-float as an emergence chain — both read paths/floats
> outside the shared kernel, so they are untouched here and warrant a separate
> methodology ruling if desired. A residual PCI note: a KEPT (mixed) path's
> `rel_float` is still computed by `float_paths` over all its members, so an
> LOE that is the single lowest-float member of a real path could still
> influence that path's weight; fully neutralizing it would require changing
> `float_paths` (shared with the driving-path analytics) — out of scope.*
>
> The sections below are retained as the as-audited (pre-0.4.2) record.

**Original status (pre-implementation):** AUDIT ONLY — no code or spec changed.

## Finding categories (same taxonomy as the FCBI audit; kept distinct)

- **Implementation defect** — code violates its own spec, or a wrong/unsafe result.
- **Specification gap** — reasonable but undocumented in §9.5/§10.2/§10.4 / matrix.
- **Methodology decision** — a substantive modelling choice (changes numbers) that
  is legitimate but must be *ruled on and recorded*.
- **Disclosure / reproducibility issue** — correct given its own definition, but a
  reader/re-runner could be surprised unless stated.

Severity is the *operational consequence*, independent of category (an
undocumented methodology choice can still be HIGH).

**Scope / evidence.** All findings reproduced with live probes driving
`run_li_indices()` on hand-built series. Code read in full: `_rdi` (L508-563),
`_demonstrated_series` (L412-441), `_bwi` (L594-670), `_resolve_bwi_target`
(L569-584), `_cdi` (L365-406), plus the shared kernel (L48-114). Existing tests
(`tests/test_li_indices.py`): `test_cdi_shares_sum_to_one`,
`test_rdi_nonnegative_one_row_per_update`, `test_bwi_first_update_is_baseline`,
`test_bwi_projected_break_date` — none of the areas below is covered.

**Downstream coupling.** RDI (LI-05, weight 2) and BWI (LI-09, weight 2) are
**scored Report Card members** with anchors (scorecard.yaml L371-372/L360-361,
L465/L488) — findings that move their numbers have grade blast radius. CDI
(LI-07) is **not scored** (leaderboard-only), so its finding has no grade impact.

---

## Current-behavior spec table

| # | Metric | Area | Current behavior | Category | Severity |
|---|---|---|---|---|---|
| C1 | CDI | LOE/summary in the dwell allocation | **Included.** LOE/WBS-summary/hammock activities earn CDI dwell if RF ≤ band; RDI and BWI exclude them (`is_loe_or_summary`). | Implementation defect / cross-index inconsistency | **High** |
| B1 | BWI | Normalization horizon | Density denominator = working days to **each update's current forecast finish** of the milestone, not a fixed reference date; a *slipping* milestone dilutes the bow-wave signal (the exact case BWI exists to catch). | **Methodology decision** (moves numbers; scored) | **High** |
| R1 | RDI | "Demonstrated pace" duration basis | Uses the **original (planned) duration** of completed near-critical activities, not actual elapsed; §9.5 says "best pace *actually demonstrated*". | Spec gap / methodology clarification (scored) | Medium |
| R2 | RDI | Demonstrated statistic | Compares required only against the running **max** demonstrated; §9.5 says "P50 **and** max". | Spec gap (scored) | Low-Med |
| C2 | CDI | Completed-activity retention undocumented at home | CDI correctly retains completed activities (retrospective dwell) but the rationale lives only in FCBI §9.1, not §10.2 / LI-07. | Disclosure | Low-Med |
| R3 | RDI | Mixed temporal sampling in accrual | Accrual compares required at window **start** (r_prev) against max demonstrated through window **end**. | Disclosure | Low |
| B2 | BWI | Target resolution from first update | Target resolved from `scheds[0]`; a re-coded/renamed milestone → density None in later updates. | Disclosure / reproducibility | Low |
| X1 | all | Representation exposure | RDI/BWI sum `remaining_duration_hours/hpd`; RDI needs `finish_date`. Missing/zeroed remaining, or absent finish_date, silently under-states the pace/None. | Disclosure / reproducibility | Low-Med |

---

## C1 — CDI counts LOE/summary/hammock activities (HIGH) — CONFIRMED

**Implementation fact.** `_cdi` (L376-377) builds the near-critical set as
`{code: weight for code, rf in k.rf.items() if rf <= band_days and code in k.weight}`
with **no `is_loe_or_summary` guard**. RDI (L522) and BWI (L616) both start their
loops with `if a.is_loe_or_summary or a.completed: continue`. So a Level-of-Effort
or WBS-summary activity that carries a low RF earns CDI dwell.

**Probe.** A 2-update series with a real task `T1`, a finish milestone `MS`, and a
Level-of-Effort `LOE1` (all RF ≤ band) → CDI leaderboard = `{LOE1, T1, MS}`.
`LOE1` is on the "cast of characters."

**Why it matters.** LOE/hammock activities span other work by construction and
routinely sit at or near zero float; they are not real work and carry no genuine
"criticality-time." Including them (a) dilutes every real activity's dwell share
and (b) can put a hammock at the *top* of the leaderboard — precisely the
"cast of characters" the metric is meant to surface. This is both a correctness
issue and a cross-index inconsistency (RDI/BWI already exclude them).

**Category / severity.** Implementation defect + cross-index inconsistency; HIGH
for the metric's forensic purpose (though not scored, so no grade impact).

**Note — this also implicates FCBI.** FCBI (LI-01) likewise has no
`is_loe_or_summary` guard (it consumes `float_deltas`, which include LOE). So the
family splits **FCBI + CDI (include LOE)** vs **RDI + BWI (exclude LOE)** — see X1.
Closing C1 should be done together with the FCBI LOE decision as a follow-up to
the LI-01 work, since the FCBI audit did not cover LOE.

**Recommendation.** Exclude `is_loe_or_summary` from CDI (and decide FCBI in the
same ruling) so the whole family treats LOE consistently. Real work only.

---

## B1 — BWI normalizes by the moving forecast finish, not a fixed date (HIGH) — CONFIRMED

**Implementation fact.** `_bwi` (L604-625) computes, per update, `wd =
working_days(data_date, tgt.finish)` where `tgt` is the milestone **in that update**
— i.e. its *current forecast finish*. Density = near-critical remaining days ahead
of it ÷ `wd`, normalized to update 0. The spec §10.4 frames BWI for a milestone
"with a **stationary** (often constrained or promised) date."

**Probe.** Milestone `MS` slips 2025-06-01 → 2025-09-01 across the pair while the
near-critical remaining work is unchanged (one 80h activity). Result: density
0.0926 → 0.0667, **BWI 1.0 → 0.72**. Work was neither added nor retired and the
date got *worse*, yet BWI reads as if the bow wave *relaxed* — because the later
window simply has more working days to a later target.

**Why it matters.** BWI's entire thesis is "the date holds while work packs." When
the date does hold, current == fixed and the metric is fine. When it slips — a
common and *aggravating* condition — using the moving forecast in the denominator
**understates** compression, exactly backwards. A held-date guardrail in the spec
is not enforced in the code.

**Category / severity.** Methodology decision (it changes numbers whenever the
milestone moves) — HIGH, and **scored** (LI-09, weight 2), so it has grade blast
radius. Options: (A recommend) normalize every update against a **fixed reference
horizon** — the milestone's baseline/first-update/constrained (promised) date — so
"working days to target" is constant and the ratio isolates the numerator
(remaining near-critical work); (B) report BWI only alongside the milestone-date
movement so a reader cannot misread a slip as relief; (C) keep as-is but rename to
disclose it is density-vs-current-forecast, not vs a held date. Recommend A, using
the constrained/baseline date when present, else the first-update forecast, with
the choice disclosed.

---

## R1 — RDI "demonstrated pace" uses planned, not actual, duration (Medium) — CONFIRMED

**Implementation fact.** `_demonstrated_series` (L428-439): for each completed
near-critical activity finishing in the window, `done += a.duration_days(...)`
where `duration_days = original_duration_hours / hpd` — the **original (planned)**
duration. Demonstrated pace = Σ planned-days of completed near-critical work ÷
window working days. Actual elapsed span (actual_finish − actual_start) is not used.

**Probe.** An activity with original duration 10 workdays but an actual span of
~40 calendar days completes in a 61-working-day window → demonstrated pace =
10/61 = 0.1639. The planned 10d, not the actual elapsed, is the numerator.

**Two readings (this is why it is a clarification, not a flat defect).**
- *Defensible:* required and demonstrated are then both in "planned scope retired
  per day" units — required = planned scope remaining ÷ time remaining;
  demonstrated = planned scope retired ÷ time elapsed. Dimensionally consistent.
- *Concerning:* §9.5 says "best pace **actually demonstrated**," which reads as an
  empirical throughput. An activity that overran badly still contributes its full
  *planned* duration in its completion window, so demonstrated pace is insensitive
  to overrun — it can **over-state** achievement and thereby **under-state** RDI
  (recovery debt), weakening the very unrealism case RDI supports.

**Category / severity.** Spec gap / methodology clarification; Medium (scored). Rule
whether demonstrated should measure planned-scope-retired (keep, and reword §9.5)
or actual-throughput (switch to actual elapsed); either way state it explicitly.

---

## R2 — RDI compares against `max` only, spec says "P50 and max" (Low-Med) — code-confirmed

`_rdi` accrues `max(0, r_prev − max_demo) × win_wd` with `max_demo` = running max of
the demonstrated series (L534, L541). §9.5: "compare against the best pace actually
demonstrated over trailing windows (**P50 and max**)." No P50 is computed. Using
max only is the *most conservative* choice (debt accrues only when required exceeds
the single best window ever), so RDI **under-accrues** relative to a P50 anchor.
Category: spec gap. Rule whether to add the P50 comparator (and how to combine) or
amend §9.5 to "max demonstrated."

---

## C2 — CDI's completed-retention rationale is undocumented at CDI (Low-Med)

CDI correctly *keeps* completed activities (retrospective criticality dwell) — this
is the intended half of the FCBI cross-index split. But the rationale is documented
only in FCBI §9.1; §10.2 and the LI-07 matrix row do not state it. A reader of CDI
alone cannot tell the inclusion is deliberate. Disclosure gap; add one sentence to
§10.2 / LI-07.

---

## Lower-severity items

- **R3 (Low).** RDI accrual mixes temporal sampling: required at window *start*
  (`required[i]`) vs demonstrated through window *end* (`demonstrated[i]` folded into
  `max_demo`). Defensible but undocumented — the analogue of FCBI item 3. Disclose.
- **B2 (Low).** BWI resolves the target from `scheds[0]`; a milestone re-coded or
  renamed in a later update yields density None there (silently drops that update).
  Reproducibility note.
- **X1 (Low-Med, representation).** RDI required and BWI density sum
  `remaining_duration_hours/hpd`; RDI required also needs `Schedule.finish_date`. An
  exporter that leaves remaining duration unmaintained (0) on incomplete
  near-critical work, or omits the project finish, silently understates the pace or
  returns None. Same representation-invariance concern the FCBI audit raised; worth a
  disclosure and, ideally, a data-completeness note in the output.

---

## Cross-index summary

- **X1 — LOE/summary handling is inconsistent across the family.** FCBI + CDI
  **include** LOE/summary; RDI + BWI **exclude** them. Unify consciously (recommend:
  exclude everywhere — LOE/hammocks are not real work) in one ruling that spans C1
  and a follow-up FCBI patch.
- **Completed handling is now consistent** post-v0.4.1: FCBI/RDI/BWI exclude
  completed (live-work), CDI retains (retrospective). No action beyond C2's
  documentation.
- **Guards are sound.** RDI (wd ≤ 0 → None; all-None → reason), BWI (base None/0 →
  reason), CDI (wsum ≤ 0 → skip; allocated 0 → reason) — no divide-by-zero found.
  RDI's cumulative is genuinely additive (unlike FCBI) — good.

---

## Proposed tests (lock behavior once ruled)

- **C1** — an LOE with RF ≤ band is *excluded* from the CDI leaderboard (and, if the
  FCBI follow-up is taken, from FCBI burn); a real activity with the same RF is
  included.
- **B1** — a milestone that slips with unchanged remaining work yields BWI == 1.0
  (or the ruled behavior) under a fixed reference horizon, not < 1.0.
- **R1** — a completed activity whose actual span ≫ its original duration produces a
  demonstrated pace equal to the *ruled* basis (planned or actual), asserted exactly.
- **R2** — a series where required exceeds the P50 but not the max demonstrated: RDI
  accrues iff the ruled comparator is P50.
- **X1** — near-critical incomplete work with remaining_duration = 0, or a missing
  finish_date, is surfaced (data-completeness disclosure), not silently zeroed.

## Minimum governance package (for the number-changing rulings C1, B1, and R1 if it switches to actual)

impl + matrix wording (LI-05/07/09) + §9.5/§10.2/§10.4 wording + seeded in-memory
fixtures + regression tests, together; regenerate METRIC_MATRIX.md; CHANGELOG note.
B1 and R1 move **scored** members (LI-09/LI-05) — the anchor recalibration caveat
from the FCBI work applies (the anchors were tuned to current magnitudes; recalibration
against real files stays the open L3 task; scorecard tests pin letter grades, not
absolute FCBI/RDI/BWI values, so verify the letters hold or update them with the change).

## Recommended ruling priority
1. **C1** (CDI LOE) — correctness; decide jointly with the FCBI LOE follow-up (X1).
2. **B1** (BWI moving horizon) — changes a scored number and inverts the signal on a
   slipping date; highest forensic stakes.
3. **R1** (RDI demonstrated basis) — rule planned vs actual and reword §9.5.
4. **R2 / C2 / R3 / B2 / X1** — disclosure/spec-alignment; adopt wording + the
   data-completeness note once the above are settled.
