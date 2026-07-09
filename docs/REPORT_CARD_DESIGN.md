# The LI Schedule Report Card — Design (FOR REVIEW)

A composite, fully transparent grading system: every schedule file receives a
report card (overall grade + category sub-scores), and a multi-file series
receives an overall report card on top.  Every point of every grade is
traceable to a named check, a published formula, and a list of offending
activities.  Proposed as the public face of ScheduleIQ's analysis — and
potentially as a published industry methodology ("the LI Schedule Grade").

## 1. Principles (what makes this defensible where Fuse's index isn't)

1. **Check-scored, not record-scored.**  Fuse's default Schedule Index scores
   each activity 0/1 on "trips any metric" — opaque, and one noisy metric
   dominates.  The Report Card scores *checks* against their published
   thresholds and aggregates with published weights, so the arithmetic from
   raw XER field to final grade is a chain anyone can recompute.
2. **Nothing hidden, nothing hardcoded.**  The scoring specification lives in
   a versioned, human-readable file (`scorecard.yaml`) shipped with the tool
   and printed in every card's appendix: per-check scoring curves, weights,
   category definitions, gates, and grade bands.  The card states its spec
   version (e.g., "LI-RC v1.0") and the input file hashes.
3. **Graded only on what applies.**  N/A and NOT EVALUATED checks leave the
   denominator entirely; every card states its coverage ("graded on 51 of 63
   checks; 12 not applicable to a baseline file").  A baseline is never
   penalized for having no execution history.
4. **Anti-gaming gates.**  A schedule cannot buy an A on volume of easy
   passes while its data is untrustworthy.  Integrity gates (below) cap
   category and overall grades, and the caps are published rules, not
   discretion.
5. **Two card variants.**  The *standard card* (report-safe) uses only
   matrix checks and neutral bespoke indices.  The *internal card* adds the
   provocative indices (SMI, DDI, ARR, RSA) and is privileged work product by
   default — same engine, different published profile.

## 2. Per-check scoring curve

Each threshold check converts its measured value to 0–100 conformance via a
piecewise-linear curve defined by three published anchors in
`scorecard.yaml`:

```
score(value) for direction=max checks:
  100  at value <= ideal          (default ideal = 0 or the standard's target)
   70  at value == threshold      (the published standard default = "just passing")
    0  at value >= fail_ceiling   (default 3x threshold; per-check overridable)
  linear interpolation between anchors; direction=min mirrored.
```

Rationale: the standard threshold is a *pass mark*, not excellence — meeting
DCMA's 5% open-ends limit exactly earns a C-, not an A.  Informational
metrics score only where the matrix defines bands (e.g., logic density 2–4);
otherwise they inform the narrative, not the grade.  Boolean checks (zero
tolerances) score 100 clean / step down per offender count relative to
population (published step).

## 3. Categories — per-schedule card

| Category | Member checks (matrix IDs) | Default weight |
|---|---|---|
| Logic & Network Integrity | DCMA-01..04, LOG-01..06, LOG-08..10, REL-01 | 25 |
| Constraint & Float Discipline | DCMA-05..07, CON-01..03, FLT-01..03 | 20 |
| Duration & Estimating | DCMA-08, DUR-01..03 | 10 |
| Status & Data Integrity | DCMA-09, DAT-01..05, RES-02, LOG-07 | 20 |
| Modeling Mechanics (calendars/structure) | CAL-01..05, CP-01, STR-01..03, RES-01 | 10 |
| Resource & Cost Loading | DCMA-10 (+ coverage %) | 5 |
| Execution Performance *(update files only)* | DCMA-11, DCMA-13, DCMA-14, PRG-01 | 10 |

Weights are per-profile: the **Baseline profile** redistributes Execution
Performance's weight across the first five categories; the **Update profile**
is as shown.  Category score = weight-normalized mean of member check scores
(member weights default to severity: critical 3, warning 2, banded-info 1).

**Overall (per-schedule) = Σ category score × category weight / Σ weights,**
then letter grade: A ≥ 90, A− ≥ 85, B+ ≥ 80, B ≥ 75, C+ ≥ 70, C ≥ 60,
D ≥ 50, F < 50.  (Fuse-continuity note in the appendix: Fuse's "good" band
>75 ≈ B.)

**Integrity gates (published caps):**
- DCMA-09 (invalid dates) or DAT-01 (status contradictions) scoring 0
  → Status & Data Integrity capped at 40 and overall capped at C+.  You
  cannot grade well on data you cannot trust.
- DCMA-12 continuity break unresolved → Logic & Network Integrity capped at
  60.
- Gate trips are printed on the card face with the rule cited.

## 4. Series report card (the overall card)

Adds four series categories over the same machinery, graded from series
checks and the bespoke indices:

| Series category | Members | Weight |
|---|---|---|
| Update & Record Discipline | TRD-05 (gate), SET-01, CAL-04, DAT-04, cadence (D1) | 25 |
| Plan Stability | LHL, PCI, TRD-02, TRD-03, TRD-07, BDI | 20 |
| Float & Progress Management | FCBI, TRD-01, BWI, IL, evergreen count | 20 |
| Forecast Credibility | FRB, RDI, CEI (EVM-02), Hit Task (EVM-01), TRD-04, ES/TSPI(t) | 20 |
| File-quality trajectory | per-file overall grades: level (mean) + slope (improving/deteriorating) | 15 |

**Overall series grade** = weighted blend as above, with the trajectory
category carrying both the average per-file grade and its direction (a C
portfolio improving each update reads very differently from a B portfolio
deteriorating — the card shows the arrow and grades the slope).
**Series gate:** any retroactive actual-date change (TRD-05) unexplained
caps Update & Record Discipline at 40 and the overall series grade at C+ —
the as-built record is the foundation of everything else.

Bespoke indices are normalized to 0–100 by published mappings (e.g., LHL:
100 at half-life ≥ remaining duration, 70 at ≥ 6 months, 0 at ≤ 1 month;
FRB: scored on band width relative to forecast horizon; each mapping lives
in `scorecard.yaml` with its rationale line).

## 5. The card itself

Per-schedule card (one page, LI style, first page of the Word report + a
standalone PDF/PNG exhibit + Excel sheet + GUI panel):

```
┌──────────────────────────────────────────────────────────────┐
│  LI SCHEDULE REPORT CARD          DEMO-PLANT — UPD 07 (DD 07 Jul 2025)
│  OVERALL: C-  (61/100)   spec LI-RC v1.0 · graded 51/63 checks
│  GATE TRIPPED: DCMA-09 invalid dates → overall capped C+
│  ──────────────────────────────────────────────
│  Logic & Network Integrity      B   78   ▼ from B+ 
│  Constraint & Float Discipline  D   52   ▼▼
│  Duration & Estimating          B-  72   –
│  Status & Data Integrity        F   38   GATE
│  Modeling Mechanics             C   64   –
│  Resource & Cost Loading        D   45   –
│  Execution Performance          C-  58   ▼
│  ──────────────────────────────────────────────
│  TOP FACTORS AFFECTING THIS GRADE (points lost · check · offenders)
│   −9.2  DCMA-07 negative float           10 activities
│   −6.8  DCMA-09 invalid dates            2 conditions (gate)
│   −5.1  DCMA-01 missing logic            4 activities
│   ...full decomposition in appendix; every row links to the
│      results workbook offender list
└──────────────────────────────────────────────────────────────┘
```

The **"top factors"** block is the credit-report reason-code pattern: the
card is never just a number — it always says where the points went.  The
series card mirrors this with per-update grade trend, series categories, the
arrow, and its own top factors.

## 6. Transparency & open-source mechanics

- `scorecard.yaml` — the complete scoring spec (curves, weights, gates,
  bands, index normalizations), versioned independently of the tool
  (LI-RC vX.Y), changelog required for any change (GOVERNANCE.md §1 extends
  to it).  Every card prints its spec version; the reproducibility capsule
  includes the spec file and its hash.
- Scoring engine reads ONLY matrix results + spec — no hidden inputs — and
  emits a `score_trace.json` with every intermediate number, so a third
  party can verify the grade from the workbook alone.
- **Publication decision (for the principal):** publish the spec + a minimal reference
  scorer as a public repository under an open license (Apache-2.0), while
  ScheduleIQ remains proprietary.  Precedent: DCMA's 14-point is public and
  tools compete on implementation.  Upside: "the LI Schedule Grade" becomes
  citable/adoptable, and opposing experts recomputing our grade and getting
  the same number is the strongest possible validation.  Downside:
  competitors adopt the spec.  Recommendation: publish the spec and
  reference scorer; keep the analytics that feed the bespoke indices
  proprietary (the spec defines their normalization, not their computation).

## 7. Relationship to the v0.1 health score

The Report Card supersedes the health score as the headline number.  The
health score remains computed (internal triage continuity and backward
comparability of early runs) but leaves the report face; METHODOLOGY.md
gains a migration note.

## 8. Build plan (backlog RC1–RC6)

| # | Item | Depends on |
|---|---|---|
| RC1 | `scorecard.yaml` spec v1.0: curves, weights, categories, gates, bands, index normalizations, per-profile weight sets | matrix (done) |
| RC2 | Scoring engine (`scheduleiq/scorecard.py`): spec-driven, emits ScoreCard objects + score_trace.json | RC1 |
| RC3 | Per-schedule card outputs: report first page, standalone exhibit, Excel sheet, GUI panel | RC2 |
| RC4 | Series card (adds series categories + trajectory + gates) | RC2; bespoke metrics N6–N15 as they land (engine degrades gracefully: ungraded members leave the denominator until built) |
| RC5 | Internal-variant card (adds N16–N20 when approved/built); privileged output flag | RC2 |
| RC6 | Publication decision + public spec repo (if approved) | RC1 stable |

Sequencing note: RC1–RC3 can build immediately against the 63 existing
checks; series-category members fill in as v0.2b/v0.2c metrics land, with
coverage % keeping the grades honest in the interim.
