# Matrix-branch verification (the Option-A gate) — 2026-07-14

**Reviewer:** Claude. Verification run in a working environment (PyYAML +
matplotlib present, unlike Codex's env). Matrix worktree at
`269730b` vs approved lineage `e99f2010` (v0.4.6).

> **Gate outcome: Option A (adopt matrix wholesale) is NOT viable as stated.**
> The verification surfaced a decisive fact the earlier ruling was made without:
> the matrix branch is green but **narrow** — it carries a superior LI-metrics
> *methodology* but is missing ~2/3 of the *product*. The cutover direction
> should flip. Re-decision requested.

## 1. Test health (corrects Codex's env-blocked run)
- Matrix full suite in a proper env: **305 passed, 1 skipped, 0 failed.** Green.
  (Codex's "17 failed" were entirely missing `yaml`/`matplotlib` imports on its
  machine — confirmed: with those deps the branch is clean.)
- **But 305 vs our 2092 tests.** Matrix has **11 test files; ours has 30.**

## 2. The decisive finding — matrix lacks the product, not just tests
The matrix branch forked from the v0.2.0 import and only ever deepened the
LI-metrics core. Verified absent on matrix (present on ours):
- **Modules:** TIA, damages, collapse engine, weather, benchmark corpus.
- **Test suites missing on matrix:** `test_tia`, `test_damages_rc6`,
  `test_montecarlo`, `test_weather`, `test_impact`, `test_halfstep`,
  `test_handshake_set02`, `test_asbuilt`, `test_cockpit`, `test_dailyledger`,
  `test_editsessions`, `test_forensic_outputs`, `test_robustness`,
  `test_workpatterns`, `test_p6xml`, `test_v04_wiring`, `test_li_provocative`,
  `test_r_id_identity`, `test_corpus_priors`, `test_ribbon_phase_compliance`.

That is the whole v0.3 engine-port downstream + S6-S10, N1-N4, M1-M4, F1-F5,
RC6 publication, the provocative set (LI-11..15), P6 XML parsing, and R-ID —
none of it exists on the matrix branch. **Adopting matrix as canonical would
discard all of it.**

## 3. Corrected picture (neither branch is a superset)
| | Our lineage (v0.4.6) | Matrix lineage (269730b) |
|---|---|---|
| Product features (TIA/damages/MC/RC6/…) | **Complete** | **Absent** |
| R-ID UID-first identity | **Yes** | No (0/5) — and RW3-F2 deliberately keeps kernel target CODE-only |
| LI-metrics methodology | v0.4.x rulings | **FCBI v0.5 target-distance basis + kernel v2** (more developed) |
| PCI (LI-04) | scored | provisional/ungraded pending recalibration |
| Test suite | 2092 | 305 (green) |

The matrix branch is a **superior LI-metrics methodology on an old, narrow
base**; ours is the **complete product on the older LI methodology**.

## 4. Methodology conflicts (these are principal rulings, and they DIVERGE)
A port in either direction must resolve conflicts where the two lineages'
principal rulings disagree:
- **FCBI basis:** ours = relative-float + negative-float `w>1` premium (v0.4.1);
  matrix = nonnegative target-distance, `w∈(0,1]`, premium **abolished** (v0.5).
- **Kernel:** ours = per-index RF kernel + mixed-path neutralization; matrix =
  unified **kernel v2** on the FCBI-v0.5 family basis (Q-B/D1-D4).
- **Identity:** ours = **R-ID UID-first family-wide**; matrix = **RW3-F2
  CODE-only** kernel target resolution (BWI anchor UID-first only). Direct conflict.
- **PCI:** ours scored; matrix provisional/ungraded (D4).
- **RDI pace endpoint:** ours (R1/R2 planned-scope, P50); matrix RW3-F7
  earlier-endpoint demonstrated numerator. Different resolution.

## 5. Recommendation — flip the cutover direction
- **Keep OUR lineage canonical** (it is the product). Do **not** adopt matrix
  wholesale — it would delete the feature suite.
- **Port the matrix branch's LI-metrics methodology INTO our base** as a
  governed batch (FCBI v0.5, kernel v2, the Q-F/Q-G BDI/MML revisions),
  **but only where the principal rules to adopt that methodology over our
  shipped v0.4.x rulings** — each conflict in §4 is a methodology decision, not
  a merge mechanic. This is large and number-changing (FCBI/PCI/CDI/RDI/BWI) and
  ships under the full governance quartet with grade re-pins.
- Alternatively, treat matrix as a **methodology reference** and cherry-pick
  specific rulings over time rather than a wholesale kernel swap.

## 6. What this does NOT change
- R-MIR (retire mirror), the R-ID v0.4.6 ship, and the LOE analysis all stand.
- The matrix branch's audits (IL_FRB 7-10, LI-02-10 matrix 7-12) remain worth
  mining regardless of direction.
