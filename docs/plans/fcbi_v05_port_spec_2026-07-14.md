# Port spec — FCBI v0.5 methodology onto our base (2026-07-14)

**For:** Codex (implementer). **Reviewer/merge:** Claude. **Ships as:** v0.5.0
(major methodology supersession of FCBI v0.4.1). **Gates cleared:** merit review
(`matrix_methodology_merit_2026-07-14.md`) + soundness gate
(`matrix_soundness_gate_2026-07-14.md`), both PASS. Principal go-ahead: 2026-07-14.

## Objective
Adopt the matrix branch's FCBI v0.5 distance-basis methodology onto OUR canonical
base (which has the full product), superseding our FCBI v0.4.1. FCBI ONLY in this
chunk; the kernel-v2 consumers (PCI/CDI/RDI/BWI) are later chunks that reuse the
shared enumerator this one brings.

## Source (matrix branch `claude/li-metrics-audit-matrix-mdadj5` @ 269730b)
Port these, faithfully, reading the matrix code as the reference:
- `analytics/li_indices.py` FCBI section: `_target_distance`, `_governed_codes`,
  `_resolve_fcbi_target`, `_prepare_fcbi_basis`, `_fcbi`/`_fcbi_from_basis`, the
  B/C/W result dataclasses, the `FCBI_CONV_LAMBDA`/`FCBI_CONV_TOL`/
  `FCBI_PATHS_MAX` constants, `REFERENCE_HPD`.
- `analytics/paths.py`: the additive `FloatPath.rel_float_hours` and the lazy
  `iter_float_paths` streaming enumerator (yields `(native_rel, fp, used_snapshot)`).
- The ruling `docs/rulings/LI-01-fcbi-v0.5.md` (port it into our docs/rulings/;
  it is the recorded methodology ruling) and the §9.1 spec text.
- The FCBI probe set P1–P11 in their `tests/test_li_indices.py`.

## Reconciliations (do NOT copy matrix verbatim here)
1. **Keep OUR R-ID UID-first identity.** Their target resolution
   (`_resolve_fcbi_target`, and the `_find_by_code(schedule, target_code)` in
   `_target_distance`) is CODE-first (their RW3-F2). Reconcile to **UID-first via
   our `match_activity`** (code fallback only for legacy no-UID rows), so a
   UID-stable re-code does not change the FCBI target. This supersedes RW3-F2 on
   our lineage; add a re-code regression test for the FCBI target.
2. **Mixed-calendar frontier fixture (soundness caveat).** The frontier bound reads
   native `total_float_hours` while path margins use fixed-reference
   `rel_float_hours`. Add a seeded fixture with activities on DIFFERENT native
   calendars that exercises the early-stop, asserting frontier-stopped == exhaustive
   distances (mirror `test_w4_03` but mixed-calendar). No known defect — make it
   airtight.

## Governance quartet (LI-01 is scored, weight 2)
- **Matrix row** `matrix.yaml` LI-01: rewrite the description/formula for the v0.5
  distance basis, B/C/W, quarantine/coverage, retired FCBI%.
- **Implementation** as above.
- **Seeded fixtures**: port P1–P11 + the mixed-calendar frontier case.
- **Tests**: the ported probes + our re-code target test; keep them green.
- **Recorded ruling**: port `LI-01-fcbi-v0.5.md`, adding a "ported onto v0.4.6
  base; identity reconciled to R-ID UID-first (supersedes RW3-F2); mixed-calendar
  frontier fixture added" note.
- **CHANGELOG** v0.5.0 entry; bump `__version__`/pyproject to 0.5.0.
- **Grade re-pin**: FCBI moves the demo LI-01 number. Re-run the scorecard; if the
  pinned demo letters move, record the re-pin deliberately in the ruling + CHANGELOG
  (do not silently change pinned grades).
- Regenerate `METRIC_MATRIX.md` and `public_spec/`.

## Scope boundary
- FCBI + the shared enumerator (`iter_float_paths`, `rel_float_hours`,
  `_target_distance`) ONLY. PCI/CDI/RDI/BWI stay on the v0.4.x kernel this chunk;
  they move in the next chunks.
- Our v0.4.3 mixed-path LOE neutralization is SUBSUMED by the v0.5 discrete-members
  basis for FCBI — note the supersession; leave the kernel consumers' v0.4.x
  neutralization intact until they port.
- Run the FULL suite (2092+) — the enumerator touches `paths.py`, a broad module;
  confirm no downstream (TIA/damages/driving-path) regression.

## Sequence
Land AFTER the in-flight v0.4.7 (R-ID provocative extension) to keep chunks clean.
Push; Claude reviews (reproduce-don't-trust on the ported math + full suite +
grade check) → merges to main → hands off the next kernel-consumer chunk.

## Acceptance criteria (what Claude will verify)
- P1–P11 reproduce on the ported code; re-code target test passes; mixed-calendar
  frontier fixture passes; full suite green.
- FCBI target is UID-first (re-code invariant); no `w>1`; orphans quarantined.
- Grade delta recorded (not silent); docs/matrix/public_spec regenerated.
