"""Matplotlib figures for the milestone impact diagnostic (backlog A3).

Two deterministic, LI-house-style figures built directly from the plain-dict
serializations of the engine analytics — ``ImpactAnalysis.to_dict()`` (see
``scheduleiq.analytics.impact``) and ``AsBuiltReconstruction.to_dict()`` (see
``scheduleiq.analytics.asbuilt``).  Neither function imports the analytics
modules; they only read the dict shape, so a caller can enrich the dict (for
example, stamping a ``data_date`` key) without touching the analytics code.

Presentation rule (ADR-0007 §4): every number drawn here is a diagnostic
delta, never a competing schedule.  Both figures carry that label verbatim so
the image is self-explanatory if it is lifted out of its report context.

Determinism: fixed figsize/dpi, no wall-clock timestamps, and inputs are
walked in the order the analytics modules already produced them (both are
themselves deterministic), so two calls on the same dict produce byte-
identical PNGs.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.dates as mdates  # noqa: E402

from ..analytics.damages import (DamagesConfig, STANDING_LABEL, exposure_for_date,  # noqa: E402
                                 exposure_for_delta)

TEAL = "#1F6F7B"
AMBER = "#FFC000"
ORANGE = "#C55A11"
GRAY = "#7F7F7F"
LIGHT_GRAY = "#BFBFBF"

PRESENTATION_NOTE = ("Engine diagnostic deltas (ADR-0007) — tool-of-record "
                     "dates remain the schedule.  PRELIMINARY — expert "
                     "review required.")

# scenarios in ImpactAnalysis.to_dict()["waterfall"] that carry no engine
# rerun (visibility-only metrics) -- excluded from the bridge bars.
_NON_DELTA_SCENARIOS = {"lags_visibility", "calendar_neutral_restatement"}

_SCENARIO_LABELS = {
    "constraints_released_all": "Constraints released",
    "expected_finish_released": "Expected-finish released",
    "leads_zeroed": "Leads zeroed",
    "oos_statusing_delta": "OOS: retained vs. override",
}


def _scenario_label(scenario: str) -> str:
    return _SCENARIO_LABELS.get(scenario, scenario.replace("_", " "))


def _fmt_date(v: Any) -> str:
    if not v:
        return "—"
    if isinstance(v, (date, datetime)):
        return v.strftime("%d %b %Y")
    s = str(v)
    try:
        return datetime.fromisoformat(s.split("T")[0]).strftime("%d %b %Y")
    except ValueError:
        return s


def _style(ax) -> None:
    ax.grid(True, axis="x", linewidth=0.4, color="#CCCCCC")
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.tick_params(labelsize=9)


# ---------------------------------------------------------------------------
# waterfall_figure — the A3 one-pager
# ---------------------------------------------------------------------------
def waterfall_figure(impact_dict: dict[str, Any], out_path: str,
                     damages: Optional[DamagesConfig] = None) -> str:
    """Horizontal waterfall/bridge of the ADR-0007 diagnostic deltas.

    Row order: tool-of-record baseline (labelled with its date), one row per
    COMPUTABLE delta scenario (skipping visibility-only scenarios such as
    ``lags_visibility``), then the engine baseline.  Each scenario bar is
    drawn from the engine baseline (x = 0) out to its delta in workdays, so
    the two anchor rows read as the bridge's start and end and every
    scenario bar reads as its movement relative to that reference.

    ``damages`` (backlog S7) is OPTIONAL and strictly additive: ``None`` (the
    default) reproduces a byte-identical PNG to before this parameter
    existed.  When given, each computable scenario's bar annotation gains its
    time-cost exposure amount, and the footer gains the engine baseline
    finish's LD exposure vs. ``damages.contractual_completion``.
    """
    target = impact_dict.get("target") or {}
    baseline = impact_dict.get("baseline") or {}
    handshake = impact_dict.get("handshake") or {}
    waterfall = impact_dict.get("waterfall") or []

    rows: list[dict[str, Any]] = []
    non_computable_names: list[str] = []
    for d in waterfall:
        scenario = d.get("scenario", "")
        if scenario in _NON_DELTA_SCENARIOS:
            continue
        if not d.get("computable", False) or d.get("delta_workdays") is None:
            non_computable_names.append(_scenario_label(scenario))
            rows.append({"label": _scenario_label(scenario), "value": 0.0,
                        "computable": False, "annotation": "not computable"})
            continue
        wd = d["delta_workdays"]
        cd = d.get("delta_calendar_days")
        ann = f"{wd:+d} wd" + (f" / {cd:+d} cd" if cd is not None else "")
        if damages is not None:
            if damages.daily_basis == "workday":
                delta, note = wd, "workdays (target calendar)"
            else:
                delta, note = cd, "calendar days"
            exp = exposure_for_delta(delta, damages, note)
            if exp.amount is not None:
                ann += "  |  " + exp.formula_text.rsplit(" = ", 1)[-1]
        rows.append({"label": _scenario_label(scenario), "value": float(wd),
                    "computable": True, "annotation": ann})

    record_ef = baseline.get("record_early_finish")
    engine_ef = baseline.get("engine_early_finish")

    labels = [f"Tool-of-record finish\n({_fmt_date(record_ef)})"]
    values = [0.0]
    colors = [GRAY]
    annotations = [_fmt_date(record_ef)]
    for r in rows:
        labels.append(r["label"])
        values.append(r["value"])
        if not r["computable"]:
            colors.append(LIGHT_GRAY)
        elif r["value"] < 0:
            colors.append(TEAL)
        elif r["value"] > 0:
            colors.append(ORANGE)
        else:
            colors.append(LIGHT_GRAY)
        annotations.append(r["annotation"])
    labels.append(f"Engine baseline\n({_fmt_date(engine_ef)})")
    values.append(0.0)
    colors.append(TEAL)
    annotations.append(_fmt_date(engine_ef))

    n = len(labels)
    fig, ax = plt.subplots(figsize=(9.5, 1.1 + 0.55 * n), dpi=200)
    y = list(range(n - 1, -1, -1))
    ax.barh(y, values, color=colors, height=0.55, edgecolor="white")
    ax.axvline(0, color="#222222", linewidth=1.0)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=9)
    for yi, v, ann in zip(y, values, annotations):
        off = 0.4 if v >= 0 else -0.4
        ha = "left" if v >= 0 else "right"
        xpos = v + off
        ax.text(xpos, yi, ann, va="center", ha=ha, fontsize=8, color="#222222")

    xmax = max([abs(v) for v in values] + [1.0])
    ax.set_xlim(-xmax * 1.35, xmax * 1.35)
    ax.set_xlabel("Workday delta relative to the engine baseline "
                  "(negative = target moves earlier)", fontsize=8)
    _style(ax)

    code = target.get("code") or target.get("uid") or "target"
    name = target.get("name")
    data_date = _fmt_date(impact_dict.get("data_date"))
    title_bits = f"Milestone {code} diagnostic"
    if name:
        title_bits += f" — {name}"
    title_bits += f"  (data date {data_date})"
    ax.set_title(title_bits, fontsize=11, color="#222222", pad=12)

    match_rate = handshake.get("match_rate_pct")
    hs_line = (f"Validation handshake: {match_rate:.1f}% match"
              if match_rate is not None else "Validation handshake: —")
    note_line = PRESENTATION_NOTE + "  " + hs_line
    if damages is not None:
        ld = exposure_for_date(engine_ef, damages)
        if ld.amount is not None:
            note_line += ("  |  Engine baseline finish LD exposure: "
                          + ld.formula_text + ".  " + STANDING_LABEL)
    fig.text(0.01, 0.02, note_line, fontsize=7.5, color="#444444")

    skipped = [_scenario_label(s) for s in
              {d.get("scenario") for d in waterfall} & _NON_DELTA_SCENARIOS]
    if skipped or non_computable_names:
        foot = []
        if skipped:
            foot.append("Non-delta scenarios (visibility only, no engine "
                        "rerun): " + ", ".join(sorted(skipped)) + ".")
        if non_computable_names:
            foot.append("Not computable this run: " +
                        ", ".join(non_computable_names) + ".")
        fig.text(0.01, -0.01 if n < 4 else 0.005, " ".join(foot),
                 fontsize=6.5, color="#666666")

    fig.tight_layout(rect=(0, 0.07, 1, 1))
    fig.savefig(out_path)
    plt.close(fig)
    return out_path


# ---------------------------------------------------------------------------
# asbuilt_figure — the as-built top chain
# ---------------------------------------------------------------------------
def asbuilt_figure(asbuilt_dict: dict[str, Any], out_path: str,
                   damages: Optional[DamagesConfig] = None) -> str:
    """Horizontal timeline of the top as-built chain's links.

    One row per link (predecessor code -> successor code), spanning the two
    anchoring actual dates; gap-flagged links (unexplained actual lag beyond
    the configured threshold) are drawn in amber.  The contradicted-link
    count is footnoted.

    ``damages`` (backlog S7) is OPTIONAL and strictly additive: ``None`` (the
    default) reproduces a byte-identical PNG to before this parameter
    existed.  When given, the footer gains the chain span's time-cost
    exposure.
    """
    chains = asbuilt_dict.get("chains") or []
    label = asbuilt_dict.get("label", "")
    summary = asbuilt_dict.get("summary") or {}

    if not chains:
        fig, ax = plt.subplots(figsize=(8.0, 2.2), dpi=200)
        ax.axis("off")
        reason = asbuilt_dict.get("reason") or "no as-built chain reconstructed"
        ax.text(0.02, 0.6, "As-built path reconstruction — no chain available",
               fontsize=11, color="#222222")
        ax.text(0.02, 0.35, reason, fontsize=9, color="#666666")
        ax.text(0.02, 0.05, label, fontsize=7, color="#666666")
        fig.tight_layout()
        fig.savefig(out_path)
        plt.close(fig)
        return out_path

    chain = chains[0]
    links = chain.get("links") or []

    rows: list[tuple[str, Optional[date], Optional[date], bool]] = []
    for lk in links:
        p = lk.get("pred_anchor_date")
        s = lk.get("succ_anchor_date")
        lbl = f"{lk.get('pred_code')} → {lk.get('succ_code')} " \
              f"({lk.get('rel_type')})"
        pd_ = datetime.fromisoformat(p).date() if p else None
        sd_ = datetime.fromisoformat(s).date() if s else None
        rows.append((lbl, pd_, sd_, bool(lk.get("is_gap"))))

    n = max(len(rows), 1)
    fig, ax = plt.subplots(figsize=(9.5, 1.1 + 0.5 * n), dpi=200)
    if rows:
        y = list(range(n - 1, -1, -1))
        for yi, (lbl, pd_, sd_, is_gap) in zip(y, rows):
            if pd_ is None or sd_ is None:
                ax.text(0.0, yi, f"{lbl}: date missing", fontsize=8,
                       color="#666666", transform=ax.get_yaxis_transform())
                continue
            left = mdates.date2num(pd_)
            width = max(mdates.date2num(sd_) - left, 0.3)
            ax.barh(yi, width, left=left, height=0.5,
                   color=(AMBER if is_gap else TEAL), edgecolor="white")
        ax.set_yticks(y)
        ax.set_yticklabels([r[0] for r in rows], fontsize=8)
        ax.xaxis_date()
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b %y"))
    _style(ax)

    end_code = asbuilt_dict.get("end_anchor_code") or "—"
    rank = chain.get("rank")
    span = chain.get("span_workdays")
    span_txt = f"{span:g} wd" if span is not None else "—"
    ax.set_title(f"As-built chain #{rank} to {end_code} — span {span_txt} "
                f"({chain.get('span_calendar') or '—'})",
                fontsize=11, color="#222222", pad=12)

    contradicted = summary.get("contradicted_relationships", 0)
    gap_flags = len(chain.get("gap_flags") or [])
    foot = (f"{label}  Gaps flagged on this chain: {gap_flags}.  "
           f"Contradicted (out-of-sequence) relationships in the file: "
           f"{contradicted}.")
    if damages is not None:
        exp = exposure_for_delta(span, damages, "workdays (as-built chain span)")
        if exp.amount is not None:
            foot += "  Chain-span time-cost exposure: " + exp.formula_text + "."
    fig.text(0.01, 0.02, foot, fontsize=7, color="#444444")

    fig.tight_layout(rect=(0, 0.06, 1, 1))
    fig.savefig(out_path)
    plt.close(fig)
    return out_path
