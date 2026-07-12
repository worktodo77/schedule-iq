# LI kernel v2 — design for approval (Wave 3, triage ruling Q-B)

**Status: PROPOSAL — nothing here is implemented.**  · **Date:** 2026-07-12
· **To:** the principal (Alex Bachowski) · **From:** implementation owner,
LI metrics.  Q-B ruled the direction ("build the new governed LI kernel …
adopted per-metric under per-metric rulings; `kernel_weight` /
`relative_float_map` stay byte-identical until retired"); this document is
the design it gated, presented before implementation per the FCBI
precedent.  Open design questions D1–D4 at the end.

---

## 1. What the v0.4 kernel still gets wrong (the Wave-3 residue)

After Waves 0–4, the four kernel consumers (LI-04 PCI, LI-05 RDI, LI-07
CDI, LI-09 BWI) still price criticality off a basis with four defects the
FCBI v0.5 revision abolished for LI-01:

- **K1 — own-total-float fallback.**  An activity on no enumerated path is
  assigned its own TF as a "relative float".  Off-path work enters CDI's
  cast of characters and RDI/BWI's near-critical band on a fabricated
  basis (audit probe: orphan task, no logic at all → rf 4.0, weight 0.574).
- **K2 — the w > 1 negative-float premium.**  `2^(−RF/λ)` explodes for
  negative float: a driver deepening 0 → −10 reads as PCI "concentration"
  rising 0.556 → 0.802 with structure unchanged; CDI dwell is priced by
  depth-of-negative, not time-near-critical.
- **K5 — the raw top-10 truncation.**  `KERNEL_PATHS_N = 10` is a cutoff
  with no proven bound (the exact anti-pattern FCBI O7.3 replaced with a
  sound frontier); PCI's Herfindahl over ≤ 10 shares has floor 0.1, dead
  scored-anchor range below it.
- **PCI weight residual.**  Kept-mixed-path Herfindahl weights still read
  the shared `rel_float_days` (LOE-inclusive, native-calendar) — deferred
  in v0.4.2/1c, due here.  Plus **RDI-2** (the demonstrated-pace population
  gate is exporter-dependent) and **CDI membership questions** (milestones,
  off-path fallback members).

## 2. Design: reuse the LOCKED FCBI basis machinery, don't rebuild it

The core proposal is that the family basis is **the FCBI v0.5.5 distance
basis, called as-is** — not a third arithmetic:

For a schedule *s* and a target milestone *m*, the v2 kernel basis is

    d_i  = min over enumerated float paths containing i of
           (path margin to m − driving-path margin to m),  d_i ≥ 0
    w_i  = 2^(−d_i / λ) ∈ (0, 1]
    unresolved = activities on no enumerated path  (NEVER own-float)
    governed   = activities whose late dates a non-target basis governs,
                 traced through the network (quarantine, disclosed)

computed by the existing, locked, wave-4-hardened functions —
`_target_distance` (exact `iter_float_paths` enumeration with the PROVEN
λ-invariant convergence frontier, `FCBI_CONV_LAMBDA`/`FCBI_CONV_TOL`, exact
`FCBI_PATHS_MAX` cap → provisional), `_governed_codes` (propagated
governance), `_resolve_fcbi_target` (stable terminal target across the
series) — **called, never modified**.  LI-01 stays locked; the family
inherits its corpus-verified enumeration instead of a parallel
approximation.  Margins are `rel_float_hours` (fixed reference hours,
discrete members only): calendar-neutral (A3), LOE-free by construction,
and the constrained-milestone signal that W1c-1 protected in v0.4 is
carried the way FCBI carries it — **governance quarantine + severity
strip**, not a float priced into w.

This resolves K1 (unresolved → quarantined/disclosed, with per-update
coverage = resolved / candidates), K2 (d ≥ 0 ⇒ w ≤ 1; severity beside, §4),
K5 (proven frontier replaces the raw top-10; a cap hit → provisional,
disclosed), and the PCI residual (weights read the discrete-only margins).
λ is bounded to `(0, FCBI_CONV_LAMBDA]` for the same W4-05 reason as FCBI;
the {3, 5, 10} sensitivity set (Wave 4c) re-points to the new basis.

## 3. Per-metric semantics (each lands as its own governed revision)

- **PCI v2 (LI-04).**  Shares over the enumerated paths' weights,
  `w_p = 2^(−(margin_p − margin_driving)/λ)`; Herfindahl of shares.
  Enumeration runs to the convergence frontier, so N is no longer fixed at
  10 (the 0.1 floor disappears — anchors must be re-based, §5).  A
  deepening negative driver no longer manufactures "concentration"
  (severity strip carries it, §4).
- **CDI v2 (LI-07).**  Per update, one unit of dwell allocated over
  **resolved, ungoverned** activities with d ≤ band; unresolved/governed →
  quarantine counts disclosed per update (B2 coverage pattern).  Milestone
  markers: excluded from dwell (they are references, not work — their
  pressure reaches the board via governance + severity), superseding the
  v0.4 incidental membership; disclosed.  Completed-retention: see **D3**.
- **RDI v2 (LI-05).**  Required pace: remaining work of resolved,
  ungoverned activities with d ≤ band at that update (unresolved volume
  disclosed as a data-quality line).  Demonstrated pace — **fixes RDI-2**:
  a completion counts if it was near-critical **at the window's earlier
  endpoint** (d at start ≤ band) — nonanticipative (the O3 lesson), and no
  longer dependent on whether the exporter nulls TF at completion.
- **BWI v2 (LI-09).**  Band membership by distance **to the BWI milestone
  itself** (its own UID-pinned target, not the completion target): d
  computed with target = the bow-wave milestone, so "work packed against
  m" means near-critical *relative to m*.  Fixed horizon (B1), UID pinning
  (B2), and the W1c-3 required-pace break test carry over unchanged.

Adoption is per-metric: each v2 lands with its own probe set, before→after
table, matrix/spec wording, ruling record, and review wave.  The legacy
kernel stays byte-identical until the last consumer migrates, then is
retired with a retirement record (FCBI% precedent); the Wave-1c/RW2 scope
locks are inverted per-metric as each migrates (a failing scope lock is an
actioned decision, by design).

## 4. Severity beside, never inside (the N/ΔN⁺ pattern)

Per update: `N = max(0, −margin_m)` (reference working days of
target-margin deficit) and `ΔN⁺` deepening, reported beside PCI and CDI —
the real signal the w > 1 premium was groping toward, carried explicitly
(FCBI O2/Q5 precedent).  RDI/BWI carry it via their existing
disclosures/severity surfaces.

## 5. Report Card / anchors (the LI-01 precedent)

- **LI-04 PCI: provisional/ungraded** on landing — the two-sided anchors
  [0.05, 0.15, 0.35, 0.6] were tuned to a floor-0.1, top-10, premium-priced
  scale that no longer exists; recalibration against real series is a
  separate, flagged step.
- **LI-05 / LI-09** stay graded (units/scale survive); pinned demo letters
  verified per revision, movements disclosed in the CHANGELOG as
  check-affecting.
- **LI-07** remains unscored (leaderboard/forensic surface only).

## 6. Explicitly out of scope

Cross-project comparability, Tier-2 statistical noise, resource-leveling /
external-successor governance (FCBI's own documented captures), any change
to `float_paths` / `iter_float_paths` / FCBI itself, and the LI-01 white
paper.

## 7. Open design questions (D1–D4)

- **D1 — Basis + governance reuse.**  Adopt the FCBI target-specific
  nonnegative distance as the family basis, reusing `_target_distance` /
  `_governed_codes` / `_resolve_fcbi_target` as-is, with per-metric targets
  (stable completion milestone for PCI/CDI/RDI; the UID-pinned bow-wave
  milestone for BWI)?  *Recommended: yes — one verified arithmetic for the
  whole family; the alternative (distance without governance tracing) is
  cheaper but re-opens the constrained-milestone hole governance closes.*
- **D2 — Severity strip.**  N/ΔN⁺ beside PCI/CDI as in §4?  *Recommended:
  yes.*
- **D3 — CDI completed-work dwell.**  Under the new basis a completed
  activity is off the remaining-work paths, so it naturally stops EARNING
  dwell after completion (all dwell earned while live is retained —
  "retrospective criticality-time" preserved).  The v0.4 behavior let
  finished work keep accruing dwell via the fallback.  *Recommended:
  accrue-while-live, recorded as a supersession of the incidental
  post-completion accrual (C2's rationale is about retaining history, not
  about accrual after finish).*
- **D4 — PCI grading.**  Mark LI-04 provisional/ungraded pending anchor
  recalibration (LI-01 precedent), rather than keeping stale anchors live?
  *Recommended: yes.*
