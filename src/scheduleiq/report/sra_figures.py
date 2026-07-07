"""Matplotlib figures for the Monte Carlo / schedule risk analysis (SRA)
outputs (backlog M3).

Deterministic, LI-house-style figures built directly from the plain-dict
serialization ``SimulationResult.to_dict()``
(:mod:`scheduleiq.analytics.montecarlo`).  This module never imports the
analytics module — it only reads the dict shape — and reuses the house
colors, date formatting, and presentation note from ``report/impact_figures.py``
so the SRA figures never drift from the rest of the report's visual system.

Presentation rule (ADR-0007 §4): every probabilistic date drawn here is a
diagnostic delta — the deterministic engine date and the tool-of-record
record date are always carried alongside, never merged.  When the simulation
carries a ``branding`` string (the M4 SRA-readiness gate stamped
DIAGNOSTIC_ONLY), both figures show it as a prominent banner.

Determinism: fixed figsize/dpi, no wall-clock timestamps; the sample and
tornado are already deterministic for a fixed seed, so two calls on the same
dict produce byte-identical PNGs.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from .impact_figures import AMBER, ORANGE, PRESENTATION_NOTE, TEAL, _fmt_date, _style  # noqa: E402

_BANNER_RED = "#C00000"


def _placeholder(out_path: str, title: str, reason: str,
                 figsize: tuple = (8.5, 2.4)) -> str:
    fig, ax = plt.subplots(figsize=figsize, dpi=200)
    ax.axis("off")
    ax.text(0.02, 0.68, title, fontsize=11, color="#222222")
    ax.text(0.02, 0.42, reason, fontsize=9, color="#666666")
    ax.text(0.02, 0.06, PRESENTATION_NOTE, fontsize=7, color="#666666")
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


def _branding_banner(fig, branding: Optional[str]) -> None:
    if not branding:
        return
    fig.text(0.5, 0.985, "DIAGNOSTIC ONLY — SRA-readiness screens failed",
             fontsize=10, color="white", ha="center", va="top",
             fontweight="bold",
             bbox=dict(boxstyle="round,pad=0.35", facecolor=_BANNER_RED,
                       edgecolor="none"))


# ---------------------------------------------------------------------------
# scurve_figure — cumulative distribution of target finish dates
# ---------------------------------------------------------------------------
def scurve_figure(sim_dict: dict[str, Any], out_path: str) -> str:
    """ECDF of the sampled target completion dates.  Vertical lines mark the
    deterministic engine date and the tool-of-record record date; P10/P50/P80/
    P90 are marked and labelled with their dates.  A DIAGNOSTIC-ONLY branding
    banner is drawn when ``sim_dict["branding"]`` is present."""
    sample = sim_dict.get("target_sample") or {}
    dates = [d for d in (sample.get("dates") or []) if d]
    tgt = sim_dict.get("target") or {}
    if not dates:
        reason = "no completion sample available (target unresolved or 0 iterations)"
        return _placeholder(out_path, "SRA S-curve — not available", reason)

    ddates = sorted(_iso_date(d) for d in dates)
    n = len(ddates)
    y = [(i + 1) / n for i in range(n)]

    fig, ax = plt.subplots(figsize=(9.5, 4.6), dpi=200)
    ax.step(ddates, y, where="post", color=TEAL, linewidth=1.8, zorder=3)
    ax.set_ylim(0, 1.02)
    ax.set_ylabel("Cumulative probability of completion by date", fontsize=8)
    ax.set_xlabel("Target completion date", fontsize=8)

    det = _iso_date(sim_dict.get("deterministic_engine_finish"))
    rec = _iso_date(sim_dict.get("record_finish"))
    if det is not None:
        ax.axvline(det, color="#222222", linewidth=1.2, linestyle="-")
        ax.text(det, 1.01, f"Engine (det.)\n{_fmt_date(det)}", fontsize=7.5,
               color="#222222", ha="center", va="bottom")
    if rec is not None:
        ax.axvline(rec, color="#7F7F7F", linewidth=1.2, linestyle=":")
        ax.text(rec, -0.06, f"Record\n{_fmt_date(rec)}", fontsize=7.5,
               color="#555555", ha="center", va="top")

    percentiles = sim_dict.get("percentiles") or {}
    for key, py in (("P10", 0.10), ("P50", 0.50), ("P80", 0.80), ("P90", 0.90)):
        blk = percentiles.get(key) or {}
        pd_ = _iso_date(blk.get("date"))
        if pd_ is None:
            continue
        ax.axvline(pd_, color=AMBER, linewidth=0.9, linestyle="--", zorder=2)
        ax.plot([pd_], [py], marker="o", color=AMBER, markersize=5, zorder=4)
        ax.annotate(f"{key}\n{_fmt_date(pd_)}", (pd_, py),
                   textcoords="offset points", xytext=(6, 0), fontsize=7.5,
                   color="#8A6D00", va="center")

    code = tgt.get("code") or tgt.get("uid") or "target"
    ax.set_title(f"SRA completion distribution — {code}  "
                f"({sim_dict.get('iterations', 0)} iterations, "
                f"seed {sim_dict.get('seed')})",
                fontsize=11, color="#222222", pad=14)
    _style(ax)
    fig.autofmt_xdate()

    mb = sim_dict.get("merge_bias") or {}
    fig.text(0.01, 0.01,
             "PRELIMINARY — probabilistic dates are diagnostic (ADR-0007 §4); "
             f"target merge bias (P50 − deterministic): "
             f"{mb.get('merge_bias_workdays')} wd.  " + PRESENTATION_NOTE,
             fontsize=6.5, color="#444444")
    _branding_banner(fig, sim_dict.get("branding"))
    fig.tight_layout(rect=(0, 0.05, 1, 0.94 if sim_dict.get("branding") else 1))
    fig.savefig(out_path)
    plt.close(fig)
    return out_path


# ---------------------------------------------------------------------------
# tornado_figure — top-N cruciality bars
# ---------------------------------------------------------------------------
def tornado_figure(sim_dict: dict[str, Any], out_path: str) -> str:
    """Top-N cruciality (duration-sensitivity) bars, each annotated with its
    criticality index.  ``tornado`` in the dict is already the top-N slice,
    sorted descending by cruciality."""
    rows = sim_dict.get("tornado") or []
    if not rows:
        reason = "no varying activities produced a cruciality ranking"
        return _placeholder(out_path, "SRA tornado — not available", reason)

    n = len(rows)
    fig, ax = plt.subplots(figsize=(9.5, 1.1 + 0.42 * n), dpi=200)
    y = list(range(n - 1, -1, -1))
    vals = [r.get("cruciality", 0.0) for r in rows]
    ax.barh(y, vals, color=TEAL, height=0.6, edgecolor="white")
    labels = [f"{r.get('code', '—')} ({r.get('tier', '—')})" for r in rows]
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=8.5)
    for yi, r in zip(y, rows):
        crit = r.get("criticality_index_pct")
        ax.text(r.get("cruciality", 0.0) + 0.01, yi,
               f"CI {crit:g}%" if crit is not None else "", va="center",
               ha="left", fontsize=7.5, color="#444444")
    ax.set_xlim(0, max(vals + [0.1]) * 1.35)
    ax.set_xlabel("Cruciality  |Spearman(sampled duration, target offset)|",
                 fontsize=8)
    ax.set_title(f"SRA tornado — top {n} activities by cruciality",
                fontsize=11, color="#222222", pad=12)
    _style(ax)

    fig.text(0.01, 0.01,
             "PRELIMINARY — cruciality is a diagnostic sensitivity measure, "
             "not a criticality ranking on its own; criticality index (CI) is "
             "shown per bar for context.  " + PRESENTATION_NOTE,
             fontsize=6.5, color="#444444")
    _branding_banner(fig, sim_dict.get("branding"))
    fig.tight_layout(rect=(0, 0.05, 1, 0.94 if sim_dict.get("branding") else 1))
    fig.savefig(out_path)
    plt.close(fig)
    return out_path
