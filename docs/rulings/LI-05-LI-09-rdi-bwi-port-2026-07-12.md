# LI-05 RDI / LI-09 BWI — v0.4.3/v0.4.4 rulings PORTED (governed revision)

**Status:** accepted · **Date:** 2026-07-12 · **Principal:** Alex Bachowski —
original adjudications 2026-07-09 on the lineage-A branch (as-audited record
imported at docs/audit/RDI_BWI_CDI_audit_2026-07-08.md) + the port ruling
(Q-A of the LI-02..LI-10 audit triage: "port as-ruled").
**Classification: number-changing** for LI-05 and LI-09 (both scored,
weight 2) on real data; the pinned demo letters hold.

## Ported rulings

- **R2 (LI-05, v0.4.3): P50 accrual anchor.**  Debt accrues when required
  pace exceeds the running **P50 (median)** demonstrated pace — the
  sustainable pace — with the running max retained and reported as the
  optimistic bound.  The prior max-only anchor under-accrued (debt only when
  required exceeded the single best window ever).
- **R1 (LI-05, v0.4.4): planned-scope demonstrated basis AFFIRMED +
  companion overrun ratio.**  Demonstrated pace remains planned
  near-critical scope actually retired (completions, at original duration)
  per calendar working-day — the only basis commensurable with required
  pace; the earlier "actual elapsed" direction was reversed on dimensional
  grounds (elapsed denominators are concurrency-non-additive: five parallel
  on-pace activities would read as phantom recovery debt; elapsed numerators
  reward overruns).  The overrun signal ships as the **companion
  duration-overrun ratio** (Σ actual elapsed ÷ Σ planned of the same
  completions) per window (`RdiRow.overrun_ratio`) and per series
  (`RdiResult.overrun_ratio`) — a disclosed efficiency diagnostic, never an
  accrual input.  Completions lacking an actual start are omitted from the
  ratio and surfaced as a DATA QUALITY disclosure.
- **B1 (LI-09, v0.4.3): fixed reference horizon.**  BWI's density
  denominator is a constant — working days from the first update's data date
  to the target's constrained (promised) date, else baseline finish, else
  first-update forecast finish — held across updates.  A slipping milestone
  with unchanged work reads BWI = 1.0 (the prior moving-forecast denominator
  read the slip as relief — the exact aggravating case BWI exists to catch;
  reproduced on this base as audit probe BWI-1: 1.0 → 0.714).
- **B2 (LI-09, v0.4.2): UID-pinned target.**  The target milestone is pinned
  by persistent UID from the first update and located UID-then-code in later
  updates, surviving re-coding/renaming (probe BWI-2: the pre-port density
  silently dropped to None).
- **X1 (both, v0.4.2): standing disclosures** — LOE exclusion (both metrics'
  own-loop guards), basis statements, and DATA QUALITY notes for missing
  project finish dates / actual starts / unusable target finishes.

## Interaction with this base's own rulings

- The Wave-0.5 **NOT EVALUATED sentinel** (docs/rulings/LI-05-LI-06-not-
  evaluated-2026-07-12.md) supersedes lineage-A's `rdi_days = 0.0` on the
  all-required-None branch: the port keeps `rdi_days = None` there and adds
  the companion ratio + disclosures to that result.
- The **kernel C1 LOE exclusion and mixed-path neutralization** (v0.4.2/3)
  are NOT in this package — they move PCI/CDI (and band membership) as a
  unit and land as Wave 1c.  The LI-05/LI-09 matrix wording here therefore
  omits the kernel-neutralization sentence until 1c lands.
- Audit finding **RDI-2** (completed activities whose float the exporter
  nulls fall out of the demonstrated-pace population) is NOT resolved by
  this port — it was not part of the lineage-A rulings and travels with the
  Wave-3 kernel-cluster revision.  The R2 regression fixture documents the
  dependency explicitly.

## Port fidelity / verification

- Implementations taken from the lineage-A head (`_median`,
  `_overrun_series`, `_rdi_disclosures`, `_bwi_fixed_horizon`,
  `_bwi_disclosures`, the `_rdi` P50 loop, the `_bwi` B1/B2 body) and
  re-based; FCBI untouched; `float_paths` untouched.
- Closed-form anchors: the lineage-A R1 concurrency case reproduces exactly
  (five parallel 5-day completions over a 10-wd window → demonstrated 2.5,
  companion ratio 2.0); P50-vs-max discrimination pinned (required 1.5 vs
  P50 1.0 / max 2.0 → 5.0 days accrue); B1 slip → 1.0/1.0; B2 re-code
  survives by UID.  6 new regression tests in tests/test_li_indices.py;
  1 Wave-0 W1 test re-fixtured (its None-density row was produced by a
  re-code, which B2 now survives — the intended improvement).
- Wave-0 note: the LI-05 exhibit line reads the ported fields directly
  (required_pace / demonstrated_pace / overrun via result objects); no
  wiring change was needed beyond Wave 0.
- Suite: **267 passed, 1 skipped**; pinned demo letters hold.

## FCBI-rubric check of the ported package

A1 (no fabricated numbers — sentinel retained; overrun None-not-guessed on
missing actual starts) ✓ · A2 (composite exposed: P50 anchor + max bound +
companion ratio all visible, never blended) ✓ · A3 (LOE own-loop exclusion
disclosed; kernel-level neutrality deferred to 1c, disclosed here) ✓ ·
B1 (population statements in disclosures) ✓ · B3 (disclose, don't
threshold) ✓ · B4 (stable reference basis: B1 fixed horizon + B2 UID pinning
are exactly this lesson) ✓ · C3 (never raises; degraded reasons) ✓ ·
C4 (band_days remains un-governed — flagged as K6, Wave 3) · D1–D4 ✓.
