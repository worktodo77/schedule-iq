"""LI-house-style report blocks for the intake-accelerator pack (backlog
D1-D8; ANALYTICS_PROPOSAL.md §3.1).

intake_blocks() returns the list-of-dicts block model consumed by docx_li /
report_builder: ALL-CAPS Heading 2, Numbered-Paragraph body with two spaces
between sentences, and teal LI tables — matching the convention already
established for the multi-path section in report/paths_report.py.  Every
accelerator here is intake material for the expert; none of it opines on
causation, entitlement, concurrency, or quantum, which remain reserved to
the expert (CLAUDE.md rules 2 and 4).
"""
from __future__ import annotations

from ..intake import run_intake


def _fmt(x, nd=1):
    return "—" if x is None else f"{round(x, nd):g}"


def _scorecard_blocks(sc) -> list:
    if not sc.files:
        return [{"type": "np",
                 "text": "Data-completeness scorecard.  "
                         + (sc.reason or "No files were available to assess.") + "."}]
    baseline_note = (
        f"The earliest file provided, {sc.baseline_file}, already contains reported "
        "progress and so does not serve as a clean native baseline.  "
        if sc.baseline_has_progress else
        "The earliest file provided does not contain reported progress and serves as "
        "a clean native baseline.  ")
    gap_note = (f"{len(sc.gaps)} update-cadence gap(s) were identified against the "
               "dominant cadence."
               if sc.gaps else
               "No update-cadence gaps were identified against the dominant cadence.")
    blocks = [
        {"type": "np",
         "text": f"Data-completeness scorecard.  {sc.n_files} schedule file(s) were "
                 f"reviewed, spanning data dates {sc.date_range[0]:%d %B %Y} through "
                 f"{sc.date_range[1]:%d %B %Y}, at a dominant cadence of "
                 f"{sc.cadence_label}.  " + baseline_note + gap_note},
    ]
    if sc.rfi_items:
        blocks.append({"type": "np",
                       "text": "Document requests generated from the file set as "
                               "provided follow.  Each line should be triaged by the "
                               "analyst before it is sent to the client."})
        rows = [["Topic", "Draft RFI Line"]]
        for item in sc.rfi_items:
            rows.append([item.topic, item.text])
        blocks.append({"type": "table", "font_sz": 15, "rows": rows})
    return blocks


def _variance_blocks(vr) -> list:
    if not vr.rows:
        return [{"type": "np",
                 "text": "As-planned vs as-built variance register.  "
                         + (vr.reason or "No common activities were found between the "
                                        "baseline and the latest update.") + "."}]
    top = vr.rows[:20]
    blocks = [
        {"type": "np",
         "text": f"As-planned vs as-built variance register.  Comparing the baseline "
                 f"({vr.baseline_label}) to the latest update ({vr.current_label}) for "
                 f"{len(vr.rows)} common activities, sorted by absolute finish "
                 f"variance descending; the leading {len(top)} are tabulated below with "
                 "driving-path membership flagged.  The complete register is in the "
                 "intake Excel workbook."},
    ]
    rows = [["Activity", "Name", "Start Var (wd)", "Finish Var (wd)",
             "Duration Growth (d)", "On Driving Path"]]
    for r in top:
        rows.append([r.code, r.name, _fmt(r.start_variance_days), _fmt(r.finish_variance_days),
                     _fmt(r.duration_growth_days), "Yes" if r.on_driving_path else ""])
    blocks.append({"type": "table", "font_sz": 15, "rows": rows})
    return blocks


def _windows_blocks(wp) -> list:
    if not wp.boundaries:
        return [{"type": "np",
                 "text": "Windows auto-segmentation.  "
                         + (wp.reason or "No boundaries could be proposed.") + "."}]
    blocks = [
        {"type": "np",
         "text": "Windows auto-segmentation.  Candidate window boundaries below merge "
                 "consecutive updates only where driving-path membership overlap is at "
                 f"least {wp.overlap_threshold:.0%} and neither a scheduling-settings "
                 "drift (SET-01) nor a calendar-definition change (CAL-04) occurred "
                 "between them; every boundary records why it was kept.  This is a "
                 "starting proposal for the analyst to adjust, not a windows-analysis "
                 "finding."},
    ]
    rows = [["Start DD", "End DD", "Updates", "Driving-Path Summary", "Boundary Kept — Reason"]]
    for b in wp.boundaries:
        rows.append([b.start_dd.strftime("%d %b %Y") if b.start_dd else "—",
                     b.end_dd.strftime("%d %b %Y") if b.end_dd else "—",
                     ", ".join(b.labels), b.driving_path_summary, b.kept_reason])
    blocks.append({"type": "table", "font_sz": 15, "rows": rows})
    return blocks


def _concurrency_blocks(cc) -> list:
    if not cc.candidates:
        return [{"type": "np",
                 "text": f"Concurrency screening ({cc.caption}).  "
                         + (cc.reason or "No candidate concurrent slippage was "
                                        "identified.") + "."}]
    blocks = [
        {"type": "np",
         "text": f"Concurrency screening ({cc.caption}).  The update pairs below each "
                 "show two or more distinct near-critical chains that lost at least 5 "
                 "working days of float, or slipped their forecast finish by that much, "
                 "in the same window — a candidate list for the concurrency review, not "
                 "a concurrency finding."},
    ]
    rows = [["Window", "Path A", "A Float Δ (d)", "A Finish Slip (d)",
             "Path B", "B Float Δ (d)", "B Finish Slip (d)"]]
    for c in cc.candidates:
        rows.append([c.window_label, " → ".join(c.path_a_codes),
                     _fmt(c.path_a_float_delta_days), _fmt(c.path_a_finish_slip_days),
                     " → ".join(c.path_b_codes), _fmt(c.path_b_float_delta_days),
                     _fmt(c.path_b_finish_slip_days)])
    blocks.append({"type": "table", "font_sz": 15, "rows": rows})
    return blocks


def _evergreen_blocks(eg) -> list:
    if not eg.activities:
        return [{"type": "np",
                 "text": "Evergreen-activity detector.  "
                         + (eg.reason or "No activities showed percent-complete creep "
                                        "without a commensurate schedule effect.") + "."}]
    blocks = [
        {"type": "np",
         "text": f"Evergreen-activity detector.  {len(eg.activities)} activity(ies) show "
                 "percent complete rising across at least two consecutive updates while "
                 "remaining duration did not meaningfully fall and/or the forecast "
                 "finish did not move earlier — statused-on-paper work that can poison "
                 "earned-value and progress narratives if relied upon uncorrected."},
    ]
    rows = [["Activity", "Name", "% Increase", "RD Change (h)", "Finish Moved Earlier?"]]
    for a in eg.activities:
        rows.append([a.code, a.name, _fmt(a.pct_increase_total, 0),
                     _fmt(a.remaining_duration_change_hours),
                     "Yes" if a.forecast_finish_moved_earlier else "No"])
    blocks.append({"type": "table", "font_sz": 15, "rows": rows})
    return blocks


def intake_blocks(series_analysis, intake_results=None) -> list:
    """Return the INTAKE REVIEW report section as LI block dicts.

    ``intake_results`` may be a prebuilt IntakeResults bundle from
    run_intake(); if None it is computed here — without an events or
    responsibility CSV, which are only available through the CLI/runner and
    are always surfaced in the intake Excel workbook regardless.  Degrades
    to explanatory paragraphs (never omits the section) when a given
    accelerator has nothing to report."""
    ir = intake_results or run_intake(series_analysis)
    blocks: list = [{"type": "h2", "text": "INTAKE REVIEW"}]
    blocks += _scorecard_blocks(ir.scorecard)
    blocks += _variance_blocks(ir.variance)
    blocks += _windows_blocks(ir.windows)
    blocks += _concurrency_blocks(ir.concurrency)
    blocks += _evergreen_blocks(ir.evergreen)
    return blocks
