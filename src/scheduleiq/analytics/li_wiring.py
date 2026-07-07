"""Wire the LI proprietary indices (N6-N15) into the series pipeline, plus the
provocative indices (N16-N20) into the PRIVILEGED / INTERNAL surface only.

N6-N15 (LI-01..LI-10): converts the li_indices / li_record results into
MetricResult objects keyed to the LI-01..LI-10 matrix rows, so the indices flow
through the existing trend workbook, report series table, and the Report Card
with zero special-casing.  All informational (the Report Card spec, not the
matrix, defines their scoring normalization).

N16-N20 (LI-11..LI-15): the provocative indices (SMI/DDI/ARR/PPS/RSA) are
DELIBERATELY NOT added to ``sa.series_results`` — that list feeds the standard
report/card/workbook, and ANALYTICS_PROPOSAL §11 requires these five to default
to a privileged/internal surface.  ``li_provocative_results`` builds their
MetricResults on demand (each carrying ``privileged=True`` / ``surface=
"internal"``) for the RC5 internal-variant card and the internal forensic
workbook to consume; the standard surfaces never see them.
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

    # LI-01 FCBI ----------------------------------------------------------
    f = ri.fcbi
    interp = f.interpretation
    finds = [Finding(b.code if hasattr(b, "code") else str(b),
                     getattr(b, "name", ""),
                     f"burn {getattr(b, 'consumption_days', getattr(b, 'c', 0)):.1f}d x "
                     f"w {getattr(b, 'weight', 0):.2f} = "
                     f"{getattr(b, 'contribution', 0):.1f}"
                     + (" [constraint-flagged]" if getattr(b, "constraint_flagged", False) else ""))
             for b in f.top_burners]
    cum = f.cumulative[-1] if f.cumulative else 0.0
    for w in f.windows:
        pct = getattr(w, "fcbi_pct", None)
        if pct is not None and pct > 100:
            interp += ("  A normalized burn above 100% is real: erosion continued "
                       "beyond the positive float available (paths driven deeper "
                       "into negative float).")
            break
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


# ==========================================================================
# N16-N20 — provocative indices (PRIVILEGED / INTERNAL surface only)
# ==========================================================================
# Map each internal-variant member ID (N16..N20) to its matrix row (LI-11..15).
PROVOCATIVE_MEMBER_MAP = {
    "N16": "LI-11", "N17": "LI-12", "N18": "LI-13", "N19": "LI-14", "N20": "LI-15",
}


def _priv_res(matrix_by_id, cid, value, narrative, findings, decomposition):
    """Build an INTERNAL-surface MetricResult for a provocative index.  Carries
    ``privileged``/``surface``/``decomposition`` attributes so the internal card
    and internal workbook can render the full decomposition; never appended to
    ``sa.series_results`` (the standard surfaces)."""
    cd = matrix_by_id.get(cid)
    if cd is None:                                    # matrix row missing: skip
        return None
    r = MetricResult(check=cd, value=value, status="INFO",
                     narrative=narrative, findings=findings[:25])
    r.threshold_applied = None
    r.privileged = True
    r.surface = "internal"
    r.decomposition = decomposition
    return r


def li_provocative_results(sa, matrix, certificate=None, events=None,
                           indices=None):
    """MetricResults for the five provocative indices (LI-11..LI-15), for the
    PRIVILEGED / INTERNAL surface only.  ``certificate`` is an optional
    precomputed N4 RobustnessCertificate (or its dict) feeding ARR and RSA;
    absent it, those two report NOT COMPUTABLE.  Never raises."""
    from .li_provocative import run_li_provocative

    by_id = {c.id: c for c in matrix}
    out: list[MetricResult] = []
    try:
        rp = run_li_provocative(sa, certificate=certificate, events=events,
                                indices=indices)
    except Exception:                                 # pragma: no cover - defensive
        return out

    # LI-11 SMI ----------------------------------------------------------
    s = rp.smi
    finds = [Finding(sig.key, sig.label,
                     f"score {sig.score:.0f}/100 (count {sig.count}); "
                     + (sig.findings[0] if sig.findings else "no findings"))
             for sig in s.signals]
    r = _priv_res(by_id, "LI-11", s.smi, s.interpretation or s.reason, finds,
                  s.to_dict())
    if r:
        out.append(r)

    # LI-12 DDI ----------------------------------------------------------
    d = rp.ddi
    finds = [Finding(name, "", "; ".join(f"{x:.2f}" for x in vals if x is not None))
             for name, vals in d.fundamentals.items()]
    r = _priv_res(by_id, "LI-12", d.ddi, d.interpretation or d.reason, finds,
                  d.to_dict())
    if r:
        out.append(r)

    # LI-13 ARR ----------------------------------------------------------
    a = rp.arr
    finds = [Finding(p.party, "", f"ARR {p.arr:.2f} (share {p.min_share:.0%}-"
                     f"{p.max_share:.0%}) over {p.n_variants} variant(s)")
             for p in a.parties]
    r = _priv_res(by_id, "LI-13", None, a.interpretation or a.reason, finds,
                  a.to_dict())
    if r:
        out.append(r)

    # LI-14 PPS ----------------------------------------------------------
    p = rp.pps
    finds = [Finding(inst.window_label, ", ".join(inst.chain_codes[:6]),
                     f"PPS {inst.pps:.0f}/100"
                     + (f"; neutral: {', '.join(inst.neutral_criteria)}"
                        if inst.neutral_criteria else ""))
             for inst in p.instances]
    top = p.instances[0].pps if p.instances else None
    r = _priv_res(by_id, "LI-14", top, p.interpretation or p.reason, finds,
                  p.to_dict())
    if r:
        out.append(r)

    # LI-15 RSA ----------------------------------------------------------
    rs = rp.rsa
    finds = [Finding(c.window_label, c.classification,
                     f"{c.delay_workdays:.1f} wd — {c.evidence}")
             for c in rs.components]
    r = _priv_res(by_id, "LI-15", rs.rsa_pct, rs.interpretation or rs.reason, finds,
                  rs.to_dict())
    if r:
        out.append(r)

    return out
