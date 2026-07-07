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

# SRA block (M3): iteration count and seed are module-level constants (not
# CLI/config plumbing) so tests can monkeypatch a smaller iteration count for
# a fast end-to-end run.  The seed is fixed for reproducibility and disclosed
# in the SRA workbook summary (SimulationResult.seed).
_SRA_ITERATIONS = 500
_SRA_SEED = 42
_SRA_MAX_INCOMPLETE = 2000


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

    # engine milestone-impact diagnostic + as-built reconstruction (additive;
    # never sinks a run — ADR-0007 / backlog A2-A4, P5-P6).  Runs against the
    # LAST schedule in the series (the current update), matching how path
    # analytics selects its file (analytics.paths.run_path_analytics uses
    # scheds[-1]).  The handshake gate means this degrades gracefully on any
    # file whose engine-vs-record match rate is below threshold; that refusal
    # is reported distinctly from an unexpected error.
    try:
        from .analytics.impact import run_impact_analysis
        from .analytics.asbuilt import reconstruct_asbuilt_paths
        from .cpm.handshake import HandshakeRefusal, run_handshake
        from .report.excel_impact import write_impact_workbook
        from .report.impact_figures import asbuilt_figure, waterfall_figure

        target_sched = sa.schedules[-1]
        try:
            ia = run_impact_analysis(target_sched, handshake="require")
        except HandshakeRefusal:
            hs = run_handshake(target_sched, threshold_pct=99.0)
            rr.messages.append(
                "SET-02 handshake below threshold — engine impact analytics "
                f"refused ({hs.match_rate_pct:.1f}%)")
        else:
            ab = reconstruct_asbuilt_paths(target_sched)
            impact_dict = ia.to_dict()
            impact_dict["data_date"] = (target_sched.data_date.isoformat()
                                        if target_sched.data_date else None)
            asbuilt_dict = ab.to_dict()

            progress("Writing milestone impact diagnostic workbook…")
            xlsx = os.path.join(out_dir, "impact_diagnostic.xlsx")
            write_impact_workbook(impact_dict, asbuilt_dict, xlsx)
            rr.outputs.append(xlsx)

            progress("Writing milestone impact diagnostic figures…")
            wf_png = os.path.join(out_dir, "fig_impact_waterfall.png")
            waterfall_figure(impact_dict, wf_png)
            rr.outputs.append(wf_png)
            ab_png = os.path.join(out_dir, "fig_asbuilt_paths.png")
            asbuilt_figure(asbuilt_dict, ab_png)
            rr.outputs.append(ab_png)
    except Exception as e:                       # pragma: no cover - defensive
        rr.messages.append(f"engine impact analytics skipped: {e}")

    # intake-accelerator workbook (additive; never sinks a run — backlog D1-D8)
    forensic_responsibility = None
    try:
        from .intake import run_intake
        from .report.excel_intake import write_intake_workbook
        ir = run_intake(sa, events_csv=events_csv, responsibility_csv=responsibility_csv)
        xlsx = os.path.join(out_dir, "intake_review.xlsx")
        progress("Writing intake-review workbook…")
        write_intake_workbook(sa, ir, xlsx)
        rr.outputs.append(xlsx)
        forensic_responsibility = ir.responsibility
    except Exception as e:                       # pragma: no cover - defensive
        rr.messages.append(f"intake review skipped: {e}")

    # forensic delay diagnostics: half-step (D9), daily ledger (N3), and the
    # methodology-robustness certificate (N4) — additive; never sinks a run.
    # Runs over the full series when there are >= 2 schedules; silently no-ops
    # (no message) on a single-file run, matching how the trend workbook is
    # gated.  Reuses the D7 responsibility overlay captured above when the
    # intake block produced one, else the sweep runs on totals only.
    if len(sa.schedules) >= 2:
        try:
            from .analytics.halfstep import run_halfstep_series
            from .analytics.dailyledger import run_daily_ledger
            from .analytics.robustness import run_robustness_certificate
            from .cpm.handshake import HandshakeRefusal, run_handshake
            from .report.excel_forensic import write_forensic_workbook
            from .report.forensic_figures import (dailyledger_figure,
                                                   halfstep_figure,
                                                   robustness_figure)

            schedules = sa.schedules
            hs_results = run_halfstep_series(schedules, handshake="require")
            hs_dicts = [r.to_dict() for r in hs_results]
            computable_hs = [d for d in hs_dicts if not d.get("refused")]

            ledger_dicts: list = []
            for earlier, later in zip(schedules, schedules[1:]):
                d0 = earlier.data_date.date() if earlier.data_date else None
                dn = later.data_date.date() if later.data_date else None
                if d0 is None or dn is None or (dn - d0).days > 120:
                    rr.messages.append(
                        "daily ledger skipped for "
                        f"{earlier.label()} -> {later.label()}: window exceeds "
                        "120 calendar days or a data date is missing")
                    continue
                try:
                    dl = run_daily_ledger(earlier, later, handshake="require",
                                          responsibility=forensic_responsibility)
                    ledger_dicts.append(dl.to_dict())
                except HandshakeRefusal as exc:
                    rr.messages.append(
                        "SET-02 handshake below threshold — daily ledger "
                        f"refused for {earlier.label()} -> {later.label()}: {exc}")

            cert_dict = None
            try:
                cert = run_robustness_certificate(
                    schedules, handshake="require",
                    responsibility=forensic_responsibility)
                cert_dict = cert.to_dict()
            except HandshakeRefusal as exc:
                rr.messages.append(
                    "SET-02 handshake below threshold — robustness certificate "
                    f"refused: {exc}")

            if computable_hs or ledger_dicts or cert_dict is not None:
                xlsx = os.path.join(out_dir, "forensic_diagnostics.xlsx")
                progress("Writing forensic delay diagnostics workbook…")
                write_forensic_workbook(hs_dicts, ledger_dicts, cert_dict, xlsx)
                rr.outputs.append(xlsx)

                progress("Writing forensic delay diagnostics figures…")
                if computable_hs:
                    hs_png = os.path.join(out_dir, "fig_halfstep.png")
                    halfstep_figure(computable_hs[-1], hs_png)
                    rr.outputs.append(hs_png)
                if ledger_dicts:
                    dl_png = os.path.join(out_dir, "fig_daily_ledger.png")
                    dailyledger_figure(ledger_dicts[-1], dl_png)
                    rr.outputs.append(dl_png)
                if cert_dict is not None:
                    rb_png = os.path.join(out_dir, "fig_robustness.png")
                    robustness_figure(cert_dict, rb_png)
                    rr.outputs.append(rb_png)
            else:
                hs = run_handshake(schedules[-1], threshold_pct=99.0)
                rr.messages.append(
                    "SET-02 handshake below threshold — forensic delay "
                    f"diagnostics refused ({hs.match_rate_pct:.1f}%)")
        except Exception as e:                   # pragma: no cover - defensive
            rr.messages.append(f"forensic delay diagnostics skipped: {e}")

    # schedule risk analysis / Monte Carlo (M3) — additive; never sinks a run.
    # Runs on the LAST schedule in the series (the current update), matching
    # how the milestone-impact block selects its file.  A default ±10%
    # triangular template spec at a fixed seed keeps the run reproducible;
    # _SRA_ITERATIONS is a module-level constant so tests can monkeypatch a
    # smaller iteration count without adding config plumbing.
    try:
        from .analytics.montecarlo import (TemplateRule, UncertaintySpec,
                                           run_simulation)
        from .cpm.handshake import HandshakeRefusal
        from .report.excel_sra import write_sra_workbook
        from .report.sra_figures import scurve_figure, tornado_figure

        sra_sched = sa.schedules[-1]
        n_incomplete = sum(1 for a in sra_sched.real_activities if not a.completed)
        if n_incomplete > _SRA_MAX_INCOMPLETE:
            rr.messages.append(
                f"schedule risk analysis skipped: {n_incomplete} incomplete "
                f"activities exceeds the {_SRA_MAX_INCOMPLETE}-activity "
                "runtime cap")
        else:
            spec = UncertaintySpec(
                templates=[TemplateRule(match="", low_pct=-10.0, high_pct=10.0)])
            try:
                sim = run_simulation(sra_sched, spec=spec,
                                     iterations=_SRA_ITERATIONS, seed=_SRA_SEED,
                                     handshake="require")
            except HandshakeRefusal as exc:
                rr.messages.append(
                    "SET-02 handshake below threshold — schedule risk "
                    f"analysis refused: {exc}")
            else:
                sim_dict = sim.to_dict()
                xlsx = os.path.join(out_dir, "sra_diagnostics.xlsx")
                progress("Writing schedule risk analysis workbook…")
                write_sra_workbook(sim_dict, xlsx)
                rr.outputs.append(xlsx)

                progress("Writing schedule risk analysis figures…")
                sc_png = os.path.join(out_dir, "fig_sra_scurve.png")
                scurve_figure(sim_dict, sc_png)
                rr.outputs.append(sc_png)
                td_png = os.path.join(out_dir, "fig_sra_tornado.png")
                tornado_figure(sim_dict, td_png)
                rr.outputs.append(td_png)
    except Exception as e:                       # pragma: no cover - defensive
        rr.messages.append(f"schedule risk analysis skipped: {e}")

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
