# FCBI (LI-01) implementation audit — peer-review response

**Date:** 2026-07-08 · **Auditor:** Claude (lead) · **Rev 3** (2026-07-08,
Codex sign-off; strengthened the severity rationale for item 1) · **Rev 2**
incorporated Codex peer review — all five primary findings independently
confirmed; wording tightened, one cross-index issue added, item 4 softened.

> **RESOLVED in v0.4.1 (2026-07-08).** All rulings adopted and implemented with
> the governance quartet — item 1 (exclude completed from burn *and* recovery),
> item 3 (weight at min(RF(u-1), RF(u))), item 1b (completed-activity split
> documented; FCBI aligned with RDI/BWI, CDI retained as retrospective), and
> the disclosure items 2/4/5 (labelled FCBI% sentinel; standing disclosures;
> §9.1 + matrix wording).  Code: `analytics/li_indices.py::_fcbi`.  Tests: 7 new
> governance tests in `tests/test_li_indices.py` (+ the exact-pair test updated
> to the new convention).  See CHANGELOG 0.4.1.  The sections below are retained
> as the as-audited record of *pre-0.4.1* behavior and the rationale for each
> ruling.

The body below was written pre-implementation ("AUDIT ONLY — no code or spec
changed"); the methodology owner has since made the rulings and they are live.
A proposed test list and the minimum governance package follow — both now
implemented.

## Finding categories (kept distinct throughout — do not conflate)

- **Implementation defect** — the code does something other than what the spec
  says, or produces a mathematically wrong/unsafe result.
- **Specification gap** — the behavior is a reasonable choice but is
  undocumented in §9.1 / the matrix.
- **Methodology decision** — a substantive modelling choice (changes numbers)
  that is legitimate but must be *ruled on and recorded*, not assumed.
- **Disclosure / reproducibility issue** — the behavior is correct given its
  own definition, but a reader or a re-runner could be surprised unless it is
  stated (e.g. a fixed truncation constant, a basis that depends on inputs).

None of the five primary findings is an outright implementation *defect*; the
one behavior that yields a wrong-looking number (item 1) does so because of an
undocumented methodology choice interacting with exporter variance, not a
coding error. That distinction is carried below.

**"Not an implementation defect" is not "not serious."** Category (root cause)
and severity (operational consequence) are independent axes. An implementation
defect means the code violates its own specification; a specification gap with
severe operational consequences means the code behaves *consistently* but the
missing methodology rule causes materially different reported results.
**Item 1 is the latter, and it is rated HIGH on that basis:** although the root
cause is a missing rule rather than a coding error, the observable consequence
is that two identical projects can produce different FCBI values solely because
different scheduling tools/exporters represent completed-activity float
differently (`0` versus `null`). A bespoke index whose headline number depends
on the exporter, not the schedule, is operationally severe regardless of how it
is classified — hence HIGH, and hence the recommended first ruling.

**Scope reviewed**

| Artifact | Location |
|---|---|
| FCBI metric | `src/scheduleiq/analytics/li_indices.py` — `_fcbi()` (L241-319), kernel L48-114 |
| Sibling indices (cross-index check) | `_rdi()` L447-503, `_bwi()` L534-565, `_cdi()` L365-406, `_demonstrated_series()` L412-441 |
| Float deltas (input) | `src/scheduleiq/compare/diff.py` — `compare()` L145-150 |
| RF / float-path module | `src/scheduleiq/analytics/paths.py` — `float_paths()` L380-441, `_walk()` L258-302 |
| RF map | `li_indices.py` — `relative_float_map()` L64-90, `_build_kernel()` L110-114 |
| Matrix entry | `src/scheduleiq/metrics/matrix.yaml` — LI-01 L928-940 |
| Spec | `docs/ANALYTICS_PROPOSAL.md` §9.1 L412-426 |
| Tests | `tests/test_li_indices.py` L52-106 (3 FCBI tests) |

All findings were reproduced with live probes driving `compare()` +
`run_li_indices()` on hand-built two/three-update series. Existing suite is
green (10 passed) but covers none of the areas below.

---

## Current-behavior spec table (for rulings)

| # | Area | Current behavior | Category | Severity |
|---|---|---|---|---|
| 1 | Completed activity (burn **and** recovery) | No completion filter. Burn `max(0,-ΔTF)·w` and recovery `ΔTF·w` both include completed activities. If the tool-of-record writes **TF=0** on completion → full prior float scored as phantom burn; **TF=null** → silently excluded. | Spec gap + **methodology decision** (yields non-reproducible output) | **High** |
| 1b | Completed-activity handling is **inconsistent across LI indices** | FCBI (burn+recovery) and CDI include completed; RDI and BWI exclude completed. Verified in code. | Spec gap / methodology decision | Medium |
| 2 | FCBI% denominator | `pct = None` when weighted float stock ≤ 0. Mathematically safe; no div-zero/NaN/inf. Bare `None` is not communicative. | Spec gap | Low-Med |
| 3 | Weight timing | RF/weight sampled at the **earlier** file (u-1). This is an objective implementation fact; whether it is the *right* convention is a separate methodology question. | Spec gap + **methodology decision** | Medium |
| 4 | RF provenance | Path-level min RF over the **top-10** float paths; min-float driving path (not CPM); own-TF fallback off-path; omit when undefined; negative RF allowed; independent of `scheduleiq.cpm` statusing. | **Disclosure / reproducibility** | Low |
| 5 | Windowing | Consecutive pairs; `cumulative` is a running sum; no rollup recompute. Not re-windowing invariant, by construction. | Spec gap (disclosure) | Low-Med |

---

## 1. Completed-activity handling (highest priority) — CONFIRMED

**Implementation facts** (all verified in code):
- `compare()` (diff.py L145-150) creates `cs.float_deltas[code]` for **any**
  activity whose `total_float_hours` is non-null in *both* files — no
  `completed`/status guard.
- `_fcbi()` (li_indices.py L259-284) burns every negative delta using the
  **earlier** schedule's weight; there is no completion filter.
- **The recovery side has the same gap.** L264-266:
  ```python
  if delta > 0:                       # regained float, tracked separately
      recov += delta * w
  ```
  Completed activities feed `fcbi_recovery` just as they feed `fcbi` (burn).
  Any ruling that freezes/excludes completed activities on the burn side
  **must apply identically to recovery**, or the two halves of the index will
  disagree about which activities are in scope.
- `TF=None` excludes an activity only as a side effect: no delta is generated.
- The XER parser preserves the raw `total_float_hr_cnt` exactly as exported
  (`xer.py` L272).

**Category — spec gap + methodology decision; severity HIGH.** The gap
(undocumented in §9.1 / matrix) is compounded by a **methodology decision**
that has never been made: the index produces a *data-dependent,
non-reproducible* number — the same project scores differently depending only
on whether the source tool nulls or zeroes the float of a completed activity.
The code is doing exactly what it was written to do, so this is not an
implementation defect — but the operational consequence (a headline index that
moves with the exporter, not the schedule) is severe, which is why it is rated
HIGH and recommended as the first ruling. Root cause and severity are separate
axes (see the taxonomy note above).

**Probe — an activity that burns 15d then completes in the window.** Earlier:
A has TF=120h (15d). Later: A `COMPLETED`.

| Later-file completed TF | FCBI+ | Burner |
|---|---|---|
| `TF = 0` (some exporters) | **15.000** | A, consumption 15.0d, weight 1.0 |
| `TF = null` (typical P6) | 0.000 | — (A excluded) |

**Options / recommendation (methodology ruling).**
- **A (recommend): freeze/exclude at completion** — when `later.completed`,
  drop the activity from *both* burn and recovery. Cleanest, reproducible,
  matches the "float story of in-flight work" intent, and aligns FCBI with
  RDI/BWI (see 1b).
- **B: net to the last-incomplete value** — count only the float actually
  consumed while the activity was live; more faithful but requires carrying
  the activity's TF from the update where it was last incomplete.
- **C: normalize exporter behavior** — treat completed TF as null regardless
  of stored value; removes phantom burn but discards any genuine
  final-window consumption.

Recommend **A**, applied symmetrically to burn and recovery, recorded in §9.1
and the matrix formula.

---

## 1b. Completed-activity handling is inconsistent across LI indices — NEW (verified)

The completed-activity question is not isolated to FCBI; the five indices
sharing the criticality kernel disagree on it. Verified in code:

| Index | Completed-activity treatment | Evidence |
|---|---|---|
| **FCBI burn** | **included** (no filter) | li_indices.py L259-284 |
| **FCBI recovery** | **included** (no filter) | li_indices.py L264-266 |
| **RDI** (required-pace side) | **excluded** | L462 `if a.is_loe_or_summary or a.completed: continue` |
| **RDI** (demonstrated-pace side) | *only* completed (by design — it measures completed near-critical work) | L429 `if ... not a.completed: continue` |
| **BWI** | **excluded** | L556 `if a.is_loe_or_summary or a.completed: continue` |
| **CDI** | **included** (any RF-qualified code gets dwell) | L376-377 (no completion test) |

So FCBI and CDI count completed activities; RDI and BWI do not. This may be
deliberate — FCBI/CDI are *retrospective* (what happened to float / where did
criticality dwell, including on now-finished work), whereas RDI/BWI are
*forward* (remaining work vs remaining time, where completed work is
irrelevant by definition). If that is the intent, **state it** in §9.1/§9.5/
§10.4 and the matrix so the asymmetry is defensible rather than accidental. If
it is not intended, it becomes a governance decision to align them.

**Category.** Specification gap / methodology decision. **Recommendation:**
document the retrospective-vs-forward rationale for the split, and make the
FCBI ruling in item 1 consciously consistent with it (freezing FCBI's
completed activities would move FCBI *toward* the RDI/BWI convention and away
from CDI — a choice worth making explicitly).

---

## 2. FCBI% denominator — CONFIRMED

**Implementation fact.** li_indices.py L286-294: `denom = Σ tf·w` over earlier
activities with `tf > 0`; `pct = 100·burn/denom if denom > 0 else None`.
Verified: no divide-by-zero, no NaN, no overflow. Absolute FCBI+ is still
emitted, and is *amplified* by negative-RF weights (a path at RF=−10d weighs
`2^(10/5)=4.0`), so the all-negative probe returns `FCBI+ = 40.000`,
`fcbi_pct = None`.

**Category.** Specification gap. `None` is mathematically safe but **not
communicative**: a reader keying on the percentage sees a blank precisely when
the schedule is most distressed (float stock exhausted / at-or-past the
driving path).

**Recommendation.** Keep the guard. When `denom ≤ 0`, emit an explicit
labelled sentinel rather than a bare `None`, e.g.:

> "Criticality-weighted float stock exhausted. Normalized FCBI undefined.
> Interpret absolute FCBI+."

and surface FCBI+ prominently in that regime. Whether the stock should also
count `|negative-float|` capacity is a separate methodology question, not a
bug.

---

## 3. Weight timing — CONFIRMED

**Implementation fact (objective).** `_fcbi()` L254: `ek = kernels[id(earlier)]`;
all weights come from the earlier kernel. Kernels are built per schedule in
`run_li_indices()` L640. Therefore:

> **RF = RF(u-1)** — sampled at the start of the window.

Isolation probe (path built so A is its path's min-float member, i.e. RF is
A's own float, not inherited): A goes RF=20 → RF=0 while burning 20d →
observed contribution **1.25**, weight **0.0625** = `2^(-20/5)`. Confirmed
earlier-file sampling. (The naïve probe where A shares a path with a zero-float
target gives weight 1.0 for a *different* reason — path-min inheritance, item
4 — and must not be used to infer timing.)

**This is not presented as an implementation defect.** RF(u-1) is a legitimate,
self-consistent choice; it is simply undocumented (spec gap) and one of
several defensible conventions (methodology decision).

**Methodology recommendation (separate from the fact above).** For a *burn*
index, **min(RF(u-1), RF(u))** is the strongest candidate: it weights float
that was critical at *either* end of the interval, so a chain that raced from
20d to 0d — i.e. the burn that *created* the criticality — is counted at full
weight rather than the start-of-window 0.0625. Alternatives: end-of-window
RF(u) (rewards "became critical" but ignores work already critical that
de-criticalised), or the current RF(u-1). Recommend `min` over the window, but
this is the methodology owner's ruling; whichever is chosen must be stated in §9.1 and the
matrix formula.

---

## 4. RF provenance — CONFIRMED (severity softened: disclosure / reproducibility)

**Implementation facts** (all verified; none is an implementation defect):
- `_build_kernel()` → `float_paths(schedule, n=KERNEL_PATHS_N=10,
  band_days=None)`: the **top-10** distinct paths to the resolved target,
  ranked by path relative float; path 1 from `_walk()`, each subsequent path a
  least-float feeder spliced onto an existing tail.
- **Driving path** = minimum total float first (`_walk` L288-291; ties within
  `FLOAT_TIE_BAND_DAYS=0.1`d broken by date-satisfaction then code). This reads
  **tool-of-record float**, not an internal longest-path/CPM pass — so RF is
  **independent of `scheduleiq.cpm` and its retained-logic vs progress-override
  statusing**.
- **Path relative float** = min TF over activities *unique* to the path.
- **RF(activity)** = min over containing paths of their rel_float; **fallback**
  to own TF when on no enumerated path; **omitted** when neither.
- Negative RF carried through (weight > 1).

**Category — disclosure / reproducibility, not correctness.** The published
methodology does *not* promise exhaustive path enumeration, so the following
are things to *state*, not bugs to fix:
- **Path-min inheritance.** An activity's weight is governed by the most
  critical member of its path, not its own float (probe 1's A: 15d own float,
  weight 1.0 via a zero-float target). Correct per the "criticality of the
  float" intent; worth documenting so a reader does not expect own-float.
- **Top-10 truncation.** An activity reachable only on the 11th+ float path
  gets no path-derived RF and falls back to own TF; on wide networks this can
  understate near-criticality for deep alternates. `KERNEL_PATHS_N` is a fixed
  constant (L42), not surfaced in output. **Reproducibility consideration**
  (a re-runner needs to know N=10), not a defect.
- **Tie/short-path basis switch.** When candidate finishes tie and the resolved
  target yields a <2-step walk, `float_paths()` returns `[]` and RF falls back
  to each activity's **own** TF (observed: RF=20 and RF=25 = own floats, not a
  shared path min). So RF's *basis* (path-relative vs own-float) can depend on
  target resolution. Again a reproducibility/disclosure point.

**Recommendation.** Document the full RF definition (path-min, fallbacks,
truncation constant, tie behavior) verbatim in §9.1; consider surfacing
`KERNEL_PATHS_N` in output and/or making it configurable. No correctness change
is implied.

---

## 5. Windowing convention — CONFIRMED (leave as-is)

**Implementation fact.** `_fcbi()` iterates `sa.changesets` (consecutive pairs,
`trend/series.py` L115); `cumulative` (L301-302) is a running sum over those
pairs. No code recomputes FCBI over coarser/merged windows.

**Probe — TF 10 → 0 → 10.** per-window (u0→u1→u2) FCBI+ total = **10.000**;
endpoint-only (u0→u2) = **0.000**. Re-windowing invariance does **not** hold —
exactly the reviewer counterexample.

**Category.** Specification gap (disclosure only). The non-additivity is
inherent to `max(0, -ΔTF)` (a total-variation measure) and is the *desired*
behavior — burn-then-regain is real churn, not a no-op. No code change.

**Recommendation.** Add a one-line disclosure to §9.1 and the FCBI output
`interpretation`: "FCBI+ is windowing-dependent and not additive across merged
windows; compare only like-for-like update cadences." Record the window count
(already available as `len(windows)`).

---

## Proposed tests (expanded per review)

Add under the governance quartet once items 1 and 3 are ruled. Lock intended
semantics so a future change cannot land silently.

- **A — completed-activity invariance.** An activity completed in-window with
  **TF=0** must produce **identical** FCBI (burn *and* recovery) to the same
  activity with **TF=null**. Assert both cases equal the adopted rule's value
  (0 under recommendation A). Add the mirror on the recovery side.
- **B — weight timing.** Fixture where RF changes dramatically across the
  window (RF 20→0 with 20d burn, and the symmetric 0→20). Assert the
  contribution under whichever convention is adopted (e.g. under `min`:
  full-weight 20; under RF(u-1): 1.25). This pins the choice numerically.
- **C — RF basis switch.** A tied target-finish that makes `float_paths()==[]`
  must be tested explicitly (assert RF falls back to own TF, and the disclosed
  basis flag) so the path↔own-float switch cannot change silently.
- **D — windowing non-additivity.** Keep the 10→0→10 test exactly: assert
  per-window FCBI+ total = 10 and endpoint-only = 0, plus monotone
  `cumulative` under pure burn.
- **(cross-index)** optional: a completed near-critical activity asserted
  *excluded* by RDI/BWI and *included* by CDI, so the 1b asymmetry is locked
  to whatever is ruled.

---

## Minimum governance package (for the two number-changing items only)

Per house governance (matrix + spec + fixture + test change together). No
implementation is proposed here beyond what the rulings require.

**Item 1 — completion handling (recommend: freeze/exclude, burn and recovery):**
- **matrix.yaml (LI-01)** — add to `formula`/`description`: "activities
  completed within a window are excluded from both burn and recovery."
- **§9.1** — one sentence stating the freeze rule and its rationale
  (retrospective float story of *in-flight* work; consistency with RDI/BWI per
  1b).
- **seeded fixture** — extend a demo update pair with one near-critical
  activity that burns then completes, exported once with TF=0 and once with
  TF=null (or a parametrized fixture) so the invariance is real data.
- **regression test** — test A above.

**Item 3 — weight timing (recommend: `min(RF(u-1), RF(u))`):**
- **matrix.yaml (LI-01)** — `formula`: state the RF sampling convention
  explicitly (`RF = min(RF_{u-1}, RF_u)` or the chosen rule).
- **§9.1** — one sentence naming the convention and why (captures float
  critical at either interval end).
- **seeded fixture** — the RF 20→0 burn pair from test B.
- **regression test** — test B above.

Items 2, 4, 5 and 1b are **disclosure/specification** changes (wording in §9.1
+ matrix, plus the sentinel string for item 2 and the windowing note for item
5); they need no fixture beyond the tests already listed and can ship in the
same documentation pass once 1 and 3 are settled.

---

## Existing test coverage of these areas

| Existing test | Covers |
|---|---|
| `test_kernel_weights_closed_form` | kernel formula only (0/5/10/−5 d) |
| `test_fcbi_burns_across_series` | burn>0, cumulative monotone, recovery≥0, ranked burners — demo series |
| `test_fcbi_exact_two_update_pair` | one hand-computed pair (no logic → RF=own float, positive stock, no completed activity) |

**Gaps:** items 1, 1b, 2, 3, 4, 5 are entirely uncovered. Proposed tests A-D
(+ cross-index) close them.

## Recommended ruling priority
1. **Item 1** (changes numbers; non-reproducible across exporters) — rule
   first; make it consciously consistent with 1b.
2. **Item 3** (changes numbers; methodology substance) — rule next.
3. **Item 1b** — decide whether the retrospective/forward split is intended and
   state it.
4. Items 2, 4, 5 — disclosure/specification; adopt wording + the sentinel +
   the windowing note once 1/3 are settled.
