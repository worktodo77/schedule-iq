# R-ID matrix-branch portability report — 2026-07-14

## Scope and lineage

This is a docs-only portability check.  The existing five probes in
`tests/test_r_id_identity.py` were executed against a clean worktree of
`claude/li-metrics-audit-matrix-mdadj5` at commit `269730b800b50da2e021e89040e734266aa7c488`
(`RW3-F6/F7 rulings executed: earlier-endpoint demonstrated numerator; PCI path policy closed`).
The test source was kept unchanged; only its source-path bootstrap was pointed
at that worktree so the matrix branch's implementation, not the v0.4.6 review
copy, was imported.  No matrix-branch files were changed.

## Probe results

| Existing probe | Result on matrix tip | Observed failure | Required portable delta |
|---|---|---|---|
| `test_shared_register_matches_uid_recode_and_rejects_replacement` | **FAIL** (`AssertionError`) | A stable-UID re-code is not treated as the same activity by the shared change register; the probe fails at the no-added/deleted assertion. | Port UID-first activity matching into `compare`, retaining narrow legacy-only code fallback and true UID replacement as added/deleted. |
| `test_frb_resolves_recode_by_uid` | **FAIL** (`AssertionError`) | The one completed activity does not produce the expected FRB observation after its code is re-coded. | Make FRB's later-actual lookup use the shared UID-first matcher. |
| `test_bdi_keeps_uid_recode_baseline_original` | **FAIL** (`IndexError: list index out of range`) | The BDI probe yields no returned path step under the re-code scenario, so the expected baseline-membership step cannot be inspected; the matrix implementation remains code-keyed for baseline membership/edge checks. | Carry UID-first baseline activity and relationship membership into BDI; codes remain display labels. |
| `test_il_response_survives_uid_recode` | **FAIL** (`AssertionError`) | The response event is not recognized after the activity code changes, so the expected chain/response assertion fails. | Carry UID identity through IL emergence and response change matching. |
| `test_mml_resolves_recode_by_uid` | **FAIL** (`AssertionError`) | The re-coded completed/resource-loaded activity does not yield the expected resource-based productivity window. | Make MML's cross-update activity/resource matching UID-first. |

**Summary: 0/5 passed, 5/5 failed.**  The matrix branch therefore needs the
full portable R-ID delta: the shared UID-first register/matcher plus the FRB,
BDI, IL, and MML consumer changes.  This is strictly the identity delta; the
matrix branch's LOE/basis/kernel work is outside this report and was not
reimplemented here.

## Cutover note

The v0.4.5 review lineage already contains the approved R-ID implementation and
its five passing probes.  At matrix cutover, port that implementation (or
equivalent reviewed commits) before adopting matrix-only methodology changes;
otherwise a stable UID re-code remains observable as a false add/delete or a
lost cross-update observation in every affected LI surface.
