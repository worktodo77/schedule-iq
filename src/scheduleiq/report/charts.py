"""Matplotlib figures for the Word/PDF report (PNG, LI-consistent styling)."""
from __future__ import annotations

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from ..trend.series import SeriesAnalysis  # noqa: E402

TEAL = "#1F6F7B"
ACCENTS = ["#1F6F7B", "#C55A11", "#4472C4", "#7F7F7F", "#997300"]


def _style(ax, title, ylab):
    ax.set_title(title, fontsize=11, color="#222222", pad=10)
    ax.set_ylabel(ylab, fontsize=9)
    ax.tick_params(labelsize=8)
    ax.grid(True, axis="y", linewidth=0.4, color="#CCCCCC")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)


def _short_labels(sa: SeriesAnalysis) -> list[str]:
    return [s.data_date.strftime("%b %Y") if s.data_date else s.source_file
            for s in sa.schedules]


def fig_health_trend(sa: SeriesAnalysis, path: str) -> str:
    fig, ax = plt.subplots(figsize=(7.0, 3.2), dpi=200)
    x = _short_labels(sa)
    y = [a.health_score for a in sa.assessments]
    ax.plot(x, y, marker="o", color=TEAL, linewidth=2)
    for xi, yi in zip(x, y):
        ax.annotate(f"{yi:.0f}", (xi, yi), textcoords="offset points",
                    xytext=(0, 7), fontsize=8, color=TEAL)
    ax.set_ylim(0, 100)
    _style(ax, "Schedule health score by update", "Score (0–100)")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return path


def fig_metric_trends(sa: SeriesAnalysis, check_ids: list[str], title: str,
                      ylab: str, path: str) -> str:
    fig, ax = plt.subplots(figsize=(7.0, 3.2), dpi=200)
    x = _short_labels(sa)
    for i, cid in enumerate(check_ids):
        vals = sa.metric_trend(cid)
        if all(v is None for v in vals):
            continue
        name = next((r.check.name for r in sa.assessments[0].results
                     if r.check.id == cid), cid)
        ax.plot(x, vals, marker="o", linewidth=1.8,
                color=ACCENTS[i % len(ACCENTS)], label=f"{cid} {name}")
    ax.legend(fontsize=7.5, frameon=False)
    _style(ax, title, ylab)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return path


def fig_status_mix(sa: SeriesAnalysis, path: str) -> str:
    """Stacked completed/in-progress/not-started per update."""
    fig, ax = plt.subplots(figsize=(7.0, 3.2), dpi=200)
    x = _short_labels(sa)
    done, prog, ns = [], [], []
    for s in sa.schedules:
        acts = s.real_activities
        n = len(acts) or 1
        done.append(100 * sum(a.completed for a in acts) / n)
        prog.append(100 * sum(a.in_progress for a in acts) / n)
        ns.append(100 * sum(a.not_started for a in acts) / n)
    ax.bar(x, done, color=TEAL, label="Completed")
    ax.bar(x, prog, bottom=done, color="#C55A11", label="In progress")
    ax.bar(x, ns, bottom=[d + p for d, p in zip(done, prog)],
           color="#BFBFBF", label="Not started")
    ax.legend(fontsize=7.5, frameon=False, ncols=3)
    ax.set_ylim(0, 100)
    _style(ax, "Activity status mix by update", "% of activities")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return path


def fig_float_histogram(assessment, path: str) -> str:
    s = assessment.schedule
    vals = []
    for a in s.real_activities:
        if not a.completed and a.total_float_hours is not None:
            cal = s.cal_for(a)
            hpd = cal.hours_per_day if cal and cal.hours_per_day else 8.0
            vals.append(a.total_float_hours / hpd)
    fig, ax = plt.subplots(figsize=(7.0, 3.0), dpi=200)
    if vals:
        ax.hist(vals, bins=25, color=TEAL, edgecolor="white")
        ax.axvline(0, color="#C55A11", linewidth=1.2)
        ax.axvline(44, color="#997300", linewidth=1.2, linestyle="--")
    _style(ax, f"Total float distribution — {s.label()}",
           "Activities")
    ax.set_xlabel("Total float (working days); 0 and 44-day DCMA lines marked",
                  fontsize=8)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return path


def series_figures(sa: SeriesAnalysis, out_dir: str) -> list[tuple[str, str]]:
    """Returns (caption, png_path) pairs for the report."""
    figs = []
    p = os.path.join(out_dir, "fig_health.png")
    fig_health_trend(sa, p)
    figs.append(("Schedule health score by update", p))
    p = os.path.join(out_dir, "fig_dcma.png")
    fig_metric_trends(sa, ["DCMA-01", "DCMA-05", "DCMA-06", "DCMA-07"],
                      "DCMA failure percentages by update", "% of population", p)
    figs.append(("DCMA metric trends by update", p))
    p = os.path.join(out_dir, "fig_status.png")
    fig_status_mix(sa, p)
    figs.append(("Activity status mix by update", p))
    p = os.path.join(out_dir, "fig_float.png")
    fig_float_histogram(sa.assessments[-1], p)
    figs.append(("Total float distribution — latest update", p))
    return figs
