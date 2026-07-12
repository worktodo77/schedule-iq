# The Contemporaneous Collapse Method (CCM) — Step-by-Step Methodology

**Working draft v0.1 (2026-07-12) — INTERNAL, for peer review.**  Companion
to `docs/AACE_CDR_PAPER_OPTIONS.md` §10–11, written tool-agnostically as the
paper's method section would be.  The core method uses no proprietary
index: longest path, a near-critical band, working-day arithmetic, a
version-to-version change register, and a validated CPM engine.

---

## 0. Purpose, placement, and claims

**Purpose.**  A retrospective delay analysis method designed to be run
window-by-window as a project executes (or in batch afterward), producing
for every window a balanced, party-attributed, concurrency-measuring
decomposition of milestone slip — from the contemporaneous schedule updates
the parties already exchange, with no analyst-constructed as-built model.

**Parentage.**  One element from each of three codified methods:
- Measurement from **MIP 3.3** (observational, dynamic, contemporaneous
  as-is): net slip measured from the updates as-is.
- Mechanism bifurcation from **MIP 3.4** (half-step): progress-driven vs.
  revision-driven slip separated by an intermediate schedule.
- Counterfactual party attribution from **MIP 3.9** (subtractive
  modeling): but-for extraction — but run one window deep on the
  contemporaneous update, never on a reconstructed as-built.

**Taxonomy placement.**  Hybrid: observational measurement with a modeled
attribution step, dynamic logic, multi-window.  Retrospective in the
29R-03 sense — each window is analyzed after it has occurred; nothing
requires the project to be complete.

**Scope boundary.**  CCM measures slip and attributes it to responsibility
codes and mechanisms.  Entitlement, concurrency doctrine, compensability,
and quantum are outside the method and reserved to the expert, tribunal,
or contract.

**Output-shape claim.**  Every window's outputs satisfy arithmetic
identities (§5.4) that any party can recheck; two practitioners applying
this protocol to the same files must produce identical tables (§8.1).

---

## 1. Definitions

| Term | Definition |
|---|---|
| Update *N* | The N-th contemporaneous schedule submission, with data date DD_N, as exchanged between the parties (tool-of-record file, unmodified). |
| Window *N* | The period DD_N → DD_N+1, analyzed from the update pair (N, N+1). |
| Tracked milestone *M* | Project completion or a contractual interim milestone selected in Phase A. |
| Measurement calendar | The calendar used to express all slip quantities in working days, **fixed at the baseline** for each tracked milestone (§4.6). |
| Control total ΔM(N) | Working-day movement of milestone M's forecast between update N and update N+1, measured on the measurement calendar. |
| Half-step schedule H(N) | Update N's network carrying update N+1's progress only (actual dates, remaining durations, percent complete) with **no** non-progress revisions, rescheduled by the engine. |
| Progress slip P | M(H(N)) − M(N): slip explained by performance against the then-current plan. |
| Revision slip R | M(N+1) − M(H(N)): slip (or recovery) explained by non-progress edits.  P + R = ΔM by construction. |
| Revision event | A named, party-coded group of change-register entries (logic add/delete/modify, duration, calendar, constraint, scope add/delete) that transforms H(N) toward update N+1.  Grouped per §3.B3. |
| Progress event | A named, party-coded performance deviation: a band-path activity whose consumed working time in the window exceeded (or a suspension/hold that interrupted) its update-N plan beyond de minimis. |
| Event bucket | The set of a party's events within one mechanism half: O_prog, C_prog, N_prog, O_rev, C_rev, N_rev (Owner / Contractor / Neutral). |
| Collapse run | One engine reschedule with a defined subset of event buckets de-impacted (§3.B4). |
| De-impact | The mechanical reversal convention for an event: revision events are reverted to their update-N state; progress events are restored to update-N planned pace (§4.1–4.2). |
| Near-critical band | Activities/paths within *b* working days of the driving path to the tracked milestone (default b = 10 wd; §4.7). |
| Exclusive contribution | Slip that disappears only when a specific bucket is de-impacted (§3.B5). |
| Overlap | The inclusion-exclusion term across buckets: measured functional concurrency when positive, interaction surplus when negative (§3.B5). |
| Residual | The window slip the collapse set cannot explain; always reported, never allocated (§5.3). |
| Ledger | The append-only record of closed windows (one row-set per window per milestone); corrections post as adjusting entries in the current window. |

---

## 2. Inputs and prerequisites

1. **The update series** in native format (e.g., .xer / .mpp / MSPDI),
   ordered by data date, plus the baseline.  Lineage verified (§3.A1).
2. **A change register capability**: mechanical version-to-version diff of
   activities, logic, durations, calendars, constraints, and status —
   including detection of retroactive changes to previously reported
   actuals.
3. **A diagnostic CPM engine with a validation handshake**: before any
   collapse run, the engine reschedules each update *as imported* and
   compares computed dates and floats to the tool-of-record values.  The
   match rate is reported.  Windows whose updates fall below the match
   threshold (default: 99% of activities within ±1 working day) are
   declared **unanalyzable as-is** (§4.5) — CCM refuses to attribute on a
   network it cannot reproduce.
4. **A responsibility coding source**: contract-designated coding where it
   exists; otherwise the analyst codes with a recorded basis per event
   (§3.B3), on the evidence hierarchy: contemporaneous project documents >
   daily reports > coder judgment.
5. **A parameter table**, fixed and hash-sealed before the first window is
   analyzed (§3.A4).  No parameter may change mid-analysis except by a
   disclosed, dated amendment that triggers re-running all closed windows
   under both parameter sets.

---

## 3. Procedure

### Phase A — Preparation (once per analysis)

- **A1. Assemble and validate the series.**  Order updates by data date;
  verify single-project lineage (project identity, activity-population
  continuity); record any missing periods (§4.4).
- **A2. Intake quality gate.**  Run a documented schedule-quality battery
  on every update (status integrity: no actuals beyond the data date, no
  incomplete work behind it; logic completeness; constraint census;
  calendar sanity).  Failures do not halt the analysis; they raise the
  expected residual and are reported per window (the method degrades
  loudly, §5.3).
- **A3. Engine validation handshake** per update (§2.3).  Record match
  rates; mark unanalyzable windows (§4.5).
- **A4. Fix and seal parameters**: band width *b*; de minimis threshold
  (default 1 wd); order convention (progress-first, §4.3); event-grouping
  rules (§3.B3); de-impact conventions (§4.1–4.2); measurement calendars
  (§4.6); engine tolerance.  Publish the sealed table to all parties in a
  live deployment.
- **A5. Select tracked milestones**: project completion plus contractual
  interim milestones.  All subsequent steps run per milestone.
- **A6. Choose mode**: *live* (each window analyzed when its closing
  update publishes) or *batch* (all windows at once).  The procedure is
  identical; only cadence differs.

### Phase B — Per window (update N → update N+1)

- **B1. Measure (the 3.3 step — no modeling).**
  - Control total ΔM = forecast(M, N+1) − forecast(M, N) in working days
    on the measurement calendar.
  - Record both lenses: net driving-path movement, and the gross movement
    of every longest-path candidate within the band (each path's relative
    float change), for the concurrency context and PCI-style stability
    reporting.
  - If |ΔM| < de minimis: bank the window (§4.8) and stop here.
- **B2. Bifurcate (the 3.4 step).**
  - Build H(N); reschedule.  P = M(H) − M(N); R = M(N+1) − M(H).
  - Verify P + R = ΔM (engine artifacts fall to residual).
  - Order-sensitivity: build the reverse-order intermediate (revisions
    first, progress second) and record the alternative split (P′, R′).
    Present progress-first as primary; disclose the difference (§4.3).
- **B3. Enumerate and code events.**
  - *Revision events*: partition the window's change-register entries into
    named event groups — grouping by change-order/directive/RFI reference
    where documented, otherwise by connected component of touched network
    objects (an added activity and the logic that ties it in is one
    event).  Code each O/C/N with the coding basis recorded.
  - *Progress events*: for each band-path activity, compare working time
    consumed in the window against the update-N plan; deviations beyond de
    minimis, plus suspensions/holds, become named progress events, coded
    O/C/N with basis (owner-coded progress events require documentary
    basis: hold, access denial, suspension directive, or similar).
  - Completeness rule: every change-register entry belongs to exactly one
    revision event; every band-path variance beyond de minimis belongs to
    exactly one progress event.  What cannot be coded is assigned to a
    **U (uncoded)** bucket — never silently to a party.
- **B4. Collapse runs (the 3.9 step, one window deep).**
  Define, per mechanism half, the slip function over de-impacted bucket
  subsets:
  - *Progress half* (basis H): g(X) = M(H with buckets X de-impacted) −
    M(N), for X ⊆ {O_prog, C_prog, N_prog, U_prog}.  g(∅) = P.
  - *Revision half* (basis N+1): f(X) = M(N+1 with buckets X reverted) −
    M(H), for X ⊆ {O_rev, C_rev, N_rev, U_rev}.  f(∅) = R.
  - Run the informative lattice subset per half: single-bucket removals
    and pairwise removals (all-bucket removal is the identity check:
    g(all) and f(all) should approach 0; deviation falls to residual).
    With three coded buckets plus U this is ≤ 6 runs per half; ~12–15
    engine runs per window per milestone in total, plus H and the
    order-check.  All runs are engine-automated.
- **B5. Decompose by inclusion-exclusion, per half.**  For buckets A, B
  (and analogously for three or more, with pairwise and higher-order
  terms):
  - Exclusive_A = g(∅) − g({A}) evaluated with all other buckets present
    — the slip that disappears only when A is de-impacted.
  - Overlap_{AB} = g({B alone removed}) + g({A alone removed}) − g(∅) −
    g({A,B removed}) … reported per pair.
  - **Sign rule**: positive overlap is **measured functional
    concurrency** — days either bucket's events would have caused alone.
    Negative overlap is **interaction surplus** (events jointly cause
    more than the sum of alone-effects, e.g., a delay pushed into a
    winter calendar): reported as its own line, never folded into any
    party's exclusive total, allocated only by disclosed convention
    (default: unallocated, presented to the decision-maker).
  - Residual_half = half total − (Σ exclusives + Σ overlaps).  Balance is
    checked automatically.
  - **Anomaly flag**: a de-impact run that *increases* slip (negative
    marginal for removing a delay event — possible under calendar or
    constraint interactions) is flagged, investigated, and reported; it
    is never netted silently.
- **B6. Populate the window record.**
  - The mechanism × party matrix (the quartered-window chart in the
    canonical Owner/Contractor view; Neutral and Uncoded as annex rows),
    each cell decomposed to its named events and activities.
  - The concurrency entries (per-half overlaps; plus a literal-overlap
    sub-analysis where daily-grain evidence exists).
  - Order-sensitivity disclosure (B2), engine match rate (A3), residual
    with its diagnosis, and the event log (id, description, party, coding
    basis, network objects touched, marginal effect).
- **B7. Ledger append.**  Write the window row-set to the append-only
  ledger.  A closed window is never edited; corrections post as adjusting
  entries in the current window, cross-referenced.

### Phase C — Roll-up and reporting (cumulative, any time)

- **C1. Party totals per milestone**: cumulative exclusive contributions
  by mechanism, with overlap and interaction columns kept separate —
  never silently allocated to parties.
- **C2. Concurrency register**: the window-by-window overlap series, the
  raw material for whatever doctrine (or contractual election) governs.
- **C3. Manipulation screen**: the cumulative progress-half vs.
  revision-half signature (persistent performance slip offset by
  persistent revision recovery), reported descriptively.
- **C4. Residual report**: total, trend, and diagnosis; conclusions are
  qualified wherever residual is material to them.
- **C5. Sensitivity annex**: band width ±, order convention, de-impact
  convention variants — attribution **rank-order stability** is the
  reported test.
- **C6. Interpretation boundary**: the report states that outputs are
  measurements feeding expert opinion or contractual machinery; the
  method renders no opinion on entitlement, doctrine, or quantum.

---

## 4. Conventions and edge cases

1. **De-impact of progress events**: the activity is restored to its
   update-N planned performance for the window (planned remaining
   duration and dates relative to DD_N+1); suspensions/holds are removed.
   This "planned-pace restoration" convention is mechanical and
   symmetric; where contested, the sensitivity annex runs the alternative
   convention (demonstrated-pace restoration) and reports both.
2. **De-impact of revision events**: the event group's change-register
   entries are reverted to their update-N state as a coherent group
   (never entry-by-entry, which can produce incoherent networks).
3. **Order convention**: progress-first (3.4 continuity) is primary;
   the reverse split is always computed and disclosed.  If the two
   splits' party rank-order differs, the window is flagged for
   escalated review.
4. **Missing or irregular updates**: analysis proceeds on the pairs that
   exist; wider windows degrade attribution resolution and are disclosed.
5. **Unanalyzable windows** (handshake failure, §2.3): the window's
   control total is still measured (B1 is observational); attribution is
   withheld and the mismatch diagnosis reported.  An unanalyzable window
   in a live deployment is an immediate data-quality escalation.
6. **Measurement calendar fixed at baseline** per milestone: calendar
   *revisions* are analyzable events like any other; the meter they would
   otherwise distort stays constant.  Disclosed prominently.
7. **Band width** default b = 10 working days; the sensitivity annex
   reports b/2 and 2b.  The band bounds progress-event enumeration only —
   collapse runs always reschedule the full network.
8. **De minimis banking**: windows with |ΔM| below threshold bank into a
   running account, analyzed when the account trips the threshold or at
   the next milestone/reconciliation event.
9. **Re-baselines**: the window containing a re-baseline is split at the
   re-baseline; mapping between old and new networks is recorded; the
   provenance share of the new driving path (baseline-original vs.
   post-baseline) is reported for context.
10. **Recovery windows** (negative ΔM): identical machinery; negative
    exclusive contributions are mitigation bookings by party.
11. **Out-of-sequence progress**: rectified per the engine's validated,
    disclosed conventions; OOS incidence is reported per window.
12. **Pacing**: where a declared-pacing register exists, declared pacing
    is annotated on the relevant events; pacing asserted only
    retrospectively is flagged as such.  The method books float
    consumption descriptively either way.

---

## 5. Outputs

1. Sealed parameter table (with hash).
2. Per-window record: quartered-window matrix, event log, concurrency
   entries, order-sensitivity, engine match rate, residual diagnosis.
3. The append-only ledger (all closed windows, adjusting entries
   cross-referenced).
4. Cumulative roll-up: party totals, concurrency register, manipulation
   screen, residual report, sensitivity annex.
5. **Arithmetic identities any party can recheck**: P + R = ΔM per
   window; per half, Σ exclusives + Σ overlaps + residual = half total;
   halves sum to the control total; ledger rows sum to cumulative slip.
6. A reproducibility capsule: hashes of inputs, parameters, and outputs
   sufficient for an opposing party to re-run and verify byte-identical
   results with any conforming implementation.

---

## 6. Known limitations (stated, not hidden)

1. **Shallow counterfactual**: cross-window ripple effects (this month's
   delay pushing later work into worse conditions) are not re-litigated;
   window attributions bank forward.  This is the standing convention of
   all windows practice, adopted knowingly.
2. **De-impact conventions are conventions**: the entanglement problem
   ("what pace would have been achieved but-for the interference") is
   answered by a published symmetric rule plus sensitivity disclosure,
   not solved.
3. **Update quality bounds attribution quality**: garbage in produces a
   large residual and unanalyzable windows — visibly, by design, but it
   produces them.
4. **Coding is human** at exactly one step (B3), with a recorded basis;
   disputes migrate there and are meant to be small, early, and specific.
5. **Mechanism is not motive**: a revision made in response to progress
   slip is booked as a revision; response relationships are a protocol/
   conduct question outside the attribution method.
6. **Engine dependence**: no validated engine, no attribution (B1's
   measurement still stands).  The validation handshake and match-rate
   disclosure are the mitigation.

---

## 7. Worked example (fixture-scale)

Window 7 (DD 01-Aug → 01-Sep), milestone M-100, measurement calendar
5d/8h fixed at baseline.  Control total **ΔM = +12 wd**.

Half-step: P = +9 wd (progress), R = +3 wd (revisions); reverse-order
split P′ = +8, R′ = +4 (disclosed; party rank-order unchanged).

Progress half (g(∅) = 9): de-impact runs give g({C_prog}) = 3,
g({O_prog}) = 8, g({O,C}) = 0 → Exclusive_C = 9 − 3 = 6,
Exclusive_O = 9 − 8 = 1, Overlap = 3 + 8 − 9 − 0 = 2 (functional
concurrency), residual = g({O,C}) = 0; events: piling crew at 60%
planned rate (C, daily reports), RFI-341 hold on risers (O, hold
notice).

Revision half (f(∅) = 3): f({O_rev}) = −1, f({C_rev}) = 4,
f({O,C}) = 0 → Exclusive_O = 3 − (−1) = +4 (CO-14 ductwork scope +
logic), Exclusive_C = 3 − 4 = −1 (resequencing recovery),
Overlap = (−1) + 4 − 3 − 0 = 0, residual 0.

| M-100, Window 7 | Progress | Revision | Row total |
|---|---|---|---|
| Owner | +1 | +4 | +5 |
| Contractor | +6 | −1 | +5 |
| Concurrent (O×C) | +2 | 0 | +2 |
| Neutral / Uncoded / Residual | 0 | 0 | 0 |
| **Column total** | **+9** | **+3** | **+12 ✓** |

One-sentence reading: "Of September's 12 days: 6 contractor performance,
1 owner hold, 2 concurrent on active work, 4 owner added scope, less 1
recovered by contractor resequencing."

---

## 8. Quality assurance and acceptance tests

1. **Determinism test**: two independent operators (one a non-expert
   scheduler) run the protocol on the same file set; the acceptance
   criterion is identical ledgers and matrices.  Any divergence
   identifies an under-specified step, which is then specified.
2. **Balance checks**: all §5.5 identities verified automatically on
   every window.
3. **Bidirectional check (optional)**: the additive mirror (insert the
   window's events into update N; forward-predict) is compared with the
   subtractive result; the gap is reported as per-window model error.
4. **Sensitivity gate**: publication or reliance requires the C5 annex to
   show party rank-order stability across the parameter variations; where
   it is unstable, the affected windows are reported as contested rather
   than concluded.
