# Methodology Notes

## Check populations

Unless a matrix row says otherwise:

- **Population** = task and milestone activities that are not Completed,
  excluding Level-of-Effort, hammock, WBS-summary, and MSP summary rows —
  matching DCMA 14-point and PASEG practice so results are comparable across
  tools.
- **Relationship populations** count relationships whose successor is
  incomplete and whose endpoints resolve to population activities.
- **Day conversions** divide hour values by the activity's own calendar
  hours/day.  The 44-working-day DCMA screens are therefore correct on 10h or
  12h calendars, where naive day math misstates duration.

## Health score

`score = 100 × Σ(w·credit) / Σ(w)` over checks with status PASS/FAIL/WARNING,
where `w = 2` for severity *critical*, `1` otherwise; credit is 1 for PASS,
0.5 for WARNING, 0 for FAIL.  Informational, N/A, and NOT EVALUATED checks are
excluded.  Interpretation bands (triage only): above ~75 sound, 50–75 needs
attention, below 50 poor — deliberately aligned with Fuse's published bands so
analysts migrating from Fuse keep their intuition.

Differences from the Fuse Schedule Index™: Fuse's default mode scores each
*activity* 0/1 on whether it trips *any* selected metric and reports the % of
clean activities; ScheduleIQ scores *checks*, which keeps single noisy metrics
from dominating and lets the report say exactly which standards failed.  Both
are triage aids; neither is an opinion on schedule adequacy.

## Baseline semantics

P6 XER exports carry planned (target) dates; a separately maintained baseline
is not embedded.  Baseline-dependent checks (DCMA-11 Missed Tasks, DCMA-13
CPLI, DCMA-14 BEI, EVM-01 Hit Task %) therefore use, in order of preference:
a linked baseline in the file (MSPDI Baseline 0) → planned/target dates.
When a true baseline file exists, ingest it as the first file of the series;
the change register then measures every later update against it.

## Series analytics

- Files are ordered by data date; a <50% activity-code overlap with the first
  file raises a same-project warning that the analyst must clear (GUI) or
  acknowledge (CLI output/report note).
- Retroactive actual-date detection (TRD-05) compares actual dates for the
  same activity code across consecutive files and flags any change to a
  previously reported value, including removals.  This is intake triage for
  AACE 29R-03 as-built validation: every hit needs an explanation before the
  schedules support delay analysis.
- CEI is computed against the earlier update's forecast finishes within the
  period (PASEG §10.4.5); Hit Task % against baseline finishes falling in the
  period.

## Verification discipline

Every number in the Word report is drawn from the same MetricResult objects
written to the Excel workbooks; the workbooks carry the full population and
offender lists so any figure can be re-derived by hand from the parsed
tables.  Input files are identified by SHA-256 in the report, workbooks, and
audit log.
