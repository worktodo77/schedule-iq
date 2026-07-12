"""Wire the LI proprietary indices (N6-N15) into the series pipeline.

Converts the li_indices / li_record results into MetricResult objects keyed
to the LI-01..LI-10 matrix rows, so the indices flow through the existing
trend workbook, report series table, and (later) the Report Card with zero
special-casing.  All informational (the Report Card spec, not the matrix,
defines their scoring normalization).

Wiring discipline (Wave-0 defect batch, docs/audit/
LI-02-10_audit_matrix_2026-07-12.md FR1/W1/W2):

* **Direct attribute access, never ``getattr`` with a numeric default.**  The
  getattr-with-default pattern silently masked renamed fields — LI-03 read
  ``b.bias``/``b.p10``/``b.p90`` for fields named ``bias_days``/``p10_days``/
  ``p90_days``, pinning the scored band width at a fabricated 0 (FR1); LI-05,
  LI-07 and LI-10 exhibits printed fabricated zeros the same way (W2).  A
  renamed field must fail loudly (and is then contained per-index, below).
* **Optional values render as an em dash** (:func:`_fmt`), never feed a
  ``:.2f`` format (W1: a None PCI window / BWI density row raised TypeError
  here and the pipeline's blanket guard then silently dropped ALL TEN
  indices from ``series_results``).
* **Per-index isolation:** every index block runs under its own guard, so a
  failure degrades that one index to a reasoned placeholder row and the
  other nine still report.  The metric layers are never-raises by contract;
  this is wiring-layer defence in depth (rubric C3), not a behavior change
  on any canonical series.
"""
from __future__ import annotations

from ..metrics.engine import CheckDef, Finding, MetricResult

_DASH = "—"


def _res(matrix_by_id, cid, value, narrative, findings):
    cd = matrix_by_id.get(cid)
    if cd is None:                                    # matrix row missing: skip
        return None
    r = MetricResult(check=cd, value=value, status="INFO",
                     narrative=narrative, findings=findings[:25])
    r.threshold_applied = None
    return r


def _fmt(v, spec="{:.2f}"):
    """Format an Optional number; ``None`` renders as an em dash instead of
    raising inside an f-string — one unavailable cell must degrade one
    exhibit cell, never the whole LI wiring (W1)."""
    return spec.format(v) if v is not None else _DASH


def li_series_results(sa, matrix: list[CheckDef]) -> list[MetricResult]:
    from .li_indices import run_li_indices
    from .li_record import run_li_record

    by_id = {c.id: c for c in matrix}
    out: list[MetricResult] = []

    # Both bundles are never-raises by contract; these guards are wiring-layer
    # defence so a surprise in one bundle degrades its indices with a reason
    # instead of blanking all ten (W1).
    ri_err = rr_err = None
    try:
        ri = run_li_indices(sa)
    except Exception as e:                            # pragma: no cover - defensive
        ri, ri_err = None, e
    try:
        rr = run_li_record(sa)
    except Exception as e:                            # pragma: no cover - defensive
        rr, rr_err = None, e

    def _emit(cid, build, bundle_err):
        try:
            if bundle_err is not None:
                raise bundle_err
            r = build()
        except Exception as e:
            r = _res(by_id, cid, None,
                     f"{cid} wiring degraded ({type(e).__name__}: {e}); the "
                     "other LI indices are unaffected.", [])
        if r is not None:
            out.append(r)

    # LI-01 FCBI (v0.5 governed: value = cumulative operational gross burn B) --
    def _li01():
        f = ri.fcbi
        interp = f.interpretation or f.reason
        finds = [Finding(b.code, b.name,
                         f"burn {b.consumption_days:.1f}d  "
                         f"d={b.distance_days:.1f}  "
                         f"w={b.weight:.2f}  "
                         f"c*w={b.contribution:.2f}")
                 for b in f.top_burners]
        # current-segment cumulative OPERATIONAL burn B (basis-change windows are
        # segmented out and restart the series — do NOT revive a prior segment, O7.9)
        cum = f.cumulative_burn[-1] if f.cumulative_burn else 0.0
        cum = 0.0 if cum is None else cum      # latest window is a basis-change restart
        last = f.windows[-1] if f.windows else None
        if last is not None and not last.basis_change:
            c_txt = (f"{last.burn_proximity:.2f}" if last.burn_proximity is not None
                     else "N/A")
            cov_txt = (f"{last.coverage:.0%}" if last.coverage is not None else "N/A")
            pe = last.population_eligibility
            te = last.tf_evaluability
            pop_txt = ((f"; population eligibility {pe:.0%}" if pe is not None else "")
                       + (f", TF-evaluability {te:.0%}" if te is not None else ""))
            interp += (f"  Latest operational window: B={last.burn_gross:.1f} gross "
                       f"activity-days, C={c_txt} burn-weighted proximity, eligible-burn "
                       f"coverage {cov_txt}"
                       + (f", N={last.n_severity:.1f}d negative-float severity"
                          if last.n_severity else "")
                       + (f"; {last.quarantine_burn:.1f}d quarantined"
                          if last.quarantine_burn else "")
                       + pop_txt + ".")
        elif last is not None and last.basis_change:
            rq = (f"{last.requirement_margin_change:+.1f}d requirement-induced margin change"
                  if last.requirement_margin_change is not None else "requirement-induced")
            interp += (f"  Latest window is a BASIS-CHANGE window ("
                       f"{'; '.join(last.basis_change_reasons)}) — excluded from the "
                       f"operational burn trend; {rq} reported separately, not execution "
                       "erosion.")
        if f.target_auto_resolved:
            interp += "  [target auto-resolved; analyst should confirm m — O7.1]"
        interp += "  " + f.scope_note
        return _res(by_id, "LI-01", cum, interp, finds)

    _emit("LI-01", _li01, ri_err)

    # LI-02 LHL -----------------------------------------------------------
    def _li02():
        lhl = rr.lhl
        v = None
        narrative = lhl.reason or ""
        if lhl.overall:
            v = lhl.overall.median_months
            flag = "" if lhl.overall.median_reached else \
                "  (median not reached — conservative lower bound; " \
                f"{lhl.overall.censored}/{lhl.overall.n} relationships censored)"
            narrative = (f"Logic half-life {v if v is not None else _DASH} months{flag}."
                         + (f"  On/off-path ratio {lhl.on_off_ratio:.2f}."
                            if lhl.on_off_ratio is not None else ""))
        return _res(by_id, "LI-02", v, narrative, [])

    _emit("LI-02", _li02, rr_err)

    # LI-03 FRB -----------------------------------------------------------
    def _li03():
        frb = rr.frb
        finds, band_width = [], None
        best = None
        for b in frb.buckets:
            if b.n > 0:
                # FR1: read the REAL fields (bias_days/p10_days/p90_days) — the
                # old getattr(b, "bias", 0)/"p10"/"p90" reads silently returned
                # their defaults and pinned the scored band width at 0.
                finds.append(Finding(b.label, "",
                                     f"n={b.n}, bias {_fmt(b.bias_days, '{:+.1f}')}d, "
                                     f"band P10 {_fmt(b.p10_days, '{:+.1f}')}d .. "
                                     f"P90 {_fmt(b.p90_days, '{:+.1f}')}d"))
                if best is None or b.n > best.n:
                    best = b
        if best is not None and best.p90_days is not None and best.p10_days is not None:
            band_width = best.p90_days - best.p10_days
        narrative = (f"Empirical forecast error band (largest bucket): width "
                     f"{band_width:.0f} working days." if band_width is not None
                     else (frb.reason or "Insufficient completions to calibrate."))
        return _res(by_id, "LI-03", band_width, narrative, finds)

    _emit("LI-03", _li03, rr_err)

    # LI-04 PCI -----------------------------------------------------------
    def _li04():
        p = ri.pci
        v = p.per_update[-1] if p.per_update else None
        finds = [Finding(lbl, "", f"PCI {_fmt(val, '{:.3f}')}")
                 for lbl, val in zip(p.labels, p.per_update)]
        return _res(by_id, "LI-04", v, p.interpretation or p.reason, finds)

    _emit("LI-04", _li04, ri_err)

    # LI-05 RDI -----------------------------------------------------------
    def _li05():
        d = ri.rdi
        # W2: the real fields are required_pace / demonstrated_pace (the old
        # getattr(row, "required", 0) reads printed a fabricated 0.00/nan).
        finds = [Finding(row.label, "",
                         f"required {_fmt(row.required_pace)} vs demonstrated "
                         f"{_fmt(row.demonstrated_pace)}; "
                         f"accrual {row.accrual_days:.1f}d")
                 for row in d.rows]
        return _res(by_id, "LI-05", d.rdi_days, d.interpretation or d.reason, finds)

    _emit("LI-05", _li05, ri_err)

    # LI-06 BDI -----------------------------------------------------------
    def _li06():
        b = rr.bdi
        finds = [Finding(x.code, "", x.detail) for x in b.decomposition]
        narrative = (f"{b.bdi_pct:.1f}% of the latest driving path "
                     f"({b.latest_label}) is post-baseline relative to {b.baseline_label}."
                     if b.bdi_pct is not None else (b.reason or ""))
        return _res(by_id, "LI-06", b.bdi_pct, narrative, finds)

    _emit("LI-06", _li06, rr_err)

    # LI-07 CDI -----------------------------------------------------------
    def _li07():
        c = ri.cdi
        # W2: the real field is dwell_share (getattr(e, "share", 0) printed a
        # fabricated 0.0% for every leaderboard entry).
        finds = [Finding(e.code, e.name,
                         f"dwell share {e.dwell_share:.1%} over "
                         f"{e.windows_present} window(s)")
                 for e in c.leaderboard[:15]]
        return _res(by_id, "LI-07", c.top_decile_share,
                    c.interpretation or c.reason, finds)

    _emit("LI-07", _li07, ri_err)

    # LI-08 IL ------------------------------------------------------------
    def _li08():
        il = rr.il
        finds = []
        for e in il.events:
            chain = e.chain_codes
            resp = e.response_label or "unresolved"
            finds.append(Finding(", ".join(chain[:6]) + ("…" if len(chain) > 6 else ""),
                                 "", f"emerged {e.emergence_label}; "
                                     f"response: {resp}"))
        v = il.median_il_updates
        narrative = (f"Median intervention latency {v} update(s) "
                     f"({il.median_il_days} days); {il.unresolved_count} unresolved."
                     if v is not None else
                     (il.reason or f"{il.unresolved_count} emergence event(s), none resolved."))
        return _res(by_id, "LI-08", v, narrative, finds)

    _emit("LI-08", _li08, rr_err)

    # LI-09 BWI -----------------------------------------------------------
    def _li09():
        w = ri.bwi
        # W1: density / bwi are Optional per row (a target absent from an
        # update yields a None row) — format via _fmt, never raw :.2f.
        finds = [Finding(row.label, "",
                         f"density {_fmt(row.density)}; BWI {_fmt(row.bwi)}")
                 for row in w.rows]
        v = None
        for row in reversed(w.rows):
            if row.bwi is not None:
                v = row.bwi
                break
        narrative = (w.interpretation or w.reason)
        if w.projected_break_label:
            narrative += f"  Projected break: {w.projected_break_label}."
        return _res(by_id, "LI-09", v, narrative, finds)

    _emit("LI-09", _li09, ri_err)

    # LI-10 MML -----------------------------------------------------------
    def _li10():
        m = rr.mml
        finds, ratios = [], []
        for row in m.wbs_results:
            if row.ratio is not None:
                ratios.append(row.ratio)
            # W2: `basis` lives on the window rows, not the WBS result (the old
            # getattr(row, "basis", "?") printed "?" for every trade).  A
            # cross-basis clean/impacted pair is disclosed as mixed rather than
            # papered over (audit MML-1; the ratio itself is a Wave-3/4 ruling).
            cb = row.clean_window.basis if row.clean_window else None
            ib = row.impacted_window.basis if row.impacted_window else None
            if cb and ib:
                basis = cb if cb == ib else f"MIXED (impacted: {ib}; clean: {cb})"
            else:
                basis = cb or ib or _DASH
            finds.append(Finding(row.wbs_code, "",
                                 f"basis {basis}; ratio {_fmt(row.ratio)}"
                                 + ("; NO CLEAN MILE" if row.no_clean_mile else "")))
        v = min(ratios) if ratios else None
        narrative = ((f"Strongest disruption contrast ratio {v:.2f} "
                      "(impacted / clean productivity; lower = stronger contrast).  "
                      if v is not None else "") + m.caption)
        return _res(by_id, "LI-10", v, narrative, finds)

    _emit("LI-10", _li10, rr_err)

    return out
