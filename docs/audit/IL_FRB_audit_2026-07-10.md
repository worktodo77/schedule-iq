> **PROVENANCE (2026-07-12).**  Authored on the unmerged lineage-A branch as an
> AUDIT ONLY record (its rulings were never adjudicated there); imported
> VERBATIM as the as-audited record for the Wave-2 revisions on THIS base,
> where the principal adjudicated the requested rulings on 2026-07-12:
> IL1-A / IL2-A / IL3-via-IL2 / IL4a+IL4b / IL5 and FR2-A / FR3-A
> ([docs/rulings/LI-08-il-v2-2026-07-12.md](../rulings/LI-08-il-v2-2026-07-12.md),
> [docs/rulings/LI-03-frb-v2-2026-07-12.md](../rulings/LI-03-frb-v2-2026-07-12.md)).
> FR1 and W1 were fixed earlier in Wave 0 (see CHANGELOG).  Code line numbers
> and suite counts cited inside refer to the lineage-A branch; every audited
> pre-ruling behavior was independently reproduced on this base.

# IL (LI-08) / FRB (LI-03) implementation audit — Intervention Latency & Forecast Reliability Band

**Date:** 2026-07-10 · **Auditor:** Claude (lead) · Fourth audit in the
series, applying the reusable template from docs/audit/FCBI_audit_2026-07-08.md,
docs/audit/RDI_BWI_CDI_audit_2026-07-08.md and docs/audit/LHL_audit_2026-07-09.md.

**Status: AUDIT ONLY — no code or spec changed.** Every behavior below is the
as-is v0.4.5 behavior, reproduced with live probes; rulings are requested at
the end. Bespoke LI metric definitions are methodology decisions owned by the
principal — this document audits and proposes, it does not revise.

**Why these two together.** Both are SCORED Report Card members at weight 2
(LI-08 in Float & Progress Management, LI-03 in Forecast Credibility — each
category 20 of 85). LI-08 is the only *other* metric scored through a special
handler (`_li08_score`), the branch structure where the LHL audit found both
of its HIGH defects; LI-03 is scored through the ordinary wiring value, where
a suspicious attribute access was flagged during the LHL work. Both suspicions
are confirmed below. Neither metric consumes the criticality kernel; each has
its own machinery (emergence/response scanning; forecast-outcome matching),
audited directly.

## Finding categories (same taxonomy; kept distinct — do not conflate)

- **Implementation defect** — the code does something other than what the
  spec/published mapping says, or produces a wrong/unsafe result.
- **Specification gap** — a reasonable choice, undocumented in §9.3/§10.3 / matrix.
- **Methodology decision** — a substantive modelling choice (changes numbers)
  that is legitimate but must be *ruled on and recorded*, not assumed.
- **Disclosure / reproducibility issue** — correct given its own definition,
  but a reader or re-runner could be surprised unless stated.

Severity is the operational consequence, independent of category.

**Scope reviewed**

| Artifact | Location |
|---|---|
| FRB metric | `src/scheduleiq/analytics/li_record.py` — `forecast_reliability_band()` L500-541, `_FRB_BUCKETS`/`_bucket_for` L459-467, `_bucket_stats` L470-476, `_add_workdays` L479-497, `frb_apply_forward()` L544-564 |
| IL metric | same file — `intervention_latency()` L777-838, `_response_in()` L747-774, `_connected_components()` L716-740, `_budget_units_sum` L743-744 |
| Wiring | `src/scheduleiq/analytics/li_wiring.py` — LI-03 block L90-108 (the defective field reads), LI-08 block L153-169, LI-04 block L111-118 (incidental W1) |
| Pipeline guard | `src/scheduleiq/trend/series.py` L410-416 (`li_series_results` under a blanket except) |
| Scoring | `scorecard.py::_li08_score` (special handler); LI-03 via the ordinary `_series_member` path reading `sa.series_results`; `scorecard.yaml` LI-08 (points `[[0,100],[2,70],[6,0]]`, `unresolved_only_score: 20`) and LI-03 (points `[[0,100],[20,70],[60,0]]`) |
| Matrix | `metrics/matrix.yaml` LI-03 L954-966, LI-08 L1019-1031 |
| Spec | `docs/ANALYTICS_PROPOSAL.md` §9.3 (FRB), §10.3 (IL) |
| Inputs | `compare/diff.py` — `duration_changes` format `f"{h:.0f}h"` L104-107 (IL's parser matches), `float_deltas` L145-150 (no LOE/completed guard); `intake/_util.py::working_days_between` (signed, actual−forecast positive = late — matches the matrix wording) |
| Tests | `tests/test_li_record.py` — FRB L~275-310, IL L~345-365 |

All findings reproduced with live probes driving `forecast_reliability_band()`,
`intervention_latency()`, `_li08_score()`, `li_series_results()` and
`score_series()` on hand-built series plus the three-update demo fixture.
Suite green at HEAD (2103 passed, 2 skipped); none of the findings below is
covered by an existing test.

---

## Executive summary

| # | Metric | Area | Current behavior | Category | Severity | Moves a SCORED number? |
|---|---|---|---|---|---|---|
| **FR1** | FRB/LI-03 | Wiring reads fields that don't exist | `li_wiring` reads `b.bias`/`b.p10`/`b.p90`; the dataclass fields are `bias_days`/`p10_days`/`p90_days`. Every `getattr` returns the default 0, so **band_width = 0 − 0 = 0 always** and **LI-03 scores 100 on every series**, regardless of forecast quality. Probe: true band 36 wd → correct score 42, wired score 100. Findings text always reads "bias +0.0d, band P10 +0.0d .. P90 +0.0d". | **Implementation defect** | **High** | **Yes — LI-03 is pinned at 100 for everyone** (58-point inflation in the probe) |
| **IL1** | IL/LI-08 | Published 100-anchor unreachable + same-window response invisible | `il_updates = j − i` with `j ≥ i+1`, so the minimum observable latency is 1 update — the yaml's "0 updates (same-update response) scores 100" can never fire; **best attainable LI-08 = 85**. Worse: a mitigation landing in the SAME window as the emergence is not scanned (responses scan starts at the next changeset), so the event reads *unresolved* — probe: halving the duration in the emergence window scores **20**, while doing nothing for a month and then acting scores **85**. The fastest possible response gets the worst score. | **Implementation defect** (mapping unreachable) + methodology (same-window semantics) | **High** | **Yes — ceiling 85; perverse 20-vs-85 inversion** |
| **IL2** | IL/LI-08 | Unresolved events excluded from the median | The median is computed over resolved events only; unresolved chains affect nothing but the offender count. Probe: respond to 1 chain in 1 update while ignoring 5 others → median 1, **score 85** — identical to a perfect responder. The 20-point "did not act" branch fires only when *nothing* ever resolved. | Methodology decision | Medium-High | Yes (score blind to ignored chains) |
| **IL3** | IL/LI-08 | Final-window emergence can never resolve | An emergence in the last update pair has no later changeset to scan; it is always "unresolved". Probe: a series whose only emergence is in the final window scores **20 ("did not act")** though no response opportunity ever existed. No censoring concept (contrast LHL's KM). | Methodology decision | Medium | Yes (20 vs N/A on young/short series) |
| **IL4** | IL/LI-08 | LOE/summary + completed population | `float_deltas` carries no LOE/summary guard, so a hammock flipping negative forms an emergence chain and can drive the score (probe: LOE-only chain → score 20). The prior family audit **explicitly deferred IL's LOE question** — this is the ruling's venue. Completed activities are excluded only when the exporter nulls their TF (representation-dependent, the X1 family concern). | Methodology decision (deferred family ruling) | Medium | Yes |
| **IL5** | IL/LI-08 | Data-date validation | Out-of-order data dates → **negative `il_days`** (probe: −30) and a negative `median_il_days`, silently. Same class as LHL's L9 (updates-based `il_updates` — the scored number — is unaffected). | Implementation defect (missing validation) | Low-Med | Not the scored value (days are narrative) |
| **FR2** | FRB/LI-03 | Zero/negative horizons unbucketed | An overdue forecast (finish ≤ data date — the *most diagnostic* forecast an analyst can test) is recorded as an observation but falls into **no bucket** (`lo < h` with lo=0): probe: 2 of 3 observations silently outside all bands. `frb_apply_forward` likewise refuses overdue horizons with a generic message. | Spec gap + methodology | Medium | Yes (band composition) |
| **FR3** | FRB/LI-03 | No minimum-n on the scored band | `frb_apply_forward` refuses to band a forecast on n < 5, but the LI-03 **score** happily uses the largest bucket at any n — the demo fixture scores off a bucket with **n = 1** (width 0 → 100 even if FR1 were fixed). | Methodology decision / cross-surface inconsistency | Medium | Yes |
| **W1** | wiring (LI-04 block; blast radius all LI) | Wiring crash silently blanks all ten LI indices | `li_wiring` LI-04 findings do `f"PCI {val:.3f}"` on `per_update` values that are **typed `Optional[float]`**; a None value raises, the pipeline's blanket except catches it, and **all of LI-01..LI-10 are skipped** from `series_results` with only a warning — six scored members drop to N/A at once. (Found incidentally when a probe series produced a None PCI window; PCI itself is out of this audit's scope, the wiring/guard is not.) | Implementation defect | Medium (silent, wide blast radius) | Yes (members → N/A) |
| **FR4** | FRB/LI-03 | Standing disclosures / conventions | Autocorrelated observations (each update re-forecasts a still-incomplete activity; probe: 2 observations of one activity resolved by the same actual); errors measured on a **fixed Mon-Fri 8h calendar** (docstring-only); scored basis = "largest bucket" only vs the spec's per-horizon FRB80(h); actual-finish lookup is code-keyed (re-code → forecast never resolves). No disclosure surface on `FRBResult`. | Disclosure / spec gap (X-series) | Low-Med | No |
| **IL6** | IL/LI-08 | Standing disclosures / conventions | "Response" = *any* touching edit (logic add/modify, duration decrease, calendar change, budget increase) — deliberately not "effective mitigation" (consistent with §10.3's acted-vs-worked distinction) but stated nowhere in output; duration-decrease detection is coupled to the `"{h:.0f}h"` diff string format; chains are grouped on the LATER schedule's edges, code-keyed; emergence requires TF non-null on both sides of the window. No disclosure surface on `ILResult`. | Disclosure (X-series) | Low-Med | No |

**Verified-correct (positive findings).** `working_days_between` sign
convention matches the matrix (positive = finished late). IL's
duration-decrease parser matches the diff's actual `"###h"` format (a
suspicion that did **not** survive probing). `_bucket_stats` percentile
arithmetic is the shared, already-tested `percentile()`. The demo pinned
letters are currently produced with FR1/IL1 live: demo LI-03 coincidentally
scores 100 either way (its largest bucket has n=1 → true width 0), and demo
LI-08 = 85 (1 event resolved in 1 update), so fixing FR1 alone does not move
the demo letters — but on any real series with forecast dispersion, FR1 is a
grade-inflating defect.

---

## FR1 — LI-03 is wired to a constant zero: every series scores 100 (HIGH) — CONFIRMED

**Implementation facts** (`li_wiring.py` L85-96):

```python
finds.append(Finding(getattr(b, "label", "bucket"), "",
             f"n={b.n}, bias {getattr(b, 'bias', 0):+.1f}d, "
             f"band P10 {getattr(b, 'p10', 0):+.1f}d .. "
             f"P90 {getattr(b, 'p90', 0):+.1f}d"))
...
band_width = getattr(best, "p90", 0) - getattr(best, "p10", 0)
```

`FRBBucket`'s fields are `bias_days`, `p10_days`, `p90_days` (li_record.py
L447-455). Every one of these `getattr` calls silently returns its default.
Consequences, all probe-confirmed:

- `band_width` = 0 − 0 = **0** whenever any bucket has n > 0; the LI-03
  member value is 0.0 and the piecewise curve `[[0,100],[20,70],[60,0]]`
  awards **100 to every series** with at least one resolved forecast.
- **Divergence probe**: 6 activities forecast at a ~20d horizon, actuals
  spread from 7 wd early to 43 wd late → the real bucket reads n=6, bias
  +11.0, P10 −3.0, P90 +33.0, **true width 36.0 wd → correct score 42**.
  Wired: width 0 → **score 100**. A 58-point member inflation on a
  demonstrably unreliable forecaster.
- The findings text shown to the reader is `bias +0.0d, band P10 +0.0d ..
  P90 +0.0d` for every bucket — the narrative asserts perfect forecasting
  while `FRBResult` holds the real numbers.
- The metric layer itself is **correct** — `frb_apply_forward` reads the
  right fields; only the wiring/report surface (and therefore the score) is
  broken. Note the metric layer is exactly what the existing tests test,
  which is why this survived: no test reads the wiring's LI-03 result.

**Demo-fixture note.** The demo scores LI-03 = 100 with or without the bug
(its largest bucket has a single observation, so the true width is also 0 —
see FR3). Pinned letters therefore hold under a fix; real series with
forecast dispersion move.

**Category / severity.** Implementation defect, HIGH — a scored member is
constant at full credit, and the exhibit text fabricates zero bias/zero
dispersion. Same class as the LHL L1 finding: the defect lives between a
correct metric and the score.

**Recommended fix shape (for the ruling, not applied):** read
`bias_days/p10_days/p90_days`; add a regression test that pins a nonzero
band width and its score through `li_series_results` → `score_series`.

---

## IL1 — The LI-08 100-point anchor is unreachable; same-window responses score WORSE than slow ones (HIGH) — CONFIRMED

**Implementation facts.**
- `intervention_latency` detects emergence in changeset `i` and scans
  responses in `changesets[j]` for `j in range(i+1, …)` (li_record.py
  L826-833): `ev.il_updates = j - i` ≥ **1** always.
- scorecard.yaml LI-08: points `[[0,100],[2,70],[6,0]]`, rationale: *"0
  updates (same-update response) scores 100"*.
- Therefore `_piecewise_score(1, …) = 85` is the **best attainable LI-08
  score**; the published 100 anchor cannot fire. (Probe-confirmed.)
- A responsive edit made in the SAME update in which the negative float
  first appears — the fastest response the record can possibly show — is
  never scanned. Probe: X flips to negative float and has its duration
  halved in one window → the event is **unresolved**, and with no other
  events the series scores **20 ("did not act")**. The same edit made one
  update later scores **85**.

**Why it matters.** The metric's stated purpose is distinguishing "didn't
act" from "acted." Under current semantics the *promptest* actor is
classified as not having acted at all — an inversion with direct grade
consequence (20 vs 85), and the mapping's top anchor is dead code, capping
everyone at 85.

**Category.** Two entangled pieces:
1. *Implementation defect* — the code cannot produce the value its own
   published mapping anchors at 100 (mapping/implementation mismatch — the
   same "published rule vs code" class as LHL-L1).
2. *Methodology decision* — what a same-window edit MEANS. Options:
   **(A)** scan the emergence changeset itself for responsive edits and
   record `il_updates = 0` (makes the anchor reachable; treats
   emergence-window mitigation as latency zero — recommended);
   **(B)** keep same-window edits invisible but re-anchor the curve at 1
   (declares one update the best measurable latency; keeps the "response
   must FOLLOW emergence" purity but concedes the record's resolution);
   **(C)** as A, but count a same-window response only when the edit
   post-dates the float signal — not implementable from snapshot diffs;
   listed for completeness.
   Recommend **A**, with the caveat that a same-window "response" is
   observationally simultaneous with the emergence (disclose: causality is
   asserted by adjacency, not sequence — true at every latency here).

---

## IL2 — Unresolved chains are invisible to the median (Medium-High) — CONFIRMED

**Implementation fact** (li_record.py L840-846): `median_il_updates` =
`percentile(resolved_updates, 50)` over events with a response;
`unresolved_count` is carried separately and reaches the score only as the
offender count — except in the *nothing-ever-resolved* case, where the
20-point branch fires (`_li08_score`).

**Probe.** One chain responded to in 1 update; five chains ignored forever:
`events=6, resolved=1, median=1 → score 85, offenders 5` — the identical
score as the perfect single-chain series (`events=1 → 85, offenders 0`).

**Why it matters.** §10.3 frames IL as quantifying *failure-to-mitigate*.
A schedule that triages one visible chain and abandons five is
indistinguishable, in score, from one that mitigates everything. The
current design grades "how fast were the responses you chose to make",
not "did you respond".

**Category / options (methodology).** (A) treat never-resolved events as
right-censored at the series end and estimate the median with the KM
machinery LHL already has (`kaplan_meier` is sitting in the same module);
(B) blend: score = curve(median) penalized by unresolved share (e.g. scale
toward 20 as unresolved/total → 1); (C) keep as-is, disclose that the
median is conditional-on-response and rely on the offender count. KM (A) is
the statistically honest option and reuses proven code; it also subsumes
IL3. Owner's call — each option changes scores.

---

## IL3 — Final-window emergence always reads "did not act" (Medium) — CONFIRMED

**Implementation fact.** An emergence at pair `i = len(changesets)−1` has
an empty response scan range → always unresolved. **Probe:** a 2-schedule
series whose only emergence is in that one window scores **20** — "did not
act" — when no update in which to act even exists.

**Category.** Methodology: this is right-censoring, unhandled. Under IL2's
option A it dissolves (a last-window event is censored at latency 0 with no
information, and KM handles it); under B/C it needs its own rule (e.g.
events with zero response opportunity are excluded from both the median and
the 20-point trigger). Interacts with `_li08_score`'s
`unresolved_only_score` branch — a young series with one late emergence
gets the worst-in-class 20 by construction.

---

## IL4 — LOE/summary chains and representation-dependent completion (Medium) — CONFIRMED

**Implementation facts.** `compare()` builds `float_deltas` for any
activity with TF non-null in both files — no `is_loe_or_summary`, no
`completed` guard (diff.py L145-150); `intervention_latency` consumes them
unfiltered (L802-811). **Probe:** a hammock (`LOE`) whose TF flips negative
forms a single-member emergence chain, is never "responded to", and drives
LI-08 to **20** on an otherwise-clean series.

The RDI/BWI/CDI audit's family table *explicitly deferred* this: "IL would
count an LOE turning negative-float as an emergence chain — warrants a
separate methodology ruling if desired." This audit is that venue. The LHL
ruling (L4a) has since excluded LOE ties from LI-02 on "hammock churn is
bookkeeping" grounds; the parallel argument here is that a hammock's float
is derived from the work it spans — the *spanned work's* chain will (and
should) carry the emergence. Counting the hammock double-counts, and a
hammock-only chain (probe) is pure noise.

Completed activities are excluded only when the exporter nulls completed
TF; a tool that writes TF=0…−n on completed work feeds them into emergence
chains — the same exporter-variance concern as FCBI item 1 (X1 family).

**Recommendation.** Exclude `is_loe_or_summary` from the emergence set
(family consistency); rule completed-activity handling explicitly
(recommend: exclude activities completed in the later file from the
emergence set — a finished activity's float is not a mitigable problem).
Both are population rulings for the owner.

---

## IL5 — Out-of-order data dates yield negative il_days (Low-Med) — CONFIRMED

`ev.il_days = (rd − l.data_date).days` with no ordering validation
(L834-836). **Probe:** data dates running backwards → `il_days = −30`,
`median_il_days = −30`, silently. The scored value (`il_updates`) is
ordinal and unaffected, so severity is below LHL-L9, but the narrative
number is nonsense on the same input class the LHL ruling now guards.
**Recommendation:** apply the L9 convention — withhold day figures with a
disclosure when data dates are missing/non-increasing.

---

## FR2 — Overdue forecasts fall out of every bucket (Medium) — CONFIRMED

**Implementation fact.** `horizon = (f − u.data_date).days`;
`_bucket_for` requires `lo < horizon ≤ hi` with the first bucket at
`(0, 30]` — a forecast finish **on or before** the data date (an overdue
activity still carrying an early/planned finish in the past, or finishing
today) has horizon ≤ 0 and lands in no bucket. **Probe:** horizons
[−10, 0, 10] → only the 10-day observation is bucketed; the other two are
recorded in `observations` but invisible to every band, bias, width and
score. `frb_apply_forward` refuses the same horizons with "falls outside
the defined buckets".

**Why it matters.** Overdue-but-unfinished work is precisely where forecast
credibility dies; excluding those errors biases every band toward the
well-behaved part of the record. (It also makes `observations` ≠
Σ bucket n, an internal-consistency surprise for a re-runner.)

**Category / options.** Spec gap + methodology: (A) add an "overdue/≤0d"
bucket, reported and scored like the others (recommended); (B) clamp ≤0
horizons into the 0-30d bucket; (C) keep exclusion, disclosed. Owner's call.

---

## FR3 — The scored band has no minimum-n; the demo scores off n=1 (Medium) — CONFIRMED

`frb_apply_forward` refuses to band a live forecast when the bucket has
fewer than 5 observations — the metric's own reliability floor. The LI-03
*score* has no such floor: the wiring picks the largest-n bucket, whatever
its n; the demo fixture's is **n=1**, whose width is definitionally 0 →
score 100 even with FR1 fixed. A single resolved forecast should not
certify a forecaster. **Options:** (A) apply the same n≥5 floor to scoring
— below it, LI-03 is ungradeable with a reason (consistent with the LHL
L10 convention: insufficient basis ⇒ N/A, not free credit); (B) score the
pooled all-horizon distribution when no bucket clears the floor; (C) keep,
disclosed. Recommend A, with B as the fallback variant if the owner wants
LI-03 gradeable on thin records.

---

## W1 — One malformed LI value silently blanks all ten LI indices (Medium) — CONFIRMED (incidental)

**Implementation facts.** `li_wiring.py` L114 formats PCI findings with
`f"PCI {val:.3f}"` over `p.per_update`, which is **typed
`list[Optional[float]]`** (li_indices.py L346) — a None raises TypeError.
`trend/series.py` L410-416 wraps the whole `li_series_results` call in a
blanket `except`, so the raise is converted into *"LI proprietary indices
skipped"* in `sa.warnings` — and **every** LI-01..LI-10 MetricResult
vanishes from `series_results`. Scored members that read series_results
(LI-01, LI-03, LI-04, LI-05, LI-06, LI-09) all drop to N/A; only LI-02 and
LI-08 survive via their special handlers. Found live: an audit probe series
produced a None PCI window and the entire wiring call crashed.

**Category.** Implementation defect (format-on-Optional) plus a
robustness-design smell (one metric's cosmetic failure takes down ten).
**Recommendation:** guard the format (`"—"` for None) and, separately,
consider per-index try/except inside `li_series_results` so a single index
degrades alone. PCI/LI-04 substance is out of this audit's scope — this is
reported as a wiring/guard finding.

---

## FR4 / IL6 — Standing disclosures (X-series) — CONFIRMED

Neither `FRBResult` nor `ILResult` carries the disclosures block the rest
of the family now has (LHL X1 pattern). Contents that belong there:

**FRB:** observation model (every update × every then-incomplete activity;
one activity yields multiple autocorrelated observations — probe: 2 for one
activity, resolved by the same actual); error units (working days on a
**fixed Mon-Fri 8h calendar**, docstring-only today); horizon basis
(calendar days, forecast − data date); the bucket boundaries and the
zero/negative-horizon rule (per FR2's ruling); the scored basis (largest
bucket, min-n per FR3's ruling); code-keyed actual matching (a re-coded
activity's forecast never resolves — family L3 disclosure).

**IL:** what counts as a "response" (any touching edit — logic
added/modified, duration decrease, calendar change, budget-units increase —
deliberately *not* "effective mitigation"; §10.3's acted-vs-worked split);
the duration-decrease detector's coupling to the diff's `"###h"` string
format (breaks silently if the diff format changes — at minimum a comment
tying the two); chain construction (undirected components over the LATER
schedule's code-keyed edges); emergence definition (TF crossing 0 downward
between two non-null observations; new activities born negative are NOT
emergences); the IL2/IL3 conventions as ruled.

---

## Proposed tests (lock behavior once ruled)

- **U1 (FR1)** — a series with dispersed forecast errors: assert the LI-03
  MetricResult value equals the largest bucket's true `p90_days − p10_days`
  (36.0 in the probe), the findings text carries the real bias/band, and
  `score_series` maps it through the curve (42.0). This test MUST go
  through `li_series_results`, not the metric layer (the metric layer was
  never broken — that's why existing tests missed it).
- **U2 (IL1)** — same-window response: emergence pair contains the
  responsive edit → assert the ruled outcome (under A: `il_updates == 0`,
  score 100 attainable; under B: re-anchored curve pins
  `_piecewise_score(1) == 100`). Plus: assert the published anchor is
  attainable under whichever ruling lands.
- **U3 (IL2)** — the 1-resolved + 5-ignored series: assert the ruled score
  ≠ the perfect-responder score (KM option: censored events enter the
  estimate; blend option: pinned penalty).
- **U4 (IL3)** — sole emergence in the final window: assert the ruled
  outcome (censored/N-A, not 20).
- **U5 (IL4)** — a hammock-only negative-float chain is excluded from the
  emergence set; a completed-in-later-file activity likewise (per ruling);
  a mixed chain keeps its discrete members.
- **U6 (IL5)** — out-of-order data dates: day figures withheld + disclosed;
  `il_updates` unaffected.
- **U7 (FR2)** — horizons −10/0/+10: assert the ruled bucketing (overdue
  bucket or clamp) and that Σ bucket n == len(observations) under it.
- **U8 (FR3)** — largest bucket n < 5: assert LI-03 ungradeable-with-reason
  (or the ruled fallback), not scored 100 off one observation.
- **U9 (W1)** — a PCI result with a None per_update window: wiring emits
  "—" (no raise); all other LI indices still present in series_results.
- **U10 (FR4/IL6)** — disclosures blocks present with the key phrases.

## Minimum governance package (for the number-changing rulings FR1, IL1, IL2/IL3, IL4, FR2, FR3)

impl + matrix wording (LI-03/LI-08) + §9.3/§10.3 wording + seeded in-memory
fixtures + regression tests U1-U10, together; regenerate METRIC_MATRIX.md;
CHANGELOG note; version bump. FR1 and IL1 move SCORED members on every
real series — the anchor-recalibration caveat applies (LI-03's
[[0,20,60]] width curve has never actually been exercised by real values;
expect letter movement on real files, which is the point). Pinned demo
letters: verify after each ruling (demo currently insensitive to FR1 —
n=1 bucket — and scores LI-08=85; FR3's n≥5 floor WOULD move the demo
LI-03 member from 100 to N/A, reweighting Forecast Credibility — flag for
the owner when ruling FR3).

## Rulings requested (accept / defer / reject per item)

1. **FR1 — fix the LI-03 wiring field names** (and pin through
   score_series). Recommend **accept** (implementation defect; scored
   member constant at 100 today).
2. **IL1a — make the published 100 anchor attainable**: scan the emergence
   changeset for responses (`il_updates = 0`, option A) or re-anchor the
   curve at 1 update (option B). Recommend **A**, with the
   adjacency-not-sequence disclosure.
3. **IL2 — unresolved chains and the median**: KM right-censored estimate
   (A, recommended — reuses `kaplan_meier`), blended penalty (B), or
   disclose-only (C).
4. **IL3 — zero-opportunity emergences**: dissolve via IL2-A, or exclude
   from both the median and the 20-point trigger. Recommend **with IL2-A**.
5. **IL4a — LOE/summary emergence chains**: exclude (family consistency;
   recommended) or include disclosed.
6. **IL4b — completed-activity emergence**: exclude activities completed in
   the later file (recommended) or keep the TF-null-dependent status quo,
   disclosed as exporter-variant.
7. **IL5 — day-figure validation**: adopt the L9 convention for `il_days`.
   Recommend **accept**.
8. **FR2 — overdue forecasts**: add an overdue bucket (A, recommended),
   clamp (B), or keep-excluded disclosed (C).
9. **FR3 — minimum-n for the scored band**: n≥5 floor with
   ungradeable-with-reason below it (A, recommended; note it moves the demo
   LI-03 member to N/A), pooled fallback (B), or keep (C).
10. **W1 — wiring None-guard + per-index isolation**: guard the PCI format
    and stop one index's failure from blanking all ten. Recommend
    **accept** (defect + robustness).
11. **FR4/IL6 — standing disclosures packages** on FRBResult and ILResult,
    per the family pattern. Recommend **accept** once 1-10 are ruled, one
    documentation pass.

No behavior was changed in this pass.
