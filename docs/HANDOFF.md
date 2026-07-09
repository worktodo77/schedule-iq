# ScheduleIQ — Session Handoff (2026-07-07, late — v0.4.0 complete)

For the next Claude session.  Read this file, then `docs/BACKLOG.md` (the
to-do list of record).

## 1. What this project is

ScheduleIQ: Long International's Acumen Fuse replacement — schedule quality,
health, trend, change, forensic-delay, and risk analysis for P6 (.xer) and
Microsoft Project (.mpp/MSPDI), with LI house-style Word/PDF reports, Excel
workbooks, a PySide6 GUI, and CI that builds a shareable Windows installer.
Principal: worktodo77 (expert schedule delay analyst).  Observations,
not opinions; causation/entitlement/quantum reserved to the expert; every
number reproducible and cited.

## 2. Where the code lives

- **Canonical**: repo `worktodo77/schedule-iq`.  v0.2.0 imported to `main`
  at commit c0a64bf (2026-07-07); all v0.3 work is on branch
  `claude/scheduleiq-v0.3-engine-port-rx96cl` (pushed, current).  Merging
  that branch to main is the principal's call.
- **Mirror**: expert-assist branch `claude/scheduleiq-v0.3-engine-port-rx96cl`
  carries a synced `schedule-iq/` subtree (per the migration plan: keep
  syncing until the principal confirms the new repo, then remove the subtree from
  expert-assist in a final commit).  Development history through v0.2.0 is
  preserved on expert-assist branch `claude/acumen-fuse-replacement-ler9kq`.
- Engine port source: `worktodo77/mip39-schedule-analysis-tool` (read-only
  reference; keep it in session scope for provenance questions).

## 3. State at handoff — v0.3.0 AND v0.4.0 complete

v0.4.0 (the principal's blanket approval of 2026-07-07, "build all items awaiting my
call") added on top of v0.3.0: N16-N20 provocative indices LI-11..15
(79-check matrix; privileged/internal surfaces only), S6 TIA workbench +
ported collapse engine (MIP 3.6-3.9), S7 damages overlay, RC6 publication
package (built/licensed/verified — THE PUBLIC PUSH IS THE ONE REMAINING
HUMAN STEP), N1 weather overlay (offline GHCN), N2 work-pattern
reconstruction, S5 editing-session forensics (+ ingest audit columns),
F1 ribbon / F2 phase / F4 per-period compliance, F3 P6 XML (PMXML)
ingestion + F5 MPXJ Asta/Phoenix, S8 self-contained HTML cockpit,
S9 anonymized benchmark corpus, S10 offline duration priors (LLM
narratives expressly out of scope), and the consolidated v0.4 wiring
(profile `config:` schema, v04_analytics_supplement.xlsx, cockpit.html,
opt-in INTERNAL_PRIVILEGED workbook, corpus record opt-in).
Suite at v0.4.0: 2,062 passed + 2 conditional skips.

v0.3.0 state (engine release; all still true, tested at 1,839 + 1 then;
`PYTHONPATH=src python3 -m pytest tests/ -q` after
`python3 tests/fixtures/make_fixtures.py`), committed, and pushed:

- **`scheduleiq.cpm`** (ADR-0007, amends ADR-0004): the MIP 3.9 tool's CPM
  core ported port-and-validate (~1,500 ported tests) — PDM passes,
  multi-calendar, per-relationship lag calendars, pinning, AACE 49R-06
  longest path, ABCS destatusing, comparison + benchmark frameworks
  (PHASE7 12/12; MULTI_CALENDAR 3/7 in BOTH source and port — pre-existing
  source baseline, flagged, not a port defect).  Added during the port:
  date-constraint scheduling (closes source LIM-028; all P6 types,
  disclosed applications, negative float) and Progress Override statusing
  (net-new).  LIM-044 carried (calendar-day tolerance).
- **Validation handshake + SET-02** (74-check matrix): engine re-schedules
  the file as imported, match rate vs tool-of-record reported; below 99%
  every engine-dependent feature refuses (`HandshakeRefusal`).  Engine
  numbers are always labelled diagnostic deltas; record dates remain the
  schedule.
- **Engine-dependent analytics**, all handshake-gated, PRELIMINARY-labelled:
  A2 issue-impact overlay (+ per-constraint waterfall attribution, float
  absorbed), A3 waterfall one-pager, A4 retained-vs-override delta, P5
  constraint-free criticality (manufactured/masked), P6 as-built path
  reconstruction (tightness-ranked actualized links, contradicted logic as
  evidence), D9 MIP 3.4 half-step (exact progress+revision identity, NAMED
  revision attribution with honest interaction residual, MIP 3.3 as-is),
  N3 daily delay ledger (telescoping sum check, D6/D7 annotation), N4
  methodology-robustness certificate (framing × statusing × boundary ×
  contested-revision grid, stability sentences + banding), M1/M2/M4 Monte
  Carlo (LHS, PERT/triangular/uniform, correlation rank-blend, risk
  events, empirical calibration from the update history, SRA-readiness
  gate READY/DIAGNOSTIC-ONLY/REFUSED), M3 outputs (S-curve, tornado,
  criticality/cruciality, merge-bias note; forensic + SRA workbooks and
  figures wired into runner + Word report).
- **Fixtures**: legacy demo series (deliberately defective; engine refuses
  it by design — that's asserted) + engine-consistent demo_cpm /
  demo_cpm_divergent (handshake 100% / exactly 75%) + demo_impact +
  demo_hs1/demo_hs2.  All regenerate byte-identically.

## 4. Next work (in rough order)

1. **The principal's own steps**: L3 real-file validation; L4 release/installer;
   the RC6 public push (docs/public_spec is built and stamped READY).
   Nothing remains PARKED except ideas not yet proposed.
2. After L3: recalibrate FCBI/RDI absolute-day anchors in scorecard.yaml;
   run the handshake + engine analytics against the real matter series and
   review SET-02 rates (real P6 files will surface convention gaps the
   synthetic fixtures cannot).
3. Candidates worth proposing (add to BACKLOG as PARKED first): workday-
   aware handshake tolerance (close LIM-044 properly); investigate the
   MULTI_CALENDAR_SUITE 3/7 source baseline; contested-revision exclusion
   in N4 as a true re-run instead of the disclosed arithmetic adjustment;
   merge-bias exhibit at the top merge nodes (currently target-only,
   disclosed); GUI surfacing of the new v0.3 artifacts.

## 5. Working conventions (unchanged; follow them)

- Delegate builds to subagents (Sonnet mechanical / Opus subtle) with
  strict file-ownership lists; agents never run git; lead audits every
  deliverable substantively (run the tests yourself, hand-verify numbers,
  read key diffs) — audits caught real defects again this session.
- Governance: matrix row + implementation + seeded fixture defect + tests
  change together; CHANGELOG note for check-affecting changes; never
  silently expand scope.
- Git: `user.email noreply@anthropic.com`, `user.name Claude`; Co-Authored-By
  + Claude-Session trailers; push early and often (a monthly API spend
  limit interrupted two subagents mid-build this session — resumed cleanly
  because everything else was already pushed).
- House style: ADR-0005 (LI template), ADR-0007 presentation rule (engine
  = diagnostic deltas only).
