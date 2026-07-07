"""RC3/RC4 — render a FileCard/SeriesCard (scorecard.py) as LI report blocks.

Layout follows docs/REPORT_CARD_DESIGN.md §5: an overall grade line, a
category table (grade, score, and a trend arrow against the prior update
where one exists), any gates tripped, a "top factors" reason-code table, and
a coverage/spec-version footer.  Never raises: report_builder.py wraps the
call in a guarded try/except (matching every other additive report section
in this codebase), so a card-rendering bug can never sink a report.
"""
from __future__ import annotations

from ..scorecard import FileCard, SeriesCard, load_spec

_ARROW_UP = "▲"
_ARROW_DOWN = "▼"
_ARROW_DOWN2 = "▼▼"
_ARROW_FLAT = "–"


def _grade_letter(score: float, spec: dict) -> str:
    for band in spec["grade_bands"]["bands"]:
        if score >= band["min"]:
            return band["letter"]
    return "F"


def _arrow(prior: float | None, current: float | None) -> str:
    if prior is None or current is None:
        return "new"
    d = current - prior
    if d >= 3:
        return _ARROW_UP
    if d <= -10:
        return _ARROW_DOWN2
    if d <= -3:
        return _ARROW_DOWN
    return _ARROW_FLAT


def _gate_lines(gates: list) -> list[dict]:
    blocks = []
    for g in gates:
        caps = "; ".join(f"{cid} capped {cap}" for cid, cap in g.category_caps.items())
        line = f"GATE TRIPPED: {g.name} ({g.rule_text}) -> {caps}"
        if g.overall_cap is not None:
            line += f"; overall capped {g.overall_cap:g}"
        blocks.append({"type": "np", "text": line})
    return blocks


def _category_table(categories: list, spec: dict, prior_categories: dict | None) -> dict:
    rows = [["Category", "Grade", "Score", "Trend"]]
    for c in categories:
        if c.score is None:
            rows.append([c.name, "—", "—", "–"])
            continue
        letter = _grade_letter(c.score, spec)
        if c.gate_cap is not None:
            letter += "  GATE"
        prior_score = (prior_categories or {}).get(c.id)
        rows.append([c.name, letter, f"{c.score:.0f}", _arrow(prior_score, c.score)])
    return {"type": "table", "font_sz": 18, "rows": rows}


def _top_factors_table(top_factors: list, name_by_id: dict) -> list[dict]:
    if not top_factors:
        return []
    blocks = [{"type": "np",
              "text": "TOP FACTORS AFFECTING THIS GRADE (points lost of 100 "
                      "attributable to this check; offender count links to the "
                      "results workbook's Findings sheet):"}]
    rows = [["Points Lost", "Check", "Offenders"]]
    for pts, cid, n in top_factors[:12]:
        rows.append([f"-{pts:.1f}", f"{cid}  {name_by_id.get(cid, '')}", str(n)])
    blocks.append({"type": "table", "font_sz": 16, "rows": rows})
    return blocks


def _name_by_id(categories: list) -> dict:
    out = {}
    for c in categories:
        for m in c.members:
            out[m.check_id] = m.name
    return out


def _file_card_blocks(fc: FileCard, spec: dict, prior_fc: FileCard | None,
                      heading: str) -> list[dict]:
    prior_cats = ({c.id: c.score for c in prior_fc.categories} if prior_fc else None)
    blocks: list[dict] = [
        {"type": "h2", "text": heading},
        {"type": "np",
         "text": f"{fc.schedule_label} — profile: {fc.profile}.  "
                 f"OVERALL: {fc.letter}  ({fc.overall:.0f}/100).  Spec "
                 f"{fc.spec_version} · graded {fc.coverage_graded} of "
                 f"{fc.coverage_total} checks."},
    ]
    blocks += _gate_lines(fc.gates)
    blocks.append(_category_table(fc.categories, spec, prior_cats))
    blocks += _top_factors_table(fc.top_factors, _name_by_id(fc.categories))
    if fc.internal_indices:
        rows = [["ID", "Index", "Status"]]
        for idx in fc.internal_indices:
            rows.append([idx["id"], idx["name"], idx["status"]])
        blocks.append({"type": "np",
                       "text": "Internal-variant candidate indices (weight 0 — "
                               "informational placeholders, do not affect the "
                               "grade above):"})
        blocks.append({"type": "table", "font_sz": 16, "rows": rows})
    return blocks


def _series_card_blocks(sc: SeriesCard, spec: dict) -> list[dict]:
    prior_cats = None
    blocks: list[dict] = [
        {"type": "h2", "text": "LI SCHEDULE REPORT CARD — SERIES"},
        {"type": "np",
         "text": f"OVERALL SERIES GRADE: {sc.letter}  ({sc.overall:.0f}/100), "
                 f"{len(sc.file_cards)} update(s).  Spec {sc.spec_version} · "
                 f"graded {sc.coverage_graded} of {sc.coverage_total} series "
                 "checks."},
    ]
    blocks += _gate_lines(sc.gates)
    cats = list(sc.series_categories)
    rows = [["Category", "Grade", "Score", "Trend"]]
    for c in cats:
        if c.score is None:
            rows.append([c.name, "—", "—", "–"])
            continue
        letter = _grade_letter(c.score, spec)
        if c.gate_cap is not None:
            letter += "  GATE"
        rows.append([c.name, letter, f"{c.score:.0f}", "–"])
    if sc.trajectory is not None and sc.trajectory.score is not None:
        t = sc.trajectory
        letter = _grade_letter(t.score, spec)
        slope_word = ("improving" if (t.slope or 0) >= 3 else
                     "deteriorating" if (t.slope or 0) <= -3 else "flat")
        rows.append(["File-Quality Trajectory", letter, f"{t.score:.0f}",
                    f"{slope_word} ({t.slope:+.1f} pts/update)" if t.slope is not None
                    else "single file"])
    blocks.append({"type": "table", "font_sz": 18, "rows": rows})
    blocks += _top_factors_table(sc.top_factors, _name_by_id(cats))
    if sc.internal_indices:
        irows = [["ID", "Index", "Status"]]
        for idx in sc.internal_indices:
            irows.append([idx["id"], idx["name"], idx["status"]])
        blocks.append({"type": "np",
                       "text": "Internal-variant candidate indices (weight 0 — "
                               "informational placeholders, do not affect the "
                               "grade above):"})
        blocks.append({"type": "table", "font_sz": 16, "rows": irows})
    return blocks


def card_blocks(series_card: SeriesCard) -> list[dict]:
    """Render the series card (if this is a multi-file run) followed by the
    latest file card, in the design §5 layout.  A single-file run renders
    the file card only (no series section, per docs/REPORT_CARD_DESIGN.md
    §3's "graded only on what applies")."""
    if not series_card.file_cards:
        return []
    spec = load_spec()
    blocks: list[dict] = []
    if series_card.is_series:
        blocks += _series_card_blocks(series_card, spec)
        latest, prior = series_card.file_cards[-1], series_card.file_cards[-2]
        blocks += _file_card_blocks(
            latest, spec, prior,
            "LI SCHEDULE REPORT CARD — LATEST FILE (" + latest.schedule_label + ")")
    else:
        blocks += _file_card_blocks(
            series_card.file_cards[-1], spec, None, "LI SCHEDULE REPORT CARD")
    return blocks
