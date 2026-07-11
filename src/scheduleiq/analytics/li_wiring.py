"""Wire the LI proprietary indices (N6-N15) into the series pipeline.

Converts the li_indices / li_record results into MetricResult objects keyed
to the LI-01..LI-10 matrix rows, so the indices flow through the existing
trend workbook, report series table, and (later) the Report Card with zero
special-casing.  All informational (the Report Card spec, not the matrix,
defines their scoring normalization).
"""
from __future__ import annotations

from ..metrics.engine import CheckDef, Finding, MetricResult


def _res(matrix_by_id, cid, value, narrative, findings):
    cd = matrix_by_id.get(cid)
    if cd is None:                                    # matrix row missing: skip
        return None
    r = MetricResult(check=cd, value=value, status="INFO",
                     narrative=narrative, findings=findings[:25])
    r.threshold_applied = None
    return r


def li_series_results(sa, matrix: list[CheckDef]) -> list[MetricResult]:
    from .li_indices import run_li_indices
    from .li_record import run_li_record

    by_id = {c.id: c for c in matrix}
    out: list[MetricResult] = []
    ri = run_li_indices(sa)
    rr = run_li_record(sa)

    # LI-01 FCBI (v0.5 governed: value = cumulative operational gross burn B) --
    f = ri.fcbi
    interp = f.interpretation or f.reason
    finds = [Finding(getattr(b, "code", str(b)), getattr(b, "name", ""),
                     f"burn {getattr(b, 'consumption_days', 0):.1f}d  "
                     f"d={getattr(b, 'distance_days', 0):.1f}  "
                     f"w={getattr(b, 'weight', 0):.2f}  "
                     f"c*w={getattr(b, 'contribution', 0):.2f}")
             for b in f.top_burners]
    # current-segment cumulative OPERATIONAL burn B (basis-change windows are
    # segmented out and restart the series — do NOT revive a prior segment, O7.9)
    cum = f.cumulative_burn[-1] if f.cumulative_burn else 0.0
    cum = 0.0 if cum is None else cum          # latest window is a basis-change restart
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
    r = _res(by_id, "LI-01", cum, interp, finds)
    if r:
        out.append(r)

    # LI-02 LHL -----------------------------------------------------------
    lhl = rr.lhl
    v = None
    narrative = lhl.reason or ""
    if lhl.overall:
        v = lhl.overall.median_months
        flag = "" if lhl.overall.median_reached else \
            "  (median not reached — conservative lower bound; " \
            f"{lhl.overall.censored}/{lhl.overall.n} relationships censored)"
        narrative = (f"Logic half-life {v if v is not None else '—'} months{flag}."
                     + (f"  On/off-path ratio {lhl.on_off_ratio:.2f}."
                        if lhl.on_off_ratio is not None else ""))
    r = _res(by_id, "LI-02", v, narrative, [])
    if r:
        out.append(r)

    # LI-03 FRB -----------------------------------------------------------
    frb = rr.frb
    finds, band_width = [], None
    best = None
    for b in frb.buckets:
        if b.n > 0:
            finds.append(Finding(getattr(b, "label", "bucket"), "",
                                 f"n={b.n}, bias {getattr(b, 'bias', 0):+.1f}d, "
                                 f"band P10 {getattr(b, 'p10', 0):+.1f}d .. "
                                 f"P90 {getattr(b, 'p90', 0):+.1f}d"))
            if best is None or b.n > best.n:
                best = b
    if best is not None:
        band_width = getattr(best, "p90", 0) - getattr(best, "p10", 0)
    narrative = (f"Empirical forecast error band (largest bucket): width "
                 f"{band_width:.0f} working days." if band_width is not None
                 else (frb.reason or "Insufficient completions to calibrate."))
    r = _res(by_id, "LI-03", band_width, narrative, finds)
    if r:
        out.append(r)

    # LI-04 PCI -----------------------------------------------------------
    p = ri.pci
    v = p.per_update[-1] if p.per_update else None
    finds = [Finding(lbl, "", f"PCI {val:.3f}")
             for lbl, val in zip(p.labels, p.per_update)]
    r = _res(by_id, "LI-04", v, p.interpretation or p.reason, finds)
    if r:
        out.append(r)

    # LI-05 RDI -----------------------------------------------------------
    d = ri.rdi
    finds = [Finding(getattr(row, "label", "update"), "",
                     f"required {getattr(row, 'required', 0):.2f} vs demonstrated "
                     f"{getattr(row, 'demonstrated', 0) if getattr(row, 'demonstrated', None) is not None else float('nan'):.2f}; "
                     f"accrual {getattr(row, 'accrual_days', 0):.1f}d")
             for row in d.rows]
    r = _res(by_id, "LI-05", d.rdi_days, d.interpretation or d.reason, finds)
    if r:
        out.append(r)

    # LI-06 BDI -----------------------------------------------------------
    b = rr.bdi
    finds = [Finding(getattr(x, "code", str(x)), getattr(x, "name", ""),
                     getattr(x, "detail", getattr(x, "first_seen", "")))
             for x in b.decomposition]
    narrative = (f"{b.bdi_pct:.1f}% of the latest driving path "
                 f"({b.latest_label}) is post-baseline relative to {b.baseline_label}."
                 if b.bdi_pct is not None else (b.reason or ""))
    r = _res(by_id, "LI-06", b.bdi_pct, narrative, finds)
    if r:
        out.append(r)

    # LI-07 CDI -----------------------------------------------------------
    c = ri.cdi
    finds = [Finding(getattr(e, "code", ""), getattr(e, "name", ""),
                     f"dwell share {getattr(e, 'share', 0):.1%} over "
                     f"{getattr(e, 'windows_present', getattr(e, 'windows', 0))} window(s)")
             for e in c.leaderboard[:15]]
    r = _res(by_id, "LI-07", c.top_decile_share, c.interpretation or c.reason, finds)
    if r:
        out.append(r)

    # LI-08 IL ------------------------------------------------------------
    il = rr.il
    finds = []
    for e in il.events:
        chain = getattr(e, "chain_codes", getattr(e, "chain", []))
        resp = getattr(e, "response_label", None) or "unresolved"
        finds.append(Finding(", ".join(list(chain)[:6]) + ("…" if len(chain) > 6 else ""),
                             "", f"emerged {getattr(e, 'emergence_label', '?')}; "
                                 f"response: {resp}"))
    v = il.median_il_updates
    narrative = (f"Median intervention latency {v} update(s) "
                 f"({il.median_il_days} days); {il.unresolved_count} unresolved."
                 if v is not None else
                 (il.reason or f"{il.unresolved_count} emergence event(s), none resolved."))
    r = _res(by_id, "LI-08", v, narrative, finds)
    if r:
        out.append(r)

    # LI-09 BWI -----------------------------------------------------------
    w = ri.bwi
    finds = [Finding(getattr(row, "label", "update"), "",
                     f"density {getattr(row, 'density', 0):.2f}; "
                     f"BWI {getattr(row, 'bwi', 0) if getattr(row, 'bwi', None) is not None else float('nan'):.2f}")
             for row in w.rows]
    v = None
    for row in reversed(w.rows):
        if getattr(row, "bwi", None) is not None:
            v = row.bwi
            break
    narrative = (w.interpretation or w.reason)
    if w.projected_break_label:
        narrative += f"  Projected break: {w.projected_break_label}."
    r = _res(by_id, "LI-09", v, narrative, finds)
    if r:
        out.append(r)

    # LI-10 MML -----------------------------------------------------------
    m = rr.mml
    finds, ratios = [], []
    for row in m.wbs_results:
        ratio = getattr(row, "ratio", None)
        if ratio is not None:
            ratios.append(ratio)
        finds.append(Finding(getattr(row, "wbs", getattr(row, "wbs_code", "?")), "",
                             f"basis {getattr(row, 'basis', '?')}; ratio "
                             f"{ratio if ratio is not None else float('nan'):.2f}"
                             + ("; NO CLEAN MILE" if getattr(row, "no_clean_mile", False) else "")))
    v = min(ratios) if ratios else None
    narrative = ((f"Strongest disruption contrast ratio {v:.2f} "
                  "(impacted / clean productivity; lower = stronger contrast).  "
                  if v is not None else "") + m.caption)
    r = _res(by_id, "LI-10", v, narrative, finds)
    if r:
        out.append(r)

    return out
