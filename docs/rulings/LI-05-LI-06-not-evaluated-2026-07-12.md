# LI-05 (RDI) / LI-06 (BDI) — NOT EVALUATED sentinels (defect-class batch)

**Status:** accepted · **Date:** 2026-07-12 · **Principal:** Alex Bachowski
(triage round 1 on docs/audit/LI-02-10_audit_matrix_2026-07-12.md, question
Q-C — "Approve batch") · **Classification: number-changing at the Report
Card surface** (GOVERNANCE.md §1): series that previously scored 100 on an
uncomputable basis become **ungraded**.  The accrual/attribution mathematics
of both metrics are UNCHANGED on every computable series.

## Ruling

Undefined must be explicit, never a plausible-looking number (FCBI v0.5
rubric A1 — the same rule that abolished FCBI's D=0 sentinel and the RF
own-float fallback):

1. **RDI (audit RDI-1).**  When no update yields a usable required pace (no
   data date → forecast finish span anywhere in the series), recovery debt
   is **undefined**: `RdiResult.rdi_days = None` with reason
   `NOT EVALUATED — … recovery debt is undefined, not zero`.  Previously the
   result carried `rdi_days = 0.0` beside the reason, the wiring scored the
   0.0, and the Report Card read "no recovery debt" = 100 on a series the
   metric could not evaluate.  `rdi_days` is now `Optional[float]`
   (`None` ⇒ NOT EVALUATED); the fewer-than-two-updates case is likewise
   `None`, no longer a default 0.0.
2. **BDI (audit BDI-1).**  A driving path with zero total working-day length
   (all milestones) has no length basis to attribute: `bdi_pct = None` with
   reason `NOT EVALUATED — … dilution is undefined, not 0%`.  Previously it
   returned 0.0% — the best-possible "fully baseline-original" reading — and
   scored 100.

No new thresholds are introduced (rubric B3): the change only converts
fabricated best-case values into explicit non-evaluation.

## Surfaces

- `analytics/li_indices.py::_rdi` / `RdiResult.rdi_days` (Optional);
  `analytics/li_record.py::baseline_dilution_index`.
- Wiring: unchanged — `li_series_results` passes the value through; a None
  value reaches the Report Card as an ungraded member via the existing
  member gate (`scorecard.py` `_series_member`: `result.value is None` →
  score None, weight redistributes per the engine's normal N/A handling).
- matrix.yaml LI-05 / LI-06 formula fields now state the NOT EVALUATED
  convention; ANALYTICS_PROPOSAL §9.5 / §10.1 carry the same convention
  note.

## Audited before → after (probe set of the LI-02..LI-10 audit)

| Probe | Before (v0.2.0 basis) | After |
|---|---|---|
| RDI on a series with no data dates / finish span | `rdi_days = 0.0` + reason; wired LI-05 value 0.0 → member score **100** | `rdi_days = None` + `NOT EVALUATED …`; wired LI-05 value None → member **ungraded** |
| BDI on an all-milestone driving path | `bdi_pct = 0.0` + reason; wired LI-06 value 0.0 → member score **100** | `bdi_pct = None` + `NOT EVALUATED …`; wired LI-06 value None → member **ungraded** |
| RDI/BDI on any computable series | unchanged | unchanged (regression-locked by the existing metric tests) |

## Tests

`tests/test_li_sentinels.py`: metric-layer NOT EVALUATED assertions for both
sentinels plus wired-value-None assertions through `li_series_results`
(non-circular, per the audit's D2 rule), and computable-series guards that
pin the numbers that must NOT move.

## Scope note

The partial case — individual windows whose required pace is None
contributing zero accrual inside an otherwise-computable RDI series — is
NOT covered by this ruling; it is audit finding RDI-6 (disclosure) and
travels with the Wave-3 RDI revision.
