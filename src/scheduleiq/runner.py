"""End-to-end run orchestration shared by the CLI and the GUI."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from .audit import append_audit
from .ingest import load_many
from .metrics.engine import load_profile
from .report.excel import (write_assessment_workbook, write_benchmark_workbook,
                           write_trend_workbook)
from .report.pdf import PdfConversionUnavailable, docx_to_pdf
from .report.report_builder import build_series_report, build_single_report
from .trend.series import SeriesAnalysis, analyze_series


@dataclass
class RunResult:
    analysis: SeriesAnalysis
    outputs: list[str] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)


def run(paths: list[str], out_dir: str, profile: str | None = None,
        paper: str = "letter", make_pdf: bool = True,
        benchmark: bool = False, events_csv: str | None = None,
        responsibility_csv: str | None = None,
        progress=lambda msg: None) -> RunResult:
    """Ingest one or many files, assess, trend, and write all outputs."""
    os.makedirs(out_dir, exist_ok=True)
    overrides = load_profile(profile)

    progress(f"Parsing {len(paths)} file(s)…")
    schedules = load_many(paths)

    progress("Running checks…")
    sa = analyze_series(schedules, overrides)
    rr = RunResult(analysis=sa)

    for s, a in zip(sa.schedules, sa.assessments):
        base = os.path.splitext(os.path.basename(s.source_file))[0]
        xlsx = os.path.join(out_dir, f"{base}_results.xlsx")
        progress(f"Writing {os.path.basename(xlsx)}…")
        write_assessment_workbook(a, xlsx)
        rr.outputs.append(xlsx)

    if sa.is_series and not benchmark:
        xlsx = os.path.join(out_dir, "trend_analysis.xlsx")
        progress("Writing trend workbook…")
        write_trend_workbook(sa, xlsx)
        rr.outputs.append(xlsx)

    # LI Schedule Report Card (additive; never sinks a run — backlog RC1-RC4)
    try:
        from .scorecard import score_series, write_trace
        from .report.excel_card import write_card_workbook
        card = score_series(sa)
        xlsx = os.path.join(out_dir, "report_card.xlsx")
        progress("Writing report card workbook…")
        write_card_workbook(card, xlsx)
        rr.outputs.append(xlsx)
        write_trace(card, os.path.join(out_dir, "score_trace.json"))
        rr.outputs.append(os.path.join(out_dir, "score_trace.json"))
    except Exception as e:                       # pragma: no cover - defensive
        rr.messages.append(f"report card skipped: {e}")

    # path analytics workbook (additive; never sinks a run)
    try:
        from .analytics.paths import run_path_analytics
        from .report.excel_paths import write_paths_workbook
        pr = run_path_analytics(sa)
        xlsx = os.path.join(out_dir, "path_analysis.xlsx")
        progress("Writing path-analysis workbook…")
        write_paths_workbook(sa, pr, xlsx)
        rr.outputs.append(xlsx)
    except Exception as e:                       # pragma: no cover - defensive
        rr.messages.append(f"path analysis skipped: {e}")

    # intake-accelerator workbook (additive; never sinks a run — backlog D1-D8)
    try:
        from .intake import run_intake
        from .report.excel_intake import write_intake_workbook
        ir = run_intake(sa, events_csv=events_csv, responsibility_csv=responsibility_csv)
        xlsx = os.path.join(out_dir, "intake_review.xlsx")
        progress("Writing intake-review workbook…")
        write_intake_workbook(sa, ir, xlsx)
        rr.outputs.append(xlsx)
    except Exception as e:                       # pragma: no cover - defensive
        rr.messages.append(f"intake review skipped: {e}")

    # statistical screens + earned schedule workbook (additive; S1/S3)
    try:
        from .analytics.statistical import run_stats
        from .analytics.earned_schedule import earned_schedule
        from .report.excel_stats import write_stats_workbook
        stats_results = run_stats(sa)
        es_results = earned_schedule(sa)
        xlsx = os.path.join(out_dir, "statistical_analysis.xlsx")
        progress("Writing statistical-analysis workbook…")
        write_stats_workbook(sa, stats_results, es_results, xlsx)
        rr.outputs.append(xlsx)
    except Exception as e:                       # pragma: no cover - defensive
        rr.messages.append(f"statistical analysis skipped: {e}")

    if benchmark and len(sa.assessments) > 1:
        xlsx = os.path.join(out_dir, "benchmark.xlsx")
        progress("Writing benchmark workbook…")
        write_benchmark_workbook(sa.assessments, xlsx)
        rr.outputs.append(xlsx)

    progress("Building Word report…")
    docx = os.path.join(out_dir, "schedule_assessment.docx")
    if sa.is_series and not benchmark:
        build_series_report(sa, docx, paper=paper)
    else:
        build_single_report(sa.assessments[-1], docx, paper=paper)
    rr.outputs.append(docx)

    if make_pdf:
        progress("Converting to PDF…")
        try:
            rr.outputs.append(docx_to_pdf(docx))
        except PdfConversionUnavailable as e:
            rr.messages.append(str(e))

    fails = sum(a.counts.get("FAIL", 0) for a in sa.assessments)
    append_audit(os.path.join(out_dir, "audit"), "run",
                 params={"paths": paths, "profile": profile, "paper": paper,
                         "benchmark": benchmark, "events_csv": events_csv,
                         "responsibility_csv": responsibility_csv},
                 inputs=paths, outputs=rr.outputs,
                 summary={"schedules": len(sa.schedules),
                          "series": sa.is_series,
                          "health_scores": [a.health_score for a in sa.assessments],
                          "total_fails": fails,
                          "series_warnings": [w.message for w in sa.warnings]})

    # reproducibility capsule (additive; never sinks a run — backlog N5)
    try:
        from .capsule import build_capsule
        build_capsule(out_dir, {"paths": paths, "out_dir": out_dir,
                                "profile": profile, "paper": paper,
                                "make_pdf": make_pdf, "benchmark": benchmark})
    except Exception as e:                       # pragma: no cover - defensive
        rr.messages.append(f"reproducibility capsule skipped: {e}")

    progress("Done.")
    return rr
