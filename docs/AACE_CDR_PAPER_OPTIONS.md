# AACE CDR Paper — Concept Options & Go/No-Go Memo

**Status: FOR REVIEW (RJL) — scoping memo only, no drafting done.**  Prepared
2026-07-12 in response to the request to brainstorm an AACE Claims & Dispute
Resolution (CDR) track paper built on ScheduleIQ's bespoke metrics, ideally
proposing a novel 29R-03-style method that field staff can run during
execution to keep disputes from escalating, with the execution-phase record
then serving as the foundation for the forensic delay analysis.

Scope decisions already taken (2026-07-12):

| Decision | Answer |
|---|---|
| Venue | AACE annual conference, CDR track technical paper |
| Disclosure | Full formulas published for whichever indices the paper uses |
| Evidence | Real anonymized project series **and** synthetic seeded fixtures |
| Deliverable now | This memo: options, scoring, honest go/no-go |

---

## 1. The framing problem (read this before the options)

The request as stated — "a new 29R-03 MIP that field staff implement during
execution" — contains a category tension that shapes every option below:

**29R-03 MIPs are retrospective forensic methods.**  The nine MIPs (3.1–3.9)
are classified by timing (retrospective), basic method (observational vs.
modeled), and implementation choices.  Nothing that runs *during* execution
is a MIP; the prospective side of delay analysis already has its own RP
(52R-06, Time Impact Analysis).  A paper claiming "MIP 3.10, run monthly by
the field" would be attacked on taxonomy before anyone reads the math.

But the tension points at a real, underserved gap:

**29R-03 assumes the contemporaneous record exists and spends an entire part
(source validation) coping with the fact that it is usually bad.**  The SCL
Delay & Disruption Protocol's first core principle is records — but its
guidance is qualitative (keep good records) rather than a defined, metric-
based, tamper-evident protocol.  DCMA-14 is a point-in-time quality gate, not
a dispute-oriented record.  Earned schedule / CEI / BEI measure pace, not
delay attribution.  **Nobody has published a defined protocol whose explicit
purpose is to manufacture, during execution, the quantified record that a
retrospective observational analysis will later stand on — with the same
numbers doing dispute-avoidance duty in the meantime.**

So the honest reframe: the novel contribution is not a tenth MIP.  It is a
**contemporaneous protocol + published metric set + sealing mechanism** that
(a) gives field staff early-warning triggers with defined responses, and
(b) hands the eventual forensic analyst a pre-validated, hash-sealed,
decomposable evidence series that collapses the source-validation fight and
quantifies the observational analysis.  A short forward-looking section can
*discuss* what a formal taxonomy extension would look like — but as an
invitation to the FSA subcommittee, not a claim.

This reframe is what makes the effort viable at all.  If the paper must
literally claim a new MIP, the recommendation below flips to no-go.

---

## 2. Asset inventory (what already exists in this repo)

| Asset | Where | Paper relevance |
|---|---|---|
| Criticality kernel `w = 2^(−RF/λ)` + float-path extraction | `src/scheduleiq/analytics/li_indices.py`, `analytics/paths.py` | The publishable mathematical heart; shared by FCBI/PCI/CDI |
| FCBI, PCI, RDI, CDI, BWI (implemented) | `analytics/li_indices.py` | Candidate published indices |
| LHL, FRB, BDI, IL, MML (implemented) | `analytics/li_record.py` | Candidate published indices; IL and FRB are tribunal-shaped |
| SMI, DDI, ARR, PPS (proposed, provocative) | `docs/ANALYTICS_PROPOSAL.md` §11 | **Exclude** — controversy magnets; not for a first paper |
| Definitions & design rationale for all indices | `docs/ANALYTICS_PROPOSAL.md` §9–10 | Source text for the paper's method section |
| 54-check intake battery w/ literature references | `metrics/matrix.yaml`, `docs/METRIC_MATRIX.md`, `docs/REFERENCES.md` | Grounding + citation base |
| Reproducibility capsule (SHA-256 manifest, rerun script, tribunal README) | `src/scheduleiq/capsule.py` | The tamper-evident sealing mechanism — Option A's spine |
| Version-to-version change register | `compare.diff` (per ANALYTICS_PROPOSAL) | Decomposition/attribution substrate for FCBI/IL/BDI |
| Report-card public-spec precedent (publish spec, compete on implementation) | `docs/public_spec/` | The disclosure playbook the paper follows |
| Seeded-defect fixture generator | `tests/fixtures/make_fixtures.py` | Synthetic evidence: controlled delay scenarios with known ground truth |
| Trend series incl. Hit Task %, CEI | `trend/series.py` | Shows the protocol extends, not replaces, accepted execution metrics |

**Governance catch (must be resolved explicitly):**
`docs/public_spec/README.md` currently states that the LI index computations
*stay proprietary* and only their score-normalization is public.  The
disclosure decision above **partially supersedes that line** for whichever
indices the paper publishes.  This memo records the conflict; RJL should
confirm the revised boundary (recommended: publish the kernel + the paper's
index formulas under the same rationale as the report card — the rulebook is
public, ScheduleIQ competes on implementation, and a formula an opposing
expert can reproduce is worth more as credibility than as secret).

---

## 3. The options

### Option A — "The As-Managed Record": a contemporaneous, sealed metric protocol

**Working title:** *As-Planned, As-Built, As-Managed: A Contemporaneous
Metric Protocol That De-Escalates Disputes and Prepares Their Resolution.*

**Core claim.**  Delay practice has two canonical records — as-planned and
as-built — and litigates the gap between them.  The paper names and defines
the missing third record: the **as-managed record** — how the schedule was
managed between baseline and completion — and specifies a protocol to
produce it: at every update, compute a fixed, published set of indices plus
the change register; seal results into a hash-verified capsule
(manifest + rerun script); act on defined early-warning thresholds; log the
response.  Cheap enough for a project scheduler to run in an hour a month.

**Execution-phase use (dispute avoidance).**  Each index maps to a defined
conversation before positions harden: RDI rising → recovery-realism review
with named activities; IL emergence events → notice/mitigation log kept
current as a side effect; FCBI top-burners table → this month's float story
attributable to named parties while memories are fresh; BWI → compression
review before the bow wave breaks.  The protocol's dispute-avoidance theory:
disputes escalate when the parties' narratives diverge unrecorded; a shared,
sealed, decomposable number set forces convergence monthly.

**Forensic bridge.**  At dispute time the sealed series (a) collapses much
of 29R-03's source-validation burden — provenance, integrity, and
consistency of every update are cryptographically established rather than
reconstructed; (b) feeds observational MIP 3.3/3.4 analyses with quantified,
pre-decomposed float-erosion and response evidence; (c) IL and RDI directly
evidence mitigation conduct and forecast realism — things tribunals ask
about and nobody measures.

**Published set (scoped, not the full ten):** the criticality kernel, FCBI,
RDI, IL — plus the capsule manifest format.  (PCI/CDI/BWI/FRB/LHL/BDI/MML
reserved for follow-up papers; a first paper that dumps ten formulas is a
spec sheet, not an argument.)

**Evidence plan.**  One real anonymized multi-update series shown
end-to-end (the as-managed record it would have produced, and what that
record would have settled early); seeded fixtures used for the controlled
demonstrations (a known injected delay → the indices' response, ground truth
recoverable).

**Attack surface.**  (1) "Tool advertisement" — mitigated by publishing the
formulas + capsule format and stating any implementation qualifies;
(2) "contractors won't self-incriminate by keeping better records" — met
head-on: the record cuts both ways by design, which is exactly why an owner
or a DRB can demand it; (3) λ in the kernel is a tunable — needs the
sensitivity analysis from Option B's gating check.

**Effort:** Medium.  Everything computes today; work is case-study runs,
threshold/response table design, and writing.
**Dead-end risk:** Low.  Even if every index were prior art (they are not),
the protocol + sealing + forensic-bridge framing has no published equivalent
found so far (gating sweep still required, §5).

---

### Option B — Criticality-Weighted Float Consumption as a quantification layer for observational MIPs

**Working title:** *Beyond Binary Criticality: Criticality-Weighted Float
Consumption Analysis for Observational Delay Attribution.*

**Core claim.**  Observational methods treat criticality as binary — an
activity is on the critical path or invisible — which is why they mishandle
near-critical path flips, creeping concurrency, and float erosion that never
quite reaches zero until it suddenly does.  Publish the kernel
(`w = 2^(−RF/λ)`), define **FCBI** (weighted float burn per window,
regained float tracked separately so recovery cannot mask burn,
constraint-manufactured criticality flagged so the index cannot be gamed)
and its decomposition to named activities/parties, and show it as an
*attribution and quantification layer bolted onto MIP 3.3/3.4* — not a
replacement method.  PCI (path concentration) rides along as the method-
selection diagnostic: low PCI ⇒ snapshot methods are unsafe, use
daily-resolution or split windows.

**Execution/forensic duality.**  Same numbers both phases: during execution
the FCBI curve is the float story in one line; forensically each window's
burn decomposes into the same top-burners table the parties saw monthly.

**Attack surface (this is the sharp end).**
1. **λ is a dial.**  A cross-examiner's dream unless the paper includes a
   sensitivity analysis showing rank-order attribution conclusions stable
   across λ ∈ [3, 10] wd on both real and seeded data.  If conclusions flip
   with λ, this option is dead — that is a genuine kill criterion, and we
   should want to know.
2. **Float ownership doctrine.**  Weighting float consumption implicitly
   prices float; the paper must stay strictly descriptive (who consumed
   what, weighted by how critical it was) and leave entitlement to the
   expert — the discipline `li_indices.py` already enforces.
3. **Prior art density.**  Float-consumption and float-mapping papers exist
   in the AACE transactions corpus.  The exponential kernel, the regained-
   float separation, and the constraint-gaming guard are believed novel, but
   this is the option most exposed to a prior-art surprise.  Sweep first.

**Effort:** Medium-High (sensitivity study + prior-art review on top of
case-study runs).
**Dead-end risk:** Medium.  Highest technical novelty of the four, and the
most likely to be either genuinely new or already half-published.

---

### Option C — The tribunal-question triad: RDI, IL, FRB (+ BWI)

**Working title:** *Measuring What Tribunals Actually Ask: Recovery Debt,
Intervention Latency, and Forecast Reliability as Field-Computable Indices.*

**Core claim.**  Three questions recur in every delay dispute and are today
answered only with narrative: *Was the recovery plan ever realistic?* (RDI:
required pace vs. anything the project ever demonstrated — at project end,
realized slip ≈ RDI is a self-validating exhibit), *Did management respond,
and did the response work?* (IL: emergence-to-response latency, with the
"didn't act" vs. "acted and it didn't work" distinction), *How credible is
this scheduler's forecast?* (FRB: empirical error bands from the project's
own track record — no distributions assumed, very hard to rebut).  All three
are computable by field staff from the files they already produce, none
requires float-path math or a CPM engine, and each doubles as a monthly
early-warning trigger.

**Attack surface.**  Low doctrinal friction — these indices describe conduct
and track record, not causation, and don't touch float ownership.  The risk
is structural: without a protocol spine the paper reads as "three nice
metrics" (a listicle), and the CDR audience has seen metric listicles.

**Effort:** Low-Medium.  **Dead-end risk:** Low — but so is the ceiling.
Best understood not as a standalone paper but as the early-warning tier
*inside* Option A.

---

### Option D — The moonshot: a formal taxonomy extension ("toward a contemporaneous MIP")

**Working title:** *Toward a Contemporaneous Layer in the 29R-03 Taxonomy.*

**Core claim.**  Formally propose that the forensic taxonomy acquire a
contemporaneous dimension: a defined, named protocol class whose artifacts
are first-class inputs to the retrospective MIPs, with source-validation
credit specified for sealed records.

**Honest assessment: NO-GO as a first paper.**  Taxonomy changes come out of
the FSA subcommittee after years of consensus-building, invariably preceded
by conference papers that earned standing.  A first paper claiming the
taxonomy slot invites hostile review, and the claim would overshadow the
real contributions.  The correct sequence is A (and/or B) as conference
papers → community reaction → subcommittee contact → RP proposal.  Keep D as
the stated ambition in A's closing section, one paragraph, framed as an
invitation.

---

## 4. Comparison

| | A: As-Managed Record | B: Weighted Float Burn | C: Tribunal Triad | D: Taxonomy |
|---|---|---|---|---|
| Novelty | High (framing + protocol) | High (math), if prior-art clean | Medium | High but unearned |
| Matches the stated vision (field → forensic) | **Direct hit** | Partial (method, not protocol) | Partial (avoidance-heavy) | Eventually |
| Field practicality | High (hour/month, tool-assisted) | Medium (needs float paths) | Highest | n/a |
| Forensic defensibility | High (descriptive + sealed) | Medium (λ, float doctrine) | High | n/a |
| CDR-track fit | Strong | Strong | Strong | Poor (committee matter) |
| Effort | Medium | Medium-High | Low-Medium | High, multi-year |
| Dead-end risk | Low | Medium | Low | High as first move |

---

## 5. Recommendation

**GO — one paper, structured as Option A with B's kernel as its quantified
heart and C's triad as its early-warning tier.**  Concretely:

- **Spine:** the as-managed record — protocol definition, sealing mechanism,
  threshold/response table, forensic bridge to observational MIPs and to
  source validation.  This is the part that is genuinely unoccupied ground
  and matches the original vision exactly.
- **Quantified heart:** the published kernel + FCBI with its decomposition
  and anti-gaming guards (the "new and exciting" mathematics), carried by
  the λ-sensitivity study.
- **Early-warning tier:** RDI + IL (FRB and the rest held for follow-ups).
- **Explicit non-claims:** not a new MIP; no causation, entitlement,
  concurrency, or quantum opinions (the CLAUDE.md discipline, stated in the
  paper); tool-agnostic — formulas and capsule format published, any
  implementation qualifies.
- **Closing section:** one paragraph of Option D as an invitation to the
  FSA subcommittee.

This is not forcing a solution onto the "new MIP" ask; it is the version of
the ask that survives contact with how 29R-03 and the CDR community actually
work.  If the reframe is unacceptable and the paper must claim a literal new
MIP, recommend **NO-GO**.

### Gating checks before any drafting (kill criteria)

1. **Prior-art sweep** of AACE transactions / *Cost Engineering* / ASCE JLDR
   / SCL papers for: contemporaneous metric-protocol proposals,
   float-consumption weighting schemes, and sealed/verifiable schedule
   records.  Kernel-shaped prior art kills B's heart (paper degrades to
   A+C, still viable); protocol-shaped prior art on the as-managed concept
   kills the spine (full stop, report back rather than force it).
2. **λ-sensitivity study** on fixtures + the real series: attribution
   rank-order must be stable across λ ∈ [3, 10] wd.  Unstable ⇒ drop FCBI
   from the paper (A+C still viable), and file the finding as a limitation
   in ANALYTICS_PROPOSAL regardless — we want this answer for our own
   practice even if the paper dies.
3. **Disclosure boundary sign-off (RJL):** confirm the revised proprietary
   line (§2 governance catch) covering kernel + FCBI + RDI + IL formulas
   and the capsule manifest format.
4. **Real-data clearance:** identify the candidate project series and
   confirm anonymization/permission.  If none clears, fixtures alone are
   acceptable for a conference paper (flag as limitation) — not a kill, but
   it weakens the centerpiece.
5. **Cycle logistics:** confirm the current AACE conference abstract
   deadline (typically autumn for the following June; target the 2027
   conference) and CDR-track paper format requirements.

### Proposed next steps (in order, pending RJL review of this memo)

1. RJL reviews this memo; decides go/no-go on the recommended shape and the
   disclosure boundary.
2. Run gating checks 1–2 (prior-art sweep; λ-sensitivity on existing
   fixtures — the harness largely exists in `tests/`).
3. If gates pass: section-level outline + AACE-style abstract for the
   combined paper.
4. Draft; internal review against the attack-surface list in §3.

---

## 6. Open questions for RJL

1. Is the reframe (protocol-not-MIP, with D as a closing invitation)
   acceptable, or is a literal new-MIP claim a requirement?  (If the
   latter: recommendation is no-go.)
2. Which real project series is the candidate case study, and who clears
   anonymization?
3. Does publishing kernel + FCBI/RDI/IL formulas change the pending
   `docs/public_spec/` report-card publication decision (same "publish the
   rulebook" rationale — arguably they should ship together)?
4. Naming: is "as-managed record" the brand, or does LI prefer the index
   names carry the branding (FCBI™-style, per ANALYTICS_PROPOSAL §9's
   Deltek comparison)?  One paper should establish one name.
5. Co-authorship/AACE membership logistics for the CDR track submission.

---

## 7. Second pass (2026-07-12): from evidence protocol to contractual regime — "Option E"

Elaboration following review of §1–6.  The direction under consideration:
a **contractually specified metric toolbox, tracked during execution, that
governs delay attribution when disputes arise — with delays resolved on a
rolling basis during the project** rather than forensically at the end.
Four pitfalls were put on the table: contract adoption; using metrics to
assign responsibility / handle concurrency / quantify entitlement and
quantum; gaming and guardrails; and resolution cadence.  Plus the market
observation that owners distrust prospective 52R-06 TIA because awarded
fragnets are often executed faster than modeled and contractor concurrent
delay in base scope during the fragnet window goes uncounted.

### 7.1 The doctrinal move that makes this coherent: measurement conventions, not machine causation

"The metrics govern causal attribution" is unenforceable and unsellable as
stated — no tribunal lets an instrument decide causation, and the CDR
audience (heavy with lawyers) will say so in the first question.  The
version that works is one reframe away:

**Parties cannot delegate causation to a formula, but they routinely
contract around the need to prove it — by agreeing a measurement convention
in its place.**  Construction contracts are already full of these:
liquidated damages replace proof of actual loss; unit-price measurement
replaces proof of cost; deemed weather-day allowances replace proof of
weather impact; daywork rates replace cost forensics; pain/gain-share pools
in alliancing replace attribution entirely.  Each is enforceable because it
is agreed ex ante, symmetric, and applied to an auditable record.

**Delay is the last major quantity in the contract still resolved by
after-the-fact causal reconstruction instead of an agreed measurement.**
That is the paper's thesis sentence.  Option E is a *liquidated attribution
regime*: the parties agree at award that responsibility for each window's
slip will be **measured** per a published convention (criticality-weighted
burn on the paths to the governing milestone, decomposed by a responsibility
overlay, netted per an agreed concurrency rule), not litigated as
causation-in-fact.  The metric need not be metaphysically correct about
causation; it must be agreed, symmetric, parameter-frozen, and computed on a
sealed record.  Law stays with the parties (they pick the rules ex ante);
measurement goes to the instrument.

Prior-art frame (must be named or reviewers will): **NEC3/NEC4 already
resolves compensation events contemporaneously** with prospective, final
assessments — proof the industry accepts interval-based delay resolution.
But NEC assessment is *forecast-based and final*, which is exactly the
pathology the owners' 52R-06 complaint describes: assessed impacts that
never materialize are not clawed back.  Option E's differentiator is that it
is **retrospective in character, contemporaneous in timing** (§7.2) — and
metric-governed rather than judgment-of-the-PM-governed.  DRB/DAAB standing
neutrals are the institutional vehicle; what they lack today is a
quantitative substrate, which is what the sealed record supplies.

### 7.2 The 52R-06 wedge: windowed true-up answers both sides' complaints

The owner objection to prospective TIA is well-founded and specific:
(a) fragnet work is often executed faster than modeled, and (b) contractor
concurrent delay in base scope during the fragnet window goes uncounted, so
prospective awards over-grant time and money.  The contractor objection to
end-of-project retrospection is equally well-founded: evidence decay,
positional hardening, expert cost, and settlement leverage games.

The windowed regime is precisely the middle path, and this is the paper's
selling wedge:

- **Each window is attributed after it happens** — observed reality, not a
  forecast.  Actual fragnet execution pace is what gets measured, and *all*
  weighted burn in the window is decomposed — including contractor burn in
  base scope during the fragnet period, which the binary TIA fragnet view
  never sees.  This hands owners exactly the retrospective measurement they
  want.
- **But only one or two updates in arrears** — evidence fresh, personnel
  still on site, positions not yet hardened, and the attribution ratchets
  into interim finality.  This hands contractors the certainty and cash-flow
  they want and never get from end-of-project forensics.
- **52R-06 TIA is repositioned, not rejected**: TIA remains the right tool
  for *pricing proposed changes prospectively* and granting **provisional**
  EOT; the window close-out is the **true-up** against actuals.  The
  confusion the owner complaint points at is using a pricing-the-future tool
  to settle attribution-of-the-past; the regime separates the two.
- **Mitigation must not be punished by the true-up.**  If the contractor
  genuinely accelerated the fragnet, truing the EOT down converts its
  mitigation into a gift to the owner.  Convention: true-down is limited by
  the demonstrated-pace envelope (the RDI machinery) — fragnet execution
  faster than anything the project has demonstrated is presumptively
  acceleration/mitigation, handled under the acceleration clause rather
  than clawed back.  This detail decides whether contractors can ever sign.

### 7.3 Responsibility, concurrency, entitlement, quantum — tiered bindingness

The mechanism should not try to resolve everything with equal force.
Three tiers, contractually explicit:

- **Tier 1 — TIME, binding-interim.**  Window slip attribution → EOT banked
  / LD exposure adjusted per window, subject to a short adjudication-style
  challenge period (e.g., 28 days), then final absent fraud or manifest
  error (expert-determination finality standard).  "Pay now, argue later"
  transplanted to time.
- **Tier 2 — PROLONGATION MONEY, presumptive or pre-priced.**  Strongest
  form: compensable-day rates pre-agreed in the contract (another
  liquidation — precedent exists in pre-agreed prolongation rates), making
  quantum mechanical: compensable days × rate.  Weaker form: the Tier-1
  time allocation carries a rebuttable presumption into any later forum.
- **Tier 3 — RESERVED.**  Disruption/loss-of-productivity, acceleration
  claims, and cardinal-change territory expressly outside the mechanism
  (MML and the record still feed them evidentially).

**Concurrency becomes a measured overlap plus a contract-chosen rule.**
Per window, per governing milestone path set: weighted burn per party
(B_owner, B_contractor, B_neutral — weather/force-majeure via the existing
deemed-day conventions).  The contract picks the allocation rule ex ante
from a menu the paper presents without advocating doctrine: dominant-cause
(cliff effects, not recommended), pro-rata to weighted burn shares,
SCL-style time-but-no-money on the overlap, or Malmaison-style (EOT if
owner burn material regardless of contractor burn; money only on the
excess).  The doctrinal fight over concurrency does not disappear — it is
**had once, at award, in the abstract**, when neither party knows which
side of it they will need.  A Rawlsian veil is the best moment this
industry will ever get to agree a concurrency rule.

**Self-aware bindingness (ARR as jurisdiction gate).**  ANALYTICS_PROPOSAL
§11.3's ARR (attribution robustness across reasonable parameter/method
choices) gets a governance job: a window's attribution **auto-binds only
when ARR clears a threshold**; fragile attributions escalate to the
standing neutral instead of binding automatically.  The instrument declines
jurisdiction when its own error bars are wide.  This single design element
answers the "you can't let a formula decide edge cases" objection, because
the formula's defined behavior in edge cases is to decline to decide.

**Pacing.**  The most abused retrospective defense gets the regime's most
valuable rule: pacing may only be asserted for window N if it was declared
during window N (the protocol makes declaration cheap).  Contemporaneous
declaration or forfeiture — retrospective pacing invention dies.  PPS
(§11.4) then scores declared pacing for plausibility.

**Where the fights relocate (honest limitation).**  Attribution decomposes
to activities; the activity→party responsibility overlay is where disputes
migrate.  Coding is fixed at baseline for structurally-owned activities
(approvals, permits, owner-furnished items), assigned at window close for
emergent events (RFI/CO linkage as default), with coding disputes on the
neutral's fast track.  The regime does not eliminate judgment; it relocates
disputes from *the whole project, years later, all at once* to *these three
activities, this month*.  Small, early, specific disputes are the
dispute-avoidance literature's definition of success — this is a feature
and the paper should claim it as one, not hide it.

### 7.4 Gaming matrix and guardrails

Symmetry is the price of adoption, so the matrix must be per-party.

| Vector | Party | Guardrail (existing machinery) |
|---|---|---|
| Preferential/soft logic, sequestered float on owner-facing paths | Contractor | LHL driving-path instability flag; change register names every edit; SMI decomposition; baseline acceptance gate (54-check battery as contractual criterion) |
| Constraint-manufactured criticality | Either | FCBI's constraint-free-criticality guard (already implemented) |
| Evergreen forecasting / status gaming to hide burn | Contractor | Evergreen detector; Hit Task %; retroactive-actual-change check; capsule sealing makes history unrewritable |
| Bow-waving work against milestones | Contractor | BWI is purpose-built for exactly this |
| Retrospective pacing invention | Contractor | Contemporaneous-declaration rule (§7.3) + PPS |
| Slow-rolled reviews/approvals pushing burn into contractor windows | Owner | IL runs symmetrically on owner-coded activities; owner burn decomposes identically |
| Directed dates / forced re-baselines to reset the record | Owner | DDI; re-baseline permitted only through a defined variation gate that carries the old record forward |
| Refusing/contesting updates to stall the record | Owner | Deemed-acceptance: the update seals and the record runs regardless; update disputes go to the neutral fast-track |
| Parameter shopping after the fact | Either | λ, band, window length, concurrency rule frozen in a contract exhibit at award; capsule already seals the spec hash |
| Submitting a degraded schedule then relying on it | Either | **Integrity estoppel rule**: an update scoring below the report-card gate cannot be used *offensively by its author* but remains usable against them.  Quality becomes self-interested. |

The last row is worth flagging as a candidate signature idea: it converts
schedule quality from a compliance nag into a party's own litigation
self-interest, which no spec-mandated DCMA threshold has ever achieved.

### 7.5 Cadence: two-speed design

Single-cadence answers are all wrong: monthly-binding is noisy and
admin-crushing; end-of-project is the status quo being escaped.  Two speeds:

- **Measurement cadence — every update (monthly).**  Metrics computed,
  sealed, published to both parties simultaneously.  No decisions — just
  the shared instrument panel and its early-warning triggers.  This is
  §3 Option A running unchanged.
- **Attribution cadence — rolling close-out, one to two updates in
  arrears** (or quarterly on slow-burn programs).  Window N closes after a
  settling lag (late data, corrections), attribution issues, challenge
  period runs, then Tier-1 finality.  **De minimis rule**: window slip
  below a materiality threshold banks into a running account resolved when
  the account trips the threshold or at the next milestone — keeps the
  machinery from grinding on noise.
- **Reconciliation events — at major milestones and completion.**
  Arithmetic/data corrections only; closed attributions reopen only for
  fraud or manifest error.  Without this finality standard the regime is
  just monthly homework for the eventual forensic fight.

### 7.6 Adoption: the bindingness ladder (answer to pitfall #1)

Nobody signs the full regime cold.  The ladder lets a contract enter at any
rung, and each rung is independently valuable:

1. **Informational** — the protocol runs, both parties see the sealed
   record (§3 Option A exactly).  Zero contractual courage required beyond
   a scheduling-spec exhibit, which owners already dictate routinely.
2. **Presumptive** — a standing DRB/DAAB adopts the record as its
   instrument panel via terms of reference; attributions are rebuttable
   findings.  No contract amendment needed at all on projects that already
   have a board — the softest real entry point.
3. **Binding-for-time** — Tier 1 interim finality with challenge windows.
4. **Full liquidated regime** — Tiers 1–2 with pre-priced compensable days.

Adoption vectors, most to least promising: (a) **GC→subcontract flow-down**
— GCs feel sub-claim pain acutely, control their subcontract forms, and can
impose uniformly; likely the fastest real-world proving ground; (b)
**owner-side spec insertion** sold on the 52R-06 over-award fix (§7.2 is
the owners' own argument handed back to them); (c) **DRB/DAAB terms of
reference** (rung 2); (d) alliancing/IPD programs already culturally
adjacent.  The paper should present the ladder and let the market climb it;
demanding rung 4 in print guarantees rejection as naïve.

### 7.7 Legal risk register (needs a lawyer co-author — this is now firm)

- **Prevention principle / time-at-large.**  If the mechanism procedurally
  bars an EOT for genuinely owner-caused delay, LDs may become
  unenforceable wholesale.  Mandatory fail-safe: mechanism failure or
  ARR-declined windows fall back to conventional assessment — the regime
  must never operate as forfeiture.
- **Statutory adjudication coexistence (UK and similar).**  Parties cannot
  contract out of the right to adjudicate at any time; the regime must be
  designed so the sealed record *travels into* adjudication rather than
  purporting to exclude it.
- **Expert-determination finality** doctrine is the enforceability rail for
  Tier-1 interim finality (fraud/manifest-error reopening standard);
  strength varies by jurisdiction — US has no statutory adjudication, so
  the mechanism rides entirely on contract + DRB enforceability there.
- **Notice-bar / condition-precedent enforceability** (the pacing
  declaration rule is one) varies by jurisdiction and must be drafted as a
  measurement convention, not a forfeiture clause, in hostile
  jurisdictions.

### 7.8 Revised paper strategy

Option E does not replace §5's recommendation — it **completes it and
raises the ceiling**.  The bindingness ladder (§7.6) means the full
framework paper *contains* Option A as rung 1.  Two viable shapes:

- **Shape 1 — one framework paper (recommended):** *"The Last Unmeasured
  Quantity: Rolling, Metric-Governed Delay Resolution"* — thesis (§7.1),
  the wedge (§7.2), the regime (§7.3–7.5), the ladder (§7.6), with the
  published kernel + FCBI/RDI/IL as the measurement layer and the
  as-managed record as rung 1.  Bigger claim, more memorable, and the
  52R-06 critique gives it a hook §3's Option A lacks.  Cost: must carry
  the legal analysis, so a construction-lawyer co-author moves from
  nice-to-have to prerequisite, and the λ-sensitivity + prior-art gates
  from §5 still apply in full.
- **Shape 2 — two papers:** A first (evidence protocol, 2027), E as the
  follow-up once A has standing.  Safer, slower; risks someone else
  publishing the framework framing in between.

Additional gating checks for Shape 1 (on top of §5's):
6. **Prior-art sweep extension**: NEC compensation-event literature, DRB
   effectiveness studies, any published "contractual delay metrics" or
   interim-binding attribution proposals (CDR and ICC/SCL corpora).
7. **Lawyer co-author identified and willing** — without one, drop to
   Shape 2.
8. **Straw-man contract exhibit drafted** (2–3 pages: parameter table,
   concurrency-rule election, challenge procedure, fail-safe clause) — if
   the exhibit cannot be drafted short, the "field-implementable" claim
   fails and the regime is not ready for print.

### 7.9 Additional open questions for RJL

6. Shape 1 (one framework paper, lawyer co-author required) or Shape 2
   (protocol paper first)?
7. Does LI want to *own* the standing-neutral computation role the regime
   creates (the "record administrator" — a recurring-revenue service line),
   and does saying so in print help adoption or taint neutrality?
8. §7's regime uses ARR and PPS from the §11 "provocative" set (as
   governance gates, not accusations) — does that change §11's PARKED
   status?
9. Which concurrency conventions go in the paper's menu, and is LI willing
   to print worked examples of each on the same fixture (the honest way to
   show the rules diverge)?

---

## 8. Third pass (2026-07-12): a literal MIP 3.10 — Option E tabled

Direction change: §7's contractual regime is **tabled** (kept on record, not
abandoned).  New target: a genuine tenth method for the 29R-03 taxonomy.
Constraints given: it need not use the LI indices; it must permit
retrospective analysis *during* execution; it must be more user-friendly
than existing MIPs; and it must handle concurrency well.

### 8.1 Taxonomy legitimacy — §1's objection narrowed

§1 argued "nothing that runs during execution is a MIP."  That was right
against §7's shape (a prospective/contemporaneous *decision mechanism*) and
is **wrong against this one**: "retrospective" in the 29R-03 sense describes
the analysis's relationship to the delay — analyzed after it occurred — not
to project completion.  A window that has closed is already the past.  A
method specified to close and analyze windows as the project proceeds is a
retrospective observational method that happens to accrete in near-real
time.  Placement: **Observational / Dynamic Logic / Contemporaneous As-Is
family — a disciplined descendant of MIP 3.3**, proposed as its own MIP
because it changes what 3.3 measures and how prescriptively, not just how
carefully.  ("MIP 3.10" is shorthand; formal placement would carry a
layered-taxonomy name, e.g. Observational–Dynamic–Contemporaneous/Balanced.)

Strategic note: 29R-03 itself was a codification of existing practice, not
an invention.  A credible new MIP proposal codifies what good practitioners
already half-do, into a protocol precise enough that two analysts produce
the same tables.  That is exactly the gap targeted below.

### 8.2 What actually makes existing MIPs user-hostile (design targets)

1. **Embedded discretion.**  Window boundaries, update rectification, path
   selection, attribution narrative — every step of 3.3/3.4 contains expert
   judgment, which is why field staff cannot run them and why opposing
   experts running "the same method" diverge.  *Target: determinism — same
   inputs, same output, from any practitioner.*
2. **Net-only measurement.**  Windows methods measure net critical-path
   movement per window; offsetting parallel delays vanish.  An owner delay
   of 10 wd and a contractor delay of 8 wd on parallel near-critical paths
   report as "10 wd owner window" — the 8 wd of functional concurrency is
   invisible until someone argues it.  *Target: concurrency measured, not
   argued.*
3. **Unauditable outputs.**  A windows analysis concludes "the window slip
   is attributable to X" without an arithmetic identity a non-expert can
   check.  Cost control solved this a century ago: books must balance.
   *Target: every day of slip booked to a named cause, rows sum to the
   control total, residual shown explicitly.*
4. **End-loaded execution.**  All nine MIPs are run as projects (the
   analysis kind) after the project (the construction kind).  *Target:
   append-only accretion — each closed window is written once; at any
   mid-project date a complete retrospective analysis to date exists.*

### 8.3 Candidate shapes considered

| Shape | Verdict |
|---|---|
| **A. The Delay Ledger** — deterministic, balanced, dual-lens windows method (below) | **Recommended** — hits all four targets |
| B. Dual-lens concurrency measurement bolted onto MIP 3.3 | Contained within A; viable smaller paper if A proves too big |
| C. Daily-resolution as-built criticality (retrospective longest path at daily grain) | Strong forensically; needs as-built logic reconstruction — the opposite of field-friendly; not during-execution |
| D. Rolling half-step (MIP 3.4 industrialized/automated) | Automation of an existing MIP, not a method; weakest novelty claim; least user-friendly mechanics |

### 8.4 The recommended shape: MIP 3.10, the Delay Ledger method

**Hook:** cost gets a monthly close, a trial balance, and an audit trail;
time gets a lawsuit five years later.  The method gives the schedule a
monthly close.  ("Double-entry delay accounting.")

Protocol properties (the spec, sketched):

1. **Windows = published updates.**  No boundary discretion, no window
   shopping.  (Sub-windowing permitted only by a specified rule when a
   window contains a re-baseline.)
2. **Control total.**  Per window, per tracked milestone: net slip of the
   tool-of-record forecast, in working days on the governing calendar.
3. **Balanced decomposition.**  The window's slip is booked to cause
   accounts: progress shortfall vs. planned pace (by path and responsible
   party), logic/duration/constraint/calendar revisions (each edit named,
   from the version-to-version change register), scope additions/deletions,
   and mitigation gains (negative bookings).  **Rows must sum to the
   control total; any gap is reported as an explicit unexplained residual
   line** — never silently absorbed.  A large residual is itself a finding
   (hidden constraints, resource leveling, external links).
4. **Dual-lens measurement.**  Lens 1 (net): critical-path movement, as
   MIP 3.3 measures today.  Lens 2 (gross): the independent movement of
   *every* longest-path candidate within a defined near-critical band —
   each party's delay measured on its own paths whether or not that path
   "won" the criticality race that window.
5. **Measured concurrency matrix** (§8.5).
6. **Append-only accretion.**  A closed window's ledger row is immutable;
   corrections post as adjusting entries in the current window (the
   accounting idiom again).  Mid-project, the ledger to date *is* the
   retrospective analysis to date.
7. **Determinism constraints.**  All parameters (band width, tie-breakers,
   calendar conventions, de minimis threshold) carry protocol defaults;
   deviations must be disclosed with sensitivity shown.  Acceptance
   criterion: two practitioners, same files → identical ledgers.
8. **Scope boundary.**  The MIP measures and attributes to *responsibility
   codes*; entitlement, concurrency doctrine, and quantum remain outside —
   the same measurement/legal split 29R-03 already draws.

**Two implementation levels** (this resolves the field-friendliness vs.
rigor tension instead of compromising on it):

- **Level 1 — field (no CPM engine).**  Tool-of-record dates and floats
  only; decomposition from the change register and path movements;
  balancing enforced with the residual line carrying whatever cannot be
  attributed mechanically.  Runnable by a project scheduler monthly.
- **Level 2 — expert (diagnostic CPM engine).**  Half-step recomputation
  (progress-only vs. revisions-only reschedules) makes the
  progress/revision split exact and shrinks the residual toward zero;
  engine output labeled diagnostic-delta per the ANALYTICS_PROPOSAL §0
  validation-handshake discipline.  Level 2 *audits* Level 1's ledger
  without changing its structure — the field ledger and the expert analysis
  are the same document at different assurance levels.

**Worked micro-example (fixture-scale):**

> Window 5 (DD 01-Jun → 01-Jul), milestone M-100.  Control total: +12 wd.
>
> | Booking | Path | Party | wd |
> |---|---|---|---|
> | Progress shortfall — piling | A (driving) | Subcontractor | +7 |
> | CO-14 added scope + logic | B (near-crit) | Owner | +4 |
> | Weather calendar exception | A | Neutral | +2 |
> | Resequencing gain (mitigation) | A | Contractor | −1 |
> | Unexplained residual | — | — | 0 |
> | **Balance** | | | **+12 ✓** |
>
> Concurrency matrix: owner-only 3 wd · contractor-only 6 wd · literal
> concurrent 3 wd · functional concurrent 4 wd · pacing-flagged 0 wd.

A superintendent can read that table.  That is the user-friendliness claim,
made concrete.

### 8.5 Concurrency: measured, doctrine-agnostic

29R-03 discusses functional vs. literal concurrency; no MIP *measures*
either — they are identified, then argued.  The ledger outputs both as
quantities:

- **Functional concurrency**: window-level overlap — for each party, gross
  delay booked on any band path in the window; functional overlap =
  min(gross per party) after netting mitigation, reported per window.
- **Literal concurrency**: calendar-interval intersection of the measured
  delay events inside the window (from actuals: the days each driven
  activity actually sat delayed), reported in days of true overlap.
- **Pacing flag**: a party's slip on a path whose relative float against
  the other party's driven path *grew* during the window is flagged as a
  pacing candidate — descriptive only, feeding the contemporaneous-
  declaration practice from §7.3 where the parties adopt it.
- The matrix is handed to whatever doctrine governs (Malmaison, dominant
  cause, apportionment, or §7's contractual election).  The method's claim
  is narrow and defensible: *whatever rule you apply, apply it to measured
  overlaps, not asserted ones.*

### 8.6 Attack surface (honest register)

1. **"Determinism meets dirty data."**  Updates with broken logic or status
   make judgment-free analysis impossible.  Answer: a specified intake gate
   (tool-agnostic minimum criteria; ScheduleIQ's 54-check battery is one
   implementation) plus the rule that what cannot be mechanically
   attributed lands in the residual line, visibly.  The method degrades
   *loudly*, which is the design.
2. **Band width is a parameter** (the new λ).  One dial, protocol default,
   mandatory sensitivity disclosure.  Materially smaller surface than the
   kernel, which is why the core method is deliberately unweighted.
3. **The residual will be attacked** ("your books don't balance").  Better
   an explicit residual than the silent mis-attribution every narrative
   method commits; Level 2 exists to shrink it.
4. **Responsibility coding remains human** — same relocation-of-fights
   honesty as §7.3: small, early, specific disputes instead of global late
   ones.
5. **"Windows analysts already do this."**  Ad hoc, sometimes, invisibly —
   never as a codified deterministic protocol with balancing rules and
   measured concurrency.  Codification of half-practice is precisely what
   29R-03 itself was; that rejoinder is the paper's legitimacy argument,
   and it needs the prior-art sweep to survive (daily-windows variants,
   concurrency-quantification papers, SCL time-slice practice notes).

### 8.7 Relationship to the tabled options and the LI indices

- The core method uses **no LI index**: longest path, a near-critical band,
  working-day arithmetic, and a change register — all standard concepts,
  fully tool-agnostic.  This maximizes MIP credibility (no proprietary
  dependency) and keeps the disclosure decision small.
- The LI indices become an **optional diagnostics annex**: FCBI as a
  weighted refinement of Lens 2, PCI as the band-stability warning, RDI/IL
  as management-conduct context.  ScheduleIQ's competitive position becomes
  "the reference implementation of MIP 3.10 plus proprietary diagnostics on
  top" — a *better* commercial posture than metrics-as-the-method.
- §3 Option A (sealed as-managed record) is the ledger's natural custody
  layer; §7 Option E is the ledger with contractual bindingness attached.
  Nothing tabled is wasted: **the ledger is rung 0 of §7.6's ladder**, and
  the paper sequence becomes: MIP 3.10 (method) → protocol (custody) →
  regime (contract), each publishable alone.

### 8.8 Paper implications and gating additions

This is the literal new-MIP paper originally asked for, now taxonomically
sound.  Recommended title direction: *"A Monthly Close for the Schedule:
a Proposed Tenth Method — Deterministic, Balanced, Concurrency-Measuring
Windows Analysis."*  CDR-track fit is exact; the closing invitation to the
FSA subcommittee (§3 Option D's one paragraph) now has a concrete object.

Gates (additive to §5): (9) prior-art sweep extension per §8.6.5;
(10) demonstrate determinism empirically — two independent runs (different
operators, ideally one non-expert) on the fixture set producing identical
ledgers, reported in the paper; (11) Level-1 residual size on the real
project series — if the no-engine residual routinely swamps the bookings,
Level 1's field claim fails and the method needs the engine port
(ANALYTICS_PROPOSAL §0) before print; (12) the worked example must fit on
one page or the user-friendliness claim is self-refuting.

### 8.9 Open questions for RJL (third set)

10. Does the paper propose the MIP alone (Shape: method paper), or method +
    the §3 custody protocol as its recommended practice context?
11. Is the "delay ledger / monthly close" accounting idiom the brand, or
    does that read as gimmick to the CDR audience?  (Alternative sober
    name: Balanced Windows Analysis.)
12. Level 2 requires the CPM engine port — does this paper's timeline
    accelerate ADR-0007/ANALYTICS_PROPOSAL §0, or does the paper ship
    Level 1 only with Level 2 described?
13. Band-width default: fixed working days, percent of remaining duration,
    or calendar-scaled?  (Needs a small fixture study; the default printed
    in the paper will be quoted forever.)

---

## 9. Fourth pass (2026-07-12): the unoccupied method space — beyond descendants of the nine

§8's Delay Ledger is a disciplined descendant of MIP 3.3.  This pass widens
the aperture: what methods exist *outside* the family tree of the nine?
The systematic route is to enumerate the assumptions all nine MIPs share —
each broken assumption is an unoccupied room in the taxonomy's house.

### 9.1 Six assumptions every existing MIP shares

| # | Shared assumption | What breaking it yields |
|---|---|---|
| 1 | **Deterministic point-estimate output.**  Every MIP produces a single attribution number with no error bar.  Delay analysis may be the only quantitative forensic discipline with no concept of confidence interval. | Probabilistic / interval attribution (§9.2-F1) |
| 2 | **Single method, single analyst.**  No MIP is an ensemble; disagreement *between* methods is treated as embarrassment, never as measurement. | Ensemble / convergence protocols (folded into F1) |
| 3 | **The schedule testifies about itself.**  As-built = the actual dates the schedule's own author entered.  No MIP specifies independent evidence for the as-built. | Evidence-fused as-built reconstruction (F3) |
| 4 | **Activity/logic is the unit of analysis.**  No MIP reasons about crews, workfaces, locations, or production flow — the things field delay is actually made of. | Production-evidence methods (F2) |
| 5 | **The plan network is treated as the causal model.**  Collapsed as-built pretends as-built logic is a causal graph; no MIP separates "the plan's logic" from "what actually caused what." | Event-graph causal method (F4) |
| 6 | **End-loaded execution.**  (Already broken by §8's append-only accretion.) | — covered |

### 9.2 The four new families

**F1 — Uncertainty-quantified attribution ("delay analysis with error
bars").**  Three implementations of one idea, cheapest first:

- *Bracket method*: compute each party's best-case and worst-case
  attribution under the same published measurement rules; output is a
  bounded interval per party, not a point.  The gap between brackets is the
  genuinely arguable zone — parties litigate the gap, not the whole
  project.  Settlement-forcing by construction, observational-cheap.
- *Ensemble convergence*: run k cheap methods (e.g., 3.2 + 3.3 + selected
  3.7 windows) under a defined convergence protocol; agreement = robust
  attribution, divergence localizes the contested windows for deep
  analysis.  Codifies the triangulation tribunals already implicitly
  reward.
- *Probabilistic but-for (PBF)*: delay-event register + as-built model with
  uncertainty distributions on contested logic/durations (priors calibrated
  empirically from the project's own forecast track record — the FRB
  machinery); Monte Carlo collapse yields a *distribution* of but-for
  completion per event set.  Attribution via expected criticality-days or a
  **Shapley-value allocation across events** — cooperative game theory's
  principled answer to joint causation, which handles concurrency *by
  construction*: literally and functionally concurrent events share credit
  per marginal contribution across orderings, and P(concurrent) is itself
  an output per window.

The forensic argument for F1 is the strongest in this memo: **Daubert's
third factor asks for a method's known or potential error rate, and no
existing delay method can answer the question.**  F1 is the first that can.
Taxonomically it is not a tenth MIP but a new layer — output type
(point / interval / distribution) — orthogonal to observational vs. modeled.

**F2 — Production-evidence methods ("delay measured where it happens").**
Two implementations:

- *Workface Availability Method (WAM)* — the field-native one.  For each
  driving/near-critical activity (band from the schedule) and each working
  day, classify the day from contemporaneous records into one of four
  states with party-coded reasons: **U** — workface unavailable
  (predecessor incomplete, access denied, open RFI/drawings, materials,
  permits, weather; each U-day carries reason + party), **A** — available
  but unmanned (crew absent/diverted), **M** — manned but under-producing
  (flagged to disruption, not booked as delay), **P** — producing.
  Activity delay = ΣU (by party) + ΣA + productivity remainder; daily codes
  roll up the driving paths into window bookings — **feeding §8's ledger
  directly** (WAM is where the ledger's bookings come from at daily grain).
  Concurrency is *counted, daily, mechanically*: a calendar day showing
  U(owner) on one driving front and A(contractor) on a parallel driving
  front is a literal concurrent day.  Precedence rule within one activity:
  U dominates A (a crew cannot be deployed to an unavailable front).
  The data discipline is one line per front per day — which is Last
  Planner's constraint log and daily-report practice already; the method
  makes PPC reason codes attribution-grade.  This is the most
  user-friendly, most during-execution-native, best-concurrency candidate
  in the entire memo.
- *Flowline forensics (location-based)*: delay as production-rate
  divergence and location-handoff interference in LBMS terms; sees
  trade-stacking cascades CPM logic never models.  Powerful where
  location-based data exists; niche elsewhere.  Second paper, not first.

**F3 — Independent as-built reconstruction (evidence fusion).**  Rebuild
the as-built from evidence streams *other than the schedule's own claims* —
daily reports, timestamped photos, RFIs/submittals, access logs, 4D/reality
capture — and measure delay against the reconstructed record.  Until
recently economically impossible; LLM document extraction changed the cost
structure, and the method question becomes the *protocol that makes
AI-extracted evidence defensible* (dual-extraction agreement rates,
human-verification sampling, disclosure of extraction prompts).  Honest
placement: this is a source-validation revolution that upgrades every MIP
rather than a competing MIP — publishable, timely, but a different paper
than "a new method."

**F4 — Event-graph causal method.**  Maintain the plan network and a
separate explicit causal graph of what-happened claims, each edge tied to
evidence; compute counterfactuals on the event graph, not the CPM.
Codifies what good experts do narratively.  Verdict: intellectually right,
tribunal-risky (reads academic), and the evidence burden is F3's anyway.
Park it; steal its plan-vs-causal-graph distinction for any paper's
limitations section.

### 9.3 Scoring against the stated criteria

| Candidate | User-friendly | Concurrency handling | During execution | Fundamental novelty | Prior-art risk | ScheduleIQ fit |
|---|---|---|---|---|---|---|
| §8 Delay Ledger | High (accounting idiom) | Good (measured matrix) | Native | Moderate (3.3 descendant) | Medium | Ships today (Level 1) |
| F1 Bracket | High (an interval) | Good (bracket overlap) | Yes | High | Low-Med | Near-term |
| F1 PBF/Shapley | Low mechanics, readable outputs ("80% chance owner drove ≥8 of 12 days") | **Best in class (by construction)** | Per window | **Highest** | Medium (academic Shapley-delay papers exist) | Needs MC module (planned, ANALYTICS_PROPOSAL §4) + engine |
| F2 WAM | **Best in class** | **Best in class (daily, counted)** | **Native** | High | Medium ("daily delay measure" practice exists — sweep) | New data layer; modest tooling |
| F2 Flowline | Low (needs LBMS culture) | Good | Native | High | Medium (Seppänen corpus) | Poor near-term |
| F3 Evidence fusion | Expert-side | n/a (validation layer) | Yes | High + timely (AI) | Low as protocol | Large build |
| F4 Event graph | Low | Formal but contestable | No | Medium | Medium | Poor |

### 9.4 Where this lands

Two front-runners emerge from outside the nine's family tree, and they are
complementary rather than competing:

- **WAM (F2)** is the method the *original vision* was always pointing at:
  field staff can run it because field staff already generate its raw
  material; concurrency stops being doctrine and becomes a daily count; and
  it composes with §8 — WAM supplies the daily-grain bookings, the ledger
  supplies the monthly close and balancing discipline.  A combined
  "WAM + Ledger" method paper is the strongest user-friendly/concurrency
  package this memo has produced.
- **PBF (F1)** is the *deepest* novelty — a new taxonomy axis, the Daubert
  error-rate argument no existing method can answer, Shapley-principled
  concurrency, and empirical priors from FRB.  It is expert-tooling-heavy
  (MC module + engine port) and mechanically opaque to field staff, so it
  serves the "revolutionary method" ambition, not the "field-friendly"
  one.  The bracket method is its cheap observational cousin and could
  ride inside either paper as the uncertainty-expression layer.

Honest tension to decide: WAM optimizes the user's stated criteria; PBF
optimizes novelty and forensic-epistemology impact.  One paper cannot carry
both without becoming a manifesto.

### 9.5 Prior-art kill-list additions

Sweep before committing: "daily delay measure" / daily windows practice
papers; Last Planner / PPC-as-evidence literature (lean construction
corpus); Shapley or cooperative-game delay-apportionment papers (known to
exist academically — the question is whether any is practicable/MIP-shaped);
probabilistic/Monte-Carlo retrospective delay papers; Seppänen & Kenley
LBMS forensics; AI/LLM document-extraction-for-claims papers (fast-moving,
sweep last).

### 9.6 Open questions for RJL (fourth set)

14. Pick the lane for the flagship paper: (a) WAM + Ledger (field-native,
    serves the original dispute-avoidance vision), (b) PBF (deepest
    novelty, expert audience), or (c) §8 Ledger alone as the conservative
    core with F1/F2 as future-work signposts?
15. Does LI have (or can it get) a project with Last-Planner-style daily
    constraint/reason-code records plus a schedule update series — the
    validation substrate WAM needs?
16. If PBF: does the paper commitment justify accelerating the Monte Carlo
    module and CPM engine port, or is PBF the *second* paper after its
    tooling exists?
17. Shapley-based apportionment produces numbers no current legal doctrine
    asks for.  Is LI comfortable publishing measurement that runs ahead of
    doctrine (arguing doctrine should catch up), or must every output map
    to an existing doctrinal question?

---

## 10. Fifth pass (2026-07-12): the 3.3 × 3.9 hybrid — Contemporaneous Collapse

Prompt: MIP 3.3's simple elegance is attractive, and so are MIP 3.9's
analytical depth and concurrency attribution.  Those preferences point at a
specific structural observation:

**The observational/modeled dichotomy conflates two different jobs.**
*Measuring* delay is done best observationally — use the record as-is, no
analyst-manufactured artifacts (3.3's elegance).  *Attributing* delay is
done best counterfactually — but-for extraction (3.9's depth).  Every
existing MIP picks one tool and makes it do both jobs.  The hybrid assigns
each job its best tool, window by window.

### 10.1 The method: Contemporaneous Collapse (CCM)

One-line pitch: **3.9's depth at 3.3's cadence, on 3.3's evidence.**

3.9's fatal weakness is its collapse basis: an analyst-built as-built model
whose logic is invented after the fact — the most manufactured artifact in
delay practice — and a counterfactual that rewinds years into fiction.
CCM's move: **collapse the contemporaneous updates instead.**

Per window (update N → update N+1):

1. **Measure observationally (the 3.3 step, untouched).**  Net milestone
   slip from the tool-of-record updates as-is: the control total.
2. **Enumerate the window's events mechanically.**  From the change
   register (imposed scope/logic changes, directives) and the progress
   variance decomposition (band-path activities that consumed more working
   time than the update-N plan), each event party-coded.  The extraction
   set derives from data both parties already exchanged — killing 3.9's
   biggest subjectivity, event framing.
3. **Attribute counterfactually (the 3.9 step, made shallow).**  On update
   N+1, run de-impact collapses per party bucket: remove owner events
   (restore to update-N planned pace/logic — a mechanical, published
   convention), remove contractor events, remove both.  Four schedule runs
   per window; with a validated diagnostic engine, seconds.
4. **Report by inclusion-exclusion.**  With S(X) = window slip under event
   set X: owner-exclusive = S(O,C) − S(C); contractor-exclusive =
   S(O,C) − S(O); **concurrent = S(O) + S(C) − S(O,C)** — measured
   functional concurrency *is the inclusion-exclusion overlap term*, not a
   doctrine.  The identity balances by construction:
   exclusive_O + exclusive_C + overlap (+ residual) = control total.
   Three buckets (owner/contractor/neutral) give a pairwise + triple
   overlap matrix — still mechanical.  If a single number per party is
   demanded, Shapley splits the overlap terms symmetrically; the raw
   marginal table is always published first (transparency before
   allocation), and doctrine (Malmaison, apportionment, time-no-money) is
   applied to the measured overlap, per §7.3/§8.5.

> Worked micro-example — Window 7, control total +12 wd:
> collapse runs give S(C-only) = 5, S(O-only) = 9, S(none) = 0.
> Owner-exclusive 12−5 = **7 wd** · contractor-exclusive 12−9 = **3 wd** ·
> concurrent 9+5−12 = **2 wd** · residual 0 · **sum 12 ✓**.
> One readable sentence: "This month slipped 12 days: 7 only the owner's
> events caused, 3 only the contractor's, 2 both would have caused."

5. **Optional bidirectional check.**  Run the additive mirror (insert the
   window's events into update N, forward-predict slip) and compare with
   the subtractive result: the gap is model error, reported per window — a
   convergence signal (F1-ensemble localized) and a Daubert error-rate
   breadcrumb without full PBF machinery.

### 10.2 Why the shallow counterfactual is the defensible one

A full collapsed as-built asks the model to rewind years; every rewound
month compounds the fiction (logic that would have changed, resequencing
that would have happened).  CCM's counterfactual is **one window deep**:
"where would the milestone stand at month-end but-for this month's events"
— asked of the very network the parties were jointly managing to that
month.  The base document is not the analyst's model of the project; it is
the project's model of itself, exchanged contemporaneously.  Cross-window
ripple effects (owner delay in window 3 pushing work into winter in window
7) are explicitly *not* re-litigated — window attributions bank forward,
the same convention all windows practice already applies, stated as a
limitation rather than hidden.

### 10.3 Fit with everything else in this memo

- **§8's Delay Ledger is CCM's reporting format**: CCM supplies
  but-for-grade bookings; the ledger supplies the monthly close, balancing
  discipline, and append-only custody.  The half-step (MIP 3.4) is
  revealed as a 2-variant special case of CCM's collapse set (progress
  vs. revisions); CCM generalizes it to party-coded marginal analysis.
- **Upgrade path within F1**: CCM (deterministic points) → dual-convention
  /bracket runs (intervals) → PBF (distributions).  One idea family, three
  maturity stages — the flagship can ship stage 1 and *describe* the rest.
- **Zero new field burden** — the decisive contrast with WAM (§9): CCM
  needs no daily data discipline, no reason codes, nothing the project
  doesn't already produce.  It extracts 3.9-grade attribution from the
  update series every CPM-specified project already exchanges monthly.
  WAM remains the richer method *where* the daily record exists; CCM is
  the method for the projects that exist.
- **Tooling**: the engine is the gate.  The firm's mip39 tool already
  contains PDM scheduling, ABCS destatusing, and longest-path extraction
  (ANALYTICS_PROPOSAL §0 port plan) — CCM is arguably the natural
  destination of that port, and the "user-friendly" claim rests on
  automation: mechanics by machine, judgment only at event coding, outputs
  a superintendent can read.

### 10.4 Attack surface (honest register)

1. **De-impact conventions are modeling judgments** ("what pace would the
   contractor have achieved but-for the interference?" — the entanglement
   problem).  Answer: a published, symmetric, mechanical convention
   (restore to update-N planned pace), with the dual-convention bracket as
   the sensitivity disclosure when contested.
2. **Update quality garbage-in** — same as 3.3; same intake-gate answer
   (§8.6.1), and the residual line catches what the collapse cannot
   explain.
3. **Additive-in-windows is practiced** (3.7 run per window is known
   practice, and half-step is codified).  The novelty claims are
   specifically: subtractive collapse on *contemporaneous updates* rather
   than a constructed as-built; the full marginal / inclusion-exclusion
   protocol as *codified concurrency measurement*; determinism and
   automation discipline.  The prior-art sweep must test exactly those
   three (practitioner "but-for windows" variants, mip39-adjacent
   methodology papers, contemporaneous period analysis literature).
4. **Cross-window ripple exclusion** — stated convention (§10.2), shared
   with all windows methods; opposing experts will raise it regardless.

### 10.5 Where this leaves the flagship question (Q14 revised)

CCM changes the answer-space of Q14: it dominates §8's ledger-alone option
(the ledger becomes its reporting layer) and outflanks WAM on adoptability
(zero new data burden vs. a new daily discipline).  Revised recommendation:
**flagship = CCM + Ledger** ("Contemporaneous Collapse, reported as a
monthly delay close"), with WAM and PBF as named future work.  The paper
inherits §8's gates (determinism experiment, residual size, one-page
example) plus one new hard gate: **the engine port with its validation
handshake must exist at least at prototype level**, because CCM without a
validated engine is a paper about software that doesn't run yet.

18. Does the CCM framing change the engine-port priority (ADR-0007 /
    ANALYTICS_PROPOSAL §0) from "analytical roadmap item" to "paper
    prerequisite," and is that acceptable scope for this effort?
19. Is "Contemporaneous Collapse" the right name, or does LI want the
    method named for what it outputs (e.g., "Marginal Window Analysis,"
    "But-For Windows") rather than its mechanics?

---

## 11. Sixth pass (2026-07-12): folding in the half-step — the two-axis lattice

Prompt: add MIP 3.4's defining element — the half-step separation of
progress from revisions — into §10's Contemporaneous Collapse.

### 11.1 What the half-step adds: a second axis

§10's CCM decomposes each window along one axis: **party** (owner /
contractor / neutral).  The half-step decomposes along a different axis:
**mechanism** — slip caused by actual performance against the then-current
plan (progress half) vs. slip caused or recovered by non-progress edits
(revision half).  Neither axis subsumes the other; crossing them yields a
**mechanism × party matrix per window**, and each cell is forensically
distinct territory:

| | Progress-driven | Revision-driven |
|---|---|---|
| **Owner** | Interference with existing scope: suspensions, access, holds on active work | Added scope, directives, change orders — the compensable heartland |
| **Contractor** | Performance shortfall — classic contractor delay | Resequencing/replanning; *negative* bookings = mitigation; persistent slip-recovery by edit = manipulation signature |
| **Neutral** | Weather on active work | Calendar/exception revisions |

Mechanics: build the MIP 3.4 half-step schedule (update N's network,
N+1's progress only — the mip39 tool's ABCS destatusing machinery), which
bifurcates the control total mechanically before any party coding.  Then
run §10.1's party-bucket collapses *within each half*: progress-half
collapses restore underperforming activities to planned pace per party;
revision-half collapses remove each party's named change-register edits.
Inclusion-exclusion balances each half, halves sum to the control total,
concurrency overlaps report per half.

> Worked example, extended — Window 7, control total +12 wd.
> Half-step: progress-driven +9, revision-driven +3.
> Progress half: contractor-exclusive **6**, owner-exclusive **1** (RFI
> hold on active work), concurrent **2** → 9 ✓.
> Revision half: owner-exclusive **+4** (CO-14), contractor-exclusive
> **−1** (resequencing recovery), concurrent 0 → 3 ✓.  Grand total 12 ✓.
> Readable: "12 days this month: 6 contractor performance, 1 owner hold,
> 2 concurrent on active work; 4 owner added scope, less 1 recovered by
> contractor resequencing."

### 11.2 Three things the combination buys beyond either parent

1. **It stratifies attribution by evidentiary confidence.**  The revision
   half's party coding is near-mechanical — every edit is a named, logged
   change-register entry with an author.  The progress half is where
   entanglement lives ("*why* did piling underperform?").  The matrix
   makes that asymmetry explicit instead of smearing it — and it is
   exactly where WAM (§9) docks: the daily U/A availability codes are the
   evidence layer for the progress column specifically.  The methods
   compose rather than compete.
2. **The manipulation detector is built into the method.**  Persistent
   positive progress-half bookings offset by persistent negative
   revision-half bookings is the evergreen signature — slip continually
   erased by paper — now quantified per window inside the attribution
   itself (ties to the evergreen detector, RDI, and SMI as corroborating
   diagnostics).  3.4 practitioners know this pattern; no method reports
   it as a standing output.
3. **It repairs the half-step's own known defect.**  Classic 3.4 applies
   progress first, then revisions — but the split is order-dependent
   (revisions applied before progress can shift the critical path
   differently), and the progress-first convention is an unexamined
   tradition.  The marginal framework treats {progress, revisions} as two
   more event buckets: run both orders (or the full lattice), report the
   order-sensitivity, Shapley-average if a single split is demanded.  The
   protocol default stays progress-first for continuity with 3.4, with
   order-sensitivity disclosed — an honest upgrade the FSA community can
   verify on its own cases.

### 11.3 Cost, tooling, and the automation claim

The full lattice (2 mechanisms × 3 parties = 6 buckets → the informative
subset of exclusive marginals plus pairwise overlaps) is roughly 10–15
engine runs per window per milestone.  No human analyst has ever done
exhaustive marginal analysis because it was fifteen schedule runs a window;
for a validated engine it is seconds.  This is the honest form of the
user-friendliness claim: **the machine runs the lattice, judgment lives
only at event coding, and the field reads a quadrant chart.**  The engine
port (Q18) remains the hard gate; the half-step integration adds the
destatusing path, which the mip39 core already implements.

### 11.4 Effect on the flagship

The flagship concept (Q14, revised in §10.5) becomes: **three-parent
synthesis — 3.3's measurement, 3.4's mechanism bifurcation, 3.9's
counterfactual party attribution — reported as §8's monthly delay close.**
That parentage is the paper's acceptance strategy: every element is either
an existing codified MIP's best feature or a mechanical protocol on top of
one; the method reads as evolution, not invention.  Candidate framing for
the title: the window "halved by 3.4, then quartered by party" — the
**Quartered Windows** presentation (owner/contractor canonical view,
neutral folded into an annex row).

One entanglement caveat for the limitations section: some revisions are
*responses* to progress slip (resequencing because of it).  The matrix
books mechanism, not motive — the response relationship is the protocol
layer's job (IL's emergence-to-response log), not the attribution
method's.  Stated, not solved.

### 11.5 Open questions (fifth set)

20. Presentation default: 2×2 quartered-window chart (neutral folded into
    an annex) or the full 2×3 matrix?  The quartered chart is the
    memorable artifact; the matrix is the complete one.
21. Order convention: progress-first (3.4 continuity) with disclosed
    sensitivity, or order-symmetrized split as the default?  Continuity
    is recommended — the paper should spend its novelty budget elsewhere.
22. Does the flagship paper mention WAM as the optional evidence layer
    for the progress column (one paragraph), or keep the paper's surface
    minimal and hold WAM entirely for follow-up work?

---

## 12. Artifacts (2026-07-12)

The flagship concept (§10–11) is now drafted as a step-by-step
methodology and packaged for external adversarial review:

- **`docs/CCM_METHODOLOGY.md`** — the method spec, working draft v0.1:
  definitions, prerequisites (engine handshake, sealed parameter table),
  the three-phase procedure (measure → bifurcate → enumerate → collapse →
  decompose → ledger), conventions and edge cases, outputs with
  recheckable identities, limitations register, corrected worked example,
  QA/acceptance tests.  Written tool-agnostically, as the paper's method
  section would be; contains no LI index mathematics.
- **`docs/CCM_PEER_REVIEW_PROMPT.md`** — self-contained adversarial
  peer-review prompt for an external LLM (or human reviewer): three-hat
  reviewer role (hostile expert / FSA subcommittee / practical
  scheduler), 29R-03 primer, six explicit novelty claims (N1–N6) each
  requiring a verdict, nine review tasks (including constructing minimal
  counterexample networks against the inclusion-exclusion math and
  rechecking the worked example), and a mandatory findings/kill-list
  output format.  Embeds the methodology verbatim; regenerate when the
  methodology changes.
