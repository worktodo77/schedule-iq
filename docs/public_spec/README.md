# The LI Schedule Report Card — public spec package (PREPARED)

> **NOT YET PUBLISHED — publication decision pending.**  This directory is a
> publication-ready package for the LI Schedule Report Card spec (backlog
> RC6), prepared per docs/REPORT_CARD_DESIGN.md §6's recommendation to
> publish the spec and a minimal reference scorer under an open license
> (Apache-2.0) while ScheduleIQ itself remains proprietary.  Nothing here
> should be shared externally until RJL makes the publication decision and
> this notice is removed.

## What is in this package

| File | Purpose |
|---|---|
| `LI-RC-spec.md` | The public-facing explanation of the scoring methodology: the curve formula, categories, weights, gates, grade bands, and the series (multi-file) extension — a prose companion to the machine-readable spec. |
| `../../src/scheduleiq/scorecard.yaml` | **The actual spec.**  Referenced, not duplicated: `LI-RC-spec.md` explains it, but the YAML file shipped with the tool is the single source of truth a reader (or an opposing expert) should check against.  At publication time, the build step for this package copies that file into this directory verbatim (`scorecard.yaml`) so the published package is self-contained; until then, read it in place. |
| `reference_scorer.py` | A minimal (<150 line), dependency-light script that reads a results CSV (check ID, value, status — the shape of the "Metric Results" sheet ScheduleIQ already writes to every results workbook) and the spec, and reproduces one file-card category's score from first principles.  It is deliberately not a full reimplementation of `scheduleiq.scorecard` — it exists to let a third party independently verify that the published curve formula, given the published inputs, produces the published number. |

## Why this exists (design rationale, docs/REPORT_CARD_DESIGN.md §6)

Every other de-facto industry scoring standard in this space (DCMA's 14-point
metrics, most obviously) is public, and tools compete on implementation, not
on secrecy of the rulebook.  The Report Card is built the same way: nothing
in `scorecard.yaml` is hidden from the analyst who receives a report, so
publishing it costs ScheduleIQ nothing it wasn't already giving away in every
delivered capsule (`capsule/manifest.json` already seals the spec's SHA-256
hash into every reproducibility capsule).  Publishing turns "trust our
grade" into "recompute our grade" — the strongest validation an opposing
expert's independent recomputation can offer is arriving at the same number.

What stays proprietary: the **analytics that feed the bespoke LI indices**
(FCBI, LHL, FRB, PCI, RDI, BDI, CDI, IL, BWI, MML — see
`src/scheduleiq/analytics/li_indices.py` and `li_record.py`).  The spec
defines how those indices are *normalized* into a 0-100 score once computed;
it does not define how they are computed.  A third party can verify that a
given LHL of, say, 8.5 months scores 78/100 per the published curve; they
cannot recompute the 8.5 from the raw schedule without ScheduleIQ (or an
independent Kaplan-Meier implementation of their own).

## Publication checklist (for RJL, not yet actioned)

- [ ] Confirm license (Apache-2.0 per the design doc's recommendation).
- [ ] Copy `src/scheduleiq/scorecard.yaml` into this directory verbatim as
      part of the publish step (keeping the copy and the shipped file in
      sync is a CI concern once this goes out, not a manual one).
- [ ] Stand up the public repository (mirrors the internal mirroring
      arrangement already used for the engine port — see docs/BACKLOG.md L1).
- [ ] Remove the "NOT YET PUBLISHED" notice from this file and from the top
      of `LI-RC-spec.md`.
- [ ] Add a CHANGELOG.md for spec revisions per GOVERNANCE.md §1 (extended
      to cover the spec once published, per docs/REPORT_CARD_DESIGN.md §6).
