# Per-metric LOE / duration-basis analysis (R-LOE, incl. LHL-L5) — 2026-07-14

**Planner:** Claude · **For:** the principal's ruling.

Purpose (per the R-LOE ruling): the criticality-based LOE/summary exclusion that
the kernel family adopted does **not** automatically transfer to metrics that
measure something other than criticality, so this analyzes each metric on its
own terms and recommends. Duration-basis questions (BDI-B5, MML) are folded in.
**LHL-L5 is resolved here.**

> **Cross-check:** the `li-metrics-audit-matrix` lineage independently reached —
> and shipped — an *exclude* decision for LHL/IL/BDI and basis rulings for
> BDI/MML (see `branch_reconciliation_2026-07-14.md`). My reasoning below was
> derived independently and converges with theirs, which both corroborates the
> recommendation and reinforces that the branch-canonical decision must be
> settled first (we may be re-deriving decisions that already exist).

## Framework
For each metric ask: (1) what does the metric measure? (2) is an LOE/summary
row's contribution *signal* or *artifact* for that specific measurement?
(3) which direction does including it bias the score, and is that misleading?

## LHL (LI-02) — logic stability — **resolves L5**
- **Measures:** stability of the logic network (Kaplan-Meier survival of ties).
- **LOE ties:** hammock/WBS-summary/LOE start-finish ties are largely
  *auto-generated* and re-point mechanically when their bounding activities move
  — churn without a replanning decision.
- **Bias:** including them biases the half-life **down** (reads as *less* stable)
  for non-decisions — the adverse direction for a forensic stability metric.
- **Steelman keep:** a genuine LOE deliberately re-sequenced is real churn — but
  rare relative to mechanical hammock movement.
- **Recommendation: EXCLUDE** `is_loe_or_summary` from the LHL survival
  population, with a standing disclosure. **(L5 = exclude.)**

## IL (LI-08) — intervention latency
- **Measures:** delay from a chain entering negative float to the first
  responsive edit.
- **LOE in the emergence set:** an LOE has no real duration/logic to
  "intervene" on (you cannot compress a level-of-effort bar); its negative float
  is derivative of its span slipping. Emitting it as an event inflates counts
  with non-actionable emergences.
- **Recommendation: EXCLUDE** LOE/summary from the emergence population.
- **Adjacent (I5 connectivity, not LOE):** the induced-negative-subgraph rule
  splits `A→B→C` into two events when `B` holds positive float. Recommend a
  **connected-chain traversal through non-negative intermediates** so one real
  chain is one event. (Methodology call; flagged, not bundled with the LOE
  ruling.)

## BDI (LI-06) — baseline dilution — **LOE + basis (B5)**
- **Measures:** what fraction of the *current* driving path (by length) is
  post-baseline.
- **LOE steps on the path:** an LOE's "length" is ill-defined (level of effort);
  counting it in the denominator distorts the ratio.
  **Recommendation: LOE steps contribute ZERO length** (neither denominator nor
  post-baseline numerator).
- **Duration basis (B5):** current mixed basis is remaining-when-positive-else-
  original, so an in-progress activity shrinks and a completed one keeps full
  length — inconsistent. For "composition of the path by scope-origin," the
  stable, interpretable basis is **original duration** for every step.
  **Recommendation: fixed original-duration basis.**
- **Baseline provenance:** `schedules[0]` is silently treated as the contractual
  baseline. **Recommendation: require an explicit baseline (param/flag); if only
  positional-first is available, emit a provenance disclosure.**

## MML (LI-10) — measured mile / productivity
- **Measures:** productivity (work per time) per WBS and its disruption contrast.
- **LOE:** a level-of-effort row has no discrete productivity — its "completion"
  is not a work rate. **Recommendation: EXCLUDE** LOE/summary from productivity
  windows.
- **Duration basis (activity-day fallback):** currently original duration for
  newly-completed work. This is the same planned-vs-actual choice settled for
  **RDI (R1)**: for a work-per-time rate, the *scope* numerator is planned
  (original) duration; elapsed time is the window. **Recommendation: original
  (planned-scope) numerator, consistent with R1.** (Distinct from M1's
  resource-vs-activity-day cross-basis defect, which needs a common-basis rule.)

## Summary of recommendations (for ruling)
| Metric | LOE/summary | Duration basis |
|---|---|---|
| LHL (L5) | **Exclude** from population | n/a (survival in update counts) |
| IL | **Exclude** from emergence set | n/a |
| BDI | **Zero-length** on the path | **Original duration**; explicit baseline provenance |
| MML | **Exclude** from productivity | **Original (planned) scope**, per R1 |

All are number-changing on affected schedules → full quartet + grade re-check per
scored metric (LI-02 LHL, LI-08 IL, LI-06 BDI; LI-10 MML not scored — evidence
re-check). **Where we adopt the matrix lineage (if Option A), verify whether its
Q-F/Q-G/IL4a implementations already match these and simply concord the rulings
rather than re-implement.**
