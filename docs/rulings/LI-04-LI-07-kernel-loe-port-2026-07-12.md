# Shared LI kernel — C1 LOE exclusion + mixed-path neutralization PORTED
# (LI-04 PCI / LI-07 CDI directly; LI-05 RDI / LI-09 BWI band membership)

**Status:** accepted · **Date:** 2026-07-12 · **Principal:** Alex Bachowski —
original adjudications 2026-07-08/09 on the lineage-A branch (rulings C1/C2
of the RDI/BWI/CDI audit + the v0.4.3 mixed-path neutralization; as-audited
record at docs/audit/RDI_BWI_CDI_audit_2026-07-08.md, validation record at
docs/audit/v0.4.2_validation_2026-07-09.md) + the port ruling (Q-A: "port
as-ruled").  **Classification: number-changing** for PCI and CDI on any
series with near-critical LOE/summary activities, and for RDI/BWI band
membership where a mixed-path LOE previously dragged a discrete activity's
RF into the band.  **FCBI (LI-01, locked) is untouched** — it does not use
this kernel; the full FCBI anchor suite passes unchanged.

## Ported rulings

- **C1 — LOE exclusion at the shared kernel.**  LOE, WBS-summary, hammock,
  and other summary activities are not discrete executable work and carry no
  project criticality: `relative_float_map` gives them no RF entry (so no
  kernel weight, no CDI dwell, no RDI/BWI band membership via the map), and
  `_build_kernel` drops float paths with no discrete-work member, so a pure
  LOE/summary or bare-milestone chain cannot inflate PCI's path count (a
  single-threaded schedule with an LOE feeder reads 1.0).  Milestones are
  retained in the RF map (legitimate criticality references) but do not
  satisfy the discrete-work path test.
- **Mixed-path neutralization (v0.4.3).**  The LI kernel computes each kept
  path's relative float over its unique **discrete** members only
  (`_li_path_rel_float`), so an LOE that is the lowest-float member of a
  mixed path no longer drives the discrete members' RF.  Implemented as an
  LI-kernel-local layer reading `FloatPath.unique_uids` — an **additive**
  field populated by `_finalize_path`; the shared `float_paths()` /
  `iter_float_paths()` walk, ordering, `rel_float_days`, and
  `rel_float_hours` are all byte-identical (regression-pinned: the shared
  path still carries the LOE's −2.0 while the kernel RF reads 0.0).
- **C2 — CDI completed-retention documented.**  No behavioral change:
  completed activities are retained because CDI measures retrospective
  criticality-time; now stated at §10.2, the LI-07 matrix row, and a
  standing `CdiResult.disclosures` block.

## Explicitly NOT in this port (Wave-3 kernel-cluster scope, audit K1–K6)

- The **own-total-float fallback for off-path DISCRETE activities** remains
  (scope-locked by `test_kernel_own_float_fallback_still_live_for_discrete_offpath`
  — the pin fails when Wave 3 lands, flagging an actioned decision).
- The **negative-float w > 1 premium**, the un-governed λ/band constants,
  the top-10 truncation disclosure, and **PCI's kept-mixed-path Herfindahl
  weight residual** (PCI path weights still read the shared
  `rel_float_days`, as lineage A deliberately deferred and its validation
  record locked).  All await the principal-approved new governed LI kernel
  (triage ruling Q-B), Wave 3.

## Verification

- Full suite **272 passed, 1 skipped**, including every FCBI anchor
  (P1–P11, worked example, W4 counterexamples, 500-DAG corpus equivalence,
  λ-sensitivity) unchanged — the locked LI-01 is numerically untouched.
- New regressions: LOE has no RF entry + pure-LOE path dropped (PCI 1.0);
  mixed-path neutralization with `float_paths()` invariance pinned in the
  same test; all-milestone schedule degrades gracefully (lineage-A
  validation lock); CDI LOE-out/completed-retained + disclosures; the K1
  fallback scope lock.
- Demo-series pinned letters hold.
