# LI-family audit — recorded rulings & implementation plan (2026-07-14)

**Principal:** worktodo77 · **Planner/reviewer:** Claude · **Implementer:** Codex
**Canonical branch:** `claude/scheduleiq-v0.3-engine-port-rx96cl` (v0.4.5, tip
`e14562b` at ruling time).

This doc records the principal's rulings on the BDI/IL/MML/SMI audits
(`docs/audit/*_2026-07-14.md`, all findings independently reproduced by the
reviewer) plus the cross-cutting family decisions, and lays out the
implementation plan Codex builds against. Bespoke LI metric definitions are
methodology decisions owned by the principal; every number-changing item ships
with the full governance quartet (matrix row + implementation + seeded fixture +
tests), a CHANGELOG note, and a pinned-demo grade re-check.

## Recorded rulings

| # | Decision | Ruling |
|---|---|---|
| R-ID | Code-vs-UID identity (BDI-B2, IL-I3, MML-M2; also LHL-L3/BWI-B2 done; FRB pending) | **Family-wide UID-first identity ruling.** Fix both layers together. |
| R-LOE | LOE/summary inclusion + duration basis (IL-I5, BDI-B5, MML, LHL-L5) | **Planner drafts a per-metric analysis first**, then principal rules. LHL-L5 folds into it. |
| R-FORK | Divergent branches (kernel-v2 / FCBI-v0.5 / LHL-split) | **Salvage good ideas, then retire.** Reconciliation plan first. |
| R-MIR | Expert-assist mirror | **Retired; migration confirmed.** (HANDOFF §2 updated.) |
| R-FRB | FRB (LI-03) un-audited | **Full FRB audit next** (Codex authors, Claude reviews). |
| R-I2 | IL mixed unresolved events | **Unresolved chains penalize the LI-08 grade** (worked effect to be shown before finalizing). |
| R-B1I1 | BDI-B1, IL-I1 | **Confirmed:** BDI-B1 zero-denominator -> N/A; IL-I1 same-pair response = 0 updates. |

## Family Ruling R-ID — UID-first identity (SPEC for implementation)

**Ruling:** activity and relationship identity across updates is keyed by
persistent **UID**, not analyst-facing code. Code/name are retained for display
only. A true UID *replacement* (genuinely new activity reusing a slot) is a new
post-baseline activity; a pure re-code (UID stable, code changed) is NOT a
change of any kind.

**Two fix layers — change together:**

1. **Shared change register** — `compare/diff.py` matches activities by `code`
   (~L90-97) and records relationship/duration deltas on that basis. This is
   upstream of IL (and any future register consumer). Re-key activity matching
   to UID (fall back to code only when a UID is absent in a legacy export),
   preserving code for display in the emitted change records.
2. **Per-metric code-keyed lookups** —
   - BDI (`li_record.py` ~L531-551): `base_codes = {a.code}`, `base_edges` by
     `(pred.code, succ.code, type)`, `step.code in base_codes` -> key by UID.
   - IL (`li_record.py` ~L669-711): earlier/later maps and resource resolution
     by code -> UID; note IL also inherits the register fix (layer 1).
   - MML (`li_record.py` ~L861-876): `e_by_code = {a.code: a}` -> UID.
   - FRB: audit pending (R-FRB); apply the same rule when audited.
   - LHL (`li_record.py`) and BWI already UID-keyed (L3 / B2) — leave, and cite
     as the pattern.

**Precedent in the codebase:** `Relationship.key()` already returns
`(pred_uid, succ_uid, rtype)`; `Activity.uid` is the stable identity.

**Fixtures/tests (per metric):** a UID-stable re-code registers NO death /
dilution / lost production and stays baseline-original; a genuine type/logic
change still registers. For IL, add the on-register test (re-code preserves the
emergence and the response).

**Governance:** number-changing on re-coded histories -> full quartet + grade
re-check for each scored metric touched (LI-06 BDI, LI-08 IL; LI-10 MML not
scored but re-check its evidence surface; LI-03 FRB when audited).

## Confirmed scored HIGH defects (R-B1I1)

- **BDI-B1** — a zero-length (all-milestone) driving path currently returns
  `bdi_pct = 0.0`, which LI-06 maps to **100** (verified: reviewer probe scored
  100.0). Ruling: return **N/A / undefined** (not 0) for a zero denominator and
  surface the reason; do not award the 100-point zero-width curve. Add an
  all-milestone fixture; pin the scorecard behavior (N/A, not 100). Quartet +
  grade re-check.
- **IL-I1** — the response scan starts at `i+1`, so a response in the emergence
  pair is invisible and the smallest observable latency is 1, making the LI-08
  curve's 0-update/100 anchor unreachable (verified). Ruling: a **same-pair
  response counts as 0 updates** (consistent with the published curve). Add a
  same-pair fixture; pin both 0 and 1. Quartet + grade re-check.

## IL-I2 — unresolved chains penalize the grade (R-I2)

**Ruling direction:** a chain that emerges into negative float and *never*
receives a response is a "failed-to-mitigate" signal and must affect LI-08, not
be silently dropped (today `_li08_score` scores on the resolved-only median as
soon as it is non-None; the fixed 20-point branch fires only when *all* events
are unresolved). **Before finalizing, the planner will show the worked scoring
effect** of the candidate treatments (e.g. treat unresolved as worst-case
latency in the median, vs. a penalty/cap proportional to `unresolved_count /
total_events`) so the principal picks the exact mechanism. Then quartet + grade
re-check. (Mixed-event fixture required.)

## Queued planner deliverables (Claude) and their consumers (Codex)

1. **R-ID family-identity fix plan** — this doc's spec section; ready for Codex
   to implement as the first governed batch (v0.4.6 candidate), sequenced FIRST
   because it unblocks the most findings.
2. **Per-metric LOE/basis analysis (R-LOE, incl. LHL-L5)** — dedicated analysis
   doc: for each of LHL / IL / BDI / MML, whether the criticality-based
   LOE-exclusion rationale transfers, and the duration-basis convention; ends
   with a per-metric recommendation for the principal to rule.
3. **Branch reconciliation plan (R-FORK)** — map what kernel-v2 / FCBI-v0.5 /
   LHL-split changed vs v0.4.5; recommend salvage vs abandon per idea; then the
   forks are retired.
4. **FRB audit (R-FRB)** — Codex authors (same template), Claude reviews;
   applies R-ID.
5. **IL-I2 worked-effect memo** — feeds the final I2 mechanism ruling.

## Remaining metric-specific rulings still open (to batch after the above)

BDI-B3 (lag identity), BDI-B4 (target selection); IL-I4 (response taxonomy:
deleted logic, remaining-duration compression); MML-M1 (cross-basis ratio, HIGH
but not scored), M3 (dispersion/sustained selection), M4 (event wiring), M5
(reporting contract); SMI-S1..S5 (event plumbing, timing scope, missing-input
NOT-COMPUTABLE, DUR-03 scope, evidence cap — all weight-0/privileged).
