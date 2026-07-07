"""End-to-end run orchestration shared by the CLI and the GUI."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import yaml

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


def load_run_config(path: str | None) -> dict[str, Any]:
    """Parse the RESERVED top-level ``config:`` mapping from a profile YAML
    file (v0.4 additive extension of the PROFILE FILE format).

    ``metrics.engine.load_profile`` (never modified — see CLAUDE.md/task
    boundary) owns the flat ``ID: threshold`` override path and does not
    special-case ``config:``: its line-based parser skips the ``config:``
    line itself (no numeric value) and any nested key whose value is not a
    bare number (dates, paths, booleans, lists); a nested NUMERIC leaf (e.g.
    ``ld_rate_per_day: 5000``) is harmlessly added to its overrides dict
    under a key that never matches a real check ID.  So a profile carrying
    BOTH flat overrides and a ``config:`` block keeps working exactly as
    before for the threshold path — this function reads the SAME file a
    second time and returns ONLY the ``config:`` sub-mapping (``{}`` when
    absent, malformed, or the profile is a flat ``.json`` threshold map,
    which never carries a reserved ``config:`` key).

    Recognized keys (all optional): ``damages`` (a dict consumed by
    ``analytics.damages.load_damages_config``), ``weather`` (``station_csv``,
    ``sensitive_tags``), ``corpus`` (``path``, ``sector``, ``record``),
    ``tia_events`` (a CSV path), ``cockpit`` (bool, default True),
    ``internal_workbook`` (bool, default False — the privileged surface is
    opt-in).
    """
    if not path or path.endswith(".json"):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    cfg = data.get("config")
    return cfg if isinstance(cfg, dict) else {}


def run(paths: list[str], out_dir: str, profile: str | None = None,
        paper: str = "letter", make_pdf: bool = True,
        benchmark: bool = False, events_csv: str | None = None,
        responsibility_csv: str | None = None,
        no_cockpit: bool = False, internal_workbook: bool = False,
        progress=lambda msg: None) -> RunResult:
    """Ingest one or many files, assess, trend, and write all outputs.

    ``no_cockpit`` / ``internal_workbook`` are CLI-level overrides of the
    profile's ``config: {cockpit, internal_workbook}`` (v0.4 run-config
    extension, see :func:`load_run_config`): ``no_cockpit=True`` always
    disables the cockpit regardless of config; ``internal_workbook=True``
    always enables the privileged workbook regardless of config.  Both
    default to leaving the config (or its own defaults — cockpit ON,
    internal workbook OFF) in charge.
    """
    os.makedirs(out_dir, exist_ok=True)
    overrides = load_profile(profile)
    config = load_run_config(profile)

    progress(f"Parsing {len(paths)} file(s)…")
    schedules = load_many(paths)

    progress("Running checks…")
    sa = analyze_series(schedules, overrides)
    rr = RunResult(analysis=sa)

    # damages/exposure overlay config (S7; backlog ANALYTICS_PROPOSAL §6.6) —
    # built once and threaded into the EXISTING impact/forensic/SRA workbook
    # and figure calls below (their damages= params already exist; None is
    # byte-identical to pre-v0.4 output).
    damages_cfg = None
    try:
        from .analytics.damages import load_damages_config
        damages_cfg = load_damages_config(config.get("damages"))
        if damages_cfg is not None:
            rr.messages.append(
                "damages/exposure overlay active (S7): currency "
                f"{damages_cfg.currency}, daily basis {damages_cfg.daily_basis}, "
                "LD math " + ("enabled" if damages_cfg.ld_enabled else
                              "disabled (ld_rate_per_day and contractual_completion "
                              "not both configured)") + ".  " +
                "EXPOSURE ARITHMETIC ONLY — quantum, causation, and entitlement "
                "are reserved to the expert.")
    except Exception as e:                       # pragma: no cover - defensive
        rr.messages.append(f"damages config skipped: {e}")
        damages_cfg = None

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
            write_impact_workbook(impact_dict, asbuilt_dict, xlsx, damages=damages_cfg)
            rr.outputs.append(xlsx)

            progress("Writing milestone impact diagnostic figures…")
            wf_png = os.path.join(out_dir, "fig_impact_waterfall.png")
            waterfall_figure(impact_dict, wf_png, damages=damages_cfg)
            rr.outputs.append(wf_png)
            ab_png = os.path.join(out_dir, "fig_asbuilt_paths.png")
            asbuilt_figure(asbuilt_dict, ab_png, damages=damages_cfg)
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
    # ``forensic_cert_dict`` is hoisted out of the block below so the v0.4
    # internal-privileged workbook (LI-13 ARR / LI-15 RSA) can reuse the same
    # N4 certificate without a second engine sweep, when one was computed.
    forensic_cert_dict = None
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
                forensic_cert_dict = cert_dict
            except HandshakeRefusal as exc:
                rr.messages.append(
                    "SET-02 handshake below threshold — robustness certificate "
                    f"refused: {exc}")

            if computable_hs or ledger_dicts or cert_dict is not None:
                xlsx = os.path.join(out_dir, "forensic_diagnostics.xlsx")
                progress("Writing forensic delay diagnostics workbook…")
                write_forensic_workbook(hs_dicts, ledger_dicts, cert_dict, xlsx,
                                       damages=damages_cfg)
                rr.outputs.append(xlsx)

                progress("Writing forensic delay diagnostics figures…")
                if computable_hs:
                    hs_png = os.path.join(out_dir, "fig_halfstep.png")
                    halfstep_figure(computable_hs[-1], hs_png, damages=damages_cfg)
                    rr.outputs.append(hs_png)
                if ledger_dicts:
                    dl_png = os.path.join(out_dir, "fig_daily_ledger.png")
                    dailyledger_figure(ledger_dicts[-1], dl_png, damages=damages_cfg)
                    rr.outputs.append(dl_png)
                if cert_dict is not None:
                    rb_png = os.path.join(out_dir, "fig_robustness.png")
                    robustness_figure(cert_dict, rb_png, damages=damages_cfg)
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
                write_sra_workbook(sim_dict, xlsx, damages=damages_cfg)
                rr.outputs.append(xlsx)

                progress("Writing schedule risk analysis figures…")
                sc_png = os.path.join(out_dir, "fig_sra_scurve.png")
                scurve_figure(sim_dict, sc_png, damages=damages_cfg)
                rr.outputs.append(sc_png)
                td_png = os.path.join(out_dir, "fig_sra_tornado.png")
                tornado_figure(sim_dict, td_png, damages=damages_cfg)
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

    # ======================================================================
    # v0.4 wiring wave — TIA workbench, weather overlay, work-pattern/edit-
    # session forensics, Ribbon/Phase/Compliance analyzers, cockpit, corpus
    # context, and the privileged internal workbook.  Every block below is
    # additive, gated per profiles/example_profile.yaml's documented
    # ``config:`` schema (see runner.load_run_config), and never sinks a run.
    # ======================================================================
    v04_analyses_run: list[str] = []

    # -- TIA workbench (§6.5) — config.tia_events, needs >= 2 schedules ------
    tia_dict = None
    tia_events_cfg = config.get("tia_events")
    if tia_events_cfg:
        if len(sa.schedules) >= 2:
            try:
                from .analytics.tia import run_tia
                from .cpm.handshake import HandshakeRefusal

                tr = run_tia(sa.schedules, tia_events_cfg, handshake="require")
                tia_dict = tr.to_dict()
                v04_analyses_run.append(
                    f"TIA workbench (§6.5): {len(tr.updates)} update impact "
                    f"table(s), {len(tr.collapse)} party collapse variant(s)")
                rr.messages.append(
                    f"TIA workbench computed: {len(tr.updates)} update impact "
                    f"table(s), {len(tr.collapse)} party collapse variant(s).")
            except HandshakeRefusal as exc:
                rr.messages.append(
                    "SET-02 handshake below threshold — TIA workbench "
                    f"refused: {exc}")
            except Exception as e:                   # pragma: no cover - defensive
                rr.messages.append(f"TIA workbench skipped: {e}")
        else:
            rr.messages.append(
                "TIA workbench skipped: config.tia_events needs >= 2 schedules "
                "(single-file series).")

    # -- weather & external-conditions overlay (§8.1) — config.weather -------
    weather_dict = None
    weather_cfg = config.get("weather") or {}
    if weather_cfg.get("station_csv"):
        try:
            from .analytics.weather import analyze_weather, load_ghcn_csv

            rec = load_ghcn_csv(weather_cfg["station_csv"])
            wa = analyze_weather(sa.schedules, rec,
                                 sensitive_tags=weather_cfg.get("sensitive_tags"))
            weather_dict = wa.to_dict()
            v04_analyses_run.append(
                f"weather overlay (§8.1): station {rec.station}, "
                f"{len(wa.windows)} window(s)")
            rr.messages.append(
                f"weather overlay computed: station {rec.station}, "
                f"{len(wa.windows)} window(s).")
        except Exception as e:                       # pragma: no cover - defensive
            rr.messages.append(f"weather overlay skipped: {e}")

    # -- work-pattern reconstruction (§8.2) + edit-session forensics (§6.1) --
    # always when >= 2 schedules (cheap, record-only); silently no-ops on a
    # single-file run, matching the forensic-diagnostics block's convention.
    workpattern_dict = None
    editsession_dict = None
    if len(sa.schedules) >= 2:
        try:
            from .analytics.workpatterns import reconstruct_work_patterns
            wp = reconstruct_work_patterns(sa.schedules)
            workpattern_dict = wp.to_dict()
            v04_analyses_run.append("as-built work-pattern reconstruction (§8.2)")
        except Exception as e:                       # pragma: no cover - defensive
            rr.messages.append(f"work-pattern reconstruction skipped: {e}")
        try:
            from .analytics.editsessions import mine_edit_sessions
            es = mine_edit_sessions(sa.schedules)
            editsession_dict = es.to_dict()
            v04_analyses_run.append("editing-session forensics (§6.1)")
        except Exception as e:                       # pragma: no cover - defensive
            rr.messages.append(f"editing-session forensics skipped: {e}")

    # -- Ribbon (Fuse F1) + Phase (Fuse F2) — always, on the latest file ------
    ribbon_dict = None
    phase_dict = None
    try:
        from .analytics.ribbon import ribbon_analysis
        ribbon_dict = ribbon_analysis(sa.schedules[-1], sa.assessments[-1]).to_dict()
        v04_analyses_run.append("Ribbon analyzer (Fuse F1)")
    except Exception as e:                           # pragma: no cover - defensive
        rr.messages.append(f"ribbon analyzer skipped: {e}")
    try:
        from .analytics.phase import phase_analysis
        phase_dict = phase_analysis(sa.schedules[-1], sa.assessments[-1]).to_dict()
        v04_analyses_run.append("Phase analyzer (Fuse F2)")
    except Exception as e:                           # pragma: no cover - defensive
        rr.messages.append(f"phase analyzer skipped: {e}")

    # -- Compliance (Fuse F4) — needs >= 2 schedules --------------------------
    compliance_dict = None
    if len(sa.schedules) >= 2:
        try:
            from .analytics.compliance import period_compliance
            compliance_dict = period_compliance(sa.schedules).to_dict()
            v04_analyses_run.append("per-period compliance analyzer (Fuse F4)")
        except Exception as e:                       # pragma: no cover - defensive
            rr.messages.append(f"period compliance skipped: {e}")

    # -- benchmark corpus context (§6.9) — config.corpus.path -----------------
    # context_for()'s lines are written into the v0.4 workbook's Summary
    # sheet; corpus.add_project() is called ONLY on the analyst's explicit
    # opt-in (config.corpus.record: true) — never a silent client-data write
    # (CLAUDE.md §9).  Disclosed in a message EITHER way.
    corpus_lines: list[str] = []
    corpus_cfg = config.get("corpus") or {}
    if corpus_cfg.get("path"):
        try:
            from .analytics.corpus import BenchmarkCorpus
            corpus = BenchmarkCorpus(corpus_cfg["path"])
            ctx = corpus.context_for(sa, sector=corpus_cfg.get("sector"))
            for mid in sorted(ctx.metrics):
                line = ctx.line(mid)
                if line:
                    corpus_lines.append(line)
            if ctx.refused:
                rr.messages.append("corpus context: " + "; ".join(ctx.disclosures))
            else:
                rr.messages.append(
                    f"corpus context placed against {ctx.n} peer project(s)"
                    + (f" in sector {ctx.sector!r}" if ctx.sector else "") + ".")
            if corpus_cfg.get("record"):
                row = corpus.add_project(sa, sector=corpus_cfg.get("sector", ""))
                rr.messages.append(
                    "corpus WRITE: this project's anonymized outcomes were "
                    f"recorded to {corpus_cfg['path']} (corpus_id "
                    f"{row.corpus_id}; opt-in config.corpus.record: true).")
            else:
                rr.messages.append(
                    "corpus: this run was placed against the corpus for "
                    "context but NOT recorded — config.corpus.record is not "
                    "true (opt-in write only; client data is never silently "
                    "persisted, CLAUDE.md §9).")
        except Exception as e:                       # pragma: no cover - defensive
            rr.messages.append(f"corpus context skipped: {e}")

    # -- write the v0.4 analytics-supplement workbook -------------------------
    # Always attempted: Ribbon/Phase always run, so Summary + at least those
    # two sheets are the default-on artifact even on a legacy/bare run.
    try:
        from .report.excel_v04 import write_v04_workbook
        v04_parts = {
            "tia": tia_dict, "weather": weather_dict,
            "workpatterns": workpattern_dict, "editsessions": editsession_dict,
            "ribbon": ribbon_dict, "phase": phase_dict,
            "compliance": compliance_dict,
            "analyses_run": v04_analyses_run, "corpus_lines": corpus_lines,
        }
        xlsx = os.path.join(out_dir, "v04_analytics_supplement.xlsx")
        progress("Writing v0.4 analytics-supplement workbook…")
        write_v04_workbook(v04_parts, xlsx, damages=damages_cfg)
        rr.outputs.append(xlsx)
    except Exception as e:                           # pragma: no cover - defensive
        rr.messages.append(f"v0.4 analytics-supplement workbook skipped: {e}")

    # -- interactive network cockpit (backlog S8) — config.cockpit, default ON
    cockpit_enabled = config.get("cockpit", True) and not no_cockpit
    if cockpit_enabled:
        try:
            from .report.cockpit import write_cockpit
            html = os.path.join(out_dir, "cockpit.html")
            progress("Writing network cockpit…")
            write_cockpit(sa, html)
            rr.outputs.append(html)
        except Exception as e:                       # pragma: no cover - defensive
            rr.messages.append(f"network cockpit skipped: {e}")

    # -- internal PRIVILEGED workbook (LI-11..LI-15 provocative indices) -----
    # config.internal_workbook (default False — opt-in only) or the CLI
    # --internal-workbook override.  Reuses the forensic block's already-
    # computed N4 certificate when one is available; otherwise computes one
    # fresh (still gated behind >= 2 schedules and the ADR-0007 handshake).
    if config.get("internal_workbook", False) or internal_workbook:
        try:
            from .metrics.engine import load_matrix
            from .analytics.li_wiring import li_provocative_results
            from .report.excel_v04 import write_internal_workbook

            priv_cert_dict = forensic_cert_dict
            if priv_cert_dict is None and len(sa.schedules) >= 2:
                try:
                    from .analytics.robustness import run_robustness_certificate
                    from .cpm.handshake import HandshakeRefusal
                    priv_cert_dict = run_robustness_certificate(
                        sa.schedules, handshake="require",
                        responsibility=forensic_responsibility).to_dict()
                except HandshakeRefusal:
                    priv_cert_dict = None

            matrix = load_matrix()
            prov_results = li_provocative_results(sa, matrix,
                                                  certificate=priv_cert_dict)
            xlsx = os.path.join(out_dir, "INTERNAL_PRIVILEGED_workbook.xlsx")
            progress("Writing INTERNAL PRIVILEGED workbook…")
            write_internal_workbook(prov_results, priv_cert_dict, xlsx)
            rr.outputs.append(xlsx)
            rr.messages.append(
                "INTERNAL_PRIVILEGED_workbook.xlsx written: LI-11..LI-15 "
                "provocative indices (SMI/DDI/ARR/PPS/RSA) — PRIVILEGED / "
                "INTERNAL surface only (ANALYTICS_PROPOSAL §11).  This "
                "workbook is NOT part of the standard report or artifact set "
                "handed to a counterparty; do not disclose outside "
                "privileged review.")
        except Exception as e:                       # pragma: no cover - defensive
            rr.messages.append(f"internal privileged workbook skipped: {e}")

    if benchmark and len(sa.assessments) > 1:
        xlsx = os.path.join(out_dir, "benchmark.xlsx")
        progress("Writing benchmark workbook…")
        write_benchmark_workbook(sa.assessments, xlsx)
        rr.outputs.append(xlsx)

    progress("Building Word report…")
    docx = os.path.join(out_dir, "schedule_assessment.docx")
    if sa.is_series and not benchmark:
        build_series_report(sa, docx, paper=paper, weather=weather_dict)
    else:
        build_single_report(sa.assessments[-1], docx, paper=paper, weather=weather_dict)
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
