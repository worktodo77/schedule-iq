"""Compose assessment/series results into the LI-house-style Word report.

House style (per LI conventions): ALL-CAPS Headings 1–2, Numbered Paragraph
body, two spaces between sentences, American spelling, serial comma, en
dashes for ranges, "Report" and "Project" capitalized, footnoted references,
teal LI tables.  Quality opinions are framed as schedule-quality observations;
causation, entitlement, and quantum are expressly reserved to the expert.
"""
from __future__ import annotations

import os
from datetime import datetime

from .. import __version__
from ..metrics.engine import ScheduleAssessment
from ..trend.series import SeriesAnalysis
from .charts import fig_float_histogram, series_figures
from .docx_li import build_docx

FOOTNOTES = {
    "dcma": {"text": "Defense Contract Management Agency, Earned Value Management "
                     "System Program Analysis Pamphlet (DCMA-EA PAM 200.1), "
                     "October 2012, §4 (14-Point Schedule Metrics).", "tag": ""},
    "gao": {"text": "U.S. Government Accountability Office, Schedule Assessment "
                    "Guide: Best Practices for Project Schedules, GAO-16-89G, "
                    "December 2015.", "tag": ""},
    "paseg": {"text": "National Defense Industrial Association, Integrated Program "
                      "Management Division, Planning & Scheduling Excellence Guide "
                      "(PASEG), v6.0, September 2025, §10 (Schedule Analysis).",
              "tag": ""},
    "nasa": {"text": "NASA Schedule Management Handbook, NASA/SP-2010-3403, "
                     "January 2010 (Schedule Assessment and Analysis).", "tag": ""},
    "aace29": {"text": "AACE International, Recommended Practice No. 29R-03, "
                       "Forensic Schedule Analysis, April 2011, §2 (Source "
                       "Validation).", "tag": ""},
    "scl": {"text": "Society of Construction Law, Delay and Disruption Protocol, "
                    "2nd edition, February 2017.", "tag": ""},
    "matrix": {"text": "ScheduleIQ Metric and Heuristic Matrix (docs/METRIC_MATRIX.md), "
                       "which records the source standard, formula, and default "
                       "threshold for every check.", "tag": ""},
}

_STATUS_ORDER = {"FAIL": 0, "WARNING": 1, "PASS": 2, "INFO": 3,
                 "N/A": 4, "NOT EVALUATED": 5}


def _dt(x) -> str:
    return x.strftime("%d %B %Y") if x else "—"


def _thr(res) -> str:
    c = res.check
    if res.threshold_applied is None:
        return "—"
    op = "≤" if c.direction == "max" else "≥"
    sfx = "%" if c.unit == "percent" else ""
    s = f"{op} {res.threshold_applied:g}{sfx}"
    if res.threshold_source != "standard default":
        s += " *"
    return s


def _intro_blocks(sa: SeriesAnalysis, run_dt: datetime) -> list[dict]:
    n = len(sa.schedules)
    first, last = sa.schedules[0], sa.schedules[-1]
    b = [
        {"type": "h1", "text": "SCHEDULE QUALITY AND TREND ASSESSMENT — "
                               + (first.project_id or first.project_name).upper()},
        {"type": "bodytext",
         "text": "DRAFT — FOR EXPERT REVIEW.  Prepared with ScheduleIQ v"
                 f"{__version__} on {run_dt:%d %B %Y}.  All schedule-quality "
                 "conclusions are preliminary observations on schedule mechanics "
                 "and data integrity; opinions on causation, entitlement, "
                 "concurrency, and quantum are reserved to the expert."},
        {"type": "h2", "text": "INTRODUCTION AND SCOPE"},
        {"type": "np",
         "text": f"This Report presents a schedule quality, health, and trend "
                 f"assessment of {n} schedule file{'s' if n > 1 else ''} for the "
                 f"{first.project_id or first.project_name} Project, covering data "
                 f"dates from {_dt(first.data_date)} through {_dt(last.data_date)}.  "
                 "The assessment applies the DCMA 14-Point Schedule Assessment,"
                 "[[C:dcma]] the GAO Schedule Assessment Guide best practices,"
                 "[[C:gao]] the NDIA PASEG schedule-health and execution metrics,"
                 "[[C:paseg]] and forensic intake checks drawn from AACE "
                 "Recommended Practice 29R-03[[C:aace29]] and the SCL Delay and "
                 "Disruption Protocol.[[C:scl]]"},
        {"type": "np",
         "text": "Each check, its formula, its default threshold, and the "
                 "standard from which it derives are recorded in the ScheduleIQ "
                 "Metric and Heuristic Matrix.[[C:matrix]]  Thresholds marked "
                 "with an asterisk were overridden by the analyst for this run; "
                 "all others are the published standard defaults.  Results "
                 "identified as FAIL or WARNING list the offending activities "
                 "in the accompanying Excel workbooks, which form part of this "
                 "assessment."},
        {"type": "h2", "text": "FILES REVIEWED"},
        {"type": "table", "font_sz": 16,
         "rows": [["File", "Format", "Data Date", "Activities",
                   "Relationships", "SHA-256 (first 12)"]] +
                 [[s.source_file, s.source_format, _dt(s.data_date),
                   str(len(s.real_activities)), str(len(s.relationships)),
                   s.source_sha256[:12]] for s in sa.schedules]},
    ]
    if sa.warnings:
        b.append({"type": "np",
                  "text": "Series intake notes:  "
                          + "  ".join(w.message for w in sa.warnings)})
    return b


def _summary_blocks(sa: SeriesAnalysis) -> list[dict]:
    rows = [["Update", "Health Score", "Checks Failed", "Warnings", "Passed"]]
    for s, a in zip(sa.schedules, sa.assessments):
        c = a.counts
        rows.append([s.label(), f"{a.health_score:.0f}", str(c.get("FAIL", 0)),
                     str(c.get("WARNING", 0)), str(c.get("PASS", 0))])
    latest = sa.assessments[-1]
    fails = [r for r in latest.results if r.status == "FAIL"]
    card_sentence = ""
    try:                                        # report card is the headline;
        from ..scorecard import score_series    # health score stays for
        card = score_series(sa)                 # backward comparability only
        latest_card = card.file_cards[-1]
        card_sentence = (f"The latest update ({sa.schedules[-1].label()}) "
                         f"earns an LI Schedule Report Card grade of "
                         f"{latest_card.letter} ({latest_card.overall:.0f}/100, "
                         f"spec {latest_card.spec_version}).  ")
    except Exception:
        pass
    b = [
        {"type": "h2", "text": "SUMMARY OF FINDINGS"},
        {"type": "np",
         "text": card_sentence +
                 f"The latest update also carries a legacy schedule health "
                 f"score of {latest.health_score:.0f} of 100 (retained for "
                 "continuity with earlier v0.1 runs), "
                 f"with {len(fails)} check{'s' if len(fails) != 1 else ''} at "
                 "FAIL severity.  Neither figure is, of itself, an opinion on "
                 "the adequacy of the schedule; see the LI Schedule Report "
                 "Card above for the category-by-category basis of the grade."},
        {"type": "table", "rows": rows},
    ]
    if fails:
        b.append({"type": "np",
                  "text": "The failed checks, in matrix order, are:  "
                          + "; ".join(f"{r.check.id} ({r.check.name}) — "
                                      f"{r.narrative.rstrip('.')}"
                                      for r in fails) + "."})
    return b


def _assessment_tables(a: ScheduleAssessment) -> list[dict]:
    by_cat = a.by_category()
    blocks: list[dict] = []
    dcma = by_cat.get("DCMA 14-Point Assessment", [])
    if dcma:
        blocks.append({"type": "h2", "text": "DCMA 14-POINT ASSESSMENT — LATEST UPDATE"})
        rows = [["#", "Check", "Value", "Threshold", "Status"]]
        for r in dcma:
            rows.append([r.check.id.replace("DCMA-", ""), r.check.name,
                         r.display_value, _thr(r), r.status])
        blocks.append({"type": "table", "rows": rows})
    others = [r for cat, rs in by_cat.items()
              if cat not in ("DCMA 14-Point Assessment", "Trend & Change (series)")
              for r in rs if r.status in ("FAIL", "WARNING")]
    others.sort(key=lambda r: (_STATUS_ORDER[r.status], r.check.id))
    if others:
        blocks.append({"type": "h2", "text": "ADDITIONAL QUALITY CHECKS — EXCEPTIONS"})
        blocks.append({"type": "np",
                       "text": "The following non-DCMA checks tripped at FAIL or "
                               "WARNING severity in the latest update.  Checks "
                               "that passed, informational metrics, and the full "
                               "population bases appear in the Excel results "
                               "workbook."})
        rows = [["ID", "Check", "Value", "Threshold", "Status", "Result"]]
        for r in others:
            rows.append([r.check.id, r.check.name, r.display_value, _thr(r),
                         r.status, r.narrative])
        blocks.append({"type": "table", "font_sz": 16, "rows": rows})
    return blocks


def _trend_blocks(sa: SeriesAnalysis, fig_dir: str) -> list[dict]:
    blocks: list[dict] = [{"type": "h2", "text": "TREND ANALYSIS"}]
    blocks.append({"type": "np",
                   "text": "The figures below trend the health score, the key "
                           "DCMA percentages, and the activity status mix across "
                           "the reviewed updates; the series metrics table "
                           "follows.  Sustained float erosion, critical-path "
                           "instability, or elevated logic churn ahead of claimed "
                           "delay events warrants targeted review before the "
                           "schedules are relied upon for delay analysis."})
    for i, (caption, png) in enumerate(series_figures(sa, fig_dir), 1):
        blocks.append({"type": "figure", "image": png})
        blocks.append({"type": "caption", "text": f"Figure {i}: {caption}"})
    rows = [["ID", "Series Metric", "Value", "Status", "Result"]]
    for r in sa.series_results:
        rows.append([r.check.id, r.check.name, r.display_value, r.status,
                     r.narrative])
    blocks.append({"type": "table", "font_sz": 16, "rows": rows})
    return blocks


def _change_blocks(sa: SeriesAnalysis) -> list[dict]:
    blocks: list[dict] = [{"type": "h2", "text": "CHANGE REGISTER SUMMARY"}]
    rows = [["Update Pair", "Added", "Deleted", "Logic Δ", "Durations",
             "Retroactive Actuals", "Constraints"]]
    for cs in sa.changesets:
        c = cs.summary_counts()
        rows.append([f"{cs.earlier.label()} → {cs.later.label()}",
                     str(c["activities added"]), str(c["activities deleted"]),
                     str(c["relationships added"] + c["relationships deleted"]
                         + c["relationships modified"]),
                     str(c["duration changes"]),
                     str(c["retroactive actual-date changes"]),
                     str(c["constraint changes"])])
    blocks.append({"type": "table", "rows": rows})
    retro = [(cs, ch) for cs in sa.changesets for ch in cs.actual_date_changes]
    if retro:
        blocks.append({"type": "np",
                       "text": f"{len(retro)} previously reported actual "
                               "date(s) changed in later updates.  Retroactive "
                               "changes to reported history bear directly on the "
                               "reliability of the as-built record and must each "
                               "be explained before these schedules are used for "
                               "delay analysis.[[C:aace29]]  The first instances "
                               "are tabulated below; the complete register is in "
                               "the trend workbook."})
        rows = [["Activity", "Field", "Reported", "Changed To", "Update Pair"]]
        for cs, ch in retro[:15]:
            rows.append([ch.code, ch.field, ch.before, ch.after,
                         f"{cs.earlier.label()} → {cs.later.label()}"])
        blocks.append({"type": "table", "font_sz": 16, "rows": rows})
    return blocks


def _basis_blocks() -> list[dict]:
    return [
        {"type": "h2", "text": "BASIS, LIMITATIONS, AND RESERVATIONS"},
        {"type": "np",
         "text": "Every figure in this Report is reproducible from the parsed "
                 "source files identified in the Files Reviewed table (hashes "
                 "recorded), using the versioned check implementations and the "
                 "thresholds stated.  The run parameters, input hashes, and "
                 "outputs are recorded in the audit log accompanying this "
                 "assessment."},
        {"type": "np",
         "text": "This assessment addresses schedule mechanics, data integrity, "
                 "and conformance with published scheduling practice.  It does "
                 "not opine on causation, entitlement, concurrency, or quantum, "
                 "which are reserved to the expert.  Where a check flags an "
                 "exception, the exception is a matter for explanation and "
                 "review, and is not, without more, evidence of impropriety."},
    ]


def _card_section(sa: SeriesAnalysis) -> list[dict]:
    """LI Schedule Report Card (RC3/RC4) — additive, never sinks a report."""
    try:
        from ..scorecard import score_series
        from .card_report import card_blocks
        return card_blocks(score_series(sa))
    except Exception:
        return []


def _impact_section(sa: SeriesAnalysis, fig_dir: str) -> list[dict]:
    """MILESTONE IMPACT DIAGNOSTIC (PRELIMINARY) — backlog A3, ADR-0007.

    Computes its own engine analytics (same pattern as ``_card_section`` /
    ``path_blocks``: never coupled to what the runner already wrote to
    ``out_dir``) against the last schedule in the series, and degrades to no
    section at all — never an error — on any failure, including a
    below-threshold validation handshake (ADR-0007's refusal gate)."""
    try:
        from ..analytics.impact import run_impact_analysis
        from ..cpm.handshake import HandshakeRefusal
        from .impact_figures import waterfall_figure

        target_sched = sa.schedules[-1]
        try:
            ia = run_impact_analysis(target_sched, handshake="require")
        except HandshakeRefusal:
            return []

        impact = ia.to_dict()
        impact["data_date"] = (target_sched.data_date.isoformat()
                               if target_sched.data_date else None)
        tgt = impact["target"]
        baseline = impact["baseline"]
        hs = impact["handshake"] or {}

        png = os.path.join(fig_dir, "fig_impact_waterfall.png")
        waterfall_figure(impact, png)

        deltas = [d for d in impact["waterfall"]
                 if d.get("computable") and d.get("delta_workdays") not in (None, 0)]
        deltas.sort(key=lambda d: abs(d["delta_workdays"]), reverse=True)
        top = deltas[:3]

        blocks: list[dict] = [
            {"type": "h2", "text": "MILESTONE IMPACT DIAGNOSTIC (PRELIMINARY)"},
            {"type": "np",
             "text": "The following engine-computed diagnostic deltas (ADR-0007) "
                     f"quantify what is moving the target milestone {tgt.get('code')}"
                     f"{' (' + tgt['name'] + ')' if tgt.get('name') else ''}.  "
                     "The tool-of-record finish of "
                     f"{_dt_str(baseline.get('record_early_finish'))} remains the "
                     "schedule; the ported engine's own reproduction of that date "
                     f"validated at a {hs.get('match_rate_pct', 0):.1f}% match rate "
                     f"against a {hs.get('threshold_pct', 99):.0f}% threshold "
                     "(SET-02).  Every number in this section is a labelled "
                     "diagnostic delta, never a competing schedule; causation and "
                     "entitlement are reserved to the expert."},
            {"type": "figure", "image": png},
            {"type": "caption",
             "text": f"Figure: Milestone {tgt.get('code')} diagnostic waterfall"},
        ]
        if top:
            stmts = "  ".join(
                f"{_scenario_prose(d['scenario'])} moves the target "
                f"{'earlier' if d['delta_workdays'] < 0 else 'later'} by "
                f"{abs(d['delta_workdays'])} workday"
                f"{'s' if abs(d['delta_workdays']) != 1 else ''}."
                for d in top)
            blocks.append({"type": "np", "text": "Largest diagnostic deltas.  " + stmts})
        notes = list(impact.get("disclosures") or []) + list(impact.get("deferred") or [])
        if notes:
            blocks.append({"type": "np",
                           "text": "Disclosures and deferred items:  "
                                   + "  ".join(notes)})
        return blocks
    except Exception:
        return []


def _dt_str(iso) -> str:
    if not iso:
        return "—"
    try:
        return datetime.fromisoformat(str(iso).split("T")[0]).strftime("%d %B %Y")
    except ValueError:
        return str(iso)


def _scenario_prose(scenario: str) -> str:
    return {
        "constraints_released_all": "Releasing all date constraints",
        "expected_finish_released": "Releasing expected-finish constraints",
        "leads_zeroed": "Zeroing leads (negative lags)",
        "oos_statusing_delta": "Retained logic vs. progress override (OOS)",
    }.get(scenario, scenario.replace("_", " ").capitalize())


def build_series_report(sa: SeriesAnalysis, out_docx: str,
                        paper: str = "letter") -> str:
    fig_dir = os.path.join(os.path.dirname(os.path.abspath(out_docx)), "figures")
    os.makedirs(fig_dir, exist_ok=True)
    run_dt = datetime.now()
    intro = _intro_blocks(sa, run_dt)
    blocks = intro[:2] + _card_section(sa) + intro[2:] + _summary_blocks(sa)
    try:                                        # intake review can never sink a run
        from .intake_report import intake_blocks
        blocks += intake_blocks(sa)
    except Exception:
        pass
    blocks += _assessment_tables(sa.assessments[-1])
    blocks += _impact_section(sa, fig_dir)          # A3: never sinks a run
    if sa.is_series:
        blocks += _trend_blocks(sa, fig_dir)
        try:                                    # path analysis can never sink a run
            from .paths_report import path_blocks
            blocks += path_blocks(sa)
        except Exception:
            pass
        blocks += _change_blocks(sa)
    blocks += _basis_blocks()
    return build_docx(blocks, out_docx, footnotes=FOOTNOTES, paper=paper)


def build_single_report(a: ScheduleAssessment, out_docx: str,
                        paper: str = "letter") -> str:
    fig_dir = os.path.join(os.path.dirname(os.path.abspath(out_docx)), "figures")
    os.makedirs(fig_dir, exist_ok=True)
    sa = SeriesAnalysis(schedules=[a.schedule], assessments=[a])
    run_dt = datetime.now()
    intro = _intro_blocks(sa, run_dt)
    blocks = intro[:2] + _card_section(sa) + intro[2:] + _summary_blocks(sa)
    try:                                        # intake review can never sink a run
        from .intake_report import intake_blocks
        blocks += intake_blocks(sa)
    except Exception:
        pass
    blocks += _assessment_tables(a)
    png = os.path.join(fig_dir, "fig_float.png")
    fig_float_histogram(a, png)
    blocks.append({"type": "figure", "image": png})
    blocks.append({"type": "caption",
                   "text": "Figure 1: Total float distribution"})
    blocks += _impact_section(sa, fig_dir)          # A3: never sinks a run
    blocks += _basis_blocks()
    return build_docx(blocks, out_docx, footnotes=FOOTNOTES, paper=paper)
