# ScheduleIQ v0.2+ — Analytical Features Proposal

**Status: FOR REVIEW — nothing here is implemented yet.**  This document
proposes the analytical layer on top of the v0.1.0 check engine: milestone
impact tracing, multi-path analytics, delay-analysis accelerators (including
an AACE 29R-03 MIP 3.4 half-step engine), and Monte Carlo simulation.
Prepared from the perspective of an expert schedule delay analyst receiving a
client's schedule set ahead of a formal delay analysis.

---

## 0. The enabling decision: a diagnostic CPM engine (ADR-0007, proposed)

Almost everything below requires the ability to recompute schedule dates:
quantifying an issue's impact means asking "what would the milestone date be
*without* the issue?", half-stepping means rescheduling update *n*'s network
with update *n+1*'s progress, and Monte Carlo means rescheduling thousands of
times.  ADR-0004 (no CPM engine) was right for v0.1's *reporting* mission and
remains right for it — but it caps the analytical mission.

**Proposal — amend, don't repeal.  And do not build: PORT.**

The firm already owns a production-quality engine: the LI-proprietary
**mip39-schedule-analysis-tool** contains a well-isolated ~2,500-SLOC core —
full PDM forward/backward pass (FS/SS/FF/SF, positive/negative lags),
per-activity multi-calendar with holiday exceptions, actual-date-anchored
ABCS destatusing (six CPW rules), AACE 49R-06 longest-path extraction,
out-of-sequence rectification, and a CPW-equivalence validation framework
that has reproduced validation windows exactly against P6.  This is the
plan of record already written in expert-assist's parking lot (item B1:
port models, engine, longest_path, calendar_ops/registry, conventions,
lag/relationship logic, clndr_parser into a `lib/cpm/`-style package and
re-run its P6-equivalence validation).  Estimated 2–3 days versus weeks to
build and validate from scratch.

Gaps to close during the port (from the tool's own limitation register):

- **LIM-028 — constraints detected but not scheduled.**  Must be added for
  ScheduleIQ: without constraint scheduling the validation handshake would
  fail on any constrained schedule, and the constraint-removal deltas in §1.2
  need a constrained baseline to measure from.
- **LIM-045 — per-relationship lag calendars** (P6 lag-calendar setting is
  already captured by our XER parser's SCHEDOPTIONS read; the engine needs to
  honor it).
- **LIM-044 — calendar-day comparison tolerance** carries over into the
  handshake's tolerance configuration.

Porting also brings ABCS destatusing and longest-path extraction, which
upgrade §2.6 (as-built path reconstruction) and the §3.2 half-step engine
from "planned" to "mostly assembled."

1. Port the MIP 3.9 engine as `scheduleiq.cpm` (retaining its validation
   framework); add constraint scheduling and retained-logic /
   progress-override statusing modes.
2. Gate it behind a **validation handshake**: before any what-if or
   simulation is offered, the engine re-schedules the file *as imported* and
   compares its computed dates/floats to the tool-of-record values.  The
   match rate is reported (e.g., "1,247 of 1,251 activities within ±1h").
   Below a configurable threshold (default 99%), analytical features refuse
   to run and the mismatches are listed — which is itself a powerful
   diagnostic (unexplained dates usually mean hidden constraints, resource
   leveling, or external links).
3. Presentation rule: tool-of-record dates remain the only dates reported as
   *the schedule*; engine output is always labeled as a **diagnostic delta**
   ("removing X moves MS-100 by −12d"), never as a competing schedule.

This is exactly how Acumen Risk, Safran, and every credible SRA tool operate,
and the validation handshake is stronger than what they expose.  It converts
ADR-0004's risk (two sources of truth) into a check (SET-02 below).

---

## 1. Milestone Impact Tracing — "what is doing this to my date?"

Analyst selects a target: project completion or any milestone/activity.
Everything in this module is computed *to that target*.

### 1.1 Driving-path extraction (no CPM engine needed)
Backward walk from the target through *satisfied* relationships (predecessor
date + lag lands exactly on successor's early date, per relationship type and
calendar), cross-checked against P6's `driving_path_flag` where present.
Output: the driving path and near-driving alternates as a table ready for an
expert report — activity, duration, calendar, constraint, float, % complete,
and which relationship drives the next step.

### 1.2 Issue-impact overlay (per finding, quantified where possible)
For every v0.1 check finding, classify its relationship to the selected
target and quantify exposure:

| Issue | Quantification |
|---|---|
| Hard/soft constraint on or near the driving path | Constraint-free reschedule delta (engine): milestone movement if the constraint is removed; also "float absorbed" = constrained float − unconstrained float |
| Multi-calendar float distortion | Restate the path in calendar-neutral work-hours; report where hour-float and day-float diverge and by how much at the target ("float shown as 5d is 5×10h = 6.25 standard days") |
| Leads (negative lags) on the path | Compression contributed: Σ lead hours on the path, and reschedule delta with leads zeroed |
| Lags on the path | "Invisible scope": Σ lag hours as % of path length; delta with lags converted to activities of equal duration (visibility only) |
| Out-of-sequence progress | Reschedule under retained logic vs progress override; report the milestone delta between the two settings — the classic dispute number |
| Excessive logic revisions (from the change register) | Re-apply update *n+1* progress to update *n* logic (half-step, §3.2): the share of milestone movement caused by the revisions rather than performance |
| Expected Finish constraints | Delta with expected-finish overrides released to computed remaining durations |
| Open ends / dangling logic | Paths that *should* reach the target but don't; list of activities whose slippage is currently invisible to the target date |

The one-page output: **"Milestone MS-100 diagnostic"** — current date, the
driving path fingerprint, and a waterfall of diagnostic deltas (constraints
−12d, calendar normalization −3d, leads +4d, …).  This is the figure the
expert draws by hand today; nobody in the market automates it against a
selectable milestone.

## 2. Multi-Path Analytics

1. **Top-N float paths** to the selected target (P6 "multiple float paths"
   style): rank by relative float, show composition, calendars, constraints,
   progress — with N and the near-critical band analyst-configurable.
2. **Path proximity profile**: distribution of sub-critical paths within 5 /
   10 / 20 days of the target — a schedule with 14 paths inside 10 days is a
   volatility warning for any windows analysis (and a merge-bias flag for
   the SRA module).
3. **True merge-point ranking**: merge nodes ranked by number and tightness
   of converging *near-critical* paths (not raw predecessor counts like
   Fuse's Merge Hotspot) — where the completion date is most fragile.
4. **Path stability across updates**: per update pair, did the driving path
   to the target change?  Attribute the flip: progress-driven (something got
   done/slipped) vs revision-driven (logic/constraint/calendar edits, from
   the change register).  Output a path-timeline chart: which path held
   criticality in each window — effectively the skeleton of a windows
   analysis before the analyst starts.
5. **Constraint-free criticality**: recompute float with constraints
   released (engine); activities whose criticality is manufactured by
   constraints vs genuine logic — "the 58% critical figure collapses to 12%
   without the Mandatory Finish."
6. **As-built path reconstruction** (retrospective): longest continuous
   chain through actualized relationships — a defensible starting point for
   as-built critical path methods (MIP 3.1/3.5 support) with every link
   traceable to actual dates.

## 3. Delay-Analysis Accelerators — what the expert wants before diving in

### 3.1 Intake pack (no engine needed — high value, low effort)
- **Data-completeness scorecard & RFI generator**: update cadence gaps,
  missing months, baseline availability, format mix, native-vs-PDF, missing
  SCHEDOPTIONS — auto-drafts the "documents to request from client" list.
  Every engagement starts with this memo; generating it from the files
  themselves saves a day and misses nothing.
- **As-planned vs as-built variance register**: per activity — baseline vs
  actual dates and durations, variance in working days on its own calendar,
  sorted by driving-path membership.  The raw material of every method.
- **Float consumption ledger**: per path and per activity, who consumed
  float, in which window, recoverable or not — with the classic
  float-erosion-by-window chart.
- **Windows auto-segmentation**: propose analysis window boundaries from
  data-date cadence + driving-path change points + major revision events;
  analyst adjusts.  Feeds MIP 3.2–3.4 directly.
- **Concurrency screening**: windows where two or more near-critical paths
  slipped together, with the paths and slip magnitudes — a candidate list
  for the concurrency review (expressly labeled preliminary/reserved).
- **Delay-event mapper**: import an event list (CSV: event, dates, keywords,
  responsibility); map to activities by date overlap + WBS/keyword match;
  output candidate fragnet insertion points for TIA work (MIP 3.6/3.7) and
  an event-vs-driving-path timeline figure.
- **Responsibility overlay**: analyst tags WBS nodes/activities
  (Owner/Contractor/Neutral/TBD); every window and path output can then be
  cut by responsibility — *presented as data aggregation only; the
  entitlement opinion stays with the expert.*
- **"Evergreen activity" detector**: percent complete creeping up across
  updates with no commensurate remaining-duration reduction or date
  movement — statused-on-paper work that poisons EV and progress narratives.

### 3.2 MIP 3.4 half-step engine (the headline accelerator; needs engine)
AACE 29R-03 MIP 3.4 (observational / dynamic / contemporaneous split)
requires, for each update pair, separating end-date movement into
**progress** and **revision** components via bifurcation:

1. Take update *n*; apply *only* the progress recorded in update *n+1*
   (actual dates, remaining durations, % complete) → reschedule → the
   **half-step schedule**.  Movement vs update *n* = performance effect.
2. Compare the half-step to update *n+1* as submitted: remaining movement =
   the revisions (logic, durations, calendars, constraints, scope), each of
   which is already itemized by our change register — so every revision-side
   day is traceable to named edits.
3. Output per window: milestone movement decomposed (progress vs revision,
   with the top contributing activities/edits for each), cumulatively across
   the project — the complete numerical backbone of a MIP 3.4 analysis,
   with an equivalent "as-is" table for MIP 3.3.

Fuse's Forensics half-step is the nearest competitor; ours adds the named
revision attribution (because the change register drives it) and the
milestone selectability.

### 3.3 Update-integrity forensics (new checks; mostly no engine)
Proposed additions to the matrix (v0.2 rows, references to be finalized):

| ID | Check | Why the analyst cares |
|---|---|---|
| SET-01 | Scheduling-settings drift between updates (retained logic ↔ progress override, lag calendar, critical definition) | A settings flip silently changes every forecast date — classic "recovery by settings" |
| SET-02 | Tool-of-record vs diagnostic-engine date match rate | Unexplained dates = hidden leveling/constraints/external links (the ADR-0007 handshake, exposed as a check) |
| CAL-04 | Calendar *definition* changes between updates (workweek/holiday edits) | Editing a calendar re-times every assigned activity without touching one duration — near-invisible today |
| CAL-05 | Quantified multi-calendar float distortion at the selected milestone | The §1.2 calendar overlay as a standing metric |
| LOG-10 | "Hollow logic" screen: near-zero-duration/logic-only activities inserted that re-route the driving path | Retrospective path engineering ahead of a claim |
| DUR-04 | Remaining-duration compression without progress ("RD shrink") | Schedule crashing on paper to hold a date |
| DAT-05 | Actual-duration anomalies (AF < AS, zero-duration actuals on tasks, actuals before NTP) | As-built corruption screens |
| STR-03 | WBS re-parenting churn between updates | Scope re-mapping that breaks vertical traceability |
| REL-01 | Relationships referencing missing activities (zombie logic in XER) | Export corruption / partial deletes |
| FLT-03 | Float greater than remaining project duration | Mathematically impossible float = calendar/constraint artifacts |

## 4. Monte Carlo (SRA) module — needs engine

- **Inputs**, three tiers: (a) global uncertainty templates by activity
  type/WBS (±% bands); (b) per-activity 3-point import (CSV/Excel);
  (c) **empirical calibration from the project's own history** — the
  distribution of actual÷planned duration ratios harvested from the update
  series, applied to remaining work.  Tier (c) is the differentiator: "at
  this project's demonstrated performance, P80 completion is …" is a far
  more defensible statement than invented ranges, and no mainstream tool
  automates it from the update files.
- **Model**: triangular/PERT/uniform distributions; systemic correlation
  factor; optional risk-event register (probability × impact fragnets);
  Latin Hypercube sampling; run against the diagnostic engine on the
  analyst-selected milestone.
- **Outputs**: S-curve with P10/P50/P80 vs deterministic date; tornado
  (duration-sensitivity correlation); **criticality index** (% of iterations
  on the critical path) and cruciality per activity; merge-bias exhibit
  (deterministic vs probabilistic dates at the top merge points from §2.3);
  all charts in LI style for direct report use.
- **SRA-readiness gate**: refuses to simulate (or brands output DIAGNOSTIC
  ONLY) until the schedule passes the leads/hard-constraint/open-end screens
  — mirroring Fuse/Acumen practice and protecting the expert from
  garbage-in simulation.
- **Delay-work uses**: forecast-realism due diligence at intake; prospective
  TIA support; reviewing/rebutting an opposing expert's SRA (re-run their
  model shape on validated inputs; the criticality index also
  cross-validates our multi-path rankings).

## 5. Suggested phasing

| Phase | Contents | Dependency |
|---|---|---|
| v0.2 | §3.1 intake pack; §2.1–2.3 path analytics (float-path walk); §3.3 new checks except SET-02; §1.1 driving-path fingerprint | None (current architecture) |
| v0.3 | ADR-0007 diagnostic CPM engine + validation handshake (SET-02); §1.2 impact waterfall; constraint-free criticality; OOS settings delta | Engine |
| v0.4 | MIP 3.4 half-step engine + windows outputs; path stability attribution | Engine + change register (done) |
| v0.5 | Monte Carlo module | Engine |

Each phase ships behind the same governance: matrix rows + references first,
implementations + seeded fixtures + tests together, methodology notes updated
(GOVERNANCE.md §1).

---

## 6. Cutting-edge additions (second brainstorm, for review)

### 6.1 Editing-session forensics ("who touched what, when") — unique, low effort
XER TASK rows carry `create_date`, `create_user`, `update_date`, and
`update_user`.  Nobody in the mainstream market mines them.  Proposed module:
reconstruct editing sessions per update file (cluster activities by
update-user and update-timestamp), then flag: bulk edit sessions dated just
before a submission or claim; edits by unusual users; activities whose logic
was edited in the same session their actuals were entered; edit activity on
the driving path vs elsewhere.  Output: an editing-timeline exhibit per
update.  This is discovery-grade material produced from files the client
already handed over.

### 6.2 Statistical manipulation screens
- Benford/last-digit and round-number analysis on durations, lags, and
  reported percent-complete distributions — manufactured data leaves
  signatures (e.g., % complete clustered at 5% steps with no 100s).
- Duration-distribution drift between updates (K-S distance) localized to
  claim windows.
- "Progress physics": implied production rates (units or cost per period
  from TASKRSRC) vs the project's demonstrated best rates — flags remaining
  work planned at rates never achieved (recovery-schedule realism, and the
  factual skeleton of acceleration/disruption arguments).

### 6.3 Pacing and acceleration screens (expert-grade heuristics, labeled preliminary)
- **Pacing candidates**: non-critical chains that decelerated (RD growth,
  reduced concurrent resources) during windows when a parallel critical
  delay was running — the pacing-defense screen, with the contemporaneous
  float relationship documented per SCL/industry pacing criteria.
- **Constructive acceleration candidates**: windows following denied/late
  EOT signals (from the delay-event list) showing duration compression +
  resource increases + OOS spikes + overtime-calendar switches.

### 6.4 Earned-schedule forecast credibility
ES(t), SPI(t), TSPI(t), and IEAC(t) computed from the update series (planned
value from baseline dates; earned from progress), giving an
independent completion forecast to set against the CPM forecast each period.
A widening gap between the earned-schedule forecast and the schedule's own
forecast is a per-window "forecast credibility" exhibit — and TSPI(t) > 1.10
while the contractor holds the date is the classic tell.

### 6.5 Push-button TIA workbench (MIP 3.6/3.7)
With the ported engine + the delay-event mapper: select events → auto-build
fragnets at mapped insertion points → impact each contemporaneous update →
period impact table with LD exposure.  The parking lot already anticipates
this ("push-button TIA").  Collapsed as-built (MIP 3.8/3.9) follows from the
same machinery run subtractively — the engine's destatusing core was built
for exactly this.

### 6.6 Damages/exposure overlay
Translate any P-date or diagnostic delta into money: analyst enters the LD
rate / time-related cost per period; every waterfall, window table, and
S-curve gains an exposure axis.  Trivial to build, disproportionate impact
in settlement discussions.

### 6.7 Interactive network cockpit + LI demonstratives
- A self-contained HTML explorer (no install, works for counsel) per run:
  zoomable time-scaled network of the driving/near-critical paths, sliders
  across updates, click-through from any check finding to its activities.
- Automated LI-style demonstratives via the firm's graphics-generator
  pipeline: windows summary bars, float-erosion ribbons, path-evolution
  storyboards — tribunal-ready figures generated from the same verified data
  as the report tables.

### 6.8 Narrative reconciliation (ties into expert-assist)
Cross-check the schedule data against the monthly narrative PDFs already
mined by expert-assist (contradiction-finder): claimed progress/completion
dates in narratives vs the XER record; retroactive actual-date changes
(TRD-05) vs what was reported to the owner at the time.  Each contradiction
is a cross-examination exhibit.

### 6.9 Internal benchmark corpus (offline, ADR-0006-compliant)
Persist anonymized metric outcomes per reviewed project (locally/Synology)
to give context lines on every chart: "this schedule's logic quality is in
the bottom quartile of process-plant schedules LI has reviewed."  Defensible
because it is the firm's own documented review history.

### 6.10 Research track (flagged, not committed)
Survival-analysis / ML duration models trained on the firm's corpus for
duration-uncertainty priors, and LLM-drafted quality narratives wired into
expert-assist's verification gates (draft cites only checked numbers; the
gate blocks anything unverified).  Both deliberately behind the governance
wall: no black-box number may reach a report.

## 7. Revised phasing (with the ported engine)

| Phase | Contents |
|---|---|
| v0.2 | Intake pack (§3.1), path analytics (§2.1–2.3), new checks (§3.3), editing-session forensics (§6.1), statistical screens (§6.2), earned schedule (§6.4) |
| v0.3 | **Port MIP 3.9 engine** + constraint scheduling + validation handshake (SET-02); impact waterfall (§1.2); constraint-free criticality; OOS settings delta; exposure overlay (§6.6) |
| v0.4 | MIP 3.4 half-step + windows outputs; pacing/acceleration screens (§6.3); as-built path via ported ABCS core; HTML cockpit (§6.7) |
| v0.5 | Monte Carlo (§4) with empirical calibration; TIA workbench (§6.5); collapsed as-built support |
| v0.6+ | Narrative reconciliation (§6.8), benchmark corpus (§6.9), research track (§6.10) |

---

## 8. Third brainstorm — five further cutting-edge ideas (2026-07-07, for review)

### 8.1 Weather & external-conditions overlay
Excusable-delay screening from authoritative data: import historical weather
for the project location (NOAA/GHCN daily records, or regional equivalents),
then (a) test **calendar realism** — do the schedule's calendars embed the
weather downtime the contract/geography implies, month by month; (b) compute
**abnormal weather** per period vs the 10-year norm (the usual contractual
test) and overlay it on the as-built slippage of weather-sensitive work
(tagged by WBS/keyword); (c) auto-draft the weather-delay exhibit: period,
norm, actual, exceedance, affected driving-path activities.  Weather is the
most common excusable-event category and today this table is assembled by
hand on every matter.  (Runs offline from a downloaded station file —
ADR-0006 intact.)

### 8.2 As-built work-pattern reconstruction
Infer the **de facto working calendar** from the data itself: distributions
of actual starts/finishes by day-of-week and date, resource actual units per
period, and progress deltas between updates.  Products: detection of weekend/
overtime working (acceleration evidence, and a cross-check on §6.3's
constructive-acceleration screen); detection of dormant spans on critical
chains (suspension/disruption evidence); planned-vs-actual calendar
divergence per trade ("the schedule assumed 6-day weeks; the record shows
5"); and a work-intensity heatmap exhibit per window.  Turns timestamps the
files already contain into disruption-grade evidence.

### 8.3 Daily-resolution delay ledger ("continuous windows")
With the ported engine: interpolate progress between consecutive updates and
reschedule at **daily** steps, producing a day-by-day ledger of critical-path
delay and recovery attributable to that day's progress state.  This is the
"daily windows / continuous delay measure" technique — it eliminates the
window-boundary judgment calls that opposing experts attack, makes
concurrency visible at the resolution where it actually happens, and sums
exactly to the per-update movement (a built-in arithmetic check).  Output:
daily delay ledger, cumulative delay curve annotated with events (from D6),
and per-responsibility subtotals via the D7 overlay.

### 8.4 Methodology-robustness certificate
Before an opinion is committed, stress-test it: re-run the delay measurement
under perturbed window boundaries (±1 update), alternative statusing
settings (retained logic vs progress override), MIP 3.3 vs 3.4 framing, and
with/without contested revisions — and report how stable the attribution is
("Contractor-responsible delay ranges 31–34 days across all 12 method
variants").  A conclusion that survives the sweep is armored against the
"you cherry-picked your windows" cross-examination; one that doesn't is a
warning the expert wants *before* signing.  No competitor offers sensitivity
analysis of the **method** rather than the schedule.

### 8.5 Reproducibility capsule & evidence sealing
One-click sealed package per analysis: hash-tree manifest of every input,
intermediate, and output (extending the existing audit log), pinned tool
version and threshold profile, and a deterministic re-run script — so the
tribunal or opposing expert can re-execute the entire analysis and obtain
bit-identical numbers.  Turns "trust our workings" into "run our workings,"
which is a materially stronger position for expert evidence and a
differentiator no schedule tool currently offers.

*Backlog mapping: N1–N5 in docs/BACKLOG.md (PARKED pending review).*

---

## 9. Bespoke Long International metrics — five never-before-seen indices (2026-07-07, for review)

Design constraints for all five: a single defensible number per update/window,
computed from data the client already produced, decomposable to named
activities (an index the expert cannot explain activity-by-activity is a
liability), and trackable as a curve across the project.  These are
candidates for LI-proprietary branding, as Deltek brands Logic Density™ and
Merge Hotspot™.

### 9.1 FCBI — Float Criticality Burn Index  (LI concept, formalized)
Float consumption weighted by how critical the float was.  Per window, for
each activity in both updates: consumption c = max(0, −ΔTF) in working days
(calendar-neutralized); weight w = 2^(−RF/λ), where RF = relative float of
the least-float path through the activity (from the float-path module) and
λ = half-weight constant (default 5 wd: float 5 days off the driving path
counts half, 10 days counts quarter; driving-path float counts full).
**FCBI(window) = Σ c·w**; normalized form FCBI% = share of the
criticality-weighted float stock burned in the window.  Regained float is
tracked separately (FCBI⁻) rather than netted, so recovery cannot mask burn.
Decomposes exactly into a top-burners table and cuts by the responsibility
overlay.  Guard: activities whose criticality is manufactured by constraints
(per constraint-free criticality) are flagged in the decomposition so the
index cannot be gamed by constraint placement.  The cumulative FCBI curve is
"the float story of the project in one line."

**Implementation conventions (v0.4.1; per the FCBI audit rulings —
docs/audit/FCBI_audit_2026-07-08.md.  v0.4.2 adds the LOE rule below, per the
RDI/BWI/CDI audit — docs/audit/RDI_BWI_CDI_audit_2026-07-08.md).**
- *LOE, WBS-summary, hammock, and other summary activities are excluded* from
  both burn and FCBI⁻: they are not discrete executable work and carry no
  project criticality.  This rule applies uniformly to every LI index that
  measures criticality, float consumption, recovery, or criticality-time
  (FCBI, PCI, CDI, RDI, BWI); it is enforced at the shared criticality kernel.
- *Completed activities are excluded* from both burn and FCBI⁻: FCBI measures
  float consumed by **in-flight** work, so an activity's float ending at
  completion is not scored as burn (which also removes the exporter-dependent
  phantom burn when a tool writes 0 rather than null for a completed
  activity's float).  This aligns FCBI with RDI and BWI (live-work indices);
  **CDI intentionally keeps completed activities** because it measures where
  criticality *dwelt* over time, including on now-finished work — a
  retrospective, not forward, question.
- *Weight timing:* RF is sampled as **min(RF_{u-1}, RF_u)** across the window,
  so float that was near-critical at *either* end of the interval is weighted
  at that criticality (burn that itself drove a chain critical is not
  under-weighted by its floaty start).
- *RF provenance:* RF is the minimum relative float over the **top-10** float
  paths containing the activity (its own total float when on no enumerated
  path); the driving path is the tool-of-record's minimum-float chain, not a
  CPM pass — so RF is independent of the diagnostic engine's statusing mode.
- *Normalized form:* FCBI% is reported **undefined** (a labelled sentinel, not
  0) when the criticality-weighted live float stock at the window start is ≤ 0.
- *Windowing:* FCBI⁺ is windowing-dependent and **not additive** across merged
  windows (max(0, −ΔTF) is a total-variation measure); compare only
  like-for-like update cadences.

### 9.2 LHL — Logic Half-Life
Survival analysis on relationships: each relationship ever observed has a
lifespan (updates until deleted or modified); Kaplan-Meier over the series
(censored at the last update) gives the **median survival of a logic tie, in
months** — the schedule's planning stability in one number.  A 24-month
programme whose logic half-life is 3 months is a rolling narrative, not a
plan.  Report the on-driving-path vs off-path ratio: driving-path logic
should be MORE stable than average; when it is less stable, the path itself
is being re-engineered — exactly where a delay analyst should dig.  First
update pair excluded by default (baseline development noise), stated in the
methodology.

### 9.3 FRB — Forecast Reliability Band
An empirical error bar on this scheduler's forecasts, from their own track
record: for every update and every activity that later finished, forecast
error = actual finish − forecast finish (working days), bucketed by forecast
horizon.  **FRB80(h) = the central-80% error interval at horizon h**, split
into bias (median — systematic optimism) and dispersion (band width —
noise).  Applied forward: "the schedule says 15 March; this project's
demonstrated 3-month-horizon band puts P80 at 23 April."  No distributions
assumed, no simulation — purely the record, which makes it very hard to
rebut.  Complements CEI (binary, one period) and Monte Carlo (model-based);
also calibrates the MC module's empirical mode.

### 9.4 PCI — Path Concentration Index
How concentrated the project's fate is across its near-critical paths:
weight each top-N float path by the same exponential criticality kernel as
FCBI; **PCI = Herfindahl index of the weight shares** (→1 = single-threaded:
one chain controls completion, attribution clean, schedule fragile; low =
diffuse near-criticality: path flips and concurrency exposure ahead).
Tracked per window, a falling PCI is an early warning of critical-path
instability BEFORE the flip happens (TRD-02 sees it only after); a sudden
PCI rise coinciding with logic churn suggests engineered path consolidation.
Directly informs method selection (low-PCI projects need daily-resolution or
split methods, not snapshot TIA) and where SRA effort matters.
*Convention (v0.4.2):* paths with no discrete-work member — pure LOE/summary
or bare-milestone chains — are excluded so summary activities cannot
manufacture a spurious near-critical path and dilute the concentration.

*Mixed-path LOE neutralization (v0.4.3).* The v0.4.2 exclusion dropped paths
that carry *no* discrete work but did not change how a *kept* mixed path's
relative float was computed, so an LOE that was the lowest-float member of a
mixed path still drove that path's relative float — and the relative-float basis
(RF) of the discrete member on it.  v0.4.3 closes this: the LI kernel computes an
**LI-specific per-path relative float over the path's discrete members only**
(`relative_float_map` / `_li_path_rel_float`), so an LOE no longer influences a
discrete activity's RF.  This is layered on top of the enumerator — the shared
`float_paths()` is **untouched** (it still feeds the tool-of-record driving-path
analytics unchanged; the LI kernel only reads its additive `unique_uids`
metadata).  A regression test
(`test_pci_mixed_path_loe_neutralized_in_kernel`) pins the neutralization while
asserting `float_paths()` itself is unchanged.

### 9.5 RDI — Recovery Debt Index
Cumulative gap between promised and demonstrated pace.  Each update implies
a required future pace to hold its forecast finish (remaining driving/near-
critical work per remaining working time); compare against the pace actually
demonstrated over trailing windows.  Debt accrues each window the required
pace exceeds the **P50 (median) demonstrated pace** — the pace the Project
has *sustainably* shown, not the single best window it ever hit:
**RDI = Σ max(0, required − demonstrated_P50) × window length**, in days.
*Convention (v0.4.3, R2 ruling):* the accrual anchor is the running P50 of
the demonstrated series (the old max-only anchor under-accrued — it forgave
any required pace below the single best window ever); the running max is
retained and reported as the optimistic bound.  RDI is the portion of the
current completion forecast resting on unproven acceleration.  A finish date
that holds steady while RDI climbs is being defended by paper productivity
(pairs with DUR-04 and the evergreen detector); at project end, realized
slip ≈ RDI is a self-validating exhibit of sustained forecast unrealism.

*Open item (R1, pending ruling):* whether "demonstrated pace" is measured as
planned scope retired per window (current) or actual-elapsed throughput is a
separate methodology decision, not yet resolved.

*Backlog: N6-N10 (PARKED pending review).  Dependencies: all five compute
from existing modules (float paths, change register, actuals, resources);
none requires the CPM engine.*

---

## 10. Bespoke LI metrics — second set (2026-07-07, for review)

Same design constraints as §9: one defensible number, decomposable to named
activities, trackable across windows, computable from the produced files.

### 10.1 BDI — Baseline Dilution Index
How much of today's completion story was never in the contract baseline.
Take the current driving path to the selected milestone; classify each step's
working-day length as baseline-original (activity existed in the baseline
AND arrived on the path via logic that existed in the baseline) or
post-baseline (added activity, or added/modified relationship).
**BDI = % of driving-path length attributable to post-baseline elements.**
Rising BDI means variance-against-baseline arguments are progressively about
work and logic the baseline never contained — the quantified trigger for
re-baselining questions, and a one-number rebuttal ("the claimed critical
delay runs 70% through scope the baseline never had").  Decomposes into the
named added activities/logic with the update in which each arrived (change
register).

### 10.2 CDI — Criticality Dwell Index
Who carried the project's risk, and for how long.  For every window, allocate
one unit of criticality across activities in the near-critical band using the
§9.1 exponential kernel; accumulate across the series.  An activity's CDI is
its share of total project criticality-time; the leaderboard is the delay
analysis's cast of characters BEFORE any method is run ("these 12 activities
held 80% of the project's criticality-time").  Project-level scalar:
concentration of dwell (top-decile share).  Sharp forensic corollary: an
activity with near-zero dwell that suddenly hosts a major claimed delay is a
red flag; a high-dwell activity that never appears in the claim narrative is
a gap in the other side's story.
*Conventions (v0.4.2):* LOE/summary activities are excluded (not discrete
work).  **Completed activities are retained** — CDI is a *retrospective*
criticality-time measure (where risk dwelt over the project's life, including
now-finished work), which is why, unlike the forward-looking FCBI/RDI/BWI, it
does not drop completed activities.

### 10.3 IL — Intervention Latency
How long problems stayed visible before the schedule shows a response.  For
each emergence event (a path entering negative float, or an activity chain
tripping FAIL-severity checks), scan subsequent updates for responsive edits
on that chain — logic resequencing, resource additions, calendar upgrades,
duration compression, or a recovery re-baseline — and measure
**median updates (and calendar days) from emergence to response**.  Long IL
quantifies failure-to-mitigate; short IL with ineffective responses (float
keeps eroding) distinguishes "didn't act" from "acted and it didn't work" —
a distinction tribunals care about and nobody measures.  Decomposes into an
emergence/response event log per path, each entry naming the triggering
finding and the responsive edits (from the change register).

### 10.4 BWI — Bow-Wave Index
Quantifies work piling up against a milestone.  For a selected milestone: per
update, compute remaining near-critical work volume ahead of the milestone,
divided by a **fixed reference horizon**, normalized to the first update.
*Convention (v0.4.3, B1 ruling):* the denominator is held constant across
updates — working days from the first update's data date to the target's
constrained (promised) date, else its baseline finish, else its first-update
forecast finish — so that "working days to target" no longer moves.  This
isolates the numerator (near-critical work packed ahead of the milestone); a
milestone that *slips* while the work is unchanged now reads BWI = 1.0, where
the old moving-forecast denominator mis-read a slip as relief (BWI < 1.0).
**BWI > 1 and rising = a bow wave: each update packs more work into the fixed
window to the promised date.**  The companion statistic is the projected break
date — the update at which required density exceeds anything the project has
demonstrated (ties to RDI's demonstrated-pace record).  The bow wave is the
most common real-world compression pathology; every expert describes it
narratively, none of the tools measure it.  Decomposes into the work packed
per window with the edits that packed it.

### 10.5 MML — Measured-Mile Locator
Automates the hardest part of a disruption analysis: finding the measured
mile.  For each WBS node / trade and each window, compute achieved
productivity (actual work-hours or activity-days completed per available
working period, from actuals and resource data) and its dispersion.  Scan all
window x trade cells for (a) the cleanest sustained period — stable, best
productivity, no mapped events — and (b) the most impacted periods.
**MML = the disruption contrast ratio (impacted productivity ÷ clean-period
productivity) per trade**, with the located candidate periods for the
measured-mile study.  Also emits the "no clean mile exists" finding — itself
decisive for method selection (forces earned-value or modeled approaches).
Labeled preliminary: period selection is confirmed by the expert; the tool's
contribution is exhaustively scanning every candidate period, which manual
practice never does.

*Backlog: N11-N15 (PARKED pending review).  All five compute from existing
modules; none requires the CPM engine (BWI and IL use the change register
and float paths; MML uses resource actuals where loaded, activity-days
otherwise).*

---

## 11. Bespoke LI metrics — third set: deeply analytical, deliberately provocative (2026-07-07, for review)

These five quantify things experts normally leave to instinct or advocacy.
Each carries real controversy, so each states its guardrails.  Common rules:
outputs are triage indicators labeled "observations consistent with…," never
findings of intent; every index decomposes to named, citable observations;
the tribunal-duty principle (evidence presented both ways) is built into the
output text, not left to the analyst's discipline.

### 11.1 SMI — Schedule Manipulation Indicator
One number for the question everyone asks first and answers by gut: "has this
schedule been curated for claims rather than managed for construction?"
Composite of the independent curation signals already computed — retroactive
actual-date changes (TRD-05), hollow logic (LOG-10), settings flips (SET-01),
calendar-definition edits (CAL-04), statistical anomalies (Benford/round-
number/pct-step), silent replans (DUR-03/-04), and churn concentrated
immediately before claim submissions — each scored for presence, severity,
and timing correlation, combined on a published weighting.
**Controversy**: it is a manipulation score, and the other side will say so.
**Guardrails**: named "indicator," reported only with its full decomposition;
every contributing signal has innocent explanations enumerated in the output
("retroactive corrections may reflect legitimate record cleanup — verify
against daily reports"); expressly excluded from report language stronger
than "warrants explanation."  Internally it is a triage instrument: a 15
means run the standard checks and move on; an 80 means budget for forensics.

### 11.2 DDI — Directed Date Index
Detects the signature of a dictated completion date: the finish (or a key
milestone) holds station update after update while every underlying
fundamental deteriorates — RDI climbing (recovery debt), BWI climbing (bow
wave), float sequestration (FCBI burn concentrated off the terminal path),
constraint additions near the target, and duration compressions without
scope relief.  **DDI = the number of consecutive updates the date has been
held multiplied by the mean deterioration z-score of the fundamentals over
that span** — high DDI reads "this date is an instruction, not a forecast."
**Controversy**: it infers organizational behavior (a directed date) from
data; contractors will call it speculation.  **Guardrails**: the index
claims only inconsistency between the held date and the schedule's own
fundamentals — the finding text is "the forecast completion is increasingly
unsupported by the schedule's internal indicators," which is defensible
arithmetic; why the date was held is expressly left open (owner pressure,
genuine recovery intent, or negotiation posture).

### 11.3 ARR — Attribution Robustness Ratio
Quantifies the strength of the delay case itself.  Run the attribution
(per-party delay by window, from the responsibility overlay) across every
defensible method variant in the N4 robustness sweep — window boundaries,
statusing settings, MIP 3.3 vs 3.4 framing, contested-revision treatment —
and report each party's attribution as a RANGE with
**ARR = narrowest-to-widest ratio (min share ÷ max share) per party**.
ARR near 1.0: the conclusion is method-independent — a strong case.  ARR of
0.3: the answer is mostly methodology — which both sides' experts should
know before trial, and which counsel needs for settlement strategy.
**Controversy**: experts avoid quantifying how contestable their own
conclusion is; a discoverable low ARR is ammunition.  **Guardrails**:
generated as privileged work product by default (separate output flag, not
in the standard report); the ethical position — knowing your conclusion's
robustness is required diligence, and an expert who won't compute it is
choosing not to know.

### 11.4 PPS — Pacing Plausibility Score
The pacing defense, scored instead of argued.  For each pacing candidate
(non-critical deceleration concurrent with a parent critical delay, from the
§6.3 screen), score the recognized criteria: did float demonstrably exist
when deceleration began; is there evidence of contemporaneous awareness of
the parent delay (event list/narrative reconciliation); was the deceleration
proportionate to the float available; was it reversible (resources
redeployed, not demobilized); did re-acceleration follow the parent delay's
resolution.  **PPS = weighted criteria score, 0–100, per pacing instance.**
**Controversy**: pacing is the most abused defense in delay practice;
scoring it cuts both ways — our clients' pacing claims get graded too.
**Guardrails**: criteria and weights published in the methodology docs and
sourced to the pacing literature; the score triages which pacing assertions
deserve expert investment, and the same table printed for an opposing
expert's pacing claim is a ready-made cross-examination.

### 11.5 RSA — Rebuttal Surface Area
An adversarial audit of a delay analysis — ours or theirs.  Decompose the
attributed delay into components and classify each: method-sensitive (the N4
sweep changes it), data-fragile (rests on records failing integrity checks —
retroactive actuals, statused-without-evidence, gaps in the update series),
path-ambiguous (low PCI in that window), or robust.
**RSA = the share of total attributed delay resting on contested ground**,
with the components named.  Run on our own draft, it is the pre-signature
audit that hardens the report; run on the opposing expert's analysis, it is
a cross-examination map — "62% of the claimed delay sits in windows where
his own method choices change the answer."
**Controversy**: it industrializes rebuttal, and a low-RSA opinion becomes a
marketing claim ("LI reports ship with a robustness audit").
**Guardrails**: symmetric by construction — the same arithmetic applies to
both sides' work; when run on our own analysis the output is privileged
work product by default, like ARR.

*Backlog: N16-N20 (PARKED pending review).  Dependencies: SMI/DDI/PPS
compute from existing modules; ARR and RSA require the N4 methodology sweep
(v0.4+).  All five default to privileged/internal output surfaces rather
than the standard report — deliberate, given their character.*
