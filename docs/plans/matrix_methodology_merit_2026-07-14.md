# Merit review — matrix FCBI-v0.5 + kernel-v2 methodology (2026-07-14)

**Reviewer:** Claude. Basis: the matrix branch's recorded rulings
(`docs/rulings/LI-01-fcbi-v0.5.md`, `LI-kernel-v2-2026-07-12.md`, et al.) read
against our shipped v0.4.6, plus the matrix suite run green in a proper env
(305 passed — includes the P1–P11 probes that verify each ruling).

> **Verdict: the matrix FCBI-v0.5 + kernel-v2 methodology is genuinely SUPERIOR
> to our shipped v0.4.x — not merely different. Recommend adopting it onto our
> (complete-product) base as a governed v0.5 batch, with two reconciliations
> (keep our R-ID UID-first identity; accept PCI going provisional).** This is a
> design-merit finding; a line-by-line implementation-soundness audit is the
> gate before the actual port.

## Where it is better (and why)

1. **Target-specific distance basis (O1/D1).** Replaces our generic relative
   float with `d ≥ 0` = distance to *the selected terminal completion milestone*,
   traced through the network. More forensically defensible: FCBI is measured
   against the milestone that matters for a claim, not a generic float. Driving
   path d=0, w=1.
2. **Abolished own-total-float fallback (K1).** Our v0.4.x priced an orphan
   activity at its own TF (an artifact — e.g. board entry rf 4.0/weight 0.574).
   Theirs **quarantines** the unresolved contribution and discloses it. Honest.
3. **Abolished the w>1 "over-critical premium"; severity moved to a separate N
   channel (O1/D2/K2).** Cleanly separates *how critical* (w ≤ 1) from *how
   negative* (N = deficit, ΔN⁺ deepening, reported BESIDE PCI/CDI). Our premium
   conflated the two; theirs is the better design (the premium was an artifact of
   the fallback basis).
4. **B/C/W decomposition + honest scope language (O2).** Retires the ill-defined
   float-stock ratio (FCBI%); reports gross burn B, burn-weighted proximity C,
   derived W=B·C, and explicitly states it does NOT cure network-size dependence.
   More rigorous and less over-claiming than our scalar.
5. **Nonanticipative start-of-window timing (O3).** Auditable from the opening
   state; the start/end/min set is labelled a *sensitivity set, not bounds*
   (correct — the true within-window value can dip below both endpoints).
   Supersedes our min-RF (mildly anticipative).
6. **Target governance / quarantine / coverage (O6).** Traces propagated
   governance through the network, quarantines unresolved burn, and reports an
   eligible-burn coverage ratio — with honest disclosure of what awaits the CPM
   engine. Sophisticated and defensible.
7. **Exact enumerator with a proven λ-invariant convergence frontier + explicit
   512-path cap (D1).** A cap hit → PROVISIONAL, disclosed. Supersedes our top-10
   heuristic truncation. Mathematically rigorous.
8. **CDI D3 / PCI D4.** CDI accrues dwell while live, retains earned history,
   stops at completion; milestones no longer get dwell. PCI is made
   **provisional/ungraded** rather than shipping anchors tuned to the abolished
   scale — intellectually honest.

**Process parity:** two-reviewer consensus (implementation + external peer
review) + methodology-owner approval, same bar as ours. The rulings are specific,
probe-verified, and self-critical (they disclose their own limits).

## Two reconciliations the port must make (do NOT take matrix wholesale here)

1. **Identity — keep OUR R-ID UID-first.** Their RW3-F2 deliberately makes family
   kernel target resolution **CODE-only** ("to mirror FCBI"). We shipped and
   verified R-ID UID-first (v0.4.6). The port should take their *basis* but
   resolve targets UID-first (our improvement), superseding RW3-F2. This is the
   one place ours is clearly better.
2. **PCI goes provisional/ungraded.** Adopting means LI-04 is ungraded pending a
   real-series recalibration workstream. The principal must accept that (a scored
   member temporarily leaves the graded set).

## Cost / risk of adopting

- **Large and number-changing:** FCBI (LI-01) + PCI/CDI/RDI/BWI (LI-04/07/05/09)
  all move to the new basis. Full governance quartet, grade re-pins, and a PCI
  recalibration workstream.
- **Reverses shipped v0.4.x rulings** (our FCBI v0.4.1, our per-index RF kernel,
  our mixed-path neutralization is subsumed by the new basis). Governance permits
  supersession with a recorded ruling — this would be a "v0.5 methodology"
  supersession, well-documented on both sides.
- **Gate before porting:** an independent implementation-soundness audit of
  `_target_distance`/`_KernelV2` (the enumerator frontier proof, the governance
  tracing, the quarantine accounting). Their green probe suite is strong evidence
  but not a substitute for our own reproduce-don't-trust pass on the math.

## Recommendation

1. **Adopt the FCBI-v0.5 + kernel-v2 methodology onto our base** as a governed
   v0.5 batch — it is the better methodology and our base is the complete product.
2. **Sequence:** (a) independent soundness audit of the matrix FCBI/kernel
   implementation [reviewer]; (b) if it holds, port the code + rulings onto our
   base with the two reconciliations above [implementer], one metric at a time
   (FCBI first, then the kernel-v2 consumers), each a governed quartet with grade
   re-pins; (c) stand up the PCI recalibration workstream.
3. **Also mine** their `IL_FRB_audit_2026-07-10` and `LI-02-10_audit_matrix`
   for findings our audits may have missed (e.g. the LHL "L8" completion-censor).
4. **Then** the divergent branches can be retired (their value captured).

## Honest scope of THIS review
This assesses **design merit** from the rulings + the green probe suite. It does
NOT independently re-derive the enumerator convergence proof or re-verify every
governance-tracing path — that is step 2(a), the gate before any port lands.
