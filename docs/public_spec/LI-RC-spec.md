# The LI Schedule Report Card — LI-RC v1.0

> **NOT YET PUBLISHED — publication decision pending.**  See `README.md` in
> this directory.  This document explains the methodology in prose; the
> normative, machine-readable spec is `scorecard.yaml`
> (`src/scheduleiq/scorecard.yaml` in the ScheduleIQ source tree — copied
> into this directory verbatim at publication time).  Where this document
> and `scorecard.yaml` disagree, `scorecard.yaml` governs.

## 1. What this is

The LI Schedule Report Card converts a schedule quality/health/trend
assessment (built from the ~70 published-standard checks in the ScheduleIQ
Metric and Heuristic Matrix — DCMA's 14-point assessment, GAO's Schedule
Assessment Guide, NDIA's PASEG, AACE RP 29R-03, the SCL Protocol, and a set
of LI bespoke indices) into a single letter grade, with full transparency
into how every point was earned or lost.

Two cards exist:

- **The file card** — one schedule file, seven categories (six for a
  baseline file with no execution history).
- **The series card** — a multi-file update series, four categories plus a
  fifth "file-quality trajectory" category built from the file cards
  themselves.

## 2. The scoring curve

Every check with a published pass/fail threshold converts its measured
value to a 0-100 conformance score via a three-point piecewise-linear curve:

```
100 points  at the ideal value        (usually zero occurrences, or the
                                        standard's own target for a ratio
                                        check like CPLI or BEI)
 70 points  at the published threshold (the standard's pass mark — not
                                        excellence: meeting a DCMA 5% limit
                                        exactly earns a C-, not an A)
  0 points  at the "fail ceiling"      (by default, three times the
                                        threshold — the point a metric has
                                        gone from "needs attention" to
                                        "failed wholesale")
```

with linear interpolation between the anchors.  Checks whose published
threshold is exactly zero ("never allow any of X") collapse the 100- and
70-point anchors into one point (there is no daylight between "ideal" and
"just passing" when the standard is zero-tolerance), so the curve becomes a
straight line from 100 at zero occurrences down to 0 at an explicit,
published fail-ceiling override — five occurrences for most zero-tolerance
count checks, one occurrence for the two checks that are also integrity
gates (see §4).  Every override to the default formula is listed, with a
one-line rationale, in `scorecard.yaml`'s `curve_overrides` (file card) and
`series_curve_overrides` (series card) sections — nothing is hidden.

Checks with no published threshold (pure inventories — "how many calendars
does this schedule use") never move a grade; they are always in the results
workbook, just not in the arithmetic.

## 3. File-card categories and weights

| Category | Weight (update) | What it covers |
|---|---|---|
| Logic & Network Integrity | 25 | Open ends, leads/lags, relationship types, dangling/redundant logic, the critical-path continuity gate |
| Constraint & Float Discipline | 20 | Hard/soft constraints, ALAP, critical/near-critical/negative float, float exceeding the project's own runway |
| Duration & Estimating | 10 | Zero/templated durations, silent duration edits, high duration |
| Status & Data Integrity | 20 | Invalid dates, status/actual-date contradictions, statusing hygiene, data currency — with its own integrity gate |
| Modeling Mechanics | 10 | Calendars, structure, census |
| Resource & Cost Loading | 5 | Whether the schedule is loaded enough to support resource/cost-based analysis |
| Execution Performance | 10 | BEI, CPLI, missed tasks — **update files only** |

A baseline file has no execution history, so its Execution Performance
weight is redistributed, pro-rata by each category's own weight, across the
other five categories rather than penalizing the baseline for having no
progress yet.  Overall = the weighted sum of category scores.  Each category
score is itself a weighted mean of its member checks' 0-100 scores, weighted
by severity (critical 3, warning 2, banded-informational 1) — informational
checks with no published band carry weight 0 and never move the number.

## 4. Integrity gates

A schedule cannot buy a good grade on volume of easy passes while its
underlying data is untrustworthy:

- **Status & Data Integrity gate** — if the invalid-dates check or the
  status/actual-date-contradiction check scores 0 (any single occurrence,
  for these two), Status & Data Integrity is capped at 40 and the overall
  grade is capped at 78 (a C+ ceiling), no matter how clean the rest of the
  schedule is.
- **Logic Continuity gate** — an unresolved critical-path continuity break
  caps Logic & Network Integrity at 60.

Every gate that trips is printed on the card face with the rule that fired.

## 5. Grade bands

A ≥ 90 · A- ≥ 85 · B+ ≥ 80 · B ≥ 75 · C+ ≥ 70 · C ≥ 60 · D ≥ 50 · F < 50.

(For rough continuity with Acumen Fuse's default Schedule Index, whose
"good" band is generally read as anything above about 75 — roughly a B here.)

## 6. The series card

Four categories, built the same way from series-level checks (retroactive
actual-date changes, settings drift, critical-path stability, logic and
scope churn, float erosion, forecast credibility) plus a set of LI bespoke
indices (Logic Half-Life, Forecast Reliability Band, Path Concentration
Index, Recovery Debt Index, Baseline Dilution Index, Bow-Wave Index,
Intervention Latency) normalized to 0-100 by published mappings — each with
its own rationale line in `scorecard.yaml`.  A fifth category, **File-Quality
Trajectory**, is built from the file cards themselves: the *level* (mean
per-file grade) and the *slope* (points gained or lost per update) are
blended so that a mediocre-but-improving series and a good-but-collapsing
series both read as a caution in the middle of the scale, rather than one
number burying the other's signal.  A retroactive actual-date change anywhere
in the series is itself a gate: it caps Update & Record Discipline at 40 and
the series overall at 78, mirroring the file-card status-integrity gate one
level up — the as-built record is the foundation everything else in a delay
analysis is built on.

## 7. Reproducing a grade

Every card states the spec version it was scored against and the SHA-256 of
`scorecard.yaml` in force.  Every ScheduleIQ run additionally writes a
`score_trace.json` alongside the report: every intermediate number (each
check's raw value, its curve anchors, its resulting score, its weight, the
category arithmetic, and any gate application) needed to recompute the final
grade from nothing but the results workbook and this spec.  `reference_scorer.py`
in this directory is a minimal, independent demonstration of exactly that
recomputation for a single category, using only a plain CSV export and this
spec — nothing else.
