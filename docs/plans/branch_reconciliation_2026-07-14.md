# Branch reconciliation analysis (2026-07-14) — CORRECTION + re-decision needed

**Planner:** Claude · **For:** the principal (worktodo77)

> **This supersedes the premise of the R-FORK ruling** in
> `li_family_rulings_2026-07-14.md`. That ruling ("ours is canonical; salvage a
> few ideas from the forks, then retire them") was made on my characterization
> of the parallel branches as *divergent experiments*. I verified the branches
> in code and that characterization was **wrong**: one of them is a **more
> advanced parallel completion of this exact work**. Retiring it would destroy
> the best version of the codebase. Please re-decide with the facts below.

## What the branches actually are (verified in code, not from commit text)

### `claude/li-metrics-audit-matrix-mdadj5` — AHEAD of ours
A full parallel lineage (31 commits from the v0.2.0 import) that:
- Drove **FCBI to v0.5.6** — six hardening waves, two external peer-review passes
  (Codex REV-01..17; "GPT-5.6 Pro" W3-01..10), an **exact `float_paths`
  enumerator with a proven frontier bound**, best-first path search, a
  white-paper briefing and a worked-example regression anchor. Ours is FCBI
  v0.4.1.
- **Ported all of our v0.4.5 rulings forward** onto that base (Wave 1a: LHL 12
  rulings + L8; Wave 1b: RDI R1/R2 + BWI B1/B2; Wave 1c: shared-kernel LOE C1 +
  mixed-path neutralization + CDI C2).
- Then went **further than us**: a **"LI kernel v2"** unifying PCI/CDI/RDI/BWI on
  the FCBI-family basis (rulings Q-B + D1-D4); **kernel-constant governance**
  (λ/band sensitivity, Q-H); **BDI governed revision** (Q-G: fixed
  original-duration basis, **LOE steps zero-length**, explicit baseline/target
  params); **MML governed revision** (Q-F: basis segregation, sustained clean
  mile, event overlay); **IL + FRB governed revisions** (Wave 2).
- Carries audits we lack: `IL_FRB_audit_2026-07-10`,
  `LI-02-10_audit_matrix_2026-07-12` (+ a probes script).

**Verified against the exact findings Codex just audited on OUR branch:**
| Our 2026-07-14 finding | State on `li-metrics-audit-matrix` |
|---|---|
| BDI-B1 (zero-len → 0 → 100) | **Already fixed** — `bdi_pct = None`, "NOT EVALUATED, never 0.0%" |
| BDI-B4 (no target input) | **Already fixed** — `baseline_index`/target params |
| BDI-B5 (basis) | **Already ruled** — fixed original-duration basis (Q-G) |
| LOE exclusion (BDI/IL) | **Already done** — `_step_length_days`→0 for LOE; IL `# IL4a`; LOE ties dropped |
| MML-M1/M3/M4 | **Already revised** — basis segregation, sustained mile, event overlay (Q-F) |
| **BDI-B2 (code vs UID)** | **NOT fixed** — still `base_codes`/`step.code`. Our finding is novel here. |

So the matrix lineage has **already implemented most of what we just audited and
were about to re-implement** — with recorded rulings and (per its history)
tests. Continuing to build BDI/IL/MML/FRB fixes on our v0.4.5 branch is likely
**duplicating better existing work**.

### `claude/fcbi-v0.5-implementation-yvsdts` — SUBSUMED
Its 14 commits are byte-identical prefixes (`caeefc9..ec30292`) of the matrix
branch's FCBI history. No unique content; retire once the matrix branch is
dispositioned.

### `claude/lhl-implementation-audit-xom1ah` — PARTIAL OVERLAP, one unique find
Forked from **our** cc0d26c (v0.4.4). A parallel, more-thorough LHL audit (Rev
1-3, peer-reviewed) implementing "all 12 rulings" plus an **"L8 split covers the
completion-censor update"** finding we did **not** have, and an
`IL_FRB_audit_2026-07-10`. Worth mining for the L8 finding regardless of the
canonical decision.

## The real decision (was mis-framed)

This is not "which experiments to salvage." It is **which lineage is canonical**:

- **Option A — adopt `li-metrics-audit-matrix` as canonical.** It is ahead
  (FCBI v0.5.6, kernel v2, BDI/MML/IL/FRB revisions, our rulings already ported).
  We then forward-port only what is unique to ours (notably **BDI-B2 UID
  identity**, and the family-wide identity ruling as it applies to *their* code)
  and the LHL "L8" find from xom1ah. **Least total work; keeps the best code.**
  Cost: their ruling scheme (Q-*/RW*/D*) differs from ours; needs a rulings
  concordance, and independent verification that their kernel-v2 and FCBI-v0.5.6
  are sound (they claim peer review — verify, don't trust).
- **Option B — keep ours (v0.4.5) canonical, forward-port their advances.**
  Large effort: re-derive FCBI v0.5.6, kernel v2, and the BDI/MML/IL/FRB
  revisions onto our base. Mostly re-does work that already exists. Hard to
  justify unless their code fails verification.
- **Option C — freeze both, run a structured 3-way evaluation first**, then
  pick. Safest; costs a comparison pass.

**Planner recommendation: Option A, gated on verification.** The matrix lineage
is the more complete artifact; the correct move is to make *it* canonical and
merge our few unique wins into it — provided an independent pass confirms its
kernel-v2 math and FCBI-v0.5.6 hold (the same reproduce-don't-trust bar we hold
everything to). If verification finds problems, fall back to C.

## Immediate implications (please confirm)

1. **Pause new BDI/IL/MML/FRB *implementation* on our v0.4.5 branch** — it likely
   duplicates the matrix lineage. (Auditing is still useful; implementing is the
   waste.)
2. **The R-FORK ruling is withdrawn pending your re-decision** (A / B / C).
3. **R-MIR (retire the expert-assist mirror) still stands** — unaffected by this.
4. If Option A: I produce a **rulings concordance** (our C1/B1/R2/L1/… ↔ their
   Q-B/Q-F/Q-G/D1-D4/RW3-*) and a **verification plan** for kernel-v2 + FCBI
   v0.5.6 before we cut over.

## How this happened (so it doesn't recur)
Parallel agents/sessions branched from the same v0.2.0 import and worked the same
backlog independently, with no shared "canonical branch" lock. The mirror
retirement (R-MIR) removes one source of confusion; a single declared canonical
branch + a short "active lineage" note in HANDOFF removes the rest. Recommend we
never again have two branches implementing the same LI metric.
