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
