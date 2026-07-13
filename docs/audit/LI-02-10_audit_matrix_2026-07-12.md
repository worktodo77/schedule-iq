# LI-02..LI-10 audit matrix — applying the FCBI (LI-01) v0.5 lessons

**Date:** 2026-07-12 · **Auditor:** Claude (implementation owner, LI metrics) ·
**Status: AUDIT ONLY — no production code, spec, fixture, or test changed.**
Fifth audit in the series; template follows the four prior audits and the
LI-01 v0.5 governed-revision precedent (docs/rulings/LI-01-fcbi-v0.5.md,
GOVERNANCE.md §1).  Bespoke LI metric definitions are methodology decisions
owned by the principal (Alex Bachowski); this document audits and proposes,
it does not revise.

**Base audited:** `ec30292` (LI-01 FCBI locked at v0.5.6).  Suite at base:
**226 passed, 1 skipped** (`PYTHONPATH=src python3 -m pytest tests/ -q`).
Every finding below was **reproduced with live probes** on hand-built
in-memory series against this base (probe runner:
`docs/audit/probes/li02_10_audit_probes_2026-07-12.py`; the probe outputs
quoted in each section are from that run), or is marked *code-read* where the
behavior is directly visible in the source and a probe adds nothing.

---

> **Rulings received (principal, 2026-07-12) — triage round 1.**
> - **Q-B (kernel cluster): RULED — build the new governed LI kernel**
>   (nonnegative distance, no own-float fallback → unresolved is
>   quarantined/disclosed, w ∈ (0, 1], LOE-free margins, disclosed
>   truncation), adopted per-metric under per-metric rulings;
>   `kernel_weight`/`relative_float_map` stay byte-identical until retired.
>   Executed in Wave 3.
> - **Q-C (0.0 sentinels): RULED — approved as a defect-class batch; EXECUTED**
>   (recorded ruling docs/rulings/LI-05-LI-06-not-evaluated-2026-07-12.md;
>   RDI-1 and BDI-1 now NOT EVALUATED — None + reason — through the wiring;
>   check-affecting: previously such series scored 100; suite 240 passed,
>   1 skipped).
> - **Sequencing: APPROVED as proposed; Wave 0 authorized and implemented**
>   (see CHANGELOG "LI wiring defect batch"; FR1/W1/W2 fixed with 7
>   wiring-path regressions; suite 233 passed, 1 skipped).
> - **Q-A (lineage-A port): RULED — port as-ruled** (triage round 2,
>   2026-07-12).  **Wave 1 EXECUTED in full:** 1a LHL v0.4.5
>   (docs/rulings/LI-02-lhl-port-2026-07-12.md), 1b RDI R1/R2 + BWI B1/B2
>   (docs/rulings/LI-05-LI-09-rdi-bwi-port-2026-07-12.md), 1c kernel C1 LOE
>   exclusion + mixed-path neutralization + CDI C2
>   (docs/rulings/LI-04-LI-07-kernel-loe-port-2026-07-12.md); as-audited
>   lineage-A records imported under docs/audit/ with provenance banners.
>   Suite after Wave 1: 272 passed, 1 skipped; all FCBI anchors unchanged;
>   pinned demo letters hold.  Findings resolved so far: FR1/W1/W2 (Wave 0),
>   RDI-1/BDI-1 (sentinels), all LHL items, RDI-3/RDI-4/RDI-6(part),
>   BWI-1/BWI-2, CDI-1(LOE part)/CDI-3, PCI-2/K3(kernel part).  Still open:
>   K1/K2/K4/K5/K6 + PCI weight residual (Wave 3, under the Q-B new-kernel
>   ruling), IL-1..6 + FRB FR2/FR3/FR4 (Wave 2, Q-D/Q-E), RDI-2, BDI-2..5,
>   MML-1..5, CDI milestone/fallback membership (Waves 3-4).
>   Q-D..Q-H remain open, asked per-wave per the FCBI Q1-Q7 practice.
> - **Q-D/Q-E (Wave 2): RULED — all recommended options adopted; EXECUTED**
>   (2026-07-12): IL1-A emergence-window scan, IL2-A KM right-censoring
>   (subsumes IL3), IL4 population package, IL5 day-figure convention, IL6
>   disclosures; FR2-A overdue bucket, FR3-A n≥5 scoring floor, FR4
>   disclosures (docs/rulings/LI-08-il-v2-2026-07-12.md,
>   docs/rulings/LI-03-frb-v2-2026-07-12.md; as-audited record imported at
>   docs/audit/IL_FRB_audit_2026-07-10.md).  Findings IL-1..6 and
>   FRB-FR2/FR3/FR4 are RESOLVED.  Suite after Wave 2: 279 passed,
>   1 skipped.  Remaining open work: Wave 3 (kernel cluster K1/K2/K4/K5/K6,
>   PCI weight residual, RDI-2, CDI milestone/fallback membership, under the
>   Q-B new-kernel ruling) and Wave 4 (BDI-2..5, MML-1..5 — Q-F/Q-G/Q-H).
> - **Adversarial review wave 1 (Waves 0-1c): COMPLETE, loop closed**
>   (2026-07-12).  3 MAJOR + 2 MINOR findings, all reproduced and
>   dispositioned (W1c-1 milestone floats retained in kept-path margins;
>   W1c-2 unfloated-branch fallback to the branch basis, never the tail min;
>   W1c-3 BWI projected-break on true required pace; W1c-4/5 record
>   wording) — full table in
>   docs/rulings/LI-04-LI-07-kernel-loe-port-2026-07-12.md.  Clean areas
>   with probe evidence: FCBI/paths byte-identity, never-raises, Wave-3
>   scope locks, all ported ruling arithmetic.  Suite after dispositions:
>   282 passed, 1 skipped.
> - **Review wave 2: run at REDUCED SCOPE, implementation-side** (the
>   independent reviewer was terminated by a spend limit — disclosed; an
>   independent confirmation wave is owed).  W1c fixes + Wave-2 IL/FRB
>   verified on-probe; one new finding **RW2-1** (zero-float-evidence
>   branch leaked the tail min through the shared rel_float_days fallback
>   -> fabricated rf 0.0) FIXED with regression.  Suite: 283 passed,
>   1 skipped.
> - **Q-F/Q-G/Q-H (Wave 4): RULED — all recommended options adopted;
>   EXECUTED** (2026-07-12): BDI fixed original-duration basis + LOE
>   zero-length + explicit baseline/target params
>   (docs/rulings/LI-06-bdi-v2-2026-07-12.md — resolves BDI-2..5); MML basis
>   segregation + sustained clean mile + event overlay wired + named
>   no-clean-mile reasons (docs/rulings/LI-10-mml-v2-2026-07-12.md —
>   resolves MML-1..5); kernel constant governance via λ/band sensitivity
>   sets + recorded conventions (docs/rulings/LI-kernel-constants-
>   2026-07-12.md — resolves K4/K6 and discloses K5's PCI floor).  Suite
>   after Wave 4: 293 passed, 1 skipped.  REMAINING OPEN: Wave 3 only — the
>   new governed LI kernel under Q-B (K1 own-float fallback, K2 w>1
>   premium, K5 truncation/convergence, PCI weight residual + scored-anchor
>   re-exam, RDI-2 demonstrated-population gate, CDI milestone/fallback
>   membership) — design to be presented to the principal before
>   implementation — plus the owed independent confirmation review wave.
> - **Wave 3 (kernel v2): DESIGN APPROVED (D1–D4) AND EXECUTED**
>   (2026-07-12).  Design presented before implementation
>   (docs/LI-kernel-v2-design-2026-07-12.md, commit 8d36b34); the principal
>   ruled D1 full FCBI basis reuse (per-metric targets), D2 severity strip
>   beside PCI/CDI, D3 CDI accrue-while-live, D4 LI-04 provisional/
>   ungraded.  PCI/CDI/RDI/BWI now run on the FCBI v0.5 family basis
>   (`_build_kernel_v2`, oracle-locked to the locked `_target_distance` on
>   a 40-DAG corpus); recorded ruling
>   docs/rulings/LI-kernel-v2-2026-07-12.md.  **Findings K1/K2/K5, the PCI
>   weight residual, RDI-2, and the CDI milestone/fallback membership are
>   RESOLVED** (K5's Herfindahl-floor disclosure is superseded — the floor
>   is gone; LI-04's scored anchors are provisional pending recalibration).
>   Legacy v0.4 helpers byte-identical, retired from the pipeline; FCBI /
>   enumerator / white paper untouched; pinned demo letters hold (LI-04
>   ungraded).  Suite after Wave 3: 296 passed, 1 skipped.
> - **Review wave 3 (the owed independent wave): EXECUTED, loop closed**
>   (2026-07-12/13).  Independent adversarial review over Waves 3/4 plus
>   confirmation of review-wave-2's reduced-scope territory.  Clean with
>   probe evidence: scope C (legacy kernel byte-identical; W1c-1/2/3 +
>   RW2-1 re-derived fresh), FCBI byte-identity, 120-fresh-DAG oracle
>   equivalence + exact cap boundary, 494-call never-raises sweep, honest
>   sentinels, all Wave-3/4 closed-form anchors re-derived.  **1 MAJOR
>   (RW3-F1: BWI projected break asserted against a fabricated 0.0
>   demonstrated pace when the family basis was NOT EVALUATED) + 6 MINOR
>   (RW3-F2..F7)** — all reproduced and dispositioned (5 fixed, 2 fixed as
>   disclosure with the underlying methodology choice OPEN); full table in
>   docs/rulings/LI-kernel-v2-2026-07-12.md.  Suite after dispositions:
>   304 passed, 1 skipped.  REMAINING OPEN: (i) TWO methodology questions
>   for the principal — RW3-F7 (demonstrated-numerator endpoint: later
>   update, as disclosed, vs earlier endpoint — number-changing) and
>   RW3-F6 (should PCI also quarantine governed PATHS — number-changing);
>   (ii) LI-04 anchor recalibration against real series (separate flagged
>   step, D4); (iii) the legacy-kernel formal retirement record at
>   eventual removal.

## 0. PRECONDITION FINDING — two unreconciled development lineages (LIN-1)

**This is the single most important governance fact in this audit and gates
everything below.**

The repository holds two divergent, never-merged lineages built from the
v0.2.0 import (`c0a64bf`):

| Lineage | Branches | Content | State |
|---|---|---|---|
| **A** (2026-07-08..10) | `claude/scheduleiq-v0.3-engine-port-rx96cl` → `claude/lhl-implementation-audit-xom1ah` | CPM engine port (v0.3) **plus LI methodology work v0.4.1–v0.4.5**: FCBI v0.4.1, kernel LOE exclusion (C1) + mixed-path neutralization, BWI fixed horizon (B1) + UID target (B2), RDI P50 accrual (R2) + planned-scope basis affirmed with companion overrun ratio (R1), **LHL v0.4.5 — all 12 rulings implemented**, plus audit docs for FCBI / RDI-BWI-CDI / LHL (all **ruled by the methodology owner**) and IL+FRB (findings filed 2026-07-10, **never ruled**). ~2,100-test suite. | Never merged; not in the FCBI v0.5 base |
| **B** (2026-07-11) | `claude/fcbi-v0.5-implementation-yvsdts` (**this audit's base**) | v0.2.0 import + the entire LI-01 FCBI v0.5.0→v0.5.6 locked revision. **LI-02..LI-10 are the original v0.2.0 implementations** — none of lineage A's v0.4.x rulings are present. | Current working base (contains the locked exemplar) |

Consequences:

- Several of the most material findings below were **already found, audited,
  peer-reviewed, and RULED by the principal in lineage A** — and those
  rulings are simply absent from this base.  They are cross-referenced per
  finding as *prior art (ruled)* and are candidates for a governed **port**
  rather than re-litigation.
- The lineage-A IL/FRB audit was filed but never adjudicated: its findings
  are *prior art (open)*.
- Lineage A's v0.3 CPM engine and the larger system are out of scope here;
  only the LI-metric rulings/audits are treated as prior art.

**Ruling requested (Q-A below):** whether lineage-A's adjudicated LI rulings
are to be ported as-ruled (recommended; each still passes the FCBI rubric),
or re-adjudicated from scratch on this base.

---

## 1. Method

Each metric was scored against the FCBI lesson rubric:

- **A — definition/basis:** A1 no masking sentinels / silent fallbacks;
  A2 expose the decomposition, never misrepresent a composite; A3 basis
  neutrality (calendar / LOE-summary / granularity); A4 requirement-induced
  vs execution change segmented.
- **B — population/governance/disclosure:** B1 precise population;
  B2 governance traced through the network + quarantine + coverage;
  B3 disclose, don't threshold; B4 stable reference basis across the series.
- **C — computation/robustness:** C1 correctness over performance (exact
  oracle equivalence); C2 sound bounds only; C3 never-raises + input
  hardening; C4 sensitivity sets for arbitrary constants; C5 integrity
  guards.
- **D — testing/governance process:** D1 audit-first probes with closed-form
  anchors; D2 non-circular tests; D3 seeded/deterministic corpora;
  D4 governance package; D5 record consistency.

Categories and severities follow the four prior audits (implementation
defect / specification gap / methodology decision / disclosure; severity =
operational consequence).  FCBI's literal shape is NOT forced onto metrics
it does not fit; the rubric is applied as principles.

**Scored-member blast radius.**  LI-02, LI-03, LI-05, LI-08, LI-09 (weight 2
each) and LI-06, LI-04 (weight 2) are scored Report Card members; LI-07 and
LI-10 are informational.  LI-01 remains provisional/ungraded (unchanged).

---

## 2. Shared v0.4 RF kernel (feeds LI-04 PCI, LI-05 RDI, LI-07 CDI, LI-09 BWI)

The legacy kernel (`kernel_weight` / `relative_float_map` /
`activity_weights` / `_build_kernel`, li_indices.py L77–143) still contains
the two anti-patterns FCBI v0.5 abolished, plus four governance gaps.
**Any change here moves all four consumers at once** (FCBI does NOT use it);
the standing constraint is: prefer new governed helpers over mutating the
shared ones, and never change `paths.float_paths` (it feeds tool-of-record
driving-path analytics outside the LI indices).

| # | Rubric | Severity | Finding (probe-confirmed) | Consumers hit |
|---|---|---|---|---|
| **K1** | A1 | **High** | **Own-total-float fallback is live.** An activity on no enumerated path is assigned its own TF as RF (probe: orphan task, no relationships at all → RF 4.0, weight 0.574). FCBI O1 abolished exactly this ("never own-float; unresolved → quarantine"). Off-path activities enter CDI's dwell set and RDI/BWI's near-critical band on a fallback basis with no disclosure or coverage figure. | PCI (indirect), RDI, CDI, BWI |
| **K2** | A1 | **High** | **w = 2^(−RF/λ) > 1 for negative float** (probe: RF −3 → 1.516; RF −10 → 4.0). The "over-critical premium" FCBI retired still prices PCI path shares and CDI dwell shares: a driver deepening 0 → −10 reads as PCI 0.556 → 0.802 — rising "concentration" that is purely the premium, not structure. Negative-float severity belongs beside the index (FCBI N/ΔN⁺ pattern), never inside the kernel. | PCI, CDI (weights); RDI/BWI unaffected (band-membership only) |
| **K3** | A3 | **High** | **LOE/summary contaminates the kernel basis.** LOE nodes participate in the v0.4 path walk and their float can SET a path's `rel_float_days` (probe: LOE at TF −2 feeding the driver → path enumerates as [L, X, T] with margin −2.0, and the LOE earns its own RF map entry). `FloatPath.rel_float_hours` (discrete-only) exists — built for FCBI — but the v0.4 kernel still reads the LOE-inclusive `rel_float_days`. *Prior art (ruled):* lineage-A C1 (v0.4.2) + mixed-path neutralization (v0.4.3) ruled LOE out of the LI kernel family-wide. | PCI, CDI directly; RDI/BWI via band membership |
| **K4** | C4 | Medium | **λ un-governed.** PCI at λ=1/5/50 reads 0.601/0.230/0.200 on one fixed network (probe) — the scored two-sided PCI anchors [0.05, 0.15, 0.35, 0.6] grade a number that is a free function of λ, with no sensitivity set (FCBI Q2 requires {3,5,10}) and no bound (FCBI caps λ ≤ 10; the kernel accepts any positive finite λ and **silently substitutes the default** on invalid input — an A1-adjacent silent fallback, disclosed only in a code comment). | PCI, CDI |
| **K5** | C2/A3 | Medium | **KERNEL_PATHS_N = 10 truncation with no convergence or disclosure.** PCI is a Herfindahl over at most 10 shares, so PCI ≥ 0.1 by construction whenever 10 paths enumerate — the scorecard's "too diffuse" left arm (anchors below 0.1) is partly unreachable dead range, and the top-10 cutoff is exactly the "raw top-N with no proven bound" that FCBI O7.3 replaced with a sound frontier. No `depth_capped`-style disclosure exists. | PCI (directly); CDI dwell membership (path members beyond rank 10 fall to the K1 fallback) |
| **K6** | C4 | Low-Med | **band_days = 10 un-governed** for CDI/RDI/BWI near-critical membership; no sensitivity set, no rationale recorded beyond the default constant. | CDI, RDI, BWI |

**Recommended action (kernel cluster, decided as one unit — Q-B):** build a
**new governed LI kernel** (nonnegative distance to a stated reference, no
own-float fallback — unresolved is unresolved, w ∈ (0, 1], LOE-free margins
via the existing discrete-only path fields, truncation disclosed), adopt it
per-metric under per-metric rulings, and leave `kernel_weight` /
`relative_float_map` byte-identical for any legacy caller until retired.
Alternative: keep the v0.4 kernel and disclose K1–K6 per output
(disclosure-only path; numbers stay put).  This is the principal's call —
it is number-changing for up to four metrics at once.

---

## 3. Per-metric findings

### LI-02 LHL — Logic Half-Life (scored, weight 2; number-changing)

Does not touch the kernel.  *Prior art (ruled): the ENTIRE lineage-A LHL
audit (docs/audit/LHL_audit_2026-07-09.md on the lineage-A branch) was
adjudicated 2026-07-10 — all 12 rulings adopted and implemented there as
v0.4.5 with 21 tests.  All 12 defects/decisions are present in this base;
every one below reproduces.*

| # | Rubric | Sev | Category | Current behavior (probe) | Action |
|---|---|---|---|---|---|
| LHL-L1 | A1/D5 | **High** | Impl. defect (scoring) | `_li02_score` grants 100 when the **censored** fraction < 10%; the published rationale says 100 when **fewer than 10% died**. Probe: frozen network (0 deaths) scores **70**; the 100 branch is unreachable for stable networks. | Port lineage-A L1 (`deaths_pass_threshold`) |
| LHL-L10 | A1 | **High** | Impl. defect (scoring) | Median reached in update units but months basis unavailable → falls into the censoring branch. Probe: 19/20 ties die with missing data dates → **score 100** (via L1 inversion); identical churn with data dates → 0. | Port lineage-A L10 (ungradeable, with reason) |
| LHL-L2/L7 | A1 | Med-High | Impl. defect (degenerate bound) | Median-not-reached falls back to the **last event time**; deaths are dated at **last-seen**, so a tie deleted in its first window is a 0-duration event. Probe: first-window deletion → "median 0.0 months, reached=True". | Port lineage-A L2 (longest-follow-up lower bound; suppress ratio when unreached) + L7 (midpoint death dating) |
| LHL-L5 | A3 | Medium | Methodology | Update-count KM × one global mean interval (probe: 7 d and 105 d windows averaged to 56 d — one months figure for two very different real durations). | Port lineage-A L5 (per-instance calendar-day lifespans) |
| LHL-L9 | C3 | Medium | Impl. defect (validation) | Out-of-order data dates → **median −0.97 months**, silently (probe). | Port lineage-A L9 (withhold months + disclose) |
| LHL-L4 | B1 | Medium | Methodology (ruled) | Completed-work ties are immortal (probe: 6 ties on completed work flip a reached ~1-month median to "not reached"); LOE-attached ties count. | Port lineage-A L4a (LOE ties out) + L4b (censor at completion) |
| LHL-L6 | B3 | Low-Med | Impl. defect (misreport) | With exactly 2 schedules the requested first-pair exclusion silently cannot apply while the result still reports `exclude_first_pair=True` (probe). | Port lineage-A L6 (effective-exclusion reporting) |
| LHL-L3/L8/X1/X2 | B1/B3 | Low-Med | Disclosure / ruled conventions | Code keying (ruled AFFIRMED + disclosed), birth-only on/off split with silent drops, no standing disclosures, duplicate-tie collapse. | Port lineage-A L3/L8/X1/X2 |
| LHL-N1 *(new)* | A1/O4 | Low | Disclosure | Lag state is keyed on `round(lag_hours, 3)` — no Tier-1-style hour tolerance; exporter lag jitter ≥ 0.001 h reads as death+rebirth. Not covered by lineage A. *Code-read.* | Disclose or adopt a Tier-1 hour tolerance (O4 analogue) — needs a ruling |

**Classification: number-changing** (scoring fixes + basis changes; scored
member).  Cleanest port target — the whole adjudicated package exists.

### LI-03 FRB — Forecast Reliability Band (scored, weight 2; number-changing at the score surface)

No kernel.  *Prior art (open): lineage-A IL/FRB audit findings FR1–FR4,
filed 2026-07-10, never ruled.*

| # | Rubric | Sev | Category | Current behavior (probe) | Action |
|---|---|---|---|---|---|
| FRB-FR1 | A1/D5 | **High** | Impl. defect (wiring) | Wiring reads `b.bias`/`b.p10`/`b.p90`; the dataclass fields are `bias_days`/`p10_days`/`p90_days` — every getattr returns 0. Probe: metric layer computes bucket n=6, bias +6.5, P10 −3.5, P90 +32.0 (width 35.5 wd); **wired LI-03 value = 0 → score 100 on every series**, findings text asserts "bias +0.0d, band P10 +0.0d .. P90 +0.0d". | Fix field names + pin through `li_series_results` → `score_series` (the metric layer was never broken — the regression must be non-circular through the wiring, D2) |
| FRB-FR2 | B1 | Medium | Spec gap + methodology | Overdue forecasts (horizon ≤ 0 — precisely where credibility dies) fall out of every bucket. Probe: 3 observations, Σ bucket n = 1. | Ruling: overdue bucket (rec) / clamp / keep-disclosed |
| FRB-FR3 | B3 | Medium | Methodology | `frb_apply_forward` refuses to band on n < 5, but the SCORE uses the largest bucket at any n (n=1 → width 0 → 100). | Ruling: n ≥ 5 floor → ungradeable-with-reason below (rec) |
| FRB-FR4 | B3/D1 | Low-Med | Disclosure | Autocorrelated observations (one activity re-forecast each update, all resolved by one actual — *code-read*), fixed Mon–Fri 8 h error calendar, code-keyed actual matching, "largest bucket" scored basis — none disclosed on `FRBResult`. | Standing disclosures block |

**Classification:** FR1 is a pure defect but **check-affecting** (LI-03
stops being constant-100); FR2/FR3 are number-changing methodology rulings.

### LI-04 PCI — Path Concentration Index (scored, weight 2; kernel cluster)

Kernel consumer (path set + weights).  Findings K1–K5 apply as tabulated in
§2; PCI-specific notes:

| # | Rubric | Sev | Category | Current behavior (probe) | Action |
|---|---|---|---|---|---|
| PCI-1 | A1 | High | Methodology (kernel) | Negative-float premium turns deepening slip into rising "concentration" (K2 probe: 0.556 → 0.802 with structure unchanged). | Kernel-cluster ruling (Q-B) |
| PCI-2 | A3 | High | Methodology (kernel) | LOE-set path margins (K3); LOE-only feeder branches count as paths on this base's walk. *Prior art (ruled): lineage-A C1 — "a single-threaded schedule with an LOE feeder reads 1.0, not 0.5".* | Kernel-cluster ruling |
| PCI-3 | C4/C2 | Medium | Methodology | λ-dependence with fixed scored anchors and no sensitivity set (K4 probe); Herfindahl floor 1/10 makes the "too diffuse" scoring arm partly unreachable (K5). | λ sensitivity set + truncation disclosure; re-examine the two-sided anchors when the basis settles |
| PCI-4 | B3 | Low | Disclosure | No standing disclosures (population = top-10 float paths; within-network trend only; Herfindahl of weight shares is granularity-dependent). | Disclosures block |

**Classification: number-changing IF the kernel ruling adopts a new basis;
disclosure-only otherwise** (plus the W1 wiring crash fix, §4).

### LI-05 RDI — Recovery Debt Index (scored, weight 2; kernel cluster, band-membership only)

| # | Rubric | Sev | Category | Current behavior (probe) | Action |
|---|---|---|---|---|---|
| RDI-1 | A1 | **High** | Impl. defect (sentinel) | An unusable series (no data dates / no finish span) returns `rdi_days = 0.0` **with** a reason string, and the wiring scores the 0.0 → **LI-05 = 100 "no recovery debt" on a series where the metric could not be computed**. Probe-confirmed. Exactly the "undefined → plausible-looking number" pattern A1 forbids (FCBI: NOT EVALUATED). Same class, lower blast radius: a window whose required pace is None accrues exactly 0 silently (*code-read*). | Undefined → `None` value + NOT EVALUATED reason through the wiring (check-affecting: such series stop scoring 100) — Q-C |
| RDI-2 | B1 | Med-High | Impl. gap (population) *(new — not in lineage A's list)* | Demonstrated pace counts a completion only if the **later** update's RF map resolves it into the band. A completed activity whose TF the exporter nulls at completion and that sits on no enumerated path **vanishes from demonstrated pace** (probe: completed near-critical task → demonstrated 0.0 — phantom debt of 2.3 d accrued in a window where the work WAS done). Representation-dependent under-count → over-accrual. | Rule the demonstrated-population basis (e.g. band membership at the EARLIER update, where the FCBI remaining-work-population lesson points) + data-quality disclosure |
| RDI-3 | B1 | Medium | Methodology (ruled) | Accrues against the running **max** demonstrated pace only. *Prior art (ruled): lineage-A R2 — P50 accrual with max as the disclosed optimistic bound.* | Port R2 |
| RDI-4 | A2 | Medium | Methodology (ruled) | Demonstrated pace = planned scope retired (probe/code-read); overrun invisible. *Prior art (ruled): lineage-A R1 — planned-scope basis AFFIRMED on dimensional grounds + companion duration-overrun ratio as a disclosed diagnostic.* The companion ratio does not exist on this base. | Port R1 (companion ratio + disclosures) |
| RDI-5 | A1 (K1) | Medium | Methodology (kernel) | Near-critical band membership includes own-TF-fallback activities (K1). | Kernel-cluster ruling |
| RDI-6 | B3 | Low | Disclosure | Mixed temporal sampling (required at window start vs demonstrated through window end — lineage-A R3), remaining-duration/finish-date data dependence (X1). | Disclosures |

**Classification: number-changing** (RDI-1 fix, R2 port, RDI-2 ruling).

### LI-06 BDI — Baseline Dilution Index (scored, weight 2; no kernel)

| # | Rubric | Sev | Category | Current behavior (probe) | Action |
|---|---|---|---|---|---|
| BDI-1 | A1 | **High** | Impl. defect (sentinel) | All-milestone driving path → `bdi_pct = 0.0` with a reason — the "perfect baseline fidelity" reading on an undefined basis, scored 100. Probe-confirmed. | Undefined → None + NOT EVALUATED (check-affecting) — Q-C |
| BDI-2 | A3/A4 | Med-High | Methodology | Step length = remaining-if->0-else-original: an in-progress original step shrinks as it burns down while added steps hold full length, so the "dilution" share **rises with mere progress** (execution and revision conflated — the exact A4 distinction FCBI segments). *Code-read; probe additionally showed the driving-path walk dropping the original activity entirely on a float tie.* | Ruling: fixed length basis (e.g. original/current-planned duration for all steps) or disclose the drift |
| BDI-3 | B1 | Medium | Methodology (deferred in lineage A) | LOE steps on the tool-of-record driving path count toward BDI length; the lineage-A family table flagged BDI's LOE question as "warrants a separate ruling" — never ruled. | Ruling |
| BDI-4 | B4 | Medium | Disclosure / methodology | "Baseline" = `schedules[0]` unconditionally (a mid-series submission window silently redefines the contract baseline); target auto-resolved per latest schedule with no cross-series stability rule (FCBI W4-06 lesson). | Disclose + optional explicit baseline/target parameters |
| BDI-5 | C3/D3 | Low | Hardening | First-appeared attribution couples to the diff's `lc.detail.split()[0]` string format (silently breaks if the diff wording changes); "NOT FOUND — REVIEW" is a good non-fabricating default (positive finding). | Harden + regression-lock the coupling |

**Classification:** BDI-1 fix is check-affecting; BDI-2/3 rulings are
number-changing if adopted.

### LI-07 CDI — Criticality Dwell Index (informational; kernel cluster)

| # | Rubric | Sev | Category | Current behavior (probe) | Action |
|---|---|---|---|---|---|
| CDI-1 | A3/B1 | **High** (forensic, unscored) | Impl. defect / cross-index inconsistency | Leaderboard admits **LOE (via kernel), zero-duration milestones (the target itself earns dwell), and off-path activities via the K1 fallback** — probe: X, T, L, ORPH all on the "cast of characters", ORPH at 16% dwell on a fallback basis. *Prior art (ruled): lineage-A C1 excluded LOE kernel-wide.* | Port C1; rule milestone + fallback membership (kernel cluster) |
| CDI-2 | A1 (K2) | Medium | Methodology (kernel) | Dwell share priced by the negative-float premium (probe: TF −10 activity carries w=4.0 → 44% dwell vs 11% for the on-time driver) — dwell is supposed to measure time-near-critical, not depth-of-negative. | Kernel-cluster ruling |
| CDI-3 | B1 | Low-Med | Disclosure (ruled) | Completed activities retained (retrospective dwell) — intentional but undocumented at CDI. *Prior art (ruled): lineage-A C2 (doc-only).* | Port C2 |
| CDI-4 | D3 | Low | Hardening | Leaderboard sort has no deterministic tie-break (dwell-share ties order by dict insertion). | Add `(−share, code)` ordering |
| CDI-5 | C4 | Low | Disclosure | λ and band_days un-governed (K4/K6). | Sensitivity/disclosure |

**Classification: number-changing** (population change) but unscored — no
grade blast radius; forensic-output blast radius is high (it names names).

### LI-08 IL — Intervention Latency (scored, weight 2; no kernel)

*Prior art (open): lineage-A IL/FRB audit IL1–IL6, never ruled.  All
reproduce on this base.*

| # | Rubric | Sev | Category | Current behavior (probe) | Action |
|---|---|---|---|---|---|
| IL-1 | A1/D5 | **High** | Impl. defect + methodology | Minimum observable latency is 1 (responses scan starts at the NEXT changeset) → the published "0 updates → 100" anchor is unreachable (ceiling 85), and a mitigation landing in the SAME window as the emergence reads **unresolved**. Probe: same-window duration-halving scores **20 ("did not act")**; the identical edit a month later scores **85**. The fastest responder gets the worst grade. | Ruling (lineage-A IL1 option A recommended: scan the emergence window, latency 0, with the adjacency-not-sequence disclosure) |
| IL-2 | B1/B2 | Med-High | Methodology | Median over resolved events only. Probe: 1 responded + 5 ignored chains → median 1, score 85 — identical to a perfect responder; "did not act" fires only when NOTHING ever resolved. | Ruling (rec: KM right-censoring — the estimator already sits in the same module) |
| IL-3 | B1 | Medium | Methodology | Sole emergence in the final window → **20**, though no response opportunity ever existed (probe). Right-censoring, unhandled. | Dissolves under IL-2 KM option |
| IL-4 | B1/A3 | Medium | Methodology (explicitly deferred by the ruled family audit) | LOE-only chain drives LI-08 to 20 (probe); completed-activity emergence is exporter-dependent. | Ruling: exclude LOE from the emergence set; rule completed handling |
| IL-5 | C3 | Low-Med | Impl. defect (validation) | Out-of-order data dates → negative `il_days` silently (*code-read; same class as LHL-L9*). | L9 convention |
| IL-6 | B3 | Low-Med | Disclosure | "Response" = any touching edit (deliberately not "effective mitigation"); duration-decrease detector coupled to the diff's `"###h"` string; emergence = TF crossing 0 between two non-null observations (born-negative activities are not emergences). Undisclosed. | Disclosures block |

**Classification: number-changing** (scored; IL-1/2/3/4 all move scores).

### LI-09 BWI — Bow-Wave Index (scored, weight 2; kernel cluster, band-membership only)

| # | Rubric | Sev | Category | Current behavior (probe) | Action |
|---|---|---|---|---|---|
| BWI-1 | B4/A4 | **High** | Methodology (ruled) | Density denominator = working days to the milestone's **current forecast finish**: a 3-month slip with identical work reads BWI 1.0 → **0.714 ("relief")** — the signal inverts on exactly the aggravating case. Probe-confirmed. *Prior art (ruled): lineage-A B1 — fixed reference horizon (constrained/promised date, else baseline finish, else first-update forecast), demo BWI 1.0/0.833/0.661.* | Port B1 |
| BWI-2 | B4 | Medium | Disclosure/reproducibility (ruled) | Target held by CODE from the first update; a re-coded milestone (same UID) silently yields density None thereafter — probe: second row (None, None), **no reason anywhere**. *Prior art (ruled): lineage-A B2 — pin by UID, locate UID-then-code.* Also: no FCBI-style stable-target validation, and the no-milestone fallback picks the latest-finishing TASK undisclosed. | Port B2 + disclose fallback |
| BWI-3 | A1 (K1) | Medium | Methodology (kernel) | Band membership includes K1 fallback activities. | Kernel-cluster ruling |
| BWI-4 | B3 | Low | Disclosure | Projected-break comparison (density vs demonstrated pace) inherits RDI's demonstrated-population fragility (RDI-2); band_days un-governed (K6); no disclosures block. | Disclose; inherits RDI-2 ruling |

**Classification: number-changing** (B1 port; scored member).

### LI-10 MML — Measured-Mile Locator (informational; no kernel)

| # | Rubric | Sev | Category | Current behavior (probe) | Action |
|---|---|---|---|---|---|
| MML-1 | A2/A3 | **High** (forensic, unscored) | Impl. defect (basis mixing) | Per-window basis auto-selects **resource units/hour** when resource actuals moved, else **activity-days/day** — and clean/impacted/ratio compare across bases. Probe: clean = resource window (1.25 units/h), impacted = fallback window (0.5 act-d/d), **ratio 0.4 — a dimensionally meaningless "disruption contrast"** presented per trade. | Never cross bases: segregate per-basis window sets (ratio within one basis only), disclose basis per window — ruling on the preferred convention |
| MML-2 | B1 | Medium | Spec gap | Spec §10.5 defines the clean mile as "the cleanest **sustained** period — **stable**, best productivity, no mapped events"; implementation takes the single max-productivity window (a one-window spike — ramp-up/closeout artifact — becomes the measured mile). Dispersion is only used for the no-clean-mile flag (0.15 spread constant, un-governed — C4). | Ruling: sustained-window definition (or disclose single-window basis); govern the 0.15 constant |
| MML-3 | B1 | Medium | Impl. gap | The `events` parameter (mapped-event exclusion — half the spec's clean-mile definition) is **never wired**: `li_wiring` calls `run_li_record(sa)` without events, so `excluded_by_event` is always False in the pipeline. *Code-read.* | Wire the event overlay (D6 mapper exists) or disclose |
| MML-4 | B1/B3 | Low-Med | Disclosure | No minimum window count / n_activities floor for a usable contrast (FR3 analogue); added-in-window activities' actuals invisible (code-keyed earlier-match); negative resource corrections silently flip the basis; windows = update cadence (cadence-dependent). | Disclosures + optional floor |
| MML-5 | B3 | Low | Positive + gap | "Preliminary — expert confirms period selection" caption exists (good B3 practice); but `no_clean_mile` conflates two different states (tight spread vs all-windows-evented) in one flag. | Split/label the flag reasons |

**Classification: number-changing** (MML-1 basis segregation changes ratios)
but unscored.

---

## 4. Cross-cutting wiring/robustness (affects all ten)

| # | Rubric | Sev | Category | Current behavior (probe) | Action |
|---|---|---|---|---|---|
| W1 | C3 | **High** (blast radius) | Impl. defect | `li_wiring` formats Optional values un-guarded at TWO sites — LI-04 (`f"PCI {val:.3f}"` on a None per-update) and LI-09 (`f"density {row.density:.2f}"` on a None density row). Either raises TypeError; `trend/series.py` catches it blanket-style and **silently drops ALL TEN LI indices** ("LI proprietary indices skipped" warning) — six scored members go N/A at once. Both sites probe-confirmed live. *Prior art (open): lineage-A W1 (found only the PCI site).* | None-guards at every format site + per-index isolation (one metric's failure degrades that metric alone, with a reason — never-raises discipline C3 applied to the wiring layer) |
| W2 | D5 | Medium | Impl. defect (narrative) | FR1-class wrong-field getattr defaults in three more blocks: LI-05 reads `row.required`/`row.demonstrated` (fields: `required_pace`/`demonstrated_pace`) → findings read "required 0.00 vs demonstrated nan"; LI-07 reads `e.share` (field: `dwell_share`) → "dwell share 0.0%" for every entry; LI-10 reads `row.basis` on `MMLWbsResult` (basis lives on the window rows) → always "?". Probe-confirmed (LI-05, LI-07). The exhibits fabricate zeros while the result objects hold real numbers. | Fix field reads; add a wiring-layer regression that asserts NO finding text contains the default-masked patterns (D2: through `li_series_results`, not the metric layer) |
| W3 | D1/D3 | Medium | Test gap | LI-02..LI-10 have thin metric-layer tests only: no closed-form probe anchors (FCBI §P pattern), nothing through the wiring (why FR1/W1/W2 survived), no determinism/PYTHONHASHSEED corpus, no seeded topology corpus for the kernel path set. | Per-metric probe sets built from §3's probes as the anchor tests of each governed revision (D1), wired-path regressions (D2), sorted-order determinism checks (D3) |

---

## 5. Classification summary

| Metric | Scored | Kernel cluster | Number-changing findings | Disclosure/hardening-only | Prior art |
|---|---|---|---|---|---|
| LI-02 LHL | yes (2) | no | L1, L10, L2/L7, L5, L9, L4 | L3/L6/L8/X1/X2, N1 | **ruled** (v0.4.5, complete package) |
| LI-03 FRB | yes (2) | no | FR1 (score surface), FR2, FR3 | FR4 | open (audit filed) |
| LI-04 PCI | yes (2) | **YES** | K1–K3 (if basis ruled), anchors | K4/K5 disclosures, W1 | C1 ruled; rest new |
| LI-05 RDI | yes (2) | **YES** (band) | RDI-1, RDI-2, R2 | RDI-6, R1-companion, X1 | R1/R2 **ruled** |
| LI-06 BDI | yes (2) | no | BDI-1, BDI-2/3 (if ruled) | BDI-4/5 | LOE deferred (flagged, unruled) |
| LI-07 CDI | no | **YES** | CDI-1, CDI-2 (population/basis) | CDI-3/4/5 | C1/C2 **ruled** |
| LI-08 IL | yes (2) | no | IL-1, IL-2, IL-3, IL-4 | IL-5/6 | open (audit filed) |
| LI-09 BWI | yes (2) | **YES** (band) | BWI-1 | BWI-2/3/4 | B1/B2 **ruled** |
| LI-10 MML | no | no | MML-1 (ratio basis) | MML-2/3/4/5 | none |
| wiring | — | — | FR1/W1 (score/N-A surface) | W2/W3 | W1 partially known |

---

## 6. Recommended sequencing

The shared-kernel cluster (PCI/RDI/CDI/BWI) moves as ONE unit — a kernel
decision silently reprices all four, so their basis ruling is taken together
even though each gets its own governed revision package.

1. **Wave 0 — wiring defect batch (no methodology content):** FR1 field
   names, W1 None-guards + per-index isolation, W2 field reads; regression
   tests through the wiring (D2).  Check-affecting only in that LI-03 stops
   being constant-100 and blanked series stop silently losing all LI rows —
   CHANGELOG labels this explicitly.
2. **Wave 1 — port the lineage-A adjudicated rulings** (subject to Q-A):
   LHL v0.4.5 (12 rulings), BWI B1+B2, RDI R1-companion+R2, kernel-C1 LOE
   exclusion + mixed-path neutralization, CDI C2.  Each ported with the full
   D4 package on THIS base and its own adversarial review wave; recorded as
   "ported ruling, originally adjudicated 2026-07-08..10", with any
   FCBI-rubric deltas called out rather than silently blended.
3. **Wave 2 — IL + FRB open rulings** (scored members with perverse
   behaviors; the lineage-A audit already frames the options — Alex rules,
   then one governed revision per metric).
4. **Wave 3 — kernel-cluster basis ruling** (Q-B) and, under it, the
   PCI/CDI/RDI/BWI revisions (population, premium, fallback, λ/band
   governance, truncation disclosure).  Deepest work; benefits from waves
   0–2 test scaffolding.
5. **Wave 4 — BDI + MML** (sentinel fixes under Q-C, basis rulings, event
   wiring, disclosures).
6. Report Card anchor recalibration stays a separate, explicitly-flagged
   step wherever a ruling moves a scored number (LI-01 precedent: mark
   provisional/ungraded rather than keep stale anchors).

Every wave: suite green, CHANGELOG check-affecting labels, rulings recorded
under docs/rulings/, reproduce-before-reporting peer review until clean.

---

## 7. Open methodology questions for the principal

- **Q-A (gates wave 1).** Lineage reconciliation: port lineage-A's
  adjudicated LI rulings as-ruled (recommended), or re-adjudicate each on
  this base?  (Either way the lineage split itself should be recorded; the
  lineage-A engine/other work is a separate decision not needed for LI.)
- **Q-B (gates wave 3).** Kernel cluster: new governed LI kernel
  (nonnegative distance, no own-float fallback → unresolved handling,
  w ∈ (0,1], discrete-only margins, disclosed truncation) adopted per-metric
  — or keep the v0.4 kernel and disclose K1–K6?  If the new kernel: does
  negative-float severity move beside PCI/CDI as an N/ΔN⁺-style strip
  (FCBI pattern)?
- **Q-C.** Undefined→explicit conversions (RDI-1, BDI-1: value 0.0 → NOT
  EVALUATED): approve as a defect-class batch?  Both currently score 100 on
  uncomputable series; after the fix those series become ungraded.
- **Q-D.** IL rulings 1–6 (the lineage-A audit's options; recommendations:
  IL1-A same-window latency 0, IL2-A KM censoring subsuming IL3, IL4 LOE out
  + completed ruled, IL5 L9-convention).
- **Q-E.** FRB rulings (FR2 overdue bucket recommended; FR3 n ≥ 5 floor
  recommended — note it moves thin-record series from 100 to ungraded).
- **Q-F.** MML: per-basis ratio segregation (never cross-basis); clean-mile
  = sustained-stable period per spec vs disclosed single-window max; wire
  the event overlay?
- **Q-G.** BDI: LOE steps on the driving path; step-length basis (fixed
  basis vs disclosed remaining-else-original drift); explicit baseline /
  target parameters.
- **Q-H.** Constant governance: λ sensitivity sets for PCI/CDI (FCBI Q2
  pattern), band_days for CDI/RDI/BWI, MML's 0.15 spread constant —
  sensitivity sets / recorded conventions, not point claims.

No behavior was changed in this pass.
