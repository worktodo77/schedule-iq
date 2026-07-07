"""LI-house-style report blocks for the multi-path analysis section
(backlog A1, P1-P4; ANALYTICS_PROPOSAL.md §§1.1, 2.1-2.4).

path_blocks() returns the list-of-dicts block model consumed by docx_li /
report_builder: ALL-CAPS Heading 2, Numbered-Paragraph body with two spaces
between sentences, and teal LI tables.  The section fingerprints the driving
path to the completion target, profiles near-critical crowding, ranks the true
merge points, and narrates how the driving path moved across updates and why —
all framed as schedule-mechanics observations, with causation and entitlement
reserved to the expert.
"""
from __future__ import annotations

from ..analytics.paths import run_path_analytics


def _fmt(x, nd=1):
    return "—" if x is None else f"{round(x, nd):g}"


def _driving_blocks(pr) -> list[dict]:
    dp = pr["driving"]
    tgt = dp.target.code if dp.target else "the completion target"
    if not dp.steps:
        return [{"type": "np",
                 "text": "A driving path could not be extracted for the latest "
                         f"update ({dp.reason or 'insufficient logic or dates'}).  "
                         "The multi-path analysis is omitted for this run."}]
    agree = ("" if dp.flag_agreement_pct is None else
             f"  The recovered path agrees with the tool's own longest-path flag "
             f"on {dp.flag_agreement_pct:.0f}% of flagged activities"
             + (f", disagreeing at {', '.join(dp.flag_disagreements[:6])}"
                if dp.flag_disagreements else "") + ".")
    blocks = [
        {"type": "np",
         "text": f"The driving path to {tgt} was recovered by a backward walk "
                 "through satisfied relationships — those whose predecessor date "
                 "plus lag lands, within a "
                 f"{dp.tolerance_hours:g}-hour tolerance, on the successor's "
                 "controlling date (actual dates governing started work).  The "
                 f"path comprises {len(dp.steps)} activities and is fingerprinted "
                 f"below with the relationship driving each step." + agree},
    ]
    rows = [["Activity", "Name", "Drives Next", "Calendar", "Constraint",
             "Total Float (d)", "% Comp."]]
    for st in dp.steps:
        rel = (f"{st.driving_rel.rtype.value} {st.lag_hours:+g}h"
               if st.driving_rel else "target")
        rows.append([st.activity.code, st.activity.name, rel, st.calendar_name,
                     st.constraint or "—", _fmt(st.total_float_days),
                     f"{st.pct_complete:.0f}"])
    blocks.append({"type": "table", "font_sz": 15, "rows": rows})
    return blocks


def _proximity_blocks(pr) -> list[dict]:
    prox = pr["proximity"]
    bands = prox.get("bands", {})
    if not bands:
        return []
    parts = []
    for band, d in bands.items():
        parts.append(f"{d['paths']} path(s) and {d['activities']} activity(ies) "
                     f"within {band} working days")
    return [
        {"type": "np",
         "text": "Path proximity profile.  The following counts near-critical "
                 "crowding around the driving path — the number of distinct paths "
                 "and activities whose relative float sits within each band of the "
                 "target.  A schedule with many paths inside a tight band is "
                 "volatile: small slips can swap which path controls completion, "
                 "which bears on the reliability of any single-path narrative.  "
                 + "; ".join(parts) + "."},
    ]


def _merge_blocks(pr) -> list[dict]:
    merges = pr["merges"]
    if not merges:
        return []
    blocks = [
        {"type": "np",
         "text": "True merge-point ranking.  Merge points are ranked by the "
                 "number of distinct near-critical predecessor chains that "
                 "converge on them — not by raw predecessor count — with "
                 "tightness given by the least float among those chains.  These "
                 "are the nodes where the completion date is most fragile and "
                 "where concurrent slippage would compound."},
    ]
    rows = [["Merge Activity", "Name", "Converging Near-Critical Chains",
             "Tightness — Min Float (d)", "Predecessors"]]
    for m in merges:
        rows.append([m.code, m.activity.name, str(m.converging_chains),
                     _fmt(m.tightness_days), ", ".join(m.predecessor_codes)])
    blocks.append({"type": "table", "font_sz": 15, "rows": rows})
    return blocks


def _stability_blocks(pr) -> list[dict]:
    stab = pr["stability"]
    if not stab:
        return []
    blocks = [
        {"type": "np",
         "text": "Path stability across updates.  For each consecutive update "
                 "pair the driving-path membership is compared by activity code "
                 "and every change is attributed, from the change register, to a "
                 "progress cause (status, actual, or forecast-date movement) or a "
                 "revision cause (logic, constraint, duration, or calendar edits).  "
                 "This separation is the skeleton of a windows analysis and is "
                 "presented as a mechanical attribution; it is not an opinion on "
                 "causation or entitlement, which are reserved to the expert."},
    ]
    rows = [["Update Pair", "Overlap", "Joined", "Left", "Attribution"]]
    for p in stab:
        jac = "—" if p.jaccard is None else f"{p.jaccard:.0%}"
        attribution = "  ".join(p.causes) if p.causes else "—"
        rows.append([f"{p.earlier_label} → {p.later_label}", jac,
                     ", ".join(p.joined) or "—", ", ".join(p.left) or "—",
                     attribution])
    blocks.append({"type": "table", "font_sz": 15, "rows": rows})
    return blocks


def path_blocks(series_analysis, paths_results=None) -> list[dict]:
    """Return the MULTI-PATH ANALYSIS report section as LI block dicts.

    ``paths_results`` may be a prebuilt bundle from run_path_analytics(); if
    None it is computed here.  Returns at least the heading so the section is
    always present; degrades to a single explanatory paragraph when no driving
    path can be recovered."""
    pr = paths_results or run_path_analytics(series_analysis)
    blocks: list[dict] = [{"type": "h2", "text": "MULTI-PATH ANALYSIS"}]
    blocks += _driving_blocks(pr)
    blocks += _proximity_blocks(pr)
    blocks += _merge_blocks(pr)
    blocks += _stability_blocks(pr)
    return blocks
