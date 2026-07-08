# FCBI (LI-01) implementation audit — peer-review response

**Date:** 2026-07-08 · **Auditor:** Claude (lead) · **Status:** AUDIT ONLY —
findings and current-behavior spec; no code or spec changed. RJL to make the
methodology rulings; a proposed test list follows each finding.

**Scope reviewed**

| Artifact | Location |
|---|---|
| FCBI metric | `src/scheduleiq/analytics/li_indices.py` — `_fcbi()` (L241-319), kernel L48-114 |
| Float deltas (input) | `src/scheduleiq/compare/diff.py` — `compare()` L145-150 |
| RF / float-path module | `src/scheduleiq/analytics/paths.py` — `float_paths()` L380-441, `_walk()` L258-302 |
| RF map | `li_indices.py` — `relative_float_map()` L64-90, `_build_kernel()` L110-114 |
| Matrix entry | `src/scheduleiq/metrics/matrix.yaml` — LI-01 L928-940 |
| Spec | `docs/ANALYTICS_PROPOSAL.md` §9.1 L412-426 |
| Tests | `tests/test_li_indices.py` L52-106 (3 FCBI tests) |

All findings below were reproduced with live probes driving `compare()` +
`run_li_indices()` on hand-built two/three-update series. Existing suite
(`tests/test_li_indices.py`) is green (10 passed) but covers none of the five
areas (see coverage table at the end).

---

## Current-behavior spec table (for rulings)

| # | Area | Current behavior | Documented? | Tested? | Severity |
|---|---|---|---|---|---|
| 1 | Completed activity | **Data-dependent.** No completion filter. Burn = `max(0, -ΔTF)·w`. If tool-of-record writes **TF=0** for a completed activity → full prior float scored as **phantom burn**. If it writes **TF=null** → activity silently excluded (delta not populated). | No | No | **High** |
| 2 | FCBI% denominator | Guarded: `pct = 100·burn/denom if denom>0 else None`. No div-zero. But normalized form goes **None** exactly in the at/past-driving-path regime; absolute FCBI+ is still reported (and amplified by negative-RF weights). | Partly (matrix says ">100% = beyond available float"; None case undocumented) | No | Medium |
| 3 | Weight timing | Weight sampled at the **earlier** file (u-1, start of window): `ek = kernels[id(earlier)]`. RF frozen at window start. | No | No (not isolated) | Medium |
| 4 | RF provenance | RF = **path-level** min relative float over the **top-10** float paths containing the activity; driving path = **min-float** (not longest-path CPM); fallback to activity's **own** TF when on no enumerated path; negative RF allowed (weight >1). Reads tool-of-record stored floats — **independent of `scheduleiq.cpm` statusing mode**. | Partly (matrix formula names "min relative float of containing float paths"; fallbacks/truncation/tie behavior undocumented) | No | Medium |
| 5 | Windowing | Strictly consecutive update pairs; `cumulative` is a running sum over those pairs. **Not** re-windowing invariant (`max(0,-ΔTF)` is not additive across concatenation). No rollup code recomputes over coarser windows. | No (no invariance claimed, but non-additivity not warned) | No | Low-Med |

---

## 1. Completed-activity handling (highest priority)

**(a) Code path.** `compare()` (diff.py L145-150) populates
`cs.float_deltas[code]` for **every** activity whose `total_float_hours` is
non-null in *both* files — there is no `completed`/status guard. `_fcbi()`
(li_indices.py L259-284) iterates those deltas, looks up the weight from the
earlier kernel, and for `delta < 0` adds `(-delta)·w` to burn. Completed
activities are neither excluded nor float-frozen; their TF is taken at face
value from each file.

**(b) Documented?** No. §9.1 and the matrix entry say "for each activity in
both updates" without addressing completion.

**(c) Tested?** No.

**(d) Probe — an activity that burns 15d then completes in the window.**
Earlier: A has TF=120h (15d). Later: A `COMPLETED`.

| Later-file completed TF | FCBI+ registered | Burner |
|---|---|---|
| `TF = 0` (some P6/XER exports) | **15.000** | A, consumption 15.0d, weight 1.0 |
| `TF = null` (typical P6 export) | 0.000 | — (A excluded) |

So an activity that finished **on schedule** is scored as having burned its
entire remaining float, purely because the tool-of-record wrote a hard zero
on completion. The result is **not reproducible across exporters** — the same
project scores differently depending on whether the scheduling tool nulls or
zeroes completed float. Our own XER parser stores whatever the file carries
(`xer.py` L272, raw `total_float_hr_cnt`), so both regimes occur in practice.

**Options / recommendation.**
- **A (recommend): freeze at completion.** When `later.completed`, drop the
  activity from the burn/recovery sums (its float history ended; any u→u
  change is a reporting artifact, not consumption). Cleanest and defensible;
  matches the "float story of in-flight work" intent.
- **B: net completion to the value at last-incomplete update.** More faithful
  to "float actually consumed while the activity was live," but needs the
  activity's TF from the update where it was last incomplete — more state.
- **C: keep as-is but normalize exporter behavior** (treat completed TF as
  null regardless of stored value). Removes the phantom burn but discards any
  genuine last-window consumption.
Recommend **A**, with the ruling recorded in §9.1 and the matrix formula.

**Proposed tests.** (1) completed-with-TF=0 → zero burn from that activity;
(2) completed-with-TF=null → unchanged (already zero); (3) an activity that
legitimately burns while *incomplete* then completes next window → burn
counted in the incomplete window only.

---

## 2. FCBI% denominator guard

**(a) Code.** li_indices.py L286-294: `denom = Σ tf·w` over earlier activities
with `tf > 0`; `pct = 100·burn/denom if denom > 0 else None`.

**(b) Documented?** Partly — the matrix notes ">100% means erosion beyond
available float." The **None** outcome (stock ≤ 0) is undocumented.

**(c) Tested?** No (the one exact test has a positive stock).

**(d) Probe — all-negative-float network.** Two activities, both negative
float in the earlier file, both driven further negative. Result:
`FCBI+ = 40.000`, `fcbi_pct = None`. No divide-by-zero, no overflow. Note the
burn is **amplified**: on a path with RF = −10d the kernel weight is
`2^(10/5) = 4.0`, so 5d of further-negative movement on each activity yields
40 weighted units. That is correct-by-design (over-critical work must not be
under-counted) but means the **normalized** reading is unavailable precisely
when the schedule is most distressed — a reader who keys on FCBI% (not FCBI+)
sees a blank exactly at the worst moment.

**Options / recommendation.** Keep the guard (safe). **Recommendation:** when
`denom ≤ 0`, emit an explicit sentinel/label ("criticality-weighted float
stock exhausted — normalized burn undefined; see absolute FCBI+") rather than
a bare `None`, and surface FCBI+ prominently in that regime. Consider whether
the stock should include |negative-float| capacity; that is a methodology
ruling, not a bug.

**Proposed tests.** (1) all-negative stock → `fcbi_pct is None`, `fcbi > 0`,
no exception; (2) mixed stock with one positive-TF activity → finite pct;
(3) empty deltas → `reason` set, pct None.

---

## 3. Weight timing

**(a) Code.** `_fcbi()` L254: `ek = kernels[id(earlier)]`; all weights come
from `ek.weight`. Kernels are built per schedule in `run_li_indices()` L640.
Weight (hence RF) is therefore sampled at the **start of the window (u-1)**.

**(b) Documented?** No — neither §9.1 nor the matrix states start-vs-end.

**(c) Tested?** Not isolated. The exact 2-update test uses no logic, so RF =
own float and the earlier value is used, but it does not *contrast* earlier vs
later, so it would not catch a switch to end-of-window sampling.

**(d) Probe — A goes RF=20 → RF=0 while burning 20d** (path built so A is the
path's min-float member, isolating the timing):
- earlier kernel RF(A)=20 → weight `2^(-20/5)=0.0625` → contribution **1.25**
- later kernel RF(A)=0 → weight 1.0 → contribution would be 20
- **Observed contribution = 1.25, weight = 0.0625 → confirmed earlier (u-1).**

**Consequence to rule on.** Start-of-window weighting means float burned on a
chain that was *not yet* near-critical at u-1 is weighted **low**, even if the
same burn is exactly what *made* it critical by u. An activity racing from 20d
to 0d float contributes 1.25, not 20. Alternatives: end-of-window (u) weight
(rewards "became critical"), or **min(RF_{u-1}, RF_u)** (counts a chain that
was critical at either end — arguably the most defensible for a burn index).
**Recommendation:** rule explicitly; my lean is `min` over the window, but
this is a genuine methodology choice, not a defect. Whatever is chosen must be
stated in §9.1 and the matrix formula.

**Proposed tests.** The probe above as a fixed assertion under whichever rule
is adopted; plus the symmetric case (RF 0→20 with burn) to pin the semantics.

---

## 4. RF provenance

**(a) How RF is computed.**
- `_build_kernel()` → `float_paths(schedule, n=KERNEL_PATHS_N=10,
  band_days=None)`: enumerate the **top-10** distinct paths to the resolved
  target, ranked by path relative float. Path 1 is the least-float chain from
  `_walk()`; each subsequent path is the least-float feeder spliced onto an
  existing path's tail (feeder activities then removed from the walkable set).
- **Driving-path identification:** `_walk()` (L258-302) chooses the
  predecessor with **minimum total float first**; ties within
  `FLOAT_TIE_BAND_DAYS = 0.1` d are broken by date-satisfaction, then by code.
  This is **tool-of-record float**, *not* an internal longest-path/CPM pass
  (ADR-0004 spine) — so RF is **independent of `scheduleiq.cpm` and its
  retained-logic vs progress-override statusing**; those modes never touch it.
- **Path relative float** (`_finalize_path` L360-377): `rel_float_days =
  min TF over activities *unique* to this path` (else the path min).
- **RF(activity)** (`relative_float_map` L64-90): `min` over the paths
  containing it of those paths' `rel_float_days`; **fallback** to the
  activity's **own** total float when it is on no enumerated path; **omitted**
  (weight undefined → excluded from FCBI) when it has neither.
- **Negative float:** carried through; negative RF → weight > 1.
- **Multiple driving paths / ties:** `_walk` deterministically commits to one
  (min float, then satisfied, then code); co-driving paths are not all
  retained in path 1, though feeders recover many as later ranks.

**(b) Documented?** Partly. The matrix formula names "min relative float of
containing float paths." Undocumented: the top-10 truncation, the own-float
fallback, the omit-when-undefined rule, tie handling, and that an activity
**inherits the path minimum** rather than its own float.

**(c) Tested?** No dedicated RF-provenance test.

**(d) Truncation / edge behavior observed.**
- **Path-min inheritance.** Probe 1's A had 15d of its *own* float but, sharing
  a path with the zero-float target, took **RF=0 → weight 1.0**. An activity's
  weight is governed by the most-critical member of its path, not its own
  float. Correct per the "criticality of the float" intent, but it means own
  TF is often *not* what drives the weight — worth stating.
- **Tie/short-path fallback flip.** When both candidate finishes tie and the
  resolved target yields a <2-step walk, `float_paths()` returns `[]`; RF then
  falls back to **each activity's own TF** (observed: two activities scored
  RF=20 and RF=25 = their own floats, not a shared path min). So RF silently
  switches basis (path-relative ↔ own-float) depending on target resolution
  and enumeration success.
- **Top-10 truncation.** An activity reachable only on the 11th+ float path
  gets no path-derived RF and falls back to own TF; on wide networks this can
  understate near-criticality for deep alternates. `KERNEL_PATHS_N` is a fixed
  constant (L42), not surfaced in the matrix.

**Options / recommendation.** (i) Document the full RF definition (path-min,
fallbacks, truncation, ties) in §9.1 verbatim; (ii) consider raising or making
`KERNEL_PATHS_N` configurable and disclosing it in output; (iii) decide
whether the own-float fallback should use the activity's own TF or its
best-available path RF when enumeration is truncated. All are methodology/
disclosure rulings — no correctness bug, but the basis-switch (path vs own) is
a reproducibility footgun on tied targets.

**Proposed tests.** (1) activity on a zero-float path inherits RF=0; (2)
activity off all top-10 paths falls back to own TF; (3) tied-target →
own-float basis, asserted and disclosed; (4) negative-float path → weight >1.

---

## 5. Windowing convention

**(a) Code.** `_fcbi()` iterates `sa.changesets` (built as consecutive pairs
in `trend/series.py` L115). `cumulative` (L301-302) is a running sum of
per-window burns over those same pairs — additive **within** the chosen
windowing. No code recomputes FCBI over coarser/merged windows; there is no
rollup that would re-window.

**(b) Documented?** §9.1 speaks of "per window" and a "cumulative FCBI curve";
it does **not** claim re-windowing invariance (correctly), but neither does it
**warn** that the index is windowing-dependent.

**(c) Tested?** No.

**(d) Probe — TF 10 → 0 → 10.**
- per-window (u0→u1→u2): FCBI+ total = **10.000** (10 burned in window 1, 0 in
  window 2 since regain is recovery, not negative burn)
- endpoint-only (u0→u2): FCBI+ = **0.000** (net ΔTF = 0)
- **Invariance holds? No** — 10 vs 0, exactly the peer-review counterexample.

This is inherent to `max(0, -ΔTF)` (a total-variation-style measure) and is
arguably the *desired* property (burn-then-regain is real churn, not a
no-op). The risk is purely presentational: a reader must not compare an
FCBI+ computed on monthly updates against one computed on quarterly windows.

**Options / recommendation.** No code change needed. **Recommendation:** add a
one-line disclosure to §9.1 and to the FCBI output (`interpretation` string):
"FCBI+ is windowing-dependent and not additive across merged windows; compare
only like-for-like update cadences." Optionally record the update cadence /
window count in the result (already have `len(windows)`).

**Proposed tests.** (1) the 10→0→10 counterexample asserting per-window=10,
endpoint=0 (locks the intended non-additive semantics so a future "fix" that
nets them can't land silently); (2) monotonic `cumulative` under pure burn.

---

## Existing test coverage of the five areas

| Existing test | Covers |
|---|---|
| `test_kernel_weights_closed_form` | kernel formula only (0/5/10/−5 d) |
| `test_fcbi_burns_across_series` | burn>0, cumulative monotone, recovery≥0, ranked burners — on the demo series |
| `test_fcbi_exact_two_update_pair` | one hand-computed pair (no logic → RF=own float, positive stock, no completed activity) |

**Gaps:** items 1 (completed), 2 (zero/negative stock), 3 (weight timing
isolation), 4 (RF path-min, fallback, truncation, ties), 5 (windowing
non-additivity) are **entirely uncovered**. Proposed tests above, added under
the governance quartet (matrix note + §9.1 wording + fixture + test) once RJL
rules on items 1 and 3 (the two that change numbers).

## Recommended ruling priority
1. **Item 1** (changes numbers, reproducibility across exporters) — rule first.
2. **Item 3** (changes numbers, methodology substance) — rule next.
3. Items 2, 4, 5 — primarily disclosure/documentation; adopt the wording and
   tests once 1 and 3 are settled.
