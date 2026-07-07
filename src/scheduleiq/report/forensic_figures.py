"""Matplotlib figures for the forensic outputs wave — half-step (D9), daily
ledger (N3), and robustness certificate (N4).

Deterministic, LI-house-style figures built directly from the plain-dict
serializations of the engine analytics: ``HalfStepResult.to_dict()``
(:mod:`scheduleiq.analytics.halfstep`), ``DailyLedger.to_dict()``
(:mod:`scheduleiq.analytics.dailyledger``), and
``RobustnessCertificate.to_dict()`` (:mod:`scheduleiq.analytics.robustness`).
None of these functions import the analytics modules — they only read the
dict shape, matching ``report/impact_figures.py``'s contract, whose house
colors, presentation note, and date/axis discipline are reused verbatim
(imported, not duplicated) so this module never drifts from the A3 figures.

Presentation rule (ADR-0007 §4): every number drawn here is a diagnostic
delta, never a competing schedule.  Every figure carries the PRESENTATION_NOTE
and, where the underlying result is expressly PRELIMINARY, that label too, so
the image is self-explanatory if it is lifted out of its report context.

Determinism: fixed figsize/dpi, no wall-clock timestamps, inputs are walked
in the order the analytics modules already produced them (both deterministic
themselves), so two calls on the same dict produce byte-identical PNGs.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from .impact_figures import (AMBER, GRAY, LIGHT_GRAY, ORANGE, PRESENTATION_NOTE,
                             TEAL, _fmt_date, _style)  # noqa: E402

_RESIDUAL_COLOR = "#595959"

_VERDICT_COLOR = {"STABLE": TEAL, "MODERATE": AMBER, "UNSTABLE": ORANGE}


def _placeholder(out_path: str, title: str, reason: str, footer: str = "",
                 figsize: tuple = (8.5, 2.4)) -> str:
    fig, ax = plt.subplots(figsize=figsize, dpi=200)
    ax.axis("off")
    ax.text(0.02, 0.68, title, fontsize=11, color="#222222")
    ax.text(0.02, 0.42, reason, fontsize=9, color="#666666", wrap=True)
    ax.text(0.02, 0.06, footer or PRESENTATION_NOTE, fontsize=7, color="#666666")
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)
    return out_path


def _iso_date(v: Any) -> Optional[date]:
    if not v:
        return None
    if isinstance(v, (date, datetime)):
        return v if isinstance(v, date) and not isinstance(v, datetime) else v.date()
    try:
        return datetime.fromisoformat(str(v).split("T")[0]).date()
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# halfstep_figure — MIP 3.4 progress/revision bridge + revision attribution
# ---------------------------------------------------------------------------
def halfstep_figure(hs_dict: dict[str, Any], out_path: str) -> str:
    """Two-segment horizontal bridge (E_n -> half-step H -> E_n1) labelled with
    the progress and revision effects in workdays, plus a per-class revision
    attribution inset (top classes + the interaction/residual, hatched)."""
    pair = hs_dict.get("pair") or {}
    decomp = hs_dict.get("decomposition") or {}
    attrib = hs_dict.get("revision_attribution") or {}
    pair_label = f"{pair.get('earlier', '—')} → {pair.get('later', '—')}"

    prog_wd = decomp.get("progress_effect_workdays")
    rev_wd = decomp.get("revision_effect_workdays")
    if (hs_dict.get("refused") or not decomp.get("computable", True)
            or prog_wd is None or rev_wd is None):
        reason = (hs_dict.get("refusal") or decomp.get("blocking")
                  or "half-step decomposition not computable")
        return _placeholder(
            out_path, "MIP 3.4 half-step decomposition — not available",
            f"{pair_label}: {reason}",
            footer="ADR-0007 diagnostic.  " + PRESENTATION_NOTE)

    eng = decomp.get("engine_dates") or {}
    en_ef = _fmt_date(eng.get("E_n_target_early_finish"))
    h_ef = _fmt_date(eng.get("half_step_target_early_finish"))
    en1_ef = _fmt_date(eng.get("E_n1_target_early_finish"))
    tgt = decomp.get("target") or {}

    per_class = [c for c in (attrib.get("per_class") or [])
                if c.get("delta_workdays") is not None]
    residual = attrib.get("interaction_residual_workdays")

    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(9.5, 3.4 + 0.35 * max(len(per_class) + 1, 4)), dpi=200,
        gridspec_kw={"height_ratios": [1.3, 2.0]})

    # -- bridge row -----------------------------------------------------------
    total = prog_wd + rev_wd
    ax1.barh(0, prog_wd, left=0, height=0.45, color=TEAL, edgecolor="white",
             label="Progress effect")
    ax1.barh(0, rev_wd, left=prog_wd, height=0.45, color=AMBER, edgecolor="white",
             label="Revision effect")
    for x, lbl, date_txt in ((0, "E_n", en_ef), (prog_wd, "Half-step H", h_ef),
                             (total, "E_n1", en1_ef)):
        ax1.axvline(x, color="#222222", linewidth=1.0,
                   linestyle="--" if x == prog_wd else "-")
        ax1.text(x, 0.42, f"{lbl}\n({date_txt})", ha="center", va="bottom",
                 fontsize=8.5, color="#222222")
    ax1.text(prog_wd / 2.0 if prog_wd else 0, -0.02, f"progress {prog_wd:+d} wd",
             ha="center", va="top", fontsize=8, color=TEAL)
    ax1.text(prog_wd + rev_wd / 2.0 if rev_wd else prog_wd, -0.02,
             f"revision {rev_wd:+d} wd", ha="center", va="top", fontsize=8,
             color="#8A6D00")
    ax1.set_yticks([])
    ax1.set_ylim(-0.5, 0.85)
    lo = min(0, prog_wd, total)
    hi = max(0, prog_wd, total)
    pad = max(abs(hi - lo) * 0.15, 1.0)
    ax1.set_xlim(lo - pad, hi + pad)
    ax1.set_xlabel("Workdays of the target's own calendar", fontsize=8)
    code = tgt.get("code") or tgt.get("uid") or "target"
    ax1.set_title(f"MIP 3.4 half-step decomposition — {code}  ({pair_label})",
                  fontsize=11, color="#222222", pad=10)
    _style(ax1)
    ax1.grid(False, axis="x")

    # -- per-class attribution inset ------------------------------------------
    rows = [(c["class"], float(c["delta_workdays"]), False) for c in per_class]
    if residual is not None:
        rows.append(("interaction/residual", float(residual), True))
    if rows:
        n = len(rows)
        y = list(range(n - 1, -1, -1))
        vals = [r[1] for r in rows]
        colors = [(_RESIDUAL_COLOR if r[2] else (TEAL if r[1] < 0 else
                  (ORANGE if r[1] > 0 else LIGHT_GRAY))) for r in rows]
        bars = ax2.barh(y, vals, color=colors, height=0.55, edgecolor="white")
        for bi, r in zip(bars, rows):
            if r[2]:
                bi.set_hatch("///")
        ax2.axvline(0, color="#222222", linewidth=1.0)
        ax2.set_yticks(y)
        ax2.set_yticklabels([r[0] for r in rows], fontsize=8.5)
        for yi, v in zip(y, vals):
            off = 0.3 if v >= 0 else -0.3
            ha = "left" if v >= 0 else "right"
            ax2.text(v + off, yi, f"{v:+.0f} wd", va="center", ha=ha, fontsize=8,
                     color="#222222")
        xm = max([abs(v) for v in vals] + [1.0])
        ax2.set_xlim(-xm * 1.4, xm * 1.4)
    else:
        ax2.axis("off")
        ax2.text(0.02, 0.5, "no revision-class attribution available",
                 fontsize=9, color="#666666")
    ax2.set_xlabel("Class-isolated delta at the target (wd)  |  hatched = "
                   "interaction/residual, never forced to zero", fontsize=8)
    ax2.set_title("Named revision attribution (per class, re-applied alone on "
                  "the half-step)", fontsize=10, color="#222222", pad=8)
    _style(ax2)
    ax2.grid(False, axis="x")

    fig.text(0.01, 0.005,
             ("PRELIMINARY — progress/revision bifurcation; causation, "
              "entitlement, concurrency, and quantum are reserved to the "
              "expert (AACE 29R-03).  " + PRESENTATION_NOTE),
             fontsize=6.5, color="#666666")
    fig.tight_layout(rect=(0, 0.035, 1, 1))
    fig.savefig(out_path)
    plt.close(fig)
    return out_path


# ---------------------------------------------------------------------------
# dailyledger_figure — N3 cumulative delay curve
# ---------------------------------------------------------------------------
def dailyledger_figure(dl_dict: dict[str, Any], out_path: str) -> str:
    """Cumulative delay step plot over the window: nonzero days marked,
    controlling-activity changes annotated (capped at ~6, deterministically
    thinned), event markers shown when present, arithmetic-check note in the
    footer."""
    pair = dl_dict.get("pair") or {}
    pair_label = f"{pair.get('earlier', '—')} → {pair.get('later', '—')}"
    rows = dl_dict.get("rows") or []
    if not dl_dict.get("computable", True) or not rows:
        reason = dl_dict.get("blocking") or "daily ledger not computable"
        return _placeholder(
            out_path, "N3 daily delay ledger — not available",
            f"{pair_label}: {reason}",
            footer="ADR-0007 diagnostic.  " + PRESENTATION_NOTE)

    days = [_iso_date(r["day"]) for r in rows]
    cum = [r["cumulative_workdays"] for r in rows]

    fig, ax = plt.subplots(figsize=(9.8, 4.4), dpi=200)
    ax.step(days, cum, where="post", color=TEAL, linewidth=1.6, zorder=3)
    ax.axhline(0, color="#BBBBBB", linewidth=0.8)

    nz_days = [d for d, r in zip(days, rows) if r.get("delta_workdays")]
    nz_cum = [c for c, r in zip(cum, rows) if r.get("delta_workdays")]
    if nz_days:
        ax.scatter(nz_days, nz_cum, color=AMBER, s=16, zorder=4,
                   label="nonzero day")

    ev_days = [d for d, r in zip(days, rows) if r.get("event_ids")]
    ev_cum = [c for c, r in zip(cum, rows) if r.get("event_ids")]
    if ev_days:
        ax.scatter(ev_days, ev_cum, marker="v", color=ORANGE, s=40, zorder=5,
                   label="event window")

    # controlling-activity change points, deterministically thinned to ~6
    changes = []
    prev = None
    for i, r in enumerate(rows):
        code = r.get("controlling_code")
        if code != prev:
            changes.append(i)
            prev = code
    cap = 6
    if len(changes) > cap:
        step = (len(changes) - 1) / (cap - 1)
        idxs = sorted({changes[round(k * step)] for k in range(cap)})
    else:
        idxs = changes
    for i in idxs:
        ax.annotate(rows[i]["controlling_code"], (days[i], cum[i]),
                   textcoords="offset points", xytext=(0, 10), fontsize=7,
                   color="#444444", ha="center",
                   arrowprops=dict(arrowstyle="-", color="#AAAAAA", lw=0.6))

    ax.set_xlabel("Day", fontsize=8)
    ax.set_ylabel("Cumulative delay (wd, target calendar)", fontsize=8)
    tgt = dl_dict.get("target") or {}
    ax.set_title(f"N3 daily delay ledger — {tgt.get('code', 'target')}  "
                f"({pair_label})", fontsize=11, color="#222222", pad=10)
    if nz_days or ev_days:
        ax.legend(loc="best", fontsize=7.5, frameon=False)
    fig.autofmt_xdate()
    _style(ax)

    ac = dl_dict.get("arithmetic_check") or {}
    check_txt = ("arithmetic check: Σ daily deltas "
                f"{ac.get('sum_of_daily_deltas_wd')} wd == endpoint movement "
                f"{ac.get('endpoint_delta_wd')} wd (exact: {ac.get('exact')}).")
    fig.text(0.01, 0.02,
             "PRELIMINARY — observational daily delay ledger.  " + check_txt,
             fontsize=6.8, color="#444444")
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    fig.savefig(out_path)
    plt.close(fig)
    return out_path


# ---------------------------------------------------------------------------
# robustness_figure — N4 stability range plot
# ---------------------------------------------------------------------------
def robustness_figure(cert_dict: dict[str, Any], out_path: str) -> str:
    """Per-party (or TOTAL) range plot: one horizontal min-max bar per measured
    series across the computable method variants, each variant plotted as a
    tick on that bar, with the verdict band labelled at right.  The §8.4
    stability sentences form the caption block."""
    stability = cert_dict.get("stability") or []
    if not stability:
        reason = "no computable method variant to build a stability screen from"
        return _placeholder(
            out_path, "N4 methodology-robustness certificate — not available",
            reason, footer="ADR-0007 diagnostic.  " + PRESENTATION_NOTE)

    n = len(stability)
    fig, ax = plt.subplots(figsize=(9.8, 1.4 + 0.7 * n), dpi=200)
    y = list(range(n - 1, -1, -1))
    for yi, s in zip(y, stability):
        mn, mx = s["min"], s["max"]
        verdict = s.get("verdict", "")
        color = _VERDICT_COLOR.get(verdict, GRAY)
        ax.hlines(yi, mn, mx if mx != mn else mn + 0.01, color=color,
                 linewidth=7, zorder=2)
        vals = s.get("values") or []
        ax.plot(vals, [yi] * len(vals), marker="|", linestyle="none",
               color="#222222", markersize=13, markeredgewidth=1.4, zorder=3)
        ax.text(mx + max(abs(mx - mn), 1.0) * 0.08, yi,
               f"{verdict}  (n={s.get('n_variants')})", va="center", ha="left",
               fontsize=8.5, color=color, fontweight="bold")
    ax.set_yticks(y)
    ax.set_yticklabels([s["series"] for s in stability], fontsize=9)
    allmin = min(s["min"] for s in stability)
    allmax = max(s["max"] for s in stability)
    pad = max(abs(allmax - allmin) * 0.35, 1.5)
    ax.set_xlim(allmin - pad * 0.2, allmax + pad)
    ax.set_xlabel("Total workday movement across the swept method variants",
                 fontsize=8)
    ax.set_title("N4 methodology-robustness certificate — per-series stability",
                fontsize=11, color="#222222", pad=10)
    _style(ax)

    sentences = " ".join(s.get("sentence", "") for s in stability)
    fig.text(0.01, 0.01,
             "PRELIMINARY — a stability screen of the METHOD, not an "
             "apportionment opinion.  " + sentences,
             fontsize=6.8, color="#444444", wrap=True)
    fig.tight_layout(rect=(0, 0.10, 1, 1))
    fig.savefig(out_path)
    plt.close(fig)
    return out_path
