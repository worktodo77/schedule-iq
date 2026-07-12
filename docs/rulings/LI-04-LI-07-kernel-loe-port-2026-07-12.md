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
  LOE/summary or bare-milestone chain cannot inflate PCI's path count (an
  LOE-only BRANCH cannot register as a kernel path; a kept MIXED path's
  Herfindahl-weight residual is separately deferred — review W1c-4 corrected
  an over-broad "reads 1.0" claim here).  Milestones are retained in the RF
  map and their floats keep setting kept-path margins (legitimate
  criticality references — a deadline-constrained finish milestone in
  negative float keeps its chain in the near-critical band); they do not
  satisfy the discrete-work path test.
- **Mixed-path neutralization (v0.4.3).**  The LI kernel computes each kept
  path's relative float over its unique **non-summary** members
  (`_li_path_rel_float` — LOE/summary out, milestones retained), so an LOE
  that is the lowest-float member of a mixed path no longer drives the
  members' RF; when no unique non-summary member carries a float, the
  fallback is the shared `rel_float_days` (the branch's own basis), never
  the spliced tail's min.  Implemented as an LI-kernel-local layer reading
  `FloatPath.unique_uids` — an **additive** field populated by
  `_finalize_path`; the shared `float_paths()` / `iter_float_paths()` walk,
  ordering, `rel_float_days`, and `rel_float_hours` are all byte-identical
  (regression-pinned: the shared path still carries the LOE's −2.0 while
  the kernel RF reads 0.0).
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

## Post-port adversarial review — wave 1 (2026-07-12), loop closed

An independent adversarial review of the Wave 0–1c change set (`ec30292..372be49`,
reproduce-before-reporting; FCBI/paths byte-identity re-verified on a 82-entry
corpus with 0 diff lines; 96 adversarial never-raises calls, 0 raises; every
ported ruling's arithmetic re-derived) raised 3 MAJOR + 2 MINOR findings, all
reproduced.  Dispositions — each fix CONFORMS the code to the already-ruled
record (the FCBI post-implementation-review precedent), no new methodology:

| ID | Sev | Finding | Disposition |
|---|---|---|---|
| **W1c-1** | MAJOR | `_li_path_rel_float` stripped MILESTONE floats from kept-path margins via `_is_discrete_work`, contradicting the ruled text ("milestones excluded ONLY from the discrete-work path test") — a deadline-constrained finish milestone at TF −2 left its whole chain's RF at +15, emptying the near-critical band for CDI/RDI/BWI. Faithfully ported from lineage-A code, whose comment carried the same contradiction latently. | **Fixed to the ruled text:** the kept-path min is over unique NON-SUMMARY members (milestones retained); regression `test_w1c1_*` (chain stays at −2, K2 premium still fires). |
| **W1c-2** | MAJOR | When a branch's unique members carried no float, the fallback read the spliced driving-path TAIL's min — fabricating rf 0.0 / weight 1.0 for a genuinely floaty branch (rubric A1). Also ported faithfully from lineage-A code. | **Fixed:** fallback goes straight to the shared `rel_float_days` (the branch's own basis); the tail-min step is removed; regression `test_w1c2_*` (rf 50.0, not 0.0). |
| **W1c-3** | MAJOR | Under B1's constant denominator the projected-break test (`density > max_demo`) no longer compared a REQUIRED pace — break sensitivity decayed exactly as the milestone approached while the narrative still said "required density". Present in lineage-A's B1 code too. | **Fixed:** the break test now uses remaining volume / working days REMAINING to the fixed reference (a true required pace); the BWI ratio keeps B1's constant denominator; regression `test_w1c3_*`. |
| **W1c-4** | MINOR | Over-broad claim "a single-threaded schedule with an LOE feeder reads PCI 1.0" (only true when the LOE feeds the target directly; a mid-chain LOE yields a kept mixed path, PCI 0.9697 — the separately-deferred Herfindahl residual). | **Reworded** here, in the CHANGELOG, and in the C1 test docstring: "an LOE-only branch cannot register as a kernel path". |
| **W1c-5** | MINOR | matrix.yaml LI-07 said "each discrete-work activity's share" while milestone markers legitimately hold dwell. | **Reworded** (matrix row + §10.2): discrete work AND milestone markers; LOE/summary excluded. |

The review's clean areas: FCBI/paths byte-identity, never-raises, the
Wave-3 scope locks (own-float fallback, w>1 premium, PCI weight residual),
and every ported LHL/RDI/BWI ruling's arithmetic — NO FINDINGS, with probe
evidence.  W1c-1/2/3 are check-affecting refinements WITHIN the Unreleased
Wave-1c train (milestone-float-bearing paths, unfloated branches, and break
labels move vs the pre-review commit; the pre-port base semantics for
milestone floats are restored).

## Review wave 2 (2026-07-12) — REDUCED SCOPE, implementation-side

**Independence caveat, disclosed:** the independent wave-2 reviewer was
terminated early by an account spend limit; this wave was run by the
implementation side against the wave-2 probe plan (verify W1c-1..3 fixes;
attack the Wave-2 IL/FRB revision).  It does NOT carry the weight of an
independent review; a fully independent confirmation wave should run when
resources allow before any of this is treated as review-clean.

Probes executed (all reproduced, outputs in the session record):
W1c-1/3 fix verification incl. the wd_rem ≤ 0 edge (no raise, break
skipped); the causing-edit-as-response case (latency 0 with the adjacency
disclosure present — behavior as adjudicated under IL1-A); the S(0) = 0.5
KM boundary (median reached at 0, standard convention); completed+negative
same-window exclusion (IL4b); overdue-horizon banding at n ≥ 5 through
`frb_apply_forward`; same-chain re-emergence (independent events, second
censored at its own follow-up).

**One new finding, fixed:**

| ID | Sev | Finding | Disposition |
|---|---|---|---|
| **RW2-1** | MAJOR | A branch carrying NO float evidence at all (its only unique member stores no float) still leaked the spliced tail's min THROUGH the shared `rel_float_days` fallback — kernel rf 0.0 / weight 1.0 for a float-less feeder task (the same rubric-A1 class as W1c-2, one level deeper). | **Fixed:** `_li_path_rel_float` returns None for a zero-float-evidence branch and `relative_float_map` skips it — the member falls through to the own-float fallback / the documented "omitted (weight undefined)" case, never a fabricated 0.0.  Regression `test_rw2_1_*`. |

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
