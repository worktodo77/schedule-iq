# LI kernel constants — governance (Wave-4 ruling Q-H: sensitivity sets)

**Status:** accepted · **Date:** 2026-07-12 · **Principal:** Alex Bachowski
(Wave-4 triage on the LI-02..LI-10 audit, question Q-H — "Sensitivity sets +
conventions") · **Classification: additive** (no canonical number changes;
new diagnostics + recorded conventions per rubric C4).

## Rulings

1. **λ sensitivity set for PCI/CDI** — `kernel_lambda_sensitivity(sa,
   lams=(3, 5, 10))` reports PCI (latest update) and CDI top-decile dwell
   per λ, the FCBI Q2 pattern.  The house default **λ = 5 working days is a
   professional convention, not a calibrated constant** (audit K4 probe: PCI
   0.601/0.230/0.200 at λ = 1/5/50 on one fixed network); contested/expert
   use shows the set.  The v0.4 kernel remains un-bounded above (any finite
   positive λ), unlike FCBI's convergence-referenced cap — that difference
   is documented at `run_li_indices`.
2. **Band sensitivity set for CDI/RDI/BWI** — `kernel_band_sensitivity(sa,
   bands=(5, 10, 20))` reports CDI top-decile, RDI recovery debt, and the
   latest BWI ratio per near-critical band.  **band_days = 10 is likewise a
   recorded convention** (audit K6).
3. **MML constants** — `MML_RUN_K = 2`, `MML_RUN_SPREAD = 25%`,
   `MML_TIGHT_SPREAD = 15%` recorded as conventions in the Wave-4b MML
   ruling (docs/rulings/LI-10-mml-v2-2026-07-12.md).
4. **KERNEL_PATHS_N = 10** recorded as a convention with the disclosed
   consequence that PCI's Herfindahl over at most 10 shares has floor 1/10 —
   the scored "too diffuse" anchor region below 0.1 is unreachable (audit
   K5).  **PCI's scored anchors are re-examined once the Wave-3 kernel basis
   settles**, per the ruling — not adjusted here.

## Scope note

These sets measure robustness of the CURRENT v0.4 kernel basis.  The Wave-3
new-kernel revision (triage ruling Q-B) will re-point them at the new basis;
the functions are additive diagnostics and carry over.

Tests: 2 regressions (λ-monotone PCI exposure on a staggered-float network;
band-set membership + never-raises on an empty series).
Suite: 293 passed, 1 skipped.
