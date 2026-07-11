# ScheduleIQ — Session Handoff (2026-07-07)

For the next Claude session picking up this project.  Read this file, then
`docs/BACKLOG.md` (the to-do list of record) before doing anything.

## 1. What this project is

ScheduleIQ: Long International's Acumen Fuse replacement — schedule quality,
health, trend, and change analysis for P6 (.xer) and Microsoft Project
(.mpp/MSPDI), with LI house-style Word/PDF reports, Excel workbooks, a
PySide6 GUI, and CI that builds a shareable Windows installer.  Principal:
RJL (worktodo77), an expert schedule delay analyst.  Perspective and
guardrails follow the firm's expert-witness discipline: observations, not
opinions; causation/entitlement/quantum reserved to the expert; every number
reproducible and cited.

## 2. Where the code lives (IMPORTANT)

- **Canonical, pushed, current**: repo `worktodo77/expert-assist`, branch
  `claude/acumen-fuse-replacement-ler9kq`, subdirectory **`schedule-iq/`**.
  This mirror is complete at v0.2.0 and is the source of truth.
- **`worktodo77/schedule-iq`** exists but contains only its initial README:
  every push from the prior session returned 403 (session repo-scope was
  stamped before the repo existed; the mid-session `add_repo` approval flow
  never delivered).  A fully identity-clean (`Claude
  <noreply@anthropic.com>`) local history was prepared but died with the
  container — do not look for it.
- **First task of the new session — migrate**: with `worktodo77/schedule-iq`
  in the session's sources, copy the `schedule-iq/` subtree from the mirror
  branch into the schedule-iq repo root and push to `main` as a single
  import commit ("Import v0.2.0 from expert-assist mirror — development
  history preserved on expert-assist branch
  claude/acumen-fuse-replacement-ler9kq").  Prefer creating the import
  commit through the GitHub API (`mcp__github__push_files`) rather than a
  local git push: API-created commits are signed by GitHub and show as
  Verified, satisfying the repo's verified-commit hook; thereafter commit
  locally as `Claude <noreply@anthropic.com>` as usual.  Then treat schedule-iq as
  canonical; keep syncing the mirror only until RJL confirms, then remove
  the subtree from the expert-assist branch in a final commit.

## 3. State at handoff — v0.2.0 complete

- **73-check matrix** (`src/scheduleiq/metrics/matrix.yaml`, rendered to
  `docs/METRIC_MATRIX.md`): DCMA 14-point, logic/constraint/float/duration/
  status/calendar/resource/structure checks, series (TRD/EVM/SET/CAL) checks,
  and the ten LI proprietary indices LI-01..LI-10 (FCBI, LHL, FRB, PCI, RDI,
  BDI, CDI, IL, BWI, MML — formulas in `analytics/li_indices.py` and
  `analytics/li_record.py`, concepts in `docs/ANALYTICS_PROPOSAL.md` §9-§10).
- **Analytics**: path analytics (driving path float-first, float paths,
  merge ranking, stability attribution), intake accelerators D1-D8 (incl.
  RFI generator, windows auto-segmentation, event mapper, responsibility
  overlay), statistical screens, earned schedule, pacing/acceleration
  screens, narrative reconciliation (CONSISTENT/DISCREPANT/RECORD-REWRITTEN/
  UNMATCHED).
- **LI Schedule Report Card** (spec `src/scheduleiq/scorecard.yaml`,
  LI-RC v1.0; engine `scorecard.py`; design `docs/REPORT_CARD_DESIGN.md`):
  per-file + series cards, integrity gates, top-factors decomposition,
  score_trace.json; card leads the Word report.  Public-spec package in
  `docs/public_spec/` is prepared but **NOT published** (RC6 decision with
  RJL).
- **Outputs per run**: 9+ artifacts (per-file workbooks, trend, paths,
  intake, statistical, report card workbooks; Word report; score trace;
  figures) + JSONL audit log + reproducibility capsule (hash manifest +
  rerun script).  PDF converts via Word on analyst PCs (LibreOffice
  fallback; both broken in the dev container — expected).
- **Tests**: 161 passed + 1 conditional skip (`python3 -m pytest tests/ -q`
  with PYTHONPATH=src; fixtures regenerate via
  `python3 tests/fixtures/make_fixtures.py`).
- Demo-series Report Card grades (regression reference): baseline C+ 74.85,
  update1 C 61.37, update2 D 57.95, series D 52.21 (record-discipline gate).

## 4. Next build work, in order (details in BACKLOG.md)

1. **Migration** (§2 above).
2. **v0.3 — CPM engine port (E1-E5)**: PORT, don't build.  Source repo
   `worktodo77/mip39-schedule-analysis-tool` (must be in session sources) —
   ~2,500-SLOC production core: PDM forward/backward pass, multi-calendar,
   ABCS destatusing, AACE 49R-06 longest path, OOS rectification, P6
   CPW-equivalence validation framework.  Port as `scheduleiq.cpm`; close
   LIM-028 (constraint scheduling — REQUIRED), LIM-045 (per-relationship lag
   calendars), carry LIM-044 tolerance.  Gate everything behind the
   validation handshake (ADR-0007 in `docs/ANALYTICS_PROPOSAL.md` §0) and
   the SET-02 check.  Plan of record also recorded in expert-assist
   `PARKING_LOT.md` item B1.
3. **Engine-dependent features** (all specified in ANALYTICS_PROPOSAL.md):
   A2-A4 impact waterfall, P5-P6 constraint-free criticality + as-built
   path, D9 MIP 3.4 half-step, N3 daily delay ledger, N4 methodology-
   robustness certificate, M1-M4 Monte Carlo (empirical calibration via the
   existing FRB/statistical modules), C2/SET-02.
4. **Recalibrate** FCBI/RDI absolute-day anchors in scorecard.yaml against
   real files (flagged in spec rationales) once RJL supplies a real .xer
   series (his task L3).  **LI-01 FCBI is now v0.5.0** (governed revision,
   rulings O1-O7 in `docs/rulings/LI-01-fcbi-v0.5.md`): the graded value is the
   cumulative operational gross burn **B** (not the retired weighted sum), and
   its Report Card scoring is currently **provisional/ungraded** pending this
   recalibration — see `scorecard.yaml` `series_curve_overrides: LI-01` and the
   briefing `docs/LI-01-v0.5-briefing.md` (questions 1-7 await the paper
   author).  When recalibrating, restore a `points:` curve on the **B** scale
   and remove the `provisional` flag.

## 5. Decisions waiting on RJL (do not build without approval)

- N16-N20 provocative metrics (SMI, DDI, ARR, PPS, RSA) — proposed §11.
- RC6: publish the Report Card spec publicly (recommendation: yes).
- Parked: N1 weather overlay, N2 work-pattern reconstruction, S5-S10
  (editing-session forensics, TIA workbench, damages overlay, HTML cockpit,
  benchmark corpus, ML research), F1-F5 Fuse-parity remainder.
- L3 real-file validation and L4 first release/installer circulation are
  RJL's own tasks.

## 6. Working conventions (RJL-directed; follow them)

- **Delegate builds to subagents — Sonnet for well-specified/mechanical
  work, Opus for algorithmically subtle work — and the lead (Fable) audits
  every deliverable substantively before acceptance**: run the tests
  yourself, hand-verify representative numbers against the fixtures, read
  the key diffs.  Audits have caught real defects in every wave (float-
  priority pathing, DUR-04 self-reference, evergreen over-flagging, a
  fixture bug); do not rubber-stamp.
- Subagent rules that worked: strict file-ownership lists per agent, pure
  new modules where possible (lead does shared-file integration), agents
  NEVER run git, final message = deliverable report + full pytest output.
- **Governance** (docs/GOVERNANCE.md): a check changes only when matrix row
  + implementation + seeded fixture defect + tests change together.  The
  scoring spec (scorecard.yaml) has the same rule.  Never silently expand
  scope; new ideas go to BACKLOG.md as PARKED for RJL review.
- Git: user.email `noreply@anthropic.com`, user.name `Claude`; end commit
  messages with the Co-Authored-By + Claude-Session trailers; push early
  and often — **containers restart without warning and un-pushed work has
  been lost once already**.
- House style for all report output: LI template conventions (ALL-CAPS H1-2,
  Numbered Paragraph, two spaces between sentences, American spelling,
  serial comma, teal #1F6F7B tables) — see docs/adr/ADR-0005 and
  `report/docx_li.py`.

## 7. Key documents map

| Doc | Role |
|---|---|
| docs/BACKLOG.md | To-do list of record (statuses: DONE/APPROVED/PARKED/BLOCKED) |
| docs/ANALYTICS_PROPOSAL.md | Full design detail for every analytic + the three bespoke-metric sets |
| docs/REPORT_CARD_DESIGN.md | Report Card design (authoritative for scorecard.yaml) |
| docs/METRIC_MATRIX.md / REFERENCES.md | Rendered check inventory + citations |
| docs/GOVERNANCE.md / METHODOLOGY.md / ARCHITECTURE.md | Rules, math conventions, module map |
| docs/FUSE_PARITY.md | Feature status vs Acumen Fuse |
| docs/adr/ | Decision records (ADR-0007 = engine port, in ANALYTICS_PROPOSAL §0) |
| CHANGELOG.md | Check-affecting changes per version |
