# Soundness gate — matrix FCBI-v0.5 + kernel-v2 implementation (2026-07-14)

**Reviewer:** Claude. Reproduce-don't-trust pass on the matrix branch's actual
implementation (`269730b`), independent of its own fixtures, to decide whether it
is safe to port. Follows the merit review (`matrix_methodology_merit_2026-07-14.md`).

> **Gate outcome: PASS.** The keystone math is sound on independent inputs, the
> frontier early-stop is both mathematically argued and corpus-tested, and the
> abolished-fallback / no-premium properties hold. Safe to proceed to a port
> plan. One minor caveat to fold into the port (below).

## What I verified independently (my inputs, not their fixtures)
- **`_target_distance` (O1 keystone).** Driving chain A→B→M + feeder C(+10d) +
  orphan D(no path):
  - driving-path activities **d = 0, w = 1.0**; feeder **d = 10d, w = 0.25**;
  - **every weight ≤ 1** (the w>1 premium is genuinely abolished);
  - **every d ≥ 0** (no negative distances, per the `max(0,·)` clamp vs the
    rank-1 driving margin);
  - the **orphan is ABSENT from the distance map** — quarantined, NOT priced at
    its own total float (K1 own-float fallback genuinely abolished).
- **Frontier soundness (the mathematical heart).** The code's argument is
  correct: a not-yet-enumerated path's unique members ⊆ the generator's unused
  set, so `min(reference float over reachable, discrete, UNUSED activities)`
  lower-bounds every omitted path's margin; since `2^(-d/λ)` decreases in d, a
  frontier weight `< FCBI_CONV_TOL` at the fixed `FCBI_CONV_LAMBDA` proves every
  omitted path immaterial. Convergence judged at a FIXED λ (not the weighting λ),
  and the weighting λ is capped at that reference so the bound stays valid at all
  λ ≤ it. Sound.
- **Test coverage for the rest (all green in the 305-suite I ran):**
  `test_w4_03_frontier_no_material_omission_corpus` (frontier omits no material
  weight across a randomized corpus — the key soundness property, verified
  empirically), `test_fcbi_adaptive_convergence`, the exact `FCBI_PATHS_MAX`
  cap-at-(MAX+1) semantics (W4-07), and the stats instrumentation.

## Assessment
The distance basis, the abolished fallback, the no-premium weight, and the frontier
early-stop are correct and defensible. The kernel-v2 consumers (PCI/CDI/RDI/BWI)
build on this same verified basis and pass their consumer tests, so the family
rests on a sound foundation. Combined with the merit review, the matrix
methodology is **both better-designed and correctly implemented**.

## Caveat to carry into the port (not a blocker)
The frontier lower-bound reads native `total_float_hours` while path margins use
fixed-reference `rel_float_hours`; these coincide on the reference calendar but
could diverge under mixed native calendars. The corpus test did not obviously
stress mixed-calendar topologies. **Port action:** add a mixed-calendar frontier
case to the seeded fixtures to make the early-stop airtight before it lands. (No
evidence of an actual defect — a belt-and-suspenders item.)

## Recommendation
Proceed to the **port plan**: adopt FCBI-v0.5 + kernel-v2 onto our base as a
governed v0.5 batch, sequenced one metric at a time (FCBI first), each a full
quartet with grade re-pins, KEEPING our R-ID UID-first identity (supersede their
RW3-F2 code-only) and accepting PCI provisional. Each metric's landing re-verifies
its own soundness under our governance; this gate clears the shared foundation.
