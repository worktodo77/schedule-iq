# ScheduleIQ — Session Handoff (2026-07-07, evening)

For the next Claude session.  Read this file, then `docs/BACKLOG.md` (the
to-do list of record).

## 1. What this project is

ScheduleIQ: Long International's Acumen Fuse replacement — schedule quality,
health, trend, change, forensic-delay, and risk analysis for P6 (.xer) and
Microsoft Project (.mpp/MSPDI), with LI house-style Word/PDF reports, Excel
workbooks, a PySide6 GUI, and CI that builds a shareable Windows installer.
Principal: RJL (worktodo77), expert schedule delay analyst.  Observations,
not opinions; causation/entitlement/quantum reserved to the expert; every
number reproducible and cited.

## 2. Where the code lives

- **Canonical**: repo `worktodo77/schedule-iq`.  v0.2.0 imported to `main`
  at commit c0a64bf (2026-07-07); all v0.3 work is on branch
  `claude/scheduleiq-v0.3-engine-port-rx96cl` (pushed, current).  Merging
  that branch to main is RJL's call.
- **Mirror**: expert-assist branch `claude/scheduleiq-v0.3-engine-port-rx96cl`
  carries a synced `schedule-iq/` subtree (per the migration plan: keep
  syncing until RJL confirms the new repo, then remove the subtree from
  expert-assist in a final commit).  Development history through v0.2.0 is
  preserved on expert-assist branch `claude/acumen-fuse-replacement-ler9kq`.
- Engine port source: `worktodo77/mip39-schedule-analysis-tool` (read-only
  reference; keep it in session scope for provenance questions).

## 3. State at handoff — v0.3.0 complete (engine release)

Everything below is DONE, tested (1,839 passed + 1 conditional skip;
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

1. **RJL decisions** (do NOT build without approval): N16–N20 provocative
   metrics; RC6 public spec publication; PARKED items (S5–S10, F1–F5,
   N1–N2).  L3 (real-file validation) and L4 (release/installer) are RJL's.
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
